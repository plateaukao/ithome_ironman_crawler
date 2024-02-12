import base64
import os
import sys
import hashlib
from bs4 import BeautifulSoup
import requests
import webbrowser
import urllib.parse
from urllib.parse import urlparse, parse_qs
import re
import subprocess

calibre_convert_path = "/Applications/calibre.app/Contents/MacOS/ebook-convert"

def getArticleHtml(url):
    response = requests.get(url, headers={"user-agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"})
    return response.text

def createFolder(title):
    folder_name = title.replace("/", "_")
    invalidstr = r"[\/\\\:\*\?\"\<\>\|]"
    folder_name = re.sub(invalidstr, "_", folder_name)
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
    return folder_name

def extractTitle(url):
    response = requests.get(url, headers={"user-agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"})
    html = BeautifulSoup(response.text, "html.parser")
    title_tag = html.find("h3", {"class":"qa-list__title"})
    if title_tag:
        return title_tag.get_text(strip=True)
    return "Unknown_Title"

def process_page(url):
    articles = {}
    response = requests.get(url, headers={"user-agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"})
    html = BeautifulSoup(response.text, "html.parser")
    article_divs = html.find_all("div", {"class":"qa-list"})

    for art in article_divs:
        title = art.find("a", {"class":"qa-list__title-link"})  # 標題名稱
        title_text = title.text.strip()
        article_url = title["href"].strip()
        articleHtml = getArticleHtml(article_url)
        articles[title_text] = articleHtml
        print("Processing " + title_text)

    return articles

def create_combined_html(main_title, articles):
    first_article_content = next(iter(articles.values()))
    soup = BeautifulSoup(first_article_content, "html.parser")
    head_content = soup.find("head")
    head_content.title.decompose()
    head_html = str(head_content) if head_content else "<head><title>Combined Articles</title></head>"

    with open("combined.html", "w", encoding="utf-8") as f:
        # Write the beginning of the HTML file
        head_html = head_html.replace("link href=\"//","link href=\"https://")
        f.write(f"<!DOCTYPE html><html>{head_html}<title>{main_title}</title><body>")

        # Article contents
        for title, article_content in articles.items():
            article_content = article_content.replace("src=\"/images/","src=\"https://ithelp.ithome.com.tw/images/")
            html = BeautifulSoup(article_content, "html.parser")
            content = html.find("div", {"class":"qa-panel__content"})
            if content:
                content['style'] = f'padding-left: 0;'

                header = content.find("div", {"class":"qa-header"})
                for child in header.find_all(recursive=False):
                    if 'qa-header__title' not in child.get('class', []):
                        child.decompose()
                
                header_title = content.find(class_="qa-header__title")
                title_hash = hashlib.md5(title.encode()).hexdigest()
                anchor = soup.new_tag("a", attrs={"name": title_hash})
                header_title.insert(0, anchor)

                action_bar = content.find("div", {"class":"qa-action"})
                action_bar.decompose()

                f.write(str(content))

        # End of the HTML file
        f.write("</body></html>")

def saveCompleteHtml():
    # 定義命令和參數
    command = "monolith"
    input_file = "combined.html"
    output_file = "complete_content.html"
    options = ["-I", "-o", output_file]

    # 展開用戶家目錄路徑
    input_file_expanded = subprocess.check_output(['echo', input_file], universal_newlines=True).strip()

    # 組合命令
    full_command = [command, input_file_expanded] + options

    # 運行命令
    try:
        subprocess.run(full_command, check=True)
        print("命令成功運行，輸出文件已保存到:", output_file)
    except subprocess.CalledProcessError as e:
        print("運行命令時出錯:", e)

def save_data_uri_to_file(data_uri, output_folder):
    # 解析data URI
    header, encoded = data_uri.split(',', 1)
    data_type = header.split(';')[0].split(':')[1]
    file_extension = data_type.split('/')[1]  # 假設從MIME類型獲取文件擴展名
    if 'base64' in header:
        data = base64.b64decode(encoded)
    else:
        data = encoded

    # 創建文件名
    file_name = f"resource.{file_extension}"
    file_path = os.path.join(output_folder, file_name)

    # 確保文件名唯一
    counter = 1
    while os.path.exists(file_path):
        file_name = f"resource_{counter}.{file_extension}"
        file_path = os.path.join(output_folder, file_name)
        counter += 1

    # 寫入文件
    with open(file_path, 'wb') as file:
        file.write(data)
    
    return file_name

def extract_css_data_text():
    # 設定本地文件夾路徑
    local_folder = 'local_resources'
    # 確保本地文件夾存在
    if not os.path.exists(local_folder):
        os.makedirs(local_folder)


    html_doc = open("complete_content.html", "r", encoding="utf-8").read() 
    soup = BeautifulSoup(html_doc, 'html.parser')
    # 處理<link>標籤
    for link in soup.find_all('link', href=True):
        if link['href'].startswith('data:'):
            file_name = save_data_uri_to_file(link['href'], local_folder)
            link['href'] = os.path.join(local_folder, file_name)

    # 處理<style>標籤中的data URI
    for style in soup.find_all('style'):
        if 'data:' in style.string:
            # 這裡的實現可能需要根據實際情況進行調整，因為CSS中可能含有多個data URI
            # 範例僅針對單一情況進行處理
            data_uris = [uri for uri in style.string.split('url(') if 'data:' in uri]
            for data_uri in data_uris:
                uri_content = data_uri.split(')')[0]  # 獲取data URI部分
                file_name = save_data_uri_to_file(uri_content, local_folder)
                # 更新style標籤中的內容
                style.string = style.string.replace(uri_content, os.path.join(local_folder, file_name))

    # 更新後的HTML
    updated_html = str(soup)
    with open("complete_content.html", "w", encoding="utf-8") as f:
        # Write the beginning of the HTML file
        f.write(updated_html)

def generate_epub_file(title, output_file_name):
    # 定義命令和參數
    command = calibre_convert_path  # 如果這是Calibre的ebook-convert命令，請確保使用正確的命令名稱，如 "ebook-convert"
    input_file = "complete_content.html"
    output_file = "output.epub" if output_file_name == None else output_file_name

    options = [
        "--level1-toc", "//h:h2[@class]",
        "--page-breaks-before", "//h:h2[re:test(@class, 'qa-header__title', 'i')]",
        "--chapter-mark", "none",
        "--title", title,
        "--output-profile", "tablet",
        "--flow-size", "10240"
    ]

    # 組合命令
    full_command = [command, input_file, output_file] + options

    # 運行命令
    try:
        subprocess.run(full_command, check=True)
        print("命令成功運行，EPUB文件已生成:", output_file)
    except subprocess.CalledProcessError as e:
        print("運行命令時出錯:", e)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("請提供一個URL作為參數。")
    else:
        base_url = sys.argv[1]
        title = extractTitle(base_url + "?page=1")
        all_articles = {}
        for page in range(1, 5):
            url_with_page = base_url + f"?page={page}"
            articles = process_page(url_with_page)
            all_articles.update(articles)
        create_combined_html(title, all_articles)

        # save as one complete html
        saveCompleteHtml()
        extract_css_data_text()

        # generate epub
        generate_epub_file(title, sys.argv[2])



