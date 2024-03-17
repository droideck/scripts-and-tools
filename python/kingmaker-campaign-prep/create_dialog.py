"""This Python script is designed to extract dialog tables from a specific Fandom Wiki
(in this case, the Pathfinder Kingmaker wiki) and translate them into a specified language
(you need to modify it for your language).

It operates by scraping dialog data from web pages, translating the text, and
formatting the translations into HTML tables.

Requirements:
- Pathfinder: Kingmaker blueprint JSON files 
    - ./Kingmaker.DialogSystem.Blueprints.BlueprintCue
    - ./Kingmaker.DialogSystem.Blueprints.BlueprintAnswer
- Pathfinder: Kingmaker translation JSON file
    - ./ruRU*.json (or any other language file)
- Provide a list of URLs to the dialog pages on the Fandom Wiki
  you can get them from here - https://pathfinderkingmaker.fandom.com/wiki/Category:Dialogs
"""

import os
import json
import re
import glob
import requests
from bs4 import BeautifulSoup

cue_directory = './Kingmaker.DialogSystem.Blueprints.BlueprintCue'
answer_directory = './Kingmaker.DialogSystem.Blueprints.BlueprintAnswer'
glossary_directory = './BlueprintRoot.json'

def parse_blueprint_root_json():
    global glossary_entries
    glossary_entries = []
    with open(glossary_directory, 'r', encoding='utf-8') as file:
        data = json.load(file)
        for glossary in data["Glossaries"]:
            glossary_entries.extend(glossary["Entries"])

def load_localized_strings(localized_strings_path):
    localized_strings = {}
    for file_path in glob.glob(os.path.join(localized_strings_path, 'ruRU*.json')):
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            for item in data['strings']:
                localized_strings[item['Key']] = item['Value']
    return localized_strings

# Load the localized strings for translation from all matching files
localized_strings_path = "./"  # Assuming the JSON files are in the current directory
localized_strings = load_localized_strings(localized_strings_path)

def translate_text(text_key):
    text = localized_strings.get(text_key, f"Missing localization for {text_key}")
    result = re.sub(r"\{mf\|\|([^}]+)\}", r"\1", text)  # Handle cases like {mf||а}
    result = re.sub(r"\{mf\|[^|]*\|([^}]+)\}", r"\1", result)  # Handle cases like {mf|X|Y}
    #result = re.sub(r"\{g\|[^}]+\}", "", result)  # Handle cases like {g|X}
    #result = result.replace("{/g}", "")
    result = result.replace("{name}", "Лекси")
    result = result.replace("{Name}", "Лекси")
    result = result.replace("{n}", "")
    result = result.replace("{/n}", "\n")

    pattern = re.compile(r'\{d\|([^}]+)\}([^{}]+)\{/d\}')

    def replace(match):
        key = match.group(1)  # Extract the key from the matched pattern
        text = match.group(2)  # Extract the text from the matched pattern
        title = translate_glossary_entry(key)  # Get the title from the dict using the key
        # Return the transformed HTML span element
        return f'<span style="color:Blue"><span title="{title}" style="border-bottom:1px dotted">{text}</span></span>'

    # Use the sub() method of the pattern object to replace all matches in the input text
    transformed_text = pattern.sub(replace, result)
    pattern = re.compile(r'\{g\|([^}]+)\}([^{}]+)\{/g\}')
    transformed_text = pattern.sub(replace, transformed_text)

    return transformed_text

def translate_by_id(text, id):
    cue_file_name = f"{text}.{id}.json"
    if cue_file_name.startswith('Answer'):
        proc_directory = answer_directory
    else:
        proc_directory = cue_directory
    cue_file_path = os.path.join(proc_directory, cue_file_name)
    try:
        with open(cue_file_path, 'r', encoding='utf-8') as cue_file:
            cue_data = json.load(cue_file)
            text_key = cue_data['Text'].split(':')[1]
            return translate_text(text_key)
    except FileNotFoundError:
        print(f"Cue file not found: {cue_file_path}")


def translate_glossary_entry(text):
    # Find the glossary entry in the glossary_entries list
    found_dict = next((item for item in glossary_entries if item["Key"] == text), None)
    text_key = found_dict["Description"].split(':')[1]
    return translate_text(text_key)

# Function to fetch and parse HTML from a URL, then translate and replace specific texts
def fetch_and_translate_html(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    tables_html = """
        <style>
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px auto; /* Center table and add some spacing around it */
        }
        th, td {
            border: 1px solid #dddddd;
            text-align: left;
            padding: 8px;
        }
        th {
            background-color: #f2f2f2;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        th:nth-child(6), td:nth-child(6) {
            width: 40%; /* Larger width for the text column */
            min-width: 500px; /* Minimum width to reduce wrapping */
            max-width: 500px; /* Minimum width to reduce wrapping */
        }
        th:nth-child(6), td:nth-child(6) {
            max-width: 200px; /* Minimum width to reduce wrapping */
        }
        /* Responsive font size adjustment for smaller screens */
        @media (max-width: 1000px) {
            table, th, td {
                font-size: 14px; /* Smaller font size */
            }
        }
        span[style="color:LightBlue"] {
            font-weight: bold;
            color: #007bff; /* Lighter blue to make it more readable */
        }
    </style>
    """
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            for cell in cells:
                cue_match = re.search(r'(Cue_[0-9a-zA-Z_]+|Answer_[0-9a-zA-Z_]+)<', cell.decode_contents())
                if cue_match:
                    cue_id = cue_match.group(1)
                    if 'will open in a moment or t' in cell.decode_contents():
                        import pdb; pdb.set_trace()
                    pattern = r'\(([a-fA-F0-9]{32})\)'
                    translation_id_match = re.search(pattern, cell.decode_contents())
                    if translation_id_match:
                        translation_id = translation_id_match.group(1)
                        translated_text = translate_by_id(cue_id, translation_id)
                        if translated_text:
                            # Parse the translated HTML string
                            new_content = BeautifulSoup(translated_text, 'html.parser')
                            
                            # Check if cells[-2] has any content to replace, if not just append
                            if cells[-2].contents:
                                # If there's existing content, replace it with new_content
                                cells[-2].clear()  # Clear existing contents
                                cells[-2].append(new_content)  # Append new parsed HTML
                            else:
                                # If no existing content, directly append the new content
                                cells[-2].append(new_content)
                            break
        tables_html += str(table).replace('href="/wiki/', 'href="https://pathfinderkingmaker.fandom.com/wiki/').replace('style="color: #00FF00"', 'style="color:Black"')

    # Put a huge centered link at the beginning of the HTML to make it easier to navigate
    tables_html = f'<h1><a href="{url}" style="font-size: 24px; display: block; text-align: center; margin: 20px 0;">{url}</a></h1>' + tables_html

    return tables_html


def extract_dialog_links(url):
    """Extracts hrefs of dialogs from a given URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raises an HTTPError if the response status code is 4XX/5XX
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all <a> tags in the HTML
        links = soup.find_all('a')
        
        # Extract href attributes
        hrefs = [f"https://pathfinderkingmaker.fandom.com{link.get('href')}" for link in links if link.get('href') and link.get('href').startswith('/wiki/Dialogue')]
        return hrefs
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return []

def main():
    parse_blueprint_root_json()
    urls = [
        # Add your list of URLs here
        # etc.
    ]
    for url in urls:
        print(f"Extracting dialogs from: {url}")
        hrefs = extract_dialog_links(url)
        for href in hrefs:
            translated_html = fetch_and_translate_html(href)
            
            # Create a directory to save the translated HTML files
            output_directory = url.split('/')[-1].split(':')[-1]
            os.makedirs(output_directory, exist_ok=True)
            output_filename = os.path.join(output_directory, href.split('/')[-1] + ".html")
            with open(output_filename, 'w', encoding='utf-8') as file:
                file.write(translated_html)

            print(f'Translated HTML has been saved to {output_filename}')
    

if __name__ == "__main__":
    main()