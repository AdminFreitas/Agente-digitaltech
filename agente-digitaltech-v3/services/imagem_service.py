"""
imagem_service.py — Busca e geração de imagem de capa

ESTRATÉGIA (da mais barata para a mais cara):
  1. Bancos de imagens livres: Unsplash → Pexels → Pixabay → Openverse
  2. Geração via OpenRouter (Nano Banana 2 Lite) — paga, mas barato
  3. Geração local via Stable Diffusion (se configurado)
  4. Pollinations AI — gratuito, último recurso

Nunca lança exceção: em caso de falha total, retorna None.
"""

import os
import re
import random
import uuid
import base64
from urllib.parse import quote
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# Chaves de API
# ---------------------------------------------------------------------------
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
OPENVERSE_CLIENT_ID = os.getenv("OPENVERSE_CLIENT_ID")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

STABLE_DIFFUSION_URL = os.getenv("STABLE_DIFFUSION_URL", "")  # ex: http://localhost:7860

TIMEOUT = 15

# ---------------------------------------------------------------------------
# Mapeamento categoria → query em inglês
# ---------------------------------------------------------------------------
CATEGORIA_PARA_QUERY = {
    "inteligência artificial": "artificial intelligence technology",
    "ia": "artificial intelligence technology",
    "programação": "programming code screen",
    "desenvolvimento web": "web development coding",
    "engenharia de software": "software engineering code",
    "banco de dados": "database server technology",
    "dados": "data technology server",
    "cibersegurança": "cybersecurity technology",
    "cloud & devops": "cloud computing server",
    "carreira": "technology workspace office",
}

STOPWORDS_PT = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos",
    "das", "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "sob",
    "sobre", "e", "ou", "que", "se", "é", "são", "foi", "ser", "sua", "seu",
    "suas", "seus", "ao", "aos", "à", "às", "como", "mais", "menos", "muito",
    "porque", "por que", "quando", "onde", "qual", "quais", "isso", "isto",
    "este", "esta", "esse", "essa", "num", "numa",
}


def _query_para_categoria(categoria: str) -> str:
    return CATEGORIA_PARA_QUERY.get(categoria.strip().lower(), "technology")


def _extrair_palavras_chave(titulo: str, max_palavras: int = 5) -> str:
    if not titulo:
        return ""
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+(?:[/\.][A-Za-zÀ-ÖØ-öø-ÿ0-9]+)*", titulo)
    significativas = []
    for tok in tokens:
        if tok.isdigit():
            significativas.append(tok)
            continue
        if tok.lower() in STOPWORDS_PT:
            continue
        if len(tok) <= 2 and "/" not in tok and "." not in tok:
            continue
        significativas.append(tok)
    return " ".join(significativas[:max_palavras])


# ---------------------------------------------------------------------------
# Fontes de BUSCA (gratuitas)
# ---------------------------------------------------------------------------

def _buscar_no_unsplash(query: str) -> Optional[dict]:
    if not UNSPLASH_ACCESS_KEY:
        return None
    try:
        resp = httpx.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 10, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        resultados = resp.json().get("results", [])
        if not resultados:
            return None
        foto = random.choice(resultados)
        return {
            "url": foto["urls"]["small"],
            "autor": foto["user"]["name"],
            "link": foto["user"]["links"]["html"],
            "fonte": "Unsplash",
            "query": query,
            "alt": foto.get("alt_description") or query,
        }
    except Exception as e:
        print(f"[Imagem] Unsplash falhou: {e}")
        return None


def _buscar_no_pexels(query: str) -> Optional[dict]:
    if not PEXELS_API_KEY:
        return None
    try:
        resp = httpx.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": 10, "orientation": "landscape"},
            headers={"Authorization": PEXELS_API_KEY},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        fotos = resp.json().get("photos", [])
        if not fotos:
            return None
        foto = random.choice(fotos)
        return {
            "url": foto["src"]["large"],
            "autor": foto["photographer"],
            "link": foto["photographer_url"],
            "fonte": "Pexels",
            "query": query,
            "alt": foto.get("alt") or query,
        }
    except Exception as e:
        print(f"[Imagem] Pexels falhou: {e}")
        return None


def _buscar_no_pixabay(query: str) -> Optional[dict]:
    if not PIXABAY_API_KEY:
        return None
    try:
        resp = httpx.get(
            "https://pixabay.com/api/",
            params={"key": PIXABAY_API_KEY, "q": query, "image_type": "photo",
                    "orientation": "horizontal", "safesearch": "true", "per_page": 10},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        fotos = resp.json().get("hits", [])
        if not fotos:
            return None
        foto = random.choice(fotos)
        return {
            "url": foto["webformatURL"],
            "autor": foto["user"],
            "link": foto["pageURL"],
            "fonte": "Pixabay",
            "query": query,
            "alt": foto.get("tags") or query,
        }
    except Exception as e:
        print(f"[Imagem] Pixabay falhou: {e}")
        return None


def _buscar_no_openverse(query: str) -> Optional[dict]:
    try:
        headers = {}
        if OPENVERSE_CLIENT_ID:
            headers["Authorization"] = f"Bearer {OPENVERSE_CLIENT_ID}"
        resp = httpx.get(
            "https://api.openverse.org/v1/images/search",
            params={"q": query, "license_type": "commercial", "page_size": 10},
            headers=headers,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        resultados = resp.json().get("results", [])
        if not resultados:
            return None
        foto = random.choice(resultados)
        return {
            "url": foto.get("url"),
            "autor": foto.get("creator") or "Desconhecido",
            "link": foto.get("foreign_landing_url") or foto.get("url"),
            "fonte": "Openverse",
            "query": query,
            "alt": foto.get("title") or query,
        }
    except Exception as e:
        print(f"[Imagem] Openverse falhou: {e}")
        return None


# ---------------------------------------------------------------------------
# Geração de imagem via OpenRouter (Nano Banana 2 Lite)
# ---------------------------------------------------------------------------

def _gerar_no_openrouter(query: str) -> Optional[dict]:
    if not OPENROUTER_API_KEY:
        return None
    print(f"[Imagem] Gerando via OpenRouter (Nano Banana 2 Lite): '{query}'")
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://www.digitaltech.digital/",
            "X-Title": "Agente DigitalTech",
        }
        prompt = (
            f"Professional technology blog cover image about {query}, "
            f"modern flat design, dark blue background, clean minimalist, "
            f"high quality, 16:9 aspect ratio"
        )
        payload = {
            "model": "t2v/nano-banana-2-lite",
            "prompt": prompt,
            "n": 1,
            "size": "1024x576",
        }
        resp = httpx.post(
            f"{OPENROUTER_BASE_URL}/images/generations",
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        url_imagem = data.get("data", [{}])[0].get("url", "")
        if not url_imagem:
            return None
        return {
            "url": url_imagem,
            "autor": "Nano Banana 2 Lite (OpenRouter)",
            "link": "https://openrouter.ai/",
            "fonte": "OpenRouter/NanoBanana",
            "query": query,
            "alt": query,
        }
    except Exception as e:
        print(f"[Imagem] OpenRouter (Nano Banana) falhou: {e}")
        return None


# ---------------------------------------------------------------------------
# Geração local via Stable Diffusion
# ---------------------------------------------------------------------------

def _gerar_no_stable_diffusion(query: str) -> Optional[dict]:
    if not STABLE_DIFFUSION_URL:
        return None
    print(f"[Imagem] Gerando via Stable Diffusion local: '{query}'")
    try:
        prompt = (
            f"professional technology blog cover, {query}, "
            f"modern design, dark background, high quality"
        )
        payload = {
            "prompt": prompt,
            "steps": 20,
            "width": 1024,
            "height": 576,
        }
        resp = httpx.post(
            f"{STABLE_DIFFUSION_URL}/sdapi/v1/txt2img",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        b64 = data.get("images", [None])[0]
        if not b64:
            return None
        # Salva localmente e retorna path/URL
        nome_arquivo = f"sd_{uuid.uuid4().hex[:8]}.png"
        os.makedirs("output/imagens", exist_ok=True)
        caminho = f"output/imagens/{nome_arquivo}"
        with open(caminho, "wb") as f:
            f.write(base64.b64decode(b64))
        return {
            "url": caminho,
            "autor": "Stable Diffusion (local)",
            "link": STABLE_DIFFUSION_URL,
            "fonte": "Stable Diffusion Local",
            "query": query,
            "alt": query,
        }
    except Exception as e:
        print(f"[Imagem] Stable Diffusion local falhou: {e}")
        return None


# ---------------------------------------------------------------------------
# Fallback final: Pollinations AI (gratuito)
# ---------------------------------------------------------------------------

def _gerar_no_pollinations(query: str) -> Optional[dict]:
    try:
        tema = query.strip() if query else "technology abstract background"
        prompt = (
            f"Modern technology illustration, {tema}, dark background, "
            f"futuristic, professional, high quality, 16:9"
        )
        sufixo = uuid.uuid4().hex[:8]
        prompt_final = f"{prompt} {sufixo}"
        prompt_codificado = quote(prompt_final)
        url = (
            f"https://image.pollinations.ai/prompt/{prompt_codificado}"
            f"?width=1200&height=630&nologo=true"
        )
        return {
            "url": url,
            "autor": "Pollinations AI",
            "link": "https://pollinations.ai",
            "fonte": "Pollinations AI (gerada)",
            "query": tema,
            "alt": tema,
        }
    except Exception as e:
        print(f"[Imagem] Pollinations falhou: {e}")
        return None


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def _padronizar(resultado: dict) -> dict:
    return {
        "imagem_url": resultado.get("url"),
        "imagem_fonte": resultado.get("fonte"),
        "imagem_query": resultado.get("query"),
        "imagem_alt": resultado.get("alt"),
        "imagem_autor": resultado.get("autor"),
        "imagem_link": resultado.get("link"),
    }


def _montar_queries(titulo: str, tema: Optional[str], categoria: Optional[str]) -> list[str]:
    candidatos = []
    kw = _extrair_palavras_chave(titulo)
    if kw:
        candidatos.append(kw)
    if tema:
        candidatos.append(tema.strip())
    if categoria:
        candidatos.append(_query_para_categoria(categoria))
    candidatos.append("technology")
    vistos = set()
    queries = []
    for q in candidatos:
        chave = q.lower()
        if q and chave not in vistos:
            vistos.add(chave)
            queries.append(q)
    return queries


def buscar_imagem_capa(
    titulo: str = "",
    tema: Optional[str] = None,
    categoria: Optional[str] = None,
) -> Optional[dict]:
    """
    Busca ou gera uma imagem de capa para o artigo.

    Ordem:
      1. Bancos de imagens livres (Unsplash → Pexels → Pixabay → Openverse)
      2. Geração via OpenRouter (Nano Banana 2 Lite)
      3. Stable Diffusion local (se configurado)
      4. Pollinations AI (gratuito, último recurso)
    """
    queries = _montar_queries(titulo, tema, categoria)
    buscadores = (_buscar_no_unsplash, _buscar_no_pexels, _buscar_no_pixabay, _buscar_no_openverse)

    for query in queries:
        for buscador in buscadores:
            resultado = buscador(query)
            if resultado:
                print(f"[Imagem] Sucesso: fonte='{resultado['fonte']}' query='{resultado['query']}'")
                return _padronizar(resultado)

    print(f"[Imagem] Nenhuma imagem encontrada em bancos livres. Tentando geração...")

    query_final = queries[0] if queries else "technology"

    # 2. OpenRouter (Nano Banana)
    resultado = _gerar_no_openrouter(query_final)
    if resultado:
        return _padronizar(resultado)

    # 3. Stable Diffusion local
    resultado = _gerar_no_stable_diffusion(query_final)
    if resultado:
        return _padronizar(resultado)

    # 4. Pollinations (gratuito)
    resultado = _gerar_no_pollinations(query_final)
    if resultado:
        return _padronizar(resultado)

    print("[Imagem] Falha completa: nem busca nem geração funcionaram.")
    return None
