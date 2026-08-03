"""
workflow.py — Ponto de entrada para GitHub Actions

Compatível com rodar_agente.py v3.
Mantém argumentos --tipo e --sem-publicar.
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rodar_agente import _rodar_artigo, _rodar_noticia, _publicar_pendentes, _log


def main() -> int:
    parser = argparse.ArgumentParser(description="Agente DigitalTech — GitHub Actions")
    parser.add_argument("--tipo", choices=["noticia", "artigo", "ambos"], default="ambos")
    parser.add_argument("--sem-publicar", action="store_true", help="Salva como rascunho")
    args = parser.parse_args()

    publicar = not args.sem_publicar
    ok_noticia = True
    ok_artigo = True

    if args.tipo in ("noticia", "ambos"):
        _log("[Workflow] Pipeline de notícias...")
        ok_noticia = _rodar_noticia(publicar=publicar)

    if args.tipo in ("artigo", "ambos"):
        _log("[Workflow] Pipeline de artigos...")
        ok_artigo = _rodar_artigo(publicar=publicar)

    if publicar:
        _log("[Workflow] Verificando rascunhos...")
        _publicar_pendentes()

    return 0 if (ok_noticia and ok_artigo) else 1


if __name__ == "__main__":
    sys.exit(main())
