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

def translate_and_update_description(description, location_url=None):
    """
    Translate the description and update the links within it.
    """
    translated_description = translate_text(description)
    # Update links in the translated description
    translated_description = update_links(translated_description)

    if location_url:
        location_link = f'<a href="{location_url}">{location_url}</a>'
        translated_description += f"\n{location_link}\n"

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

# Function to post to a location in Kanka
def post_to_kanka_location(location_id, poi_content):
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
    translated_description = translate_and_update_description(description, location_url)

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
    return response.json()

def create_kanka_character(name, description, location_id):
    """
    Create a character in Kanka with the given information.
    """
    translated_description = translate_and_update_description(description)

    character_endpoint = f"{KANKA_ENDPOINT}/characters"
    headers = {
        'Authorization': f'Bearer {KANKA_TOKEN}',
        'Content-Type': 'application/json'
    }
    import pdb; pdb.set_trace()
    data = {
        "name": name,
        "entry": translated_description,
        "location_id": location_id
    }

    response = requests.post(character_endpoint, json=data, headers=headers)
    return response.json()

def process_character(character_url, location_id):
    """
    Process each character: fetch data, create entity in Kanka.
    """
    character_name = extract_name_from_url(character_url)
    character_description, _, _ = fetch_and_parse_wiki(character_url, ["Background", "Description"])  # Assuming these sections are relevant

    character_response = create_kanka_character(character_name, character_description, location_id)

    if character_response.get('data'):
        print(f"Created character {character_name} with ID: {character_response['data']['id']}")
    else:
        print(f"Failed to create character {character_name}: Status {character_response.get('errors')}")


# Modify process_location to handle characters
def process_location(location, parent_id=None):
    location_name = extract_name_from_url(location['url'])
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
        #time.sleep(60)
