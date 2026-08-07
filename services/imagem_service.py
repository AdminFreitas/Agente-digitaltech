"""
imagem_service.py — Busca (e, em último caso, geração) de imagem de capa gratuita

ESTRATÉGIA DE BUSCA POR CONSULTA (query), da mais específica para a mais genérica:
    1. Palavras-chave extraídas do TÍTULO do artigo
    2. TEMA (se informado)
    3. CATEGORIA (mapeada para uma query em inglês)
    4. "technology" (fallback final de query)

ORDEM DE PRIORIDADE DAS FONTES:

  PARA ARTIGOS:
    1. Openverse (licença aberta, gratuito, sem chave)
    2. Unsplash (requer chave)
    3. Pexels (requer chave)
    4. Pixabay (requer chave)
    5. Pollinations AI (geração — último recurso)

  PARA NOTÍCIAS:
    1. Imagem do feed RSS (foto real da notícia original)
    2. Openverse
    3. Unsplash → Pexels → Pixabay
    4. Pollinations AI (último recurso)

Assim que uma fonte retornar um resultado, a busca para e o resultado é
devolvido — não é feita nenhuma chamada desnecessária às fontes seguintes.

Se NENHUMA combinação de (query x fonte) encontrar uma foto, o serviço cai
para geração de imagem sob demanda via Pollinations AI (não é uma busca,
é geração — sempre "encontra" algo, então é usada como último recurso).

Nunca lança exceção: em caso de falha total, retorna None e o artigo é
publicado sem imagem.

Retorno padronizado (dict) em caso de sucesso:
    {
        "imagem_url":    str,
        "imagem_fonte":  str,   # "RSS" | "Openverse" | "Unsplash" | "Pexels" | "Pixabay" | "Pollinations AI (gerada)"
        "imagem_query":  str,    # a query que efetivamente encontrou/gerou a imagem
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
PEXELS_API_KEY      = os.getenv("PEXELS_API_KEY")
PIXABAY_API_KEY     = os.getenv("PIXABAY_API_KEY")
# Openverse não exige chave para uso básico (requisições anônimas permitidas).

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
    "este", "esta", "esse", "essa", "num", "numa", "nenhum", "nenhuma",
}


def _extrair_palavras_chave(titulo: str, max_palavras: int = 5) -> str:
    """Extrai as palavras mais relevantes do título (remove stopwords, artigos
    e preposições), preservando termos técnicos compostos (ex.: 'HTTP/3',
    "Node.js") e números de versão que normalmente seriam descartados por
    serem curtos demais (ex.: o "17" de "PostgreSQL 17")."""
    if not titulo:
        return ""

    tokens = re.findall(
        r"[A-Za-zçÇãÃõÕáéíóúÁÉÍÓÚâêîôûÂÊÎÔÛ0-9]+(?:[/\.][A-Za-zçÇãÃõÕáéíóúÁÉÍÓÚâêîôûÂÊÎÔÛ0-9]+)*", titulo
    )

    significativas = []
    for tok in tokens:
        tok_lower = tok.lower()

        if tok.isdigit():
            significativas.append(tok)
            continue

        if tok_lower in STOPWORDS_PT:
            continue

        if len(tok) <= 2 and "/" not in tok and "." not in tok:
            continue

        significativas.append(tok)

    if not significativas:
        return ""

    return " ".join(significativas[:max_palavras])


# ---------------------------------------------------------------------------
# Fontes de BUSCA (retornam None se não encontrarem nada ou em caso de erro)
# ---------------------------------------------------------------------------
def _buscar_no_openverse(query: str) -> dict | None:
    """
    Openverse (openverse.org) agrega imagens com licença aberta (Creative
    Commons) de várias fontes. Não exige chave para uso básico.

    CORREÇÃO v2 (2026-08-06):
    - Endpoint confirmado: https://api.openverse.org/v1/images/
    - Adicionado User-Agent para evitar bloqueios
    - Removido license_type que pode causar 404 em algumas queries
    - Adicionado fallback para endpoint alternativo se o primário falhar
    - Melhor tratamento de erro e validação da resposta
    """
    print(f'[Imagem] Buscando "{query}" no Openverse')

    headers = {
        "User-Agent": "DigitalTechBot/1.0 (https://www.digitaltech.digital/)",
        "Accept": "application/json",
    }

    # Tentativa 1: endpoint oficial com parâmetros mínimos
    try:
        resp = httpx.get(
            "https://api.openverse.org/v1/images/",
            params={
                "q": query,
                "page_size": 10,
            },
            headers=headers,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        print(f"[Imagem] Openverse resposta: {resp.status_code}")

        if resp.status_code == 200:
            dados = resp.json()
            resultados = dados.get("results", []) if isinstance(dados, dict) else []
            if resultados:
                foto = random.choice(resultados)
                return {
                    "url": foto.get("url") or foto.get("thumbnail") or foto.get("detail_url"),
                    "autor": foto.get("creator") or "Desconhecido",
                    "link": foto.get("foreign_landing_url") or foto.get("url") or "https://openverse.org",
                    "fonte": "Openverse",
                    "query": query,
                    "alt": foto.get("title") or query,
                }
            print(f"[Imagem] Openverse: nenhum resultado para '{query}'")
            return None

        elif resp.status_code == 404:
            print(f"[Imagem] Openverse 404 — tentando endpoint alternativo...")
        else:
            print(f"[Imagem] Openverse erro HTTP {resp.status_code}: {resp.text[:200]}")

    except httpx.TimeoutException:
        print(f"[Imagem] Openverse timeout para '{query}'")
    except Exception as e:
        print(f"[Imagem] Openverse falhou para '{query}': {e}")

    # Tentativa 2: endpoint alternativo (sem trailing slash, algumas APIs preferem)
    try:
        resp = httpx.get(
            "https://api.openverse.org/v1/images",
            params={"q": query, "page_size": 10},
            headers=headers,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            dados = resp.json()
            resultados = dados.get("results", []) if isinstance(dados, dict) else []
            if resultados:
                foto = random.choice(resultados)
                return {
                    "url": foto.get("url") or foto.get("thumbnail"),
                    "autor": foto.get("creator") or "Desconhecido",
                    "link": foto.get("foreign_landing_url") or foto.get("url") or "https://openverse.org",
                    "fonte": "Openverse",
                    "query": query,
                    "alt": foto.get("title") or query,
                }
    except Exception:
        pass  # já logamos o erro acima

    return None


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


# ---------------------------------------------------------------------------
# Extração de imagem do RSS (para NOTÍCIAS — prioridade máxima)
# ---------------------------------------------------------------------------
def _extrair_imagem_do_rss(url_fonte: str) -> dict | None:
    """
    Tenta extrair a imagem principal (og:image) da página da notícia original.
    Usado como PRIORIDADE 1 para notícias — foto real do evento/notícia.
    """
    if not url_fonte:
        return None
    print(f"[Imagem] Tentando extrair imagem da fonte: {url_fonte}")
    try:
        resp = httpx.get(url_fonte, timeout=10, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text

        # Tenta og:image
        og_match = re.search(r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)[\"']", html, re.IGNORECASE)
        if og_match:
            img_url = og_match.group(1)
            return {
                "url": img_url,
                "autor": "Fonte original",
                "link": url_fonte,
                "fonte": "RSS (og:image)",
                "query": url_fonte,
                "alt": "Imagem da notícia original",
            }

        # Tenta twitter:image
        tw_match = re.search(r"<meta[^>]+name=[\"']twitter:image[\"'][^>]+content=[\"']([^\"']+)[\"']", html, re.IGNORECASE)
        if tw_match:
            img_url = tw_match.group(1)
            return {
                "url": img_url,
                "autor": "Fonte original",
                "link": url_fonte,
                "fonte": "RSS (twitter:image)",
                "query": url_fonte,
                "alt": "Imagem da notícia original",
            }

        # Tenta primeira imagem grande no corpo do artigo
        img_match = re.search(r"<img[^>]+src=[\"'](https?://[^\"']+)[\"'][^>]*>", html, re.IGNORECASE)
        if img_match:
            img_url = img_match.group(1)
            # Evita ícones e imagens pequenas
            if any(x in img_url.lower() for x in ["icon", "logo", "avatar", "button"]):
                return None
            return {
                "url": img_url,
                "autor": "Fonte original",
                "link": url_fonte,
                "fonte": "RSS (imagem no corpo)",
                "query": url_fonte,
                "alt": "Imagem da notícia original",
            }

        return None
    except Exception as e:
        print(f"[Imagem] Falha ao extrair imagem de {url_fonte}: {e}")
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
# Padronização
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

    # remove duplicatas mantendo a ordem de prioridade
    vistos = set()
    queries = []
    for q in candidatos:
        chave = q.lower()
        if q and chave not in vistos:
            vistos.add(chave)
            queries.append(q)

    return queries


# ---------------------------------------------------------------------------
# Função pública — ARTIGOS (sem URL de fonte)
# ---------------------------------------------------------------------------
def buscar_imagem_capa(
    titulo: str = "",
    tema: str | None = None,
    categoria: str | None = None,
) -> dict | None:
    """
    Busca uma imagem de capa para ARTIGOS evergreen.
    Ordem: Openverse → Unsplash → Pexels → Pixabay → Pollinations AI.
    """
    queries = _montar_queries(titulo, tema, categoria)
    buscadores = (
        _buscar_no_openverse,
        _buscar_no_unsplash,
        _buscar_no_pexels,
        _buscar_no_pixabay,
    )

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


# ---------------------------------------------------------------------------
# Função pública — NOTÍCIAS (com URL da fonte RSS)
# ---------------------------------------------------------------------------
def buscar_imagem_noticia(
    titulo: str = "",
    tema: str | None = None,
    categoria: str | None = None,
    url_fonte: str | None = None,
) -> dict | None:
    """
    Busca uma imagem de capa para NOTÍCIAS.
    Ordem: RSS (og:image) → Openverse → Unsplash → Pexels → Pixabay → Pollinations AI.
    """
    # PRIORIDADE 1: extrair imagem da fonte original (foto real da notícia)
    if url_fonte:
        resultado = _extrair_imagem_do_rss(url_fonte)
        if resultado:
            print(f'[Imagem] Sucesso: fonte="{resultado["fonte"]}" url={url_fonte}')
            return _padronizar(resultado)

    # PRIORIDADE 2+: mesma ordem dos artigos, começando pelo Openverse
    return buscar_imagem_capa(titulo=titulo, tema=tema, categoria=categoria)