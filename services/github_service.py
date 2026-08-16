"""
github_service.py — Publicação de artigos e notícias via GitHub API

Responsabilidade única: criar ou atualizar arquivos .md
no repositório do blog (artigos e notícias), disparando o deploy automático.
"""

import os
import base64
import httpx
from dotenv import load_dotenv
from pathlib import Path

# Carrega o .env da RAIZ do projeto (independente de onde o script rodar)
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "").strip()
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "").strip()
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip()
GITHUB_CONTENT_PATH = os.getenv("GITHUB_CONTENT_PATH", "content").strip().strip("/")

# Monta o nome completo do repositório
if GITHUB_OWNER and GITHUB_REPOSITORY:
    GITHUB_REPO = f"{GITHUB_OWNER}/{GITHUB_REPOSITORY}"
else:
    GITHUB_REPO = "AdminFreitas/digitaltech"  # fallback de segurança

# Configuração por tipo de conteúdo: subpasta dentro de GITHUB_CONTENT_PATH,
# rótulo usado na mensagem de commit e URL pública do blog.
_TIPOS_CONTEUDO = {
    "artigos": {
        "subpasta": "artigos",
        "rotulo_commit": "artigo",
        "url_base": "https://digitaltech.digital/artigos",
    },
    "noticias": {
        "subpasta": "noticias",
        "rotulo_commit": "noticia",
        "url_base": "https://digitaltech.digital/noticias",
    },
}

# Diagnóstico no início (aparece no terminal quando importar)
print(f"[GitHub Service] Repositório alvo: {GITHUB_REPO}")
print(f"[GitHub Service] Branch: {GITHUB_BRANCH}")
print(f"[GitHub Service] Diretório base de conteúdo: {GITHUB_CONTENT_PATH}")
print(f"[GitHub Service] Token carregado: {'SIM (' + GITHUB_TOKEN[:10] + '...)' if GITHUB_TOKEN else 'NÃO — VERIFIQUE O .ENV!'}")


def _headers() -> dict:
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN não configurado. Verifique o arquivo .env na raiz do projeto.")

    # Fine-Grained PATs usam 'Bearer', Classic PATs aceitam 'token' ou 'Bearer'
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _url_arquivo(slug: str, tipo: str = "artigos") -> str:
    """
    Monta a URL da API do GitHub para o arquivo .md de um conteúdo,
    usando GITHUB_CONTENT_PATH como diretório-base e a subpasta
    correspondente ao tipo ('artigos' ou 'noticias').
    """
    config = _TIPOS_CONTEUDO.get(tipo, _TIPOS_CONTEUDO["artigos"])
    caminho = f"{GITHUB_CONTENT_PATH}/{config['subpasta']}/{slug}.md"
    return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{caminho}"


def testar_conexao() -> dict:
    """
    Testa se o token consegue ler o repositório.
    Retorna dict com status e mensagem.
    """
    if not GITHUB_TOKEN:
        return {"ok": False, "erro": "Token não configurado no .env"}

    url = f"https://api.github.com/repos/{GITHUB_REPO}"

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=_headers())

        if resp.status_code == 200:
            dados = resp.json()
            return {
                "ok": True,
                "repo": dados.get("full_name"),
                "privado": dados.get("private"),
                "default_branch": dados.get("default_branch"),
            }
        elif resp.status_code == 401:
            return {"ok": False, "erro": "Token inválido ou expirado (401)"}
        elif resp.status_code == 403:
            return {"ok": False, "erro": f"Token sem permissão para acessar este repo (403). Verifique se o token tem acesso ao repositório '{GITHUB_REPO}'"}
        elif resp.status_code == 404:
            return {"ok": False, "erro": f"Repositório '{GITHUB_REPO}' não encontrado (404). Verifique GITHUB_OWNER e GITHUB_REPOSITORY no .env"}
        else:
            return {"ok": False, "erro": f"Erro inesperado: {resp.status_code} — {resp.text}"}
    except Exception as e:
        return {"ok": False, "erro": f"Erro de conexão: {str(e)}"}


def _publicar_conteudo(tipo: str, slug: str, conteudo_markdown: str, titulo: str) -> dict:
    """
    Lógica interna reutilizável para publicar artigos ou notícias.

    `tipo` deve ser 'artigos' ou 'noticias' — define a subpasta dentro de
    GITHUB_CONTENT_PATH, o rótulo usado na mensagem de commit e a URL
    pública de retorno.
    """
    if tipo not in _TIPOS_CONTEUDO:
        raise ValueError(f"Tipo de conteúdo inválido: '{tipo}'. Use 'artigos' ou 'noticias'.")

    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN não configurado. Verifique o .env na raiz do projeto.")

    config = _TIPOS_CONTEUDO[tipo]
    url = _url_arquivo(slug, tipo=tipo)
    conteudo_b64 = base64.b64encode(conteudo_markdown.encode("utf-8")).decode("utf-8")
    headers = _headers()

    # Verifica se o arquivo já existe (para pegar o SHA necessário no update)
    sha = None
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=headers)
        if resp.status_code == 200:
            sha = resp.json().get("sha")
            print(f"[GitHub Service] {config['rotulo_commit'].capitalize()} já existe, SHA: {sha[:8]}... (vai atualizar)")
        elif resp.status_code == 404:
            print(f"[GitHub Service] {config['rotulo_commit'].capitalize()} novo (vai criar)")
        else:
            print(f"[GitHub Service] Aviso ao verificar existência: {resp.status_code}")

    payload = {
        "message": f"feat: adiciona {config['rotulo_commit']} '{titulo}'",
        "content": conteudo_b64,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    with httpx.Client(timeout=15.0) as client:
        resp = client.put(url, headers=headers, json=payload)

    if resp.status_code == 403:
        erro = resp.json() if resp.text else {}
        mensagem = erro.get("message", "Sem detalhes")
        raise RuntimeError(
            f"Erro 403 — Token sem permissão suficiente.\n"
            f"Mensagem do GitHub: {mensagem}\n\n"
            f"Soluções:\n"
            f"1. Se usar Fine-Grained PAT: dê permissão 'Contents: Read and Write' no repo '{GITHUB_REPO}'\n"
            f"2. Se usar Classic PAT: marque o escopo 'repo'\n"
            f"3. Verifique se o token não expirou\n"
            f"4. Se a branch '{GITHUB_BRANCH}' for protegida, o token precisa de permissão de admin"
        )
    elif resp.status_code == 401:
        raise RuntimeError("Erro 401 — Token inválido ou expirado. Gere um novo token no GitHub.")
    elif resp.status_code == 404:
        raise RuntimeError(
            f"Erro 404 — Repositório ou caminho não encontrado.\n"
            f"Verifique se '{GITHUB_REPO}' existe, se a branch '{GITHUB_BRANCH}' está correta "
            f"e se a pasta '{GITHUB_CONTENT_PATH}/{config['subpasta']}/' existe nessa branch."
        )
    elif resp.status_code not in (200, 201):
        raise RuntimeError(f"Erro ao publicar {config['rotulo_commit']} no GitHub: {resp.status_code} — {resp.text}")

    html_url = resp.json().get("content", {}).get("html_url", "")
    print(f"[GitHub Service] ✅ {config['rotulo_commit'].capitalize()} publicado com sucesso: {html_url}")

    return {
        "github_url": html_url,
        "blog_url": f"{config['url_base']}/{slug}",
        "atualizado": sha is not None,
    }


def publicar_artigo(slug: str, conteudo_markdown: str, titulo: str) -> dict:
    """
    Cria o arquivo .md do artigo no repositório do blog, em
    {GITHUB_CONTENT_PATH}/artigos/{slug}.md.
    Se o arquivo já existir, atualiza o conteúdo.
    Retorna a URL do arquivo no GitHub e a URL pública no blog.
    """
    return _publicar_conteudo("artigos", slug, conteudo_markdown, titulo)


def publicar_noticia(slug: str, conteudo_markdown: str, titulo: str) -> dict:
    """
    Cria o arquivo .md da notícia no repositório do blog, em
    {GITHUB_CONTENT_PATH}/noticias/{slug}.md.
    Se o arquivo já existir, atualiza o conteúdo.
    Retorna a URL do arquivo no GitHub e a URL pública no blog.
    """
    return _publicar_conteudo("noticias", slug, conteudo_markdown, titulo)


def artigo_existe(slug: str) -> bool:
    """Verifica se um artigo com este slug já existe no repositório."""
    if not GITHUB_TOKEN:
        return False

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(_url_arquivo(slug, tipo="artigos"), headers=_headers())
    return resp.status_code == 200


def noticia_existe(slug: str) -> bool:
    """Verifica se uma notícia com este slug já existe no repositório."""
    if not GITHUB_TOKEN:
        return False

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(_url_arquivo(slug, tipo="noticias"), headers=_headers())
    return resp.status_code == 200