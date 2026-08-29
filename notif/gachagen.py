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
# Try to import requests-html for JavaScript rendering.
# If not available, fall back to a simpler approach.
# ----------------------------------------------------------------------
try:
    from requests_html import HTMLSession
    HAS_REQUESTS_HTML = True
except ImportError:
    HAS_REQUESTS_HTML = False
    print("⚠️ requests-html not installed. Install with: pip install requests-html")
    print("⚠️ Falling back to static HTML parsing (may not get all articles).")

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
ARCHIVE_URL = "https://game8.co/games/Genshin-Impact/archives"
MAX_ITEMS = 15  # Number of articles to include

# Global list to hold all processed items
items_data = []

class MLStripper(HTMLParser):
    """Simple HTML stripper to get plain text from HTML content."""
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
    """Strip HTML tags and return plain text."""
    if not html:
        return ""
    s = MLStripper()
    s.feed(html)
    return s.get_data().strip()

def fetch_page_with_js(url):
    """
    Fetch page content using requests-html with JavaScript rendering.
    Falls back to static request if requests-html is not available.
    """
    if HAS_REQUESTS_HTML:
        try:
            session = HTMLSession()
            print(f"🌐 Rendering page with JavaScript: {url}")
            response = session.get(url)
            response.html.render(timeout=20, sleep=2)
            return response.html.html
        except Exception as e:
            print(f"⚠️ JavaScript rendering failed: {e}")
            print("⚠️ Falling back to static request...")
    
    # Fallback: static request
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read().decode('utf-8', errors='ignore')

def fetch_full_page_content(url):
    """
    Fetch and extract the FULL plain text content from a webpage.
    Gets all text without truncation.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read().decode('utf-8', errors='ignore')
            
            # Remove scripts and styles
            content = re.sub(r'<script.*?>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<style.*?>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
            
            # Try to extract article content from paragraphs
            paragraphs = re.findall(r'<p.*?>(.*?)</p>', content, re.DOTALL | re.IGNORECASE)
            
            if paragraphs:
                # Join ALL paragraphs to get full text
                full_text = ' '.join(strip_html(p) for p in paragraphs)
                # Clean up excessive whitespace
                full_text = re.sub(r'\s+', ' ', full_text).strip()
                # Remove common boilerplate
                full_text = re.sub(r'\bGame8\b.*?(?:\n|$)', '', full_text)
                return full_text
            else:
                # Fallback: get all text from the page
                full_text = strip_html(content)
                full_text = re.sub(r'\s+', ' ', full_text).strip()
                return full_text
                
    except Exception as e:
        print(f"⚠️ Could not fetch {url}: {e}")
        return "Content unavailable"

def extract_articles_from_html(html):
    """
    Extract article titles, links, and descriptions from the Game8 archives page.
    The page uses a specific structure with article cards.
    """
    # Try to find article links - Game8 uses a specific pattern
    # Look for <a> tags with href containing "/games/Genshin-Impact/archives/"
    article_pattern = r'<a\s+(?:[^>]*?\s+)?href="(/games/Genshin-Impact/archives/[^"]+)"[^>]*>(.*?)</a>'
    
    # Also try to find article titles in headings
    title_pattern = r'<h[2-3][^>]*>(.*?)</h[2-3]>'
    
    # Find all links that look like article links
    links = re.findall(article_pattern, html, re.DOTALL | re.IGNORECASE)
    
    # Also find all headings which might contain titles
    headings = re.findall(title_pattern, html, re.DOTALL | re.IGNORECASE)
    
    # If we didn't find links with the pattern, try a broader search
    if not links:
        # Look for any link that contains "/archives/" and is likely an article
        all_links = re.findall(r'<a\s+(?:[^>]*?\s+)?href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE)
        links = [(url, text) for url, text in all_links if '/archives/' in url and 'games/Genshin-Impact' in url]
    
    # Also try to find article cards with specific classes
    card_pattern = r'<div[^>]*class="[^"]*article[^"]*"[^>]*>.*?<a\s+href="([^"]+)"[^>]*>(.*?)</a>.*?</div>'
    card_matches = re.findall(card_pattern, html, re.DOTALL | re.IGNORECASE)
    if card_matches:
        links = card_matches
    
    # Remove duplicates while preserving order
    seen = set()
    unique_links = []
    for url, text in links:
        if url not in seen:
            seen.add(url)
            unique_links.append((url, text))
    links = unique_links
    
    # Build full URLs
    base_url = "https://game8.co"
    articles = []
    
    for url, title_text in links:
        # Clean up the title text
        title = strip_html(title_text).strip()
        # Remove extra whitespace
        title = re.sub(r'\s+', ' ', title)
        
        # Skip if title is too short or looks like navigation
        if len(title) < 3 or title.lower() in ['home', 'games', 'search', 'login', 'sign up']:
            continue
            
        full_url = url if url.startswith('http') else base_url + url
        
        # Try to find a description for this article
        # Look for a paragraph or div following the link
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
    """Generate RSS feed with transformed items."""
    # Build the channel header
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Game8 Genshin Impact Guides</title>
<link>{ARCHIVE_URL}</link>
<description>Latest Genshin Impact guides and walkthroughs from Game8</description>
"""
    # Add each item
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
    # Close channel and rss
    rss += '\n</channel>\n</rss>'
    return rss

# ----------------------------------------------------------------------
# Main execution
# ----------------------------------------------------------------------
def main():
    global items_data

    print("🔍 Fetching Game8 Genshin Impact archives...")
    
    # Fetch the page with JavaScript rendering if possible
    html_content = fetch_page_with_js(ARCHIVE_URL)
    
    if not html_content:
        print("❌ Failed to fetch page content.")
        sys.exit(1)
    
    print("📋 Extracting articles from page...")
    articles = extract_articles_from_html(html_content)
    
    if not articles:
        print("⚠️ No articles found. The page structure may have changed.")
        print("⚠️ Trying alternative extraction method...")
        
        # Try to find articles using a simpler pattern
        # Look for any link that looks like an article
        all_links = re.findall(r'<a\s+href="(/games/Genshin-Impact/archives/[^"]+)"[^>]*>([^<]+)</a>', html_content)
        for url, title in all_links:
            if title.strip() and len(title.strip()) > 3:
                full_url = "https://game8.co" + url
                articles.append({
                    'title': title.strip(),
                    'link': full_url,
                    'description': title.strip()
                })
    
    if not articles:
        print("❌ Still no articles found. The page may require JavaScript to load content.")
        print("💡 Try installing requests-html: pip install requests-html")
        print("💡 Or check if the page structure has changed.")
        sys.exit(1)
    
    print(f"📊 Found {len(articles)} articles")
    
    # Process each article (limit to MAX_ITEMS)
    processed = 0
    
    for article in articles:
        if processed >= MAX_ITEMS:
            break
            
        title = article['title']
        link = article['link']
        desc = article.get('description', title)
        
        print(f"🔄 Processing: {title[:50]}...")
        print(f"📡 Fetching full content from: {link[:50]}...")
        
        # Fetch full content from the article page
        full_content = fetch_full_page_content(link)
        
        # If we got a good amount of content, use it; otherwise use the description
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
        
        # Add a small delay to be nice to the servers
        if processed < min(len(articles), MAX_ITEMS):
            time.sleep(1)
    
    print(f"✅ Processed {processed} items")

    # Write to file
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
        print(f'❌ Failed: {e}')

if __name__ == "__main__":
    main()
