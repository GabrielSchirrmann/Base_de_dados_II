import requests
from bs4 import BeautifulSoup

url = "https://docs.ufpr.br/~mmsabino/sstatistics/gol_oficial.html"
response = requests.get(url, timeout=20)
response.encoding = "iso-8859-1" 

soup = BeautifulSoup(response.text, "html.parser")

nomes = []
for a in soup.select("table.texto a"):
    texto = a.get_text(" ", strip=True)
    nomes.append(texto)
    

for n in nomes:
    print(n)


#    nome = texto.split(" - (")[0].strip()
#    nomes.append(nome)

