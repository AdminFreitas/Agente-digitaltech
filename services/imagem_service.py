"""
imagem_service.py — Busca de imagem de capa gratuita

Tenta o Unsplash primeiro; se não encontrar (ou a chave não estiver
configurada), cai para o Pexels. Nunca lança erro — se nenhuma das
duas funcionar, retorna None e o artigo é publicado sem imagem.

Busca várias imagens e escolhe uma aleatoriamente entre elas, para
evitar que todo artigo da mesma categoria saia com a foto idêntica.
"""

import os
import random
import httpx

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

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


def _query_para_categoria(categoria: str) -> str:
    return CATEGORIA_PARA_QUERY.get(categoria.strip().lower(), "technology")


def _buscar_no_unsplash(query: str) -> dict | None:
    if not UNSPLASH_ACCESS_KEY:
        return None
    try:
        resp = httpx.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 10, "orientation": "landscape"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=15,
        )
        resp.raise_for_status()
        resultados = resp.json().get("results", [])
        if not resultados:
            return None
        foto = random.choice(resultados)
        return {
            "url": foto["urls"]["regular"],
            "autor": foto["user"]["name"],
            "link": foto["user"]["links"]["html"],
        }
    except Exception as e:
        print(f"[Imagem] Unsplash falhou: {e}")
        return None


def _buscar_no_pexels(query: str) -> dict | None:
    if not PEXELS_API_KEY:
        return None
    try:
        resp = httpx.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": 10, "orientation": "landscape"},
            headers={"Authorization": PEXELS_API_KEY},
            timeout=15,
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
        }
    except Exception as e:
        print(f"[Imagem] Pexels falhou: {e}")
        return None


def buscar_imagem_capa(categoria: str) -> dict | None:
    """
    Busca uma foto de capa com base na categoria do artigo, escolhida
    aleatoriamente entre várias opções relevantes (evita repetir sempre
    a mesma foto para artigos da mesma categoria).
    """
    query = _query_para_categoria(categoria)

    imagem = _buscar_no_unsplash(query)
    if imagem:
        return imagem

    imagem = _buscar_no_pexels(query)
    if imagem:
        return imagem

    print(f"[Imagem] Nenhuma imagem encontrada para a categoria '{categoria}'.")
    return None
