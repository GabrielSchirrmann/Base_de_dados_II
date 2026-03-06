import requests
from bs4 import BeautifulSoup

url = "https://realpython.github.io/fake-jobs/"

response = requests.get(url, timeout=20)

soup = BeautifulSoup(response.text, "html.parser")

for vaga in soup.find_all("div", class_="card-content"):

    for caixa in vaga.find_all("h2", class_="title is-5"):
        print("Cargo:", caixa.text)

    for caixa in vaga.find_all("h3", class_="subtitle is-6 company"):
        print("Empresa:", caixa.text)

    for caixa in vaga.find_all("p", class_="location"):
        print("Local:", caixa.text)

    for caixa in vaga.find_all("time"):
        print("Data:", caixa.text)

    print("--------------------------------------------------------------------------")