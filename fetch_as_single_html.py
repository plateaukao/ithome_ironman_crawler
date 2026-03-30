import base64
import io
import json
import os
import sys
import hashlib
from bs4 import BeautifulSoup
from PIL import Image
import requests
import re
import shutil
import concurrent.futures
from urllib.parse import urljoin, urlparse
from ebooklib import epub
from simple_term_menu import TerminalMenu

local_folder = 'local_resources'

# Session for connection pooling
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
session.mount('http://', adapter)
session.mount('https://', adapter)

HEADERS = {
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"
}

def get_url_content(url):
    try:
        response = session.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def get_resource(url):
    try:
        response = session.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"Error downloading resource {url}: {e}")
        return None

def extractTitle(url):
    html = get_url_content(url)
    if not html:
        return "Unknown_Title"
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("h3", {"class": "qa-list__title--ironman"})
    if title_tag:
        return title_tag.get_text(strip=True).replace("系列", "").strip()
    return "Unknown_Title"

def get_article_links_from_page(url):
    links = []
    html = get_url_content(url)
    if not html:
        return links
    
    soup = BeautifulSoup(html, "html.parser")
    article_divs = soup.find_all("div", {"class": "qa-list"})

    for art in article_divs:
        title_tag = art.find("a", {"class": "qa-list__title-link"})
        if title_tag:
            title_text = title_tag.text.strip()
            article_url = title_tag["href"].strip()
            links.append((title_text, article_url))
    
    return links

def process_article_content(title, url):
    print(f"Fetching article: {title}")
    html_content = get_url_content(url)
    if not html_content:
        return title, None
    
    # Pre-process content to isolate the article body
    soup = BeautifulSoup(html_content, "html.parser")
    content = soup.find("div", {"class": "qa-panel__content"})
    
    if content:
        # Cleanup header
        header = content.find("div", {"class": "qa-header"})
        if header:
            for child in header.find_all(recursive=False):
                if 'qa-header__title' not in child.get('class', []):
                    child.decompose()
            
            header_title = content.find(class_="qa-header__title")
            if header_title:
                title_hash = hashlib.md5(title.encode()).hexdigest()
                anchor = soup.new_tag("a", attrs={"name": title_hash})
                header_title.insert(0, anchor)

        # Remove action bar
        action_bar = content.find("div", {"class": "qa-action"})
        if action_bar:
            action_bar.decompose()

        # Remove style/link tags to prevent font CSS from being embedded
        for style_tag in content.find_all("style"):
            style_tag.decompose()
        for link_tag in content.find_all("link"):
            link_tag.decompose()

        content['style'] = 'padding-left: 0;'
        return title, str(content)
    
    return title, None

def download_and_replace_resources(html_content, base_url):
    soup = BeautifulSoup(html_content, "html.parser")
    resources_to_download = {} # url -> filename

    # Strip any remaining style/link tags
    for tag in soup.find_all("style"):
        tag.decompose()
    for tag in soup.find_all("link", attrs={"rel": "stylesheet"}):
        tag.decompose()

    # Find images
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue

        if src.startswith("data:"):
            # Decode data URL images and save to disk
            match = re.match(r'data:image/([^;]+);base64,(.*)', src, re.DOTALL)
            if match:
                img_data = base64.b64decode(match.group(2))
                # Convert PNG to JPEG to reduce size (PNGs are 3-10x larger)
                pil_img = Image.open(io.BytesIO(img_data))
                if pil_img.mode in ('RGBA', 'P'):
                    pil_img = pil_img.convert('RGB')
                buf = io.BytesIO()
                pil_img.save(buf, format='JPEG', quality=80)
                img_data = buf.getvalue()
                filename = hashlib.md5(img_data).hexdigest() + '.jpg'
                filepath = os.path.join(local_folder, filename)
                if not os.path.exists(filepath):
                    with open(filepath, 'wb') as f:
                        f.write(img_data)
                img['src'] = f"{local_folder}/{filename}"
        else:
            abs_url = urljoin(base_url, src)
            ext = os.path.splitext(urlparse(abs_url).path)[1]
            filename = hashlib.md5(abs_url.encode()).hexdigest() + ext
            if not filename.endswith(('.jpg', '.png', '.gif', '.jpeg', '.svg', '.webp')):
                 filename += ".jpg" # Default fallback
            # PNG/GIF will be converted to JPEG during download
            html_filename = filename.rsplit('.', 1)[0] + '.jpg' if filename.endswith(('.png', '.gif')) else filename
            resources_to_download[abs_url] = filename
            img['src'] = f"{local_folder}/{html_filename}"

    return str(soup), resources_to_download

def download_asset(url, filename, output_folder):
    content = get_resource(url)
    if content:
        path = os.path.join(output_folder, filename)
        # Convert PNG/GIF to JPEG to reduce EPUB size
        if filename.endswith(('.png', '.gif')):
            try:
                pil_img = Image.open(io.BytesIO(content))
                if pil_img.mode in ('RGBA', 'P'):
                    pil_img = pil_img.convert('RGB')
                buf = io.BytesIO()
                pil_img.save(buf, format='JPEG', quality=80)
                content = buf.getvalue()
                path = path.rsplit('.', 1)[0] + '.jpg'
            except Exception:
                pass  # Keep original if conversion fails
        with open(path, "wb") as f:
            f.write(content)

def generate_epub_file(title, output_file_name, articles_html, resource_folder):
    book = epub.EpubBook()
    book.set_identifier('ithome-' + hashlib.md5(title.encode()).hexdigest())
    book.set_title(title)
    book.set_language('zh-TW')
    book.add_author('iThome')

    style = epub.EpubItem(
        uid="default_style",
        file_name="style/default.css",
        media_type="text/css",
        content=b"img { max-width: 100%; height: auto; }\n"
                b".qa-header__title { page-break-before: always; }\n",
    )
    book.add_item(style)

    # Collect referenced images from article HTML
    referenced_images = set()
    for html in articles_html:
        for match in re.findall(rf'{re.escape(resource_folder)}/([^"\'<>\s]+)', html):
            referenced_images.add(match)

    # Add only referenced images
    media_types = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.gif': 'image/gif',
        '.svg': 'image/svg+xml', '.webp': 'image/webp',
    }
    for filename in referenced_images:
        filepath = os.path.join(resource_folder, filename)
        if not os.path.isfile(filepath):
            continue
        ext = os.path.splitext(filename)[1].lower()
        media_type = media_types.get(ext, 'application/octet-stream')
        with open(filepath, 'rb') as f:
            book.add_item(epub.EpubItem(
                uid=filename,
                file_name=f"images/{filename}",
                media_type=media_type,
                content=f.read(),
            ))

    # Create one chapter per article
    chapters = []
    for i, html in enumerate(articles_html):
        # Rewrite image paths from local_resources/ to images/
        html = html.replace(f'{resource_folder}/', 'images/')

        soup = BeautifulSoup(html, 'html.parser')
        h2 = soup.find('h2')
        chapter_title = h2.get_text(strip=True) if h2 else f'Chapter {i + 1}'

        chapter = epub.EpubHtml(
            title=chapter_title,
            file_name=f'chapter_{i + 1}.xhtml',
            lang='zh-TW',
        )
        chapter.content = html
        chapter.add_item(style)
        book.add_item(chapter)
        chapters.append(chapter)

    book.toc = chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav'] + chapters

    output_file = output_file_name or 'output.epub'
    epub.write_epub(output_file, book)
    print("EPUB generated:", output_file)

def load_rewards(year):
    """Load rewards from local JSON file. Returns {tier: [entries]}."""
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"rewards_{year}.json")
    if not os.path.exists(json_path):
        return {}
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)
    tiers = {}
    for entry in data:
        tiers.setdefault(entry['tier'], []).append(entry)
    return tiers

def interactive_mode():
    years = list(range(2020, 2026))
    idx = TerminalMenu([str(y) for y in years], title="Select a year:").show()
    if idx is None:
        return

    year = years[idx]
    tiers = load_rewards(year)
    if not tiers:
        print(f"No data found. Make sure rewards_{year}.json exists.")
        return

    tier_names = list(tiers.keys())
    idx = TerminalMenu(
        [f"{name} ({len(tiers[name])} series)" for name in tier_names],
        title="Select award tier:",
    ).show()
    if idx is None:
        return
    tier = tier_names[idx]

    entries = tiers[tier]
    idx = TerminalMenu(
        [f"[{e['category']}] {e['title']}" for e in entries],
        title=f"{tier}:",
    ).show()
    if idx is None:
        return
    selected = entries[idx]
    series_title = selected['title']
    series_url = selected['url']

    default_name = re.sub(r'[^\w\s-]', '', series_title).strip().replace(' ', '_') + ".epub"
    filename = input(f"Output filename [{default_name}]: ").strip()
    if not filename:
        filename = default_name
    if not filename.endswith('.epub'):
        filename += '.epub'

    return series_url, filename

def main():
    if len(sys.argv) < 2:
        result = interactive_mode()
        if not result:
            return
        base_url, output_filename = result
    else:
        base_url = sys.argv[1]
        output_filename = sys.argv[2] if len(sys.argv) > 2 else None
    
    # 1. Get Title
    print("Extracting Series Title...")
    title = extractTitle(base_url + "?page=1")
    print(f"Series Title: {title}")

    # 2. Get all article links (fetch pages in parallel, reassemble in order)
    all_links = []
    print("Collecting article links...")
    max_pages = 20
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_page = {executor.submit(get_article_links_from_page, f"{base_url}?page={page}"): page for page in range(1, max_pages + 1)}
        page_results = {}
        for future in concurrent.futures.as_completed(future_to_page):
            page = future_to_page[future]
            page_results[page] = future.result()
    for page in range(1, max_pages + 1):
        links = page_results.get(page, [])
        if not links:
            break
        all_links.extend(links)

    print(f"Found {len(all_links)} articles.")

    # 3. Fetch Article Content in Parallel
    articles_map = {} # url -> content
    print("Downloading articles in parallel...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(process_article_content, title, url): url for title, url in all_links}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            t, content = future.result()
            if content:
                articles_map[url] = content
            else:
                print(f"Failed to fetch content for {t}")

    # 4. Process Resources and Rebuild HTML
    print("Processing resources...")
    if not os.path.exists(local_folder):
        os.makedirs(local_folder)
        
    final_articles_html = []
    all_resources = {} # url -> filename

    # We want to maintain original order
    for _, article_url in all_links:
        if article_url in articles_map:
            content = articles_map[article_url]
            # Replace resources
            new_content, res = download_and_replace_resources(content, "https://ithelp.ithome.com.tw") # Base URL prediction
            final_articles_html.append(new_content)
            all_resources.update(res)

    # 5. Download Resources in Parallel
    print(f"Downloading {len(all_resources)} images/resources...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(download_asset, url, fname, local_folder) for url, fname in all_resources.items()]
        concurrent.futures.wait(futures)

    # 6. Generate EPUB
    generate_epub_file(title, output_filename, final_articles_html, local_folder)

    # Cleanup
    if os.path.exists(local_folder):
        shutil.rmtree(local_folder)
    print("Done!")

if __name__ == "__main__":
    main()




