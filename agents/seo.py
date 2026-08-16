"""
agents/seo.py — Agente SEO + GEO Profissional

Recebe o artigo já revisado e gera metadados de SEO e GEO:
  • keyword principal e secundárias
  • intenção de busca
  • título SEO otimizado
  • meta description informativa
  • tags relevantes
  • Open Graph (título + descrição)
  • alt da imagem descritivo
  • entidades identificadas
  • perguntas respondidas pelo conteúdo
  • scores internos (seo_score, geo_score)
  • validação programática com fallbacks

NÃO altera:
  • slug     → preserva URL pública
  • conteudo_markdown → responsabilidade do editor/revisor

NÃO inventa:
  • fontes, estatísticas, citações, especialistas

Compatibilidade:
  Mantém os campos legados (titulo_seo, meta_description, tags,
  og_titulo, imagem_alt) e adiciona novos sem breaking changes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any

from services.llm_service import gerar_texto


# ═══════════════════════════════════════════════════════════════
# Constantes
# ═══════════════════════════════════════════════════════════════

TITULO_SEO_MIN = 30
TITULO_SEO_MAX = 65
META_DESC_MIN = 120
META_DESC_MAX = 165
TAGS_MIN = 5
TAGS_MAX = 8
OG_TITULO_MAX = 90
OG_DESC_MAX = 200
ALT_MIN = 10
ALT_MAX = 150

INTENCOES_VALIDAS = frozenset(
    {"informacional", "navegacional", "transacional", "investigacional", "noticiosa"}
)

TAGS_GENERICAS_PROIBIDAS = frozenset(
    {
        "tecnologia", "artigo", "notícia", "noticia",
        "informação", "informacao", "blog", "digitaltech",
        "news", "post", "conteúdo", "conteudo",
        "dica", "dicas", "guia", "tutorial",
    }
)

CTAS_GENERICOS_PROIBIDOS = frozenset(
    {
        "leia mais", "saiba tudo", "confira agora",
        "descubra tudo", "veja mais", "clique aqui",
        "não perca", "imperdível", "urgente",
        "saiba mais", "confira", "não perca",
    }
)

CLICKBAIT_PATTERNS = re.compile(
    r"você não vai acreditar|descubra tudo|o que ninguém|"
    r"urgente!!!?|imperdível|não perca|chocante|surpreendente",
    re.IGNORECASE,
)


# ═══════════════════════════════════════════════════════════════
# Estrutura de dados interna
# ═══════════════════════════════════════════════════════════════

@dataclass
class _SeoGeoResult:
    """Resultado estruturado do agente SEO + GEO (uso interno)."""

    keyword_principal: str = ""
    keywords_secundarias: list[str] = field(default_factory=list)
    intencao_busca: str = "informacional"
    titulo_seo: str = ""
    meta_description: str = ""
    tags: list[str] = field(default_factory=list)
    og_titulo: str = ""
    og_description: str = ""
    imagem_alt: str = ""
    perguntas_respondidas: list[str] = field(default_factory=list)
    entidades: list[str] = field(default_factory=list)
    seo_score: int = 0
    geo_score: int = 0
    problemas: list[str] = field(default_factory=list)
    slug_sugestao: str = ""  # informativo — NUNCA aplicado automaticamente

    def to_flat_dict(self) -> dict[str, Any]:
        """Exporta para dict plano (compatível com artigo)."""
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
# Prompts
# ═══════════════════════════════════════════════════════════════

_PROMPT_SEO_GEO = """Você é um especialista sênior em SEO técnico e otimização para busca generativa (GEO).
Sua tarefa é analisar o artigo fornecido e produzir metadados estruturados em JSON.

REGRAS FUNDAMENTAIS:
1. NUNCA invente estatísticas, fontes, especialistas, citações ou eventos.
2. NUNCA use clickbait, palavras como "URGENTE", "Você Não Vai Acreditar", "Descubra Tudo".
3. O título SEO deve ser claro, específico, natural e ter entre 50–60 caracteres quando possível.
4. A meta description deve resumir o conteúdo, ser específica, ter 140–160 caracteres e NÃO conter CTA genérico como "Leia mais!" ou "Saiba tudo!".
5. Tags devem ser 5–8, relacionadas ao conteúdo, priorizando entidades, tecnologias e conceitos. NÃO use tags genéricas como "tecnologia", "artigo", "notícia", "blog", "digitaltech".
6. OG title pode ser ligeiramente mais chamativo que o título SEO, mas sem sensacionalismo. OG description complementa o título.
7. Alt da imagem deve descrever objetivamente a imagem, NUNCA repetir o título do artigo genericamente.
8. GEO: identifique entidades (pessoas, empresas, produtos, tecnologias, organizações, países, eventos) e perguntas que o conteúdo responde.
9. Intenção de busca: informacional, navegacional, transacional, investigacional ou noticiosa.
10. NÃO altere o slug. Se quiser sugerir algo, coloque em slug_sugestao apenas como informativo.
11. NÃO reescreva o conteúdo do artigo.

FORMATO DE RESPOSTA — JSON ESTRITO, sem markdown, sem explicações:

{{
  "keyword_principal": "string",
  "keywords_secundarias": ["string", "string"],
  "intencao_busca": "informacional|navegacional|transacional|investigacional|noticiosa",
  "titulo_seo": "string (50–65 chars)",
  "meta_description": "string (120–165 chars)",
  "tags": ["string", "string"],
  "og_titulo": "string (até 90 chars)",
  "og_description": "string (até 200 chars)",
  "imagem_alt": "string descritivo da imagem",
  "perguntas_respondidas": ["string", "string"],
  "entidades": ["string", "string"],
  "slug_sugestao": "string informativa apenas"
}}

ARTIGO PARA ANÁLISE:
Tipo: {tipo}
Título editorial: {titulo}
Categoria: {categoria}
Slug atual: {slug}
Excerpt: {excerpt}

Conteúdo (primeiros 2000 caracteres):
{conteudo_preview}

{imagem_contexto}

Gere o JSON agora."""


# ═══════════════════════════════════════════════════════════════
# API pública
# ═══════════════════════════════════════════════════════════════

def otimizar_seo(artigo: dict, imagem: dict | None = None) -> dict:
    """
    Recebe um dict de artigo e, opcionalmente, o dict retornado por
    imagem_service.buscar_imagem_capa().

    Devolve uma CÓPIA do artigo com metadados SEO + GEO adicionados,
    sem alterar `conteudo_markdown` nem `slug`.
    Não modifica o dict recebido.
    """
    # ── 1. Preparar contexto ──────────────────────────────────
    tipo = artigo.get("tipo", "artigo")
    titulo = artigo.get("titulo", "")
    categoria = artigo.get("categoria", "")
    slug = artigo.get("slug", "")
    excerpt = artigo.get("excerpt", "")
    conteudo = artigo.get("conteudo_markdown", "")
    conteudo_preview = conteudo[:2000]

    imagem_contexto = ""
    if imagem:
        desc = imagem.get("descricao", "")
        alt_atual = imagem.get("imagem_alt", "")
        if desc:
            imagem_contexto = f"\nImagem da capa: {desc}"
        if alt_atual:
            imagem_contexto += f"\nAlt atual da imagem: {alt_atual}"

    # ── 2. Prompt para o LLM ─────────────────────────────────
    prompt = _PROMPT_SEO_GEO.format(
        tipo=tipo,
        titulo=titulo,
        categoria=categoria,
        slug=slug,
        excerpt=excerpt,
        conteudo_preview=conteudo_preview,
        imagem_contexto=imagem_contexto,
    )

    # ── 3. Chamar LLM e fazer parsing ────────────────────────
    try:
        texto_resposta = gerar_texto(prompt)
    except Exception:
        texto_resposta = ""

    resultado = _parsear_resposta_llm(texto_resposta)

    # ── 4. Fallback para campos vazios/inválidos ─────────────
    resultado = _aplicar_fallbacks(resultado, artigo, imagem)

    # ── 5. Forçar intenção correta para notícias ─────────────
    if tipo == "noticia":
        resultado.intencao_busca = "noticiosa"

    # ── 6. Validação programática + scores ───────────────────
    resultado = _validar_e_score(resultado, artigo, imagem)

    # ── 7. Montar artigo otimizado ────────────────────────────
    artigo_otimizado = dict(artigo)
    artigo_otimizado.update(resultado.to_flat_dict())

    # Garantias finais de imutabilidade
    artigo_otimizado["slug"] = artigo.get("slug", "")
    artigo_otimizado["conteudo_markdown"] = artigo.get("conteudo_markdown", "")

    return artigo_otimizado


# ═══════════════════════════════════════════════════════════════
# Parsing da resposta do LLM
# ═══════════════════════════════════════════════════════════════

def _parsear_resposta_llm(texto: str) -> _SeoGeoResult:
    """Tenta extrair JSON estruturado; usa fallback de texto simples se falhar."""
    texto = (texto or "").strip()
    if not texto:
        return _SeoGeoResult(problemas=["Resposta do LLM vazia"])

    # Tentar extrair JSON
    json_str = _extrair_json(texto)
    if json_str:
        try:
            dados = json.loads(json_str)
            return _preencher_do_dict(dados)
        except json.JSONDecodeError:
            pass

    # Fallback: parser de texto simples (compatibilidade com formato antigo)
    resultado = _parsear_texto_simples(texto)
    resultado.problemas.append("Resposta do LLM não foi JSON válido; usado parser de fallback")
    return resultado


def _extrair_json(texto: str) -> str | None:
    """Extrai bloco JSON da resposta, tolerante a markdown."""
    # Tentar ```json ... ```
    match = re.search(r"```json\s*(\{.*?\})\s*```", texto, re.DOTALL)
    if match:
        return match.group(1)

    # Tentar ``` ... ```
    match = re.search(r"```\s*(\{.*?\})\s*```", texto, re.DOTALL)
    if match:
        return match.group(1)

    # Tentar JSON puro — procurar o bloco { ... } mais profundo possível
    # Estratégia: encontrar o primeiro '{' e o último '}' correspondente
    inicio = texto.find("{")
    if inicio == -1:
        return None

    # Contar chaves para encontrar o fechamento correto
    profundidade = 0
    fim = -1
    for i, ch in enumerate(texto[inicio:], start=inicio):
        if ch == "{":
            profundidade += 1
        elif ch == "}":
            profundidade -= 1
            if profundidade == 0:
                fim = i
                break

    if fim != -1:
        candidato = texto[inicio : fim + 1]
        # Verificação rápida de sanidade
        if candidato.count("{") == candidato.count("}"):
            return candidato

    return None


def _preencher_do_dict(dados: dict) -> _SeoGeoResult:
    """Preenche _SeoGeoResult a partir de um dict (vindo do JSON do LLM)."""

    def _lista(val: Any) -> list[str]:
        if isinstance(val, list):
            return [str(v).strip() for v in val if str(v).strip()]
        if isinstance(val, str):
            return [v.strip() for v in val.split(",") if v.strip()]
        return []

    return _SeoGeoResult(
        keyword_principal=str(dados.get("keyword_principal", "")).strip(),
        keywords_secundarias=_lista(dados.get("keywords_secundarias", [])),
        intencao_busca=str(dados.get("intencao_busca", "informacional")).strip().lower(),
        titulo_seo=str(dados.get("titulo_seo", "")).strip(),
        meta_description=str(dados.get("meta_description", "")).strip(),
        tags=_lista(dados.get("tags", [])),
        og_titulo=str(dados.get("og_titulo", "")).strip(),
        og_description=str(dados.get("og_description", "")).strip(),
        imagem_alt=str(dados.get("imagem_alt", "")).strip(),
        perguntas_respondidas=_lista(dados.get("perguntas_respondidas", [])),
        entidades=_lista(dados.get("entidades", [])),
        slug_sugestao=str(dados.get("slug_sugestao", "")).strip(),
    )


def _parsear_texto_simples(texto: str) -> _SeoGeoResult:
    """Parser de fallback para formato texto simples (compatibilidade legada)."""
    resultado = _SeoGeoResult()

    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or ":" not in linha:
            continue

        chave, _, valor = linha.partition(":")
        chave_norm = chave.strip().upper().replace(" ", "_")
        valor = valor.strip()

        if not valor:
            continue

        if chave_norm in ("TITULO_SEO", "TITULO-SEO"):
            resultado.titulo_seo = valor
        elif chave_norm in ("META_DESCRIPTION", "META-DESCRIPTION", "DESCRIPTION"):
            resultado.meta_description = valor
        elif chave_norm in ("TAGS", "TAG"):
            resultado.tags = [t.strip() for t in valor.split(",") if t.strip()]
        elif chave_norm in ("OPEN_GRAPH_TITULO", "OG_TITULO", "OG:TITLE", "OG_TITLE"):
            resultado.og_titulo = valor
        elif chave_norm in ("OPEN_GRAPH_DESCRIPTION", "OG_DESCRIPTION", "OG:DESCRIPTION", "OG_DESC"):
            resultado.og_description = valor
        elif chave_norm in ("IMAGEM_ALT", "IMAGE_ALT", "ALT", "ALT_TEXT"):
            resultado.imagem_alt = valor
        elif chave_norm in ("KEYWORD_PRINCIPAL", "KEYWORD", "PALAVRA_CHAVE"):
            resultado.keyword_principal = valor
        elif chave_norm in ("KEYWORDS_SECUNDARIAS", "KEYWORDS", "PALAVRAS_CHAVE"):
            resultado.keywords_secundarias = [t.strip() for t in valor.split(",") if t.strip()]
        elif chave_norm in ("INTENCAO_BUSCA", "INTENCAO", "INTENT"):
            resultado.intencao_busca = valor.lower()
        elif chave_norm in ("PERGUNTAS_RESPONDIDAS", "PERGUNTAS", "QUESTIONS"):
            resultado.perguntas_respondidas = [t.strip() for t in valor.split(",") if t.strip()]
        elif chave_norm in ("ENTIDADES", "ENTITIES"):
            resultado.entidades = [t.strip() for t in valor.split(",") if t.strip()]
        elif chave_norm in ("SLUG_SUGESTAO", "SLUG"):
            resultado.slug_sugestao = valor

    return resultado


# ═══════════════════════════════════════════════════════════════
# Fallbacks seguros
# ═══════════════════════════════════════════════════════════════

def _aplicar_fallbacks(
    resultado: _SeoGeoResult, artigo: dict, imagem: dict | None
) -> _SeoGeoResult:
    """Aplica fallbacks seguros quando o LLM retorna campos vazios ou inválidos."""
    titulo = artigo.get("titulo", "")
    excerpt = artigo.get("excerpt", "")
    conteudo = artigo.get("conteudo_markdown", "")

    # ── Título SEO ──
    if not resultado.titulo_seo:
        resultado.titulo_seo = _truncar(titulo, TITULO_SEO_MAX)
        resultado.problemas.append("titulo_seo vazio; usado fallback do título editorial")

    # ── Meta description ──
    if not resultado.meta_description:
        if excerpt and len(excerpt) >= META_DESC_MIN:
            resultado.meta_description = _truncar(excerpt, META_DESC_MAX)
        elif excerpt:
            resultado.meta_description = excerpt
        else:
            preview = _extrair_texto_plano(conteudo)[:META_DESC_MAX]
            resultado.meta_description = _truncar(preview, META_DESC_MAX)
        resultado.problemas.append("meta_description vazia; usado fallback")

    # ── OG title ──
    if not resultado.og_titulo:
        resultado.og_titulo = resultado.titulo_seo or titulo
        resultado.problemas.append("og_titulo vazio; usado fallback")

    # ── OG description ──
    if not resultado.og_description:
        resultado.og_description = resultado.meta_description or excerpt
        resultado.problemas.append("og_description vazio; usado fallback")

    # ── Tags ──
    if not resultado.tags:
        resultado.tags = _gerar_tags_fallback(titulo, artigo.get("categoria", ""))
        resultado.problemas.append("tags vazias; usado fallback por categoria")

    # ── Alt da imagem ──
    if not resultado.imagem_alt:
        desc_img = (imagem or {}).get("descricao", "")
        if desc_img:
            resultado.imagem_alt = desc_img
        else:
            resultado.imagem_alt = f"Imagem relacionada a: {titulo}"
        resultado.problemas.append("imagem_alt vazio; usado fallback")

    # ── Keyword principal ──
    if not resultado.keyword_principal:
        resultado.keyword_principal = _extrair_keyword_do_titulo(titulo)
        resultado.problemas.append("keyword_principal vazia; usado fallback")

    # ── Intenção de busca ──
    tipo = artigo.get("tipo", "artigo")
    if resultado.intencao_busca not in INTENCOES_VALIDAS:
        if tipo == "noticia":
            resultado.intencao_busca = "noticiosa"
        else:
            resultado.intencao_busca = "informacional"
        resultado.problemas.append(
            f"intencao_busca inválida; usado fallback \"{resultado.intencao_busca}\""
        )

    # ── Keywords secundárias ──
    if not resultado.keywords_secundarias:
        resultado.keywords_secundarias = []

    # ── Perguntas respondidas ──
    if not resultado.perguntas_respondidas:
        resultado.perguntas_respondidas = []

    # ── Entidades ──
    if not resultado.entidades:
        resultado.entidades = []

    return resultado


def _gerar_tags_fallback(titulo: str, categoria: str) -> list[str]:
    """Gera tags básicas de fallback quando o LLM falha."""
    tags: list[str] = []
    if categoria and categoria.lower() not in TAGS_GENERICAS_PROIBIDAS:
        tags.append(categoria)

    # Extrair palavras técnicas do título (CamelCase e siglas)
    palavras = re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|\b[A-Z]{2,}\b", titulo)
    for p in palavras:
        p = p.strip()
        if len(p) > 2 and p.lower() not in TAGS_GENERICAS_PROIBIDAS:
            tags.append(p)

    # Deduplicar preservando ordem
    vistos: set[str] = set()
    tags_unicas: list[str] = []
    for t in tags:
        tl = t.lower()
        if tl not in vistos:
            vistos.add(tl)
            tags_unicas.append(t)

    return tags_unicas[:TAGS_MAX] if tags_unicas else ["tecnologia"]


def _extrair_keyword_do_titulo(titulo: str) -> str:
    """Extrai uma keyword razoável do título."""
    stopwords = {
        "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das",
        "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "sobre",
        "entre", "durante", "após", "antes", "que", "como", "quando", "onde",
        "veja", "tudo", "sobre", "novo", "nova", "novos", "novas", "principais",
        "veja", "confira", "saiba", "descubra", "entenda", "guia", "completo",
        "tudo", "sobre", "como", "funciona", "passo", "passo",
    }
    palavras = [
        p for p in re.findall(r"\b\w+\b", titulo.lower())
        if p not in stopwords and len(p) > 2
    ]
    if palavras:
        return " ".join(palavras[:3])
    return titulo[:40]


def _extrair_texto_plano(markdown: str) -> str:
    """Remove sintaxe markdown básica para extrair texto plano."""
    texto = re.sub(r"!?\[([^\]]+)\]\([^\)]+\)", r"\1", markdown)  # links e imagens
    texto = re.sub(r"[#*_~>|\-`]|\d+\.", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _truncar(texto: str, max_chars: int) -> str:
    """Trunca texto no limite de caracteres, respeitando palavras."""
    if len(texto) <= max_chars:
        return texto
    truncado = texto[:max_chars]
    ultimo_espaco = truncado.rfind(" ")
    if ultimo_espaco > max_chars * 0.7:
        truncado = truncado[:ultimo_espaco]
    return truncado.rstrip(".,;:") + "..."


# ═══════════════════════════════════════════════════════════════
# Validação programática e cálculo de scores
# ═══════════════════════════════════════════════════════════════

def _validar_e_score(
    resultado: _SeoGeoResult, artigo: dict, imagem: dict | None
) -> _SeoGeoResult:
    """Valida todos os campos e calcula seo_score e geo_score."""
    problemas = list(resultado.problemas)
    seo_pontos = 0
    seo_max = 0
    geo_pontos = 0
    geo_max = 0

    # ── TÍTULO SEO (0–20) ──
    seo_max += 20
    ts = resultado.titulo_seo
    if ts:
        if TITULO_SEO_MIN <= len(ts) <= TITULO_SEO_MAX:
            seo_pontos += 15
        elif len(ts) <= TITULO_SEO_MAX + 10:
            seo_pontos += 10
        else:
            problemas.append(f"titulo_seo muito longo ({len(ts)} chars)")
        if not CLICKBAIT_PATTERNS.search(ts):
            seo_pontos += 5
        else:
            problemas.append("titulo_seo contém possível clickbait")
    else:
        problemas.append("titulo_seo está vazio")

    # ── META DESCRIPTION (0–20) ──
    seo_max += 20
    md = resultado.meta_description
    if md:
        if META_DESC_MIN <= len(md) <= META_DESC_MAX:
            seo_pontos += 15
        elif len(md) >= 80:
            seo_pontos += 10
        else:
            problemas.append(f"meta_description muito curta ({len(md)} chars)")
        if not any(p in md.lower() for p in CTAS_GENERICOS_PROIBIDOS):
            seo_pontos += 5
        else:
            problemas.append("meta_description contém CTA genérico proibido")
    else:
        problemas.append("meta_description está vazia")

    # ── TAGS (0–15) ──
    seo_max += 15
    tags = resultado.tags
    if tags:
        if TAGS_MIN <= len(tags) <= TAGS_MAX:
            seo_pontos += 8
        else:
            problemas.append(f"quantidade de tags fora do ideal ({len(tags)})")

        tags_norm = [t.strip().lower() for t in tags]
        tags_unicas = []
        vistos: set[str] = set()
        for t in tags_norm:
            if t not in vistos:
                vistos.add(t)
                tags_unicas.append(t)
        if len(tags_unicas) == len(tags_norm):
            seo_pontos += 4
        else:
            problemas.append("tags contêm duplicatas")

        genericas = [t for t in tags_norm if t in TAGS_GENERICAS_PROIBIDAS]
        if not genericas:
            seo_pontos += 3
        else:
            problemas.append(f"tags genéricas detectadas: {genericas}")

        resultado.tags = tags_unicas
    else:
        problemas.append("tags estão vazias")

    # ── OPEN GRAPH (0–10) ──
    seo_max += 10
    if resultado.og_titulo and len(resultado.og_titulo) <= OG_TITULO_MAX:
        seo_pontos += 5
    else:
        problemas.append("og_titulo vazio ou muito longo")
    if resultado.og_description and len(resultado.og_description) <= OG_DESC_MAX:
        seo_pontos += 5
    else:
        problemas.append("og_description vazio ou muito longo")

    # ── ALT DA IMAGEM (0–10) ──
    seo_max += 10
    alt = resultado.imagem_alt
    if alt:
        if ALT_MIN <= len(alt) <= ALT_MAX:
            seo_pontos += 6
        else:
            problemas.append(f"imagem_alt fora do tamanho ideal ({len(alt)} chars)")
        if alt.lower() != artigo.get("titulo", "").lower():
            seo_pontos += 4
        else:
            problemas.append("imagem_alt é cópia do título do artigo")
    else:
        problemas.append("imagem_alt está vazio")

    # ── KEYWORD E INTENÇÃO (0–15) ──
    seo_max += 15
    if resultado.keyword_principal:
        seo_pontos += 8
        kw = resultado.keyword_principal.lower()
        if kw in resultado.titulo_seo.lower() or kw in resultado.meta_description.lower():
            seo_pontos += 4
        else:
            problemas.append("keyword_principal não presente em título ou description")
    else:
        problemas.append("keyword_principal vazia")
    if resultado.intencao_busca in INTENCOES_VALIDAS:
        seo_pontos += 3
    else:
        problemas.append("intencao_busca inválida")

    # ── GEO: ENTIDADES (0–25) ──
    geo_max += 25
    if resultado.entidades:
        if len(resultado.entidades) >= 3:
            geo_pontos += 15
        elif len(resultado.entidades) >= 1:
            geo_pontos += 8
    else:
        problemas.append("nenhuma entidade identificada (GEO)")

    # ── GEO: PERGUNTAS RESPONDIDAS (0–25) ──
    geo_max += 25
    if resultado.perguntas_respondidas:
        if len(resultado.perguntas_respondidas) >= 2:
            geo_pontos += 15
        elif len(resultado.perguntas_respondidas) >= 1:
            geo_pontos += 8
    else:
        problemas.append("nenhuma pergunta respondida identificada (GEO)")

    # ── GEO: ESTRUTURA DO CONTEÚDO (0–25) ──
    geo_max += 25
    conteudo = artigo.get("conteudo_markdown", "")
    if conteudo:
        subtitulos = len(re.findall(r"^#{2,3}\s+", conteudo, re.MULTILINE))
        if subtitulos >= 3:
            geo_pontos += 8
        elif subtitulos >= 1:
            geo_pontos += 4
        else:
            problemas.append("conteúdo sem subtítulos suficientes (GEO)")

        if re.search(r"^[-*]\s+", conteudo, re.MULTILINE):
            geo_pontos += 5
        else:
            problemas.append("conteúdo sem listas (GEO)")

        paragrafos = [p for p in conteudo.split("\n\n") if p.strip()]
        paragrafos_curtos = sum(1 for p in paragrafos if len(p) < 300)
        if paragrafos and paragrafos_curtos / len(paragrafos) >= 0.5:
            geo_pontos += 7
        else:
            problemas.append("parágrafos muito longos (GEO)")

        primeiro_bloco = _extrair_texto_plano(conteudo)[:500]
        if primeiro_bloco and len(primeiro_bloco) > 50:
            geo_pontos += 5
        else:
            problemas.append("introdução muito curta ou ausente (GEO)")
    else:
        problemas.append("conteudo_markdown vazio (GEO)")

    # ── GEO: EVIDÊNCIAS E FONTES (0–25) ──
    geo_max += 25
    if re.search(r"https?://", conteudo):
        geo_pontos += 10
    else:
        problemas.append("nenhuma fonte externa/link detectada (GEO)")

    if re.search(r"\b\d{1,3}(?:[.,]\d+)?%?\b", conteudo):
        geo_pontos += 8
    else:
        problemas.append("nenhum dado numérico no conteúdo (GEO)")

    if re.search(r"(?:é|significa|refere-se|definido como)\s+", conteudo, re.IGNORECASE):
        geo_pontos += 7
    else:
        problemas.append("nenhuma definição clara detectada (GEO)")

    # ── CÁLCULO FINAL ──
    resultado.seo_score = round((seo_pontos / seo_max) * 100) if seo_max > 0 else 0
    resultado.geo_score = round((geo_pontos / geo_max) * 100) if geo_max > 0 else 0
    resultado.problemas = problemas

    resultado.seo_score = max(0, min(100, resultado.seo_score))
    resultado.geo_score = max(0, min(100, resultado.geo_score))

    return resultado