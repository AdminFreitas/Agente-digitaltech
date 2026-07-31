"""
pipeline/gerar_noticias.py — Orquestra o fluxo de NOTÍCIAS

pesquisador (RSS) → EditorChefe (dedup + score, sem LLM) → editor
(reescreve) → revisor → seo → NoticiaRepository (tabela `noticias` —
schema próprio, sem colunas de imagem, categoria é FK)

Reaproveitado tanto pela API (app.py, endpoint POST /noticias/gerar)
quanto por um script de linha de comando (bloco __main__ abaixo).

Sem busca de imagem aqui: a tabela `noticias` não tem nenhuma coluna
pra isso hoje. Sem publicação no GitHub também — isso ainda depende de
decidir se faz sentido pra notícias (github_service.py hoje só sabe
escrever em content/artigos/), então por enquanto "publicar" uma
notícia só muda o status no Neon, igual ao Agente B parece fazer.
"""

from sqlalchemy.orm import Session

from agents import pesquisador, editor, revisor, seo
from agents.editor_chefe import EditorChefe
from repositories.noticia_repository import NoticiaRepository


def gerar_e_processar_noticia(
    db: Session,
    categoria: str = "Tecnologia",
    max_tentativas: int = 3,
    publicar_imediatamente: bool = False,
) -> dict:
    """
    Busca notícias recentes via RSS, usa o EditorChefe pra descartar
    duplicadas (entre os candidatos e contra o que já está salvo em
    `noticias`) e priorizar, e roda a cadeia completa para o item de
    maior prioridade que ainda não tenha sido publicado (checagem por
    slug, feita DEPOIS de gerar o texto — o slug final depende do
    título que o editor.py produz, não do título original do feed).
    Tenta até `max_tentativas` itens da pauta antes de desistir.

    Levanta ValueError se não houver nenhuma notícia nos feeds, se o
    EditorChefe descartar tudo por duplicidade, ou se todos os
    candidatos tentados já tiverem sido publicados antes.
    """
    candidatos_brutos = pesquisador.pesquisar_noticias()
    if not candidatos_brutos:
        raise ValueError("Nenhuma notícia encontrada nos feeds RSS configurados")

    repo = NoticiaRepository(db)
    titulos_existentes = repo.listar_titulos_recentes(limite=100)

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
        if repo.buscar_por_slug(candidato_artigo["slug"]):
            print(f"[Pipeline] '{item.titulo}' já publicada (slug duplicado), tentando a próxima da pauta.")
            continue
        artigo = candidato_artigo
        item_escolhido = item
        break

    if artigo is None:
        raise ValueError("Todos os itens tentados da pauta já foram publicados antes")

    artigo = revisor.revisar_artigo(artigo)
    artigo = seo.otimizar_seo(artigo)  # sem imagem — noticias não tem coluna pra isso

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
    from config.database import SessionLocal

    db = SessionLocal()
    try:
        resultado = gerar_e_processar_noticia(db)
        print(f"Notícia salva: {resultado}")
    finally:
        db.close()