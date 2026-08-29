def fetch_article_content(url):
    """Fetch and extract the main article content."""
    headers = {'User-Agent': USER_AGENT}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  ⚠️ Could not fetch article: {e}")
        return None

    # Use BeautifulSoup if available
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        
        # Look for the main article content container
        # Common WordPress classes: entry-content, post-content, article-content
        content_div = soup.find('div', class_=re.compile(r'entry-content|post-content|article-content'))
        
        if content_div:
            # Remove unwanted elements from the content div
            for unwanted in content_div.find_all(['script', 'style', 'ins', 'iframe', 'noscript']):
                unwanted.decompose()
            
            # Extract paragraphs
            paragraphs = content_div.find_all('p')
            if paragraphs:
                text = ' '.join(p.get_text(separator=" ").strip() for p in paragraphs)
                text = re.sub(r'\s+', ' ', text).strip()
                return text
        
        # Fallback: look for any div with class containing "content"
        content_div = soup.find('div', class_=re.compile(r'content'))
        if content_div:
            for unwanted in content_div.find_all(['script', 'style', 'ins', 'iframe', 'noscript']):
                unwanted.decompose()
            paragraphs = content_div.find_all('p')
            if paragraphs:
                text = ' '.join(p.get_text(separator=" ").strip() for p in paragraphs)
                text = re.sub(r'\s+', ' ', text).strip()
                return text

    # Fallback to the original method if BeautifulSoup isn't available
    html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<nav.*?>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<footer.*?>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<header.*?>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<aside.*?>.*?</aside>', '', html, flags=re.DOTALL | re.IGNORECASE)
    
    paragraphs = re.findall(r'<p.*?>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    if paragraphs:
        full_text = ' '.join(strip_html(p) for p in paragraphs)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        
        # Filter out short paragraphs that are likely navigation or ads
        sentences = [s for s in full_text.split('. ') if len(s) > 30]
        if sentences:
            return '. '.join(sentences)
        return full_text
    
    return None
