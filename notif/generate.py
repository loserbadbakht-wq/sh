import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

# ----------------------------------------------------------------------
# Fetch and parse the original RSS feed
# ----------------------------------------------------------------------
RSS_URL = "https://subsplease.org/rss/?t&r=1080"

# Global variables to hold the processed data
latest_title = ""
latest_link = ""
latest_description = ""

def fetch_rss(url):
    """Fetch RSS content with a proper User-Agent header."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
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
    # Remove the prefix "[SubsPlease] "
    if original_title.startswith("[SubsPlease] "):
        title = original_title[len("[SubsPlease] "):]
    else:
        title = original_title

    # Remove everything after the first " ("
    if " (" in title:
        title = title.split(" (", 1)[0]

    return title.strip()

# ----------------------------------------------------------------------
# The exact generate_rss() function you requested (with global variables)
# ----------------------------------------------------------------------
def generate_rss():
    # Use the global variables populated earlier
    safe_title = escape(latest_title)
    safe_link = escape(latest_link)
    safe_description = escape(latest_description)

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
"""
    rss += '\n</channel>\n</rss>'
    return rss

# ----------------------------------------------------------------------
# Main execution
# ----------------------------------------------------------------------
def main():
    global latest_title, latest_link, latest_description

    # 1. Fetch the original RSS
    rss_xml = fetch_rss(RSS_URL)

    # 2. Extract title and link from the latest item
    orig_title, orig_link = get_latest_item_title_and_link(rss_xml)

    # 3. Transform the title
    new_title = transform_title(orig_title)

    # 4. Store in global variables for generate_rss()
    latest_title = new_title
    latest_link = orig_link
    latest_description = new_title   # Use the transformed title as description

    # 5. Write to file using the exact generate_rss() and try/except block
    try:
        os.makedirs('./notif', exist_ok=True)
        filename = './notif/airing.xml'
        if os.path.exists(filename):
            os.remove(filename)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(generate_rss().strip())
        print('✅ Airing RSS generated successfully.')
    except Exception as e:
        print(f'❌ Failed: {e}')

if __name__ == "__main__":
    main()
