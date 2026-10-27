const xml2js = require('xml2js');
const fs = require('fs');
const parser = new xml2js.Parser({ explicitArray: false });

// Feeds are defined in feeds.json — each entry must have:
//   { "path": "<repo-relative xml path>", "filename": "<output>.json" }
// feeds.json is required; there is no built-in default.
if (!fs.existsSync('feeds.json')) {
  console.error('❌ feeds.json not found in repository root. Aborting.');
  process.exit(1);
}
const feeds = JSON.parse(fs.readFileSync('feeds.json', 'utf8'));
if (!Array.isArray(feeds) || feeds.length === 0) {
  console.error('❌ feeds.json must contain a non-empty array of { path, filename } objects.');
  process.exit(1);
}

// Escape bare '&' to '&amp;' so strict XML parsers don't choke on
// URLs like "...?a=1&b=2". CDATA sections are left untouched.
function escapeBareAmpersands(xml) {
  const parts = xml.split(/(<!\[CDATA\[[\s\S]*?\]\]>)/);
  return parts.map((part, i) => {
    if (i % 2 === 1) return part;   // CDATA section – leave as-is
    return part.replace(
      /&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)/g,
      '&amp;'
    );
  }).join('');
}

// Move ONLY the FIRST <img src="..."> out of description into a
// dedicated `image` field. Any additional <img> tags remain in the
// description untouched.
//
// The regex is intentionally NON-GLOBAL so `.match()` captures the
// first image and `.replace()` strips only that first occurrence.
function extractImageFromDescription(item) {
  if (!item || typeof item.description !== 'string') return item;

  // Handles src="..." and src='...', self-closing or not.
  // Group 1 = double-quoted URL, Group 2 = single-quoted URL.
  const imgRegex = /<img\b[^>]*?\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)')[^>]*\/?>/i;
  const match = item.description.match(imgRegex);
  if (!match) return item;

  const imageUrl = match[1] !== undefined ? match[1] : match[2];
  if (!imageUrl) return item;

  // Remove ONLY the first matched <img> tag.
  // Later <img> tags are preserved in the description.
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
  const channel = result?.rss?.channel;
  if (!channel || !channel.item) return result;
  if (!Array.isArray(channel.item)) {
    channel.item = [channel.item];
  }
  channel.item = channel.item.map(extractImageFromDescription);
  return result;
}

async function convertFeed(feed) {
  const jsonPath = `json/${feed.filename}`;
  try {
    console.log(`Reading: ${feed.path}`);
    const xmlContent = fs.readFileSync(feed.path, 'utf8');
    const cleanedXml = escapeBareAmpersands(xmlContent);
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
