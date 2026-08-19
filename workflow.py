"""
workflow.py — Ponto de entrada para GitHub Actions

O disparo do deploy (disparar_deploy_site) agora acontece dentro de
rodar_agente.py, então este arquivo só precisa chamar rodar_artigo()
e/ou rodar_noticia() conforme o --tipo.

Uso:
    python workflow.py --tipo noticia
    python workflow.py --tipo artigo
    python workflow.py --tipo ambos
"""

import argparse
import sys

from rodar_agente import rodar_artigo, rodar_noticia


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa o agente DigitalTech")
    parser.add_argument("--tipo", choices=["noticia", "artigo", "ambos"], default="ambos")
    args = parser.parse_args()

    ok_noticia = True
    ok_artigo = True

    if args.tipo in ("noticia", "ambos"):
        ok_noticia = rodar_noticia()

    if args.tipo in ("artigo", "ambos"):
        ok_artigo = rodar_artigo()

    return 0 if (ok_noticia and ok_artigo) else 1


if __name__ == "__main__":
    sys.exit(main())