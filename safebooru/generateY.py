import requests
import xml.etree.ElementTree as ET
import os
from tags_config import COPYRIGHT_TAGS, CHARACTER_TAGS, ORIENTATION

def fetch_posts(tag, limit=50):
    url = 'https://konachan.com/post.xml'
    params = {'limit': limit, 'pid': 0, 'tags': f'{tag} -ai-generated'}
    response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})
    root = ET.fromstring(response.content)
    posts = []
    for post in root.findall('post'):
        posts.append({
            'id': int(post.get('id')),
            'sample_url': post.get('sample_url'),
            'source': post.get('source'),
            'tags': post.get('tags'),
            'rating': post.get('rating'),
            'score': post.get('score'),
            'file_url': post.get('file_url')
        })
    return posts

def get_latest(limit=50):
    yuri_posts = fetch_posts('yuri', limit)
    yaoi_posts = fetch_posts('yaoi', limit)
    all_posts = {post['id']: post for post in yuri_posts + yaoi_posts}.values()
    sorted_posts = sorted(all_posts, key=lambda p: p['id'], reverse=True)[:limit]
    return sorted_posts

def generate_rss():
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Safebooru Yuri & Yaoi - RSS Feed</title>
<link>https://github.com</link>
<description>Latest yuri or yaoi images from safebooru</description>
"""
    for post in get_latest():
        all_tags = post['tags'].split()
        
        copyright_tags = [t for t in all_tags if t in COPYRIGHT_TAGS]
        character_tags = [t for t in all_tags if t in CHARACTER_TAGS]
        orientation_tags = [t for t in all_tags if t in ORIENTATION]
        other_tags = [t for t in all_tags 
                      if t not in COPYRIGHT_TAGS 
                      and t not in CHARACTER_TAGS 
                      and t not in ORIENTATION]
        
        copy_str = ' '.join(copyright_tags) if copyright_tags else 'Cannot guess'
        char_str = ' '.join(character_tags) if character_tags else 'Cannot guess'
        orien_str = ' '.join(orientation_tags) if orientation_tags else 'Cannot guess'
        tags_str = ' '.join(other_tags) if other_tags else 'None'
        if len(tags_str) > 1000:
            tags_str = tags_str[:1000] + '...'
        
        title = ' '.join(all_tags[:3]) if all_tags else f"Image {post['id']}"
        desc_text = (f'<img src="{post["sample_url"]}" /><br/><br/>'
                     f"<b>Copyright:</b> {copy_str}<br/><br/>"
                     f"<b>Character(s):</b> {char_str}<br/><br/>"
                     f"<b>Orientation:</b> {orien_str}<br/><br/>"
                     f"<b>Tags:</b> {tags_str}")
        link = post['source'] if post['source'] else post['sample_url']
        
        rss += f"""
<item>
    <title>{title}</title>
    <link>{link}</link>
    <description><![CDATA[{desc_text} <br/><br/> <a href="{post["file_url"]}">original size</a>]]></description>
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
