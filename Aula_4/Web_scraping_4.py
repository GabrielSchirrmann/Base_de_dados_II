import requests
from bs4 import BeautifulSoup

url = "https://books.toscrape.com/"

response = requests.get(url, timeout=20)

soup = BeautifulSoup(response.text, "html.parser")

for div in soup.find_all("article", class_="product_pod"):

    for caixa in div.find_all("a"):
        print("Título:", caixa.get("title"))

    for caixa in div.find_all("p", class_="price_color"):
        print("Preço:", caixa.text)

    for caixa in div.find_all("p", class_="instock availability"):
        print("Disponibilidade:", caixa.text.strip())

    print("--------------------------------------------------------------------")