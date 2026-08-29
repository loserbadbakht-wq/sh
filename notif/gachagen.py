import os
import sys
import re
import time
import json
import urllib.parse
from xml.sax.saxutils import escape

# ----------------------------------------------------------------------
# Ensure we have the necessary libraries
# ----------------------------------------------------------------------
try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False
    print("⚠️ cloudscraper not installed. Install with: pip install cloudscraper")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("⚠️ BeautifulSoup not installed. Install with: pip install beautifulsoup4")

try:
    from requests_html import HTMLSession
    HAS_REQUESTS_HTML = True
except ImportError:
    HAS_REQUESTS_HTML = False
    print("⚠️ requests-html not installed. Install with: pip install requests-html")

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
ARCHIVE_URL = "https://game8.co/games/Genshin-Impact/archives"
MAX_ITEMS = 15
items_data = []

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def strip_html(html):
    if not html:
        return ""
    # quick and dirty: remove tags, but we'll use BeautifulSoup if available
    if HAS_BS4:
        return BeautifulSoup(html, "html.parser").get_text(separator=" ").strip()
    else:
        # fallback regex
        return re.sub(r'<[^>]+>', ' ', html).strip()

def fetch_page_static(url):
    """Fetch HTML using cloudscraper (bypasses Cloudflare)."""
    if not HAS_CLOUDSCRAPER:
        return None
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Static fetch failed: {e}")
        return None

def fetch_page_with_js(url):
    """Fetch HTML using requests-html with JavaScript rendering."""
    if not HAS_REQUESTS_HTML:
        return None
    try:
        session = HTMLSession()
        response = session.get(url)
        # Render with a timeout; headless browser may take a few seconds
        response.html.render(timeout=30, sleep=2, keep_page=True)
        return response.html.html
    except Exception as e:
        print(f"❌ JS rendering failed: {e}")
        return None

def fetch_full_page_content(url):
    """Fetch full article text from its URL."""
    html = fetch_page_static(url)
    if not html:
        return "Content unavailable"

    # Use BeautifulSoup if available to extract <p> tags
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        # Try to get article content: find main content container (common patterns)
        # Look for div with class 'article-body', 'post-content', etc.
        content_div = soup.find('div', class_=re.compile(r'article-body|post-content|entry-content|content'))
        if content_div:
            paragraphs = content_div.find_all('p')
        else:
            paragraphs = soup.find_all('p')
        if paragraphs:
            text = ' '.join(p.get_text(separator=" ").strip() for p in paragraphs)
            text = re.sub(r'\s+', ' ', text).strip()
            # Remove common boilerplate
            text = re.sub(r'\bGame8\b.*?(?:\n|$)', '', text)
            return text

    # Fallback: regex extraction
    html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    paragraphs = re.findall(r'<p.*?>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if paragraphs:
        full_text = ' '.join(strip_html(p) for p in paragraphs)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        return full_text
    else:
        full_text = strip_html(html)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        return full_text

# ----------------------------------------------------------------------
# Article extraction
# ----------------------------------------------------------------------
def extract_articles_from_html(html):
    """Extract article links, titles, and descriptions using BeautifulSoup."""
    if not HAS_BS4:
        print("❌ BeautifulSoup required for extraction.")
        return []
    soup = BeautifulSoup(html, "html.parser")
    
    # Find all links that point to article archives
    # Typically: <a href="/games/Genshin-Impact/archives/...">
    links = soup.find_all('a', href=re.compile(r'/games/Genshin-Impact/archives/'))
    
    articles = []
    seen = set()
    for a in links:
        href = a.get('href')
        if not href:
            continue
        # Skip if it's a fragment or navigation
        if href in seen or href.startswith('#') or href.startswith('javascript:'):
            continue
        seen.add(href)
        
        # Get title text
        title_text = a.get_text(strip=True)
        if not title_text or len(title_text) < 3:
            # Maybe the title is inside a heading element within the link?
            parent = a.parent
            if parent and parent.name in ['h2', 'h3', 'h4']:
                title_text = parent.get_text(strip=True)
            elif a.find('h2') or a.find('h3'):
                title_text = a.get_text(strip=True)
            else:
                continue
        
        # Clean title
        title = re.sub(r'\s+', ' ', title_text).strip()
        if title.lower() in ['home', 'games', 'search', 'login', 'sign up', 'archives']:
            continue
        
        # Build full URL
        full_url = href if href.startswith('http') else "https://game8.co" + href
        
        # Try to find a description snippet (e.g., a following paragraph)
        description = title
        # Find next sibling or parent's next sibling that is a p
        next_p = a.find_next('p')
        if next_p:
            desc_text = next_p.get_text(strip=True)
            if len(desc_text) > 20:
                description = desc_text
        
        articles.append({
            'title': title,
            'link': full_url,
            'description': description
        })
    
    return articles

# ----------------------------------------------------------------------
# RSS generation
# ----------------------------------------------------------------------
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

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    global items_data

    print("🔍 Fetching Game8 Genshin Impact archives...")

    # 1. Try static fetch first (fast, may work if no JS needed)
    html = fetch_page_static(ARCHIVE_URL)
    if html:
        articles = extract_articles_from_html(html)
        if articles:
            print(f"✅ Found {len(articles)} articles using static fetch.")
        else:
            print("⚠️ Static fetch returned no articles. Trying JS rendering...")
            # 2. Try JS rendering
            html_js = fetch_page_with_js(ARCHIVE_URL)
            if html_js:
                articles = extract_articles_from_html(html_js)
                if articles:
                    print(f"✅ Found {len(articles)} articles using JS rendering.")
                else:
                    print("❌ JS rendering also found no articles.")
                    # dump snippet for debugging
                    snippet = html_js[:500] if html_js else ""
                    print(f"📄 HTML snippet: {snippet}")
                    sys.exit(1)
            else:
                print("❌ JS rendering failed.")
                sys.exit(1)
    else:
        print("❌ Static fetch failed. Trying JS rendering...")
        html_js = fetch_page_with_js(ARCHIVE_URL)
        if html_js:
            articles = extract_articles_from_html(html_js)
            if articles:
                print(f"✅ Found {len(articles)} articles using JS rendering.")
            else:
                print("❌ JS rendering found no articles.")
                snippet = html_js[:500] if html_js else ""
                print(f"📄 HTML snippet: {snippet}")
                sys.exit(1)
        else:
            print("❌ All fetch attempts failed. Exiting.")
            sys.exit(1)

    if not articles:
        print("❌ No articles extracted. Exiting.")
        sys.exit(1)

    print(f"📊 Processing up to {MAX_ITEMS} articles...")
    processed = 0
    for article in articles:
        if processed >= MAX_ITEMS:
            break
        title = article['title']
        link = article['link']
        print(f"🔄 Processing: {title[:50]}...")
        print(f"📡 Fetching full content from: {link[:50]}...")
        full_content = fetch_full_page_content(link)
        if len(full_content.split()) > 20:
            content_to_use = full_content
        else:
            content_to_use = article['description']
        items_data.append({
            'title': title,
            'link': link,
            'description': content_to_use
        })
        processed += 1
        if processed < min(len(articles), MAX_ITEMS):
            time.sleep(1)

    print(f"✅ Processed {processed} items")

    # Write RSS file
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
