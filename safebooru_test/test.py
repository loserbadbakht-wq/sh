import requests
import xml.etree.ElementTree as ET
import os

# ---- Get script's directory for reliable file paths ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_tags_from_file(filename):
    tags = set()
    filepath = os.path.join(SCRIPT_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    tags.add(line)
        print(f"✅ Loaded {len(tags)} tags from {filename}")
    else:
        print(f"⚠️ File not found: {filepath}")
    return tags

def load_tags_from_folder(folder_name):
    tags = set()
    folder_path = os.path.join(SCRIPT_DIR, folder_name)
    if os.path.exists(folder_path) and os.path.isdir(folder_path):
        for filename in os.listdir(folder_path):
            if filename.endswith('.txt'):
                filepath = os.path.join(folder_path, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            tags.add(line)
                print(f"✅ Loaded tags from {filename}")
    else:
        print(f"⚠️ Folder not found: {folder_path}")
    return tags

# ---- Load tags ----
COPYRIGHT_TAGS = load_tags_from_file('copyright_tags.txt')
CHARACTER_TAGS = load_tags_from_folder('character_tags')

print("\n📚 COPYRIGHT_TAGS (first 10):", list(COPYRIGHT_TAGS)[:10])
print("👤 CHARACTER_TAGS (first 10):", list(CHARACTER_TAGS)[:10])
print("---")

# ---- Fetch & Debug ----
def get_latest(limit=5):
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

# ---- Show first post's tags ----
first_posts = get_latest(1)
if first_posts:
    sample_tags = first_posts[0]['tags'].split()
    print("🧩 Tags from FIRST post (exact strings):")
    for t in sample_tags:
        print(f"  '{t}'")
    print("\n👉 Copy these EXACT strings into your .txt files (one per line, no quotes).")
else:
    print("❌ No posts fetched – check internet or API.")

# ---- Now generate full RSS with debug info inside ----
def generate_rss_debug():
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Safebooru Yuri - RSS Feed (debug)</title>
<link>https://github.com</link>
<description>Debug version – shows matched tags</description>
"""
    for idx, post in enumerate(get_latest(50)):
        all_tags = post['tags'].split()
        
        # Match
        copyright_tags = [t for t in all_tags if t in COPYRIGHT_TAGS]
        character_tags = [t for t in all_tags if t in CHARACTER_TAGS]
        other_tags = [t for t in all_tags if t not in COPYRIGHT_TAGS and t not in CHARACTER_TAGS]
        
        # Debug print for first 3 items
        if idx < 3:
            print(f"\n--- Post {idx+1} ---")
            print("All tags:", all_tags[:10])  # show first 10
            print("Copyright matched:", copyright_tags)
            print("Character matched:", character_tags)
            print("Other tags (first 10):", other_tags[:10])
        
        # Build description
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

# ---- Save ----
try:
    os.makedirs(os.path.join(SCRIPT_DIR, 'safebooru_test'), exist_ok=True)
    filename = os.path.join(SCRIPT_DIR, 'safebooru_test', 'safebooru-yuri-rss-test.xml')
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(generate_rss_debug().strip())
    print(f"\n✅ RSS saved to {filename}")
except Exception as e:
    print(f'❌ Failed: {e}')
