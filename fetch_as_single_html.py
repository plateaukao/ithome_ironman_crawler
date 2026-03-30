import base64
import io
import os
import sys
import hashlib
from bs4 import BeautifulSoup
from PIL import Image
import requests
import re
import shutil
import subprocess
import concurrent.futures
from urllib.parse import urljoin, urlparse

calibre_convert_path = "/Applications/calibre.app/Contents/MacOS/ebook-convert"
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
            # Decode data URL images directly instead of letting Calibre handle them
            # (Calibre creates bloated duplicate PNG+JPEG pairs from data URLs)
            match = re.match(r'data:image/([^;]+);base64,(.*)', src, re.DOTALL)
            if match:
                img_data = base64.b64decode(match.group(2))
                # Convert PNG to JPEG to reduce size (PNGs are 3-10x larger)
                pil_img = Image.open(io.BytesIO(img_data))
                if pil_img.mode in ('RGBA', 'P'):
                    pil_img = pil_img.convert('RGB')
                buf = io.BytesIO()
                pil_img.save(buf, format='JPEG', quality=85)
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
            # PNG will be converted to JPEG during download
            html_filename = filename.replace('.png', '.jpg') if filename.endswith('.png') else filename
            resources_to_download[abs_url] = filename
            img['src'] = f"{local_folder}/{html_filename}"

    return str(soup), resources_to_download

def download_asset(url, filename, output_folder):
    content = get_resource(url)
    if content:
        path = os.path.join(output_folder, filename)
        # Convert PNG to JPEG to reduce EPUB size
        if filename.endswith('.png'):
            try:
                pil_img = Image.open(io.BytesIO(content))
                if pil_img.mode in ('RGBA', 'P'):
                    pil_img = pil_img.convert('RGB')
                buf = io.BytesIO()
                pil_img.save(buf, format='JPEG', quality=85)
                content = buf.getvalue()
                path = path.rsplit('.', 1)[0] + '.jpg'
            except Exception:
                pass  # Keep original if conversion fails
        with open(path, "wb") as f:
            f.write(content)

def generate_epub_file(title, output_file_name):
    command = calibre_convert_path
    input_file = "complete_content.html"
    output_file = "output.epub" if output_file_name is None else output_file_name

    options = [
        "--level1-toc", "//h:h2[@class]",
        "--page-breaks-before", "//h:h2[re:test(@class, 'qa-header__title', 'i')]",
        "--chapter-mark", "none",
        "--title", title,
        "--authors", "iThome",
        "--output-profile", "tablet",
        "--flow-size", "10240",
        "--filter-css", "font-family",
        "--subset-embedded-fonts",
    ]

    full_command = [command, input_file, output_file] + options

    try:
        subprocess.run(full_command, check=True)
        print("EPUB generated:", output_file)
    except subprocess.CalledProcessError as e:
        print("Error generating EPUB:", e)
    except FileNotFoundError:
        print(f"Error: Calibre ebook-convert not found at {command}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_as_single_html.py <URL(exclude page param)> [output_filename]")
        return

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

    # 6. Create Combined HTML
    print("Creating combined HTML...")
    with open("complete_content.html", "w", encoding="utf-8") as f:
        f.write(f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title></head><body>")
        for art_html in final_articles_html:
            f.write(art_html)
            f.write("<hr/>")
        f.write("</body></html>")

    # 7. Generate EPUB
    generate_epub_file(title, output_filename)

    # Cleanup
    # if os.path.exists(local_folder):
    #     shutil.rmtree(local_folder)
    # os.remove("complete_content.html")
    print("Done!")

if __name__ == "__main__":
    main()




