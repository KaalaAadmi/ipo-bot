import time
import re
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

def parse_ipo_date_range(date_range_str):
    """
    Parses IPO date ranges like:
      - '10th – 14th Oct 2025'
      - '30th Oct 2025 – 03rd Nov 2025'
      - '29th – 31st Oct 2025'
      - '10th Oct 2025' (single-day IPO)
    Returns: (start_date_iso, end_date_iso) or (None, None)
    """

    if not date_range_str or date_range_str.strip() in ["–", "-", "To be announced", ""]:
        return None, None

    text = date_range_str.strip()

    # Regex for all possible formats
    # 1️⃣ Cross-month: 30th Oct 2025 – 03rd Nov 2025
    pattern_cross = r'(\d+)(?:st|nd|rd|th)?\s+([A-Za-z]{3,})\s+(\d{4})\s*[–-]\s*(\d+)(?:st|nd|rd|th)?\s+([A-Za-z]{3,})\s+(\d{4})'
    # 2️⃣ Same-month: 29th – 31st Oct 2025
    pattern_same = r'(\d+)(?:st|nd|rd|th)?\s*[–-]\s*(\d+)(?:st|nd|rd|th)?\s+([A-Za-z]{3,})\s+(\d{4})'
    # 3️⃣ Single date: 10th Oct 2025
    pattern_single = r'(\d+)(?:st|nd|rd|th)?\s+([A-Za-z]{3,})\s+(\d{4})'

    start_date = end_date = None

    # Helper function to convert date components to ISO format
    def to_iso(day, month_str, year):
        try:
            month_num = datetime.datetime.strptime(month_str, '%b').month
        except ValueError:
            month_num = datetime.datetime.strptime(month_str, '%B').month
        return datetime.date(int(year), month_num, int(day)).isoformat()

    try:
        if re.search(pattern_cross, text):
            # Case 1: 30th Oct 2025 – 03rd Nov 2025
            m = re.search(pattern_cross, text)
            d1, m1, y1, d2, m2, y2 = m.groups()
            start_date = to_iso(d1, m1, y1)
            end_date = to_iso(d2, m2, y2)

        elif re.search(pattern_same, text):
            # Case 2: 29th – 31st Oct 2025
            m = re.search(pattern_same, text)
            d1, d2, mth, yr = m.groups()
            start_date = to_iso(d1, mth, yr)
            end_date = to_iso(d2, mth, yr)

        elif re.search(pattern_single, text):
            # Case 3: 10th Oct 2025
            m = re.search(pattern_single, text)
            d1, mth, yr = m.groups()
            start_date = to_iso(d1, mth, yr)
            end_date = start_date

        else:
            print(f"DEBUG: Date parsing failed for string: '{text}'")
            return None, None

    except Exception as e:
        print(f"Error creating date object for '{date_range_str}': {e}")
        return None, None

    return start_date, end_date

def parse_listing_date(listing_date_str):
    """
    Parses listing date strings like '06 Nov 2025' or '17th Oct 2025' into an ISO date string (YYYY-MM-DD).
    Returns None if parsing fails or if the date is 'To be announced' / '-'.
    """
    import re, datetime

    # Handle missing or placeholder dates
    if not listing_date_str or listing_date_str.strip() in ["–", "-", "To be announced", ""]:
        return None

    # Remove ordinal suffixes (st, nd, rd, th)
    clean_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', listing_date_str.strip())

    # Pattern for standard format: '06 Nov 2025'
    match = re.search(r'(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})', clean_str)
    if not match:
        print(f"DEBUG: Could not parse listing date string: '{listing_date_str}'")
        return None

    day, month_str, year = match.groups()

    try:
        # Convert month abbreviation to number
        month_num = datetime.datetime.strptime(month_str, "%b").month
    except ValueError:
        try:
            month_num = datetime.datetime.strptime(month_str, "%B").month
        except ValueError:
            print(f"Error: Could not parse month string '{month_str}' in '{listing_date_str}'.")
            return None

    try:
        listing_date = datetime.date(int(year), month_num, int(day)).isoformat()
        return listing_date
    except ValueError as e:
        print(f"Error creating listing date for '{listing_date_str}': {e}")
        return None

# --- MODIFIED SCRAPING FUNCTION ---
def scrape_live_ipos():
    """
    Scrapes the Upcoming IPO data from the Zerodha IPO page, matching the URL fragment.
    Handles driver initialization, scraping, and cleanup.
    """
    url = "https://zerodha.com/ipo/"
    driver = None # Initialize driver to None for the finally block
    
    print("Starting WebDriver...")

    # --- Chrome Options Setup ---
    chrome_options = Options()
    
    # Adding the large window size is key for ensuring desktop layout loads
    # and avoiding mobile card scraping logic (which the previous fix attempted).
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-extensions")
    
    data = []
    
    try:
        driver = webdriver.Chrome(options=chrome_options) 
        # Increase the wait time to 20 seconds for robustness against slow loading
        wait = WebDriverWait(driver, 20) 
        
        print(f"Opening URL: {url}")
        driver.get(url)
        
        # --- Corrected Logic for Upcoming IPOs (Targeting #tab-upcoming-ipo) ---
        UPCOMING_IPO_TAB_ID = "#tab-upcoming-ipo"
        ITEM_SELECTOR = f".ipo-list-item"

        # 1. Check for "No Upcoming IPOs" (Keep this check as requested)
        try:
            # Check if the "No IPOs" message is visible within the Upcoming tab
            no_ipo_message = driver.find_elements(
                By.XPATH, f"{UPCOMING_IPO_TAB_ID}//div[contains(text(), 'There are no upcoming IPOs right now.')]"
            )
            if len(no_ipo_message) > 0:
                print("No upcoming IPOs available. Returning empty list.")
                return []
        except Exception:
            # Ignore if the element is not found
            pass 
        
        # 2. Wait for and find the IPO list items
        # Use visibility_of_all_elements_located for dynamic content
        ipo_elements = WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#live-ipo-table tbody tr"))
        )

            
        # 3. Iterate and extract data using precise CSS selectors (Fixed selectors)
        for item in ipo_elements:
            try:
                cells = item.find_elements(By.TAG_NAME, "td")

                # Extract link and stock name
                link_elem = cells[1].find_element(By.TAG_NAME, "a")
                link = link_elem.get_attribute("href").strip()
                stock_name = link_elem.text.strip().split("\n")[0]  # First line of text (symbol)

                # Extract date range and listing date
                ipo_date_range = cells[2].text.strip()
                listing_date_raw = cells[3].text.strip()
                start_date, end_date = parse_ipo_date_range(ipo_date_range)
                listing_date = parse_listing_date(listing_date_raw)  # Only need the start date for listing
                data.append({
                    "stock_name": stock_name,
                    "ipo_date_range": ipo_date_range,
                    "start_date": start_date,
                    "end_date": end_date,
                    "listing_date": listing_date,
                    "link": link,
                })
                
            except NoSuchElementException as e:
                print(f"Error: Missing expected data element in an IPO item. Skipping. Error: {e}")
                continue
            except Exception as e:
                print(f"Error scraping an IPO item: {e}")
                continue

        return data

    except TimeoutException:
        print(f"Timeout (20s) waiting for Upcoming IPO list items: {ITEM_SELECTOR}")
        return data

    except Exception as e:
        print(f"A major error occurred during scraping: {e}")
        return data

    finally:
        # Ensure the driver is closed
        if driver:
            print("Closing WebDriver...")
            driver.quit()
    
    pass


# --- MODIFIED EXECUTION BLOCK ---
if __name__ == '__main__':
    
    # The scraping function now handles driver initialization and closure
    try:
        live_ipos = scrape_live_ipos()
        print(live_ipos)
    except Exception as e:
        print(f"A final error occurred during script execution: {e}")
    
    pass