"""
scripts/rodar_agente.py — Ponto de entrada para automação via cron local

Gera e publica um artigo e/ou uma notícia por execução. Publica
imediatamente por padrão (PUBLICAR_IMEDIATAMENTE = True) — pensado
pra rodar sem supervisão. Se preferir revisar antes de publicar,
troque PUBLICAR_IMEDIATAMENTE para False abaixo e publique manualmente
depois (POST /artigos/publicar/{id} ou /noticias/publicar/{id}).

rodar_artigo() e rodar_noticia() também são importadas por
pipeline/workflow.py (ponto de entrada do GitHub Actions self-hosted
runner) — é a MESMA lógica pros dois jeitos de disparar o agente, pra
nunca ter dois comportamentos diferentes do mesmo pipeline por estarem
implementados em dois lugares separados.

Uso (linha de comando):
    python -m scripts.rodar_agente --artigo
    python -m scripts.rodar_agente --noticia
    python -m scripts.rodar_agente --artigo --noticia

Cada geração abre suas próprias sessões curtas do banco internamente
(gerar_artigos.py e gerar_noticias.py já cuidam disso) — este script
só abre sessão diretamente para ler os títulos recentes usados como
contexto do sugerir_tema(), e fecha essa sessão logo em seguida.
"""

import argparse
import random
import sys
from datetime import datetime

from config.database import SessionLocal
from agents import pesquisador
from repositories.artigo_repository import ArtigoRepository
from pipeline.gerar_artigos import gerar_e_processar_artigo
from pipeline.gerar_noticias import gerar_e_processar_noticia

PUBLICAR_IMEDIATAMENTE = True

CATEGORIAS_ARTIGOS = [
    "Inteligência Artificial",
    "Programação",
    "Banco de Dados",
    "Cibersegurança",
    "Cloud e DevOps",
    "Desenvolvimento Web",
    "Engenharia de Software",
    "Hardware",
    "Open Source",
    "Carreira",
]


def _log(mensagem: str) -> None:
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{agora}] {mensagem}", flush=True)


def _buscar_temas_recentes(limite: int = 30) -> list[str]:
    """
    Busca os títulos mais recentes no banco para servir de contexto ao
    sugerir_tema() (evita repetir assunto). Protegido por try/except
    porque a assinatura exata de ArtigoRepository.listar_todos() ainda
    não foi confirmada — se ela não aceitar 'limite', ou qualquer outra
    coisa falhar aqui, a geração do artigo não deve travar por causa
    disso, só perde o contexto de "não repita esses temas".
    """
    db = SessionLocal()
    try:
        artigos = ArtigoRepository(db).listar_todos(limite=limite)
        return [a.titulo for a in artigos]
    except TypeError as e:
        _log(f"AVISO: listar_todos() não aceitou 'limite' ({e}) — seguindo sem temas recentes")
        return []
    except Exception as e:
        _log(f"AVISO: falha ao buscar temas recentes ({e}) — seguindo sem temas recentes")
        return []
    finally:
        db.close()


def rodar_artigo(publicar: bool | None = None) -> bool:
    """
    Gera um artigo evergreen. Retorna True em sucesso, False em falha
    real — nunca lança exceção, quem chama decide o que fazer com o
    resultado (ex.: exit code pro cron/GitHub Actions perceber falha).
    """
    publicar_imediatamente = PUBLICAR_IMEDIATAMENTE if publicar is None else publicar
    categoria = random.choice(CATEGORIAS_ARTIGOS)
    temas_recentes = _buscar_temas_recentes(limite=30)

    try:
        tema = pesquisador.sugerir_tema(categoria, temas_recentes=temas_recentes)
    except Exception as e:
        _log(f"FALHA ao sugerir tema: {e}")
        return False

    _log(f"Tema sugerido ({categoria}): {tema}")

    try:
        resultado = gerar_e_processar_artigo(
            tema, categoria, publicar_imediatamente=publicar_imediatamente
        )
        _log(f"Artigo OK: {resultado}")
        return True
    except Exception as e:
        _log(f"FALHA ao gerar artigo: {e}")
        return False


def rodar_noticia(publicar: bool | None = None) -> bool:
    """
    Gera uma notícia via RSS. Retorna True em sucesso — inclusive
    quando não havia nada de novo pra gerar (ValueError esperado do
    pipeline: feeds sem novidade, tudo duplicado etc. — isso não é uma
    falha real, é um estado normal). Só retorna False em erro
    inesperado.
    """
    publicar_imediatamente = PUBLICAR_IMEDIATAMENTE if publicar is None else publicar
    try:
        resultado = gerar_e_processar_noticia(publicar_imediatamente=publicar_imediatamente)
        _log(f"Notícia OK: {resultado}")
        return True
    except ValueError as e:
        _log(f"Sem notícia nova: {e}")
        return True
    except Exception as e:
        _log(f"FALHA ao gerar notícia: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gera artigo e/ou notícia — para uso via cron.")
    parser.add_argument("--artigo", action="store_true", help="Gera um artigo evergreen")
    parser.add_argument("--noticia", action="store_true", help="Gera uma notícia via RSS")
    args = parser.parse_args()

    if not args.artigo and not args.noticia:
        parser.error("Use --artigo, --noticia, ou os dois.")

    ok_artigo = True
    ok_noticia = True

    if args.artigo:
        ok_artigo = rodar_artigo()
    if args.noticia:
        ok_noticia = rodar_noticia()

    sys.exit(0 if (ok_artigo and ok_noticia) else 1)