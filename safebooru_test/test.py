import requests
import xml.etree.ElementTree as ET
import os

# ---- Inline tag sets for testing (no file loading) ----
COPYRIGHT_TAGS = {'genshin_impact'}   # Add more if you want
CHARACTER_TAGS = {
    'hu_tao_(genshin_impact)',
    'ganyu_(genshin_impact)',
    'xiao_(genshin_impact)',
    # add more characters you know appear
}

def get_latest(limit=10):
    url = 'https://safebooru.org/index.php?page=dapi&s=post&q=index'
    # Force genshin_impact so every post has it
    params = {'limit': limit, 'pid': 0, 'tags': 'yuri -ai-generated genshin_impact'}
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
<title>Safebooru Yuri (Genshin) - RSS Feed</title>
<link>https://github.com</link>
<description>Test separation</description>
"""
    for post in get_latest():
        all_tags = post['tags'].split()
        
        # ---- SEPARATE ----
        copyright_tags = [t for t in all_tags if t in COPYRIGHT_TAGS]
        character_tags = [t for t in all_tags if t in CHARACTER_TAGS]
        other_tags = [t for t in all_tags if t not in COPYRIGHT_TAGS and t not in CHARACTER_TAGS]
        
        # Print to console so you see what was matched
        print(f"Post {post['id']}: Copyright: {copyright_tags}, Character: {character_tags}")
        
        copy_str = ' '.join(copyright_tags) if copyright_tags else 'None'
        char_str = ' '.join(character_tags) if character_tags else 'None'
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

# Save
try:
    os.makedirs('./safebooru', exist_ok=True)
    with open('./safebooru_test/safebooru-yuri-test.xml', 'w', encoding='utf-8') as f:
        f.write(generate_rss().strip())
    print("✅ Test RSS saved to ./safebooru_test/safebooru-yuri-test.xml")
except Exception as e:
    print(f"❌ Error: {e}")
