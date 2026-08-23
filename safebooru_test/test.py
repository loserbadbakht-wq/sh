import requests
import xml.etree.ElementTree as ET
import os

def load_tags_from_folder(folder_path):
    """Load all tags from .txt files inside the given folder, return a set."""
    tags = set()
    if os.path.exists(folder_path) and os.path.isdir(folder_path):
        for filename in os.listdir(folder_path):
            if filename.endswith('.txt'):
                filepath = os.path.join(folder_path, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        tag = line.strip()
                        if tag:
                            tags.add(tag)
    return tags

def load_tags_from_file(filename):
    """Load tags from a single text file, one per line."""
    tags = set()
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                tag = line.strip()
                if tag:
                    tags.add(tag)
    return tags

# Load copyright tags from a single file
COPYRIGHT_TAGS = load_tags_from_file('copyright_tags.txt')

# Load character tags from all .txt files in the 'character_tags' folder
CHARACTER_TAGS = load_tags_from_folder('character_tags')

def get_latest(limit=50):
    """Fetch latest posts containing the 'yuri' tag."""
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
        posts.append({
            'id': post.get('id'),
            'sample_url': post.get('sample_url'),
            'source': post.get('source'),
            'tags': post.get('tags'),
            'rating': post.get('rating'),
            'score': post.get('score'),
            'file_url': post.get('file_url')
        })
    return posts

def generate_rss():
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Safebooru Yuri (Beta Test)- RSS Feed</title>
<link>https://github.com</link>
<description>Latest yuri images from Safebooru with inline previews</description>
"""
    for post in get_latest():
        all_tags = post['tags'].split()
        
        # Separate tags by category
        copyright_tags = [t for t in all_tags if t in COPYRIGHT_TAGS]
        character_tags = [t for t in all_tags if t in CHARACTER_TAGS]
        other_tags = [t for t in all_tags if t not in COPYRIGHT_TAGS and t not in CHARACTER_TAGS]
        
        # Build title from first 3 tags (any tags)
        title = ' '.join(all_tags[:3]) if all_tags else f"Image {post['id']}"
        
        # Build description with categories and image
        copy_str = ' '.join(copyright_tags) if copyright_tags else 'None'
        char_str = ' '.join(character_tags) if character_tags else 'None'
        tags_str = ' '.join(other_tags) if other_tags else 'None'
        
        # Truncate tags if too long
        if len(tags_str) > 1000:
            tags_str = tags_str[:1000] + '...'
        
        desc_text = (f"<b>Copyright:</b> {copy_str}<br/>"
                     f"<b>Character(s):</b> {char_str}<br/>"
                     f"<b>Tags:</b> {tags_str}<br/>"
                     f'<img src="{post["sample_url"]}" />')
        
        # Link: use source if available, otherwise sample_url
        link = post['source'] if post['source'] else post['sample_url']
        
        # Append item with CDATA
        rss += f"""
<item>
    <title>{title}</title>
    <link>{link}</link>
    <description><![CDATA[{desc_text} <br> <a href="{post["file_url"]}">original size</a>]]></description>
</item>"""
    
    rss += '\n</channel>\n</rss>'
    return rss

# Save the RSS file
try:
    os.makedirs('./safebooru_test', exist_ok=True)
    filename = './safebooru_test/safebooru-yuri-rss-test.xml'
    if os.path.exists(filename):
        os.remove(filename)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(generate_rss().strip())
    print('✅ Safebooru yuri RSS generated successfully.')
except Exception as e:
    print(f'❌ Failed: {e}')
