import requests
url = "https://api.nasa.gov/neo/rest/v1/feed?start_date=2017-09-10&end_date=2017-09-10&api_key=DEMO_KEY"
response = requests.get(url)
dados = response.json()
print(dados)