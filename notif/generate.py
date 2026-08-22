import os
import sys
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

# ----------------------------------------------------------------------
# Fetch and parse the original RSS feed
# ----------------------------------------------------------------------
RSS_URL = "https://subsplease.org/rss/?t&r=1080"

# Global list to hold all processed items (each as dict with title, link, description)
items_data = []

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

def get_all_items(rss_xml):
    """Parse RSS and return a list of (title, link) for all items."""
    try:
        root = ET.fromstring(rss_xml)
    except ET.ParseError as e:
        print(f"❌ Failed to parse RSS: {e}")
        sys.exit(1)

    items = root.findall('./channel/item')
    if not items:
        print("❌ No items found in RSS.")
        sys.exit(1)

    result = []
    for item in items:
        title_elem = item.find('title')
        link_elem = item.find('link')
        if title_elem is None or title_elem.text is None:
            continue  # skip items without a title
        title = title_elem.text.strip()
        link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
        result.append((title, link))
    return result

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

def get_base_anime_title(transformed_title):
    """
    Extract the base anime name from a transformed title like "Hell Mode S2 - 08".
    Returns e.g., "Hell Mode".
    """
    # Split on " - " to separate anime part from episode number
    if " - " in transformed_title:
        base = transformed_title.split(" - ", 1)[0]
    else:
        base = transformed_title

    # Remove season indicators like " S2", " S02", " Season 2", etc.
    base = re.sub(r'\s+S\d+$', '', base)                      # " S2" at end
    base = re.sub(r'\s+Season\s*\d+$', '', base, flags=re.IGNORECASE)
    return base.strip()

def build_mal_search_url(anime_title):
    """Return a MyAnimeList search URL for the given anime title."""
    encoded = urllib.parse.quote(anime_title)
    return f"https://myanimelist.net/anime.php?q={encoded}"

# ----------------------------------------------------------------------
# generate_rss() now uses the global items_data to create multiple items
# ----------------------------------------------------------------------
def generate_rss():
    # Build the channel header
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Air Notif - RSS Feed</title>
<link>https://github.com</link>
<description>Airing notification for feed</description>
"""
    # Add each item
    for item in items_data:
        safe_title = escape(item['title'])
        safe_link = escape(item['link'])
        safe_description = escape(item['description'])
        rss += f"""
<item>
    <title>{safe_title}</title>
    <link>{safe_link}</link>
    <description>{safe_description} !اومد </description>
</item>"""
    # Close channel and rss
    rss += '\n</channel>\n</rss>'
    return rss

# ----------------------------------------------------------------------
# Main execution
# ----------------------------------------------------------------------
def main():
    global items_data

    # 1. Fetch the original RSS
    rss_xml = fetch_rss(RSS_URL)

    # 2. Get all items (title, link)
    all_items = get_all_items(rss_xml)

    # 3. Process each item
    for orig_title, orig_link in all_items:
        # Transform the title
        new_title = transform_title(orig_title)
        # Extract the base anime name
        base_anime = get_base_anime_title(new_title)
        # Build the MAL search URL
        mal_link = build_mal_search_url(base_anime)

        items_data.append({
            'title': new_title,
            'link': mal_link,                # now points to MAL search
            'description': new_title         # still the episode title
        })

    # 4. Write to file using the exact generate_rss() and try/except block
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
