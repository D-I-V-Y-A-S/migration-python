import json
import re
import chardet
from atlassian import Confluence

file_path = "output.json"

with open(file_path, "rb") as raw_file:
    raw_data = raw_file.read()
    detected = chardet.detect(raw_data)
    encoding = detected['encoding']

try:
    data = json.loads(raw_data.decode(encoding))
except Exception as e:
    print(f"❌ Failed to decode using {encoding}: {e}")
    exit()

#Document title extraction
def get_document_title(fields):
    for field in fields:
        if field.get("name") == "DocumentTitle":
            return re.sub(r'[<>:"/\\|?*]', '', field.get("value", "Untitled Page"))
    return "Untitled Page"

title = get_document_title(data.get("fields", []))

#Formatting Content
html_parts = []

def extract_content_from_fields(fields):
    for field in fields:
        if field.get("name") in ["Text", "VisibleText", "HiddenText"]:
            value = field.get("value", "")
            if value:
                html_parts.append(value)

#To access every child content
def recurse_children(children):
    for child in children:
        if "fields" in child:
            extract_content_from_fields(child["fields"])
        if "children" in child and child["children"]:
            recurse_children(child["children"])

#Function Triggers
if "fields" in data:
    extract_content_from_fields(data["fields"])
if "children" in data:
    recurse_children(data["children"])

html_content = "\n".join(html_parts)

confluence = Confluence(
    url='',
    username='',
    password=' ' )

#Page Creation
space_key = 'Migration' 

try:
    result = confluence.create_page(
        space=space_key,
        title=title,
        body=html_content,
        representation='storage'  
    )
    print(f"✅ Page created: {result['_links']['base']}{result['_links']['webui']}")
except Exception as e:
    print(f"❌ Failed to create Confluence page: {e}")
