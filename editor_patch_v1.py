"""
editor.py -- Agente Editor / Redator  (PATCH v1: debug + fallback de chaves)

Mudancas:
  1. Debug print no ponto do ValueError (incompleta) mostrando chaves reais
  2. Fallback de chaves alternativas no parser (corpo, conteudo, texto, body)
  3. Fallback de chaves para resumo (excerpt, summary, descricao)
"""

from __future__ import annotations

import json
import re
import unicodedata

from services.llm_service import gerar_texto_com_metadados


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_RE_LINK_MD = re.compile(
    r"\[([^\]]+)\]\((https?://[^\s)]+)\)"
)

_RE_BLOCO_IMAGEM = re.compile(
    r"\[IMAGEM\](.*?)\[/IMAGEM\]",
    re.DOTALL | re.IGNORECASE,
)

_CAMPOS_IMAGEM_OBRIGATORIOS = (
    "tipo",
    "assunto",
    "motivo",
)


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

def gerar_artigo_base(
    tema: str,
    categoria: str,
    briefing: dict | None = None,
) -> dict:
    briefing = briefing or {}
    urls_permitidas = _extrair_urls_permitidas(briefing)

    prompt = _montar_prompt_artigo(
        tema,
        categoria,
        briefing,
        urls_permitidas,
    )

    resultado_llm = gerar_texto_com_metadados(prompt)

    dados = _parsear_resposta(
        resultado_llm["texto"],
        contexto="artigo",
    )

    corpo_validado = _validar_links(
        dados["corpo"],
        urls_permitidas,
    )

    corpo_validado = _validar_blocos_imagem(
        corpo_validado,
    )

    return {
        "slug": _gerar_slug(dados["titulo"]),
        "titulo": dados["titulo"],
        "categoria": categoria,
        "excerpt": dados["excerpt"],
        "conteudo_markdown": corpo_validado,
        "provedor_llm": resultado_llm["provedor"],
        "modelo_llm": resultado_llm["modelo"],
        "tempo_geracao_ms": resultado_llm["tempo_ms"],
    }


def gerar_noticia_base(
    fonte: dict,
    categoria: str,
) -> dict:
    if (
        not fonte
        or not fonte.get("titulo")
        or not fonte.get("resumo")
    ):
        raise ValueError(
            "gerar_noticia_base: 'fonte' precisa ter pelo menos "
            "'titulo' e 'resumo' preenchidos -- material insuficiente "
            "para escrever a noticia"
        )

    url_fonte = fonte.get("link")
    urls_permitidas = {url_fonte} if url_fonte else set()

    prompt = _montar_prompt_noticia(fonte, categoria)
    resultado_llm = gerar_texto_com_metadados(prompt)

    dados = _parsear_resposta(
        resultado_llm["texto"],
        contexto="noticia",
    )

    corpo_validado = _validar_links(dados["corpo"], urls_permitidas)

    return {
        "slug": _gerar_slug(dados["titulo"]),
        "titulo": dados["titulo"],
        "categoria": categoria,
        "excerpt": dados["excerpt"],
        "conteudo_markdown": corpo_validado,
        "provedor_llm": resultado_llm["provedor"],
        "modelo_llm": resultado_llm["modelo"],
        "tempo_geracao_ms": resultado_llm["tempo_ms"],
    }


# ---------------------------------------------------------------------------
# Construcao de prompts
# ---------------------------------------------------------------------------

_INSTRUCOES_FORMATO = """
Responda SOMENTE com um objeto JSON valido.

NAO use bloco de codigo Markdown.
NAO use ```json.
NAO escreva nenhuma frase antes do JSON.
NAO escreva nenhuma frase depois do JSON.

O JSON deve ter exatamente estas tres chaves:

{
  "titulo": "titulo editorial, uma frase, sem clickbait",
  "resumo": "resumo de no maximo 120 caracteres",
  "corpo_markdown": "conteudo completo em Markdown"
}

IMPORTANTE SOBRE O CAMPO "corpo_markdown":

O valor de "corpo_markdown" deve ser uma STRING JSON valida.

Portanto, quebras de linha dentro dessa string devem ser representadas
com \\n.

Exemplo valido:

{
  "titulo": "Exemplo",
  "resumo": "Resumo do artigo",
  "corpo_markdown": "# Titulo\\n\\n## Introducao\\n\\nTexto do artigo."
}

NAO coloque quebras de linha literais dentro de uma string JSON.
""".strip()


def _montar_prompt_artigo(
    tema: str,
    categoria: str,
    briefing: dict,
    urls_permitidas: set[str],
) -> str:

    angulo = briefing.get("angulo") or briefing.get("angle")
    pergunta_principal = briefing.get("pergunta_principal")
    fatos = briefing.get("fatos_confirmados") or briefing.get("fatos")
    contexto = briefing.get("contexto")

    partes_briefing = [
        f"Tema: {tema}",
        f"Categoria: {categoria}",
    ]

    if angulo:
        partes_briefing.append(f"Angulo editorial sugerido: {angulo}")
    if pergunta_principal:
        partes_briefing.append(f"Pergunta principal do leitor: {pergunta_principal}")
    if fatos:
        partes_briefing.append(
            "Fatos confirmados a considerar: " + _formatar_lista(fatos)
        )
    if contexto:
        partes_briefing.append(f"Contexto adicional: {contexto}")

    if urls_permitidas:
        partes_briefing.append(
            "URLs oficiais/confiaveis disponiveis "
            "(use como link SOMENTE se for editorialmente "
            "util, nunca invente outra): "
            + ", ".join(sorted(urls_permitidas))
        )
    else:
        partes_briefing.append(
            "Nenhuma URL confiavel foi fornecida -- "
            "NAO inclua nenhum link no texto."
        )

    briefing_formatado = "\n".join(f"- {linha}" for linha in partes_briefing)

    return f"""Voce e o Editor/Redator do blog de tecnologia DigitalTech.

O DigitalTech tem identidade propria:

- tecnologia
- ciberseguranca
- OSINT
- privacidade
- inteligencia artificial
- infraestrutura
- programacao
- bancos de dados
- casos tecnologicos incomuns

Sempre trabalhe com apuracao real.

Nunca use sensacionalismo.
Nunca apresente teoria da conspiracao como fato.
Se algo for hipotese ou especulacao, deixe isso claramente
identificado no texto.

Escreva um ARTIGO EVERGREEN.
Nao e uma noticia.

Use esta pauta:

{briefing_formatado}

Regras editoriais obrigatorias:

- Priorize utilidade pratica.
- Explique os conceitos de maneira clara.
- Use exemplos praticos quando fizer sentido.
- Use comparacoes quando forem uteis.
- Use passo a passo quando o assunto permitir.
- O tamanho deve ser suficiente para explicar o assunto.
- Nao encha linguica apenas para aumentar a quantidade de palavras.
- Use titulos e subtitulos em Markdown.
- Use listas quando ajudarem a leitura.
- Use blocos de codigo quando forem realmente necessarios.
- O titulo deve ser claro, especifico e sem clickbait.
- Nunca invente fatos.
- Nunca invente URLs.
- So utilize URLs presentes na lista fornecida.
- Se nenhuma URL foi fornecida, nao coloque links externos.

Marcadores de imagem:

Quando uma imagem realmente ajudar o leitor, use EXATAMENTE este formato:

[IMAGEM]
tipo: diagrama
assunto: descricao objetiva da imagem
motivo: explicacao de por que a imagem ajuda o leitor
[/IMAGEM]

Os valores permitidos para "tipo" sao:

- diagrama
- screenshot
- foto

NAO use:

[IMAGEM: diagrama

NAO use marcadores incompletos.

Use imagens com moderacao.

Se o assunto envolver opiniao, hipotese ou algo ainda nao confirmado,
dejixe isso explicitamente claro no texto.

{_INSTRUCOES_FORMATO}
"""


def _montar_prompt_noticia(fonte: dict, categoria: str) -> str:
    return f"""Voce e o Editor/Redator do blog de tecnologia DigitalTech,
escrevendo a secao de NOTICIAS.

Material bruto:

Titulo original:
{fonte['titulo']}

Resumo original:
{fonte['resumo']}

Fonte:
{fonte.get('fonte', 'nao informada')}

IMPORTANTE:

NUNCA copie frases do material original.

Escreva com suas proprias palavras.
Use o material somente como referencia factual.

Categoria:
{categoria}

Regras editoriais obrigatorias:

- Explique primeiro o que aconteceu.
- Informe quando aconteceu, se essa informacao estiver disponivel.
- Identifique quem esta envolvido.
- Separe claramente o que foi confirmado do que ainda nao foi confirmado.
- Explique por que o acontecimento importa.
- Explique quem pode ser afetado.
- Acrescente apenas contexto que possa ser sustentado pelo material.
- NAO invente informacao.
- Se o material for curto, o texto tambem deve ser curto.
- Nao invente detalhes para atingir uma quantidade de palavras.
- Titulo claro e especifico.
- Sem clickbait.
- Nao utilize marcador de imagem em noticia curta.

{_INSTRUCOES_FORMATO}
"""


# ---------------------------------------------------------------------------
# Utilitarios
# ---------------------------------------------------------------------------

def _formatar_lista(valor) -> str:
    if isinstance(valor, (list, tuple, set)):
        return "; ".join(str(item) for item in valor)
    return str(valor)


def _extrair_urls_permitidas(briefing: dict) -> set[str]:
    urls: set[str] = set()
    for chave in ("links", "urls", "fontes"):
        valor = briefing.get(chave)
        if not valor:
            continue
        if isinstance(valor, str):
            urls.add(valor)
        elif isinstance(valor, (list, tuple, set)):
            for item in valor:
                if isinstance(item, str):
                    urls.add(item)
                elif isinstance(item, dict) and item.get("url"):
                    urls.add(item["url"])
                elif isinstance(item, dict) and item.get("link"):
                    urls.add(item["link"])
    link_unico = briefing.get("link")
    if isinstance(link_unico, str):
        urls.add(link_unico)
    return {
        url for url in urls
        if isinstance(url, str) and url.startswith(("http://", "https://"))
    }


# ---------------------------------------------------------------------------
# Parsing da resposta do LLM  (PATCH: debug + fallback de chaves)
# ---------------------------------------------------------------------------

def _sanitizar_controle_json(texto: str) -> str:
    resultado = []
    dentro_string = False
    escapado = False

    for caractere in texto:
        if dentro_string:
            if escapado:
                resultado.append(caractere)
                escapado = False
                continue
            if caractere == "\\":
                resultado.append(caractere)
                escapado = True
                continue
            if caractere == '"':
                resultado.append(caractere)
                dentro_string = False
                continue
            codigo = ord(caractere)
            if caractere == "\n":
                resultado.append("\\n")
                continue
            if caractere == "\r":
                resultado.append("\\r")
                continue
            if caractere == "\t":
                resultado.append("\\t")
                continue
            if codigo < 0x20:
                continue
            resultado.append(caractere)
            continue

        if caractere == '"':
            resultado.append(caractere)
            dentro_string = True
            continue
        resultado.append(caractere)

    return "".join(resultado)


def _extrair_json_de_resposta(texto: str) -> str:
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?\s*", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s*```$", "", texto)
    texto = texto.strip()

    inicio = texto.find("{")
    if inicio == -1:
        return texto

    profundidade = 0
    dentro_string = False
    escapado = False

    for indice in range(inicio, len(texto)):
        caractere = texto[indice]
        if dentro_string:
            if escapado:
                escapado = False
                continue
            if caractere == "\\":
                escapado = True
                continue
            if caractere == '"':
                dentro_string = False
            continue
        if caractere == '"':
            dentro_string = True
            continue
        if caractere == "{":
            profundidade += 1
        elif caractere == "}":
            profundidade -= 1
            if profundidade == 0:
                return texto[inicio : indice + 1]

    return texto[inicio:]


# ---------------------------------------------------------------------------
# NOVO: Fallback de chaves alternativas
# ---------------------------------------------------------------------------

_CHAVES_TITULO = ("titulo", "title", "titulo_do_artigo", "headline")
_CHAVES_RESUMO = ("resumo", "excerpt", "summary", "descricao", "description")
_CHAVES_CORPO = (
    "corpo_markdown",
    "corpo",
    "conteudo",
    "conteudo_markdown",
    "texto",
    "body",
    "markdown",
    "content",
)


def _extrair_campo_com_fallback(dados: dict, chaves_esperadas: tuple[str, ...]) -> str:
    """
    Tenta extrair um valor string de 'dados' usando varias chaves candidatas.
    Retorna a primeira que existir e nao for vazia.
    """
    for chave in chaves_esperadas:
        valor = dados.get(chave)
        if valor is not None:
            texto = str(valor).strip()
            if texto:
                return texto
    return ""


def _parsear_resposta(texto: str, contexto: str) -> dict:
    if not texto or not texto.strip():
        raise ValueError(f"Resposta vazia do LLM ao gerar {contexto}")

    texto_limpo = texto.strip()
    texto_limpo = re.sub(r"^```(?:json)?\s*", "", texto_limpo, flags=re.IGNORECASE)
    texto_limpo = re.sub(r"\s*```$", "", texto_limpo, flags=re.IGNORECASE)
    texto_limpo = texto_limpo.strip()

    inicio = texto_limpo.find("{")
    fim = texto_limpo.rfind("}")

    if inicio != -1 and fim != -1 and fim > inicio:
        texto_json = texto_limpo[inicio : fim + 1]
    else:
        texto_json = texto_limpo

    texto_json = _sanitizar_controle_json(texto_json)

    try:
        dados_json = json.loads(texto_json)
    except json.JSONDecodeError:
        try:
            dados_json = _extrair_campos_json_tolerante(texto_json)
        except Exception as exc:
            print("\n--- RESPOSTA BRUTA DO LLM (falha no parse) ---")
            print(texto_json[:5000])
            print("--- FIM DA RESPOSTA BRUTA ---\n")
            raise ValueError(
                f"Resposta do LLM nao e um JSON valido ao gerar {contexto}: {exc}"
            ) from exc

    if not isinstance(dados_json, dict):
        raise ValueError(
            f"Resposta do LLM ao gerar {contexto} nao e um objeto JSON."
        )

    # ------------------------------------------------------------------
    # PATCH: extracao com fallback de chaves alternativas + DEBUG
    # ------------------------------------------------------------------
    titulo = _extrair_campo_com_fallback(dados_json, _CHAVES_TITULO)
    excerpt = _extrair_campo_com_fallback(dados_json, _CHAVES_RESUMO)
    corpo = _extrair_campo_com_fallback(dados_json, _CHAVES_CORPO)

    if not titulo or not corpo:
        print("\n========== DEBUG _parsear_resposta ==========")
        print(f"Contexto: {contexto}")
        print(f"Chaves encontradas no JSON: {list(dados_json.keys())}")
        print(f"Tamanho do texto bruto: {len(texto_limpo)} chars")
        print("--- TEXTO BRUTO (primeiros 3000 chars) ---")
        print(texto_limpo[:3000])
        print("--- FIM DO DEBUG ----------\n")
        raise ValueError(
            f"Resposta incompleta do LLM ao gerar {contexto}: "
            f"faltou 'titulo' ou 'corpo_markdown' (chaves presentes: {list(dados_json.keys())})"
        )

    return {
        "titulo": titulo,
        "excerpt": excerpt,
        "corpo": corpo,
    }


def _extrair_campos_json_tolerante(texto: str) -> dict:
    def _extrair_string(campo: str, inicio_busca: int = 0):
        padrao = re.search(
            rf'"{re.escape(campo)}"\s*:',
            texto[inicio_busca:],
            flags=re.IGNORECASE,
        )
        if not padrao:
            raise ValueError(f"campo '{campo}' nao encontrado")

        inicio_valor = inicio_busca + padrao.end()
        while inicio_valor < len(texto) and texto[inicio_valor].isspace():
            inicio_valor += 1

        if inicio_valor >= len(texto) or texto[inicio_valor] != '"':
            raise ValueError(f"campo '{campo}' nao possui valor string")

        inicio_conteudo = inicio_valor + 1
        campos_seguintes = ("titulo", "resumo", "corpo_markdown")
        proximo_campo_pos = len(texto)

        for outro_campo in campos_seguintes:
            if outro_campo == campo:
                continue
            resultado = re.search(
                rf'"\s*,?\s*"{re.escape(outro_campo)}"\s*:',
                texto[inicio_conteudo:],
                flags=re.IGNORECASE,
            )
            if resultado:
                pos = inicio_conteudo + resultado.start()
                if pos < proximo_campo_pos:
                    proximo_campo_pos = pos

        if campo == "corpo_markdown":
            fim_conteudo = texto.rfind("}")
            if fim_conteudo == -1:
                fim_conteudo = len(texto)
            trecho = texto[inicio_conteudo:fim_conteudo]
            trecho = trecho.rstrip()
            if trecho.endswith('"'):
                trecho = trecho[:-1]
            return trecho, fim_conteudo

        trecho = texto[inicio_conteudo:proximo_campo_pos]
        trecho = trecho.rstrip()
        if trecho.endswith(","):
            trecho = trecho[:-1].rstrip()
        if trecho.endswith('"'):
            trecho = trecho[:-1]
        return trecho, proximo_campo_pos

    titulo, pos_titulo = _extrair_string("titulo")
    resumo, pos_resumo = _extrair_string("resumo", pos_titulo)
    corpo, _ = _extrair_string("corpo_markdown", pos_resumo)

    titulo = titulo.strip()
    resumo = resumo.strip()
    corpo = corpo.strip()

    if not titulo:
        raise ValueError("titulo vazio")
    if not corpo:
        raise ValueError("corpo_markdown vazio")

    return {
        "titulo": titulo,
        "resumo": resumo,
        "corpo_markdown": corpo,
    }


# ---------------------------------------------------------------------------
# Validacao pos-geracao
# ---------------------------------------------------------------------------

def _validar_links(corpo_markdown: str, urls_permitidas: set[str]) -> str:
    if not urls_permitidas:
        return _RE_LINK_MD.sub(lambda match: match.group(1), corpo_markdown)

    def _substituir(match: re.Match) -> str:
        texto_link = match.group(1)
        url = match.group(2)
        if url in urls_permitidas:
            return match.group(0)
        return texto_link

    return _RE_LINK_MD.sub(_substituir, corpo_markdown)


def _validar_blocos_imagem(corpo_markdown: str) -> str:
    def _checar(match: re.Match) -> str:
        conteudo = match.group(1)
        tem_todos_campos = all(
            re.search(
                rf"^\s*{campo}\s*:",
                conteudo,
                re.IGNORECASE | re.MULTILINE,
            )
            for campo in _CAMPOS_IMAGEM_OBRIGATORIOS
        )
        if not tem_todos_campos:
            return ""
        return match.group(0)

    return _RE_BLOCO_IMAGEM.sub(_checar, corpo_markdown)


# ---------------------------------------------------------------------------
# Slug
# ---------------------------------------------------------------------------

def _gerar_slug(titulo: str) -> str:
    slug = unicodedata.normalize("NFD", titulo.lower())
    slug = slug.encode("ascii", "ignore").decode("utf-8")
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug[:80].strip("-")