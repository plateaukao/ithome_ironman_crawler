import base64
import os
import sys
import hashlib
from bs4 import BeautifulSoup
import requests
import re
import shutil
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

def createFolder(title):
    folder_name = title.replace("/", "_")
    invalidstr = r"[\/\\\:\*\?\"\<\>\|]"
    folder_name = re.sub(invalidstr, "_", folder_name)
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
    return folder_name

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
        
        content['style'] = 'padding-left: 0;'
        return title, str(content)
    
    return title, None

def download_and_replace_resources(html_content, base_url):
    soup = BeautifulSoup(html_content, "html.parser")
    resources_to_download = {} # url -> filename

    # Find images
    for img in soup.find_all("img"):
        src = img.get("src")
        if src:
            abs_url = urljoin(base_url, src)
            filename = hashlib.md5(abs_url.encode()).hexdigest() + os.path.splitext(urlparse(abs_url).path)[1]
            if not filename.endswith(('.jpg', '.png', '.gif', '.jpeg', '.svg', '.webp')):
                 filename += ".jpg" # Default fallback
            resources_to_download[abs_url] = filename
            img['src'] = f"{local_folder}/{filename}"

    # Find CSS (if we were preserving full head, but we are stripping most. 
    # However, if there are inline styles or other assets, we might need them.
    # The original script focused mostly on images for the content part)
    
    return str(soup), resources_to_download

def download_asset(url, filename, output_folder):
    content = get_resource(url)
    if content:
        path = os.path.join(output_folder, filename)
        with open(path, "wb") as f:
            f.write(content)
        # print(f"Downloaded {filename}")

def generate_epub_file(title, output_file_name):
    command = calibre_convert_path
    input_file = "complete_content.html"
    output_file = "output.epub" if output_file_name is None else output_file_name

    options = [
        "--level1-toc", "//h:h2[@class]",
        "--page-breaks-before", "//h:h2[re:test(@class, 'qa-header__title', 'i')]",
        "--chapter-mark", "none",
        "--title", title,
        "--output-profile", "tablet",
        "--flow-size", "10240"
    ]

    full_command = [command, input_file, output_file] + options

    try:
        subprocess.run(full_command, check=True)
        print("EPUB generated:", output_file)
    except subprocess.CalledProcessError as e:
        print("Error generating EPUB:", e)
    except FileNotFoundError:
        print(f"Error: Calibre ebook-convert not found at {command}")
import subprocess

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

    # 2. Get all article links (Pages 1-4)
    # Note: Currently hardcoded 1-4 as per original script. 
    # Could be dynamic, but sticking to original logic for finding pages.
    all_links = []
    print("Collecting article links...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_page = {executor.submit(get_article_links_from_page, f"{base_url}?page={page}"): page for page in range(1, 6)} # Increased to 5 just in case
        for future in concurrent.futures.as_completed(future_to_page):
            links = future.result()
            all_links.extend(links)
    
    # Deduplicate while preserving order (if logic allows) or just use dict
    # But usually order matters for books. 
    # Since we fetched in parallel, order might be scrambled. We should probably sort or fetch sequentially for pages.
    # To keep simple and correct: re-fetch pages sequentially or handle sorting.
    # For now, let's just re-sort based on something if needed? 
    # Actually, the original script looped 1 to 5 sequentially. 
    # Let's fix the link collection to be ordered correctly.
    
    all_links = []
    for page in range(1, 5):
        url_with_page = base_url + f"?page={page}"
        print(f"Scanning page {page}...")
        links = get_article_links_from_page(url_with_page)
        all_links.extend(links)

    print(f"Found {len(all_links)} articles.")

    # 3. Fetch Article Content in Parallel
    articles_map = {} # title -> content
    print("Downloading articles in parallel...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_title = {executor.submit(process_article_content, title, url): title for title, url in all_links}
        for future in concurrent.futures.as_completed(future_to_title):
            t, content = future.result()
            if content:
                articles_map[t] = content
            else:
                print(f"Failed to fetch content for {t}")

    # 4. Process Resources and Rebuild HTML
    print("Processing resources...")
    if not os.path.exists(local_folder):
        os.makedirs(local_folder)
        
    final_articles_html = []
    all_resources = {} # url -> filename

    # We want to maintain original order
    for article_title, _ in all_links:
        if article_title in articles_map:
            content = articles_map[article_title]
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




