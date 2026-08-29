import os
import sys
import re
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from html.parser import HTMLParser

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
SOURCE_RSS = "https://bsky.app/profile/did:plc:z6tuqt4wk6dmvhxnotxmamvi/rss"
MAX_ITEMS = 10
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Words/phrases to filter out (case‑insensitive)
BLACKLIST = [
    r'advertisement', r'ad', r'promoted',
    r'home', r'games', r'companies', r'news',
    r'all', r'announced', r'projects', r'pre[ -]register', r'releases', r'updates',
    r'join', r'discord', r'twitter', r'facebook', r'youtube', r'instagram',
    r'subscribe', r'newsletter',
    r'search', r'menu', r'navigation',
    r'about', r'contact', r'privacy', r'terms'
]
BLACKLIST_RE = re.compile(r'\b(' + '|'.join(BLACKLIST) + r')\b', re.IGNORECASE)

items_data = []

# ----------------------------------------------------------------------
# HTML stripping helper
# ----------------------------------------------------------------------
class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, d):
        self.text.append(d)
    def get_data(self):
        return ''.join(self.text)

def strip_html(html):
    if not html:
        return ""
    s = MLStripper()
    s.feed(html)
    return s.get_data().strip()

# ----------------------------------------------------------------------
# Fetch RSS feed
# ----------------------------------------------------------------------
def fetch_rss(url):
    headers = {'User-Agent': USER_AGENT}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        print(f"❌ Failed to fetch RSS: {e}")
        sys.exit(1)

# ----------------------------------------------------------------------
# Parse RSS and extract items
# ----------------------------------------------------------------------
def parse_rss_items(rss_xml):
    try:
        root = ET.fromstring(rss_xml)
    except ET.ParseError as e:
        print(f"❌ Failed to parse RSS: {e}")
        sys.exit(1)

    items = []
    for item in root.findall('./channel/item'):
        link_elem = item.find('link')
        desc_elem = item.find('description')
        link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
        description = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""
        # Extract article URL from description
        url_match = re.search(r'(https?://[^\s]+)', description)
        article_url = url_match.group(1) if url_match else ""
        if link and article_url:
            items.append({
                'bluesky_link': link,
                'article_url': article_url,
                'description': description
            })
    return items

# ----------------------------------------------------------------------
# Clean article content
# ----------------------------------------------------------------------
def clean_paragraph(text):
    """Return True if the paragraph should be kept."""
    text = text.strip()
    if len(text) < 20:
        return False
    # If the text consists mostly of blacklisted terms, drop it
    # Count how many blacklisted words appear
    matches = BLACKLIST_RE.findall(text)
    # If more than 50% of the words are blacklisted, drop it
    words = re.findall(r'\b\w+\b', text)
    if words and (len(matches) / len(words)) > 0.5:
        return False
    # Also drop if the text is just a single blacklisted word
    if len(words) <= 3 and matches:
        return False
    return True

def fetch_article_content(url):
    """Fetch and extract clean article text."""
    headers = {'User-Agent': USER_AGENT}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  ⚠️ Could not fetch article: {e}")
        return None

    # Remove scripts and styles
    html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Extract all paragraphs
    paragraphs = re.findall(r'<p.*?>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if not paragraphs:
        # Fallback: get all text
        text = strip_html(html)
        text = re.sub(r'\s+', ' ', text).strip()
        return text if text else None

    # Clean and filter paragraphs
    cleaned = []
    for p in paragraphs:
        p_text = strip_html(p).strip()
        if p_text and clean_paragraph(p_text):
            cleaned.append(p_text)

    if not cleaned:
        return None

    # Join and clean whitespace
    full_text = ' '.join(cleaned)
    full_text = re.sub(r'\s+', ' ', full_text).strip()
    return full_text

# ----------------------------------------------------------------------
# Generate new RSS feed
# ----------------------------------------------------------------------
def generate_rss():
    rss = f'''<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Gacha Go! Articles</title>
<link>https://gachago.com/en</link>
<description>Latest gacha game news and guides from Gacha Go!</description>
'''
    for item in items_data:
        safe_title = escape(item['title'])
        safe_link = escape(item['link'])
        safe_description = escape(item['description'])
        rss += f'''
<item>
    <title>{safe_title}</title>
    <link>{safe_link}</link>
    <description>{safe_description}</description>
</item>'''
    rss += '\n</channel>\n</rss>'
    return rss

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    global items_data

    print("🔍 Fetching source RSS feed...")
    rss_xml = fetch_rss(SOURCE_RSS)

    print("📋 Parsing RSS items...")
    items = parse_rss_items(rss_xml)
    print(f"📊 Found {len(items)} items")

    processed = 0
    for item in items:
        if processed >= MAX_ITEMS:
            break

        article_url = item['article_url']
        print(f"🔄 Processing: {article_url}")

        content = fetch_article_content(article_url)

        if content:
            items_data.append({
                'title': "Gacha Go! Article",
                'link': article_url,
                'description': content
            })
            processed += 1
            print(f"  ✅ Extracted {len(content.split())} words (after cleaning)")
        else:
            print(f"  ⚠️ No content extracted, skipping")

        if processed < min(len(items), MAX_ITEMS):
            time.sleep(1)

    print(f"✅ Processed {processed} items")

    try:
        os.makedirs('./notif', exist_ok=True)
        filename = './notif/gachago_feed.xml'
        if os.path.exists(filename):
            os.remove(filename)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(generate_rss().strip())
        print('✅ RSS feed generated successfully.')
        print(f'📁 Output file: {filename}')
    except Exception as e:
        print(f'❌ Failed to write file: {e}')

if __name__ == "__main__":
    main()
