import json
import re
import chardet
from atlassian import Confluence

file_path = "ToolTIp_data.json"

# Detect encoding & load JSON
with open(file_path, "rb") as raw_file:
    raw_data = raw_file.read()
    detected = chardet.detect(raw_data)
    encoding = detected['encoding']

try:
    data = json.loads(raw_data.decode(encoding))
except Exception as e:
    print(f"❌ Failed to decode using {encoding}: {e}")
    exit()

# Extract document title
def get_document_title(fields):
    for field in fields:
        if field.get("name") == "DocumentTitle":
            return re.sub(r'[<>:"/\\|?*]', '', field.get("value", "Untitled Page"))
    return "Untitled Page"

title = get_document_title(data.get("fields", []))

# Extract content fields and accumulate HTML parts
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

# Run extraction
if "fields" in data:
    extract_content_from_fields(data["fields"])
if "children" in data:
    recurse_children(data["children"])

# Join all content
html_content = "\n".join(html_parts)


# === FUNCTION to highlight data-externalid and insert info panel ===

# === Build a lookup map from external["information"] list ===
external_info_list = data.get("external", {}).get("information", [])
info_lookup = {item["informationId"]: item for item in external_info_list if "informationId" in item}

def get_info_panel_content(external_id):
    """
    Returns formatted info panel content if informationType is null.
    Otherwise returns None to skip.
    """
    entry = info_lookup.get(external_id)
    if not entry:
        return None

    if entry.get("informationType") is not None:
        return None  # ⛔ Skip info panels with non-null infoType

    title = entry.get("title", "Untitled")
    content = entry.get("content", "No content provided.")

    return f"<h3>{title}</h3>\n{content}"


def highlight_externalid(html_content):
    """
    Replace tooltip tags (with data-externalid) with info panels only if informationType is null.
    """
    pattern = re.compile(
        r'(<[^>]*data-externalid="([^"]+)"[^>]*>)(.*?)</[^>]+>',
        re.DOTALL | re.IGNORECASE
    )

    def repl(match):
        start_tag, external_id, inner_text = match.group(1), match.group(2), match.group(3)
        tag_name = re.findall(r'^<(\w+)', start_tag)[0]
        end_tag = f'</{tag_name}>'

        info_panel_content = get_info_panel_content(external_id)
        if not info_panel_content:
            # 🟡 Return original tag unchanged if no info panel is needed
            return f'{start_tag}{inner_text}{end_tag}'

        # Add inline styling
        styled_tag = (
            re.sub(
                r'style="([^"]*)"',
                lambda m: f'style="{m.group(1)}; color: violet; text-decoration: underline; cursor: pointer;"',
                start_tag
            ) if 'style=' in start_tag else
            start_tag.replace(
                '>',
                ' style="color: violet; text-decoration: underline; cursor: pointer;">'
            )
        )

        info_panel = f'''
<ac:structured-macro ac:name="info">
  <ac:rich-text-body>
    {info_panel_content}
  </ac:rich-text-body>
</ac:structured-macro>
        '''.strip()

        return f'{styled_tag}{inner_text}{end_tag}{info_panel}'

    return pattern.sub(repl, html_content)



# Highlight externalid text in the extracted html content
html_content = highlight_externalid(html_content)

# Add JavaScript toggle function to the page body (optional, if needed)
js_toggle_script = """
<script>
function toggleInfoPanel(el) {
  const panel = el.nextElementSibling;
  if (panel.style.display === "none") {
    panel.style.display = "block";
  } else {
    panel.style.display = "none";
  }
}
</script>
"""

html_content += js_toggle_script
