"""
pesquisador.py — Agente de pesquisa

Duas responsabilidades, uma por fluxo de conteúdo. Nunca escreve o
artigo final — só entrega contexto estruturado para o agente editor.py.

- pesquisar_tema(): para ARTIGOS evergreen. O projeto ainda não tem
  nenhuma API de busca configurada, então esta função usa o próprio
  llm_service para expandir o tema recebido em um briefing (ângulo,
  pontos-chave, termos relacionados) — já ajuda o editor a fugir de
  texto genérico, sem depender de nenhuma chave nova.

- pesquisar_noticias(): para NOTÍCIAS. Busca itens recentes em feeds
  RSS públicos de veículos de tecnologia (não exige chave de API).
  Devolve só título, resumo curto e link de cada fonte — o editor.py é
  quem reescreve isso em texto próprio; este agente nunca copia o
  corpo da notícia original.

DEPENDÊNCIA NOVA: pesquisar_noticias() precisa do pacote `feedparser`,
que ainda não está no projeto.
    pip install feedparser --break-system-packages
(ou só `pip install feedparser` dentro do seu .venv)
"""

import re

from services.llm_service import gerar_texto

FEEDS_NOTICIAS_TECH = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://hnrss.org/frontpage",
]


def pesquisar_tema(tema: str, categoria: str) -> dict:
    """
    Expande um tema de artigo evergreen em um briefing de pesquisa:
    ângulo sugerido, pontos-chave a cobrir e termos relacionados.
    Retorna um dict pronto para ser injetado no prompt do editor.py.
    Nunca lança erro por causa de formato — se o modelo não seguir o
    formato esperado, devolve um briefing mínimo baseado só no tema.
    """
    prompt = f"""Você é um pesquisador técnico brasileiro.

Tema do artigo: "{tema}"
Categoria: {categoria}

Gere um briefing curto de pesquisa para um redator escrever sobre esse
tema. Responda EXATAMENTE neste formato, sem Markdown, sem explicações
extras:

ANGULO: uma linha descrevendo o ângulo/abordagem mais interessante
PONTOS_CHAVE: item 1; item 2; item 3; item 4
TERMOS_RELACIONADOS: termo1, termo2, termo3, termo4, termo5
"""
    texto = gerar_texto(prompt)
    return _parsear_briefing(texto, tema)


def _parsear_briefing(texto: str, tema_original: str) -> dict:
    angulo = ""
    pontos_chave: list[str] = []
    termos_relacionados: list[str] = []

    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        chave, _, valor = linha.partition(":")
        chave_normalizada = chave.strip().upper()
        valor = valor.strip()

        if chave_normalizada == "ANGULO":
            angulo = valor
        elif chave_normalizada == "PONTOS_CHAVE":
            pontos_chave = [p.strip() for p in valor.split(";") if p.strip()]
        elif chave_normalizada == "TERMOS_RELACIONADOS":
            termos_relacionados = [t.strip() for t in valor.split(",") if t.strip()]

    return {
        "tema": tema_original,
        "angulo": angulo or tema_original,
        "pontos_chave": pontos_chave,
        "termos_relacionados": termos_relacionados,
    }


def pesquisar_noticias(max_itens: int = 8) -> list[dict]:
    """
    Busca itens recentes nos feeds RSS configurados. Retorna só título,
    resumo curto e link — nunca o corpo completo da notícia original
    (o editor.py reescreve em linguagem própria a partir disso).
    Nunca lança erro: se um feed falhar, é ignorado e a busca continua
    com os demais.
    """
    import feedparser

    candidatos = []
    for url_feed in FEEDS_NOTICIAS_TECH:
        try:
            feed = feedparser.parse(url_feed)
            fonte = feed.feed.get("title", url_feed)
            for entrada in feed.entries[:10]:
                candidatos.append({
                    "titulo": entrada.get("title", "").strip(),
                    "resumo": _limpar_resumo(entrada.get("summary", "")),
                    "link": entrada.get("link", ""),
                    "fonte": fonte,
                    "publicado_em": entrada.get("published", ""),
                    # feedparser normaliza o <guid> do RSS (ou <id> do
                    # Atom) neste atributo; cai pro link se o feed não
                    # tiver guid nenhum, pra nunca ficar vazio à toa.
                    "guid": entrada.get("id") or entrada.get("link", ""),
                })
        except Exception as e:
            print(f"[Pesquisador] Feed '{url_feed}' falhou: {e}")

    candidatos = _remover_duplicadas(candidatos)
    return candidatos[:max_itens]


def _limpar_resumo(html_ou_texto: str, max_chars: int = 300) -> str:
    """Remove tags HTML simples que costumam vir no <summary> do RSS."""
    texto = re.sub(r"<[^>]+>", " ", html_ou_texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:max_chars]


def _remover_duplicadas(itens: list[dict]) -> list[dict]:
    vistos = set()
    unicos = []
    for item in itens:
        chave = item["titulo"].lower().strip()
        if chave and chave not in vistos:
            vistos.add(chave)
            unicos.append(item)
    return unicos


def sugerir_tema(categoria: str, temas_recentes: list[str] | None = None) -> str:
    """
    Sugere um tema novo e específico de artigo evergreen dentro da
    categoria, evitando repetir temas recentes. Existe para a
    automação (cron) não depender de um tema fixo hardcoded a cada
    execução — sem isso, rodar sem supervisão geraria sempre o mesmo
    artigo (e falharia por slug duplicado a partir da 2ª execução).
    """
    from services.llm_service import gerar_texto

    bloqueio = ""
    if temas_recentes:
        lista = "\n".join(f"- {t}" for t in temas_recentes[:15])
        bloqueio = f"\nNÃO repita (nem algo muito parecido com) nenhum destes temas já publicados:\n{lista}\n"

    prompt = f"""Você é um editor de pauta de um blog brasileiro de tecnologia.

Categoria: {categoria}
{bloqueio}
Sugira UM tema específico e interessante para um artigo evergreen
(atemporal) nessa categoria — algo prático, que gere tráfego de busca
orgânica. Não seja genérico demais.

Responda APENAS com o tema, em uma linha, sem numeração, sem aspas,
sem explicação.
"""
    return gerar_texto(prompt).strip().strip('"').strip("'")
