import os
import sys
import re
import time
import hashlib
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
# STABLE filename derived from article URL slug (not the mutable title)
# ----------------------------------------------------------------------
def get_stable_filename(article_url):
    """
    Derive a stable, sanitized filename from the article URL slug.

    IGN rewrites headlines frequently but keeps URL slugs fixed, so this
    guarantees that re-runs map to the same image filename and prevent
    404s in previously generated XML.

    Note: '%' is stripped because it is a URL metacharacter and, if left
    in a filename, produces malformed raw.githubusercontent.com URLs.
    """
    parsed = urllib.parse.urlparse(article_url)
    slug = parsed.path.rstrip('/').split('/')[-1]
    if not slug:
        slug = hashlib.md5(article_url.encode()).hexdigest()[:16]
    slug = re.sub(r'[\\/*?:"<>|%]', '', slug)
    slug = re.sub(r'[-\s]+', '_', slug)
    slug = slug.strip('_.')
    return slug[:255] or "untitled"

# ----------------------------------------------------------------------
# Sanitize title (kept for backwards compat / fallback use)
# ----------------------------------------------------------------------
def sanitize_filename(title):
    title = re.sub(r'[\\/*?:"<>|%]', '', title)
    title = re.sub(r'[-\s]+', '_', title)
    title = title.strip('_.')
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
# Download thumbnail and return remote GitHub raw URL
# ----------------------------------------------------------------------
def download_thumbnail(article_url, stable_name):
    tumb_dir = os.path.join('notif', 'ign_tumb')
    os.makedirs(tumb_dir, exist_ok=True)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
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

    local_filename = stable_name + ext
    local_path = os.path.join(tumb_dir, local_filename)

    try:
        print(f"  📥 Downloading thumbnail: {image_url[:80]}...")
        urllib.request.urlretrieve(image_url, local_path)
        print(f"  ✅ Saved thumbnail: {local_path}")
    except Exception as e:
        print(f"  ⚠️ Failed to download thumbnail locally: {e}")

    # URL-encode the filename so %, comma, parens, spaces resolve on GitHub.
    remote_url = RAW_BASE + urllib.parse.quote(local_filename)
    return remote_url

# ----------------------------------------------------------------------
# RSS / HTML helpers
# ----------------------------------------------------------------------
RSS_URL = "https://feeds.feedburner.com/ign/news"

items_data = []

class MLStripper(HTMLParser):
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
    if not html:
        return ""
    s = MLStripper()
    s.feed(html)
    return s.get_data().strip()

def fetch_rss(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        print(f"❌ Failed to fetch RSS: {e}")
        sys.exit(1)

# ----------------------------------------------------------------------
# Stack-based extraction of a container (div/section) by class substring
# ----------------------------------------------------------------------
def extract_container_by_class(html, tag, class_substring):
    """
    Return the inner HTML of the first <tag> whose class contains class_substring.
    Handles nested <tag> correctly using a depth counter.
    """
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
            ch = html[next_open + len(open_tag):next_open + len(open_tag) + 1]
            if ch in (' ', '>', '\n', '\t', '\r', '/'):
                depth += 1
            pos = next_open + len(open_tag)
        else:
            depth -= 1
            if depth == 0:
                return html[start:next_close]
            pos = next_close + len(close_tag)
    return None

# ----------------------------------------------------------------------
# Remove all elements matching <tag ... attr_regex ...>...</tag> (depth-aware)
# ----------------------------------------------------------------------
def remove_element(html, tag, attr_regex):
    """
    Remove all elements whose opening tag matches tag + attr_regex.
    Uses depth counting so nested same-name tags are handled correctly.
    """
    open_pattern = re.compile(
        r'<' + tag + r'[^>]*' + attr_regex + r'[^>]*>',
        re.IGNORECASE
    )
    result = []
    pos = 0
    open_tag = '<' + tag.lower()
    close_tag = '</' + tag.lower() + '>'

    while pos < len(html):
        match = open_pattern.search(html, pos)
        if not match:
            result.append(html[pos:])
            break

        result.append(html[pos:match.start()])
        scan = match.end()
        depth = 1
        found_end = False

        while scan < len(html) and depth > 0:
            no = html.lower().find(open_tag, scan)
            nc = html.lower().find(close_tag, scan)
            if nc == -1:
                break
            if no != -1 and no < nc:
                ch = html[no + len(open_tag):no + len(open_tag) + 1]
                if ch in (' ', '>', '\n', '\t', '\r', '/'):
                    depth += 1
                scan = no + len(open_tag)
            else:
                depth -= 1
                if depth == 0:
                    pos = nc + len(close_tag)
                    found_end = True
                    break
                scan = nc + len(close_tag)

        if not found_end:
            # Malformed / unterminated – stop scanning, keep the remainder.
            result.append(html[match.start():])
            break

    return ''.join(result)

# ----------------------------------------------------------------------
# Fetch article content – only the real article body
# ----------------------------------------------------------------------
def fetch_page_content(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"⚠️ Could not fetch {url}: {e}")
        return "Content unavailable"

    # ---- 1. Isolate the article body ----
    article_html = extract_container_by_class(content, 'section', 'article-page')
    if not article_html:
        # Fallback: try the outer article-subtitle section
        article_html = extract_container_by_class(content, 'section', 'article-section')

    if not article_html:
        print("  ⚠️ Could not find article body container; falling back to page-wide extraction.")
        article_html = content

    # ---- 2. Strip scripts / styles ----
    article_html = re.sub(r'<script.*?</script>', '', article_html, flags=re.DOTALL | re.IGNORECASE)
    article_html = re.sub(r'<style.*?</style>', '', article_html, flags=re.DOTALL | re.IGNORECASE)

    # ---- 3. Remove known non-article elements ----
    article_html = remove_element(article_html, 'output', r'data-cy="author-sign-off"')
    article_html = remove_element(article_html, 'output', r'data-cy="article-video"')
    article_html = remove_element(article_html, 'span',   r'data-cy="poll-view-trigger"')
    article_html = remove_element(article_html, 'div',    r'class="[^"]*catalog-wrapper[^"]*"')
    article_html = remove_element(article_html, 'section', r'data-transform="catalog-item-wrapper"')
    article_html = remove_element(article_html, 'section', r'data-transform="ignvideo"')
    article_html = remove_element(article_html, 'section', r'data-transform="poll"')
    article_html = remove_element(article_html, 'div',    r'data-cy="accent-divider"')
    # Ad / pogo wrappers
    article_html = remove_element(article_html, 'ins', r'class="[^"]*zmgad[^"]*"')
    article_html = remove_element(article_html, 'div', r'data-pogo="[^"]*"')

    # ---- 4. Extract meaningful text in document order ----
    parts = []
    for match in re.finditer(
        r'<(p|h2|h3|h4|li)[^>]*>(.*?)</\1>',
        article_html, re.DOTALL | re.IGNORECASE
    ):
        text = strip_html(match.group(2)).strip()
        if len(text) <= 15:
            continue
        # Filter out common boilerplate that slips through
        if re.search(
            r'(^advertisement$|^skip to content$|^related:|^recommends$|'
            r'read more|sign up for|subscribe to our)',
            text, re.IGNORECASE
        ):
            continue
        parts.append(text)

    if parts:
        return '<br>'.join(parts)

    # ---- 5. Last-ditch fallback ----
    text = strip_html(content)
    text = re.sub(r'\s+', ' ', text).strip()
    sentences = [s.strip() for s in text.split('. ') if len(s) > 40]
    return '<br>'.join(sentences) if sentences else "Content unavailable"

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
# Main
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

        stable_name = get_stable_filename(orig_link)
        remote_image_url = download_thumbnail(orig_link, stable_name)

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
        print('⚠️  REMINDER: commit & push new files under ./notif/ign_tumb/ to GitHub,')
        print('    otherwise the <img src> URLs will 404 on fresh items.')
    except Exception as e:
        print(f'❌ Failed: {e}')

if __name__ == "__main__":
    main()
