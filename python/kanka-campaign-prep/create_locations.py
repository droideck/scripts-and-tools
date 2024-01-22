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

# Load translations
character_translations = {}
location_translations = {}

with open("characters.txt", 'r', encoding='utf-8') as file:
    for line in file:
        english, translated = line.strip().split(' - ')
        character_translations[english] = translated

with open("maps.txt", 'r', encoding='utf-8') as file:
    for line in file:
        english, translated = line.strip().split(' - ')
        location_translations[english] = translated

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

# Function to fetch and parse wiki for specified sections
def fetch_and_parse_wiki(url, section_ids):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    all_content = ""
    image_url = None  # Initialize variable to hold the image URL
    location_type = None

    # Find the type of location
    type_section = soup.find("div", {"data-source": "type"})
    if type_section:
        type_value = type_section.find("div", class_="pi-data-value pi-font")
        if type_value:
            location_type = type_value.text.strip()

    sections = soup.find_all("section", class_="pi-item pi-group pi-border-color")
    for section in sections:
        h2_tag = section.find("h2")
        if h2_tag and "Loading screen" in h2_tag.text:
            figure = section.find("figure", class_="pi-item pi-image")
            if figure and figure.a and 'href' in figure.a.attrs:
                image_url = figure.a['href'].split("/revision")[0]  # Clean up the URL
                break  # Break after finding the first matching image

    for section_id in section_ids:
        section_heading = soup.find('span', id=section_id)
        if section_heading:
            section_heading = section_heading.parent
            if section_id != "Background":
                all_content += f"<h3>{section_id.replace('_', ' ').title()}</h3>"
            html_content = ""
            content_sibling = section_heading.find_next_sibling()
            while content_sibling and (content_sibling.name != "h2"):
                html_content += str(content_sibling)
                content_sibling = content_sibling.find_next_sibling()
            all_content += html_content if html_content else f"{section_id} section not found.\n"

    return all_content, image_url, location_type  # Return content, image URL, and location type


# Helper function to extract location name from URL
def extract_name_from_url(url):
    name = url.split('/')[-1]  
    return unquote(name).replace('_', ' ')

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

# Function to post to a location in Kanka
def post_to_kanka_location(location_id, poi_content):
    check_rate_limit()
    translated_poi_content = translate_and_update_description(poi_content)

    post_endpoint = f"https://api.kanka.io/1.0/campaigns/227289/entities/{location_id}/posts"
    headers = {
        'Authorization': f'Bearer {KANKA_TOKEN}',
        'Content-Type': 'application/json'
    }
    data = {
        "name": "Additional Information",
        "entity_id": location_id,
        "entry": translated_poi_content
    }
    response = requests.post(post_endpoint, json=data, headers=headers)
    return response

def create_kanka_location(name, description, image_url=None, location_type=None, parent_id=None, location_url=None):
    check_rate_limit()
    translated_description = translate_and_update_description(description)

    location_endpoint = f"{KANKA_ENDPOINT}/locations"
    headers = {
        'Authorization': f'Bearer {KANKA_TOKEN}',
        'Content-Type': 'application/json'
    }
    data = {
        "name": name,
        "entry": translated_description
    }
    if parent_id:
        data["location_id"] = parent_id
    if image_url:
        data["image_url"] = image_url
    if location_type:
        data["type"] = location_type

    response = requests.post(location_endpoint, json=data, headers=headers)
    response_data = response.json()  # Convert response to JSON format
    if response_data.get('data') and response_data['data'].get('entity_id'):
        location_entity_id = response_data['data']['entity_id']
        post_to_kanka_entity(location_entity_id, location_url)
    return response_data

def create_kanka_character(name, description, location_id, character_url=None):
    """
    Create a character in Kanka with the given information.
    """
    check_rate_limit()
    translated_description = translate_and_update_description(description)

    character_endpoint = f"{KANKA_ENDPOINT}/characters"
    headers = {
        'Authorization': f'Bearer {KANKA_TOKEN}',
        'Content-Type': 'application/json'
    }
    data = {
        "name": name,
        "entry": translated_description,
        "location_id": location_id
    }

    response = requests.post(character_endpoint, json=data, headers=headers)
    response_data = response.json()  # Convert response to JSON format
    if response_data.get('data') and response_data['data'].get('entity_id'):
        entity_id = response_data["data"]["entity_id"]
        post_to_kanka_entity(entity_id, character_url)
    return response_data

def process_character(character_url, location_id):
    """
    Process each character: fetch data, create entity in Kanka.
    """
    character_name = extract_name_from_url(character_url)
    if character_name in character_translations:
        character_name = character_translations[character_name]
    character_description, _, _ = fetch_and_parse_wiki(character_url, ["Background", "Description"])  # Assuming these sections are relevant

    character_response = create_kanka_character(character_name, character_description, location_id, character_url)

    if character_response.get('data'):
        print(f"Created character {character_name} with ID: {character_response['data']['id']}")
    else:
        print(f"Failed to create character {character_name}: Status {character_response.get('errors')}")


# Modify process_location to handle characters
def process_location(location, parent_id=None):
    location_name = extract_name_from_url(location['url'])
    if location_name in location_translations:
        location_name = location_translations[location_name]
    location_description, image_url, location_type = fetch_and_parse_wiki(location['url'], ["Background", "Description"])
    poi_description = fetch_and_parse_wiki(location['url'], ["Points_of_interest", "Characters", "Companion_reactions", "History", "Districts"])[0]

    location_response = create_kanka_location(location_name, location_description, image_url, location_type, parent_id, location['url'])

    if location_response.get('data') and location_response.get('data').get('entity_id'):
        location_id = location_response["data"]["id"]
        entity_id = location_response["data"]["entity_id"]
        post_response = post_to_kanka_location(entity_id, poi_description)
        print(f"Posted to {location_name}: Status {post_response.status_code}")

        # Process characters associated with this location
        for character in location.get('characters', []):
            process_character(character['url'], location_id)

        # Process child locations
        for child_location in location.get('children', []):
            process_location(child_location, parent_id=location_id)
    else:
        print(f"Failed to create {location_name}: Status {location_response.get('errors')}")


# Main execution
if __name__ == "__main__":
    for location in config['locations']:
        process_location(location)
