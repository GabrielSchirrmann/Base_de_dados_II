# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time, re
from datetime import date

from sqlalchemy import (create_engine, Table, Column, Integer, String,
                        MetaData, insert, Float, Date, Text, text)
from webdriver_manager.chrome import ChromeDriverManager

# ── Banco de dados ─────────────────────────────────────────────────────────────
USERNAME = "root"
PASSWORD = "OnPc1071!"
HOST     = "localhost"
PORT     = 3306
DATABASE = "imobiliaria"

engine = create_engine(
    f"mysql+pymysql://{USERNAME}:{PASSWORD}@{HOST}:{PORT}/{DATABASE}?charset=utf8mb4"
)
metadata = MetaData()

imovel = Table(
    "imoveis", metadata,
    Column("id",                       Integer, primary_key=True, autoincrement=True),
    Column("data_coleta",              Date),
    Column("descricao",                Text),
    Column("cidade",                   String(100)),
    Column("rua",                      String(255)),
    Column("bairro",                   String(150)),
    Column("cep",                      String(20)),
    Column("numero",                   String(20)),
    Column("area_total",               String(50)),
    Column("area_construida",          String(50)),
    Column("valor",                    Float),
    Column("modalidade",               String(20)),
    Column("tipo",                     String(50)),
    Column("finalidade",               String(30)),
    Column("utilizacao",               String(20)),
    Column("quantidade_suites",        Integer),
    Column("quantidade_quartos",       Integer),
    Column("quantidade_banheiros",     Integer),
    Column("quantidade_vagas",         Integer),
    Column("quantidade_salas",         Integer),
    Column("quantidade_cozinhas",      Integer),
    Column("quantidade_churrasqueira", Integer),
    Column("quantidade_escritorio",    Integer),
    Column("url",                      String(500)),
)
metadata.create_all(engine)

# ── URLs ja salvas ─────────────────────────────────────────────────────────────
def urls_ja_coletadas() -> set:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT url FROM imoveis WHERE url IS NOT NULL"))
        return {r[0] for r in rows}

# ── Helpers ────────────────────────────────────────────────────────────────────
def limpar_preco(texto: str):
    v = re.sub(r'[R$\s\.]', '', texto)
    v = v.replace(',', '.')
    try:
        return float(v)
    except ValueError:
        return None

def extrair_int(texto: str) -> int:
    m = re.search(r'\d+', texto)
    return int(m.group()) if m else 0

def tipo_da_url(url: str) -> str:
    m = re.search(r'/imovel/([^/]+)/', url)
    return m.group(1) if m else "outro"

def modalidade_da_url(url: str) -> str:
    if "/venda/" in url:
        return "venda"
    if "/aluguel/" in url or "/locacao/" in url:
        return "aluguel"
    return ""

def finalidade(tipo: str, descricao: str) -> str:
    comerciais = ["sala", "galpao", "galpao", "barracao", "loja", "escritorio", "comercial"]
    texto = (tipo + " " + descricao).lower()
    return "comercial" if any(p in texto for p in comerciais) else "residencial"

def extrair_m2(texto: str) -> str:
    m = re.search(r'[\d.,]+\s*m[2²]', texto, re.IGNORECASE)
    return m.group().strip() if m else ""

# ── Coleta da pagina de DETALHE ────────────────────────────────────────────────
def coletar_detalhe(driver, url: str):
    try:
        driver.get(url)
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
        time.sleep(1.5)

        # Clica em "Ver mais" para expandir descricao, se existir
        try:
            ver_mais = driver.find_element(
                By.CSS_SELECTOR, "span.Descricao_seeMoreOrSeeLessStyle__xliQm"
            )
            driver.execute_script("arguments[0].click();", ver_mais)
            time.sleep(0.5)
        except Exception:
            pass

        # ── Descricao (id=description) ──
        try:
            descricao_el = driver.find_element(By.ID, "description")
            descricao = descricao_el.text.strip()
        except Exception:
            try:
                descricao = driver.find_element(By.TAG_NAME, "h1").text.strip()
            except Exception:
                descricao = ""

        # ── Endereco ──
        try:
            endereco_raw = driver.find_element(By.TAG_NAME, "address").text.strip()
        except Exception:
            endereco_raw = ""

        partes = [p.strip() for p in re.split(r'\s*[-,]\s*', endereco_raw)]
        rua    = partes[0] if partes else ""
        if len(partes) > 1 and re.match(r'^\d', partes[1]):
            numero    = partes[1]
            bairro    = partes[2] if len(partes) > 2 else ""
            cidade_uf = partes[3] if len(partes) > 3 else ""
        else:
            numero    = ""
            bairro    = partes[1] if len(partes) > 1 else ""
            cidade_uf = partes[2] if len(partes) > 2 else ""
        cidade = re.split(r'[/\-]', cidade_uf)[0].strip()
        cep    = ""
        m = re.search(r'\d{5}-?\d{3}', endereco_raw)
        if m:
            cep = m.group()

        # ── Areas: badges estruturados (ex: "444 m² total", "333 m² útil") ──
        area_total      = ""
        area_construida = ""
        # Busca nos elementos de badge de area
        try:
            badges = driver.find_elements(By.CSS_SELECTOR, "ul.Icons_list__SlDEy li")
            for badge in badges:
                txt = badge.text.strip().lower()
                if "m²" in txt or "m2" in txt:
                    val = extrair_m2(badge.text)
                    label_el = badge.find_elements(By.TAG_NAME, "span")
                    label = badge.text.lower()
                    if "útil" in label or "util" in label:
                        area_construida = val
                    elif "total" in label or "terreno" in label:
                        area_total = val
                    elif not area_construida:
                        area_construida = val
        except Exception:
            pass

        # Fallback: busca no texto da descricao
        if not area_total or not area_construida:
            for trecho in re.findall(r'[\d.,]+\s*m[²2][^\n]*', descricao, re.IGNORECASE):
                t = trecho.lower()
                if ("total" in t or "terreno" in t) and not area_total:
                    area_total = extrair_m2(trecho)
                elif ("util" in t or "construid" in t or "casa" in t) and not area_construida:
                    area_construida = extrair_m2(trecho)

        # ── Quartos / suites / banheiros / vagas dos badges + descricao ──
        body = driver.find_element(By.TAG_NAME, "body").text

        def buscar_num(padrao):
            m = re.search(padrao, body, re.IGNORECASE)
            return extrair_int(m.group()) if m else 0

        quartos   = buscar_num(r'(\d+)\s*quarto')
        suites    = buscar_num(r'(\d+)\s*su[ií]te')
        banheiros = buscar_num(r'(\d+)\s*banheiro')
        vagas     = buscar_num(r'(\d+)\s*vaga')

        # ── Comodidades ──
        comodidades = []
        try:
            els = driver.find_elements(By.CSS_SELECTOR, "div.Comodidades_amenities__8NeB3 span, ul li")
            comodidades = [e.text.strip().lower() for e in els if e.text.strip()]
        except Exception:
            pass

        def tem(*palavras):
            return int(any(p in c for c in comodidades for p in palavras))

        salas         = tem("sala de estar", "sala de tv", "sala de jantar")
        cozinhas      = tem("cozinha", "gourmet")
        churrasqueira = tem("churrasqueira")
        escritorio    = tem("escritorio", "escritório")

        # ── Preco ──
        valor = None
        m = re.search(r'R\$[\s\xa0]*([\d.,]+)', body)
        if m:
            valor = limpar_preco("R$ " + m.group(1))

        tipo_imovel = tipo_da_url(url)
        modalidade  = modalidade_da_url(url)

        return {
            "data_coleta":              date.today(),
            "descricao":                descricao[:5000] if descricao else "",
            "cidade":                   cidade,
            "rua":                      rua,
            "bairro":                   bairro,
            "cep":                      cep,
            "numero":                   numero,
            "area_total":               area_total,
            "area_construida":          area_construida,
            "valor":                    valor,
            "modalidade":               modalidade,
            "tipo":                     tipo_imovel,
            "finalidade":               finalidade(tipo_imovel, descricao),
            "utilizacao":               "",
            "quantidade_suites":        suites,
            "quantidade_quartos":       quartos,
            "quantidade_banheiros":     banheiros,
            "quantidade_vagas":         vagas,
            "quantidade_salas":         salas,
            "quantidade_cozinhas":      cozinhas,
            "quantidade_churrasqueira": churrasqueira,
            "quantidade_escritorio":    escritorio,
            "url":                      url,
        }

    except Exception as e:
        print(f"  ERRO detalhe {url}: {e}")
        return None

# ── Persistencia ───────────────────────────────────────────────────────────────
def persistir(dados: dict):
    if dados.get("valor") is None:
        print(f"  [SKIP] sem preco: {dados.get('url','')[-40:]}")
        return
    with engine.connect() as conn:
        conn.execute(insert(imovel).values(dados))
        conn.commit()
    tipo  = str(dados.get('tipo', ''))[:12]
    valor = dados['valor']
    bairro = str(dados.get('bairro', ''))[:30]
    print(f"  [OK] {tipo:<12} R${valor:>14,.2f}  {bairro}")

# ── Coleta de links na listagem (scroll suave) ─────────────────────────────────
def coletar_links(driver) -> list:
    links = set()
    posicao = 0
    PASSO     = 150
    INTERVALO = 0.06

    print("  Scroll na listagem...")

    while True:
        posicao += PASSO
        driver.execute_script(f"window.scrollTo(0, {posicao});")
        time.sleep(INTERVALO)

        for el in driver.find_elements(By.TAG_NAME, "a"):
            try:
                href = el.get_attribute("href")
                if href and "/imovel/" in href and "_META" in href:
                    links.add(href.split("?")[0])
            except Exception:
                pass

        altura = driver.execute_script("return document.body.scrollHeight")
        if posicao >= altura:
            time.sleep(2)
            if driver.execute_script("return document.body.scrollHeight") == altura:
                print(f"  Fim da listagem. {len(links)} links coletados.")
                break

    return list(links)

# ── URLs a coletar ─────────────────────────────────────────────────────────────
URLS_LISTAGEM = [
    "https://www.metaimobiliariasinop.com.br/imoveis/a-venda/brasil?order=maior_preco",
    # "https://www.metaimobiliariasinop.com.br/imoveis/aluguel/brasil?order=maior_preco",
]

# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")

    driver = webdriver.Chrome(service=service, options=options)

    try:
        ja_coletados = urls_ja_coletadas()
        print(f"URLs ja no banco: {len(ja_coletados)}")

        for url_listagem in URLS_LISTAGEM:
            print(f"\n{'='*60}")
            print(f"Listagem: {url_listagem}")
            print('='*60)

            driver.get(url_listagem)
            time.sleep(3)

            links = coletar_links(driver)
            novos = [l for l in links if l not in ja_coletados]
            print(f"  Novos para coletar hoje: {len(novos)}")

            for i, link in enumerate(novos, 1):
                print(f"  [{i}/{len(novos)}] {link[-50:]}")
                dados = coletar_detalhe(driver, link)
                if dados:
                    persistir(dados)
                time.sleep(1.5)

        print("\nColeta finalizada!")

    finally:
        driver.quit()