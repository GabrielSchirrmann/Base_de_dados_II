import requests
from bs4 import BeautifulSoup

url = "https://quotes.toscrape.com/"

response = requests.get(url, timeout = 20)

soup = BeautifulSoup (response.text, "html.parser")

for div in soup .find_all("div", class_="quote"):
    for span in div.find_all ("span", class_="text"):
        print(span)
    for span in div.find_all("small", calss_="author"):
        print(span)
    for tag in div.find_all ("a", class_="tag"):

        print(tag)
    print("-------------------------------------------------------------------------------------------------------------------------------------------------------------------------")