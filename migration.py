import json
import os
import re
import chardet
from bs4 import BeautifulSoup
from atlassian import Confluence
import requests
from dotenv import load_dotenv
import os

file_path = "toolTip_data.json"
images_folder = "images"
space_key = 'EE'

# Load variables from .env into the environment
load_dotenv()

# Get values from environment
url = os.getenv("CONFLUENCE_URL")
username = os.getenv("CONFLUENCE_USERNAME")
api_token = os.getenv("CONFLUENCE_API_TOKEN")

# Authenticate with Confluence
confluence = Confluence(
    url=url,
    username=username,
    password=api_token
)

def make_requests(url,token):
    headers:{
        "Authorization":f"Bearer {token}",
        "Accept":"application/json"
    }
    response=requests.get(url,headers)
        

# Step 1: Detect encoding & load JSON
with open(file_path, "rb") as raw_file:
    raw_data = raw_file.read()
    detected = chardet.detect(raw_data)
    encoding = detected['encoding']

try:
    data = json.loads(raw_data.decode(encoding))
except Exception as e:
    print(f"Failed to decode using {encoding}: {e}")
    exit()

# Step 2: Extract document title
def get_document_title(fields):
    for field in fields:
        if field.get("name") == "DocumentTitle":
            # return re.sub(r'[<>:"/\\|?*]', '', field.get("value", "Untitled Page"))
            return field.get("value","Untitled Page")
    return "Untitled Page"

title = get_document_title(data.get("fields", []))

# Step 3: Build info_lookup map from external information
external_info_list = data.get("external", {}).get("information", [])
info_lookup = {item["informationId"]: item for item in external_info_list if "informationId" in item}

# Step 4: Content building
html_parts = []

def extract_content_from_fields(fields):
    link_text = None
    hidden_text = None

    for field in fields:
        name = field.get("name")
        value = field.get("value", "")

        if name == "LinkText":
            link_text = value
        elif name == "HiddenText":
            hidden_text = value
        elif name in ["Text", "VisibleText"]:
            if value:
                html_parts.append(value)

    if link_text and hidden_text:
        expand_macro = f"""
<ac:structured-macro ac:name="expand">
  <ac:parameter ac:name="title">{link_text}</ac:parameter>
  <ac:rich-text-body>
    {hidden_text}
  </ac:rich-text-body>
</ac:structured-macro>
"""
        html_parts.append(expand_macro)

def recurse_children(children):
    for child in children:
        if "fields" in child:
            extract_content_from_fields(child["fields"])
        if "children" in child and child["children"]:
            recurse_children(child["children"])

if "fields" in data:
    extract_content_from_fields(data["fields"])
if "children" in data:
    recurse_children(data["children"])

html_content = "\n".join(html_parts)

# Step 5: Image macro logic
def generate_image_macro(filename):
    return f'''
<ac:image ac:height="30" ac:width="50" >
  <ri:attachment ri:filename="{filename}"/>
</ac:image>
'''.strip()

def get_tooltip_panel_content(external_id):
    entry = info_lookup.get(external_id)
    if not entry:
        return None

    info_type = entry.get("informationType")
    content = entry.get("content", "")

    if info_type == "Image / screenshot":
        soup = BeautifulSoup(content, "html.parser")
        img_tag = soup.find("img")
        if not img_tag or not img_tag.get("itemid"):
            return None
        item_id = img_tag["itemid"]

        for file in os.listdir(images_folder):
            print(" -", file)
            if file.startswith(item_id):
                return generate_image_macro(file)

    if info_type is None:
        title = entry.get("title", "Untitled")
        return f"<h3>{title}</h3>\n{content}"

    return None

def highlight_externalid(html_content):
    pattern = re.compile(
        r'(<[^>]*data-externalid="([^"]+)"[^>]*>)(.*?)</[^>]+>',
        re.DOTALL | re.IGNORECASE
    )
    
    def html_to_tooltip_text(html_fragment):
        soup = BeautifulSoup(html_fragment, "html.parser")

    # Optional: remove problematic tags
        for tag in soup.find_all(["script", "style"]):
           tag.decompose()

        return str(soup).strip()


    def repl(match):
        _, external_id, inner_text = match.group(1), match.group(2), match.group(3)
        result = get_tooltip_panel_content(external_id)

        if not result:
            return match.group(0)

        if result.strip().startswith("<ac:image"):
            return result

        tooltip_text = html_to_tooltip_text(result)
        return f'''
<ac:structured-macro ac:name="tooltip" ac:schema-version="1" ac:local-id="tooltip-{external_id}" ac:macro-id="tooltip-{external_id}">
  <ac:parameter ac:name="linkText">{inner_text.strip()}</ac:parameter>
  <ac:rich-text-body>
    {tooltip_text}
  </ac:rich-text-body>
</ac:structured-macro>
'''.strip()

    return pattern.sub(repl, html_content)

html_content = highlight_externalid(html_content)

# Step 6: Create page
try:
    result = confluence.create_page(
        space=space_key,
        title=title,
        body=html_content,
        representation='storage'
    )
    print(f"✅ Page created: {result['_links']['base']}{result['_links']['webui']}")
except Exception as e:
    print(f"Failed to create Confluence page: {e}")
    exit()

# Step 7: Upload images to the created page
page_id = result["id"]
uploaded = []

for file in os.listdir(images_folder):
    file_path_full = os.path.join(images_folder, file)
    try:
        confluence.attach_file(
            filename=file_path_full,
            name=file,
            content_type='image/png',
            page_id=page_id
        )
        uploaded.append(file)
    except Exception as e:
        print(f"Failed to upload {file}: {e}")

print(f"📷 Uploaded {len(uploaded)} images: {uploaded}")
