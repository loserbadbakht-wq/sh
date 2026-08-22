import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

# ----------------------------------------------------------------------
# Fetch and parse the original RSS feed
# ----------------------------------------------------------------------
RSS_URL = "https://subsplease.org/rss/?t&r=1080"

def fetch_rss(url):
    """Fetch RSS content from the given URL."""
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        print(f"❌ Failed to fetch RSS: {e}")
        sys.exit(1)

def get_latest_item_title_and_link(rss_xml):
    """Parse RSS, return (title, link) of the first <item>."""
    try:
        root = ET.fromstring(rss_xml)
    except ET.ParseError as e:
        print(f"❌ Failed to parse RSS: {e}")
        sys.exit(1)

    # Find the first <item> element (RSS 2.0)
    item = root.find('./channel/item')
    if item is None:
        print("❌ No items found in RSS.")
        sys.exit(1)

    title_elem = item.find('title')
    link_elem = item.find('link')
    if title_elem is None or title_elem.text is None:
        print("❌ Missing title in item.")
        sys.exit(1)

    title = title_elem.text.strip()
    link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""

    return title, link

def transform_title(original_title):
    """
    Transform title from:
        [SubsPlease] Hell Mode S2 - 08 (1080p) [F2A317D5].mkv
    to:
        Hell Mode S2 - 08
    """
    # Remove the prefix "[SubsPlease] " (case-sensitive as per example)
    if original_title.startswith("[SubsPlease] "):
        title = original_title[len("[SubsPlease] "):]
    else:
        title = original_title

    # Remove everything after the first occurrence of " ("
    # (this removes the resolution and hash part)
    if " (" in title:
        title = title.split(" (", 1)[0]

    return title.strip()

# ----------------------------------------------------------------------
# Generate the new RSS feed (as a string)
# ----------------------------------------------------------------------
def generate_rss(title, link, description):
    """Return the new RSS XML as a string."""
    # Escape XML special characters
    safe_title = escape(title)
    safe_link = escape(link)
    safe_description = escape(description)

    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Air Notif - RSS Feed</title>
<link>https://github.com</link>
<description>Airing notification for feed</description>
<item>
    <title>{safe_title}</title>
    <link>{safe_link}</link>
    <description>{safe_description}</description>
</item>
</channel>
</rss>"""
    return rss

# ----------------------------------------------------------------------
# Main execution
# ----------------------------------------------------------------------
def main():
    # 1. Fetch the original RSS
    rss_xml = fetch_rss(RSS_URL)

    # 2. Extract title and link from the latest item
    orig_title, orig_link = get_latest_item_title_and_link(rss_xml)

    # 3. Transform the title
    new_title = transform_title(orig_title)

    # 4. Generate the new RSS (use the transformed title as description as well)
    new_rss = generate_rss(new_title, orig_link, new_title)

    # 5. Write to file
    try:
        os.makedirs('./notif', exist_ok=True)
        filename = './notif/airing.xml'
        if os.path.exists(filename):
            os.remove(filename)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(new_rss.strip())
        print('✅ Airing RSS generated successfully.')
    except Exception as e:
        print(f'❌ Failed: {e}')

if __name__ == "__main__":
    main()
