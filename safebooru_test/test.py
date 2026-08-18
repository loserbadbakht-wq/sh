import requests
import xml.etree.ElementTree as ET
import os
from datetime import datetime, timezone
import re

MAX_ITEMS = 500  # maximum number of entries in the feed

def get_latest(limit=10):
    """Fetch latest posts containing 'yuri' but NOT 'ai-generated'."""
    url = 'https://safebooru.org/index.php?page=dapi&s=post&q=index'
    params = {
        'limit': limit,
        'pid': 0,
        'tags': 'yuri -ai-generated'
    }
    response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})
    root = ET.fromstring(response.content)
    
    posts = []
    for post in root.findall('post'):
        # Convert Unix timestamp to RFC 822 date string
        created_ts = int(post.get('created_at', 0))
        pub_date = datetime.fromtimestamp(created_ts, tz=timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')
        posts.append({
            'id': post.get('id'),
            'sample_url': post.get('sample_url'),
            'source': post.get('source'),
            'tags': post.get('tags'),
            'rating': post.get('rating'),
            'score': post.get('score'),
            'file_url': post.get('file_url'),
            'pub_date': pub_date
        })
    return posts

def generate_rss():
    # Prepare base XML structure
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'Safebooru Yuri - RSS Feed'
    ET.SubElement(channel, 'link').text = 'https://github.com'
    ET.SubElement(channel, 'description').text = 'Latest yuri images from Safebooru (test)'
    
    existing_items = []
    existing_links = set()
    
    # Try to load existing RSS file
    filename = './safebooru_test/safebooru-yuri-rss-test.xml'
    if os.path.exists(filename):
        try:
            tree = ET.parse(filename)
            root = tree.getroot()
            old_channel = root.find('channel')
            if old_channel is not None:
                # Extract all existing items and their links
                for item in old_channel.findall('item'):
                    link_elem = item.find('link')
                    if link_elem is not None:
                        existing_links.add(link_elem.text)
                    existing_items.append(item)
        except Exception as e:
            print(f'Warning: Could not parse existing RSS: {e}')
            existing_items = []
            existing_links = set()
    
    # Fetch new posts
    new_posts = get_latest()
    
    # Build new items for posts not already in feed
    new_items = []
    for post in new_posts:
        link = post['source'] if post['source'] else post['sample_url']
        if link in existing_links:
            continue  # already have this post
        # Create new item
        item = ET.Element('item')
        title = ' '.join(post['tags'].split()[:3]) if post['tags'] else f"Image {post['id']}"
        ET.SubElement(item, 'title').text = title
        ET.SubElement(item, 'link').text = link
        ET.SubElement(item, 'guid', isPermaLink='false').text = post['id']
        ET.SubElement(item, 'pubDate').text = post['pub_date']
        # Description with tags and image
        desc_tags = post['tags'][:1000] + ('...' if len(post['tags']) > 1000 else '')
        desc_text = (f"Tags: {desc_tags}<br/>"
                     f'<img src="{post["sample_url"]}" /><br/>'
                     f'<a href="{post["file_url"]}">original size</a>')
        desc = ET.SubElement(item, 'description')
        desc.text = desc_text
        # We'll wrap CDATA later, but we can store raw text
        # We'll handle CDATA when writing
        new_items.append(item)
    
    # Combine: new items first (newest), then existing
    all_items = new_items + existing_items
    
    # Truncate to MAX_ITEMS
    if len(all_items) > MAX_ITEMS:
        all_items = all_items[:MAX_ITEMS]
    
    # Add all items to channel
    for item in all_items:
        channel.append(item)
    
    # Create XML tree and write with CDATA for description
    # We need to manually handle CDATA because ElementTree doesn't support it directly.
    # We'll generate XML string and replace description content with CDATA.
    rough_string = ET.tostring(rss, encoding='utf-8').decode('utf-8')
    # Use regex to wrap description content in CDATA
    # Find all <description> tags and replace their content with <![CDATA[...]]>
    # We'll do a simple replace: find <description> and the content until </description>
    # But careful: description content may contain HTML, we want to keep it as is.
    # Since we set desc.text as raw HTML, it will be escaped by ET.tostring.
    # To avoid escaping, we need to use CDATA. We'll manually insert CDATA after generation.
    # Simpler: we can write the file ourselves using string formatting.
    # Given complexity, we'll build the XML manually or use a library that supports CDATA.
    # For simplicity, we'll use a custom write function.
    # But to keep the code simple, we'll write the RSS using string concatenation.
    # However, we already have the tree. Let's use a method: after generating the string, replace description content.
    # We'll use a regular expression to find description tag and replace its content.
    # But description may contain newlines and special chars.
    # Alternative: we can store the description as a raw string and then use a custom serializer.
    # Since the user already had a working string-based RSS generation, we can adapt that approach.
    # Let's revert to string-based generation but with deduplication logic.
    # That might be simpler.

    # I'll rewrite using the original string-based method but with deduplication and persistence.
    # This avoids CDATA issues.
    # I'll implement the following:
    # 1. Read existing RSS file content, parse to get links and keep the whole string.
    # 2. Fetch new posts.
    # 3. For each new post, create a new <item> string.
    # 4. Prepend new items to the existing content (between <channel> and </channel>).
    # 5. Truncate to max items (by removing oldest from the end).
    # This is simpler and preserves CDATA.

    # But to keep the code clean, I'll provide the string-based version.
    # I'll now implement that.

# Let's start over with string-based approach for simplicity.

def generate_rss_string():
    filename = './safebooru_test/safebooru-yuri-rss-test.xml'
    existing_items = []
    existing_links = set()
    
    # Try to read existing file
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        # Extract items using regex or parse with ET. We'll use ET to extract links.
        try:
            root = ET.fromstring(content)
            channel = root.find('channel')
            if channel is not None:
                for item in channel.findall('item'):
                    link_elem = item.find('link')
                    if link_elem is not None:
                        existing_links.add(link_elem.text)
                    # Keep the entire item as a string? We'll reconstruct later.
                    # For now, we'll store the item's XML string.
                    # We can use ET.tostring(item, encoding='unicode') to get the string.
                    existing_items.append(ET.tostring(item, encoding='unicode'))
        except Exception as e:
            print(f'Warning: Could not parse existing RSS, will overwrite: {e}')
            existing_items = []
            existing_links = set()
    
    # Fetch new posts
    new_posts = get_latest()
    
    # Build new item strings for posts not already present
    new_item_strings = []
    for post in new_posts:
        link = post['source'] if post['source'] else post['sample_url']
        if link in existing_links:
            continue
        title = ' '.join(post['tags'].split()[:3]) if post['tags'] else f"Image {post['id']}"
        desc_tags = post['tags'][:1000] + ('...' if len(post['tags']) > 1000 else '')
        desc_text = (f"Tags: {desc_tags}<br/>"
                     f'<img src="{post["sample_url"]}" /><br/>'
                     f'<a href="{post["file_url"]}">original size</a>')
        
        # Build item XML with CDATA for description
        item_str = f"""
<item>
    <title>{title}</title>
    <link>{link}</link>
    <guid isPermaLink="false">{post['id']}</guid>
    <pubDate>{post['pub_date']}</pubDate>
    <description><![CDATA[{desc_text}]]></description>
</item>"""
        new_item_strings.append(item_str)
    
    # Combine: new items first, then existing
    all_items = new_item_strings + existing_items
    
    # Truncate to MAX_ITEMS
    if len(all_items) > MAX_ITEMS:
        all_items = all_items[:MAX_ITEMS]
    
    # Build the full RSS XML
    rss_header = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Safebooru Yuri - RSS Feed</title>
<link>https://github.com</link>
<description>Latest yuri images from Safebooru (test)</description>
"""
    rss_footer = """
</channel>
</rss>"""
    
    # Join items
    items_xml = '\n'.join(all_items)
    full_rss = rss_header + items_xml + rss_footer
    return full_rss

# Save the RSS file
try:
    os.makedirs('./safebooru_test', exist_ok=True)
    filename = './safebooru_test/safebooru-yuri-rss-test.xml'
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(generate_rss_string().strip())
    print('✅ Safebooru yuri RSS generated successfully (test).')
except Exception as e:
    print(f'❌ Failed: {e}')
