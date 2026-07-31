"""
pipeline/gerar_noticias.py — Orquestra o fluxo de NOTÍCIAS

pesquisador (RSS) → editor (reescreve) → revisor → imagem_service →
seo → publisher

Reaproveitado tanto pela API (app.py, endpoint POST /noticias/gerar)
quanto por um script de linha de comando (bloco __main__ abaixo).
"""

from sqlalchemy.orm import Session

from agents import pesquisador, editor, revisor, seo, publisher
from repositories.artigo_repository import ArtigoRepository
from services.imagem_service import buscar_imagem_capa


def gerar_e_processar_noticia(
    db: Session,
    categoria: str = "Tecnologia",
    max_tentativas: int = 3,
    publicar_imediatamente: bool = False,
) -> dict:
    """
    Busca notícias recentes via RSS e roda a cadeia completa para a
    primeira que ainda não tenha sido publicada (checagem por slug,
    feita DEPOIS de gerar o texto reescrito — o slug final depende do
    título que o editor.py produz, não do título original da fonte).
    Tenta até `max_tentativas` candidatos antes de desistir.

    Levanta ValueError se não houver nenhuma notícia nos feeds, ou se
    todos os candidatos tentados já tiverem sido publicados antes.
    """
    candidatos = pesquisador.pesquisar_noticias()
    if not candidatos:
        raise ValueError("Nenhuma notícia encontrada nos feeds RSS configurados")

    repo = ArtigoRepository(db)
    artigo = None
    noticia_escolhida = None

    for noticia in candidatos[:max_tentativas]:
        candidato_artigo = editor.gerar_noticia_base(noticia, categoria=categoria)
        if repo.buscar_por_slug(candidato_artigo["slug"]):
            print(f"[Pipeline] '{noticia['titulo']}' já publicada (slug duplicado), tentando a próxima.")
            continue
        artigo = candidato_artigo
        noticia_escolhida = noticia
        break

    if artigo is None:
        raise ValueError("Todas as notícias candidatas já foram publicadas antes")

    artigo = revisor.revisar_artigo(artigo)
    imagem = buscar_imagem_capa(titulo=artigo["titulo"], categoria=categoria)
    artigo = seo.otimizar_seo(artigo, imagem=imagem)
    artigo_id = publisher.salvar_artigo(db, artigo, imagem)

    resultado = {
        "id": artigo_id,
        "slug": artigo["slug"],
        "titulo": artigo["titulo"],
        "categoria": artigo["categoria"],
        "status": "rascunho",
        "imagem": imagem["imagem_url"] if imagem else None,
        "fonte_original": noticia_escolhida["link"],
    }

    if publicar_imediatamente:
        resultado_publicacao = publisher.publicar(db, artigo_id)
        resultado["status"] = resultado_publicacao["status"]
        resultado["github_url"] = resultado_publicacao["github_url"]
        resultado["blog_url"] = resultado_publicacao["blog_url"]

    return resultado


if __name__ == "__main__":
    from config.database import SessionLocal

    db = SessionLocal()
    try:
        resultado = gerar_e_processar_noticia(db)
        print(f"Notícia salva: {resultado}")
    finally:
        db.close()
