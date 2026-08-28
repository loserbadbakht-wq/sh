import requests
import xml.etree.ElementTree as ET
import os

# ---- Import tag lists from the config file ----
from tags_config import COPYRIGHT_TAGS, CHARACTER_TAGS, ORIENTATION

def get_latest(limit=50):
    url = 'https://safebooru.org/index.php?page=dapi&s=post&q=index'
    params = {'limit': limit, 'pid': 0, 'tags': 'yuri yaoi -ai-generated'}
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
<title>Safebooru Yuri Yaoi - RSS Feed</title>
<link>https://github.com</link>
<description>Latest yuri & yaoi images from safebooru</description>
"""
    for post in get_latest():
        all_tags = post['tags'].split()
        
        copyright_tags = [t for t in all_tags if t in COPYRIGHT_TAGS]
        character_tags = [t for t in all_tags if t in CHARACTER_TAGS]
        orientation = [t for t in all_tags if t in ORIENTATION]
        other_tags = [t for t in all_tags if t not in COPYRIGHT_TAGS and t not in CHARACTER_TAGS]
        
        copy_str = ' '.join(copyright_tags) if copyright_tags else 'Can not guees'
        char_str = ' '.join(character_tags) if character_tags else 'Can not guess'
        orien_str = ' '.join(orientation) if orientation else 'Can not guess'
        tags_str = ' '.join(other_tags) if other_tags else 'None'
        if len(tags_str) > 1000:
            tags_str = tags_str[:1000] + '...'
        
        title = ' '.join(all_tags[:3]) if all_tags else f"Image {post['id']}"
        desc_text = (f'<img src="{post["sample_url"]}" />'
                     f"<b>Copyright:</b> {copy_str}<br/> <br/>"
                     f"<b>Character(s):</b> {char_str}<br/> <br/>"
                     f"<b>Orientation:</b> {orien_str}<br/> <br/>"
                     f"<b>Tags:</b> {tags_str}<br/>")
        link = post['source'] if post['source'] else post['sample_url']
        
        rss += f"""
<item>
    <title></title>
    <link>{link}</link>
    <description><![CDATA[{desc_text} <br> <a href="{post["file_url"]}">original size</a>]]></description>
</item>"""
    
    rss += '\n</channel>\n</rss>'
    return rss

# ---- Save ----
try:
    os.makedirs('./safebooru', exist_ok=True)
    filename = './safebooru/safebooru-yy-rss.xml'
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(generate_rss().strip())
    print('✅ RSS saved to ./safebooru/safebooru-yy-rss.xml')
except Exception as e:
    print(f'❌ Failed: {e}')
