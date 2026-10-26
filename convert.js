const xml2js = require('xml2js');
const fs = require('fs');
const parser = new xml2js.Parser({ explicitArray: false });
const feeds = [
  { path: 'safebooru/safebooru-yuri-rss.xml', filename: 'safebooru-yuri-rss.json' },
  { path: 'notif/new1.xml', filename: 'new1.json' },
  { path: 'notif/new2.xml', filename: 'new2.json' },
  { path: 'notif/game8_feed.xml', filename: 'new3.json' }
  
];

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

// Move <img src="..."> out of description into a dedicated `image` field
function extractImageFromDescription(item) {
  if (!item || typeof item.description !== 'string') return item;

  const imgRegex = /<img\b[^>]*\bsrc="([^"]+)"[^>]*\/?>/i;
  const match = item.description.match(imgRegex);
  if (!match) return item;

  const imageUrl = match[1];
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
