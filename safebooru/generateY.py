def generate_rss():
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
<title>Gelbooru Yuri & Yaoi - Updated {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
<link>https://github.com</link>
<description>Latest yuri or yaoi images (blocked filtered)</description>
"""
    posts = get_latest()
    print(f"📝 Adding {len(posts)} items to RSS")
    
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
    print(f"📝 Generated RSS length: {len(rss)} characters")
    return rss
