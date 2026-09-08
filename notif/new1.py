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
# Fetch and parse the original IGN RSS feed
# ----------------------------------------------------------------------
RSS_URL = "https://feeds.feedburner.com/ign/news"

# Global list to hold all processed items
items_data = []

class MLStripper(HTMLParser):
    """Simple HTML stripper to get plain text from HTML content."""
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []
    
    def handle_data(self, d):
        self.text.append(d)
    
    def get_data(self):
        return ''.join(self.text)

def strip_html(html):
    """Strip HTML tags and return plain text."""
    if not html:
        return ""
    s = MLStripper()
    s.feed(html)
    return s.get_data().strip()

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

def fetch_page_content(url):
    """Fetch article content and return paragraphs joined with <br>."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read().decode('utf-8', errors='ignore')
            # Remove scripts and styles
            content = re.sub(r'<script.*?>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<style.*?>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
            # Extract text from paragraphs
            paragraphs = re.findall(r'<p.*?>(.*?)</p>', content, re.DOTALL | re.IGNORECASE)
            if paragraphs:
                # Clean each paragraph and join with <br>
                texts = []
                for p in paragraphs:
                    p_text = strip_html(p).strip()
                    if len(p_text) > 20:  # filter out short/navigation paragraphs
                        texts.append(p_text)
                if texts:
                    return '<br>'.join(texts)
            else:
                # Fallback: get all text (split by newlines or periods)
                text = strip_html(content)
                text = re.sub(r'\s+', ' ', text).strip()
                # Split into sentences and join with <br> (approximate)
                sentences = [s.strip() for s in text.split('. ') if len(s) > 20]
                if sentences:
                    return '<br>'.join(sentences)
                return text
    except Exception as e:
        print(f"⚠️ Could not fetch {url}: {e}")
        return "Content unavailable"
    return "Content unavailable"

def get_all_items(rss_xml):
    """Parse RSS and return a list of (title, description, link) for all items."""
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
        desc_elem = item.find('description')
        link_elem = item.find('link')
        
        title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
        description = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""
        # Remove HTML tags from description for clean text
        description = strip_html(description)
        link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
        
        if title and link:  # Only include items with at least title and link
            result.append((title, description, link))
    return result

# ----------------------------------------------------------------------
# generate_rss() now uses CDATA for description
# ----------------------------------------------------------------------
def generate_rss():
    """Generate RSS feed with transformed items."""
    # Build the channel header
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>IGN News RSS</title>
<link>https://feeds.feedburner.com/ign/news</link>
<description>Transformed IGN News Feed</description>
"""
    # Add each item
    for item in items_data:
        safe_title = escape(item['title'])      # IGN description as our title
        safe_link = escape(item['link'])        # Original IGN link
        # Wrap description in CDATA to preserve <br> tags
        description = item['description'] if item['description'] else "No content available"
        # Escape any CDATA closing sequence
        description = description.replace(']]>', ']]]]><![CDATA[>')
        safe_description = f"<![CDATA[{description}]]>"
        
        rss += f"""
<item>
    <title>{safe_title}</title>
    <link>{safe_link}</link>
    <description>{safe_description}</description>
</item>"""
    # Close channel and rss
    rss += '\n</channel>\n</rss>'
    return rss

# ----------------------------------------------------------------------
# Main execution
# ----------------------------------------------------------------------
def main():
    global items_data

    print("🔍 Fetching IGN RSS feed...")
    rss_xml = fetch_rss(RSS_URL)
    
    print("📋 Parsing RSS items...")
    all_items = get_all_items(rss_xml)
    print(f"📊 Found {len(all_items)} items")

    # Process each item (limit to 50 items to avoid excessive requests)
    max_items = 50
    processed = 0
    
    for orig_title, orig_description, orig_link in all_items:
        if processed >= max_items:
            break
            
        print(f"🔄 Processing: {orig_title[:50]}...")
        
        # Fetch content from the link
        print(f"📡 Fetching content from: {orig_link[:50]}...")
        page_content = fetch_page_content(orig_link)
        
        items_data.append({
            'title': orig_description,   # IGN description becomes our title
            'link': orig_link,           # Original link stays the same
            'description': page_content  # Content with <br> formatting
        })
        processed += 1
        
        # Add a small delay to be nice to the servers
        if processed < min(len(all_items), max_items):
            time.sleep(1)

    print(f"✅ Processed {processed} items")

    # Write to file
    try:
        os.makedirs('./notif', exist_ok=True)
        filename = './notif/new1.xml'
        if os.path.exists(filename):
            os.remove(filename)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(generate_rss().strip())
        print('✅ IGN RSS generated successfully.')
        print(f'📁 Output file: {filename}')
    except Exception as e:
        print(f'❌ Failed: {e}')

if __name__ == "__main__":
    main()
