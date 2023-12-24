import os
import sys
from bs4 import BeautifulSoup
import requests

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

    return articles

def create_combined_html(folder, articles):
    combined_html_path = os.path.join(folder, "combined.html")
    with open(combined_html_path, "w", encoding="utf-8") as f:
        # Write the beginning of the HTML file
        f.write("<html><head><title>Combined Articles</title></head><body>")
        f.write("<h1>Table of Contents</h1><ul>")

        # TOC
        for title, path in articles.items():
            f.write(f'<li><a href="#{title}">{title}</a></li>')

        f.write("</ul>")

        # Article contents
        for title, path in articles.items():
            with open(path, 'r', encoding='utf-8') as article_file:
                article_content = article_file.read()
                f.write(f'<h2 id="{title}">{title}</h2>')
                f.write(article_content)

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
        create_combined_html(folder, all_articles)

