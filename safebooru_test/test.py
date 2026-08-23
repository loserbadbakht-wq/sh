import requests
import xml.etree.ElementTree as ET
import os

# ---- Import tag lists from the config file ----
from tags_config import COPYRIGHT_TAGS, CHARACTER_TAGS

def get_latest(limit=50):
    url = 'https://safebooru.org/index.php?page=dapi&s=post&q=index'
    params = {'limit': limit, 'pid': 0, 'tags': 'yuri -ai-generated'}
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
<title>Safebooru Yuri (beta test) - RSS Feed</title>
<link>https://github.com</link>
<description>Latest yuri images with separated tags</description>
"""
    for post in get_latest():
        all_tags = post['tags'].split()
        
        copyright_tags = [t for t in all_tags if t in COPYRIGHT_TAGS]
        character_tags = [t for t in all_tags if t in CHARACTER_TAGS]
        other_tags = [t for t in all_tags if t not in COPYRIGHT_TAGS and t not in CHARACTER_TAGS]
        
        copy_str = ' '.join(copyright_tags) if copyright_tags else 'Can not guees'
        char_str = ' '.join(character_tags) if character_tags else 'Can not guess'
        tags_str = ' '.join(other_tags) if other_tags else 'None'
        if len(tags_str) > 1000:
            tags_str = tags_str[:1000] + '...'
        
        title = ' '.join(all_tags[:3]) if all_tags else f"Image {post['id']}"
        desc_text = (f"<b>Copyright:</b> {copy_str}<br/>"
                     f"<b>Character(s):</b> {char_str}<br/>"
                     f"<b>Tags:</b> {tags_str}<br/>"
                     f'<img src="{post["sample_url"]}" />')
        link = post['source'] if post['source'] else post['sample_url']
        
        rss += f"""
<item>
    <title>{title}</title>
    <link>{link}</link>
    <description><![CDATA[{desc_text} <br> <a href="{post["file_url"]}">original size</a>]]></description>
</item>"""
    
    rss += '\n</channel>\n</rss>'
    return rss

# ---- Save ----
try:
    os.makedirs('./safebooru_test', exist_ok=True)
    filename = './safebooru_test/safebooru-yuri-rss-test.xml'
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(generate_rss().strip())
    print('✅ RSS saved to ./safebooru_test/safebooru-yuri-rss.xml (50 items)')
except Exception as e:
    print(f'❌ Failed: {e}')
