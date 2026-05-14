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
                        MetaData, insert, Float, Date, Text, text,
                        UniqueConstraint)
from sqlalchemy.exc import IntegrityError
from webdriver_manager.chrome import ChromeDriverManager

# ── Banco de dados ─────────────────────────────────────────────────────────────
USERNAME = "root"
PASSWORD = "OnPc1071!"
HOST     = "localhost"
PORT     = 3306
DATABASE = "imobiliaria"

# Cria o banco automaticamente se nao existir
_bootstrap = create_engine(
    f"mysql+pymysql://{USERNAME}:{PASSWORD}@{HOST}:{PORT}/?charset=utf8mb4"
)
with _bootstrap.connect() as _c:
    _c.execute(text(
        f"CREATE DATABASE IF NOT EXISTS {DATABASE} "
        f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    ))
    _c.commit()
_bootstrap.dispose()

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
    UniqueConstraint("url", name="uq_imoveis_url"),
)
metadata.create_all(engine)

# Garante o índice único em bancos antigos criados antes do UniqueConstraint.
with engine.connect() as _conn:
    try:
        _conn.execute(text(
            "ALTER TABLE imoveis ADD CONSTRAINT uq_imoveis_url UNIQUE (url)"
        ))
        _conn.commit()
    except Exception:
        pass  # já existe, ignora

# ── URLs ja salvas ─────────────────────────────────────────────────────────────
def urls_ja_coletadas() -> set:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT url FROM imoveis WHERE url IS NOT NULL"))
        return {r[0] for r in rows}

# ── Helpers ────────────────────────────────────────────────────────────────────
def limpar_preco(texto: str):
    v = re.sub(r'[R$\s\xa0\.]', '', texto)
    v = v.replace(',', '.')
    try:
        return float(v)
    except ValueError:
        return None

# Faixas plausiveis (R$). Fora disso o valor e descartado.
FAIXAS_VALOR = {
    # modalidade -> tipo -> (min, max)
    "venda": {
        "casa":        (50_000,    20_000_000),
        "apartamento": (50_000,    20_000_000),
        "kitnet":      (40_000,     2_000_000),
        "terreno":     (20_000,    30_000_000),
        "sala":        (30_000,    10_000_000),
        "galpao":      (80_000,    50_000_000),
        "barracao":    (80_000,    50_000_000),
        "loja":        (50_000,    20_000_000),
        "*":           (20_000,    50_000_000),  # fallback
    },
    "aluguel": {
        "casa":        (300,        50_000),
        "apartamento": (300,        30_000),
        "kitnet":      (200,        10_000),
        "terreno":     (200,        50_000),
        "sala":        (300,        50_000),
        "galpao":      (500,       200_000),
        "barracao":    (500,       200_000),
        "loja":        (300,       100_000),
        "*":           (200,       200_000),
    },
}

def faixa_para(modalidade: str, tipo: str):
    mod = FAIXAS_VALOR.get(modalidade, {})
    return mod.get(tipo) or mod.get("*") or (1, 1_000_000_000)

def coletar_todos_precos(body: str) -> list:
    """Extrai todos os R$ do body e devolve floats validos."""
    valores = []
    for raw in re.findall(r'R\$[\s\xa0]*[\d.,]+', body):
        # so aceita formatos com pelo menos um separador (descarta "R$ 1")
        if not re.search(r'\d', raw):
            continue
        v = limpar_preco(raw)
        if v is None or v <= 0:
            continue
        valores.append(v)
    return valores

def _preco_de_itemprop(el) -> float:
    """
    Extrai preco de um elemento [itemprop="price"].
    Tenta o atributo 'content' (sempre limpo, ex: '4500000.00') e cai pro
    text() ('R$ 4.500.000,00') se nao tiver.
    """
    try:
        # 1) Atributo content e o mais confiavel — Schema.org usa decimal point
        content = (el.get_attribute("content") or "").strip()
        if content:
            try:
                return float(content)
            except ValueError:
                pass
        # 2) Fallback: parseia o texto visivel
        txt = (el.text or el.get_attribute("innerText") or "").strip()
        if txt:
            return limpar_preco(txt)
    except Exception:
        return None
    return None

def escolher_preco(driver, body: str, modalidade: str, tipo: str):
    """
    Estrategia (em ordem de confianca):
      1. <span itemprop="price"> dentro do container [itemprop="offers"]
         (Schema.org — é o preco canonico DESTE imovel, nao de imoveis relacionados)
      2. Outros [itemprop="price"] na pagina principal
      3. Seletores de classe (Prices_colorOfValue, etc.)
      4. Fallback final: maior R$ do body dentro da faixa plausivel
    """
    lo, hi = faixa_para(modalidade, tipo)

    # 1) PRIORIDADE MAXIMA: [itemprop="offers"] [itemprop="price"]
    # Esse e o preco canonico do imovel. Imoveis relacionados (rodape) ficam
    # fora deste container, entao nao ha risco de embaralhamento.
    try:
        for offer in driver.find_elements(By.CSS_SELECTOR, '[itemprop="offers"]'):
            for price_el in offer.find_elements(By.CSS_SELECTOR, '[itemprop="price"]'):
                v = _preco_de_itemprop(price_el)
                if v and v > 0:
                    # Mesmo se cair fora da faixa, esse preco vem do schema.org
                    # do proprio imovel — confiamos nele e deixamos a validacao
                    # de faixa rejeitar depois (em persistir()).
                    return v
    except Exception:
        pass

    # 2) [itemprop="price"] solto, mas no TOPO da pagina (antes da secao "similares")
    try:
        candidatos = driver.find_elements(By.CSS_SELECTOR, '[itemprop="price"]')
        if candidatos:
            v = _preco_de_itemprop(candidatos[0])
            if v and v > 0:
                return v
    except Exception:
        pass

    # 3) Seletores de classe especificos (ex: Prices_colorOfValue__SBuQZ)
    for css in [
        "span.Prices_colorOfValue__SBuQZ",
        "[class*='Prices_colorOfValue']",
        "[class*='Preco_price']",
        "[class*='Price_price']",
        "[class*='preco-principal']",
    ]:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, css):
                txt = (el.text or "").strip()
                if not txt or "R$" not in txt:
                    continue
                t_low = txt.lower()
                if any(p in t_low for p in ("condom", "iptu", "taxa", "/m", "por m")):
                    continue
                m = re.search(r'R\$[\s\xa0]*([\d.,]+)', txt)
                if not m:
                    continue
                v = limpar_preco("R$ " + m.group(1))
                if v and lo <= v <= hi:
                    return v
        except Exception:
            continue

    # 4) Fallback final: NAO usamos mais "max" do body porque a pagina inclui
    # imoveis similares no rodape (cada um com seu R$), e isso causava
    # embaralhamento — pegava o preco de OUTRO anuncio.
    # Preferimos retornar None e descartar o registro (ou re-coletar depois)
    # a salvar um valor errado.
    print(f"  [WARN] sem [itemprop=price] confiavel; descartando preco.")
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

def codigo_do_imovel(url: str) -> str:
    """Extrai o identificador unico do imovel da URL (ex: SO0001_META)."""
    m = re.search(r'/([A-Z0-9]+_META)/?', url, re.IGNORECASE)
    return m.group(1).upper() if m else ""

# ── Coleta da pagina de DETALHE ────────────────────────────────────────────────
def coletar_detalhe(driver, url: str):
    try:
        codigo = codigo_do_imovel(url)

        # Limpa o DOM anterior antes de navegar (evita ler dados velhos)
        try:
            driver.get("about:blank")
        except Exception:
            pass

        driver.get(url)

        # Espera 1: a URL atual precisa bater com o que pedimos
        try:
            WebDriverWait(driver, 12).until(
                lambda d: codigo and codigo.upper() in d.current_url.upper()
            )
        except Exception:
            print(f"  [SKIP integridade] URL nao confere apos navegar: {url[-50:]}")
            return None

        # Espera 2: o h1 precisa estar carregado
        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.TAG_NAME, "h1"))
            )
        except Exception:
            print(f"  [SKIP integridade] sem h1: {url[-50:]}")
            return None

        time.sleep(1.5)

        # Espera 3: o codigo do imovel precisa aparecer na pagina (sanity check)
        try:
            body_inicial = driver.find_element(By.TAG_NAME, "body").text
            if codigo and codigo.upper() not in body_inicial.upper():
                # As vezes o codigo aparece so na url ou em meta tags — nao e fatal,
                # mas exigimos pelo menos que a URL atual contenha o codigo (ja validado).
                pass
        except Exception:
            pass

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

        tipo_imovel = tipo_da_url(url)
        modalidade  = modalidade_da_url(url)

        # ── Preco (estrategia robusta) ──
        valor = escolher_preco(driver, body, modalidade, tipo_imovel)

        # ── CHECAGEM FINAL DE INTEGRIDADE ──
        # Garante que o navegador ainda esta na pagina certa (nao houve redirect
        # silencioso ou navegacao em meio a coleta, o que embaralharia os dados).
        try:
            url_atual = driver.current_url
        except Exception:
            url_atual = ""
        if codigo and codigo.upper() not in url_atual.upper():
            print(f"  [SKIP integridade] navegou no meio da coleta: {url[-50:]} -> {url_atual[-50:]}")
            return None

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
    # Validacao de faixa: descarta precos absurdos
    lo, hi = faixa_para(dados.get("modalidade", ""), dados.get("tipo", ""))
    v = dados["valor"]
    if not (lo <= v <= hi):
        print(f"  [SKIP] valor fora da faixa ({v:,.2f} ∉ [{lo:,}, {hi:,}]): {dados.get('url','')[-40:]}")
        return
    url = dados.get("url")
    with engine.connect() as conn:
        # Defesa extra: confere por URL antes de inserir (race-conditions / re-runs)
        existe = conn.execute(
            text("SELECT 1 FROM imoveis WHERE url = :u LIMIT 1"), {"u": url}
        ).scalar()
        if existe:
            print(f"  [DUP] ja existe: {str(url)[-40:]}")
            return
        try:
            conn.execute(insert(imovel).values(dados))
            conn.commit()
        except IntegrityError:
            conn.rollback()
            print(f"  [DUP] integrity: {str(url)[-40:]}")
            return
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
    "https://www.metaimobiliariasinop.com.br/imoveis/aluguel/brasil?order=maior_preco",
]

# Cache em disco (caso a fase 2 caia, nao precisa re-scrollar tudo)
import os, json
CACHE_LINKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "links_coletados.json")

def coletar_todos_links(driver) -> list:
    """FASE 1 — passa por todas as listagens e devolve a uniao dos links."""
    todos = set()
    for i, url_listagem in enumerate(URLS_LISTAGEM, 1):
        print(f"\n[FASE 1] ({i}/{len(URLS_LISTAGEM)}) Listagem: {url_listagem}")
        driver.get(url_listagem)
        time.sleep(3)
        links = coletar_links(driver)
        print(f"  -> {len(links)} links nesta listagem.")
        todos.update(links)

    todos = sorted(todos)
    # Persiste em disco
    try:
        with open(CACHE_LINKS, "w", encoding="utf-8") as fp:
            json.dump(todos, fp, ensure_ascii=False, indent=2)
        print(f"\n[FASE 1] {len(todos)} link(s) unicos salvos em {CACHE_LINKS}")
    except Exception as e:
        print(f"[FASE 1] aviso: nao consegui salvar cache: {e}")
    return todos

def carregar_links_cache() -> list:
    if not os.path.exists(CACHE_LINKS):
        return []
    try:
        with open(CACHE_LINKS, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return []

# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    service = Service(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    # options.add_argument("--headless")

    driver = webdriver.Chrome(service=service, options=options)

    # Flags por linha de comando:
    #   --fase1       : so coleta os links e salva em disco
    #   --fase2       : pula a coleta de listagens e usa o cache
    #   (sem flags)   : roda fase 1 + fase 2 em sequencia
    args = set(sys.argv[1:])
    so_fase1 = "--fase1" in args
    so_fase2 = "--fase2" in args

    try:
        # ============== FASE 1 — coletar todos os links ==============
        if so_fase2:
            todos_links = carregar_links_cache()
            print(f"[FASE 2] Carregando {len(todos_links)} link(s) do cache.")
        else:
            print("="*60)
            print("FASE 1 — Coletando links das listagens")
            print("="*60)
            todos_links = coletar_todos_links(driver)

        if so_fase1:
            print("\n[--fase1] Concluido. Cache salvo em links_coletados.json")
            sys.exit(0)

        # ============== FASE 2 — visitar cada link ==============
        print("\n" + "="*60)
        print("FASE 2 — Coletando detalhes de cada imovel")
        print("="*60)

        ja_coletados = urls_ja_coletadas()
        print(f"URLs ja no banco: {len(ja_coletados)}")

        novos = [l for l in todos_links if l not in ja_coletados]
        print(f"Novos para coletar hoje: {len(novos)} (de {len(todos_links)} totais)")

        for i, link in enumerate(novos, 1):
            print(f"\n[{i}/{len(novos)}] {link}")
            dados = coletar_detalhe(driver, link)
            if dados:
                persistir(dados)
            time.sleep(1.5)

        print("\nColeta finalizada!")

    finally:
        driver.quit()