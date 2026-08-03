"""
pipeline/workflow.py — Ponto de entrada para o self-hosted runner do
GitHub Actions

Não reimplementa a geração de artigo/notícia — importa e chama
rodar_artigo()/rodar_noticia() de scripts/rodar_agente.py, a MESMA
lógica usada pelo cron local (sugestão de tema via LLM, sessões
curtas, mesmo tratamento de erro). Existe como arquivo separado só
para dar um ponto de entrada com nome claro dentro dos workflows do
GitHub Actions (fica mais fácil de achar nos logs do Actions) e para
aceitar --tipo/--sem-publicar, que fazem mais sentido num
workflow_dispatch com inputs do que os --artigo/--noticia do script
de cron.

IMPORTANTE: se precisar mudar como o tema é escolhido, como as sessões
do banco são abertas, etc., mude em scripts/rodar_agente.py — este
arquivo não deve ganhar lógica própria. A versão anterior deste
arquivo usava uma lista BACKLOG_TEMAS com índice salvo em
.backlog_state.json — isso foi removido porque o actions/checkout
(comportamento padrão: clean=true) apaga esse arquivo a cada execução,
o que travava o índice sempre em 0 e fazia o agente tentar gerar o
mesmo tema repetidas vezes. sugerir_tema() não tem esse problema
porque consulta o histórico direto no Neon, que persiste de verdade
entre execuções.

Uso:
    python -m pipeline.workflow                  # notícia + artigo, publica direto
    python -m pipeline.workflow --tipo noticia    # só notícia
    python -m pipeline.workflow --tipo artigo     # só artigo
    python -m pipeline.workflow --sem-publicar    # gera como rascunho, sem publicar
"""

import argparse
import sys

from scripts.rodar_agente import rodar_artigo, rodar_noticia


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Executa o agente DigitalTech via GitHub Actions self-hosted runner"
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
        ok_noticia = rodar_noticia(publicar=publicar)

    if args.tipo in ("artigo", "ambos"):
        ok_artigo = rodar_artigo(publicar=publicar)

    return 0 if (ok_noticia and ok_artigo) else 1


if __name__ == "__main__":
    sys.exit(main())