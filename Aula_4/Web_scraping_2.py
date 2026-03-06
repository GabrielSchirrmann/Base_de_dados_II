import requests
from bs4 import BeautifulSoup

url = "https://github.com/trending"

response = requests.get(url, timeout = 20)

soup = BeautifulSoup (response.text, "html.parser")

for div in soup .find_all("article", class_="Box-row"):

    for caixa in div.find_all ("p", class_="col-9 color-fg-muted my-1 tmp-pr-4"):
        print(caixa.text)

    for caixa in div.find_all ("span", class_="programmingLanguage"):
        print(caixa.text)

    for caixa in div.find_all ("font"):
        print(caixa.text)
    print("-------------------------------------------------------------------------------------------------------------------------------------------------------------------------")