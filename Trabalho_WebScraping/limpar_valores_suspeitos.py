# -*- coding: utf-8 -*-
"""
Auditoria de valores suspeitos no banco.

Modo:
  python limpar_valores_suspeitos.py            # so lista (dry-run)
  python limpar_valores_suspeitos.py --delete   # apaga os suspeitos
  python limpar_valores_suspeitos.py --null     # zera o valor (mantem registro)
"""
import sys, io, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from sqlalchemy import create_engine, text
from Trabalho_WebScraping import faixa_para  # reaproveita as faixas

USERNAME = "root"
PASSWORD = "OnPc1071!"
HOST     = "localhost"
PORT     = 3306
DATABASE = "imobiliaria"

engine = create_engine(
    f"mysql+pymysql://{USERNAME}:{PASSWORD}@{HOST}:{PORT}/{DATABASE}?charset=utf8mb4"
)

def encontrar_suspeitos():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, modalidade, tipo, valor, bairro, url
            FROM imoveis
            WHERE valor IS NOT NULL
        """)).fetchall()

    suspeitos = []
    for r in rows:
        lo, hi = faixa_para(r.modalidade or "", r.tipo or "")
        if not (lo <= r.valor <= hi):
            suspeitos.append((r, lo, hi))
    return suspeitos

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--delete", action="store_true", help="apaga os registros suspeitos")
    parser.add_argument("--null",   action="store_true", help="zera o campo valor (mantem registro)")
    args = parser.parse_args()

    suspeitos = encontrar_suspeitos()
    print(f"\n{len(suspeitos)} registro(s) suspeito(s) encontrado(s):\n")
    print(f"  {'ID':>6} {'Mod':<8} {'Tipo':<14} {'Valor':>16} {'Faixa esperada':<28} {'Bairro'}")
    print("  " + "-"*100)
    for r, lo, hi in suspeitos:
        faixa = f"[{lo:,} – {hi:,}]"
        print(f"  {r.id:>6} {str(r.modalidade or ''):<8} {str(r.tipo or ''):<14} R$ {r.valor:>13,.2f} {faixa:<28} {r.bairro or ''}")

    if not suspeitos:
        return

    if args.delete:
        ids = [r.id for r, _, _ in suspeitos]
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM imoveis WHERE id IN :ids").bindparams(
                __import__("sqlalchemy").bindparam("ids", expanding=True)
            ), {"ids": ids})
            conn.commit()
        print(f"\n{len(ids)} registro(s) APAGADO(s). Pode rodar o scraper de novo para recoletar.")
    elif args.null:
        ids = [r.id for r, _, _ in suspeitos]
        with engine.connect() as conn:
            conn.execute(text("UPDATE imoveis SET valor = NULL WHERE id IN :ids").bindparams(
                __import__("sqlalchemy").bindparam("ids", expanding=True)
            ), {"ids": ids})
            conn.commit()
        print(f"\n{len(ids)} registro(s) com valor ZERADO.")
    else:
        print("\n(dry-run — use --delete para apagar ou --null para zerar o valor)")

if __name__ == "__main__":
    main()
