"""
imagem_service.py — Busca (e, em último caso, geração) de imagem de capa gratuita

Estratégia de busca por CONSULTA (query), da mais específica para a mais genérica:

    1. Palavras-chave extraídas do TÍTULO do artigo
    2. TEMA (se informado)
    3. CATEGORIA (mapeada para uma query em inglês)
    4. "technology" (fallback final de query)

Para CADA uma dessas queries, tenta as fontes nesta ordem:

    1. Unsplash
    2. Pexels
    3. Pixabay
    4. Openverse

Assim que uma fonte retorna um resultado, a busca para e o resultado é
devolvido — não é feita nenhuma chamada desnecessária às fontes seguintes.

Se NENHUMA combinação de (query x fonte) encontrar uma foto, o serviço cai
para geração de imagem sob demanda via Pollinations AI (não é uma busca,
é geração — sempre "encontra" algo, então é usada como último recurso).

Nunca lança exceção: em caso de falha total, retorna None e o artigo é
publicado sem imagem.

Retorno padronizado (dict) em caso de sucesso:
    {
        "imagem_url":    str,
        "imagem_fonte":  str,   # "Unsplash" | "Pexels" | "Pixabay" | "Openverse" | "Pollinations AI (gerada)"
        "imagem_query":  str,   # a query que efetivamente encontrou/gerou a imagem
        "imagem_alt":    str,
        "imagem_autor":  str,
        "imagem_link":   str,
    }
"""

import os
import re
import random
import uuid
from urllib.parse import quote

import httpx

# ---------------------------------------------------------------------------
# Chaves de API
# ---------------------------------------------------------------------------
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
# Openverse e Pollinations não exigem chave para uso básico.
OPENVERSE_CLIENT_ID = os.getenv("OPENVERSE_CLIENT_ID")  # opcional, aumenta limite de requisições

TIMEOUT = 15

# ---------------------------------------------------------------------------
# Mapeamento categoria -> query em inglês (fontes de imagem funcionam melhor
# com termos em inglês)
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


def _query_para_categoria(categoria: str) -> str:
    return CATEGORIA_PARA_QUERY.get(categoria.strip().lower(), "technology")


# ---------------------------------------------------------------------------
# Extração de palavras-chave a partir do título
# ---------------------------------------------------------------------------
STOPWORDS_PT = {
    "a", "as", "o", "os", "um", "uma", "uns", "umas", "de", "do", "da", "dos",
    "das", "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "sob",
    "sobre", "e", "ou", "que", "se", "é", "são", "foi", "ser", "sua", "seu",
    "suas", "seus", "ao", "aos", "à", "às", "como", "mais", "menos", "muito",
    "porque", "por que", "quando", "onde", "qual", "quais", "isso", "isto",
    "este", "esta", "esse", "essa", "num", "numa",
}


def _extrair_palavras_chave(titulo: str, max_palavras: int = 5) -> str:
    """Extrai as palavras mais relevantes do título (remove stopwords, artigos
    e preposições), preservando termos técnicos compostos (ex.: "HTTP/3",
    "Node.js") e números de versão que normalmente seriam descartados por
    serem curtos demais (ex.: o "17" de "PostgreSQL 17")."""
    if not titulo:
        return ""

    # Captura tokens alfanuméricos, incluindo variações como "HTTP/3" ou
    # "Node.js" (letra/número seguido opcionalmente de /x ou .x).
    tokens = re.findall(
        r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+(?:[/.][A-Za-zÀ-ÖØ-öø-ÿ0-9]+)*", titulo
    )

    significativas = []
    for tok in tokens:
        tok_lower = tok.lower()

        # números de versão isolados nunca são descartados por tamanho —
        # só por serem stopword, o que nunca ocorre para números.
        if tok.isdigit():
            significativas.append(tok)
            continue

        if tok_lower in STOPWORDS_PT:
            continue

        # mantém termos curtos que contenham "/" ou "." (ex.: "HTTP/3");
        # descarta palavras curtas comuns (ex.: "de", "ao") com < 3 letras.
        if len(tok) <= 2 and "/" not in tok and "." not in tok:
            continue

        significativas.append(tok)

    if not significativas:
        return ""

    return " ".join(significativas[:max_palavras])


# ---------------------------------------------------------------------------
# Fontes de BUSCA (retornam None se não encontrarem nada ou em caso de erro)
# ---------------------------------------------------------------------------
def _buscar_no_unsplash(query: str) -> dict | None:
    if not UNSPLASH_ACCESS_KEY:
        return None
    print(f'[Imagem] Buscando "{query}" no Unsplash')
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
            # "small"/"small_s3" carregam bem mais rápido que "regular" e
            # têm resolução suficiente para uma capa de blog.
            "url": foto["urls"]["small"],
            "autor": foto["user"]["name"],
            "link": foto["user"]["links"]["html"],
            "fonte": "Unsplash",
            "query": query,
            "alt": foto.get("alt_description") or query,
        }
    except Exception as e:
        print(f"[Imagem] Unsplash falhou para '{query}': {e}")
        return None


def _buscar_no_pexels(query: str) -> dict | None:
    if not PEXELS_API_KEY:
        return None
    print(f'[Imagem] Buscando "{query}" no Pexels')
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
        print(f"[Imagem] Pexels falhou para '{query}': {e}")
        return None


def _buscar_no_pixabay(query: str) -> dict | None:
    if not PIXABAY_API_KEY:
        return None
    print(f'[Imagem] Buscando "{query}" no Pixabay')
    try:
        resp = httpx.get(
            "https://pixabay.com/api/",
            params={
                "key": PIXABAY_API_KEY,
                "q": query,
                "image_type": "photo",
                "orientation": "horizontal",
                "safesearch": "true",
                "per_page": 10,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        fotos = resp.json().get("hits", [])
        if not fotos:
            return None
        foto = random.choice(fotos)
        return {
            # "webformatURL" é bem mais leve que "largeImageURL" e mantém
            # qualidade suficiente para capa de blog.
            "url": foto["webformatURL"],
            "autor": foto["user"],
            "link": foto["pageURL"],
            "fonte": "Pixabay",
            "query": query,
            "alt": foto.get("tags") or query,
        }
    except Exception as e:
        print(f"[Imagem] Pixabay falhou para '{query}': {e}")
        return None


def _buscar_no_openverse(query: str) -> dict | None:
    """Openverse (openverse.org) agrega imagens com licença aberta (Creative
    Commons) de várias fontes. Não exige chave para uso básico, mas respeita
    um client_id opcional para aumentar o limite de requisições."""
    print(f'[Imagem] Buscando "{query}" no Openverse')
    try:
        headers = {}
        if OPENVERSE_CLIENT_ID:
            headers["Authorization"] = f"Bearer {OPENVERSE_CLIENT_ID}"

        resp = httpx.get(
            "https://api.openverse.org/v1/images/search",
            params={
                "q": query,
                # apenas "commercial" (sem exigir "modification") amplia
                # bastante a quantidade de resultados retornados.
                "license_type": "commercial",
                "page_size": 10,
            },
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
        print(f"[Imagem] Openverse falhou para '{query}': {e}")
        return None


# ---------------------------------------------------------------------------
# Geração de imagem (último recurso — não é busca, é criação sob demanda)
# ---------------------------------------------------------------------------
def _gerar_no_pollinations(query: str) -> dict | None:
    """Gera uma imagem via Pollinations AI (image.pollinations.ai) quando
    nenhuma fonte de busca encontrou nada. Não exige chave. A URL retornada
    já serve a imagem diretamente (geração acontece na primeira requisição
    a essa URL)."""
    try:
        tema = query.strip() if query else "technology abstract background"
        prompt = (
            f"Modern technology illustration, {tema}, dark background, "
            f"futuristic, professional, high quality, 16:9"
        )
        # sufixo aleatório para evitar que o cache do Pollinations devolva
        # sempre a mesma imagem para o mesmo tema/query.
        sufixo_anticache = uuid.uuid4().hex[:8]
        prompt_final = f"{prompt} {sufixo_anticache}"

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
        print(f"[Imagem] Pollinations falhou para '{query}': {e}")
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


def _montar_queries(titulo: str, tema: str | None, categoria: str | None) -> list[str]:
    candidatos = []

    kw_titulo = _extrair_palavras_chave(titulo)
    if kw_titulo:
        candidatos.append(kw_titulo)

    if tema:
        candidatos.append(tema.strip())

    if categoria:
        candidatos.append(_query_para_categoria(categoria))

    candidatos.append("technology")

    # remove duplicadas mantendo a ordem de prioridade
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
    tema: str | None = None,
    categoria: str | None = None,
) -> dict | None:
    """
    Busca (ou, em último caso, gera) uma imagem de capa para o artigo.

    Ordem de prioridade das QUERIES: título -> tema -> categoria -> "technology"
    Ordem de prioridade das FONTES, para cada query: Unsplash -> Pexels ->
    Pixabay -> Openverse.

    Se nenhuma combinação encontrar nada, gera uma imagem via Pollinations AI
    usando a query mais específica disponível.

    Retorna um dict padronizado (imagem_url, imagem_fonte, imagem_query,
    imagem_alt, imagem_autor, imagem_link) ou None em caso de falha total.
    """
    queries = _montar_queries(titulo, tema, categoria)
    buscadores = (_buscar_no_unsplash, _buscar_no_pexels, _buscar_no_pixabay, _buscar_no_openverse)

    for query in queries:
        for buscador in buscadores:
            resultado = buscador(query)
            if resultado:
                print(
                    f'[Imagem] Sucesso: fonte="{resultado["fonte"]}" '
                    f'query="{resultado["query"]}"'
                )
                return _padronizar(resultado)

    print(f"[Imagem] Nenhuma imagem encontrada em nenhuma fonte para {queries}. Gerando via Pollinations AI.")

    query_final = queries[0] if queries else "technology"
    resultado = _gerar_no_pollinations(query_final)
    if resultado:
        return _padronizar(resultado)

    print("[Imagem] Falha completa: nem busca nem geração funcionaram.")
    return None