import os
import sys
import re
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from html.parser import HTMLParser
from html import unescape as html_unescape
from email.utils import formatdate
import datetime

# ----------------------------------------------------------------------
# Proxy configuration (direct-path style)
# ----------------------------------------------------------------------
PROXY_BASE = "https://prox.loserbadbakht.workers.dev"


def proxify(url):
    return f"{PROXY_BASE}/{url}"


def deproxify(url):
    """Strip our proxy prefix from a URL if present."""
    if url.startswith(PROXY_BASE + '/'):
        return url[len(PROXY_BASE) + 1:]
    return url


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
LISTING_URL = "https://game8.co/articles/latest"
MAX_ITEMS = 15

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}


# ----------------------------------------------------------------------
# HTML helpers
# ----------------------------------------------------------------------
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
    return html_unescape(s.get_data()).strip()


def fetch(url):
    """Fetch URL via the proxy and return decoded HTML."""
    proxied = proxify(url)
    req = urllib.request.Request(proxied, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode('utf-8', errors='ignore')


def extract_meta(html, name):
    patterns = [
        rf'<meta[^>]*name="{re.escape(name)}"[^>]*content="([^"]*)"',
        rf'<meta[^>]*content="([^"]*)"[^>]*name="{re.escape(name)}"',
        rf'<meta[^>]*property="{re.escape(name)}"[^>]*content="([^"]*)"',
        rf'<meta[^>]*content="([^"]*)"[^>]*property="{re.escape(name)}"',
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            return html_unescape(m.group(1))
    return ""


def extract_title(html):
    m = re.search(
        r'<h1[^>]*class="[^"]*p-articleCover__title[^"]*"[^>]*>(.*?)</h1>',
        html, re.DOTALL | re.IGNORECASE
    )
    if m:
        t = strip_html(m.group(1)).strip()
        if t:
            return t

    t = extract_meta(html, 'og:title')
    if t:
        return t.split('｜')[0].strip()

    m = re.search(r'<title>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
    if m:
        return strip_html(m.group(1)).split('｜')[0].strip()
    return ""


def extract_published_date(html):
    """Return RFC-2822 date string or None."""
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if not m:
        return None
    raw = m.group(1)
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d"):
        try:
            dt = datetime.datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return formatdate(dt.timestamp(), usegmt=True)
        except ValueError:
            continue
    return None


def extract_article_body(html):
    """Extract the main article text from a Game8 article page."""
    m = re.search(
        r'<div[^>]*class="[^"]*p-articleBody[^"]*article-style-wrapper[^"]*"[^>]*>(.*)',
        html, re.DOTALL | re.IGNORECASE
    )
    if not m:
        return ""
    body = m.group(1)

    # Cut off trailing boilerplate sections
    for cutoff in (
        r'<h2[^>]*>\s*You may also like\s*</h2>',
        r'<div[^>]*class="[^"]*p-articleComment[^"]*"',
        r'<div[^>]*class="[^"]*p-articleBottom_share[^"]*"',
        r'<div[^>]*class="[^"]*p-article__author[^"]*"',
        r'</article>',
    ):
        cm = re.search(cutoff, body, re.IGNORECASE | re.DOTALL)
        if cm:
            body = body[:cm.start()]

    parts = []
    for elem in re.finditer(
        r'<(h2|h3|p|li)(?:\s[^>]*)?>(.*?)</\1>',
        body, re.DOTALL | re.IGNORECASE
    ):
        tag = elem.group(1).lower()
        text = strip_html(elem.group(2)).strip()
        text = re.sub(r'\s+', ' ', text)
        if not text:
            continue
        if tag == 'h2':
            parts.append(f"\n\n## {text}\n")
        elif tag == 'h3':
            parts.append(f"\n\n### {text}\n")
        elif tag == 'li':
            parts.append(f"\n- {text}")
        else:
            parts.append(f"\n{text}")

    return '\n'.join(parts).strip()


# ----------------------------------------------------------------------
# Listing extraction
# ----------------------------------------------------------------------
# The main body of the article body starts before this heading.
# Anything after should be dropped.
LISTING_PAGES = {
    '/articles/latest', '/articles/featured', '/articles/reviews',
    '/articles/release-dates', '/articles/game-sales', '/articles/games',
}
ARTICLE_PATH_RE = re.compile(
    r'^/articles/(latest|featured|reviews|release-dates|game-sales|games)/[^/]+'
)


def extract_articles_from_listing(html):
    articles = []
    seen = set()

    def maybe_add(url, title_html):
        original_url = deproxify(url)
        path = urllib.parse.urlparse(original_url).path

        if not ARTICLE_PATH_RE.match(path):
            return
        if path.rstrip('/') in LISTING_PAGES:
            return
        if '/articles/author/' in path:
            return

        title = strip_html(title_html).strip()
        title = re.sub(r'\s+', ' ', title)
        title = re.sub(r'[＞>»]+\s*$', '', title).strip()

        if len(title) < 10:
            return
        if original_url in seen:
            return
        seen.add(original_url)
        articles.append({'url': original_url, 'title': title})

    # Pattern A: <div class="p-articleListFootline__title"><a href="URL">TITLE</a>
    for m in re.finditer(
        r'<div[^>]*class="[^"]*p-articleListFootline__title[^"]*"[^>]*>\s*'
        r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html, re.DOTALL | re.IGNORECASE
    ):
        maybe_add(m.group(1), m.group(2))

    # Pattern B: <a href="URL" ...> ... <p class="c-sideArticleList__item_title">TITLE</p>
    for m in re.finditer(
        r'<a[^>]*href="([^"]+)"[^>]*>(?:(?!</a>).)*?'
        r'<p[^>]*class="[^"]*c-sideArticleList__item_title[^"]*"[^>]*>(.*?)</p>',
        html, re.DOTALL | re.IGNORECASE
    ):
        maybe_add(m.group(1), m.group(2))

    # Pattern C: any anchor pointing to an article detail URL
    for m in re.finditer(
        r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html, re.DOTALL | re.IGNORECASE
    ):
        url = m.group(1)
        inner = m.group(2)

        # Skip image-only anchors
        if '<img' in inner.lower() and not re.search(r'>[^<]{10,}<', inner):
            continue
        # Skip giant container anchors
        if len(inner) > 500:
            continue

        maybe_add(url, inner)

    return articles


# ----------------------------------------------------------------------
# RSS generation
# ----------------------------------------------------------------------
def cdata(text):
    """Wrap in CDATA, escaping any nested CDATA terminators."""
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def generate_rss(items):
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<title>Game8 Latest Articles</title>
<link>{LISTING_URL}</link>
<description>Latest gaming news and articles from Game8</description>
"""
    for item in items:
        rss += "\n<item>"
        rss += f"\n    <title>{escape(item['title'])}</title>"
        rss += f"\n    <link>{escape(item['link'])}</link>"
        rss += f"\n    <guid isPermaLink=\"true\">{escape(item['link'])}</guid>"
        if item.get('description'):
            rss += f"\n    <description>{escape(item['description'])}</description>"
        if item.get('pubDate'):
            rss += f"\n    <pubDate>{item['pubDate']}</pubDate>"
        if item.get('content'):
            rss += f"\n    <content:encoded>{cdata(item['content'])}</content:encoded>"
        rss += "\n</item>"
    rss += '\n</channel>\n</rss>'
    return rss


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    print(f"🔍 Fetching listing page: {LISTING_URL}")
    try:
        listing_html = fetch(LISTING_URL)
    except Exception as e:
        print(f"❌ Failed to fetch listing page: {e}")
        sys.exit(1)

    print("📋 Extracting article links...")
    articles = extract_articles_from_listing(listing_html)

    if not articles:
        print("❌ No articles found. The listing markup may have changed.")
        sys.exit(1)

    print(f"📊 Found {len(articles)} articles, fetching up to {MAX_ITEMS}")

    items = []
    for i, art in enumerate(articles[:MAX_ITEMS], 1):
        print(f"🔄 [{i}/{min(len(articles), MAX_ITEMS)}] {art['title'][:70]}...")
        try:
            article_html = fetch(art['url'])
        except Exception as e:
            print(f"  ⚠️ Fetch failed: {e}")
            continue

        title = extract_title(article_html) or art['title']
        description = extract_meta(article_html, 'description') or ""
        pub_date = extract_published_date(article_html)
        body = extract_article_body(article_html)

        items.append({
            'title': title,
            'link': art['url'],
            'description': description,
            'content': body,
            'pubDate': pub_date,
        })

        if i < min(len(articles), MAX_ITEMS):
            time.sleep(1)

    print(f"✅ Processed {len(items)} items")

    try:
        os.makedirs('./notif', exist_ok=True)
        filename = './notif/game8_feed.xml'
        if os.path.exists(filename):
            os.remove(filename)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(generate_rss(items))
        print('✅ Game8 RSS generated successfully.')
        print(f'📁 Output file: {filename}')
    except Exception as e:
        print(f'❌ Failed: {e}')
        sys.exit(1)


if __name__ == "__main__":
    main()
