# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from sqlalchemy import create_engine, text

USERNAME = "root"
PASSWORD = "OnPc1071!"
HOST     = "localhost"
PORT     = 3306
DATABASE = "imobiliaria"

engine = create_engine(f"mysql+pymysql://{USERNAME}:{PASSWORD}@{HOST}:{PORT}/{DATABASE}")

with engine.connect() as conn:
    # Total de registros
    total = conn.execute(text("SELECT COUNT(*) FROM imoveis")).scalar()
    print(f"\nTotal de imoveis no banco: {total}")

    # Resumo por tipo
    print("\n--- Por tipo ---")
    for row in conn.execute(text("SELECT tipo, COUNT(*) as qtd FROM imoveis GROUP BY tipo ORDER BY qtd DESC")):
        print(f"  {row[0]:20} {row[1]} imoveis")

    # Resumo por modalidade
    print("\n--- Por modalidade ---")
    for row in conn.execute(text("SELECT modalidade, COUNT(*) as qtd FROM imoveis GROUP BY modalidade")):
        print(f"  {row[0]:10} {row[1]} imoveis")

    # Resumo por data de coleta
    print("\n--- Por data de coleta ---")
    for row in conn.execute(text("SELECT data_coleta, COUNT(*) as qtd FROM imoveis GROUP BY data_coleta ORDER BY data_coleta DESC")):
        print(f"  {str(row[0]):12} {row[1]} imoveis")

    # Ultimos 10 coletados
    print("\n--- Ultimos 10 coletados ---")
    rows = conn.execute(text("""
        SELECT data_coleta, tipo, modalidade, valor, bairro, cidade
        FROM imoveis
        ORDER BY id DESC
        LIMIT 10
    """))
    print(f"  {'Data':<12} {'Tipo':<15} {'Modal':<8} {'Valor':>15}  {'Bairro'}")
    print("  " + "-"*75)
    for row in rows:
        valor_fmt = f"R$ {row[3]:,.2f}" if row[3] else "N/A"
        print(f"  {str(row[0]):<12} {str(row[1]):<15} {str(row[2]):<8} {valor_fmt:>15}  {row[4]}")

    # Estatisticas de valor
    print("\n--- Estatisticas de valor (venda) ---")
    stats = conn.execute(text("""
        SELECT
            MIN(valor)  as minimo,
            MAX(valor)  as maximo,
            AVG(valor)  as media
        FROM imoveis
        WHERE modalidade = 'venda' AND valor IS NOT NULL
    """)).fetchone()
    if stats and stats[0]:
        print(f"  Minimo : R$ {stats[0]:,.2f}")
        print(f"  Maximo : R$ {stats[1]:,.2f}")
        print(f"  Media  : R$ {stats[2]:,.2f}")