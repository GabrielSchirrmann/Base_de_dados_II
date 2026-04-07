from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import time
import re


# ORM
from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, insert, Double

# ── Configuração do banco ──────────────────────────────────────────────────────
username = "root"
password = "OnPc1071!"
host = "localhost"
port = 3306
database = "imobiliaria"

connection_string = f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"
engine = create_engine(connection_string)

metadata = MetaData()

imovel = Table(
    "imoveis", metadata,
    Column("id", Integer, primary_key=True),
    Column("titulo", String(255)),
    Column("endereco", String(255)),
    Column("area_util", String(50)),
    Column("quartos", Integer),
    Column("banheiros", Integer),
    Column("valor", Double)
)

# Cria a tabela no banco se ainda não existir
metadata.create_all(engine)

# ── Função de limpeza do preço ─────────────────────────────────────────────────
def limpar_preco(preco):
    valor = re.sub(r'R\$\s*', '', preco)
    valor = re.sub(r'\.', '', valor)
    valor = re.sub(r',', '.', valor)
    valor = valor.strip()
    try:
        return float(valor)
    except ValueError:
        return None

# ── Função de persistência ─────────────────────────────────────────────────────
def persistir_dados(titulo, endereco, area_util, quartos, banheiros, preco):
    valor = limpar_preco(preco)
    if valor is None:
        print(f"Preço inválido para '{titulo}', pulando...")
        return

    novo_imovel = {
        "titulo": titulo,
        "endereco": endereco,
        "area_util": area_util,
        "quartos": quartos,
        "banheiros": banheiros,
        "valor": valor
    }

    with engine.connect() as conexao:
        comando = insert(imovel).values(novo_imovel)
        conexao.execute(comando)
        conexao.commit()
    print(f"Salvo: {titulo[:50]} | R$ {valor:,.2f}")

# ── Função de coleta dos cards ─────────────────────────────────────────────────
ids_coletados = set()  # evita duplicatas ao fazer scroll

def coletar(driver):
    cards = driver.find_elements(By.TAG_NAME, "article")
    novos = 0

    for card in cards:
        try:
            # ID único do card para evitar duplicata
            card_id = card.id
            if card_id in ids_coletados:
                continue
            ids_coletados.add(card_id)

            titulo   = card.find_element(By.TAG_NAME, "h2").text.strip()
            endereco = card.find_element(By.TAG_NAME, "address").text.strip()
            preco    = card.find_element(By.TAG_NAME, "h3").text.strip()

            # Itens da lista: área, quartos, banheiros
            itens = card.find_elements(By.TAG_NAME, "li")
            area_util = itens[0].text.strip() if len(itens) > 0 else "N/A"
            quartos   = int(re.sub(r'\D', '', itens[1].text)) if len(itens) > 1 else 0
            banheiros = int(re.sub(r'\D', '', itens[2].text)) if len(itens) > 2 else 0

            persistir_dados(titulo, endereco, area_util, quartos, banheiros, preco)
            novos += 1

        except Exception as e:
            print(f"Erro ao processar card: {e}")

    return novos

# ── Scroll infinito ────────────────────────────────────────────────────────────
def scroll_ate_o_fim(driver):
    ultima_altura = driver.execute_script("return document.body.scrollHeight")

    while True:
        # Rola até o final da página
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)  # aguarda novos itens carregarem

        # Coleta os cards visíveis
        coletar(driver)

        # Verifica se a página cresceu
        nova_altura = driver.execute_script("return document.body.scrollHeight")
        if nova_altura == ultima_altura:
            print("Fim da página atingido!")
            break
        ultima_altura = nova_altura

# ── Main ───────────────────────────────────────────────────────────────────────
from webdriver_manager.chrome import ChromeDriverManager

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service)

try:
    driver.get("https://www.metaimobiliariasinop.com.br/imoveis/a-venda/brasil?order=maior_preco")
    time.sleep(3)  # aguarda o carregamento inicial

    print("Iniciando coleta com scroll...")
    scroll_ate_o_fim(driver)
    print("Coleta finalizada!")

finally:
    driver.quit()
