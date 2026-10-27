 import os
import sys
import re
import time
import hashlib
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

# ----------------------------------------------------------------------
# GitHub raw base for downloaded thumbnails
# ----------------------------------------------------------------------
RAW_BASE = "https://raw.githubusercontent.com/loserbadbakht-wq/sh/refs/heads/main/notif/game8_tumb/"


def proxify(url):
    return f"{PROXY_BASE}/{url}"


def deproxify(url):
    if url.startswith(PROXY_BASE + '/'):
        return url[len(PROXY_BASE) + 1:]
    return url


# ----------------------------------------------------------------------
# Stable filename derived from article URL slug
# ----------------------------------------------------------------------
def get_stable_filename(article_url):
    parsed = urllib.parse.urlparse(article_url)
    slug = parsed.path.rstrip('/').split('/')[-1]
    if not slug:
        slug = hashlib.md5(article_url.encode()).hexdigest()[:16]
    slug = re.sub(r'[\\/*?:"<>|%]', '', slug)
    slug = re.sub(r'[-\s]+', '_', slug)
    slug = slug.strip('_.')
    return slug[:255] or "untitled"


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
# Image download
# ----------------------------------------------------------------------
def extract_image_url(html):
    url = extract_meta(html, 'og:image')
    if not url:
        url = extract_meta(html, 'twitter:image')
    if not url:
        return None
    if url.startswith('data:'):
        return None
    if url.startswith('//'):
        url = 'https:' + url
    return url


def download_thumbnail(article_html, article_url, stable_name):
    tumb_dir = os.path.join('notif', 'game8_tumb')
    os.makedirs(tumb_dir, exist_ok=True)

    image_url = extract_image_url(article_html)
    if not image_url:
        print("  ⚠️ No thumbnail found in article.")
        return None

    m = re.search(r'\.(jpe?g|png|gif|webp)(?:[/?&#]|$)', image_url, re.IGNORECASE)
    ext = '.' + m.group(1).lower() if m else '.jpg'

    local_filename = stable_name + ext
    local_path = os.path.join(tumb_dir, local_filename)

    try:
        print(f"  📥 Downloading thumbnail: {image_url[:80]}...")
        req = urllib.request.Request(image_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            if not data:
                raise ValueError("empty response body")
            with open(local_path, 'wb') as f:
                f.write(data)
        print(f"  ✅ Saved thumbnail: {local_path}")
    except Exception as e:
        print(f"  ⚠️ Failed to download thumbnail: {e}")
        return None

    return RAW_BASE + urllib.parse.quote(local_filename)


# ----------------------------------------------------------------------
# Emoji-bullet conversion
# ----------------------------------------------------------------------
BULLET_CHARS = (
    r'[\u26AB\u26AA\u25CF\u25CB\u25A0\u25A1\u25B2\u25B3\u25BC\u25BD'
    r'\u25C6\u25C7\u2605\u2606\u2022\u25AA\u25AB\u25E6]'
)
BULLET_RE = re.compile(rf'^\s*{BULLET_CHARS}[\uFE0E\uFE0F]?\s*')


def is_bullet_line(text):
    return BULLET_RE.match(text) is not None


def strip_bullet(text):
    return BULLET_RE.sub('', text, count=1).strip()


def convert_emoji_bullets_in_p(inner):
    lines = inner.split('<br>')

    segments = []
    current_type = None
    current_items = []

    def flush():
        nonlocal current_type, current_items
        if current_type is not None and current_items:
            segments.append((current_type, current_items))
        current_type = None
        current_items = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if is_bullet_line(stripped):
            item = strip_bullet(stripped)
            if not item:
                continue
            if current_type == 'list':
                current_items.append(item)
            else:
                flush()
                current_type = 'list'
                current_items = [item]
        else:
            if current_type == 'text':
                current_items.append(stripped)
            else:
                flush()
                current_type = 'text'
                current_items = [stripped]

    flush()

    out = []
    for seg_type, items in segments:
        if seg_type == 'list':
            out.append('<ul>' + ''.join(f'<li>{i}</li>' for i in items) + '</ul>')
        else:
            out.append('<br>'.join(items))

    return '<br>'.join(out)


# ----------------------------------------------------------------------
# Table helpers
# ----------------------------------------------------------------------
def clean_cell_content(cell_html):
    cell_html = re.sub(r'<img[^>]*>', '', cell_html, flags=re.IGNORECASE)
    cell_html = re.sub(r'</?a[^>]*>', '', cell_html, flags=re.IGNORECASE)
    cell_html = re.sub(r'<br\s*/?>', '<br>', cell_html, flags=re.IGNORECASE)
    cell_html = re.sub(r'<(?!br>)[^>]+>', '', cell_html, flags=re.IGNORECASE)
    cell_html = html_unescape(cell_html)
    cell_html = re.sub(r'[ \t\r\n]+', ' ', cell_html)
    return cell_html.strip()


def emit_table(table_html):
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
    return '<table>' + ''.join(rows_out) + '</table><br>'


# ----------------------------------------------------------------------
# Article body -> HTML
# ----------------------------------------------------------------------
def extract_article_body_html(html):
    m = re.search(
        r'<div[^>]*class="[^"]*p-articleBody[^"]*article-style-wrapper[^"]*"[^>]*>(.*)',
        html, re.DOTALL | re.IGNORECASE
    )
    if not m:
        return ""
    body = m.group(1)

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

    table_matches = list(re.finditer(
        r'<table[^>]*>.*?</table>', body, re.DOTALL | re.IGNORECASE
    ))
    table_spans = [(tm.start(), tm.end()) for tm in table_matches]

    def in_table(pos):
        return any(s <= pos < e for s, e in table_spans)

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
        if kind == 'table':
            table_html = emit_table(match.group(0))
            if table_html:
                if in_list:
                    out.append('</ul><br>')
                    in_list = False
                out.append(table_html)
            continue

        tag = match.group(1).lower()
        inner = match.group(2)

        inner = re.sub(r'<img[^>]*>', '', inner, flags=re.IGNORECASE)
        inner = re.sub(r'</?a[^>]*>', '', inner, flags=re.IGNORECASE)
        inner = re.sub(r'<br\s*/?>', '<br>', inner, flags=re.IGNORECASE)
        inner = re.sub(r'<(?!br>)[^>]+>', '', inner, flags=re.IGNORECASE)
        inner = html_unescape(inner)

        inner = re.sub(r'[ \t]+', ' ', inner)
        inner = re.sub(r'(?:<br>\s*){2,}', '<br>', inner)
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
            out.append('</ul><br>')
            in_list = False

        if tag == 'h2':
            out.append(f'<h2>{inner}</h2><br>')
        elif tag == 'h3':
            out.append(f'<h3>{inner}</h3><br>')
        else:  # p
            converted = convert_emoji_bullets_in_p(inner)
            if converted:
                out.append(f'{converted}<br>')

    if in_list:
        out.append('</ul>')

    return ''.join(out).strip()


# ----------------------------------------------------------------------
# Listing extraction
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
# RSS (no content:encoded)
# ----------------------------------------------------------------------
def cdata(text):
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def generate_rss(items):
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
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

        # Download thumbnail and prepend <img>
        stable_name = get_stable_filename(art['url'])
        remote_image_url = download_thumbnail(article_html, art['url'], stable_name)
        if remote_image_url:
            body_html = f'<img src="{remote_image_url}" /><br>{body_html}'

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
        print('⚠️  REMINDER: commit & push new files under ./notif/game8_tumb/ to GitHub,')
        print('    otherwise the <img src> URLs will 404 on fresh items.')
    except Exception as e:
        print(f'❌ Failed to write: {e}')
        sys.exit(1)


if __name__ == "__main__":
    main()
