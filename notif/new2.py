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
# Base URL for GitHub raw images
# ----------------------------------------------------------------------
RAW_BASE = "https://raw.githubusercontent.com/loserbadbakht-wq/sh/refs/heads/main/notif/euro_tumb/"

# ----------------------------------------------------------------------
# Sanitize title for use in filename
# ----------------------------------------------------------------------
def sanitize_filename(title):
    title = re.sub(r'[\\/*?:"<>|]', '', title)
    title = re.sub(r'[-\s]+', '_', title)
    title = title.strip('_.')
    title = title.encode('ascii', 'ignore').decode('ascii')
    title = re.sub(r'[^a-zA-Z0-9_.]', '_', title)
    return title[:255] or "untitled"

# ----------------------------------------------------------------------
# Extract thumbnail image URL from article HTML
# ----------------------------------------------------------------------
def extract_image_url(html):
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
# Download thumbnail
# ----------------------------------------------------------------------
def download_thumbnail(article_url, sanitized_title):
    tumb_dir = os.path.join('notif', 'euro_tumb')
    os.makedirs(tumb_dir, exist_ok=True)

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

    if image_url.startswith('//'):
        image_url = 'https:' + image_url
    elif image_url.startswith('/'):
        parsed = urllib.parse.urlparse(article_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        image_url = base + image_url

    ext = os.path.splitext(urllib.parse.urlparse(image_url).path)[1]
    if not ext or ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        ext = '.jpg'

    local_filename = sanitized_title + ext
    local_path = os.path.join(tumb_dir, local_filename)

    try:
        img_req = urllib.request.Request(image_url, headers=headers)
        with urllib.request.urlopen(img_req, timeout=15) as response:
            image_data = response.read()
            with open(local_path, 'wb') as f:
                f.write(image_data)
        print(f"  ✅ Saved thumbnail: {local_path}")
    except Exception as e:
        print(f"  ⚠️ Failed to download thumbnail: {e}")

    return RAW_BASE + local_filename

# ----------------------------------------------------------------------
# RSS / HTML helpers
# ----------------------------------------------------------------------
RSS_URL = "https://www.eurogamer.net/feed"
items_data = []

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

def fetch_rss(url):
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

# ----------------------------------------------------------------------
# Stack-based extraction of a container (div or section) by class
# ----------------------------------------------------------------------
def extract_container_by_class(html, tag, class_substring):
    """
    Return the inner HTML of the first <tag> whose class attribute contains class_substring.
    Handles nested <tag> correctly using a depth counter.
    """
    # Find the opening tag
    pattern = r'<' + tag + r'[^>]*class="[^"]*' + re.escape(class_substring) + r'[^"]*"[^>]*>'
    match = re.search(pattern, html, re.IGNORECASE)
    if not match:
        return None
    start = match.end()

    open_tag = '<' + tag
    close_tag = '</' + tag + '>'

    depth = 1
    pos = start
    while depth > 0 and pos < len(html):
        next_open = html.lower().find(open_tag, pos)
        next_close = html.lower().find(close_tag, pos)
        if next_close == -1:
            return None
        if next_open != -1 and next_open < next_close:
            # Ensure it's actually the same tag (not <divx>)
            char_after = html[next_open + len(open_tag):next_open + len(open_tag) + 1]
            if char_after in (' ', '>', '\n', '\t', '\r'):
                depth += 1
            pos = next_open + len(open_tag)
        else:
            depth -= 1
            if depth == 0:
                return html[start:next_close]
            pos = next_close + len(close_tag)
    return None

# ----------------------------------------------------------------------
# Fetch article content – clean, paragraphs only
# ----------------------------------------------------------------------
def fetch_page_content(url):
    """Fetch article content and return only the article body paragraphs joined with <br>."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"⚠️ Could not fetch {url}: {e}")
        return "Content unavailable"

    # ---- Isolate the article body ----
    # Eurogamer commonly uses: <section class="article_body"> or <div class="article_body">
    article_html = None
    for candidate in ['article_body', 'article-body', 'article__body', 'article-content']:
        article_html = extract_container_by_class(content, 'section', candidate)
        if not article_html:
            article_html = extract_container_by_class(content, 'div', candidate)
        if article_html:
            break

    # If we couldn't find the article body, fall back to whole page but strip structure
    if not article_html:
        print("  ⚠️ Could not find article body container; falling back to page-wide extraction.")
        article_html = content

    # ---- Remove unwanted elements from the isolated HTML ----
    article_html = re.sub(r'<script.*?>.*?</script>', '', article_html, flags=re.DOTALL | re.IGNORECASE)
    article_html = re.sub(r'<style.*?>.*?</style>', '', article_html, flags=re.DOTALL | re.IGNORECASE)
    article_html = re.sub(r'<aside.*?>.*?</aside>', '', article_html, flags=re.DOTALL | re.IGNORECASE)
    article_html = re.sub(r'<figure.*?>.*?</figure>', '', article_html, flags=re.DOTALL | re.IGNORECASE)
    article_html = re.sub(r'<figcaption.*?>.*?</figcaption>', '', article_html, flags=re.DOTALL | re.IGNORECASE)
    article_html = re.sub(r'<nav.*?>.*?</nav>', '', article_html, flags=re.DOTALL | re.IGNORECASE)
    # Remove embedded ads / promos
    article_html = re.sub(r'<div[^>]*class="[^"]*(?:ad|promo|newsletter|related|share|social|embed)[^"]*"[^>]*>.*?</div>', '', article_html, flags=re.DOTALL | re.IGNORECASE)

    # ---- Extract paragraphs ----
    paragraphs = re.findall(r'<p.*?>(.*?)</p>', article_html, re.DOTALL | re.IGNORECASE)

    texts = []
    for p in paragraphs:
        p_text = strip_html(p).strip()
        # Filter short paragraphs and common Eurogamer noise
        if len(p_text) < 30:
            continue
        if re.search(
            r'(read more|sign up|subscribe|newsletter|advertisement|affiliate|'
            r'support us|become a supporter|follow us|share this|related:|'
            r'click here|comments?|loading|skip to)',
            p_text, re.IGNORECASE
        ):
            continue
        texts.append(p_text)

    if texts:
        return '<br>'.join(texts)

    # ---- Fallback: whole page text (last resort) ----
    text = strip_html(content)
    text = re.sub(r'\s+', ' ', text).strip()
    sentences = [s.strip() for s in text.split('. ') if len(s) > 40]
    if sentences:
        return '<br>'.join(sentences)
    return "Content unavailable"

# ----------------------------------------------------------------------
# Parse RSS
# ----------------------------------------------------------------------
def get_all_items(rss_xml):
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
# Generate RSS
# ----------------------------------------------------------------------
def generate_rss():
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Eurogamer News RSS</title>
<link>https://www.eurogamer.net/feed</link>
<description>Eurogamer News Feed</description>
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
# Main
# ----------------------------------------------------------------------
def main():
    global items_data

    print("🔍 Fetching Eurogamer RSS feed...")
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
        filename = './notif/new2.xml'
        if os.path.exists(filename):
            os.remove(filename)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(generate_rss().strip())
        print('✅ Eurogamer RSS generated successfully.')
        print(f'📁 Output file: {filename}')
    except Exception as e:
        print(f'❌ Failed: {e}')

if __name__ == "__main__":
    main()
