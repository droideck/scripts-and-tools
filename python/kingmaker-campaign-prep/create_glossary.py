"""This Python script is designed to facilitate the creation of a glossary for the DeepL translator.
Its primary function is to parse through designated directories to find localized strings,
load translations from JSON files, and then generate a CSV glossary that pairs English names
with their Russian translations.

Requirements:
- Pathfinder: Kingmaker blueprint JSON files 
    - ./Kingmaker.Blueprints.Area.BlueprintArea
    - ./Kingmaker.Blueprints.BlueprintUnit
    - ./Kingmaker.Blueprints.BlueprintUnitType
    - ./Kingmaker.Blueprints.Root.BlueprintRoot
- Pathfinder: Kingmaker translation JSON file
    - ./ruRU.json (or any other language file)
    - ./enGB.json
"""

import os
import re
import json
import csv

# Modified Step 1: Function to find localized strings in multiple directories
def find_localized_strings(directories):
    pattern = re.compile(r"LocalizedString:([0-9a-f\-]+):(.*)")
    matches = []
    for directory in directories:  # Iterate over each directory in the list
        for root, dirs, files in os.walk(directory):
            for file in files:
                with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                    for line in f:
                        match = pattern.search(line)
                        if match:
                            uuid, name = match.groups()
                            matches.append((uuid, name))
    return matches

# Function to load Russian translations from ruRU.json (unchanged)
def load_russian_translations(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return {entry["Key"]: entry["Value"] for entry in data["strings"]}

def load_english_translations(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return {entry["Key"]: entry["Value"] for entry in data["strings"]}

# Function to create a CSV glossary from the matches and translations (unchanged)
def create_csv_glossary(matches, translations, english, output_csv):
    restult = []
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["English Name", "Russian Translation"])
        for uuid, name in matches:
            russian_translation = translations.get(uuid, "Translation not found")
            english_tr = english.get(uuid, "Eng Translation not found")
            if len(russian_translation) > 30:
                continue
            # if russian_translation doesn't start with a capital letter, skip it
            if len(russian_translation) < 1 or not russian_translation[0].isupper():
                continue
            add_line = [english_tr, russian_translation]
            if add_line not in restult:
                restult.append(add_line)
        writer.writerows(restult)

# Main execution (modified to use a list of directories)
if __name__ == "__main__":
    # Define your list of directories here
    directories_to_search = ["Kingmaker.Blueprints.Area.BlueprintArea", "Kingmaker.Blueprints.BlueprintUnit", "Kingmaker.Blueprints.BlueprintUnitType", "Kingmaker.Blueprints.Root.BlueprintRoot"]
    ruRU_json_path = "ruRU.json"
    enGB_json_path = "enGB.json"
    output_csv_path = "output.csv"

    # Execute the functions
    matches = find_localized_strings(directories_to_search)
    translations = load_russian_translations(ruRU_json_path)
    english = load_english_translations(enGB_json_path)
    create_csv_glossary(matches, translations, english, output_csv_path)

    print("CSV glossary has been created successfully.")
