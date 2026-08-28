import requests
import os
import sys
from tags_config import COPYRIGHT_TAGS, CHARACTER_TAGS, ORIENTATION

# ---- Load .env if available ----
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---- Environment variables ----
API_KEY = os.environ.get("KEY", "").strip()
USER_ID = os.environ.get("ID", "").strip()

# ---- Debug: show if they are set (masked) ----
print(f"🔑 KEY is {'SET' if API_KEY else 'EMPTY'}")
print(f"🆔 ID is {'SET' if USER_ID else 'EMPTY'}")

if not API_KEY or not USER_ID:
    print("❌ ERROR: KEY or ID environment variable is missing or empty.")
    print("   Please set them via:")
    print("   - .env file (KEY=... / ID=...)")
    print("   - or export KEY=... ID=...")
    print("   - or GitHub Secrets -> env mapping")
    sys.exit(1)

# ---- Blocked tags ----
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

    # ---- Debug: print request (masking the key) ----
    safe_params = params.copy()
    safe_params["api_key"] = "***MASKED***"
    print(f"🌐 Request URL: {url}")
    print(f"📦 Params: {safe_params}")

    response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"})

    # ---- Debug: print response ----
    print(f"📡 Status code: {response.status_code}")
    if response.status_code != 200:
        print(f"❌ Response text (first 500 chars):\n{response.text[:500]}")
        return []

    try:
        data = response.json()
    except ValueError as e:
        print(f"❌ JSON decode error: {e}")
        print(f"Raw response:\n{response.text[:1000]}")
        return []

    # ---- Check if API returned an error message ----
    if "error" in data:
        print(f"❌ API error: {data['error']}")
        return []

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
    print(f"✅ Fetched {len(posts)} posts for tag '{tag}'")
    return posts

def get_latest(limit=50):
    yuri_posts = fetch_posts("yuri", limit)
    yaoi_posts = fetch_posts("yaoi", limit)
    all_posts = {post["id"]: post for post in yuri_posts + yaoi_posts}.values()
    sorted_posts = sorted(all_posts, key=lambda p: p["id"], reverse=True)[:limit]
    return sorted_posts

def generate_rss():
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Gelbooru Yuri & Yaoi - RSS Feed</title>
<link>https://github.com</link>
<description>Latest yuri or yaoi images from Gelbooru (blocked tags filtered)</description>
"""
    posts = get_latest()
    if not posts:
        print("⚠️ No posts retrieved – RSS will be empty.")
    for post in posts:
        all_tags = post["tags"].split()
        copyright_tags = [t for t in all_tags if t in COPYRIGHT_TAGS]
        character_tags = [t for t in all_tags if t in CHARACTER_TAGS]
        orientation_tags = [t for t in all_tags if t in ORIENTATION]
        other_tags = [t for t in all_tags 
                      if t not in COPYRIGHT_TAGS 
                      and t not in CHARACTER_TAGS 
                      and t not in ORIENTATION]

        copy_str = " ".join(copyright_tags) if copyright_tags else "Cannot guess"
        char_str = " ".join(character_tags) if character_tags else "Cannot guess"
        orien_str = " ".join(orientation_tags) if orientation_tags else "Cannot guess"
        tags_str = " ".join(other_tags) if other_tags else "None"
        if len(tags_str) > 1000:
            tags_str = tags_str[:1000] + "..."

        title = " ".join(all_tags[:3]) if all_tags else f"Image {post['id']}"
        desc_text = (f'<img src="{post["sample_url"]}" /><br/><br/>'
                     f"<b>Copyright:</b> {copy_str}<br/><br/>"
                     f"<b>Character(s):</b> {char_str}<br/><br/>"
                     f"<b>Orientation:</b> {orien_str}<br/><br/>"
                     f"<b>Tags:</b> {tags_str}")
        link = post["source"] if post["source"] else post["sample_url"]

        rss += f"""
<item>
    <title>{title}</title>
    <link>{link}</link>
    <description><![CDATA[{desc_text} <br/><br/> <a href="{post["file_url"]}">original size</a>]]></description>
</item>"""

    rss += "\n</channel>\n</rss>"
    return rss

# ---- Main ----
try:
    os.makedirs("./gelbooru", exist_ok=True)
    filename = "./gelbooru/gelbooru-yy-rss.xml"
    rss_content = generate_rss()
    with open(filename, "w", encoding="utf-8") as f:
        f.write(rss_content.strip())
    print("✅ RSS saved to ./gelbooru/gelbooru-yy-rss.xml")
except Exception as e:
    print(f"❌ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
