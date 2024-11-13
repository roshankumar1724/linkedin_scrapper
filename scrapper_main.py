import sys
sys.dont_write_bytecode = True

from config import LINKEDIN_USERNAME, LINKEDIN_PASSWORD, POST_LIMIT, OPENAI_GPT_API_KEY

import time
from openai import OpenAI
import pickle
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Configure Webdriver
options = Options()
options.add_argument("--start-maximized")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


# Configure OpenAI GPT
client = OpenAI(api_key=OPENAI_GPT_API_KEY)

# Load / login and save cookies
def login_linkedIn():
    driver.get("https://www.linkedin.com/login")

    # check if cookie is saved
    try:
        with open("linkedin_cookie.pkl", "rb") as file:
            cookies=pickle.load(file)
            for cookie in cookies:
                driver.add_cookie(cookie)
        
        # Refresh to use loaded cookie
        driver.refresh() 
    
    except:
        print("No cookie found, proceeding with manual login !")
        # Enter username and password and (or) OTP
        username = driver.find_element(By.ID, "username")
        password = driver.find_element(By.ID, "password")

        username.send_keys(LINKEDIN_USERNAME)
        time.sleep(2)
        password.send_keys(LINKEDIN_PASSWORD)
        time.sleep(2)
        password.send_keys(Keys.RETURN)

        # driver.implicitly_wait(30)

        try:
            WebDriverWait(driver=driver, timeout=30).until(
                EC.title_contains(title="Feed | LinkedIn")
            )
            
            with open("linkedin_cookie.pkl", "wb") as file:
                print ("After login ==> \n" + str(driver.get_cookies()))
                pickle.dump(driver.get_cookies(), file)
        except:
            print("Either increase timeout or Something went wrong !")

    finally:
        time.sleep(3)


# Search for a keyword and apply sorting
def search_and_sort(keyword):
    driver.get("https://www.linkedin.com/feed/")
    search_box = driver.find_element(By.XPATH, "//input[@placeholder='Search']")
    search_box.send_keys(keyword)
    search_box.send_keys(Keys.RETURN)
    time.sleep(3)
    
    # Apply sorting by 'Latest'
    try:
        driver.find_element(By.XPATH, "//div[@id='search-reusables__filters-bar']/div[1]/div[1]/button[1]").click()
        time.sleep(2)
        driver.find_element(By.XPATH, "//label[@for='advanced-filter-sortBy-date_posted']").click()
        time.sleep(2)
        driver.find_element(By.XPATH, "//div[@id='artdeco-modal-outlet']/div[1]/div[1]/div[3]/div[1]/button[2]").click()
    except NoSuchElementException:
        print("Sort by 'Latest' option not found.")
    except Exception as e:
        print("Error in sorting posts : \n", e)
    time.sleep(3)


# Reporting the post with identified category
def report_this_post(post, category):
    try:
        post.find_element(By.XPATH, ".//button[contains(@aria-label,'Open control menu')]").click()
        time.sleep(1)
        post.find_element(By.XPATH, ".//div[@class='artdeco-dropdown__content-inner']/ul/li/div[1]/div[2]/h5[text()='Report post']").click()
        time.sleep(2)
        reporting_content = driver.find_element(By.XPATH, "//div[contains(@class,'trust-reporting-flow-modal__content')]")
        if (category in reporting_content.get_attribute("innerText")):
            print("CATEGORY EXISTS !!")
            reporting_content.find_element(By.XPATH, f".//button[text()='{category}']").click()
            time.sleep(1)
            driver.find_element(By.XPATH, "//button[@data-test-trust-button-action-component-button='NEXT_STEP']").click()
            time.sleep(1)
            driver.find_element(By.XPATH, "//button[@data-test-trust-button-action-component-button='SUBMIT']").click()
            print(f"POST Reported for {category}")
            time.sleep(2)
    except Exception as e:
        print ("Error in reporting post", e)
        raise Exception("Error in reporting post")

# Analyse post using openAI GPT
def analyze_post(message):
    post_categories = ['Harassment', 'Fraud or Scam', 'Spam', 'Misinformation', 'Hateful speech', 'Threats or violence', 'Self-harm', 'Graphic content', 'Dangerous or extremist organizations', 'Sexual content', 'Fake account', 'Child exploitation', 'Illegal goods and services', 'Infringement']

    prompt = f"""
    Classify the following LinkedIn POST content message as NONE or any of the categories mentioned. Also return the probability of its being categorised.
    Message: ""{message}"".
    categories: {post_categories}
    The output should only contain two lines: first should contain NONE or the categorized text, and the next line should contain probability with up to three decimal points.
    """

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.0,
    )
    result = response.choices[-1].message.content
    categories = re.split(r'[\n]', result)
    return categories[0], categories[-1]

# VERIFY POSTS
def verify_posts():
    try:
        post_count = 0
        post_container_ids = []

        while (post_count < POST_LIMIT):
            divs = driver.find_elements(By.XPATH, "//div[@class='scaffold-finite-scroll__content']/div")
            last_post = None
            for div in divs:
                # Identifying the post container uniquely by it's ID
                div_id = div.get_attribute("id")
                if ((div_id is not None) and (div_id not in post_container_ids)):
                    post_container_ids.append(div_id)
                    posts = div.find_elements(By.XPATH, ".//ul[contains(@class,'reusable-search__entity-result-list')]/li")
                    for post in posts:
                        if ("Feed post" in post.text):
                            # Analyze the post for reporting
                            category, probability = analyze_post(post.text)
                            print(category, probability)
                            if ((category != "NONE") and (probability > 0.95)):
                                try:
                                    print("Potential violation found. Reporting post...")
                                    # Reporting the post
                                    report_this_post(post, category)
                                except:
                                    # Click on body to close the pop up / modal if any opened
                                    time.sleep(2)
                                    driver.find_element(By.XPATH, "//body").click()
                                    time.sleep(2)
                                    continue
                            
                            post_count += 1
                            last_post = post
                # print ("\n post_count", post_count, "\n post_container_ids ", post_container_ids)
            if (post_count < POST_LIMIT and (last_post is not None)):
                # scroll
                scroll_height = last_post.get_attribute("scrollHeight")
                # driver.execute_script(f"window.scrollTo(0, ${scroll_height});")
                driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight);")
                print("scrolled !!", scroll_height)
                time.sleep(3)

    except Exception as e:
        print("post verification failed !!")
        print(e)


def main():
    try:
        login_linkedIn()
        time.sleep(5)

        keywordToSearch = "Healh Care"
        search_and_sort(keyword=keywordToSearch)
        time.sleep(5)

        verify_posts()
        time.sleep(5)
    except Exception as e:
        print("Error Occurred !! \n", e)
        time.sleep(5)
        driver.quit()


if __name__ == "__main__":
    main()
