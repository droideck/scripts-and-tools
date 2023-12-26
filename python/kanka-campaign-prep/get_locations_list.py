import requests
from bs4 import BeautifulSoup
import yaml

BASE_URL = "https://pillarsofeternity.fandom.com"

class QuotedStr(str):
    pass

def quoted_scalar(dumper, data):
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')

yaml.add_representer(QuotedStr, quoted_scalar)

def get_parsed_html(url):
    response = requests.get(url)
    response.raise_for_status()  # Raises an HTTPError if the HTTP request returned an unsuccessful status code
    return BeautifulSoup(response.content, 'html.parser')

def extract_contains_section(soup):
    contains = soup.select_one('div[data-source="sub_locations"]')
    return [QuotedStr(BASE_URL + a['href']) for a in contains.select('a')] if contains else []

def extract_characters_section(soup):
    characters_section = soup.find('span', id="Characters")
    if characters_section:
        next_siblings = characters_section.parent.find_next_sibling('ul').find_all('li')
        return [QuotedStr(BASE_URL + a['href']) for li in next_siblings for a in li.select('a') if 'title' in a.attrs]
    return []

def format_data(url, characters, children):
    return {
        'url': QuotedStr(url),
        'characters': [{'url': char} for char in characters],
        'children': [{'url': child} for child in children]
    }

def process_location(url, processed=set()):
    if url in processed:  # Prevent processing the same URL multiple times
        return None
    processed.add(url)
    soup = get_parsed_html(url)
    characters = extract_characters_section(soup)
    children = extract_contains_section(soup)
    data = format_data(url, characters, children)
    child_data_list = []
    for child in children:
        child_data = process_location(child, processed)
        if child_data:  # Append child data if it exists
            child_data_list.append(child_data)
    if child_data_list:
        data['children'] = child_data_list
    return data

# Start the script with the initial URL
if __name__ == "__main__":
    initial_url = BASE_URL + "/wiki/Stormwall_Gorge"
    try:
        location_data = process_location(initial_url)
        formatted_data = {'locations': [location_data]}  # Wrap the single location data into a list
        yaml_data = yaml.dump(formatted_data, allow_unicode=True, default_flow_style=False, sort_keys=False, indent=2)
        print(yaml_data)
    except requests.RequestException as e:
        print(f"Request failed: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

