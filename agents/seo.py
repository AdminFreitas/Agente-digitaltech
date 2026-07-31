"""
seo.py — Agente de otimização SEO

Recebe o artigo já revisado e gera os metadados de SEO: título
otimizado, meta description, tags e título para Open Graph. Não
reescreve o corpo do artigo — isso já foi feito pelo editor.py e
revisor.py. Não gera um novo slug: o slug já foi definido pelo
editor.py e trocar aqui quebraria a URL do artigo.
"""

from services.llm_service import gerar_texto


def otimizar_seo(artigo: dict, imagem: dict | None = None) -> dict:
    """
    Recebe um dict de artigo e, opcionalmente, o dict retornado por
    imagem_service.buscar_imagem_capa(). Devolve uma CÓPIA do artigo
    com metadados de SEO adicionados (`titulo_seo`, `meta_description`,
    `tags`, `og_titulo`, `imagem_alt`), sem alterar `conteudo_markdown`.
    Não modifica o dict recebido.
    """
    prompt = f"""Você é um especialista em SEO para blogs de tecnologia.

Artigo:
Título atual: {artigo['titulo']}
Categoria: {artigo['categoria']}
Resumo atual: {artigo.get('excerpt', '')}

Primeiros parágrafos do artigo:
{artigo['conteudo_markdown'][:800]}

Gere metadados de SEO para esse artigo. Responda EXATAMENTE neste
formato de texto simples, sem Markdown, sem explicações extras:

TITULO_SEO: título otimizado para SEO, até 60 caracteres
META_DESCRIPTION: até 155 caracteres, com call-to-action sutil
TAGS: tag1, tag2, tag3, tag4, tag5
OPEN_GRAPH_TITULO: título chamativo para redes sociais, até 90 caracteres
"""
    texto = gerar_texto(prompt)
    metadados = _parsear_metadados_seo(texto)

    artigo_otimizado = dict(artigo)
    artigo_otimizado["titulo_seo"] = metadados["titulo_seo"] or artigo["titulo"]
    artigo_otimizado["meta_description"] = metadados["meta_description"] or artigo.get("excerpt", "")
    artigo_otimizado["tags"] = metadados["tags"]
    artigo_otimizado["og_titulo"] = metadados["og_titulo"] or artigo["titulo"]
    artigo_otimizado["imagem_alt"] = (imagem or {}).get("imagem_alt") or artigo["titulo"]

    return artigo_otimizado


def _parsear_metadados_seo(texto: str) -> dict:
    titulo_seo = ""
    meta_description = ""
    tags: list[str] = []
    og_titulo = ""

    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        chave, _, valor = linha.partition(":")
        chave_normalizada = chave.strip().upper()
        valor = valor.strip()

        if chave_normalizada == "TITULO_SEO":
            titulo_seo = valor
        elif chave_normalizada == "META_DESCRIPTION":
            meta_description = valor
        elif chave_normalizada == "TAGS":
            tags = [t.strip() for t in valor.split(",") if t.strip()]
        elif chave_normalizada == "OPEN_GRAPH_TITULO":
            og_titulo = valor

    return {
        "titulo_seo": titulo_seo,
        "meta_description": meta_description,
        "tags": tags,
        "og_titulo": og_titulo,
    }
