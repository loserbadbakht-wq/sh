import os
import sys
import re
import json
import time
import urllib.parse
from xml.sax.saxutils import escape

# ----------------------------------------------------------------------
# Optional imports – we use what's available
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

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
ARCHIVE_URL = "https://game8.co/games/Genshin-Impact/archives"
MAX_ITEMS = 15
items_data = []

# ----------------------------------------------------------------------
# Helper: strip HTML tags (if BS4 missing, fallback to regex)
# ----------------------------------------------------------------------
def strip_html(html):
    if not html:
        return ""
    if HAS_BS4:
        return BeautifulSoup(html, "html.parser").get_text(separator=" ").strip()
    else:
        return re.sub(r'<[^>]+>', ' ', html).strip()

# ----------------------------------------------------------------------
# Fetch page with cloudscraper (bypasses Cloudflare)
# ----------------------------------------------------------------------
def fetch_page(url):
    if not HAS_CLOUDSCRAPER:
        print("❌ cloudscraper required.")
        return None
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Fetch failed: {e}")
        return None

# ----------------------------------------------------------------------
# Extract articles from JSON inside <script> tags
# ----------------------------------------------------------------------
def extract_from_json(html):
    """Search for JSON‑LD or custom script data containing article list."""
    # Common patterns: <script type="application/ld+json"> ... </script>
    # or a script containing "articleList" or similar.
    script_pattern = r'<script[^>]*>(.*?)</script>'
    scripts = re.findall(script_pattern, html, re.DOTALL | re.IGNORECASE)
    for script in scripts:
        # Try to parse as JSON
        try:
            data = json.loads(script)
            # Recursively search for article URLs/titles in the JSON
            articles = []
            def find_articles(obj, path=""):
                if isinstance(obj, dict):
                    # Look for keys that might contain article info
                    if 'url' in obj and 'name' in obj:
                        url = obj.get('url')
                        name = obj.get('name')
                        if url and name and '/archives/' in url:
                            articles.append((url, name))
                    for k, v in obj.items():
                        find_articles(v, path + "." + k)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        find_articles(item, path + f"[{i}]")
            find_articles(data)
            if articles:
                return articles
        except json.JSONDecodeError:
            continue
    return None

# ----------------------------------------------------------------------
# Extract articles using BeautifulSoup (fallback)
# ----------------------------------------------------------------------
def extract_from_html(html):
    if not HAS_BS4:
        return []
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen = set()
    # Find all links that point to archives
    for a in soup.find_all('a', href=re.compile(r'/games/Genshin-Impact/archives/')):
        href = a.get('href')
        if not href or href in seen:
            continue
        seen.add(href)
        title = a.get_text(strip=True)
        if not title or len(title) < 3:
            # maybe the title is inside a heading within the <a>
            parent = a.parent
            if parent and parent.name in ['h2', 'h3', 'h4']:
                title = parent.get_text(strip=True)
            else:
                continue
        title = re.sub(r'\s+', ' ', title).strip()
        if title.lower() in ['home', 'games', 'search', 'login']:
            continue
        full_url = href if href.startswith('http') else "https://game8.co" + href
        # Try to get a description snippet
        description = title
        next_p = a.find_next('p')
        if next_p:
            desc = next_p.get_text(strip=True)
            if len(desc) > 20:
                description = desc
        articles.append({
            'title': title,
            'link': full_url,
            'description': description
        })
    return articles

# ----------------------------------------------------------------------
# Fetch full article content
# ----------------------------------------------------------------------
def fetch_full_article_content(url):
    html = fetch_page(url)
    if not html:
        return "Content unavailable"
    # Use BeautifulSoup to extract paragraphs
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        # Try to find the main content container
        main = soup.find('div', class_=re.compile(r'article-body|post-content|entry-content|content'))
        if main:
            paragraphs = main.find_all('p')
        else:
            paragraphs = soup.find_all('p')
        if paragraphs:
            text = ' '.join(p.get_text(separator=" ").strip() for p in paragraphs)
            text = re.sub(r'\s+', ' ', text).strip()
            text = re.sub(r'\bGame8\b.*?(?:\n|$)', '', text)
            return text
    # Fallback to regex
    html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    paragraphs = re.findall(r'<p.*?>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if paragraphs:
        full_text = ' '.join(strip_html(p) for p in paragraphs)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        return full_text
    return strip_html(html)

# ----------------------------------------------------------------------
# Generate RSS
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
    html = fetch_page(ARCHIVE_URL)
    if not html:
        print("❌ Failed to fetch page. Exiting.")
        sys.exit(1)

    # Debug: print first 500 characters to see what we got
    print(f"📄 Fetched {len(html)} bytes. Snippet:\n{html[:500]}\n")

    # 1. Try to extract from JSON in scripts
    articles_json = extract_from_json(html)
    if articles_json:
        print(f"✅ Found {len(articles_json)} articles from JSON.")
        articles = [{'title': title, 'link': url, 'description': title} for url, title in articles_json]
    else:
        # 2. Fallback to HTML parsing
        print("⚠️ No JSON articles found. Trying HTML parsing...")
        articles = extract_from_html(html)
        if articles:
            print(f"✅ Found {len(articles)} articles from HTML.")
        else:
            print("❌ No articles found at all.")
            # Save a snippet for debugging
            with open('debug.html', 'w', encoding='utf-8') as f:
                f.write(html)
            print("💾 Saved full HTML as debug.html for inspection.")
            sys.exit(1)

    # Limit and process articles
    print(f"📊 Processing up to {MAX_ITEMS} articles...")
    processed = 0
    for article in articles:
        if processed >= MAX_ITEMS:
            break
        title = article['title']
        link = article['link']
        print(f"🔄 Processing: {title[:50]}...")
        print(f"📡 Fetching full content from: {link[:50]}...")
        full_content = fetch_full_article_content(link)
        if len(full_content.split()) < 20:
            full_content = article.get('description', title)
        items_data.append({
            'title': title,
            'link': link,
            'description': full_content
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
