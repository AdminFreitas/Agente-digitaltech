"""
editor.py -- Agente Editor / Redator

Papel na redação:

    PESQUISADOR -> EDITOR-CHEFE -> [EDITOR / REDATOR] -> REVISOR -> SEO/GEO -> PUBLICACAO

O Editor recebe uma pauta/briefing (artigo) ou um material bruto de
RSS (noticia) e produz conteudo editorial: define angulo, estrutura,
escreve o texto, insere links apenas quando ha URL confiavel
disponivel, e indica pontos de imagem quando isso realmente ajuda o
leitor.

Duas funcoes publicas, uma por fluxo de conteudo -- mesma interface
de sempre, para nao quebrar `pipeline/gerar_artigos.py`,
`pipeline/gerar_noticias.py`, `revisor.py` e `seo.py`:

    gerar_artigo_base(tema, categoria, briefing=None) -> dict
    gerar_noticia_base(fonte, categoria) -> dict

Ambas devolvem o mesmo formato de dict:

    {
        "slug": str,
        "titulo": str,
        "categoria": str,
        "excerpt": str,
        "conteudo_markdown": str,
        "provedor_llm": str,
        "modelo_llm": str,
        "tempo_geracao_ms": int | float,
    }

IMPORTANTE:
A versao anterior de `gerar_artigo_base` delegava tudo para
`services.llm_service.gerar_artigo(tema, categoria)`, que monta seu
proprio prompt internamente e nao aceita briefing.

Por isso, `gerar_artigo_base` constroi seu proprio prompt editorial
e chama `services.llm_service.gerar_texto_com_metadados(prompt)`.

Nenhum provedor novo foi adicionado.
"""

from __future__ import annotations

import json
import re
import unicodedata

from services.llm_service import gerar_texto_com_metadados


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Regex que identifica um link Markdown:
# [texto](https://exemplo.com)
_RE_LINK_MD = re.compile(
    r"\[([^\]]+)\]\((https?://[^\s)]+)\)"
)

# Regex que identifica um bloco de marcador de imagem:
#
# [IMAGEM]
# tipo: diagrama
# assunto: ...
# motivo: ...
# [/IMAGEM]
#
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
    """
    Gera um artigo evergreen.

    `briefing` (opcional, vindo de `pesquisador.pesquisar_tema()`) pode
    conter, entre outras coisas:

        tipo
        tema
        angulo
        pergunta_principal
        fontes
        links
        fatos_confirmados
        entidades
        categoria
        contexto

    Nenhuma dessas chaves e obrigatoria.
    """

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
    """
    Reescreve uma noticia a partir do material bruto do pesquisador.

    `fonte` deve conter pelo menos:

        titulo
        resumo

    O texto produzido e proprio e nao copia frases da fonte original.
    """

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

    urls_permitidas = (
        {url_fonte}
        if url_fonte
        else set()
    )

    prompt = _montar_prompt_noticia(
        fonte,
        categoria,
    )

    resultado_llm = gerar_texto_com_metadados(prompt)

    dados = _parsear_resposta(
        resultado_llm["texto"],
        contexto="noticia",
    )

    corpo_validado = _validar_links(
        dados["corpo"],
        urls_permitidas,
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

    angulo = (
        briefing.get("angulo")
        or briefing.get("angle")
    )

    pergunta_principal = briefing.get(
        "pergunta_principal"
    )

    fatos = (
        briefing.get("fatos_confirmados")
        or briefing.get("fatos")
    )

    contexto = briefing.get("contexto")

    partes_briefing = [
        f"Tema: {tema}",
        f"Categoria: {categoria}",
    ]

    if angulo:
        partes_briefing.append(
            f"Angulo editorial sugerido: {angulo}"
        )

    if pergunta_principal:
        partes_briefing.append(
            f"Pergunta principal do leitor: "
            f"{pergunta_principal}"
        )

    if fatos:
        partes_briefing.append(
            "Fatos confirmados a considerar: "
            f"{_formatar_lista(fatos)}"
        )

    if contexto:
        partes_briefing.append(
            f"Contexto adicional: {contexto}"
        )

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

    briefing_formatado = "\n".join(
        f"- {linha}"
        for linha in partes_briefing
    )

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
deixe isso explicitamente claro no texto.

{_INSTRUCOES_FORMATO}
"""


def _montar_prompt_noticia(
    fonte: dict,
    categoria: str,
) -> str:

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
        return "; ".join(
            str(item)
            for item in valor
        )

    return str(valor)


def _extrair_urls_permitidas(
    briefing: dict,
) -> set[str]:
    """
    Coleta todas as URLs fornecidas pelo pesquisador.

    O Editor somente pode utilizar URLs presentes neste conjunto.
    """

    urls: set[str] = set()

    for chave in (
        "links",
        "urls",
        "fontes",
    ):
        valor = briefing.get(chave)

        if not valor:
            continue

        if isinstance(valor, str):
            urls.add(valor)

        elif isinstance(
            valor,
            (list, tuple, set),
        ):
            for item in valor:

                if isinstance(item, str):
                    urls.add(item)

                elif (
                    isinstance(item, dict)
                    and item.get("url")
                ):
                    urls.add(item["url"])

                elif (
                    isinstance(item, dict)
                    and item.get("link")
                ):
                    urls.add(item["link"])

    link_unico = briefing.get("link")

    if isinstance(link_unico, str):
        urls.add(link_unico)

    return {
        url
        for url in urls
        if isinstance(url, str)
        and url.startswith(
            ("http://", "https://")
        )
    }


# ---------------------------------------------------------------------------
# Parsing da resposta do LLM
# ---------------------------------------------------------------------------

def _sanitizar_controle_json(texto: str) -> str:
    """
    Corrige caracteres de controle crus encontrados DENTRO de strings
    JSON produzidas por LLMs.

    CORRECAO IMPORTANTE:

    Nao transforma quebras de linha estruturais do JSON.

    Exemplo:

        {
          "titulo": "Exemplo",
          "corpo": "linha 1
        linha 2"
        }

    A quebra de linha dentro da string precisa virar:

        {
          "titulo": "Exemplo",
          "corpo": "linha 1\\nlinha 2"
        }

    Mas as quebras de linha entre propriedades JSON devem permanecer
    normais.

    Esta funcao tambem preserva sequencias de escape JSON existentes,
    como:

        \\n
        \\r
        \\t
        \\"
        \\\\

    """

    resultado = []
    dentro_string = False
    escapado = False

    for caractere in texto:

        # ---------------------------------------------------------------
        # Estamos dentro de uma string JSON
        # ---------------------------------------------------------------
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
                # Outros controles nao sao validos dentro de strings JSON.
                # Remove para evitar quebra do parser.
                continue

            resultado.append(caractere)
            continue

        # ---------------------------------------------------------------
        # Fora de uma string JSON
        # ---------------------------------------------------------------

        if caractere == '"':
            resultado.append(caractere)
            dentro_string = True
            continue

        # Fora de string, preservamos a estrutura original.
        resultado.append(caractere)

    return "".join(resultado)


def _extrair_json_de_resposta(texto: str) -> str:
    """
    Remove sujeira comum adicionada por LLMs antes/depois do JSON.

    Exemplos aceitos:

        ```json
        {...}
        ```

        Aqui esta o JSON:
        {...}

    A funcao procura o primeiro objeto JSON e retorna apenas seu
    conteudo candidato.
    """

    texto = texto.strip()

    # Remove bloco Markdown de codigo quando existir.
    texto = re.sub(
        r"^```(?:json)?\s*",
        "",
        texto,
        flags=re.IGNORECASE,
    )

    texto = re.sub(
        r"\s*```$",
        "",
        texto,
    )

    texto = texto.strip()

    inicio = texto.find("{")

    if inicio == -1:
        return texto

    # Procura o fechamento correto do objeto JSON, respeitando strings.
    profundidade = 0
    dentro_string = False
    escapado = False

    for indice in range(
        inicio,
        len(texto),
    ):
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
                return texto[
                    inicio : indice + 1
                ]

    # Nao encontrou fechamento.
    return texto[inicio:]


def _parsear_resposta(
    texto: str,
    contexto: str,
) -> dict:
    """
    Faz o parsing da resposta do LLM.

    O LLM deve retornar:
        {
            "titulo": "...",
            "resumo": "...",
            "corpo_markdown": "..."
        }

    O parser tolera alguns problemas comuns de modelos pequenos,
    especialmente:
      - blocos ```json ... ```
      - texto antes/depois do JSON
      - quebras de linha cruas dentro de strings
      - aspas duplas não escapadas dentro do corpo Markdown

    A prioridade é preservar o conteúdo do artigo sem aceitar uma
    resposta estruturalmente inválida.
    """

    if not texto or not texto.strip():
        raise ValueError(
            f"Resposta vazia do LLM ao gerar {contexto}"
        )

    texto_limpo = texto.strip()

    # ---------------------------------------------------------------
    # 1. Remove cercas Markdown caso o modelo tenha usado:
    #
    # ```json
    # {...}
    # ```
    # ---------------------------------------------------------------
    texto_limpo = re.sub(
        r"^```(?:json)?\s*",
        "",
        texto_limpo,
        flags=re.IGNORECASE,
    )

    texto_limpo = re.sub(
        r"\s*```$",
        "",
        texto_limpo,
        flags=re.IGNORECASE,
    )

    texto_limpo = texto_limpo.strip()

    # ---------------------------------------------------------------
    # 2. Se o modelo colocou texto antes/depois do JSON,
    #    tenta isolar o objeto principal.
    # ---------------------------------------------------------------
    inicio = texto_limpo.find("{")
    fim = texto_limpo.rfind("}")

    if inicio != -1 and fim != -1 and fim > inicio:
        texto_json = texto_limpo[inicio : fim + 1]
    else:
        texto_json = texto_limpo

    # ---------------------------------------------------------------
    # 3. Primeira tentativa:
    #    JSON normal, depois de corrigir caracteres de controle.
    # ---------------------------------------------------------------
    texto_json = _sanitizar_controle_json(
        texto_json
    )

    try:
        dados_json = json.loads(
            texto_json
        )

    except json.JSONDecodeError:
        # -----------------------------------------------------------
        # 4. Segunda tentativa:
        #
        # Alguns modelos pequenos produzem:
        #
        # "corpo_markdown": "texto com "aspas" internas"
        #
        # Isso quebra o JSON.
        #
        # Em vez de tentar corrigir o JSON inteiro de forma cega,
        # reconstruímos especificamente os três campos esperados.
        # -----------------------------------------------------------

        try:
            dados_json = _extrair_campos_json_tolerante(
                texto_json
            )

        except Exception as exc:
            print(
                "\n--- RESPOSTA BRUTA DO LLM (falha no parse) ---"
            )
            print(texto_json[:5000])
            print("--- FIM DA RESPOSTA BRUTA ---\n")

            raise ValueError(
                f"Resposta do LLM nao e um JSON valido ao gerar "
                f"{contexto}: {exc}"
            ) from exc

    # ---------------------------------------------------------------
    # 5. O resultado precisa ser um objeto JSON.
    # ---------------------------------------------------------------
    if not isinstance(dados_json, dict):
        raise ValueError(
            f"Resposta do LLM ao gerar {contexto} "
            f"nao e um objeto JSON."
        )

    # ---------------------------------------------------------------
    # 6. Extrai os campos esperados.
    # ---------------------------------------------------------------
    titulo = str(
        dados_json.get("titulo") or ""
    ).strip()

    excerpt = str(
        dados_json.get("resumo") or ""
    ).strip()

    corpo = str(
        dados_json.get("corpo_markdown") or ""
    ).strip()

    # ---------------------------------------------------------------
    # 7. Validação mínima.
    # ---------------------------------------------------------------
    if not titulo:
        raise ValueError(
            f"Resposta incompleta do LLM ao gerar {contexto}: "
            f"faltou 'titulo'"
        )

    if not corpo:
        raise ValueError(
            f"Resposta incompleta do LLM ao gerar {contexto}: "
            f"faltou 'corpo_markdown'"
        )

    return {
        "titulo": titulo,
        "excerpt": excerpt,
        "corpo": corpo,
    }


def _extrair_campos_json_tolerante(texto: str) -> dict:
    """
    Extrai os campos esperados de uma resposta que deveria ser JSON,
    mas possui pequenas violações causadas por modelos locais pequenos.

    Espera os campos:

        "titulo": "..."
        "resumo": "..."
        "corpo_markdown": "..."

    A função não tenta interpretar JSON arbitrário. Ela é deliberadamente
    limitada ao contrato usado pelo Editor.
    """

    def _extrair_string(campo: str, inicio_busca: int = 0):
        """
        Localiza:

            "campo":

        e lê seu valor até o fechamento correto da string.

        Aspas internas são aceitas quando não representam o início de
        outro campo JSON.
        """

        padrao = re.search(
            rf'"{re.escape(campo)}"\s*:',
            texto[inicio_busca:],
            flags=re.IGNORECASE,
        )

        if not padrao:
            raise ValueError(
                f"campo '{campo}' nao encontrado"
            )

        inicio_valor = inicio_busca + padrao.end()

        # Ignora espaços.
        while (
            inicio_valor < len(texto)
            and texto[inicio_valor].isspace()
        ):
            inicio_valor += 1

        if (
            inicio_valor >= len(texto)
            or texto[inicio_valor] != '"'
        ):
            raise ValueError(
                f"campo '{campo}' nao possui valor string"
            )

        inicio_conteudo = inicio_valor + 1

        # Procura o próximo campo conhecido.
        campos_seguintes = (
            "titulo",
            "resumo",
            "corpo_markdown",
        )

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

        # Para o último campo, usamos o último } do objeto.
        if campo == "corpo_markdown":
            fim_conteudo = texto.rfind("}")

            if fim_conteudo == -1:
                fim_conteudo = len(texto)

            # Remove eventual fechamento da string.
            trecho = texto[inicio_conteudo:fim_conteudo]

            trecho = trecho.rstrip()

            if trecho.endswith('"'):
                trecho = trecho[:-1]

            return trecho, fim_conteudo

        # Para titulo/resumo, o próximo campo marca o fim.
        trecho = texto[inicio_conteudo:proximo_campo_pos]

        trecho = trecho.rstrip()

        # Remove vírgula separadora.
        if trecho.endswith(","):
            trecho = trecho[:-1].rstrip()

        # Remove aspas finais.
        if trecho.endswith('"'):
            trecho = trecho[:-1]

        return trecho, proximo_campo_pos

    titulo, pos_titulo = _extrair_string(
        "titulo"
    )

    resumo, pos_resumo = _extrair_string(
        "resumo",
        pos_titulo,
    )

    corpo, _ = _extrair_string(
        "corpo_markdown",
        pos_resumo,
    )

    # ---------------------------------------------------------------
    # Normalização final.
    # ---------------------------------------------------------------

    titulo = titulo.strip()
    resumo = resumo.strip()
    corpo = corpo.strip()

    if not titulo:
        raise ValueError(
            "titulo vazio"
        )

    if not corpo:
        raise ValueError(
            "corpo_markdown vazio"
        )

    return {
        "titulo": titulo,
        "resumo": resumo,
        "corpo_markdown": corpo,
    }

# ---------------------------------------------------------------------------
# Validacao pos-geracao
# ---------------------------------------------------------------------------

def _validar_links(
    corpo_markdown: str,
    urls_permitidas: set[str],
) -> str:
    """
    Remove qualquer link Markdown cuja URL nao esteja autorizada.
    """

    if not urls_permitidas:
        return _RE_LINK_MD.sub(
            lambda match: match.group(1),
            corpo_markdown,
        )

    def _substituir(
        match: re.Match,
    ) -> str:

        texto_link = match.group(1)
        url = match.group(2)

        if url in urls_permitidas:
            return match.group(0)

        return texto_link

    return _RE_LINK_MD.sub(
        _substituir,
        corpo_markdown,
    )


def _validar_blocos_imagem(
    corpo_markdown: str,
) -> str:
    """
    Mantem somente blocos [IMAGEM] completos e estruturados.

    Exemplo aceito:

    [IMAGEM]
    tipo: diagrama
    assunto: arquitetura de uma API
    motivo: ajuda a visualizar o fluxo
    [/IMAGEM]
    """

    def _checar(
        match: re.Match,
    ) -> str:

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

    return _RE_BLOCO_IMAGEM.sub(
        _checar,
        corpo_markdown,
    )


# ---------------------------------------------------------------------------
# Slug
# ---------------------------------------------------------------------------

def _gerar_slug(
    titulo: str,
) -> str:
    """
    Gera slug ASCII seguro para URL.
    """

    slug = unicodedata.normalize(
        "NFD",
        titulo.lower(),
    )

    slug = slug.encode(
        "ascii",
        "ignore",
    ).decode(
        "utf-8"
    )

    slug = re.sub(
        r"[^a-z0-9\s-]",
        "",
        slug,
    )

    slug = re.sub(
        r"\s+",
        "-",
        slug.strip(),
    )

    slug = re.sub(
        r"-+",
        "-",
        slug,
    )

    return slug[:80].strip("-")