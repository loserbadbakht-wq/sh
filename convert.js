const xml2js = require('xml2js');
const fs = require('fs');
const parser = new xml2js.Parser({ explicitArray: false });

if (!fs.existsSync('feeds.json')) {
  console.error('❌ feeds.json not found in repository root. Aborting.');
  process.exit(1);
}
const feeds = JSON.parse(fs.readFileSync('feeds.json', 'utf8'));
if (!Array.isArray(feeds) || feeds.length === 0) {
  console.error('❌ feeds.json must contain a non-empty array of { path, filename } objects.');
  process.exit(1);
}

// ── Preprocessing ─────────────────────────────────────────────────

// xml2js with explicitArray:false descends into any child elements
// it finds, so a raw-HTML description like:
//   <description>Some <b>bold</b> text</description>
// becomes { _: "Some  text", b: "bold" } — the <b> tag is lost and
// the word order is scrambled. To keep the HTML verbatim we wrap
// non-CDATA description/content:encoded bodies in CDATA BEFORE
// parsing. CDATA makes xml2js treat the content as an opaque
// string, so tags, entities, and bare `&` all survive unchanged.
//
// Bodies that already contain a CDATA marker are left alone (assumed
// to be valid CDATA already, possibly with text around it).
function wrapDescriptionsInCDATA(xml) {
  const tagPattern = /<(description|content:encoded)>([\s\S]*?)<\/\1>/gi;
  return xml.replace(tagPattern, (match, tagName, content) => {
    if (content.includes('<![CDATA[')) {
      return match; // already has CDATA somewhere — don't touch
    }
    // Escape any literal ]]> inside the content so our CDATA
    // envelope stays intact.
    const safeContent = content.replace(/]]>/g, ']]]]><![CDATA[>');
    return `<${tagName}><![CDATA[${safeContent}]]></${tagName}>`;
  });
}

// Escape bare '&' to '&amp;' so strict XML parsers don't choke on
// URLs like "...?a=1&b=2". CDATA sections are left untouched —
// which now includes any description we just wrapped.
function escapeBareAmpersands(xml) {
  const parts = xml.split(/(<!\[CDATA\[[\s\S]*?\]\]>)/);
  return parts.map((part, i) => {
    if (i % 2 === 1) return part;
    return part.replace(
      /&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)/g,
      '&amp;'
    );
  }).join('');
}

// ── Helpers ───────────────────────────────────────────────────────

// Fallback used only if preprocessing somehow misses a description
// (e.g. weird namespace). Flattens nested xml2js objects into text;
// tag structure is lost here, but this path should essentially
// never trigger once wrapDescriptionsInCDATA is in place.
function coerceToString(value) {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(coerceToString).join(' ').trim();
  if (typeof value === 'object') {
    let out = '';
    if (typeof value._ === 'string') out += value._;
    for (const key of Object.keys(value)) {
      if (key === '_' || key === '$') continue;
      const sub = coerceToString(value[key]);
      if (sub) out += ' ' + sub;
    }
    return out.trim();
  }
  return String(value);
}

// Ensure every field we care about is a plain string. Normally a
// no-op once wrapDescriptionsInCDATA has done its job.
function coerceItemFields(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return item;
  for (const field of ['title', 'link', 'guid', 'pubDate', 'description', 'image']) {
    if (item[field] !== undefined && typeof item[field] !== 'string') {
      item[field] = coerceToString(item[field]);
    }
  }
  return item;
}

// Move ONLY the FIRST <img src="..."> out of description into a
// dedicated `image` field. Any additional <img> tags remain in the
// description untouched. The regex is intentionally NON-GLOBAL.
function extractImageFromDescription(item) {
  if (!item || typeof item.description !== 'string') return item;

  const imgRegex = /<img\b[^>]*?\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)')[^>]*\/?>/i;
  const match = item.description.match(imgRegex);
  if (!match) return item;

  const imageUrl = match[1] !== undefined ? match[1] : match[2];
  if (!imageUrl) return item;

  let newDesc = item.description.replace(imgRegex, '');
  newDesc = newDesc.replace(/^(?:\s|<br\s*\/?>)+/i, '').trim();

  const newItem = {};
  if (item.title !== undefined) newItem.title = item.title;
  if (item.link  !== undefined) newItem.link  = item.link;
  newItem.image = imageUrl;
  for (const key of Object.keys(item)) {
    if (['title', 'link', 'description'].includes(key)) continue;
    newItem[key] = item[key];
  }
  newItem.description = newDesc;
  return newItem;
}

function normalizeAndProcess(result) {
  if (!result || typeof result !== 'object') return result;
  const channel = result?.rss?.channel;
  if (!channel || typeof channel !== 'object') return result;
  if (!channel.item) return result;
  if (!Array.isArray(channel.item)) {
    channel.item = [channel.item];
  }
  channel.item = channel.item
    .filter(it => it && typeof it === 'object' && !Array.isArray(it))
    .map(coerceItemFields)
    .map(extractImageFromDescription);
  return result;
}

async function convertFeed(feed) {
  const jsonPath = `json/${feed.filename}`;
  try {
    console.log(`Reading: ${feed.path}`);
    const rawXml = fs.readFileSync(feed.path, 'utf8');
    const cdataXml = wrapDescriptionsInCDATA(rawXml);
    const cleanedXml = escapeBareAmpersands(cdataXml);
    let result = await parser.parseStringPromise(cleanedXml);
    result = normalizeAndProcess(result);
    fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2));
    console.log(`✅ Saved: ${jsonPath}`);
  } catch (error) {
    console.error(`❌ Error processing ${feed.path}:`, error.message);
    const fallback = { error: `Failed to read: ${error.message}`, timestamp: new Date().toISOString() };
    fs.writeFileSync(jsonPath, JSON.stringify(fallback, null, 2));
    console.log(`⚠️  Fallback written: ${jsonPath}`);
  }
}
async function processAllFeeds() {
  await Promise.all(feeds.map(feed => convertFeed(feed)));
  console.log('All feeds processed!');
}
processAllFeeds();
