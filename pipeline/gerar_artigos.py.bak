"""
pipeline/gerar_artigos.py — Orquestra o fluxo de ARTIGOS evergreen

pesquisador → editor → revisor → imagem_service → seo → publisher

CORREÇÃO v4:
- Remove chamada pesquisar_tema() que era descartada por editor.gerar_artigo_base()
  (o briefing não era usado no prompt real, só aumentava tempo sem valor)
- Mantém sessões curtas (_sessao_curta) para evitar SSL closed no Neon
"""

from contextlib import contextmanager

from config.database import SessionLocal
from agents import pesquisador, editor, revisor, seo, publisher
from repositories.artigo_repository import ArtigoRepository
from services.imagem_service import buscar_imagem_capa


@contextmanager
def _sessao_curta():
    """
    Abre uma sessão do banco só pelo tempo de UMA operação rápida, e
    fecha em seguida. Nunca fica aberta durante o trabalho lento do
    LLM — é exatamente isso que causava o erro "SSL connection has been
    closed unexpectedly" que o Neon dispara em conexões ociosas por tempo demais.

    Segue o MESMO padrão de gerar_noticias.py, que já funcionava.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def gerar_e_processar_artigo(
    tema: str,
    categoria: str = "Tecnologia",
    publicar_imediatamente: bool = False,
) -> dict:
    """
    Roda a cadeia completa para um artigo evergreen e salva no Neon
    como 'rascunho'. Levanta ValueError se já existir um artigo com
    o mesmo slug.

    Se publicar_imediatamente=True, também publica no GitHub e marca
    como 'publicado' em seguida.

    ATENÇÃO: esta função NÃO recebe mais `db: Session`. Ela abre
    sessões curtas internamente, seguindo o mesmo padrão de
    gerar_noticias.py.
    """
    # 1. Geração de conteúdo — SEM conexão com banco aberta
    # CORREÇÃO v4: pesquisar_tema() era chamada mas o briefing era
    # descartado por editor.gerar_artigo_base() (parâmetro aceito mas
    # nunca usado no prompt). Removida para economizar uma chamada LLM.
    # TODO: quando editor.py for ajustado para usar briefing no prompt,
    # descomentar a linha abaixo.
    # briefing = pesquisador.pesquisar_tema(tema, categoria)
    artigo = editor.gerar_artigo_base(tema, categoria, briefing=None)

    # 2. Checa slug duplicado — sessão CURTA, fecha imediatamente
    with _sessao_curta() as db:
        if ArtigoRepository(db).buscar_por_slug(artigo["slug"]):
            raise ValueError(f"Já existe um artigo com o slug '{artigo['slug']}'")

    # 3. Revisão, imagem, SEO — SEM conexão com banco aberta
    artigo = revisor.revisar_artigo(artigo)
    imagem = buscar_imagem_capa(titulo=artigo["titulo"], tema=tema, categoria=categoria)
    artigo = seo.otimizar_seo(artigo, imagem=imagem)

    # 4. Salva no banco — sessão CURTA, fecha imediatamente
    with _sessao_curta() as db:
        artigo_id = publisher.salvar_artigo(db, artigo, imagem)

    resultado = {
        "id": artigo_id,
        "slug": artigo["slug"],
        "titulo": artigo["titulo"],
        "categoria": artigo["categoria"],
        "status": "rascunho",
        "imagem": imagem["imagem_url"] if imagem else None,
    }

    # 5. Publica no GitHub se solicitado — outra sessão CURTA
    if publicar_imediatamente:
        with _sessao_curta() as db:
            resultado_publicacao = publisher.publicar(db, artigo_id)
        resultado["status"] = resultado_publicacao["status"]
        resultado["github_url"] = resultado_publicacao["github_url"]
        resultado["blog_url"] = resultado_publicacao["blog_url"]

    return resultado
