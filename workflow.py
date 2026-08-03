"""
workflow.py — Ponto de entrada para GitHub Actions

Compatibilidade: importa e chama rodar_agente.py na raiz.
Mantém os mesmos argumentos --tipo e --sem-publicar para não quebrar
workflows existentes, mas delega toda a lógica para o CLI principal.

Uso:
    python workflow.py                    # notícia + artigo, publica direto
    python workflow.py --tipo noticia     # só notícia
    python workflow.py --tipo artigo      # só artigo
    python workflow.py --sem-publicar     # gera como rascunho
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rodar_agente import _rodar_artigo, _rodar_noticia, _publicar_pendentes, _log


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Executa o agente DigitalTech via GitHub Actions"
    )
    parser.add_argument(
        "--tipo",
        choices=["noticia", "artigo", "ambos"],
        default="ambos",
        help="O que gerar nesta execução (padrão: ambos)",
    )
    parser.add_argument(
        "--sem-publicar",
        action="store_true",
        help="Salva como rascunho em vez de publicar direto",
    )
    args = parser.parse_args()

    publicar = not args.sem_publicar
    ok_noticia = True
    ok_artigo = True

    if args.tipo in ("noticia", "ambos"):
        _log("[Workflow] Executando pipeline de notícias...")
        ok_noticia = _rodar_noticia(publicar=publicar)

    if args.tipo in ("artigo", "ambos"):
        _log("[Workflow] Executando pipeline de artigos...")
        ok_artigo = _rodar_artigo(publicar=publicar)

    # Se estiver publicando, também publica pendentes
    if publicar:
        _log("[Workflow] Verificando rascunhos pendentes...")
        _publicar_pendentes()

    return 0 if (ok_noticia and ok_artigo) else 1


if __name__ == "__main__":
    sys.exit(main())
