import os
import sys
import re
import time
import urllib.request
import urllib.parse
from xml.sax.saxutils import escape
from html.parser import HTMLParser
from html import unescape as html_unescape
from email.utils import formatdate
import datetime

# ----------------------------------------------------------------------
# Proxy (direct-path style)
# ----------------------------------------------------------------------
PROXY_BASE = "https://prox.loserbadbakht.workers.dev"


def proxify(url):
    return f"{PROXY_BASE}/{url}"


def deproxify(url):
    if url.startswith(PROXY_BASE + '/'):
        return url[len(PROXY_BASE) + 1:]
    return url


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
LISTING_URL = "https://game8.co/articles/latest"
MAX_ITEMS = 20

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
    req = urllib.request.Request(proxify(url), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode('utf-8', errors='ignore')


def extract_meta(html, name):
    for p in (
        rf'<meta[^>]*name="{re.escape(name)}"[^>]*content="([^"]*)"',
        rf'<meta[^>]*content="([^"]*)"[^>]*name="{re.escape(name)}"',
        rf'<meta[^>]*property="{re.escape(name)}"[^>]*content="([^"]*)"',
        rf'<meta[^>]*content="([^"]*)"[^>]*property="{re.escape(name)}"',
    ):
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


# ----------------------------------------------------------------------
# Table helpers (NEW)
# ----------------------------------------------------------------------
def clean_cell_content(cell_html):
    """Strip images / anchors / formatting tags from a cell, keep text."""
    cell_html = re.sub(r'<img[^>]*>', '', cell_html, flags=re.IGNORECASE)
    cell_html = re.sub(r'</?a[^>]*>', '', cell_html, flags=re.IGNORECASE)
    cell_html = re.sub(r'<br\s*/?>', '<br>', cell_html, flags=re.IGNORECASE)
    cell_html = re.sub(r'<(?!br>)[^>]+>', '', cell_html, flags=re.IGNORECASE)
    cell_html = html_unescape(cell_html)
    cell_html = re.sub(r'[ \t\r\n]+', ' ', cell_html)
    return cell_html.strip()


def emit_table(table_html):
    """Convert <table>...</table> to a clean HTML table preserving structure."""
    rows_out = []
    for tr_match in re.finditer(
        r'<tr[^>]*>(.*?)</tr>',
        table_html, re.DOTALL | re.IGNORECASE
    ):
        cells = []
        for cell_match in re.finditer(
            r'<(td|th)(?:\s[^>]*)?>(.*?)</\1>',
            tr_match.group(1), re.DOTALL | re.IGNORECASE
        ):
            cell_type = cell_match.group(1).lower()
            content = clean_cell_content(cell_match.group(2))
            if not content:
                content = '&nbsp;'
            cells.append(f'<{cell_type}>{content}</{cell_type}>')
        if cells:
            rows_out.append('<tr>' + ''.join(cells) + '</tr>')
    if not rows_out:
        return ''
    return '<table>' + ''.join(rows_out) + '</table><br><br>'


# ----------------------------------------------------------------------
# Article body -> HTML (tables preserved)
# ----------------------------------------------------------------------
def extract_article_body_html(html):
    m = re.search(
        r'<div[^>]*class="[^"]*p-articleBody[^"]*article-style-wrapper[^"]*"[^>]*>(.*)',
        html, re.DOTALL | re.IGNORECASE
    )
    if not m:
        return ""
    body = m.group(1)

    # Hard cutoff: "You may also like…" and trailing boilerplate
    cm = re.search(r'<h2[^>]*>[^<]*You may also like', body, re.IGNORECASE)
    if cm:
        body = body[:cm.start()]

    for pattern in (
        r'<div[^>]*class="[^"]*p-articleComment',
        r'<div[^>]*class="[^"]*p-articleBottom_share',
        r'<div[^>]*class="[^"]*p-article__author',
        r'<table[^>]*>\s*<tbody>\s*<tr>\s*<td[^>]*width="30%"',
        r'</article>',
    ):
        cm = re.search(pattern, body, re.IGNORECASE)
        if cm:
            body = body[:cm.start()]

    # Find all tables and record their spans (defensive: skip blocks inside)
    table_matches = list(re.finditer(
        r'<table[^>]*>.*?</table>', body, re.DOTALL | re.IGNORECASE
    ))
    table_spans = [(tm.start(), tm.end()) for tm in table_matches]

    def in_table(pos):
        return any(s <= pos < e for s, e in table_spans)

    # Collect tables + blocks as ordered events
    events = [(tm.start(), 'table', tm) for tm in table_matches]
    for em in re.finditer(
        r'<(h2|h3|p|li)(?:\s[^>]*)?>(.*?)</\1>',
        body, re.DOTALL | re.IGNORECASE
    ):
        if in_table(em.start()):
            continue
        events.append((em.start(), 'block', em))
    events.sort(key=lambda x: x[0])

    out = []
    in_list = False

    for _, kind, match in events:
        # --- table ---
        if kind == 'table':
            table_html = emit_table(match.group(0))
            if table_html:
                if in_list:
                    out.append('</ul><br><br>')
                    in_list = False
                out.append(table_html)
            continue

        # --- block ---
        tag = match.group(1).lower()
        inner = match.group(2)

        inner = re.sub(r'<img[^>]*>', '', inner, flags=re.IGNORECASE)
        inner = re.sub(r'</?a[^>]*>', '', inner, flags=re.IGNORECASE)
        inner = re.sub(r'<br\s*/?>', '<br>', inner, flags=re.IGNORECASE)
        inner = re.sub(r'<(?!br>)[^>]+>', '', inner, flags=re.IGNORECASE)
        inner = html_unescape(inner)

        inner = re.sub(r'[ \t]+', ' ', inner)
        inner = re.sub(r'(?:<br>\s*){3,}', '<br><br>', inner)
        inner = inner.strip()
        inner = re.sub(r'^(?:<br>)+', '', inner)
        inner = re.sub(r'(?:<br>)+$', '', inner)

        if not inner:
            continue

        if tag == 'li':
            if not in_list:
                out.append('<ul>')
                in_list = True
            out.append(f'<li>{inner}</li>')
            continue

        if in_list:
            out.append('</ul><br><br>')
            in_list = False

        if tag == 'h2':
            out.append(f'<h2>{inner}</h2><br><br>')
        elif tag == 'h3':
            out.append(f'<h3>{inner}</h3><br><br>')
        else:
            out.append(f'{inner}<br><br>')

    if in_list:
        out.append('</ul>')

    return ''.join(out).strip()


# ----------------------------------------------------------------------
# Listing extraction (unchanged)
# ----------------------------------------------------------------------
def truncate_at(html, pattern):
    m = re.search(pattern, html, re.IGNORECASE)
    return html[:m.start()] if m else html


def extract_main_column(html):
    m = re.search(
        r'<div[^>]*class="[^"]*\bl-2col__main__article\b[^"]*"[^>]*>',
        html, re.IGNORECASE
    )
    if not m:
        return ""
    main = html[m.end():]

    right = re.search(
        r'<div[^>]*class="[^"]*\bl-2col__right\b[^"]*"[^>]*>',
        main, re.IGNORECASE
    )
    if right:
        main = main[:right.start()]

    main = truncate_at(main, r'<div[^>]*class="[^"]*\bp-articleFooter\b')
    main = truncate_at(main, r'<footer[^>]*class="[^"]*l-footer')
    return main


def extract_latest_articles(html):
    main = extract_main_column(html)
    if not main:
        return []

    articles = []
    seen = set()

    for m in re.finditer(
        r'<li[^>]*class="[^"]*\bp-articleListItem\b[^"]*"[^>]*>(.*?)</li>',
        main, re.DOTALL | re.IGNORECASE
    ):
        item = m.group(1)

        title_match = re.search(
            r'<h3[^>]*class="[^"]*\bp-articleListItem__title\b[^"]*"[^>]*>\s*'
            r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            item, re.DOTALL | re.IGNORECASE
        )
        if not title_match:
            continue

        url = deproxify(title_match.group(1).strip())
        title = strip_html(title_match.group(2)).strip()
        title = re.sub(r'\s+', ' ', title)

        if not url.startswith('https://game8.co/'):
            continue
        if url in seen or len(title) < 10:
            continue

        lead_match = re.search(
            r'<p[^>]*class="[^"]*\bp-articleListItem__lead\b[^"]*"[^>]*>(.*?)</p>',
            item, re.DOTALL | re.IGNORECASE
        )
        lead = strip_html(lead_match.group(1)).strip() if lead_match else ""

        seen.add(url)
        articles.append({'url': url, 'title': title, 'lead': lead})

    return articles


# ----------------------------------------------------------------------
# RSS
# ----------------------------------------------------------------------
def cdata(text):
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
        if item.get('pubDate'):
            rss += f"\n    <pubDate>{item['pubDate']}</pubDate>"
        if item.get('content'):
            rss += f"\n    <description>{cdata(item['content'])}</description>"
            rss += f"\n    <content:encoded>{cdata(item['content'])}</content:encoded>"
        rss += "\n</item>"
    rss += '\n</channel>\n</rss>'
    return rss


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    print(f"🔍 Fetching listing: {LISTING_URL}")
    try:
        listing_html = fetch(LISTING_URL)
    except Exception as e:
        print(f"❌ Failed to fetch listing: {e}")
        sys.exit(1)

    print("📋 Extracting latest list (main content only)...")
    articles = extract_latest_articles(listing_html)

    if not articles:
        print("❌ No articles found in the main list.")
        sys.exit(1)

    print(f"📊 Found {len(articles)} articles, fetching up to {MAX_ITEMS}")

    items = []
    limit = min(len(articles), MAX_ITEMS)
    for i, art in enumerate(articles[:MAX_ITEMS], 1):
        print(f"🔄 [{i}/{limit}] {art['title'][:70]}...")
        try:
            article_html = fetch(art['url'])
        except Exception as e:
            print(f"  ⚠️ Fetch failed: {e}")
            continue

        title = extract_title(article_html) or art['title']
        pub_date = extract_published_date(article_html)

        body_html = extract_article_body_html(article_html)
        if not body_html:
            meta_desc = extract_meta(article_html, 'description')
            if meta_desc:
                body_html = escape(meta_desc)
            elif art.get('lead'):
                body_html = escape(art['lead'])

        items.append({
            'title': title,
            'link': art['url'],
            'content': body_html,
            'pubDate': pub_date,
        })

        if i < limit:
            time.sleep(1)

    print(f"✅ Processed {len(items)} items")

    try:
        os.makedirs('./notif', exist_ok=True)
        filename = './notif/game8_feed.xml'
        if os.path.exists(filename):
            os.remove(filename)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(generate_rss(items))
        print('✅ RSS generated.')
        print(f'📁 {filename}')
    except Exception as e:
        print(f'❌ Failed to write: {e}')
        sys.exit(1)


if __name__ == "__main__":
    main()
