import requests
from bs4 import BeautifulSoup

def saveArticle(title, url):
    with open(title+".html", "w", encoding="utf-8") as f:
        response = requests.get(url, headers={"user-agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"})
        f.write(response.text)

url = "https://ithelp.ithome.com.tw/users/20140998/ironman/4362?page=1"
response = requests.get(url, headers={"user-agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"})
html = BeautifulSoup(response.text, "html.parser")
article = html.find_all("div", {"class":"qa-list"})

for art in article:
    title = art.find("a", {"class":"qa-list__title-link"})  # 標題名稱
    print("標題", title.text.strip())
    print("網址", title["href"].strip())
    saveArticle(title.text.strip(), title["href"].strip())

