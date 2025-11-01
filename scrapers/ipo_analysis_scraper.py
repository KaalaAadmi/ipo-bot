import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

def scrape_ipo_analysis():
    """
    Scrapes IPO analysis details (Link, Title, Summary) from sptulsian.com
    using the specific class names provided, including the dedicated link class.
    """
    print("Starting WebDriver...")
    
    url="https://www.sptulsian.com/f/ipo-analysis"
    
    # --- Chrome Options Setup ---
    chrome_options = Options()
    
    # Keep this commented out for testing, as requested
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    
    # These arguments help resolve general WebDriver startup issues and mimic a real browser
    chrome_options.add_argument("window-size=1920,1080")
    # chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    chrome_options.add_argument("--disable-extensions")
    
    extracted_data = []
    
    try:
        # Initialize the WebDriver
        driver = webdriver.Chrome(options=chrome_options)
        
        print(f"Opening URL: {url}")
        driver.get(url)
        
        # 1. Wait for an article element to be visible/present
        article_list_selector = "listing-article-class"
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, article_list_selector))
        )
        print("Article listings found. Extracting data...")

        # 2. Locate all the article wrapper elements
        article_listings = driver.find_elements(By.CLASS_NAME, article_list_selector)
        
        if not article_listings:
            print("No IPO analysis articles found on the page.")
        
        # 3. Iterate over the articles and extract the required data
        for i, article in enumerate(article_listings):
            try:
                # Class names provided by the user:
                title_class = "font_size_20_article"
                summary_class = "article_content_container"
                link_class = "article_content_url" # The newly identified class for the <a> tag
                
                # --- A. Get Link (<a>) ---
                link_element = article.find_element(By.CLASS_NAME, link_class)
                link = link_element.get_attribute("href")
                
                # --- B. Get the IPO Name/Title from the H2 tag
                title = article.find_element(By.CLASS_NAME, title_class).text.strip()
                
                # --- C. Get the Summary from the specific DIV tag
                summary = article.find_element(By.CLASS_NAME, summary_class).text.strip()
                
                extracted_data.append({
                    "IPO Name/Title": title,
                    "Summary": summary,
                    "Link": link
                })
            except NoSuchElementException as e:
                # This handles cases where a particular article is malformed (e.g., missing a link or title)
                print(f"Could not find required elements (link/title/summary) for article #{i + 1}. Skipping this entry.")
            except Exception as e:
                # Catch any other unforeseen error
                print(f"An unexpected error occurred while processing article #{i + 1}: {e}")
                continue

    except Exception as e:
        # This catches errors related to WebDriver initialization or page loading
        print(f"\nAn UNRECOVERABLE error occurred during scraping (check chromedriver/browser compatibility): {e}")
        
    finally:
        if 'driver' in locals() and driver:
            print("Closing WebDriver.")
            driver.quit()
        return extracted_data

if __name__ == "__main__":
    # URL provided by the user
    TARGET_URL = "https://www.sptulsian.com/f/ipo-analysis"
    articles = scrape_ipo_analysis(TARGET_URL)
    print(articles)
