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
# Base URL for GitHub raw images – now using the new repository
# ----------------------------------------------------------------------
RAW_BASE = "https://raw.githubusercontent.com/loserbadbakht-wq/sh/refs/heads/main/notif/ign_tumb/"

# ----------------------------------------------------------------------
# Sanitize title for use in filename
# ----------------------------------------------------------------------
def sanitize_filename(title):
    """Remove problematic characters and replace spaces/hyphens with underscores."""
    title = re.sub(r'[\\/*?:"<>|]', '', title)   # remove invalid filename chars
    title = re.sub(r'[-\s]+', '_', title)        # replace spaces and hyphens with underscore
    title = title.strip('_.')                    # strip leading/trailing underscores/dots
    return title[:255] or "untitled"             # ensure non-empty

# ----------------------------------------------------------------------
# Extract thumbnail image URL from article HTML
# ----------------------------------------------------------------------
def extract_image_url(html):
    """Return the URL of the main article image (og:image, twitter:image, or first img)."""
    og_match = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if og_match:
        return og_match.group(1)
    tw_match = re.search(r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if tw_match:
        return tw_match.group(1)
    content_div = re.search(r'<div[^>]*class="[^"]*(?:content|post|article)[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
    if content_div:
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_div.group(1), re.IGNORECASE)
        if img_match:
            return img_match.group(1)
    all_imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    for img_url in all_imgs:
        if 'logo' in img_url.lower() or 'icon' in img_url.lower() or 'ad' in img_url.lower():
            continue
        return img_url
    return None

# ----------------------------------------------------------------------
# Download thumbnail and return remote GitHub raw URL
# ----------------------------------------------------------------------
def download_thumbnail(article_url, sanitized_title):
    """
    Fetch the article, extract the main image, download it to ./notif/ign_tumb/,
    and return the remote GitHub raw URL for the image.
    Returns the remote URL string or None on failure.
    """
    # Create local directory if not exists
    tumb_dir = os.path.join('notif', 'ign_tumb')
    os.makedirs(tumb_dir, exist_ok=True)

    # Fetch the article HTML
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(article_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  ⚠️ Could not fetch article for thumbnail: {e}")
        return None

    image_url = extract_image_url(html)
    if not image_url:
        print("  ⚠️ No image found in article.")
        return None

    # Resolve relative URLs
    if image_url.startswith('//'):
        image_url = 'https:' + image_url
    elif image_url.startswith('/'):
        parsed = urllib.parse.urlparse(article_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        image_url = base + image_url

    # Determine file extension
    ext = os.path.splitext(urllib.parse.urlparse(image_url).path)[1]
    if not ext or ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        ext = '.jpg'  # default

    local_filename = sanitized_title + ext
    local_path = os.path.join(tumb_dir, local_filename)

    # Download the image locally (for archiving)
    try:
        print(f"  📥 Downloading thumbnail: {image_url[:80]}...")
        urllib.request.urlretrieve(image_url, local_path)
        print(f"  ✅ Saved thumbnail: {local_path}")
    except Exception as e:
        print(f"  ⚠️ Failed to download thumbnail locally: {e}")
        # Continue anyway; we can still use the remote URL if we can construct it

    # Build remote GitHub raw URL (now using the new repository)
    remote_url = RAW_BASE + local_filename
    return remote_url

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
            content = re.sub(r'<script.*?>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<style.*?>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
            paragraphs = re.findall(r'<p.*?>(.*?)</p>', content, re.DOTALL | re.IGNORECASE)
            if paragraphs:
                texts = []
                for p in paragraphs:
                    p_text = strip_html(p).strip()
                    if len(p_text) > 20:
                        texts.append(p_text)
                if texts:
                    return '<br>'.join(texts)
            else:
                text = strip_html(content)
                text = re.sub(r'\s+', ' ', text).strip()
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
        description = strip_html(description)
        link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
        
        if title and link:
            result.append((title, description, link))
    return result

# ----------------------------------------------------------------------
# generate_rss() now uses CDATA for description
# ----------------------------------------------------------------------
def generate_rss():
    """Generate RSS feed with transformed items."""
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>IGN News RSS</title>
<link>https://feeds.feedburner.com/ign/news</link>
<description>Transformed IGN News Feed</description>
"""
    for item in items_data:
        safe_title = escape(item['title'])
        safe_link = escape(item['link'])
        description = item['description'] if item['description'] else "No content available"
        description = description.replace(']]>', ']]]]><![CDATA[>')
        safe_description = f"<![CDATA[{description}]]>"
        
        rss += f"""
<item>
    <title>{safe_title}</title>
    <link>{safe_link}</link>
    <description>{safe_description}</description>
</item>"""
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

    max_items = 50
    processed = 0
    
    for orig_title, orig_description, orig_link in all_items:
        if processed >= max_items:
            break
            
        print(f"🔄 Processing: {orig_title[:50]}...")
        print(f"📡 Fetching content from: {orig_link[:50]}...")
        page_content = fetch_page_content(orig_link)
        
        sanitized = sanitize_filename(orig_title)
        remote_image_url = download_thumbnail(orig_link, sanitized)
        
        if remote_image_url:
            img_tag = f'<img src="{remote_image_url}" />'
        else:
            img_tag = ''
        if page_content:
            description = f'{img_tag}<br>{page_content}' if img_tag else page_content
        else:
            description = f'{img_tag}<br>No content available' if img_tag else "No content available"
        
        items_data.append({
            'title': orig_description,
            'link': orig_link,
            'description': description
        })
        processed += 1
        
        if processed < min(len(all_items), max_items):
            time.sleep(1)

    print(f"✅ Processed {processed} items")

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
