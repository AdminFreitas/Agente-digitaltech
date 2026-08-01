"""
editor.py -- Agente redator

Duas responsabilidades, uma por fluxo de conteúdo:

- gerar_artigo_base(): para ARTIGOS evergreen. Reaproveita o fallback
  chain de services.llm_service.gerar_artigo() (que já sabe montar
  prompt, tentar os 4 provedores e fazer o parsing).

- gerar_noticia_base(): para NOTÍCIAS. Recebe o material bruto do
  pesquisador (título, resumo, fonte, link vindos de RSS) e REESCREVE
  em texto original via gerar_texto() -- nunca copia o corpo da fonte
  original, só usa como referência factual.

Ambas devolvem o mesmo formato de dict (slug, titulo, categoria,
excerpt, conteudo_markdown), pra revisor.py e seo.py funcionarem sem
precisar saber qual dos dois fluxos gerou o artigo.
"""

import re
import unicodedata

from services.llm_service import gerar_artigo as _gerar_artigo_llm
from services.llm_service import gerar_texto_com_metadados


def gerar_artigo_base(tema: str, categoria: str, briefing: dict | None = None) -> dict:
    """
    Gera o artigo completo. `briefing` (opcional) vem de
    pesquisador.pesquisar_tema() -- hoje ainda nao e injetado no
    prompt (services.llm_service.gerar_artigo nao aceita briefing
    ainda); o parametro existe para nao quebrar a assinatura chamada
    por pipeline/gerar_artigos.py, e fica pronto pra ser usado assim
    que o prompt for ajustado para aproveita-lo.
    """
    return _gerar_artigo_llm(tema, categoria)


def gerar_noticia_base(fonte: dict, categoria: str) -> dict:
    """
    Reescreve uma notícia a partir do material bruto do pesquisador
    (fonte = {"titulo", "resumo", "fonte", "link"} vindos do RSS) em
    texto próprio -- nunca copia frases da fonte original, só usa como
    referência factual. Devolve o mesmo formato de dict usado pelo
    resto do pipeline (slug, titulo, categoria, excerpt,
    conteudo_markdown).
    """
    prompt = f"""Você é um jornalista de tecnologia brasileiro.

Com base SOMENTE nestas informações de uma notícia (nunca copie frases
da fonte -- escreva com suas próprias palavras):

Título original: {fonte['titulo']}
Resumo original: {fonte['resumo']}
Fonte: {fonte['fonte']}

Escreva uma notícia original em português, em Markdown, sobre esse
fato, categoria "{categoria}". Entre 250 e 400 palavras.

Responda EXATAMENTE neste formato de texto simples -- NÃO use JSON e
NÃO use blocos de código (```) envolvendo a resposta:

TITULO: título da notícia aqui, em uma linha
RESUMO: resumo de uma linha, no máximo 120 caracteres
===CORPO===
o texto completo da notícia em markdown vai aqui
"""
    resultado_llm = gerar_texto_com_metadados(prompt)
    dados = _parsear_noticia(resultado_llm["texto"])

    return {
        "slug": _gerar_slug(dados["titulo"]),
        "titulo": dados["titulo"],
        "categoria": categoria,
        "excerpt": dados["excerpt"],
        "conteudo_markdown": dados["corpo"],
        "provedor_llm": resultado_llm["provedor"],
        "modelo_llm": resultado_llm["modelo"],
        "tempo_geracao_ms": resultado_llm["tempo_ms"],
    }


def _remover_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _gerar_slug(titulo: str) -> str:
    slug = unicodedata.normalize("NFD", titulo.lower())
    slug = slug.encode("ascii", "ignore").decode("utf-8")
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return re.sub(r"-+", "-", slug)[:80]


def _parsear_noticia(texto: str) -> dict:
    """
    Mesma lógica de parsing de services.llm_service._parsear_resposta,
    duplicada aqui de propósito (versão simplificada, sem
    TEMPO_LEITURA) pra editor.py não depender de função privada de
    outro módulo. Se um dia isso incomodar, dá pra extrair pra um
    lugar compartilhado -- não é urgente agora.
    """
    texto = texto.strip()
    texto = re.sub(r"^```[a-zA-Z]*\n?", "", texto)
    texto = re.sub(r"\n?```$", "", texto)

    linhas = texto.splitlines()
    titulo = None
    excerpt = ""
    indice_corpo = len(linhas)

    for i, linha_original in enumerate(linhas):
        linha = linha_original.strip()
        if not linha:
            continue
        if linha == "===CORPO===":
            indice_corpo = i + 1
            break

        linha_normalizada = _remover_acentos(linha).upper()
        if linha_normalizada.startswith("TITULO:"):
            titulo = linha.split(":", 1)[1].strip()
            continue
        if linha_normalizada.startswith("RESUMO:"):
            excerpt = linha.split(":", 1)[1].strip()
            continue

        indice_corpo = i
        break

    corpo = "\n".join(linhas[indice_corpo:]).strip()

    if not titulo or not corpo:
        raise ValueError("Resposta incompleta do modelo (faltou título ou corpo) ao gerar notícia")

    return {"titulo": titulo, "excerpt": excerpt, "corpo": corpo}