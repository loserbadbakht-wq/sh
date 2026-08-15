import requests
import xml.etree.ElementTree as ET
import os

def get_latest(limit=10):
    """Fetch latest posts containing the 'yuri' tag."""
    url = 'https://safebooru.org/index.php?page=dapi&s=post&q=index'
    params = {
        'limit': limit,
        'pid': 0,
        'tags': 'yuri'          # server‑side filtering – only yuri posts
    }
    response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})
    root = ET.fromstring(response.content)
    
    posts = []
    for post in root.findall('post'):
        posts.append({
            'id': post.get('id'),
            'file_url': post.get('file_url'),
            'tags': post.get('tags'),
            'rating': post.get('rating'),
            'score': post.get('score')
        })
    return posts

def generate_rss():
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Safebooru Yuri - RSS Feed</title>
<link>https://github.com/ArjixGamer/anime-rss</link>
<description>Latest yuri images from Safebooru</description>
"""
    for post in get_latest():
        # Title: first 3 tags, or fallback to image ID
        tags = post['tags'].split()
        title = ' '.join(tags[:3]) if tags else f"Image {post['id']}"
        
        # Description: tags (truncated), rating, score
        desc_tags = post['tags'][:200] + ('...' if len(post['tags']) > 200 else '')
        desc = f"Tags: {desc_tags} | Rating: {post['rating']} | Score: {post['score']}"
        
        rss += f"""
<item>
    <title>{title}</title>
    <link>{post['file_url']}</link>
    <description>{desc}</description>
</item>"""
    
    rss += '\n</channel>\n</rss>'
    return rss

# Save the RSS file
try:
    os.makedirs('./safebooru', exist_ok=True)
    filename = './safebooru/safebooru-yuri-rss.xml'
    if os.path.exists(filename):
        os.remove(filename)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(generate_rss().strip())
    print('✅ Safebooru yuri RSS generated successfully.')
except Exception as e:
    print(f'❌ Failed: {e}')
