import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote

# Constants and configuration
WIKI_URL_LIST = [
    "https://pillarsofeternity.fandom.com/wiki/Caed_Nua",
    "https://pillarsofeternity.fandom.com/wiki/The_Goose_and_Fox"
    # Add more URLs here
]
KANKA_ENDPOINT = "https://api.kanka.io/1.0/campaigns/227289/locations"  # Replace with your campaign ID

KANKA_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiIxIiwianRpIjoiYzYzYjU4NjRjYTU3YWY5ZTRhOGEyZDZiZWQxMzE5OThlY2FhMzQ0YmYzOWM2NzQwZWU0ZjNiMzA0ZDRjN2M3MjY4ODQyMDJiNjg1NDA3ODUiLCJpYXQiOjE3MDM0OTA2NTAuMDMxNjk2LCJuYmYiOjE3MDM0OTA2NTAuMDMxNzAyLCJleHAiOjE3MzUxMTMwNTAuMDE2MTczLCJzdWIiOiIzMjI3OSIsInNjb3BlcyI6W119.vrroviv5Ur8zmjVoxk8GfgGnKOoJqpD94OzaUxfLFakST7rE2_LFL54WNPEzAPtr0fe_i3hBeOCQidoPelXF4RyFBoRy7mcNCjl94784nc7kV7xM2Uf7rrfOXDlYuIkuIHh5kGo3P60YUSmFBcknlUnpeDcbu2mAMeZZS5_yaZnY9KiaA-Df4x2w1aRazAruzp7FINpul80TSzt_AGyjJQP854cqU9WOZS1_JS03LL04Xth2xj40qind3JqGrQ2STUiXVfX-j2b5-j4fbFNTPHDUBEoOrySs64yXlwYW5gFH2IXxepGcrYP_hiXxm3cZSb_sh-LniaUgBgW_qM_JjyvB6RsN3MVrWG1dJrqVUum-G_faKafCfmzqzH55Q7e4Abfd4NoziZwhGa0KsWKjiMPL7mBzzScFBOat2OZQ1Ani29mSGsi0l1sKWxx6sWJd0XgXdLWmVUWqbD8qaNLRnnKdQpzTg_5OSLU3twLP5a7OIlHJRMMtj4Que2Z1Ix90AF5xt0d1TgAn-Sp-7-AaNQTcnuQm98LAgc9sDMMmPOK6xQkW8lXjdnKTKgTiyA_U1NnXMNuc1ijy8DHCk-5qaDn8iqOxG9jI5ZZrGsWDg3aCI5TIbRlqpSVY-pwtwN51izt1cKE6gC9InNY2kwRTnKfG4IKSnXkWNPGKnxTgnTA"  # Replace with your Kanka API token


# Function to fetch and parse wiki for specified sections
def fetch_and_parse_wiki(url, section_ids):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    all_content = ""

    for section_id in section_ids:
        section_heading = soup.find('span', id=section_id)
        if section_heading:
            section_heading = section_heading.parent
            all_content += f"<h3>{section_id.replace('_', ' ').title()}</h3>"
            html_content = ""
            content_sibling = section_heading.find_next_sibling()
            while content_sibling and (content_sibling.name != "h2"):
                html_content += str(content_sibling)
                content_sibling = content_sibling.find_next_sibling()
            all_content += html_content if html_content else f"{section_id} section not found.\n"

    return all_content

# Helper function to extract location name from URL
def extract_name_from_url(url):
    name = url.split('/')[-1]  
    return unquote(name).replace('_', ' ')

# Function to create a location in Kanka
def create_kanka_location(name, description):
    headers = {
        'Authorization': f'Bearer {KANKA_TOKEN}',
        'Content-Type': 'application/json'
    }
    data = {
        "name": name,
        "type": "Village",
        "entry": description
    }
    response = requests.post(KANKA_ENDPOINT, json=data, headers=headers)
    return response.json()  # Return the entire JSON response

# Function to post to a location in Kanka
def post_to_kanka_location(location_id, poi_content):
    post_endpoint = f"https://api.kanka.io/1.0/campaigns/227289/entities/{location_id}/posts"
    headers = {
        'Authorization': f'Bearer {KANKA_TOKEN}',
        'Content-Type': 'application/json'
    }
    data = {
        "name": "Additional Information",
        "entity_id": location_id,
        "entry": poi_content
    }
    response = requests.post(post_endpoint, json=data, headers=headers)
    return response


# Main execution
if __name__ == "__main__":
    for wiki_url in WIKI_URL_LIST:
        location_name = extract_name_from_url(wiki_url)
        location_description = fetch_and_parse_wiki(wiki_url, ["Background", "Description"])
        # Fetching multiple sections now
        poi_description = fetch_and_parse_wiki(wiki_url, ["Points_of_interest", "Characters", "Companion_reactions"])
        location_response = create_kanka_location(location_name, location_description)

        if location_response.get('data') and location_response.get('data').get('entity_id'):
            location_id = location_response["data"]["entity_id"]
            post_response = post_to_kanka_location(location_id, poi_description)
            print(f"Posted to {location_name}: Status {post_response.status_code}", post_response.json())
        else:
            print(f"Failed to create {location_name}: Status {location_response.get('errors')}")

        print(f"Created {location_name}: Status {location_response.get('id')}", location_response)

