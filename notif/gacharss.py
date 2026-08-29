import os
import sys
import re
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

# ----------------------------------------------------------------------
# Optional: BeautifulSoup for better parsing (recommended)
# ----------------------------------------------------------------------
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("⚠️ BeautifulSoup not installed. Install with: pip install beautifulsoup4")

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
SOURCE_RSS = "https://bsky.app/profile/did:plc:z6tuqt4wk6dmvhxnotxmamvi/rss"
MAX_ITEMS = 10
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

items_data = []

# ----------------------------------------------------------------------
# Helper: strip HTML tags (fallback if BeautifulSoup is missing)
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
# Fetch the source RSS feed
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
# Parse RSS and extract article URLs
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
# Fetch and clean article content (returns <br>-separated paragraphs)
# ----------------------------------------------------------------------
def fetch_article_content(url):
    """Fetch article and return paragraphs joined with <br>."""
    headers = {'User-Agent': USER_AGENT}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  ⚠️ Could not fetch article: {e}")
        return None

    # Use BeautifulSoup if available (preferred)
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted elements
        for tag in soup(['script', 'style', 'ins', 'iframe', 'noscript', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()

        # Try main content container
        content_div = soup.find('div', class_=re.compile(r'entry-content|post-content|article-content'))
        if not content_div:
            content_div = soup.find('div', class_=re.compile(r'content'))

        if content_div:
            paragraphs = content_div.find_all('p')
            if paragraphs:
                texts = []
                for p in paragraphs:
                    p_text = p.get_text(separator=" ").strip()
                    # Keep paragraphs longer than 20 chars (likely real content)
                    if len(p_text) > 20:
                        texts.append(p_text)
                if texts:
                    return '<br>'.join(texts)

        # Fallback: all paragraphs
        all_paragraphs = soup.find_all('p')
        if all_paragraphs:
            clean_texts = []
            for p in all_paragraphs:
                p_text = p.get_text(separator=" ").strip()
                if len(p_text) > 20:
                    clean_texts.append(p_text)
            if clean_texts:
                return '<br>'.join(clean_texts)

    # Regex fallback
    html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<nav.*?>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<footer.*?>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<header.*?>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<aside.*?>.*?</aside>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<ins.*?>.*?</ins>', '', html, flags=re.DOTALL | re.IGNORECASE)

    paragraphs = re.findall(r'<p.*?>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if paragraphs:
        texts = []
        for p in paragraphs:
            p_text = strip_html(p).strip()
            if len(p_text) > 20:
                texts.append(p_text)
        if texts:
            return '<br>'.join(texts)

    return None

# ----------------------------------------------------------------------
# Generate the new RSS feed with CDATA-wrapped description
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
        # Use CDATA to preserve <br> tags in description
        description = item['description'] if item['description'] else "No content available"
        # Escape any CDATA closing sequence to avoid breaking XML
        description = description.replace(']]>', ']]]]><![CDATA[>')
        safe_description = f"<![CDATA[{description}]]>"
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

        # Always add an item, even if content extraction fails
        if content is None:
            content = "Content could not be retrieved."

        items_data.append({
            'title': "Gacha Go! Article",
            'link': article_url,
            'description': content
        })
        processed += 1
        print(f"  ✅ Added item {processed}")

        if processed < min(len(items), MAX_ITEMS):
            time.sleep(1)

    print(f"✅ Processed {processed} items")

    # Write the RSS file
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
