import json, os, glob, time, re, hashlib, sys
from googletrans import Translator

SOURCE_DIR = 'json'
OUTPUT_DIR = 'json/translated'
TARGET_LANG = os.getenv('TARGET_LANG', 'es')
os.makedirs(OUTPUT_DIR, exist_ok=True)

MAX_CHUNK = 4000


def coerce_to_str(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(coerce_to_str(v) for v in value).strip()
    if isinstance(value, dict):
        parts = []
        if isinstance(value.get('_'), str):
            parts.append(value['_'])
        for k, v in value.items():
            if k in ('_', '$'):
                continue
            s = coerce_to_str(v)
            if s:
                parts.append(s)
        return " ".join(parts).strip()
    return str(value)


def item_key(item):
    if not isinstance(item, dict):
        return ""
    return (coerce_to_str(item.get('guid'))
            or coerce_to_str(item.get('link'))
            or coerce_to_str(item.get('title')))


def item_hash(item):
    if not isinstance(item, dict):
        return ""
    h = hashlib.sha256()
    h.update(coerce_to_str(item.get('title')).encode('utf-8'))
    h.update(b'\x00')
    h.update(coerce_to_str(item.get('description')).encode('utf-8'))
    return h.hexdigest()


def _safe_str(value, fallback):
    return value if isinstance(value, str) and value else fallback


def translate_text(text, translator, retries=3):
    text = coerce_to_str(text)
    if not text:
        return ""
    stripped = text.strip()
    if not stripped:
        return text

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
            translated = getattr(result, 'text', None)
            if not isinstance(translated, str):
                translated = text

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

    return _safe_str(text, "")


def split_with_seps(text, max_len=MAX_CHUNK):
    text = coerce_to_str(text)
    if len(text) <= max_len:
        return [(text, '')]

    result = []
    remaining = text

    while len(remaining) > max_len:
        window = remaining[:max_len]

        matches = list(re.finditer(r'([.!?])(\s)', window))
        if matches and matches[-1].end() > max_len // 2:
            m = matches[-1]
            result.append((remaining[:m.end() - 1], m.group(2)))
            remaining = remaining[m.end():]
            continue

        space_pos = window.rfind(' ')
        if space_pos > max_len // 4:
            result.append((remaining[:space_pos], ' '))
            remaining = remaining[space_pos + 1:]
            continue

        result.append((remaining[:max_len], ''))
        remaining = remaining[max_len:]

    if remaining:
        result.append((remaining, ''))
    return result


def translate_long(text, translator):
    text = coerce_to_str(text)
    if not text:
        return ""
    if len(text) <= MAX_CHUNK:
        return translate_text(text, translator)

    parts = re.split(r'(<br\s*/?>)', text, flags=re.IGNORECASE)

    result = []
    buffer = ''

    for i, part in enumerate(parts):
        if part is None:
            continue
        if i % 2 == 1:
            for chunk, sep in split_with_seps(buffer, MAX_CHUNK):
                result.append(translate_text(chunk, translator) + sep)
            buffer = ''
            result.append(part)
        else:
            buffer += part

    if buffer:
        for chunk, sep in split_with_seps(buffer, MAX_CHUNK):
            result.append(translate_text(chunk, translator) + sep)

    return ''.join(result)


def load_previous_translated(output_path):
    if not os.path.exists(output_path):
        return {}
    try:
        with open(output_path, 'r', encoding='utf-8') as f:
            prev = json.load(f)
    except Exception:
        return {}
    channel = prev.get('rss', {}).get('channel', {}) if isinstance(prev, dict) else {}
    if not isinstance(channel, dict):
        return {}
    items = channel.get('item', [])
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return {}
    result = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item_key(item)
        if key:
            result[key] = item
    return result


def translate_feed_incremental(data, translator, previous_items):
    channel = data.get('rss', {}).get('channel', {})
    if not isinstance(channel, dict):
        return data, {"reused": 0, "translated": 0}

    stats = {"reused": 0, "translated": 0}

    try:
        if 'title' in channel:
            channel['title'] = translate_text(channel['title'], translator)
        if 'description' in channel:
            channel['description'] = translate_long(channel['description'], translator)
    except Exception as e:
        print(f"  ⚠️  Channel-level translation failed: {e}")

    items = channel.get('item', [])
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return data, stats
    channel['item'] = items

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            print(f"  ⚠️  Item {idx}: not an object, skipping.")
            continue
        try:
            key = item_key(item)
            current_hash = item_hash(item)

            prev = previous_items.get(key)
            if (isinstance(prev, dict)
                    and prev.get('_source_hash') == current_hash):
                if 'title' in prev:
                    item['title'] = prev['title']
                if 'description' in prev:
                    item['description'] = prev['description']
                item['_source_hash'] = current_hash
                stats["reused"] += 1
                continue

            if 'title' in item:
                item['title'] = translate_text(item['title'], translator)
            if 'description' in item:
                desc = coerce_to_str(item['description'])
                if len(desc) > MAX_CHUNK:
                    print(f"  Item {idx}: long description ({len(desc)} chars) → chunking")
                item['description'] = translate_long(desc, translator)
            item['_source_hash'] = current_hash
            stats["translated"] += 1
            time.sleep(0.3)

        except Exception as e:
            print(f"  ❌ Item {idx}: {type(e).__name__}: {e}")
            continue

    return data, stats


def load_items_from_source(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ❌ Cannot read {file_path}: {e}")
        return None
    if not isinstance(data, dict):
        print(f"  ⚠️  {file_path} root is not an object, skipping.")
        return None
    if 'error' in data:
        print(f"  ⚠️  {file_path} is an error fallback, skipping.")
        return None
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
    grand = {"reused": 0, "translated": 0}
    files_ok = 0
    files_failed = 0

    for file_path in json_files:
        filename = os.path.basename(file_path)
        output_path = os.path.join(OUTPUT_DIR, filename)
        print(f"\n--- Processing: {filename} ---")

        data = load_items_from_source(file_path)
        if data is None:
            files_failed += 1
            continue

        try:
            previous_items = load_previous_translated(output_path)
            translated_data, stats = translate_feed_incremental(
                data, translator, previous_items
            )
            grand["reused"] += stats["reused"]
            grand["translated"] += stats["translated"]

            if stats["translated"] > 0:
                translated_data['_translated_at'] = time.strftime(
                    '%Y-%m-%dT%H:%M:%SZ', time.gmtime()
                )
            elif os.path.exists(output_path):
                try:
                    with open(output_path, 'r', encoding='utf-8') as f:
                        prev_ts = json.load(f).get('_translated_at')
                    if prev_ts:
                        translated_data['_translated_at'] = prev_ts
                except Exception:
                    pass

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(translated_data, f, indent=2, ensure_ascii=False)
            print(f"  ✅ Saved: {output_path} "
                  f"({stats['translated']} new, {stats['reused']} reused)")
            files_ok += 1

        except Exception as e:
            print(f"  ❌ File-level error on {filename}: {e}")
            files_failed += 1

    print(f"\n📊 Translation summary: {grand['translated']} translated, "
          f"{grand['reused']} reused, {files_ok} file(s) ok, "
          f"{files_failed} failed")

    if files_ok == 0 and files_failed > 0:
        print("\n❌ All files failed — exiting non-zero.")
        sys.exit(1)
    elif files_failed > 0:
        print(f"\n⚠️  {files_failed} file(s) failed but "
              f"{files_ok} succeeded — continuing.")


if __name__ == "__main__":
    main()
