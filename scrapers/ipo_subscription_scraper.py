import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

HEADERS = [
    "Total", "Name", "QIB", "SHNI", "BHNI", "NII", "RII", 
    "IPO Size", "IPO Price", "P/E", "Close Date"
]

def get_ipo_subscription():
    """
    Scrapes live IPO subscription data from the specified URL using Selenium.

    Args:
        url (str): The URL of the Zerodha IPO page.
    """
    url="https://www.investorgain.com/report/ipo-subscription-live/333/all/?page=1&search=search_ipo%253D#table_section"
    print("Starting WebDriver...")

    # --- Chrome Options Setup ---
    chrome_options = Options()
    
    # Keep this commented out for testing, as requested
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    
    ipo_data = [] # List to hold the extracted data dictionaries

    driver = None  # Initialize driver to None

    try:
        # Initialize the WebDriver
        driver = webdriver.Chrome(options=chrome_options) # Use service=service if specifying path
        
        print(f"Opening URL: {url}")
        driver.get(url)
        
        # 1. Wait for the main IPO table element to be visible/present
        # We target the ID of the live IPO table container
        table_container_id = "report_table"
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, table_container_id))
        )
        print("Live IPO table found. Extracting data...")
        
        # 2. Locate all the rows (tr elements) in the main table body
        # We target the desktop view table inside the container
        # Selector: ID -> class container -> table -> tbody -> all rows
        ipo_rows = driver.find_elements(
            By.CSS_SELECTOR, 
            "tr.color-green" # Explicitly targets the <tr> element with the class
        )
        
        print(f"Found {len(ipo_rows)} live IPOs.")
        
        for row in ipo_rows:
            # Locate all the data cells (td elements) within the current row
            cells = row.find_elements(By.TAG_NAME, "td")
            
            # --- Data Cleaning and Mapping ---
            if len(cells) == 12: # Check if a full row of data exists (13 cells: 0 to 12)
                
                # --- A. Total Subscription (Clean Extraction) ---
                # Cell 2 contains the visible Total subscription value (e.g., 0.09)
                total_subscription = cells[1].text.strip().split()[0].strip()
                
                # --- B. Name and GMP Extraction (Cell 1) ---
                name_cell = cells[0].text
                
                # 1. Extract IPO Name: Get the first line, then use regex to clean up 'IPO/BSE SME'
                name_line = name_cell.split('\n')[0]
                name_match = re.match(r"(.+?)\s+(IPO|BSE SME)", name_line, re.IGNORECASE)
                ipo_name = name_match.group(1).strip() if name_match else name_line.strip()
                
                # 2. Extract GMP Info
                gmp_match = re.search(r"GMP:[\S\s]*\)", name_cell)
                gmp_info = gmp_match.group(0).strip() if gmp_match else "N/A"
                
                # --- C. Extracting remaining data (simple text extraction) ---
                # Indices: 3(QIB), 4(SHNI), 5(BHNI), 6(NII), 7(RII), 9(Size), 10(Price), 11(P/E), 12(Date)
                clean_data_values = [
                    cells[2].text.strip(),  # QIB
                    cells[3].text.strip(),  # SHNI
                    cells[4].text.strip(),  # BHNI
                    cells[5].text.strip(),  # NII
                    cells[6].text.strip(),  # RII
                    # cells[7].text.strip(),  # Anchor (Skipping)
                    cells[8].text.strip(),  # IPO Size
                    cells[9].text.strip(),  # IPO Price
                    cells[10].text.strip(), # P/E
                    cells[11].text.strip(), # Close Date
                ]
                
                # Final list of data for mapping (11 items + GMP)
                final_data = [total_subscription, ipo_name] + clean_data_values + [gmp_info]
                
                # Create a dictionary, mapping headers to data
                full_headers = HEADERS + ["GMP"]
                
                if len(full_headers) == len(final_data):
                    ipo_dict = dict(zip(full_headers, final_data))
                    ipo_data.append(ipo_dict)
                    
                    # Debug print for verification
                #     print("-" * 50)
                #     print(f"Total: {ipo_dict['Total']}")
                #     print(f"Name: {ipo_dict['Name']}")
                #     print(f"QIB: {ipo_dict['QIB']}, SHNI: {ipo_dict['SHNI']}, BHNI: {ipo_dict['BHNI']}")
                #     print(f"NII: {ipo_dict['NII']}, RII: {ipo_dict['RII']}")
                #     print(f"Size: {ipo_dict['IPO Size']}, Price: {ipo_dict['IPO Price']}, P/E: {ipo_dict['P/E']}")
                #     print(f"Close Date: {ipo_dict['Close Date']}")
                # else:
                #     print(f"Skipping row due to incorrect final column count: Expected {len(full_headers)}, got {len(final_data)}")

            else:
                # ADDED DEBUGGING PRINT
                print(f"Skipping row: Found only {len(cells)} cells. Expected 13+.")

        print("\nScraping complete.")
    
    except Exception as e:
        print(f"An error occurred: {e}")
        ipo_rows = []
    finally:
        # Crucial step: close the browser
        if driver is not None:
            driver.quit()
            driver.quit()
    
    return ipo_data # This returns the ipo subscription data
        
if __name__ == "__main__":
    subscription_data = get_ipo_subscription()
    print(subscription_data)