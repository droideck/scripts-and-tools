"""The FoundryVTT Journal Creator is a Python script designed to convert HTML-formatted
input into a JSON file suitable for use as a journal entry in Foundry Virtual TableTop (FoundryVTT).

This script is particularly useful for creating structured journal entries from documents
that are divided into sections, allowing for easier integration and organization within FoundryVTT.

Requirements:
- HTML in a format that can be split into sections based on <h3> tags
"""

import json

def convert_data(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as file:
        data = file.read()

    # Split the data into sections based on <h3> tags
    sections = data.split('<h3>')
    sections = [section.strip() for section in sections if section.strip()]

    # Extract the name and pages from the sections
    name = sections[0].split('</h3>')[0].strip()
    pages = []

    for i, section in enumerate(sections[1:], start=1):
        title, content = section.split('</h3>')
        title = title.strip()
        content = content.strip()

        page = {
            "sort": i * 100000,
            "name": title,
            "type": "text",
            "title": {
                "show": True,
                "level": 2 if i > 1 else 1
            },
            "image": {},
            "text": {
                "format": 1,
                "content": content
            },
            "video": {
                "controls": True,
                "volume": 0.5
            },
            "src": None,
            "system": {},
            "ownership": {
                "default": -1
            },
            "flags": {}
        }
        pages.append(page)

    output_data = {
        "folder": None,
        "name": name,
        "pages": pages,
        "flags": {
            "core": {
                "sheetClass": "pf2e-kingmaker.KingmakerJournalSheet"
            },
            "exportSource": {
                "world": "km-panda-goes-wild",
                "system": "pf2e",
                "coreVersion": "11.315",
                "systemVersion": "5.13.6"
            }
        }
    }

    with open(output_file, 'w', encoding='utf-8') as file:
        json.dump(output_data, file, ensure_ascii=False, indent=2)

# Usage example
input_file = 'input.txt'
output_file = 'output.json'
convert_data(input_file, output_file)