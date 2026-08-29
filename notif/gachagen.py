import os
import sys
import re
import time
import urllib.parse
from xml.sax.saxutils import escape
from html.parser import HTMLParser

# ----------------------------------------------------------------------
# Try to import cloudscraper (bypass Cloudflare), else use requests
# ----------------------------------------------------------------------
try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False
    print("⚠️ cloudscraper not installed. Install with: pip install cloudscraper")
    print("⚠️ Falling back to standard requests (may be blocked).")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("❌ requests not installed. Install with: pip install requests")
    sys.exit(1)

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
ARCHIVE_URL = "https://game8.co/games/Genshin-Impact/archives"
MAX_ITEMS = 15  # Number of articles to include

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

def fetch_page(url):
    """
    Fetch page content using cloudscraper if available, else requests with robust headers.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0',
    }

    try:
        if HAS_CLOUDSCRAPER:
            scraper = cloudscraper.create_scraper()
            response = scraper.get(url, headers=headers, timeout=30)
        else:
            session = requests.Session()
            session.headers.update(headers)
            response = session.get(url, timeout=30)

        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Failed to fetch {url}: {e}")
        return None

def fetch_full_page_content(url):
    """Fetch full article content from a given URL."""
    html = fetch_page(url)
    if not html:
        return "Content unavailable"

    # Remove scripts and styles
    html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Extract paragraphs
    paragraphs = re.findall(r'<p.*?>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if paragraphs:
        full_text = ' '.join(strip_html(p) for p in paragraphs)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        full_text = re.sub(r'\bGame8\b.*?(?:\n|$)', '', full_text)
        return full_text
    else:
        # Fallback: all text
        full_text = strip_html(html)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        return full_text

def extract_articles_from_html(html):
    """Extract article links, titles, and descriptions from the archives page."""
    # Look for links containing "/games/Genshin-Impact/archives/"
    article_pattern = r'<a\s+(?:[^>]*?\s+)?href="(/games/Genshin-Impact/archives/[^"]+)"[^>]*>(.*?)</a>'
    links = re.findall(article_pattern, html, re.DOTALL | re.IGNORECASE)

    # Also try to find article cards with specific classes
    card_pattern = r'<div[^>]*class="[^"]*article[^"]*"[^>]*>.*?<a\s+href="([^"]+)"[^>]*>(.*?)</a>.*?</div>'
    card_matches = re.findall(card_pattern, html, re.DOTALL | re.IGNORECASE)
    if card_matches:
        links = card_matches

    # Remove duplicates
    seen = set()
    unique_links = []
    for url, text in links:
        if url not in seen:
            seen.add(url)
            unique_links.append((url, text))
    links = unique_links

    base_url = "https://game8.co"
    articles = []

    for url, title_text in links:
        title = strip_html(title_text).strip()
        title = re.sub(r'\s+', ' ', title)
        if len(title) < 3 or title.lower() in ['home', 'games', 'search', 'login', 'sign up']:
            continue

        full_url = url if url.startswith('http') else base_url + url

        # Try to get a description (snippet) from the page
        desc_pattern = f'<a[^>]*href="{re.escape(url)}"[^>]*>.*?</a>\\s*(?:<[^>]+>)*\\s*([^<]+)'
        desc_matches = re.findall(desc_pattern, html, re.DOTALL | re.IGNORECASE)
        description = desc_matches[0].strip() if desc_matches else title

        articles.append({
            'title': title,
            'link': full_url,
            'description': strip_html(description)
        })

    return articles

def generate_rss():
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Game8 Genshin Impact Guides</title>
<link>{ARCHIVE_URL}</link>
<description>Latest Genshin Impact guides and walkthroughs from Game8</description>
"""
    for item in items_data:
        safe_title = escape(item['title'])
        safe_link = escape(item['link'])
        safe_description = escape(item['description'])
        rss += f"""
<item>
    <title>{safe_title}</title>
    <link>{safe_link}</link>
    <description>{safe_description}</description>
</item>"""
    rss += '\n</channel>\n</rss>'
    return rss

def main():
    global items_data

    print("🔍 Fetching Game8 Genshin Impact archives...")
    html = fetch_page(ARCHIVE_URL)
    if not html:
        print("❌ Failed to fetch page content. Exiting.")
        sys.exit(1)

    print("📋 Extracting articles from page...")
    articles = extract_articles_from_html(html)

    if not articles:
        # Fallback: look for any link with "/archives/" 
        all_links = re.findall(r'<a\s+href="(/games/Genshin-Impact/archives/[^"]+)"[^>]*>([^<]+)</a>', html)
        for url, title in all_links:
            if title.strip() and len(title.strip()) > 3:
                full_url = "https://game8.co" + url
                articles.append({
                    'title': title.strip(),
                    'link': full_url,
                    'description': title.strip()
                })

    if not articles:
        print("❌ No articles found. The page structure may have changed.")
        print("💡 Try installing cloudscraper: pip install cloudscraper")
        print("💡 Or check if the page requires JavaScript – consider using requests-html with a headless browser.")
        sys.exit(1)

    print(f"📊 Found {len(articles)} articles")

    processed = 0
    for article in articles:
        if processed >= MAX_ITEMS:
            break

        title = article['title']
        link = article['link']
        desc = article.get('description', title)

        print(f"🔄 Processing: {title[:50]}...")
        print(f"📡 Fetching full content from: {link[:50]}...")

        full_content = fetch_full_page_content(link)
        if len(full_content.split()) > 20:
            content_to_use = full_content
        else:
            content_to_use = desc

        items_data.append({
            'title': title,
            'link': link,
            'description': content_to_use
        })
        processed += 1

        if processed < min(len(articles), MAX_ITEMS):
            time.sleep(1)

    print(f"✅ Processed {processed} items")

    try:
        os.makedirs('./notif', exist_ok=True)
        filename = './notif/game8_feed.xml'
        if os.path.exists(filename):
            os.remove(filename)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(generate_rss().strip())
        print('✅ Game8 RSS generated successfully.')
        print(f'📁 Output file: {filename}')
    except Exception as e:
        print(f'❌ Failed to write file: {e}')

if __name__ == "__main__":
    main()
