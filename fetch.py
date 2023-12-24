import requests
from bs4 import BeautifulSoup
import os
import sys

def saveArticle(folder, title, url):
    file_path = os.path.join(folder, title.replace("/", "_") + ".html")
    with open(file_path, "w", encoding="utf-8") as f:
        response = requests.get(url, headers={"user-agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"})
        f.write(response.text)

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
    response = requests.get(url, headers={"user-agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"})
    html = BeautifulSoup(response.text, "html.parser")
    article = html.find_all("div", {"class":"qa-list"})

    for art in article:
        title = art.find("a", {"class":"qa-list__title-link"})  # 標題名稱
        print("標題", title.text.strip())
        print("網址", title["href"].strip())
        saveArticle(folder, title.text.strip(), title["href"].strip())

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("請提供一個URL作為參數。")
    else:
        base_url = sys.argv[1]
        title = extractTitle(base_url + "?page=1")
        folder = createFolder(title)
        for page in range(1, 5):
            url_with_page = base_url + f"?page={page}"
            process_page(folder, url_with_page)

