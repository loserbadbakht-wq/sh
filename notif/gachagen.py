import os
import sys
import re
import time
import json
import urllib.parse
from xml.sax.saxutils import escape

# ----------------------------------------------------------------------
# Use undetected-chromedriver if available, else fallback to selenium
# ----------------------------------------------------------------------
try:
    import undetected_chromedriver as uc
    HAS_UNDETECTED = True
except ImportError:
    HAS_UNDETECTED = False
    print("⚠️ undetected-chromedriver not installed. Install with: pip install undetected-chromedriver")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("⚠️ BeautifulSoup not installed. Install with: pip install beautifulsoup4")

try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
ARCHIVE_URL = "https://game8.co/games/Genshin-Impact/archives"
MAX_ITEMS = 15
items_data = []

# Optional proxy (set to None if not used)
PROXY = None  # e.g., "http://user:pass@ip:port" or "socks5://..."

def strip_html(html):
    if not html:
        return ""
    if HAS_BS4:
        return BeautifulSoup(html, "html.parser").get_text(separator=" ").strip()
    else:
        return re.sub(r'<[^>]+>', ' ', html).strip()

# ----------------------------------------------------------------------
# Fetch with undetected-chromedriver (supports proxies)
# ----------------------------------------------------------------------
def fetch_page_undetected(url):
    if not HAS_UNDETECTED:
        return None
    try:
        options = uc.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        if PROXY:
            options.add_argument(f'--proxy-server={PROXY}')
        driver = uc.Chrome(options=options)
        driver.get(url)
        time.sleep(5)
        html = driver.page_source
        driver.quit()
        return html
    except Exception as e:
        print(f"❌ Undetected fetch failed: {e}")
        return None

# ----------------------------------------------------------------------
# Fallback: cloudscraper (if no proxy, likely fails)
# ----------------------------------------------------------------------
def fetch_page_static(url):
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
        if PROXY:
            scraper.proxies = {'http': PROXY, 'https': PROXY}
        response = scraper.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Static fetch failed: {e}")
        return None

# ----------------------------------------------------------------------
# Article extraction (unchanged)
# ----------------------------------------------------------------------
def extract_from_json(html):
    script_pattern = r'<script[^>]*>(.*?)</script>'
    scripts = re.findall(script_pattern, html, re.DOTALL | re.IGNORECASE)
    for script in scripts:
        try:
            data = json.loads(script)
            articles = []
            def find_articles(obj, path=""):
                if isinstance(obj, dict):
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

def extract_from_html(html):
    if not HAS_BS4:
        return []
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    seen = set()
    for a in soup.find_all('a', href=re.compile(r'/games/Genshin-Impact/archives/')):
        href = a.get('href')
        if not href or href in seen:
            continue
        seen.add(href)
        title = a.get_text(strip=True)
        if not title or len(title) < 3:
            parent = a.parent
            if parent and parent.name in ['h2', 'h3', 'h4']:
                title = parent.get_text(strip=True)
            else:
                continue
        title = re.sub(r'\s+', ' ', title).strip()
        if title.lower() in ['home', 'games', 'search', 'login']:
            continue
        full_url = href if href.startswith('http') else "https://game8.co" + href
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

def fetch_full_article_content(url):
    html = fetch_page_undetected(url) or fetch_page_static(url)
    if not html:
        return "Content unavailable"
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
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
    html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    paragraphs = re.findall(r'<p.*?>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if paragraphs:
        full_text = ' '.join(strip_html(p) for p in paragraphs)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        return full_text
    return strip_html(html)

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
    
    html = fetch_page_undetected(ARCHIVE_URL) or fetch_page_static(ARCHIVE_URL)
    if not html:
        print("❌ All fetch attempts failed. Exiting.")
        sys.exit(1)

    print(f"📄 Fetched {len(html)} bytes. Snippet:\n{html[:300]}\n")

    articles_json = extract_from_json(html)
    if articles_json:
        print(f"✅ Found {len(articles_json)} articles from JSON.")
        articles = [{'title': title, 'link': url, 'description': title} for url, title in articles_json]
    else:
        print("⚠️ No JSON articles found. Trying HTML parsing...")
        articles = extract_from_html(html)
        if articles:
            print(f"✅ Found {len(articles)} articles from HTML.")
        else:
            print("❌ No articles found. Saving debug.html for inspection.")
            with open('debug.html', 'w', encoding='utf-8') as f:
                f.write(html)
            sys.exit(1)

    print(f"📊 Processing up to {MAX_ITEMS} articles...")
    processed = 0
    for article in articles:
        if processed >= MAX_ITEMS:
            break
        title = article['title']
        link = article['link']
        print(f"🔄 Processing: {title[:50]}...")
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
