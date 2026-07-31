"""
pipeline/gerar_noticias.py — Orquestra o fluxo de NOTÍCIAS

pesquisador (RSS) → EditorChefe (dedup + score, sem LLM) → editor
(reescreve) → revisor → seo → NoticiaRepository (tabela `noticias` —
schema próprio, sem colunas de imagem, categoria é FK)

Reaproveitado tanto pela API (app.py, endpoint POST /noticias/gerar)
quanto por um script de linha de comando (bloco __main__ abaixo).

NÃO recebe `db` de fora. A função abre e fecha sessões CURTAS do banco
só nos momentos que realmente precisa dele (listar títulos existentes,
checar slug duplicado, salvar no final) — nunca durante o trabalho de
LLM (pesquisador → editor → revisor → seo pode levar vários minutos
nesta máquina). Isso evita o erro "SSL connection has been closed
unexpectedly" que o Neon dispara em conexões ociosas por tempo demais.

Sem busca de imagem aqui: a tabela `noticias` não tem nenhuma coluna
pra isso hoje. Sem publicação no GitHub também — isso ainda depende de
decidir se faz sentido pra notícias (github_service.py hoje só sabe
escrever em content/artigos/), então por enquanto "publicar" uma
notícia só muda o status no Neon.
"""

from contextlib import contextmanager

from config.database import SessionLocal
from agents import pesquisador, editor, revisor, seo
from agents.editor_chefe import EditorChefe
from repositories.noticia_repository import NoticiaRepository


@contextmanager
def _sessao_curta():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def gerar_e_processar_noticia(
    categoria: str = "Tecnologia",
    max_tentativas: int = 3,
    publicar_imediatamente: bool = False,
) -> dict:
    candidatos_brutos = pesquisador.pesquisar_noticias()
    if not candidatos_brutos:
        raise ValueError("Nenhuma notícia encontrada nos feeds RSS configurados")

    with _sessao_curta() as db:
        titulos_existentes = NoticiaRepository(db).listar_titulos_recentes(limite=100)

    editor_chefe = EditorChefe()
    pauta = editor_chefe.montar_pauta(candidatos_brutos, categoria, titulos_existentes=titulos_existentes)

    if not pauta:
        raise ValueError("Todas as notícias encontradas já foram publicadas ou são duplicadas entre si")

    artigo = None
    item_escolhido = None

    for item in pauta[:max_tentativas]:
        candidato_artigo = editor.gerar_noticia_base(
            {"titulo": item.titulo, "resumo": item.resumo, "fonte": item.fonte, "link": item.link},
            categoria=categoria,
        )

        with _sessao_curta() as db:
            ja_existe = NoticiaRepository(db).buscar_por_slug(candidato_artigo["slug"])

        if ja_existe:
            print(f"[Pipeline] '{item.titulo}' já publicada (slug duplicado), tentando a próxima da pauta.")
            continue

        artigo = candidato_artigo
        item_escolhido = item
        break

    if artigo is None:
        raise ValueError("Todos os itens tentados da pauta já foram publicados antes")

    artigo = revisor.revisar_artigo(artigo)
    artigo = seo.otimizar_seo(artigo)

    with _sessao_curta() as db:
        repo = NoticiaRepository(db)
        noticia_id = repo.criar(
            slug=artigo["slug"],
            titulo=artigo.get("titulo_seo") or artigo["titulo"],
            categoria=categoria,
            resumo=artigo.get("meta_description") or artigo.get("excerpt", ""),
            conteudo=artigo["conteudo_markdown"],
            fonte=item_escolhido.fonte,
            url_fonte=item_escolhido.link,
            status="rascunho",
        )

        resultado = {
            "id": noticia_id,
            "slug": artigo["slug"],
            "titulo": artigo["titulo"],
            "categoria": categoria,
            "status": "rascunho",
            "prioridade": item_escolhido.prioridade,
            "score": item_escolhido.score,
            "fonte_original": item_escolhido.link,
        }

        if publicar_imediatamente:
            repo.publicar(noticia_id)
            resultado["status"] = "publicado"

    return resultado


if __name__ == "__main__":
    resultado = gerar_e_processar_noticia()
    print(f"Notícia salva: {resultado}")
