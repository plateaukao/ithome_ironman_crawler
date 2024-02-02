import os
import sys
import hashlib
from bs4 import BeautifulSoup
import requests
import webbrowser


def saveArticle(folder, title, url):
    file_path = os.path.join(folder, title.replace("/", "_") + ".html")
    with open(file_path, "w", encoding="utf-8") as f:
        response = requests.get(url, headers={"user-agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"})
        f.write(response.text)
    return file_path

def createFolder(title):
    folder_name = title.replace("/", "_")
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

def process_page(folder, url):
    articles = {}
    response = requests.get(url, headers={"user-agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"})
    html = BeautifulSoup(response.text, "html.parser")
    article_divs = html.find_all("div", {"class":"qa-list"})

    for art in article_divs:
        title = art.find("a", {"class":"qa-list__title-link"})  # 標題名稱
        title_text = title.text.strip()
        article_url = title["href"].strip()
        file_path = saveArticle(folder, title_text, article_url)
        articles[title_text] = file_path
        print("Porcessing " + title_text)

    return articles

def create_combined_html(folder, main_title, articles):
    combined_html_path = os.path.join(folder, "combined.html")
    first_article_path = next(iter(articles.values()))
    with open(first_article_path, 'r', encoding='utf-8') as first_article_file:
        soup = BeautifulSoup(first_article_file, "html.parser")
        head_content = soup.find("head")
        head_content.title.decompose()
        head_html = str(head_content) if head_content else "<head><title>Combined Articles</title></head>"

    with open(combined_html_path, "w", encoding="utf-8") as f:
        # Write the beginning of the HTML file
        f.write(f"<!DOCTYPE html><html>{head_html}<title>{main_title}</title><body>")
        #f.write("<h1 id=toc>Table of Contents</h1><ul>")

        # TOC
        for title, path in articles.items():
            title_hash = hashlib.md5(title.encode()).hexdigest()
            #f.write(f'<li><a href="#{title_hash}">{title}</a></li>')

        #f.write("</ul>")

        # Article contents
        for title, path in articles.items():
            with open(path, 'r', encoding='utf-8') as article_file:
                article_content = article_file.read()
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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("請提供一個URL作為參數。")
    else:
        base_url = sys.argv[1]
        title = extractTitle(base_url + "?page=1")
        folder = createFolder(title)
        all_articles = {}
        for page in range(1, 5):
            url_with_page = base_url + f"?page={page}"
            articles = process_page(folder, url_with_page)
            all_articles.update(articles)
        create_combined_html(folder, title, all_articles)

	# Open the combined HTML file in the default web browser
        combined_html_path = os.path.join(folder, "combined.html")
        webbrowser.open('file://' + os.path.realpath(combined_html_path))

