"""This Python script is designed to extract and translate banter dialogues from the game Kingmaker (a CRPG).
It specifically focuses on parsing JSON files containing localized strings and conditions that determine
when specific banters are triggered in the game. The extracted dialogues are then translated and
saved in a structured format for easy access and reference.

Requirements:
- Pathfinder: Kingmaker blueprint JSON files 
    - ./Kingmaker.BarkBanters.BlueprintBarkBanter
    - ./Kingmaker.DialogSystem.Blueprints.BlueprintCue
- Pathfinder: Kingmaker translation JSON file
    - ./ruRU*.json (or any other language file)
"""

import glob
import json
import os
import re

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
    result = result.replace("{name}", "Лекси")
    result = result.replace("{Name}", "Лекси")
    return result

def parse_nested_conditions(nested_conditions, cue_directory):
    nested_text = []
    for cond in nested_conditions:
        if cond['$type'].endswith('.CueSeen, Assembly-CSharp'):
            cue_id = cond['Cue'].split(':')[-1]
            nested_text.append(f"Cue Seen: {cue_id}")
        elif cond['$type'].endswith('.AnswerListShown, Assembly-CSharp'):
            answers_list_id = cond['AnswersList'].split(':')[-1]
            nested_text.append(f"Answer List Shown: {answers_list_id}")
        # Add handling for other condition types as necessary
    return ' or '.join(nested_text)  # Adjust based on the operation if needed

def parse_conditions(conditions, cue_directory):
    conditions_text = []
    standardized_conditions = []  # List to hold simplified condition strings

    if 'ExtraConditions' in conditions:
        for condition in conditions['ExtraConditions']['Conditions']:
            if condition['$type'].endswith('.CueSeen, Assembly-CSharp'):
                cue_id = condition['Cue'].split(':')[-1]
                cue_file_name = f"{cue_id}.{condition['Cue'].split(':')[1]}.json"
                cue_file_path = os.path.join(cue_directory, cue_file_name)
                not_flag = "Not " if condition.get("Not", False) else ""
                try:
                    with open(cue_file_path, 'r', encoding='utf-8') as cue_file:
                        cue_data = json.load(cue_file)
                        text_key = cue_data['Text'].split(':')[1]
                        conditions_text.append(f"{not_flag}Cue Text: " + translate_text(text_key))
                except FileNotFoundError:
                    conditions_text.append(f"Cue file not found: {cue_file_path}")
            elif condition['$type'].endswith('.FlagUnlocked, Assembly-CSharp'):
                condition_flag = condition['ConditionFlag'].split(':')[-1]  # Extract the last part of the ConditionFlag
                not_flag = "Not " if condition.get("Not", False) else ""
                if 'SpecifiedValues' in condition and condition['SpecifiedValues']:
                    specified_values_text = ", ".join(str(condition.get('SpecifiedValues', [])))
                else:
                    specified_values_text = ""
                conditions_text.append(f"Flag Unlocked: {not_flag}{condition_flag}" + (f" with values {specified_values_text}" if specified_values_text else ""))
            elif condition['$type'].endswith('.QuestStatus, Assembly-CSharp'):
                quest = condition['Quest'].split(':')[-1]  # Extract the last part of the Quest
                state = condition.get('State', '')
                not_flag = condition.get('Not', False)
                if "AgainstAllOdds" in quest and not_flag:
                    continue # Skip the AgainstAllOdds quest conditions
                else:
                    conditions_text.append(f"Quest {"Not " if not_flag else "Is "}{state}: {quest}")
            elif condition['$type'].endswith('.ObjectiveStatus, Assembly-CSharp'):
                quest_objective = condition['QuestObjective'].split(':')[-1]  # Extract the last part of the QuestObjective
                not_flag = " Not" if condition.get("Not", False) else ""
                conditions_text.append(f"Objective Status Is{not_flag}: {quest_objective}")
            elif condition['$type'].endswith('.CompanionInParty, Assembly-CSharp'):
                companion_name = condition['companion'].split(':')[-1]  # Extract the last part of the companion
                match_when_active = "Active" if condition.get("MatchWhenActive", False) else "Inactive"
                not_flag = "Not " if condition.get("Not", False) else ""
                conditions_text.append(f"{not_flag}Companion In Party: {companion_name} ({match_when_active})")
            elif condition['$type'].endswith('.BarkBanterPlayed, Assembly-CSharp'):
                banter_id = condition['Banter'].split(':')[-1]  # Extract the last part of the Banter ID
                not_flag = "Not " if condition.get("Not", False) else ""
                conditions_text.append(f"{not_flag}Bark Banter Played: {banter_id}")
            elif condition['$type'].endswith('.DayTime, Assembly-CSharp'):
                conditions_text.append("Condition: Day Time")
            elif condition['$type'].endswith('.AnswerSelected, Assembly-CSharp'):
                answer_id = condition['Answer'].split(':')[-1]  # Extract the last part of the Answer ID
                not_flag = "Not " if condition.get("Not", False) else ""
                conditions_text.append(f"Condition: Answer {not_flag}Selected - {answer_id}")
            elif condition['$type'].endswith('.OrAndLogic, Assembly-CSharp'):
                operation = condition['ConditionsChecker']['Operation']
                nested_conditions = condition['ConditionsChecker']['Conditions']
                nested_conditions_text = parse_nested_conditions(nested_conditions, cue_directory)
                combined_text = f" ({operation} Logic): " + nested_conditions_text
                conditions_text.append(combined_text)
            else:
                conditions_text.append("Condition: " + json.dumps(condition, indent=2))
            type_end = condition['$type'].split('.')[-1]
            if type_end == 'CueSeen, Assembly-CSharp':
                cue_name = condition['Cue'].split(':')[-1]
                cue_id = condition['Cue'].split(':')[-2]
                not_flag = "Not" if condition.get('Not', False) else "Is"
                standardized_conditions.append(f"CueSeen-{not_flag}-{cue_name}-{cue_id}")
            elif type_end == 'FlagUnlocked, Assembly-CSharp':
                flag = condition['ConditionFlag'].split(':')[-1]
                not_flag = "Not" if condition.get('Not', False) else "Is"
                standardized_conditions.append(f"FlagUnlocked-{not_flag}-{flag}")
            elif type_end == 'QuestStatus, Assembly-CSharp':
                quest = condition['Quest'].split(':')[-1]
                state = condition.get('State', '')
                not_flag = "Not" if condition.get('Not', False) else "Is"
                standardized_conditions.append(f"QuestStatus-{not_flag}-{state}-{quest}")
            elif type_end == 'ObjectiveStatus, Assembly-CSharp':
                objective = condition['QuestObjective'].split(':')[-1]
                not_flag = "Not" if condition.get('Not', False) else "Is"
                standardized_conditions.append(f"ObjectiveStatus-{not_flag}-{objective}")
            elif type_end == 'CompanionInParty, Assembly-CSharp':
                companion = condition['companion'].split(':')[-1]
                match_when_active = "Active" if condition.get("MatchWhenActive", False) else "Inactive"
                not_flag = "Not" if condition.get("Not", False) else "Is"
                standardized_conditions.append(f"Companion-{not_flag}-{match_when_active}-{companion}")
            elif type_end == 'BarkBanterPlayed, Assembly-CSharp':
                banter_id = condition['Banter'].split(':')[-1]
                not_flag = "Not" if condition.get("Not", False) else "Is"
                standardized_conditions.append(f"BanterPlayed-{not_flag}-{banter_id}")
            elif type_end == 'DayTime, Assembly-CSharp':
                standardized_conditions.append("DayTime")
            elif type_end == 'AnswerSelected, Assembly-CSharp':
                answer_id = condition['Answer'].split(':')[-1]
                not_flag = "Not" if condition.get('Not', False) else "Is"
                standardized_conditions.append(f"AnswerSelected-{not_flag}-{answer_id}")
            elif type_end == 'OrAndLogic, Assembly-CSharp':
                operation = condition['ConditionsChecker']['Operation']
                standardized_conditions.append(f"Logic-{operation}")
  
    return '\n'.join(conditions_text), standardized_conditions


def parse_banter_files(source_dir, cue_directory, translation_dir, output_dir):
    banter_files = glob.glob(os.path.join(source_dir, 'Banter_*.json'))
    
    for banter_file in banter_files:
        print(f"Parsing {banter_file}")
        with open(banter_file, 'r', encoding='utf-8') as file:
            banter_data = json.load(file)
            m_AssetGuid = banter_data['m_AssetGuid']
            
            localized_strings = extract_localized_strings(banter_data)
            if 'Unit' in banter_data:
                speaker = banter_data['Unit'].split(':')[-1]
            else:
                speaker = "None"
            
            conditions_text = ""
            if 'Conditions' in banter_data:
                conditions_text, conditions = parse_conditions(banter_data['Conditions'], cue_directory)  # Adjusted to return conditions list
        
        dialog = replace_with_translations(localized_strings, speaker, banter_data['Responses'])
        
        save_dialog(conditions_text, dialog, banter_file, output_dir, conditions)  # Now passing conditions to save_dialog

def sanitize_directory_name(name):
    """Sanitize and shorten the condition name for a valid and concise directory name."""
    # Basic sanitation to remove unwanted characters and limit length
    return re.sub(r'[^\w\s-]', '', name).strip()[:100]

def save_dialog(conditions_text, dialog, filename, output_dir, conditions):
    # New parameter 'conditions' added, which is a list of condition strings
    
    # Example logic for directory creation based on conditions
    if conditions:
        # Join conditions into a single string or handle them separately
        condition_dir_name = '_'.join(sanitize_directory_name(cond) for cond in conditions)
        final_output_dir = os.path.join(output_dir, condition_dir_name)
    else:
        final_output_dir = output_dir

    if not os.path.exists(final_output_dir):
        os.makedirs(final_output_dir)

    base_name = os.path.basename(filename)
    base_name_without_ext = os.path.splitext(base_name)[0].split('.')[0]
    new_filename = f"{base_name_without_ext}.txt"
    new_file_path = os.path.join(final_output_dir, new_filename)

    with open(new_file_path, 'w', encoding='utf-8') as file:
        if conditions_text:
            file.write(conditions_text + '\n\n')
        file.write('\n\n'.join(dialog))
    
    print(f"Saved translated dialog to {new_file_path}")

def extract_localized_strings(banter_data):
    strings = {}
    for phrase in banter_data['FirstPhrase']:
        key = phrase.split(':')[1]
        strings[key] = {"text": phrase, "speaker": None}  # Main dialog does not have a speaker defined in the structure
    return strings

def replace_with_translations(localized_strings, main_speaker, responses):
    dialog = []
    # Include main speaker's dialog
    for key, data in localized_strings.items():
        translation = translate_text(key)
        dialog.append(f"{main_speaker} SPEAKS FIRST: {translation}")
    
    # Include responses with speakers
    for response in responses:
        if 'Unit' in response:
            speaker = response['Unit'].split(':')[-1]
        else:
            speaker = "None"
        speaker = response['Unit'].split(':')[-1]  # Extract speaker name
        key = response['Response'].split(':')[1]
        translation = translate_text(key)
        dialog.append(f"{speaker}: {translation}")
    
    return dialog


source_directory = 'Kingmaker.BarkBanters.BlueprintBarkBanter'
cue_directory = './Kingmaker.DialogSystem.Blueprints.BlueprintCue'
translation_directory = './'
output_directory = './banters'
parse_banter_files(source_directory, cue_directory, translation_directory, output_directory)
