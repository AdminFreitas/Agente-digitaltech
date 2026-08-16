"""
publisher.py — Agente publicador

Responsável por:
- salvar_artigo(): salvar o artigo pronto no Neon como 'rascunho'.
- publicar(): montar o Markdown final, publica no GitHub e só então
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


def _escapar_yaml(valor: str) -> str:
    """
    Escapa uma string para uso seguro dentro de aspas duplas no YAML.

    Escapa barras invertidas e aspas duplas. Substitui quebras de linha
    por \\n para evitar quebrar a estrutura do front matter.
    """
    if not valor:
        return ""
    # Ordem importa: primeiro escape de \, depois de "
    valor = valor.replace("\\", "\\\\")
    valor = valor.replace('"', '\\"')
    valor = valor.replace("\r\n", "\\n")
    valor = valor.replace("\n", "\\n")
    valor = valor.replace("\r", "")
    return valor


def _campo_yaml_string(nome: str, valor: str | None) -> str | None:
    """
    Retorna a linha YAML 'nome: "valor"' se valor for truthy.
    Retorna None se valor for vazio/None.
    """
    if not valor:
        return None
    return f'{nome}: "{_escapar_yaml(valor)}"'


def _campo_yaml_lista(nome: str, valores: list | None) -> str | None:
    """
    Retorna a linha YAML 'nome: [...]' se a lista tiver itens válidos.
    Retorna None se a lista for vazia/None.
    """
    if not valores:
        return None
    itens = ", ".join(
        f'"{_escapar_yaml(str(v))}"'
        for v in valores
        if v is not None and str(v).strip()
    )
    if not itens:
        return None
    return f"{nome}: [{itens}]"


def salvar_artigo(db, artigo: dict, imagem: dict | None) -> int:
    """
    Salva o artigo no Neon como rascunho (status='rascunho'). Retorna
    o ID gerado. Não publica no GitHub ainda — isso é publicar().
    """
    repo = ArtigoRepository(db)

    categoria_id = repo.buscar_categoria_id(artigo["categoria"])
    if categoria_id is None:
        raise ValueError(
            f"Categoria '{artigo['categoria']}' não existe no banco. "
            "Verifique o nome ou cadastre a categoria antes de salvar."
        )

    return repo.criar(
        slug=artigo["slug"],
        titulo=artigo.get("titulo_seo") or artigo["titulo"],
        categoria_id=categoria_id,
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
    então marca como 'publicado'.

    Levanta ValueError se o artigo não existir, já estiver publicado,
    ou não possuir campos essenciais. Deixa subir qualquer erro do
    GitHub sem marcar como publicado.
    """
    repo = ArtigoRepository(db)
    artigo_db = repo.buscar_por_id(artigo_id)

    if artigo_db is None:
        raise ValueError(f"Artigo {artigo_id} não encontrado no banco.")

    # Idempotência: evita republicar se já estiver publicado
    status_atual = getattr(artigo_db, "status", None)
    if status_atual == "publicado":
        raise ValueError(
            f"Artigo {artigo_id} já está publicado. "
            "Não é possível publicar novamente."
        )

    # Validações de campos essenciais
    if not artigo_db.slug or not str(artigo_db.slug).strip():
        raise ValueError(
            f"Artigo {artigo_id} sem slug: não é possível publicar."
        )

    if not artigo_db.titulo or not str(artigo_db.titulo).strip():
        raise ValueError(
            f"Artigo {artigo_id} sem título: não é possível publicar."
        )

    if not artigo_db.conteudo_md or not str(artigo_db.conteudo_md).strip():
        raise ValueError(
            f"Artigo {artigo_id} sem conteúdo: não é possível publicar."
        )

    categoria_nome = repo.buscar_categoria_nome(artigo_db.categoria_id)

    artigo = {
        "titulo": artigo_db.titulo,
        "slug": artigo_db.slug,
        "categoria": categoria_nome or "Tecnologia",
        "excerpt": artigo_db.resumo,
        "conteudo_markdown": artigo_db.conteudo_md,
        "readTime": artigo_db.tempo_leitura,
        "data": (
            str(artigo_db.data_publicacao)
            if artigo_db.data_publicacao
            else date.today().isoformat()
        ),
    }

    # Campos opcionais que podem existir no modelo do banco (SEO)
    campos_opcionais = [
        "titulo_seo",
        "meta_description",
        "tags",
        "og_titulo",
        "fonte_original",
        "imagem_alt",
        "imagem_fonte",
    ]
    for campo in campos_opcionais:
        if hasattr(artigo_db, campo):
            artigo[campo] = getattr(artigo_db, campo)

    imagem = None
    if artigo_db.imagem_url:
        imagem = {
            "imagem_url": artigo_db.imagem_url,
            "imagem_autor": artigo_db.imagem_autor,
            "imagem_link": artigo_db.imagem_link,
            "imagem_fonte": artigo.get("imagem_fonte", ""),
            "imagem_alt": artigo.get("imagem_alt") or artigo["titulo"],
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
    Retorna o dict de github_service.publicar_artigo().
    """
    conteudo_markdown = _montar_markdown_para_github(artigo, imagem)
    return github_service.publicar_artigo(
        slug=artigo["slug"],
        conteudo_markdown=conteudo_markdown,
        titulo=artigo.get("titulo_seo") or artigo["titulo"],
    )


def _montar_markdown_para_github(artigo: dict, imagem: dict | None) -> str:
    """
    Monta o arquivo .md completo (front matter YAML + corpo) que vai
    pro GitHub.

    Só inclui campos opcionais quando possuem valor truthy.
    Não gera campos vazios no front matter.
    """
    linhas = ["---"]

    # Campos obrigatórios
    # title usa o fallback de SEO (titulo_seo), igual ao publicar_no_github
    # e ao salvar_artigo — mantém consistência entre o título usado no
    # commit do GitHub e o título exibido no front matter do blog.
    titulo_final = artigo.get("titulo_seo") or artigo["titulo"]
    linhas.append(f'title: "{_escapar_yaml(titulo_final)}"')
    linhas.append(f'slug: "{_escapar_yaml(artigo["slug"])}"')
    linhas.append(f'category: "{_escapar_yaml(artigo["categoria"])}"')

    descricao = artigo.get("meta_description") or artigo.get("excerpt", "")
    linhas.append(f'description: "{_escapar_yaml(descricao)}"')

    linhas.append(f'date: "{artigo.get("data", date.today().isoformat())}"')

    # readTime só entra se tiver valor
    read_time = artigo.get("readTime")
    if read_time:
        linhas.append(f'readTime: "{_escapar_yaml(str(read_time))}"')

    # Tags
    linha_tags = _campo_yaml_lista("tags", artigo.get("tags"))
    if linha_tags:
        linhas.append(linha_tags)

    # Campos opcionais do front matter
    if artigo.get("og_titulo"):
        linhas.append(f'ogTitle: "{_escapar_yaml(artigo["og_titulo"])}"')

    if artigo.get("fonte_original"):
        linhas.append(f'sourceUrl: "{_escapar_yaml(artigo["fonte_original"])}"')

    # Metadados de imagem
    if imagem:
        if imagem.get("imagem_url"):
            linhas.append(f'image: "{_escapar_yaml(imagem["imagem_url"])}"')
        if imagem.get("imagem_alt"):
            linhas.append(f'imageAlt: "{_escapar_yaml(imagem["imagem_alt"])}"')
        if imagem.get("imagem_autor"):
            linhas.append(f'imageAuthor: "{_escapar_yaml(imagem["imagem_autor"])}"')
        if imagem.get("imagem_fonte"):
            linhas.append(f'imageSource: "{_escapar_yaml(imagem["imagem_fonte"])}"')

    linhas.append("---")

    corpo = artigo["conteudo_markdown"].strip()
    return "\n".join(linhas) + "\n\n" + corpo + "\n"