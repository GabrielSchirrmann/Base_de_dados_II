import requests
from bs4 import BeautifulSoup

url = "https://astronoo.com/pt/artigos/asteroides-lista.html"
headers = {"User-Agent": "Mozilla/5.0"}

response = requests.get(url, headers=headers, timeout=12)
soup = BeautifulSoup(response.text, "html.parser")

tabela = soup.find("table")

for i, tr in enumerate(tabela.find_all("tr"), 1):
    linha = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
    if linha:
        print(f"{i:2d} | {' | '.join(linha)}")



