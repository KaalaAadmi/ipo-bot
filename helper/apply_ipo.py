from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import dotenv_values
# from .ai_info import resolve_application_row_name
# from .email_helper import get_gmail_service, get_otp_from_email
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException, UnexpectedAlertPresentException, NoAlertPresentException

import requests
import json
from time import sleep
import os
import re # Import regex for flexible string matching
import sys

# Support running as a script and as a module
if __package__ is None or __package__ == "":
    # Running directly: add project root to sys.path so 'helper' package is importable
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from helper.ai_info import resolve_application_row_name
    from helper.email_helper import get_gmail_service, get_otp_from_email
else:
    # Running via: python -m helper.apply_ipo
    from .ai_info import resolve_application_row_name
    from .email_helper import get_gmail_service, get_otp_from_email
# --- Configuration ---
# Note: For standalone testing, ensure a .env file is present or this will raise a FileNotFoundError/IOError.
config = dotenv_values(".env")
HDFC_USER=config.get("HDFC_USER")
HDFC_PASSWORD=config.get("HDFC_PASSWORD")
DP_NAME=config.get("DP_NAME")
DP_NO=config.get("ZERODHA_DP_NO")
DOB=config.get("DOB")

# --- Helper Functions ---
def _xpath_literal(s: str) -> str:  # NEW - safe string literal for XPath
    if "'" not in s:
        return f"'{s}'"
    if '"' not in s:
        return f'"{s}"'
    # Handle strings with both quote types: concat('a',"'",'b')
    parts = s.split("'")
    return "concat(" + ", ".join([f"'{p}'" if i == len(parts) - 1 else f"'{p}', \"'\", "
                                  for i, p in enumerate(parts)]) + ")"

def _scrape_first_column_names_in_current_frame(driver, wait):  # NEW
    """
    Scrape first-column text values from the IPO table rows in the current frame.
    Assumes we've already switched to Frame14.
    """
    rows = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//table//tr[td]")))
    names = []
    for r in rows:
        tds = r.find_elements(By.TAG_NAME, "td")
        if not tds:
            continue
        name = (tds[0].text or "").strip()
        if name:
            names.append(name)
    seen, deduped = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    return deduped

def _find_apply_link_for_name(wait, resolved_name):  # NEW
    """
    Strategy A: Find the row by first-column text, then its Apply link.
    """
    name_lit = _xpath_literal(resolved_name)
    xpath = f"//tr[td[normalize-space()={name_lit}]]//a[normalize-space()='Apply']"
    return wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))

def _find_apply_link_by_onclick(wait, resolved_name):  # NEW
    """
    Strategy B: Match <a> by its onclick second argument (the display name).
    Handles both \", 'NAME'\" and \",'NAME'\" variants.
    """
    name_lit = _xpath_literal(resolved_name)
    # Build contains substrings as string literals for XPath
    contains_1 = f"contains(@onclick, concat(', ', {name_lit}))"
    contains_2 = f"contains(@onclick, concat(',', {name_lit}))"
    xpath = f"//a[normalize-space()='Apply' and ({contains_1} or {contains_2})]"
    return wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))

def _accept_alert_if_present(driver, wait, timeout: int = 5) -> bool:  # NEW
    """Accepts alert if present; returns True if an alert was accepted."""
    try:
        alert = WebDriverWait(driver, timeout).until(EC.alert_is_present())
        try:
            text = alert.text
            print(f"Alert present: {text[:200]}...")
        except Exception:
            pass
        alert.accept()
        print("Alert accepted.")
        sleep(1)
        return True
    except TimeoutException:
        return False
    except Exception:
        # Fallback direct switch
        try:
            driver.switch_to.alert.accept()
            print("Alert accepted (fallback).")
            sleep(1)
            return True
        except Exception:
            return False

# --- Function to Handle IPO Application Selection ---
def apply_for_ipo_general_category(driver, wait, base_ipo_name):
    """
    Switches to Frame14, resolves the IPO row name, and clicks the Apply link.
    Uses two strategies to locate the Apply button.
    """
    try:
        driver.switch_to.frame(frame_reference="Frame14")
        print("Switched to Frame14.")
    except Exception as e:
        print(f"Failed to switch to Frame14: {e}")
        return False

    try:
        page_names = _scrape_first_column_names_in_current_frame(driver, wait)
        if not page_names:
            print("No IPO names found in table.")
            return False
        print(f"Found {len(page_names)} IPO rows.")

        resolved_name = resolve_application_row_name(base_ipo_name, page_names)
        print(f"Resolved IPO row name: '{resolved_name}' (from target '{base_ipo_name}')")

        # Try Strategy A: by row name
        try:
            apply_link = _find_apply_link_for_name(wait, resolved_name)
            print(f"Found Apply link via row-match for '{resolved_name}'.")
        except TimeoutException:
            # Try Strategy B: by onclick second argument
            print("Primary locator failed. Trying onclick-based locator...")
            apply_link = _find_apply_link_by_onclick(wait, resolved_name)
            print(f"Found Apply link via onclick for '{resolved_name}'.")

        # Scroll into view and click
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", apply_link)
        try:
            apply_link.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", apply_link)
        print("Clicked 'Apply' link.")
        return True

    except TimeoutException:
        print("Timeout: Apply link not found for resolved row after waiting.")
        # Debug aid: print all Apply onclicks to help refine locator
        try:
            anchors = driver.find_elements(By.XPATH, "//a[normalize-space()='Apply']")
            print("Visible 'Apply' anchors and their onclicks:")
            for a in anchors:
                print(a.get_attribute("onclick"))
        except Exception:
            pass
        return False
    except NoSuchElementException:
        print("Element not found for resolved row.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during selection: {e}")
        return False
    finally:
        driver.switch_to.default_content()
        
# --- Main IPO Application Function (Renamed for main.py compatibility) ---
def apply_ipo(ipo_name):
    """
    Initiates the IPO application process using Selenium.
    
    :param ipo_name: The name of the IPO to apply for (e.g., "MIDWEST LIMITED").
    :return: True if the application process was successfully initiated, False otherwise.
    """
    driver = None
    try:
        # Configure Chrome options
        options = Options()
        # TODO: uncomment the headless option for production use
        # options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.set_capability("unhandledPromptBehavior", "accept")
        # Initialize the WebDriver
        # Note: Replace with your actual Service path if needed
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 10)
        
        # --- Login and Navigation Steps (unchanged from your original code) ---
        
        driver.get("https://now.hdfcbank.com/auth/realms/retail/protocol/openid-connect/auth?response_type=code&client_id=bb-web-client&state=U0VzZWRwMGlUY0pkSHB-dnZacmFNSU5PT3ludllkQkpWUmwyZ0FabWZCNFhu&redirect_uri=https%3A%2F%2Fnow.hdfcbank.com%2Fretail-app%2Fselect-context&scope=openid&code_challenge=yuYD7Fs2ZgKCrEZspAVuP8v2FfRuP_lwgiHuEkJUq4E&code_challenge_method=S256&nonce=U0VzZWRwMGlUY0pkSHB-dnZacmFNSU5PT3ludllkQkpWUmwyZ0FabWZCNFhu&refNo=e4c157ba99c91e7e0199decb433f6cea&acr_values=l5")
        sleep(2)
        login_frame_id = "kc-form-login"
        wait.until(
            EC.presence_of_element_located((By.ID, login_frame_id))
        )
        
        sleep(4)
        
        print("Login frame found. Proceeding with login...")
        username=driver.find_element(By.ID,"username")
        username.send_keys(HDFC_USER)
        password=driver.find_element(By.ID,"password")
        password.send_keys(HDFC_PASSWORD)
        password.send_keys(Keys.ENTER)
        sleep(5)
        
        try:
            request_otp_dialog=driver.find_element(By.ID, "channel-BOTH")
            wait.until(
                EC.presence_of_element_located((By.ID, "channel-BOTH"))
            )
            radio_id = "channel-BOTH"
            radio_click=driver.find_element(By.ID, radio_id)
            radio_click.click()
            radio_click.send_keys(Keys.ENTER)

            print("Attempting to request OTP...")
            # mfa_btn_id="mfa-get-otp-btn"
            # mfa_btn=driver.find_element(By.ID,mfa_btn_id)
            # mfa_btn.click()
            print("OTP requested. Waiting to receive OTP email...")

            print("--- Attempting to retrieve OTP from email ---")
            # 1. Get the Gmail API service object
            gmail_service = get_gmail_service()

            # 2. Define the email subject to search for
            OTP_EMAIL_SUBJECT = "View: Account update for your HDFC Bank A/c"

            # 3. Get the OTP
            otp_code = None
            if gmail_service:
                # This function includes a 10-second wait before the first search
                # and a 5-second retry if the email is not immediately found.
                otp_code = get_otp_from_email(gmail_service, OTP_EMAIL_SUBJECT, sender_email="alerts@hdfcbank.net")

            if not otp_code:
                print("FATAL: Could not retrieve OTP. Exiting automation.")
                driver.quit()
                exit(1)
            print(f"Retrieved OTP: {otp_code}")
                
            sleep(10) # Wait for manual 2FA input

            print("Entering OTP...")
            actions = ActionChains(driver)
            actions.send_keys(otp_code)
            actions.send_keys(Keys.ENTER)
            actions.perform()

            print("OTP submitted. Waiting for dashboard...")
        except NoSuchElementException:
            print("Request OTP dialog not found.")
        finally:    
            try:
                dashboard_header_class = "bb-heading-widget__heading"
                wait.until(
                    EC.presence_of_element_located((By.CLASS_NAME, dashboard_header_class))
                )
                investments_menu=driver.find_element(By.ID,"bb-menu-header-investment-button")
                investments_menu.click()
                print("Investments menu opened.")
                ipo_option=driver.find_element(By.XPATH,"//*[@id=\"investment-menu-dropdown\"]/ul/li[4]/a")
                ipo_option.click()
                print("IPO option selected.")

                sleep(5)
                actions1 = ActionChains(driver)
                actions1.send_keys(Keys.TAB)
                actions1.pause(1)
                actions1.send_keys(Keys.ENTER)
                actions1.pause(1)
                actions1.send_keys(Keys.ENTER)
                actions1.pause(1)
                actions1.send_keys(Keys.TAB)
                actions1.pause(1)
                actions1.send_keys(Keys.TAB)
                actions1.pause(1)
                actions1.send_keys(Keys.ENTER)
                actions1.pause(1)
                actions1.perform()

                print("Proceeded to next step.")

                wait.until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME,"demat-landing-container"))
                )
                print("Demat accounts loaded.")
                actions3= ActionChains(driver)
                actions3.send_keys(Keys.TAB)
                actions3.pause(1)
                actions3.send_keys(Keys.SPACE)
                actions3.pause(1)
                actions3.send_keys(Keys.SPACE)
                actions3.pause(1)
                actions3.send_keys(Keys.SPACE)
                actions3.pause(1)
                actions3.send_keys(Keys.TAB)
                actions3.pause(1)
                actions3.send_keys(Keys.TAB)
                actions3.pause(1)
                actions3.send_keys(Keys.TAB)
                actions3.pause(1)
                actions3.send_keys(Keys.TAB)
                actions3.pause(1)
                actions3.send_keys(Keys.ENTER)
                actions3.pause(3)
                actions3.send_keys(Keys.ENTER)
                actions3.pause(1)
                actions3.perform()
                print("Checkbox selected.")

                sleep(10) #wait for the new tab to open
                
                # switch to the new tab or the tab with the title containint "HDFC Securities Limited - Online IPO"
                print(f"Window title(Before switching): {driver.title}")
                
                # Wait for a second window handle to be available
                wait.until(EC.number_of_windows_to_be(2))
                driver.switch_to.window(driver.window_handles[1])
                print(f"Current window title(After switching): {driver.title}")
                
                actions4= ActionChains(driver)
                actions4.send_keys(Keys.TAB)
                actions4.pause(1)
                actions4.send_keys(Keys.TAB)
                actions4.pause(1)
                actions4.send_keys(Keys.TAB)
                actions4.pause(1)
                actions4.send_keys(Keys.ENTER)
                actions4.pause(10)
                actions4.perform()
                
                print("Navigated to IPO application page.")
                
                sleep(10)
                
                success = apply_for_ipo_general_category(driver, wait, ipo_name)
                
                sleep(2)
                
                # Dismiss ASBA/info alert if it pops on load
                _accept_alert_if_present(driver, wait, timeout=5)
                if success:
                    print("Successfully initiated IPO application for GENERAL category.")
                else:
                    print("Failed to initiate IPO application.")
                    
                print("Waiting for the IPO order form page to load...")
                sleep(5)
                
                get_frame = driver.find_element(By.ID, "Frame14")
                driver.switch_to.frame(get_frame)
                print("Switched to Frame14.")

                wait.until(
                    # Wait for the first key element inside the frame to be present
                    EC.presence_of_element_located((By.ID, "CDSL"))
                )
                print("IPO order form loaded.")

                # --- Modification 1: Use JavaScript click for Radio Button ---
                # This method is more reliable for styled/hidden radio buttons.
                depository_select = driver.find_element(By.ID, "CDSL")
                driver.execute_script("arguments[0].click();", depository_select)
                print("Depository selected as CDSL using robust click.")

                # --- Input fields remain correct ---
                dp_name = driver.find_element(By.NAME, "DP_NAME")
                # Assuming DP_NAME is defined elsewhere and contains the value
                dp_name.send_keys(Keys.CONTROL, 'a')  # Select all existing text
                dp_name.send_keys(Keys.BACKSPACE)     # Clear the field
                dp_name.send_keys(Keys.DELETE)
                dp_name.send_keys(DP_NAME)
                print("DP Name entered.")

                dp_acc_no = driver.find_element(By.NAME, "dpAccNo")
                # Assuming DP_NO is defined elsewhere and contains the value
                dp_acc_no.send_keys(DP_NO)
                print("DP Account Number entered.")

                dob = driver.find_element(By.NAME, "DOB_1")
                # Assuming DOB is defined elsewhere and contains the value
                dob.send_keys(DOB)
                print("DOB entered.")

                # --- Modification 2: Use JavaScript click for Checkbox ---
                checkbox = driver.find_element(By.ID, "ipoTncCheckbox")
                driver.execute_script("arguments[0].click();", checkbox)
                print("Terms and conditions checkbox selected using robust click.")


                # --- Uncomment and correct the locator for the submit button if needed ---
                submit_btn = wait.until(EC.element_to_be_clickable((By.NAME, "submit11")))
                submit_btn.click()
                print("IPO application submitted.")
                sleep(5)
                # confirmtable
                wait.until(EC.element_to_be_clickable((By.NAME, "confirmtable")))
                confirm_btn=driver.find_element(By.ID,"submit1")
                confirm_btn.click()
                print("Confirmed submission dialog.")
                sleep(5)
                print("IPO application process completed.")
                success_msg=driver.find_element(By.XPATH,"/html/body/form/table/tbody/tr[1]/td/b/p").text
                print(f"Application Result Message: {success_msg}")
                sleep(5)
                get_frame = driver.find_element(By.ID, "Frame13")
                driver.switch_to.frame(get_frame)
                
                sleep(60)
                # --- Modification 3: Switch back to default content (Crucial if the Submit button is outside) ---
                driver.switch_to.default_content()
                print("Switched back to default content.")
            
                return success  # was: return True
            
            except Exception as e:
                print(f"An error occurred during navigation/application: {e}")
                return False
        
    except Exception as e:
        print(f"An error occurred: {e}")
        # Ensure the driver is active before attempting logout
        if driver and driver.window_handles:
            # Switch to the primary window if needed
            if len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[0])
                
            try:
                logout=driver.find_element(By.CLASS_NAME,"logout-icon") # Placeholder class name
                logout.click()
                sleep(1)
                actions2 = ActionChains(driver)
                actions2.send_keys(Keys.ENTER)
                actions2.pause(2)
                actions2.perform()
                sleep(5)
                print("Logged out.")
            except:
                print("Could not find or execute logout.")
        return False # Function must return False on exception

    finally:
        print("Automation script completed.")
        # Optionally close the browser
        if driver:
            driver.quit()

# --- Test Block for Standalone Execution ---

if __name__ == "__main__":
    
    # --- IMPORTANT NOTE FOR TESTING ---
    # This standalone test will LIKELY FAIL unless you have:
    # 1. A valid `.env` file with HDFC_USER and HDFC_PASSWORD.
    # 2. ChromeDriver installed and accessible in your system PATH.
    # 3. The `email_test.py` file available with the correct functions.
    # 
    # This block is purely to demonstrate the function's signature and expected boolean return.
    
    print("--- Running standalone test for apply_ipo function ---")
    
    # Use a dummy IPO name for testing the function call
    TEST_IPO_NAME = "STUDDS" 
    
    # Call the main function
    success = apply_ipo(TEST_IPO_NAME)
    
    if success:
        print(f"\nTest Result: IPO application for '{TEST_IPO_NAME}' returned SUCCESS (True).")
    else:
        print(f"\nTest Result: IPO application for '{TEST_IPO_NAME}' returned FAILURE (False).")
    
    print("-----------------------------------------------------")
