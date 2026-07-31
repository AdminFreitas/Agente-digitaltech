"""
pipeline/gerar_artigos.py — Orquestra o fluxo de ARTIGOS evergreen

pesquisador → editor → revisor → imagem_service → seo → publisher

Reaproveitado tanto pela API (app.py, endpoint POST /artigos/gerar)
quanto pelo script de linha de comando pipeline/workflow.py.
"""

from sqlalchemy.orm import Session

from agents import pesquisador, editor, revisor, seo, publisher
from repositories.artigo_repository import ArtigoRepository
from services.imagem_service import buscar_imagem_capa


def gerar_e_processar_artigo(
    db: Session,
    tema: str,
    categoria: str = "Tecnologia",
    publicar_imediatamente: bool = False,
) -> dict:
    """
    Roda a cadeia completa para um artigo evergreen e salva no Neon
    como 'rascunho'. Levanta ValueError se já existir um artigo com o
    mesmo slug — quem chamar decide como reportar isso (ex.: app.py
    converte para HTTPException 409).

    Se publicar_imediatamente=True, também publica no GitHub e marca
    como 'publicado' em seguida, reaproveitando publisher.publicar() —
    o mesmo caminho usado por POST /artigos/publicar/{id}, para não
    existirem dois jeitos diferentes de publicar.
    """
    briefing = pesquisador.pesquisar_tema(tema, categoria)
    artigo = editor.gerar_artigo_base(tema, categoria, briefing=briefing)

    if ArtigoRepository(db).buscar_por_slug(artigo["slug"]):
        raise ValueError(f"Já existe um artigo com o slug '{artigo['slug']}'")

    artigo = revisor.revisar_artigo(artigo)
    imagem = buscar_imagem_capa(titulo=artigo["titulo"], tema=tema, categoria=categoria)
    artigo = seo.otimizar_seo(artigo, imagem=imagem)
    artigo_id = publisher.salvar_artigo(db, artigo, imagem)

    resultado = {
        "id": artigo_id,
        "slug": artigo["slug"],
        "titulo": artigo["titulo"],
        "categoria": artigo["categoria"],
        "status": "rascunho",
        "imagem": imagem["imagem_url"] if imagem else None,
    }

    if publicar_imediatamente:
        resultado_publicacao = publisher.publicar(db, artigo_id)
        resultado["status"] = resultado_publicacao["status"]
        resultado["github_url"] = resultado_publicacao["github_url"]
        resultado["blog_url"] = resultado_publicacao["blog_url"]

    return resultado
