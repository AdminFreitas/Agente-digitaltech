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

MUDANCA DE ARQUITETURA IMPORTANTE (leia antes de mexer em qualquer
outra coisa): a versao anterior de `gerar_artigo_base` delegava tudo
para `services.llm_service.gerar_artigo(tema, categoria)`, que monta
seu proprio prompt internamente e NAO aceita briefing. Isso e
incompativel com o requisito de "usar o briefing quando disponivel".
Por isso, `gerar_artigo_base` passou a construir seu proprio prompt
editorial (igual `gerar_noticia_base` ja fazia) e chamar
`services.llm_service.gerar_texto_com_metadados(prompt)` -- a MESMA
fallback chain de sempre, so que com um prompt escrito aqui dentro,
no editor. Nenhum provedor novo foi adicionado; nenhum sistema de LLM
novo foi criado. `gerar_artigo` do llm_service deixou de ser usado
por este arquivo (ver observacao no final do arquivo).
"""

from __future__ import annotations

import json
import re
import unicodedata

from services.llm_service import gerar_texto_com_metadados

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Regex que identifica um link Markdown: [texto](url)
_RE_LINK_MD = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")

# Regex que identifica um bloco de marcador de imagem:
# [IMAGEM]\ntipo: ...\nassunto: ...\nmotivo: ...\n[/IMAGEM]
_RE_BLOCO_IMAGEM = re.compile(r"\[IMAGEM\](.*?)\[/IMAGEM\]", re.DOTALL)

_CAMPOS_IMAGEM_OBRIGATORIOS = ("tipo", "assunto", "motivo")


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

def gerar_artigo_base(tema: str, categoria: str, briefing: dict | None = None) -> dict:
    """
    Gera um artigo evergreen.

    `briefing` (opcional, vindo de `pesquisador.pesquisar_tema()`) pode
    conter, entre outras coisas: tipo, tema, angulo, pergunta_principal,
    fontes, links, fatos_confirmados, entidades, categoria, contexto.
    Nenhuma dessas chaves e obrigatoria -- o codigo funciona igual com
    briefing=None ou briefing incompleto.
    """
    briefing = briefing or {}
    urls_permitidas = _extrair_urls_permitidas(briefing)

    prompt = _montar_prompt_artigo(tema, categoria, briefing, urls_permitidas)
    resultado_llm = gerar_texto_com_metadados(prompt)
    dados = _parsear_resposta(resultado_llm["texto"], contexto="artigo")

    corpo_validado = _validar_links(dados["corpo"], urls_permitidas)
    corpo_validado = _validar_blocos_imagem(corpo_validado)

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


def gerar_noticia_base(fonte: dict, categoria: str) -> dict:
    """
    Reescreve uma noticia a partir do material bruto do pesquisador
    (fonte = {"titulo", "resumo", "fonte", "link"} vindos do RSS) em
    texto proprio -- nunca copia frases da fonte original, so usa como
    referencia factual.
    """
    if not fonte or not fonte.get("titulo") or not fonte.get("resumo"):
        raise ValueError(
            "gerar_noticia_base: 'fonte' precisa ter pelo menos 'titulo' e "
            "'resumo' preenchidos -- material insuficiente para escrever a noticia"
        )

    url_fonte = fonte.get("link")
    urls_permitidas = {url_fonte} if url_fonte else set()

    prompt = _montar_prompt_noticia(fonte, categoria)
    resultado_llm = gerar_texto_com_metadados(prompt)
    dados = _parsear_resposta(resultado_llm["texto"], contexto="noticia")

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
Responda SOMENTE com um objeto JSON valido, sem crases, sem markdown
ao redor, sem nenhum texto antes ou depois. O JSON deve ter
exatamente estas chaves:

{{
  "titulo": "titulo editorial, uma frase, sem clickbait",
  "resumo": "resumo de no maximo 120 caracteres",
  "corpo_markdown": "o conteudo completo em Markdown, com \\n para quebras de linha"
}}
""".strip()


def _montar_prompt_artigo(
    tema: str, categoria: str, briefing: dict, urls_permitidas: set[str]
) -> str:
    angulo = briefing.get("angulo") or briefing.get("angle")
    pergunta_principal = briefing.get("pergunta_principal")
    fatos = briefing.get("fatos_confirmados") or briefing.get("fatos")
    contexto = briefing.get("contexto")

    partes_briefing = [f"Tema: {tema}", f"Categoria: {categoria}"]
    if angulo:
        partes_briefing.append(f"Angulo editorial sugerido: {angulo}")
    if pergunta_principal:
        partes_briefing.append(f"Pergunta principal do leitor: {pergunta_principal}")
    if fatos:
        partes_briefing.append(f"Fatos confirmados a considerar: {_formatar_lista(fatos)}")
    if contexto:
        partes_briefing.append(f"Contexto adicional: {contexto}")
    if urls_permitidas:
        partes_briefing.append(
            "URLs oficiais/confiaveis disponiveis (use como link SOMENTE se "
            "for editorialmente util, nunca invente outra): "
            + ", ".join(sorted(urls_permitidas))
        )
    else:
        partes_briefing.append(
            "Nenhuma URL confiavel foi fornecida -- NAO inclua nenhum link no texto."
        )

    briefing_formatado = "\n".join(f"- {linha}" for linha in partes_briefing)

    return f"""Voce e o Editor/Redator do blog de tecnologia DigitalTech.

O DigitalTech tem identidade propria: tecnologia, ciberseguranca,
OSINT, privacidade, IA, infraestrutura, programacao, bancos de dados e
casos tecnologicos incomuns -- sempre com apuracao real, nunca com
sensacionalismo ou teoria da conspiracao. Se algo for hipotese ou
especulacao, isso deve ficar claramente identificado como tal no
texto.

Escreva um ARTIGO EVERGREEN (nao e noticia) usando esta pauta:

{briefing_formatado}

Regras editoriais obrigatorias:
- Priorize utilidade pratica, explicacao clara, exemplos e, quando
  fizer sentido, comparacao ou passo a passo.
- O tamanho do texto deve ser o necessario para explicar bem o
  assunto -- nunca encha linguica so para aumentar contagem de
  palavras.
- Use titulos e subtitulos em Markdown (#, ##, ###), listas e blocos
  de codigo (```linguagem) quando fizer sentido.
- Titulo editorial: claro, especifico, sem clickbait, sem exageros.
- Quando mencionar uma ferramenta/produto/documentacao com URL
  fornecida na pauta, pode linkar no formato [texto](url) -- nunca
  invente uma URL que nao esteja na lista acima.
- Quando um ponto do texto se beneficiar muito de uma imagem (ex:
  diagrama de arquitetura, screenshot de uma tela especifica), insira
  um marcador neste formato exato, sem URL nenhuma dentro dele:
  [IMAGEM]
  tipo: diagrama ou screenshot ou foto
  assunto: o que a imagem deveria mostrar
  motivo: por que ela ajuda o leitor aqui
  [/IMAGEM]
  Use isso com moderacao -- so quando realmente agregar.
- Se o assunto envolver opiniao, hipotese ou algo ainda nao
  confirmado, deixe isso explicito no texto (ex: "ainda nao esta
  confirmado se...", "uma hipotese e que...").

{_INSTRUCOES_FORMATO}
"""


def _montar_prompt_noticia(fonte: dict, categoria: str) -> str:
    return f"""Voce e o Editor/Redator do blog de tecnologia DigitalTech,
escrevendo a secao de NOTICIAS.

Material bruto (NUNCA copie frases dele -- escreva 100% com suas
proprias palavras, usando-o so como referencia factual):

- Titulo original: {fonte['titulo']}
- Resumo original: {fonte['resumo']}
- Fonte: {fonte.get('fonte', 'nao informada')}

Categoria: {categoria}

Regras editoriais obrigatorias para NOTICIA (diferente de artigo
evergreen):
- Estruture priorizando: o que aconteceu, quando, quem esta
  envolvido, o que foi confirmado, por que isso importa, quem pode
  ser afetado, contexto necessario e (se aplicavel) o que ainda nao
  foi confirmado.
- NAO invente informacao para preencher o texto. Se o material for
  curto, o texto tambem deve ser curto -- entre 250 e 400 palavras
  APENAS se houver material suficiente para sustentar isso; caso
  contrario, escreva so o que da pra sustentar com o que foi
  fornecido.
- Titulo editorial: claro, especifico, sem clickbait.
- Nao use marcadores de imagem em noticias curtas (a capa ja e
  tratada por outro processo).

{_INSTRUCOES_FORMATO}
"""


def _formatar_lista(valor) -> str:
    if isinstance(valor, (list, tuple, set)):
        return "; ".join(str(item) for item in valor)
    return str(valor)


def _extrair_urls_permitidas(briefing: dict) -> set[str]:
    """
    Coleta todas as URLs que o briefing/pesquisador realmente forneceu,
    de qualquer uma das chaves plausiveis. O Editor so pode linkar
    para URLs presentes neste conjunto -- nunca inventa outra.
    """
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

    return {u for u in urls if isinstance(u, str) and u.startswith(("http://", "https://"))}


# ---------------------------------------------------------------------------
# Parsing da resposta do LLM
# ---------------------------------------------------------------------------

def _parsear_resposta(texto: str, contexto: str) -> dict:
    """
    Faz o parsing da resposta do LLM (esperado: JSON puro, ver
    `_INSTRUCOES_FORMATO`). Tolera o LLM ter envolvido o JSON em
    ```json ... ``` mesmo pedindo pra nao fazer isso, porque isso
    acontece na pratica com alguns provedores.

    Levanta ValueError com mensagem clara em qualquer caso de resposta
    vazia, incompleta ou malformada -- para o pipeline (rodar_agente.py
    / workflow.py) poder tratar isso sem cair de forma opaca.
    """
    if not texto or not texto.strip():
        raise ValueError(f"Resposta vazia do LLM ao gerar {contexto}")

    texto_limpo = texto.strip()
    texto_limpo = re.sub(r"^```[a-zA-Z]*\n?", "", texto_limpo)
    texto_limpo = re.sub(r"\n?```$", "", texto_limpo)
    texto_limpo = texto_limpo.strip()

    try:
        dados_json = json.loads(texto_limpo)
    except json.JSONDecodeError as exc:
        # Fallback: tenta achar o primeiro '{' e o ultimo '}' -- alguns
        # modelos adicionam uma frase de abertura mesmo quando instruidos
        # a nao fazer isso.
        inicio = texto_limpo.find("{")
        fim = texto_limpo.rfind("}")
        if inicio == -1 or fim == -1 or fim <= inicio:
            raise ValueError(
                f"Resposta do LLM nao e um JSON valido ao gerar {contexto}: {exc}"
            ) from exc
        try:
            dados_json = json.loads(texto_limpo[inicio : fim + 1])
        except json.JSONDecodeError as exc2:
            raise ValueError(
                f"Resposta do LLM nao e um JSON valido ao gerar {contexto} "
                f"(nem apos tentativa de recorte): {exc2}"
            ) from exc2

    titulo = (dados_json.get("titulo") or "").strip()
    excerpt = (dados_json.get("resumo") or "").strip()
    corpo = (dados_json.get("corpo_markdown") or "").strip()

    if not titulo or not corpo:
        raise ValueError(
            f"Resposta incompleta do LLM ao gerar {contexto} "
            f"(faltou 'titulo' ou 'corpo_markdown')"
        )

    return {"titulo": titulo, "excerpt": excerpt, "corpo": corpo}


# ---------------------------------------------------------------------------
# Validacao pos-geracao (garante as regras que o prompt sozinho nao garante)
# ---------------------------------------------------------------------------

def _validar_links(corpo_markdown: str, urls_permitidas: set[str]) -> str:
    """
    Remove (transforma em texto simples) qualquer link Markdown cuja
    URL nao esteja em `urls_permitidas`. Isso e reforco de codigo para
    a regra "nunca invente URLs" -- nao confia so no prompt.
    """
    if not urls_permitidas:
        # Sem nenhuma URL permitida: nenhum link deveria existir.
        return _RE_LINK_MD.sub(lambda m: m.group(1), corpo_markdown)

    def _substituir(match: re.Match) -> str:
        texto_link, url = match.group(1), match.group(2)
        if url in urls_permitidas:
            return match.group(0)
        return texto_link  # derruba o link, mantem so o texto visivel

    return _RE_LINK_MD.sub(_substituir, corpo_markdown)


def _validar_blocos_imagem(corpo_markdown: str) -> str:
    """
    Remove marcadores [IMAGEM]...[/IMAGEM] malformados (que nao trazem
    os tres campos esperados), para nao passar lixo adiante para o
    revisor/seo/publicacao.
    """

    def _checar(match: re.Match) -> str:
        conteudo = match.group(1)
        tem_todos_campos = all(
            re.search(rf"{campo}\s*:", conteudo, re.IGNORECASE)
            for campo in _CAMPOS_IMAGEM_OBRIGATORIOS
        )
        return match.group(0) if tem_todos_campos else ""

    return _RE_BLOCO_IMAGEM.sub(_checar, corpo_markdown)


# ---------------------------------------------------------------------------
# Slug
# ---------------------------------------------------------------------------

def _remover_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _gerar_slug(titulo: str) -> str:
    slug = unicodedata.normalize("NFD", titulo.lower())
    slug = slug.encode("ascii", "ignore").decode("utf-8")
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return re.sub(r"-+", "-", slug)[:80]
