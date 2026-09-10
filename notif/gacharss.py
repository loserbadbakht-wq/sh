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
# Base URL for GitHub raw images – Gacha Go thumbnails
# ----------------------------------------------------------------------
RAW_BASE = "https://raw.githubusercontent.com/loserbadbakht-wq/sh/refs/heads/main/notif/gachago_tumb/"

# ----------------------------------------------------------------------
# Sanitize title for use in filename (ASCII only)
# ----------------------------------------------------------------------
def sanitize_filename(title):
    """Remove problematic characters, replace spaces/hyphens with underscores, and keep ASCII."""
    # Remove invalid filename chars
    title = re.sub(r'[\\/*?:"<>|]', '', title)
    # Replace spaces and hyphens with underscore
    title = re.sub(r'[-\s]+', '_', title)
    # Strip leading/trailing underscores/dots
    title = title.strip('_.')
    # Convert to ASCII, replacing non-ASCII chars with '_'
    title = title.encode('ascii', 'ignore').decode('ascii')
    # Remove any remaining non-alnum except underscore and dot
    title = re.sub(r'[^a-zA-Z0-9_.]', '_', title)
    # Ensure non-empty
    return title[:255] or "untitled"

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
    Fetch the article, extract the main image, download it to ./notif/gachago_tumb/,
    and return the remote GitHub raw URL for the image.
    Returns the remote URL string or None on failure.
    """
    # Create local directory if not exists
    tumb_dir = os.path.join('notif', 'gachago_tumb')
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

    # Download the image with proper User-Agent
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        img_req = urllib.request.Request(image_url, headers=headers)
        with urllib.request.urlopen(img_req, timeout=15) as response:
            image_data = response.read()
            with open(local_path, 'wb') as f:
                f.write(image_data)
        print(f"  ✅ Saved thumbnail: {local_path}")
    except Exception as e:
        print(f"  ⚠️ Failed to download thumbnail locally: {e}")
        # Continue anyway; we can still use the remote URL if we can construct it

    # Build remote GitHub raw URL
    remote_url = RAW_BASE + local_filename
    return remote_url

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
SOURCE_RSS = "https://bsky.app/profile/did:plc:z6tuqt4wk6dmvhxnotxmamvi/rss"
MAX_ITEMS = 10
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

items_data = []

# ----------------------------------------------------------------------
# HTML stripper (for regex fallback)
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
            if '/advertise' in article_url or '/blind-ranking' in article_url or '/tag/' in article_url:
                continue
            items.append({
                'bluesky_link': link,
                'article_url': article_url,
                'description': description
            })
    return items

# ----------------------------------------------------------------------
# Extract the content div with matching closing tag (stack-based)
# ----------------------------------------------------------------------
def extract_div_content(html, div_class):
    """Return the inner HTML of the first <div> with the given class."""
    pattern = r'<div[^>]*class="[^"]*' + re.escape(div_class) + r'[^"]*"[^>]*>'
    match = re.search(pattern, html, re.IGNORECASE)
    if not match:
        return None
    start = match.end()
    depth = 1
    pos = start
    while depth > 0 and pos < len(html):
        next_open = html.find('<div', pos)
        next_close = html.find('</div>', pos)
        if next_close == -1:
            break
        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + 4
        else:
            depth -= 1
            if depth == 0:
                return html[start:next_close]
            pos = next_close + 6
    return None

# ----------------------------------------------------------------------
# Fetch article: returns (title, content_with_br)
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

    title = "Gacha Go! Article"
    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
    if h1_match:
        title = strip_html(h1_match.group(1)).strip()
    else:
        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = strip_html(title_match.group(1)).strip()
            title = re.sub(r'\s*[-|]\s*Gacha Go!.*$', '', title)
    if not title:
        title = "Gacha Go! Article"

    content_html = extract_div_content(html, "entry-content")
    if not content_html:
        content_html = extract_div_content(html, "post-content")
    if not content_html:
        content_html = extract_div_content(html, "content")

    paragraphs = []
    if content_html:
        p_matches = re.findall(r'<p.*?>(.*?)</p>', content_html, re.DOTALL | re.IGNORECASE)
        for p in p_matches:
            p_text = strip_html(p).strip()
            if len(p_text) >= 30 and not re.search(r'advertisement|fund your pulls|cashback|affiliate|discord|subscribe|newsletter|register|login', p_text, re.IGNORECASE):
                paragraphs.append(p_text)
    else:
        html = re.sub(r'<nav.*?>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<header.*?>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<footer.*?>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<aside.*?>.*?</aside>', '', html, flags=re.DOTALL | re.IGNORECASE)
        p_matches = re.findall(r'<p.*?>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
        for p in p_matches:
            p_text = strip_html(p).strip()
            if len(p_text) >= 30 and not re.search(r'advertisement|fund your pulls|cashback|affiliate|discord|subscribe|newsletter|register|login', p_text, re.IGNORECASE):
                paragraphs.append(p_text)

    if paragraphs:
        content = '<br>'.join(paragraphs)
        return title, content

    return title, None

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
        print(f"\n🔄 Processing: {article_url}")

        title, content = fetch_article(article_url)

        if content is None:
            content = "No content could be retrieved."

        sanitized = sanitize_filename(title)
        remote_image_url = download_thumbnail(article_url, sanitized)

        if remote_image_url:
            img_tag = f'<img src="{remote_image_url}" />'
        else:
            img_tag = ''
        if content and content != "No content could be retrieved.":
            description = f'{img_tag}<br>{content}' if img_tag else content
        else:
            description = f'{img_tag}<br>No content available' if img_tag else "No content available"

        items_data.append({
            'title': title or "Gacha Go! Article",
            'link': article_url,
            'description': description
        })
        processed += 1
        print(f"  ➕ Added item {processed}: {items_data[-1]['title'][:50]}")

        if processed < min(len(items), MAX_ITEMS):
            time.sleep(1)

    print(f"\n✅ Processed {processed} items")

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
