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
            # Skip non-article pages
            if '/advertise' in article_url or '/blind-ranking' in article_url or '/tag/' in article_url:
                continue
            items.append({
                'bluesky_link': link,
                'article_url': article_url,
                'description': description
            })
    return items

# ----------------------------------------------------------------------
# Fetch article: returns (title, content_with_br) – no external libs
# ----------------------------------------------------------------------
def fetch_article(url):
    """Fetch article and return (title, paragraphs joined with <br>)."""
    headers = {'User-Agent': USER_AGENT}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  ⚠️ Could not fetch article: {e}")
        return None, None

    # ---- Extract title ----
    title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = strip_html(title_match.group(1)).strip()
        # Remove site suffix like " - Gacha Go!" or " | Gacha Go!"
        title = re.sub(r'\s*[-|]\s*Gacha Go!.*$', '', title)
        if not title:
            title = "Gacha Go! Article"
    else:
        title = "Gacha Go! Article"

    # ---- Extract content paragraphs ----
    # Remove scripts, styles, nav, header, footer, aside
    html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<nav.*?>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<header.*?>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<footer.*?>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<aside.*?>.*?</aside>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<ins.*?>.*?</ins>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Extract all <p>...</p> blocks
    paragraphs = re.findall(r'<p.*?>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)

    if paragraphs:
        texts = []
        for p in paragraphs:
            p_text = strip_html(p).strip()
            # Keep only substantial paragraphs (>= 30 chars) to skip navigation/ads
            if len(p_text) >= 30:
                texts.append(p_text)
        if texts:
            content = '<br>'.join(texts)
            return title, content

    # Fallback: split by newlines or periods if no <p> tags
    text = strip_html(html)
    # Split into sentences by period, keep long ones
    sentences = [s.strip() for s in text.split('. ') if len(s) > 30]
    if sentences:
        content = '<br>'.join(sentences)
        return title, content

    return title, None  # No content found

# ----------------------------------------------------------------------
# Generate RSS with CDATA
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
        description = item['description'] if item['description'] else "No content available"
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

        title, content = fetch_article(article_url)

        if title is None:
            title = "Gacha Go! Article"
        if content is None:
            content = "No content could be retrieved."
        else:
            # Log how many paragraphs we got
            para_count = content.count('<br>') + 1
            print(f"  📝 Extracted {para_count} paragraphs, {len(content.split())} words")

        items_data.append({
            'title': title,
            'link': article_url,
            'description': content
        })
        processed += 1
        print(f"  ✅ Added item {processed}: {title[:50]}")

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
