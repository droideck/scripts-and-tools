import requests
import time
from bs4 import BeautifulSoup
from urllib.parse import unquote
import yaml
from google.cloud import translate_v2 as translate

# Initialize the Google Cloud Translate client
translate_client = translate.Client()

# Load configuration from YAML
with open("config.yaml", 'r') as stream:
    config = yaml.safe_load(stream)

KANKA_ENDPOINT = config['kanka']['endpoint']
KANKA_TOKEN = config['kanka']['token']
TARGET_LANGUAGE = 'ru'

# Rate limiting variables
request_counter = 0
last_request_time = time.time()

def check_rate_limit():
    global request_counter, last_request_time
    current_time = time.time()
    if current_time - last_request_time >= 60:
        request_counter = 0
        last_request_time = current_time
    request_counter += 1
    if request_counter > 85:
        sleep_time = 60 - (current_time - last_request_time)
        print(f"Rate limit reached. Sleeping for {sleep_time} seconds.")
        if sleep_time > 0:
            time.sleep(sleep_time)
        request_counter = 0
        last_request_time = time.time()

def update_links(html_content, base_url="https://pillarsofeternity.fandom.com"):
    """
    Update all relative links in the html_content to absolute links.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    for a_tag in soup.find_all('a', href=True):  # Find all anchor tags with href attribute
        href = a_tag['href']
        if href.startswith("/"):  # Check if the link is relative
            a_tag['href'] = base_url + href  # Update with the base_url
    return str(soup)

def translate_and_update_description(description):
    """
    Translate the description and update the links within it.
    """
    translated_description = translate_text(description)
    # Update links in the translated description
    translated_description = update_links(translated_description)

    return translated_description

# Function to translate text
def translate_text(text, target=TARGET_LANGUAGE):
    try:
        result = translate_client.translate(text, target_language=target)
        return result['translatedText']
    except Exception as e:
        print(f"Error in translation: {e}")
        return text


def post_to_kanka_entity(entity_id, fandom_url):
    check_rate_limit()  # Checking the rate limit

    # Prepare the post data
    post_title = "Fandom Link"
    post_entry = f"<a href='{fandom_url}'>{fandom_url}</a>"

    # API endpoint and headers
    post_endpoint = f"https://api.kanka.io/1.0/campaigns/227289/entities/{entity_id}/posts"
    headers = {
        'Authorization': f'Bearer {KANKA_TOKEN}',
        'Content-Type': 'application/json'
    }

    # Data for the POST request
    data = {
        "name": post_title,
        "entity_id": entity_id,
        "entry": post_entry
    }

    response = requests.post(post_endpoint, json=data, headers=headers)
    return response.json()  # Return the response data
