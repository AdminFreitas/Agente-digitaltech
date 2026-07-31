"""
publisher.py — Agente publicador

Responsável por:
- salvar_artigo(): salvar o artigo pronto no Neon como 'rascunho'.
- publicar(): montar o Markdown final, publicar no GitHub e só então
  marcar o artigo como 'publicado' no Neon.

Ordem importa: só marca como publicado no Neon DEPOIS que o commit no
GitHub for confirmado. Se o GitHub falhar, o artigo continua salvo
como 'rascunho' no Neon — nada é perdido — e a exceção sobe para quem
chamou tratar (ex.: reexibir erro 502 no endpoint da API).

Os campos de SEO (tags, meta description, título Open Graph) e os
metadados de imagem (fonte, alt) entram no front matter do Markdown
publicado no GitHub mesmo sem colunas próprias no banco Neon ainda —
isso não depende da migração do banco combinada para depois.
"""

from datetime import date

from repositories.artigo_repository import ArtigoRepository
from services import github_service


def salvar_artigo(db, artigo: dict, imagem: dict | None) -> int:
    """
    Salva o artigo no Neon como rascunho (status='rascunho'). Retorna
    o ID gerado. Não publica no GitHub ainda — isso é publicar().
    """
    repo = ArtigoRepository(db)
    return repo.criar(
        slug=artigo["slug"],
        titulo=artigo.get("titulo_seo") or artigo["titulo"],
        categoria=artigo["categoria"],
        resumo=artigo.get("meta_description") or artigo.get("excerpt", ""),
        conteudo_markdown=artigo["conteudo_markdown"],
        status="rascunho",
        imagem_url=imagem["imagem_url"] if imagem else None,
        imagem_autor=imagem["imagem_autor"] if imagem else None,
        imagem_link=imagem["imagem_link"] if imagem else None,
    )


def publicar(db, artigo_id: int) -> dict:
    """
    Publica um artigo que já está salvo no Neon (status 'rascunho'):
    relê os dados do banco, monta o Markdown, publica no GitHub e só
    então marca como 'publicado'. Levanta ValueError se o artigo não
    existir; deixa subir qualquer erro do GitHub sem marcar como
    publicado.
    """
    repo = ArtigoRepository(db)
    artigo_db = repo.buscar_por_id(artigo_id)

    if artigo_db is None:
        raise ValueError(f"Artigo {artigo_id} não encontrado")

    artigo = {
        "titulo": artigo_db.titulo,
        "slug": artigo_db.slug,
        "categoria": artigo_db.categoria,
        "excerpt": artigo_db.resumo,
        "conteudo_markdown": artigo_db.conteudo_md,
        "readTime": artigo_db.tempo_leitura,
        "data": str(artigo_db.data_publicacao) if artigo_db.data_publicacao else date.today().isoformat(),
    }

    imagem = None
    if artigo_db.imagem_url:
        imagem = {
            "imagem_url": artigo_db.imagem_url,
            "imagem_autor": artigo_db.imagem_autor,
            "imagem_link": artigo_db.imagem_link,
            # imagem_fonte e imagem_alt ainda não têm coluna no banco —
            # ficam de fora até a migração combinada para depois.
            "imagem_fonte": "",
            "imagem_alt": artigo["titulo"],
        }

    resultado_github = publicar_no_github(artigo, imagem)
    repo.publicar(artigo_id)

    return {
        "id": artigo_id,
        "slug": artigo["slug"],
        "status": "publicado",
        "github_url": resultado_github["github_url"],
        "blog_url": resultado_github["blog_url"],
    }


def publicar_no_github(artigo: dict, imagem: dict | None) -> dict:
    """
    Monta o Markdown final e publica no GitHub via github_service.
    Retorna o dict de github_service.publicar_artigo() (github_url,
    blog_url, atualizado).
    """
    conteudo_markdown = _montar_markdown_para_github(artigo, imagem)
    return github_service.publicar_artigo(
        slug=artigo["slug"],
        conteudo_markdown=conteudo_markdown,
        titulo=artigo.get("titulo_seo") or artigo["titulo"],
    )


def _escapar_yaml(valor: str) -> str:
    """Escapa aspas duplas para não quebrar o front matter YAML."""
    return (valor or "").replace('"', '\\"')


def _montar_markdown_para_github(artigo: dict, imagem: dict | None) -> str:
    """
    Monta o arquivo .md completo (front matter YAML + corpo) que vai
    pro GitHub.
    """
    tags = artigo.get("tags") or []
    tags_yaml = "[" + ", ".join(f'"{_escapar_yaml(t)}"' for t in tags) + "]"

    linhas_front_matter = [
        "---",
        f'title: "{_escapar_yaml(artigo.get("titulo_seo") or artigo["titulo"])}"',
        f'slug: "{_escapar_yaml(artigo["slug"])}"',
        f'category: "{_escapar_yaml(artigo["categoria"])}"',
        f'description: "{_escapar_yaml(artigo.get("meta_description") or artigo.get("excerpt", ""))}"',
        f'date: "{artigo.get("data", date.today().isoformat())}"',
        f'readTime: "{_escapar_yaml(artigo.get("readTime", ""))}"',
        f"tags: {tags_yaml}",
    ]

    if artigo.get("og_titulo"):
        linhas_front_matter.append(f'ogTitle: "{_escapar_yaml(artigo["og_titulo"])}"')

    if imagem:
        linhas_front_matter += [
            f'image: "{_escapar_yaml(imagem.get("imagem_url", ""))}"',
            f'imageAlt: "{_escapar_yaml(artigo.get("imagem_alt") or imagem.get("imagem_alt", ""))}"',
            f'imageAuthor: "{_escapar_yaml(imagem.get("imagem_autor", ""))}"',
            f'imageSource: "{_escapar_yaml(imagem.get("imagem_fonte", ""))}"',
        ]

    if artigo.get("fonte_original"):
        linhas_front_matter.append(f'sourceUrl: "{_escapar_yaml(artigo["fonte_original"])}"')

    linhas_front_matter.append("---")

    return "\n".join(linhas_front_matter) + "\n\n" + artigo["conteudo_markdown"].strip() + "\n"
