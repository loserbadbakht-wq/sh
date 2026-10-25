import json, os, glob, time, re
from googletrans import Translator

SOURCE_DIR = 'json'
OUTPUT_DIR = 'json/translated'
TARGET_LANG = os.getenv('TARGET_LANG', 'es')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# googletrans (free API) has a ~5000-char request limit; 4000 is safe
MAX_CHUNK = 4000


def translate_text(text, translator, retries=3):
    if not text or not isinstance(text, str):
        return text
    stripped = text.strip()
    if not stripped:
        return text

    # If input has very little Latin text, it's probably already in
    # the target language (or pure markup/symbols) — don't retry on
    # "no change".
    total_alpha = sum(1 for c in stripped if c.isalpha())
    latin_alpha = sum(1 for c in stripped if c.isascii() and c.isalpha())
    is_likely_translated = (
        total_alpha == 0
        or len(stripped) < 20
        or (latin_alpha / total_alpha) < 0.3
    )

    for attempt in range(retries):
        try:
            result = translator.translate(text, dest=TARGET_LANG)
            translated = result.text
            # Silent-failure detection (googletrans returns original
            # text when the request silently fails — e.g. rate limit
            # edge cases, or oversized payloads it can't handle)
            if (not is_likely_translated
                    and translated.strip() == stripped
                    and attempt < retries - 1):
                print(f"    ⚠️  Silent failure (unchanged), retry {attempt+1}/{retries}")
                time.sleep(2 ** attempt)
                continue
            return translated
        except Exception as e:
            print(f"    ❌ Translation error (attempt {attempt+1}/{retries}): {e}")
            time.sleep(2 ** attempt)
    return text


def split_with_seps(text, max_len=MAX_CHUNK):
    """Split text into (chunk, sep_after) tuples.

    sep_after is the whitespace that followed the chunk — needed
    because Google Translate strips leading/trailing whitespace from
    its output.
    Preference order: sentence boundaries → spaces → hard cut."""
    if len(text) <= max_len:
        return [(text, '')]

    result = []
    remaining = text

    while len(remaining) > max_len:
        window = remaining[:max_len]

        # 1. Sentence boundary: punctuation followed by whitespace
        matches = list(re.finditer(r'([.!?])(\s)', window))
        if matches and matches[-1].end() > max_len // 2:
            m = matches[-1]
            result.append((remaining[:m.end() - 1], m.group(2)))
            remaining = remaining[m.end():]
            continue

        # 2. Word boundary (space)
        space_pos = window.rfind(' ')
        if space_pos > max_len // 4:
            result.append((remaining[:space_pos], ' '))
            remaining = remaining[space_pos + 1:]
            continue

        # 3. Hard cut (last resort)
        result.append((remaining[:max_len], ''))
        remaining = remaining[max_len:]

    if remaining:
        result.append((remaining, ''))
    return result


def translate_long(text, translator):
    """Translate text, chunking it if it exceeds MAX_CHUNK."""
    if not text or not isinstance(text, str):
        return text
    if len(text) <= MAX_CHUNK:
        return translate_text(text, translator)

    # Split on <br> / <br/> / <br /> first — these are preserved in
    # the output, and are a natural boundary in these feeds.
    parts = re.split(r'(<br\s*/?>)', text, flags=re.IGNORECASE)

    result = []
    buffer = ''

    for i, part in enumerate(parts):
        if i % 2 == 1:  # <br> separator
            for chunk, sep in split_with_seps(buffer, MAX_CHUNK):
                result.append(translate_text(chunk, translator) + sep)
            buffer = ''
            result.append(part)  # keep <br> verbatim
        else:  # text content
            buffer += part

    if buffer:
        for chunk, sep in split_with_seps(buffer, MAX_CHUNK):
            result.append(translate_text(chunk, translator) + sep)

    return ''.join(result)


def translate_feed(data, translator):
    channel = data.get('rss', {}).get('channel', {})
    if channel:
        if 'title' in channel:
            channel['title'] = translate_text(channel['title'], translator)
        if 'description' in channel:
            channel['description'] = translate_long(channel['description'], translator)

        items = channel.get('item', [])
        if isinstance(items, dict):
            items = [items]
            channel['item'] = items

        for idx, item in enumerate(items):
            if 'title' in item:
                item['title'] = translate_text(item['title'], translator)
            if 'description' in item:
                desc = item['description']
                if len(desc) > MAX_CHUNK:
                    print(f"  Item {idx}: long description ({len(desc)} chars) → chunking")
                item['description'] = translate_long(desc, translator)
            time.sleep(0.3)
    return data


def main():
    if not os.path.isdir(SOURCE_DIR):
        print(f"Source folder '{SOURCE_DIR}' does not exist.")
        return
    json_files = sorted(glob.glob(os.path.join(SOURCE_DIR, '*.json')))
    if not json_files:
        print(f"No JSON files found in '{SOURCE_DIR}'.")
        return

    translator = Translator()
    for file_path in json_files:
        filename = os.path.basename(file_path)
        print(f"\n--- Processing: {filename} ---")
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        translated_data = translate_feed(data, translator)
        translated_data['_translated_at'] = time.strftime(
            '%Y-%m-%dT%H:%M:%SZ', time.gmtime()
        )
        output_path = os.path.join(OUTPUT_DIR, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(translated_data, f, indent=2, ensure_ascii=False)
        print(f"  ✅ Saved to: {output_path}")
    print("\nAll feeds translated successfully.")


if __name__ == "__main__":
    main()
