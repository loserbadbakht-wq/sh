import requests
import os
import sys
from tags_config import COPYRIGHT_TAGS, CHARACTER_TAGS, ORIENTATION
from datetime import datetime

# ---- Load .env ----
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_KEY = os.environ.get("KEY", "").strip()
USER_ID = os.environ.get("ID", "").strip()

print(f"🔑 KEY is {'SET' if API_KEY else 'EMPTY'}")
print(f"🆔 ID is {'SET' if USER_ID else 'EMPTY'}")

if not API_KEY or not USER_ID:
    print("❌ ERROR: KEY or ID missing")
    sys.exit(1)

BLOCKED_TAGS = [
    "guro", "snuff", "scat", "bestiality", "rape",
    "loli", "shota", "incest", "mind_break", "netorare",
]

def build_blocked_filter():
    return " " + " ".join(f"-{tag}" for tag in BLOCKED_TAGS)

def fetch_posts(tag, limit=50):
    url = "https://gelbooru.com/index.php"
    params = {
        "page": "dapi",
        "s": "post",
        "q": "index",
        "json": 1,
        "limit": limit,
        "pid": 0,
        "tags": f"{tag}{build_blocked_filter()}",
        "api_key": API_KEY,
        "user_id": USER_ID,
    }

    response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})

    if response.status_code != 200:
        print(f"⚠️ API error: {response.status_code}")
        return []

    data = response.json()
    posts = []
    for post in data.get("post", []):
        posts.append({
            "id": int(post.get("id", 0)),
            "sample_url": post.get("sample_url", ""),
            "source": post.get("source", ""),
            "tags": post.get("tags", ""),
            "rating": post.get("rating", ""),
            "score": post.get("score", 0),
            "file_url": post.get("file_url", ""),
        })
    print(f"✅ Fetched {len(posts)} posts for '{tag}'")
    if posts:
        print(f"   First 3 IDs: {[p['id'] for p in posts[:3]]}")
    return posts

def get_latest(limit=50):
    yuri_posts = fetch_posts("yuri", limit)
    yaoi_posts = fetch_posts("yaoi", limit)
    all_posts = {post["id"]: post for post in yuri_posts + yaoi_posts}.values()
    sorted_posts = sorted(all_posts, key=lambda p: p["id"], reverse=True)[:limit]
    print(f"🔄 Merged unique posts: {len(sorted_posts)}")
    return sorted_posts

def generate_rss():
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Gelbooru Yuri & Yaoi - Updated {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
<link>https://github.com</link>
<description>Latest yuri or yaoi images (blocked filtered)</description>
"""
    posts = get_latest()
    if not posts:
        print("⚠️ No posts to add – RSS will have only skeleton.")
    for post in posts:
        all_tags = post["tags"].split()
        # ... (same as your code for tags extraction)
        # I'll keep it short – you can copy your full generation block
        copyright_tags = [t for t in all_tags if t in COPYRIGHT_TAGS]
        # ...
        # (put your existing code here)
        rss += f"""<item>...</item>"""
    rss += "\n</channel>\n</rss>"
    print(f"📝 Generated RSS length: {len(rss)} characters")
    return rss

# ---- Main ----
try:
    os.makedirs("./gelbooru", exist_ok=True)
    filename = "./gelbooru/gelbooru-yy-rss.xml"
    abs_path = os.path.abspath(filename)
    print(f"📁 Writing to: {abs_path}")

    rss_content = generate_rss().strip()
    with open(filename, "w", encoding="utf-8") as f:
        f.write(rss_content)

    # Verify file size
    file_size = os.path.getsize(abs_path)
    print(f"📄 File size after write: {file_size} bytes")
    if file_size == 0:
        print("❌ File is EMPTY – something went wrong with writing.")
    else:
        print("✅ RSS saved.")
except Exception as e:
    print(f"❌ Failed: {e}")
    import traceback
    traceback.print_exc()
