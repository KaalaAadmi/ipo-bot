from scrapers.ipo_scraper import scrape_live_ipos
from scrapers.ipo_analysis_scraper import scrape_ipo_analysis
from scrapers.ipo_subscription_scraper import get_ipo_subscription
from helper.ai_info import get_ipo_decision
# from helper.mongo_connector import upsert_ipo_status, get_ipo_db_record, update_ipo_applied_status 
from helper.mongo_connector import (
    upsert_ipo_status,
    get_ipo_db_record_by_keys,  # NEW
    is_ipo_applied,             # NEW
    update_ipo_applied_status
)
from helper.google_calendar import get_calendar_service, create_or_update_ipo_event 
from helper.apply_ipo import apply_ipo 
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # NEW
import os
import re

def _now_ist():  # NEW
    return datetime.now(tz=IST)

def _parse_date_maybe(value):  # NEW - robust parsing for end date
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "date"):
        try:
            return value.date()
        except Exception:
            pass
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    # last-gasp: try stripping trailing time
    try:
        return datetime.fromisoformat(s.split("T")[0]).date()
    except Exception:
        return None

def _is_last_day(end_date_like):  # NEW
    end_date = _parse_date_maybe(end_date_like)
    if not end_date:
        return False
    return end_date == _now_ist().date()

def _is_after_noon():  # NEW
    return _now_ist().hour >= NOON_CUTOFF_HOUR

def _parse_sub_x(value):  # NEW - parse "12.3x" -> 12.3
    if value is None:
        return 0.0
    s = str(value).lower().replace("x", " ").strip()
    m = re.search(r"([0-9]+(\.[0-9]+)?)", s)
    try:
        return float(m.group(1)) if m else 0.0
    except Exception:
        return 0.0

def _subscription_is_good(sub_snapshot) -> bool:  # NEW
    if not isinstance(sub_snapshot, dict):
        return False
    total = _parse_sub_x(sub_snapshot.get("Total"))
    qib = _parse_sub_x(sub_snapshot.get("QIB"))
    nii = max(
        _parse_sub_x(sub_snapshot.get("NII")),
        _parse_sub_x(sub_snapshot.get("SHNI")),
        _parse_sub_x(sub_snapshot.get("BHNI")),
    )
    rii = _parse_sub_x(sub_snapshot.get("RII"))
    return (
        total >= SUB_THRESHOLDS["TOTAL"]
        or qib >= SUB_THRESHOLDS["QIB"]
        or nii >= SUB_THRESHOLDS["NII"]
        or rii >= SUB_THRESHOLDS["RII"]
    )
    
IST = ZoneInfo("Asia/Kolkata")  # NEW
NOON_CUTOFF_HOUR = int(os.getenv("IPO_NOON_CUTOFF_HOUR", "12"))  # NEW
SUB_THRESHOLDS = {  # NEW - can be tuned via env vars
    "TOTAL": float(os.getenv("IPO_SUB_TOTAL_X", "10")),
    "QIB": float(os.getenv("IPO_SUB_QIB_X", "10")),
    "NII": float(os.getenv("IPO_SUB_NII_X", "5")),
    "RII": float(os.getenv("IPO_SUB_RII_X", "1")),
}

# --- Helper Function for Data Consolidation (Retained from previous fix for schema) ---
def consolidate_data(decisions, subscriptions, ipo_data_map):
    """
    Merges IPO decision, raw IPO data (for dates), and subscription data into a nested structure.
    """
    sub_map = {item["Name"]: item for item in subscriptions}
    
    for decision in decisions:
        ipo_name = decision["LiveIPOName"]
        sub_data = sub_map.get(ipo_name, {})
        original_data = ipo_data_map.get(ipo_name, {}) 

        # 1. CREATE THE NESTED DICTIONARY 
        subscription_details = {
            "Total": sub_data.get("Total", "N/A"),
            "QIB": sub_data.get("QIB", "N/A"),
            "SHNI": sub_data.get("SHNI", "N/A"),
            "BHNI": sub_data.get("BHNI", "N/A"),
            "NII": sub_data.get("NII", "N/A"),
            "RII": sub_data.get("RII", "N/A"),
            "IPO Size": sub_data.get("IPO Size", "N/A"),
            "IPO Price": sub_data.get("IPO Price", "N/A"),
            "P/E": sub_data.get("P/E", "N/A"),
            "Close Date": sub_data.get("Close Date", "N/A"),
            "GMP": sub_data.get("GMP", "N/A"),
        }
        
        # 2. Add the nested dictionary and the corrected dates
        decision["LiveIPOSubscriptionDetails"] = subscription_details
        
        # Add the correctly parsed dates from the scraper's output
        decision['IPO_Start_Date'] = original_data.get('IPO_Start_Date')
        decision['IPO_End_Date'] = original_data.get('IPO_End_Date')
        decision['IPO_Date_Raw'] = original_data.get('IPO_Date_Raw') 

        # 3. Clean up the old flat subscription fields (assuming they were in the original decision object)
        keys_to_delete = ["Total", "QIB", "NII", "RII", "P/E"] 
        for key in keys_to_delete:
            if key in decision:
                del decision[key]

    return decisions

# --- Main Logic ---
def main():
    print("Hello from ipo-bot!")
    
    # 1. Scrape data
    ipos = scrape_live_ipos()
    if len(ipos) == 0:
        print("No live IPOs found. Exiting.")
        return
    ipo_analysis=scrape_ipo_analysis()
    live_ipo_subscriptions =get_ipo_subscription()
    
    if ipos:
        print(f"Successfully scraped {len(ipos)} IPOs.")
    else:
        print("No IPOs found.")
        
    # 2. AI Processing
    try:
        ipo_decisions=get_ipo_decision(ipos, ipo_analysis, live_ipo_subscriptions)
        print(f"AI processed {len(ipo_decisions)} IPO decisions.")
    except Exception as e:
        print(f"Error during AI processing of IPO decisions: {e}")
        return
    print(f"AI IPO Decisions: {ipo_decisions}")
    calendar_service = get_calendar_service()
    
    ipo_map = {i.get("LiveIPOName") or i.get("Name"): i for i in ipos}  # NEW
    analysis_map = {a.get("LiveIPOName") or a.get("Name"): a for a in (ipo_analysis or [])}  # NEW
    sub_map = {s.get("Name") or s.get("LiveIPOName"): s for s in (live_ipo_subscriptions or [])}  # NEW

    # Database and Calendar Automation Loop
    for processed_status in ipo_decisions:
        ipo_name = processed_status["LiveIPOName"]
        recommendation = processed_status["Recommendation"]
        analysis_title = processed_status.get("IPOAnalysisTitle") or "No Analysis Found"  # NEW

        # 7a. Save/Update IPO Status in MongoDB
        # Check if any record for this IPO is already APPLIED (IPO-level flag)
        applied_already = is_ipo_applied(ipo_name)  # NEW
        db_record = get_ipo_db_record_by_keys(ipo_name, analysis_title)  # NEW
        current_db_status = "APPLIED" if applied_already else (db_record.get('AppliedStatus', 'PENDING') if db_record else 'PENDING')  # NEW

        status_to_save = current_db_status if current_db_status == 'APPLIED' else recommendation.upper()
        upsert_ipo_status(processed_status)
        print(f"DB: Updated {ipo_name} status to: {status_to_save}")


        # 7b. Google Calendar Integration (NEW LOGIC)
        # Create a calendar event for any IPO that is NOT 'Avoid'
        if calendar_service and recommendation in ['Apply', 'Review', 'APPLIED']:
            
            # Use the status from the DB for the calendar title if it's APPLIED
            calendar_status_key = current_db_status if current_db_status == 'APPLIED' else recommendation
            
            # The function handles date validation and event creation/update
            create_or_update_ipo_event(
                ipo_data=processed_status, 
                service=calendar_service, 
                status_key=calendar_status_key.upper()
            )
            
        # 2. Application Logic (Only proceed if recommended and not yet applied)
        should_apply = processed_status.get("Recommendation") == "Apply"
        # if should_apply and applied_status == "To_Apply":
            # try:
            #     # TODO: Only apply if it is the last day of the ipo and if either of the following is true:
            #     # - tulsiyan says to apply or
            #     # - the subscription levels are good - exact values to be decided
            #     # if both are true, then definitely apply.
            #     # if only tulsiyan says to apply
            #     # if neither are true, then do not apply.
        if should_apply and current_db_status != "APPLIED":
            # Resolve end-date and subscription snapshot
            ipo_row = ipo_map.get(ipo_name, {})
            analysis_row = analysis_map.get(ipo_name, {})
            sub_snapshot = processed_status.get("LiveIPOSubscriptionDetails") or sub_map.get(ipo_name) or {}
            end_date_like = (
                processed_status.get("IPO_End_Date")
                or ipo_row.get("IPO_End_Date")
                or (sub_snapshot.get("Close Date") if isinstance(sub_snapshot, dict) else None)
            )

            last_day = _is_last_day(end_date_like)
            after_noon = _is_after_noon()
            subs_good = _subscription_is_good(sub_snapshot)

            # Use AI recommendation as the Tulsiyan signal
            # Previously: tulsiyan_apply = processed_status == "APPLY"  (bug)
            tulsiyan_apply = (recommendation or "").strip().upper() == "APPLY"  # FIX

            if not end_date_like:
                print(f"SKIP auto-apply for {ipo_name}: missing IPO end date.")
            elif not last_day:
                print(f"SKIP auto-apply for {ipo_name}: not the last day.")
            elif not after_noon:
                print(f"SKIP auto-apply for {ipo_name}: before {NOON_CUTOFF_HOUR}:00 IST.")
            elif not (tulsiyan_apply or subs_good):
                print(f"SKIP auto-apply for {ipo_name}: neither Tulsiyan apply nor strong subscription.")
            else:
                try:
                    print(f"Attempting auto-apply for IPO: {ipo_name} (last day, after noon, "
                          f"tulsiyan={tulsiyan_apply}, subs_good={subs_good})...")
                    application_success = apply_ipo(ipo_name)
                    if application_success:
                        print(f"SUCCESS: Auto-applied for {ipo_name}!")
                        
                        # Update DB and Calendar upon successful application
                        update_ipo_applied_status(ipo_name, "APPLIED")
                        
                        # Update Calendar title with APPLIED status
                        processed_status["AppliedStatus"] = "APPLIED" 
                        create_or_update_ipo_event(processed_status, calendar_service, status_key="APPLIED")
                    else:
                        print(f"FAILURE: Could not auto-apply for {ipo_name}.")
                        # retry again
                        application_success = apply_ipo(ipo_name)
                        if application_success:
                            print(f"SUCCESS on retry: Auto-applied for {ipo_name}!")
                            update_ipo_applied_status(ipo_name, "APPLIED")
                            processed_status["AppliedStatus"] = "APPLIED" 
                            create_or_update_ipo_event(processed_status, calendar_service, status_key="APPLIED")
                        else:
                            print(f"FAILURE on retry: Could not auto-apply for {ipo_name}.")
                except Exception as e:
                    print(f"Error during auto-apply for {ipo_name}: {e}")
    print("\nIPO Bot run complete.")

# def main():
#     print("Hello from ipo-bot!")
    
#     ipos=scrape_live_ipos()
#     print(f"Scraped {len(ipos)} live IPOs.")
#     print(ipos)

if __name__ == "__main__":
    main()