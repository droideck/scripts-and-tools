"""The Python script provided is a utility for creating text files that serve as session logs or quests for Pathfinder 2e games.
It facilitates easy navigation and writing of session logs by automatically generating and organizing quest information based on JSON data.
The script specifically caters to the Russian language, with functionality to feminize certain texts for character names and descriptions.

Requirements:
- Pathfinder: Kingmaker blueprint JSON files 
    - ./Kingmaker.Blueprints.Quests.BlueprintQuest
    - ./Kingmaker.Blueprints.Quests.BlueprintQuestObjective
- Pathfinder: Kingmaker translation JSON file
    - ./ruRU.json (or any other language file)
"""

import os
import json
import re

def femalize(text):
    # Replace all {mf||X} elements with X, and {mf|X|Y} with Y
    result = re.sub(r"\{mf\|\|([^}]+)\}", r"\1", text)  # Handle cases like {mf||а}
    result = re.sub(r"\{mf\|[^|]*\|([^}]+)\}", r"\1", result)  # Handle cases like {mf|X|Y}
    result = result.replace("{name}", "Лекси")
    result = result.replace("{Name}", "Лекси")
    return result

result_dir = "./result"

# Load the localized strings
localized_strings_path = "./ruRU.json"
localized_strings = {}

with open(localized_strings_path, 'r', encoding='utf-8') as file:
    data = json.load(file)
    for item in data['strings']:
        localized_strings[item['Key']] = item['Value']

# Define the directory paths
quests_directory = "./Kingmaker.Blueprints.Quests.BlueprintQuest"
objectives_directory = "./Kingmaker.Blueprints.Quests.BlueprintQuestObjective"

# List all files in the quests directory
quest_files = os.listdir(quests_directory)

for quest_file in quest_files:
    with open(os.path.join(quests_directory, quest_file), 'r', encoding='utf-8') as file:
        print(f"Quest File: {quest_file}")
        quest_data = json.load(file)
        objectives = quest_data['m_Objectives']
        if 'm_Group' in quest_data:
            quest_group = quest_data['m_Group']
        else:
            quest_group = "No Group"
        quest_description = quest_data['Description'].split(':')[1]
        quest_title = quest_data['Title'].split(':')[1]
        quest_title_en = femalize(quest_data['Title'].split(':')[2])
        quest_completion = quest_data['CompletionText'].split(':')[1]
        quest_url = f'https://pathfinderkingmaker.fandom.com/wiki/{quest_title_en.replace(" ", "_")}'

        quest_title_localized = femalize(localized_strings.get(quest_title, f"Missing localization for {quest_title}"))
        quest_description_localized = femalize(localized_strings.get(quest_description, f"Missing localization for {quest_description}"))
        quest_completion_localized = femalize(localized_strings.get(quest_completion, f"Missing localization for {quest_completion}"))

        group_directory = os.path.join(result_dir, quest_group)
        if not os.path.exists(group_directory):
            os.makedirs(group_directory)

        quest_info_filename = os.path.join(group_directory, f'{quest_title_en} - {quest_title_localized}.txt')
        with open(quest_info_filename, 'w', encoding='utf-8') as f:
            f.write(f"Quest Title:\n{quest_title_en}\n")
            f.write(f"{localized_strings.get(quest_title, f'Missing localization for {quest_title}')}\n\n")
            f.write(f"Quest Description:\n{quest_description_localized}\n\n")
            f.write(f"Quest Completion:\n{quest_completion_localized}\n\n")
            f.write(f"Quest URL:\n{quest_url}\n\n")
            f.write("--------------------------------------------------\n")

            for objective in objectives:
                objective_id = objective.split(':')[1]
                objective_name = objective.split(':')[2]
                objective_file_name = objective_name + '.' + objective_id + '.json'
                objective_path = os.path.join(objectives_directory, objective_file_name)

                with open(objective_path, 'r', encoding='utf-8') as obj_file:
                    objective_data = json.load(obj_file)
                    objective_description = objective_data['Description'].split(':')[1]
                    name_key = objective_data['Title'].split(':')[1]
                    description_key = objective_data['Description'].split(':')[1]
                    addendums = objective_data['m_Addendums']
                    if 'm_Type' in objective_data and objective_data['m_Type'] == "Addendum":
                        continue

                    # Lookup localized strings
                    name_localized = femalize(localized_strings.get(name_key, ''))
                    description_localized = femalize(localized_strings.get(description_key, f"Missing localization for {description_key}"))
                    if name_localized is None:
                        continue
                    f.write(f"\n{name_localized}\n---\n")
                    f.write(f"{description_localized}\n")

                    for addendum in addendums:
                        addendum_key = addendum.split(':')[1]
                        addendum_name = addendum.split(':')[2]
                        addendum_file_name = addendum_name + '.' + addendum_key + '.json'
                        addendum_path = os.path.join(objectives_directory, addendum_file_name)
                        with open(addendum_path, 'r', encoding='utf-8') as obj_add_file:
                            addendum_data = json.load(obj_add_file)
                            addendum_description_key = addendum_data['Description'].split(':')[1]
                            addendum_localized = femalize(localized_strings.get(addendum_description_key, f"Missing localization for {addendum_description_key}"))
                            f.write(f"- {addendum_localized}\n")
