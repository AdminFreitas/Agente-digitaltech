"""
agents/pesquisador.py — Agente de Pesquisa Editorial DigitalTech

Responsabilidades:
  • pesquisar_tema()    → briefing editorial rico para artigos evergreen
  • pesquisar_noticias() → candidatos de notícias com qualificação e deduplicação
  • sugerir_tema()       → sugestão de pauta específica e original

O pesquisador NUNCA escreve o artigo final. Entrega contexto
estruturado para o editor.py e candidatos de notícias para o
editor_chefe.py.

Novidades desta versão (evolução do agente):
  • Classificação de prioridade editorial por notícia
    (urgente / relevante / aceitavel / fraco), usando as constantes
    RECENCIA_URGENTE_HORAS / RECENCIA_RELEVANTE_HORAS / RECENCIA_ACEITAVEL_HORAS
    que já existiam mas não eram aplicadas.
  • Classificação de veracidade por notícia
    (fato_reportado / hipotese / especulacao / nao_verificado), com
    atenção redobrada a temas sensíveis (dark tech, OSINT, ataques,
    vazamentos, mistérios) — nunca promove rumor a fato.
  • Contagem explícita de quantas fontes cobriram a mesma história
    (total_fontes), além da lista fontes_adicionais já existente.
  • Campos totalmente aditivos e com fallback seguro: nada do briefing
    ou dos candidatos de notícia existentes foi removido.

DEPENDÊNCIA: feedparser (pip install feedparser) — inalterada.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from services.llm_service import gerar_texto


# ═══════════════════════════════════════════════════════════════
# Constantes
# ═══════════════════════════════════════════════════════════════

FEEDS_NOTICIAS_TECH = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://hnrss.org/frontpage",
]

# Intenções de busca válidas
INTENCOES_BUSCA = frozenset(
    {
        "informacional",
        "navegacional",
        "comercial",
        "transacional",
        "tutorial",
        "pratica",
        "investigativa",
        "noticiosa",
    }
)

# Níveis técnicos válidos
NIVEIS_TECNICOS = frozenset(
    {"iniciante", "intermediario", "avancado", "misto", "nao_especificado"}
)

# Palavras-chave para identificar conteúdo de baixa qualidade/spam
SPAM_KEYWORDS = frozenset(
    {
        "click here", "subscribe now", "limited time", "act now",
        "clique aqui", "inscreva-se agora", "tempo limitado",
        "promoção", "promocao", "desconto", "compre agora",
        "ganhe dinheiro", "ganhe dinheiro", "ganhe dinheiro",
    }
)

# Limite de horas para considerar notícia "recente"
RECENCIA_URGENTE_HORAS = 6
RECENCIA_RELEVANTE_HORAS = 24
RECENCIA_ACEITAVEL_HORAS = 72

# Classificações de prioridade editorial (usadas por editor_chefe.py)
PRIORIDADES_NOTICIA = frozenset({"urgente", "relevante", "aceitavel", "fraco"})

# Classificações de veracidade/verificabilidade de uma notícia.
# O pesquisador NUNCA declara algo como "fato confirmado" de forma absoluta —
# apenas descreve o que a(s) fonte(s) reportam e o grau de certeza do texto.
CLASSIFICACOES_VERACIDADE = frozenset(
    {"fato_reportado", "hipotese", "especulacao", "nao_verificado"}
)

# Sinais textuais de especulação (mais fortes que "necessita verificação" genérico)
_SINAIS_ESPECULACAO = (
    "especula", "especulação", "especulacao", "pode ser", "possivelmente",
    "talvez", "parece que", "indica que", "sugere que", "acredita-se",
)

# Sinais textuais de hipótese/rumor não oficial
_SINAIS_HIPOTESE = (
    "rumor", "supostamente", "alegadamente", "fontes dizem", "suposto",
    "alegação", "alegacao", "não confirmado", "nao confirmado",
    "não verificado", "nao verificado", "anônimo", "anonimo",
)

# Temas sensíveis (dark tech / OSINT / segurança) que exigem cuidado redobrado
# na distinção entre fato, hipótese e especulação.
TEMAS_SENSIVEIS_VERIFICACAO = (
    "dark web", "deep web", "vazamento", "leak", "hacker", "hackers",
    "espionagem", "osint", "invasão", "invasao", "ataque", "ataques",
    "vulnerabilidade", "vulnerabilidades", "crime digital", "crimes digitais",
    "ransomware", "malware", "phishing", "exploit", "breach", "mistério",
    "misterio",
)


# ═══════════════════════════════════════════════════════════════
# Estruturas de dados
# ═══════════════════════════════════════════════════════════════

@dataclass
class BriefingEvergreen:
    """Briefing editorial completo para artigos evergreen."""

    tema: str = ""
    categoria: str = ""
    intencao_busca: str = "informacional"
    pergunta_principal: str = ""
    angulo: str = ""
    publico_alvo: str = ""
    nivel_tecnico: str = "nao_especificado"
    pontos_chave: list[str] = field(default_factory=list)
    perguntas_secundarias: list[str] = field(default_factory=list)
    entidades: list[str] = field(default_factory=list)
    termos_relacionados: list[str] = field(default_factory=list)
    fontes_sugeridas: list[dict] = field(default_factory=list)
    links_oficiais: list[dict] = field(default_factory=list)
    ferramentas: list[dict] = field(default_factory=list)
    riscos_verificacao: list[str] = field(default_factory=list)
    oportunidades_imagem: list[str] = field(default_factory=list)
    oportunidades_link: list[str] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidatoNoticia:
    """Candidato de notícia qualificado."""

    titulo: str = ""
    resumo: str = ""
    fonte: str = ""
    link: str = ""
    guid: str = ""
    publicado_em: str = ""
    categoria: str = ""
    entidades: list[str] = field(default_factory=list)
    tipo: str = "noticia"
    recencia_horas: float = -1.0
    fonte_tipo: str = "nao_classificada"
    confiabilidade: int = 50
    necessita_verificacao: bool = False
    fontes_adicionais: list[dict] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)
    prioridade: str = "nao_classificada"
    classificacao_veracidade: str = "fato_reportado"
    total_fontes: int = 1
    tema_sensivel: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
# Prompts
# ═══════════════════════════════════════════════════════════════

_PROMPT_BRIEFING_RICO = """Você é um pesquisador editorial sênior de um blog brasileiro de tecnologia chamado DigitalTech.

Sua tarefa é produzir um briefing editorial completo e estruturado em JSON para o tema fornecido. O briefing será consumido por um editor de conteúdo que escreverá o artigo final.

REGRAS FUNDAMENTAIS:
1. NUNCA invente URLs, fontes, estatísticas, especialistas ou eventos.
2. NUNCA transforme rumor em fato.
3. Se não souber algo, deixe o campo vazio ou com "nao_disponivel".
4. A intenção de busca deve ser uma das: informacional, navegacional, comercial, transacional, tutorial, pratica, investigativa.
5. A pergunta principal deve ser específica e guiar o editor.
6. Entidades devem ser nomes próprios reais (empresas, produtos, tecnologias, organizações).
7. Fontes sugeridas devem ser primárias quando possível (documentação oficial, site oficial, GitHub, NIST, CVE).
8. Links oficiais: só inclua URLs que você conhece e tem certeza de que existem.
9. Ferramentas: liste ferramentas reais relacionadas ao tema.
10. Riscos de verificação: aponte informações que possam estar desatualizadas, serem especulativas ou precisarem de confirmação.
11. Oportunidades de imagem: sugira tipos de imagens ou screenshots úteis.
12. Oportunidades de link: sugira tipos de links internos/externos úteis.
13. Não seja genérico. Seja específico e útil para um redator.

FORMATO DE RESPOSTA — JSON ESTRITO, sem markdown, sem explicações:

{{
  "intencao_busca": "informacional|navegacional|comercial|transacional|tutorial|pratica|investigativa",
  "pergunta_principal": "string",
  "angulo": "string",
  "publico_alvo": "string",
  "nivel_tecnico": "iniciante|intermediario|avancado|misto|nao_especificado",
  "pontos_chave": ["string", "string"],
  "perguntas_secundarias": ["string", "string"],
  "entidades": ["string", "string"],
  "termos_relacionados": ["string", "string"],
  "fontes_sugeridas": [{{"nome": "string", "tipo": "primaria|secundaria|nao_classificada"}}],
  "links_oficiais": [{{"nome": "string", "url": "string"}}],
  "ferramentas": [{{"nome": "string", "descricao": "string"}}],
  "riscos_verificacao": ["string", "string"],
  "oportunidades_imagem": ["string", "string"],
  "oportunidades_link": ["string", "string"]
}}

TEMA: {tema}
CATEGORIA: {categoria}

Gere o JSON agora."""

_PROMPT_SUGERIR_TEMA = """Você é um editor de pauta sênior do blog DigitalTech, especializado em tecnologia.

Sua tarefa é sugerir UM tema específico e interessante para um artigo evergreen (atemporal) na categoria fornecida.

REGRAS:
1. O tema deve ser ESPECÍFICO, não genérico.
2. Deve ter utilidade prática para o leitor.
3. Deve ter potencial de tráfego de busca orgânica.
4. Deve ser original e não repetir temas já publicados.
5. Deve estar alinhado com a linha editorial: IA, cibersegurança, OSINT, programação, cloud, DevOps, privacidade, ferramentas.
6. A pergunta central deve guiar o conteúdo.

Exemplos RUINS (genéricos):
- "Entenda a importância da inteligência artificial"
- "Como funciona a cibersegurança"
- "Tudo sobre Python"

Exemplos BONS (específicos):
- "Como um atacante pode descobrir a tecnologia usada por um site usando apenas informações públicas"
- "Como verificar se um domínio expõe tecnologias e serviços sem realizar nenhum ataque"
- "O que mudou no Python 3.14 e quem realmente precisa atualizar"
- "Como usar OSINT para identificar infraestrutura de phishing antes do ataque"

Responda APENAS com o tema sugerido, em uma única linha, sem numeração, sem aspas, sem explicação.

Categoria: {categoria}
{bloqueio}
Tema sugerido:"""


# ═══════════════════════════════════════════════════════════════
# API PÚBLICA — pesquisar_tema()
# ═══════════════════════════════════════════════════════════════

def pesquisar_tema(tema: str, categoria: str) -> dict:
    """
    Expande um tema de artigo evergreen em um briefing editorial rico.

    Retorna um dict plano compatível com o pipeline existente,
    contendo todos os campos do briefing (antigos + novos).
    """
    # 1. Prompt para o LLM
    prompt = _PROMPT_BRIEFING_RICO.format(tema=tema, categoria=categoria)

    # 2. Chamar LLM com tratamento de erro
    try:
        texto_resposta = gerar_texto(prompt)
    except Exception as e:
        texto_resposta = ""

    # 3. Parsing
    briefing = _parsear_briefing(texto_resposta)

    # 4. Preencher campos fixos
    briefing.tema = tema
    briefing.categoria = categoria

    # 5. Fallbacks e validação
    briefing = _validar_e_fallback_briefing(briefing)

    return briefing.to_dict()


# ═══════════════════════════════════════════════════════════════
# Parsing do briefing
# ═══════════════════════════════════════════════════════════════

def _parsear_briefing(texto: str) -> BriefingEvergreen:
    """Tenta extrair JSON; usa parser de texto simples como fallback."""
    texto = (texto or "").strip()
    if not texto:
        return BriefingEvergreen(problemas=["Resposta do LLM vazia"])

    # Tentar JSON
    json_str = _extrair_json(texto)
    if json_str:
        try:
            dados = json.loads(json_str)
            return _preencher_briefing_do_dict(dados)
        except json.JSONDecodeError:
            pass

    # Fallback: parser de texto simples (compatibilidade legada)
    return _parsear_briefing_texto_simples(texto)


def _extrair_json(texto: str) -> str | None:
    """Extrai bloco JSON da resposta, tolerante a markdown."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", texto, re.DOTALL)
    if match:
        return match.group(1)
    match = re.search(r"```\s*(\{.*?\})\s*```", texto, re.DOTALL)
    if match:
        return match.group(1)
    inicio = texto.find("{")
    if inicio == -1:
        return None
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
        if candidato.count("{") == candidato.count("}"):
            return candidato
    return None


def _preencher_briefing_do_dict(dados: dict) -> BriefingEvergreen:
    """Preenche BriefingEvergreen a partir de dict JSON."""

    def _lista(val: Any) -> list[str]:
        if isinstance(val, list):
            return [str(v).strip() for v in val if str(v).strip()]
        if isinstance(val, str):
            return [v.strip() for v in val.split(",") if v.strip()]
        return []

    def _lista_dicts(val: Any) -> list[dict]:
        if isinstance(val, list):
            return [dict(v) for v in val if isinstance(v, dict)]
        return []

    return BriefingEvergreen(
        intencao_busca=str(dados.get("intencao_busca", "informacional")).strip().lower(),
        pergunta_principal=str(dados.get("pergunta_principal", "")).strip(),
        angulo=str(dados.get("angulo", "")).strip(),
        publico_alvo=str(dados.get("publico_alvo", "")).strip(),
        nivel_tecnico=str(dados.get("nivel_tecnico", "nao_especificado")).strip().lower(),
        pontos_chave=_lista(dados.get("pontos_chave", [])),
        perguntas_secundarias=_lista(dados.get("perguntas_secundarias", [])),
        entidades=_lista(dados.get("entidades", [])),
        termos_relacionados=_lista(dados.get("termos_relacionados", [])),
        fontes_sugeridas=_lista_dicts(dados.get("fontes_sugeridas", [])),
        links_oficiais=_lista_dicts(dados.get("links_oficiais", [])),
        ferramentas=_lista_dicts(dados.get("ferramentas", [])),
        riscos_verificacao=_lista(dados.get("riscos_verificacao", [])),
        oportunidades_imagem=_lista(dados.get("oportunidades_imagem", [])),
        oportunidades_link=_lista(dados.get("oportunidades_link", [])),
    )


def _parsear_briefing_texto_simples(texto: str) -> BriefingEvergreen:
    """Parser de fallback para formato texto simples legado."""
    resultado = BriefingEvergreen(
        problemas=["Resposta do LLM não foi JSON válido; usado parser de fallback"]
    )

    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or ":" not in linha:
            continue
        chave, _, valor = linha.partition(":")
        chave_norm = chave.strip().upper().replace(" ", "_")
        valor = valor.strip()
        if not valor:
            continue

        if chave_norm == "ANGULO":
            resultado.angulo = valor
        elif chave_norm in ("PONTOS_CHAVE", "PONTOS-CHAVE"):
            resultado.pontos_chave = [p.strip() for p in valor.split(";") if p.strip()]
        elif chave_norm in ("TERMOS_RELACIONADOS", "TERMOS"):
            resultado.termos_relacionados = [t.strip() for t in valor.split(",") if t.strip()]
        elif chave_norm in ("PERGUNTA_PRINCIPAL", "PERGUNTA"):
            resultado.pergunta_principal = valor
        elif chave_norm in ("INTENCAO_BUSCA", "INTENCAO"):
            resultado.intencao_busca = valor.lower()
        elif chave_norm in ("PUBLICO_ALVO", "PUBLICO"):
            resultado.publico_alvo = valor
        elif chave_norm in ("NIVEL_TECNICO", "NIVEL"):
            resultado.nivel_tecnico = valor.lower()
        elif chave_norm in ("PERGUNTAS_SECUNDARIAS", "PERGUNTAS"):
            resultado.perguntas_secundarias = [p.strip() for p in valor.split(";") if p.strip()]
        elif chave_norm in ("ENTIDADES", "ENTITY"):
            resultado.entidades = [t.strip() for t in valor.split(",") if t.strip()]

    return resultado


# ═══════════════════════════════════════════════════════════════
# Validação e fallbacks do briefing
# ═══════════════════════════════════════════════════════════════

def _validar_e_fallback_briefing(b: BriefingEvergreen) -> BriefingEvergreen:
    """Aplica fallbacks e validações ao briefing."""
    problemas = list(b.problemas)

    # Intenção de busca
    if b.intencao_busca not in INTENCOES_BUSCA:
        b.intencao_busca = "informacional"
        problemas.append("intencao_busca inválida; usado fallback 'informacional'")

    # Nível técnico
    if b.nivel_tecnico not in NIVEIS_TECNICOS:
        b.nivel_tecnico = "nao_especificado"
        problemas.append("nivel_tecnico inválido; usado fallback")

    # Pergunta principal
    if not b.pergunta_principal:
        b.pergunta_principal = f"O que é {b.tema} e por que importa?"
        problemas.append("pergunta_principal vazia; usado fallback")

    # Ângulo
    if not b.angulo:
        b.angulo = b.tema
        problemas.append("angulo vazio; usado fallback do tema")

    # Pontos-chave mínimos
    if not b.pontos_chave:
        b.pontos_chave = [f"Conceitos fundamentais sobre {b.tema}"]
        problemas.append("pontos_chave vazios; usado fallback")

    # Entidades mínimas
    if not b.entidades:
        b.entidades = []

    # Fontes sugeridas
    if not b.fontes_sugeridas:
        b.fontes_sugeridas = []

    # Links oficiais — remover URLs vazias ou suspeitas
    links_validos = []
    for link in b.links_oficiais:
        if isinstance(link, dict):
            url = str(link.get("url", "")).strip()
            nome = str(link.get("nome", "")).strip()
            if url and url.startswith(("http://", "https://")):
                links_validos.append({"nome": nome or "Fonte", "url": url})
    b.links_oficiais = links_validos

    # Ferramentas
    if not b.ferramentas:
        b.ferramentas = []

    b.problemas = problemas
    return b


# ═══════════════════════════════════════════════════════════════
# API PÚBLICA — pesquisar_noticias()
# ═══════════════════════════════════════════════════════════════

def pesquisar_noticias(max_itens: int = 8) -> list[dict]:
    """
    Busca itens recentes nos feeds RSS configurados.

    Retorna lista de dicts qualificados, deduplicados e filtrados.
    Cada item contém metadados enriquecidos para o editor_chefe.py.
    """
    try:
        import feedparser
    except ImportError:
        return []

    # 1. Coletar todos os candidatos dos feeds
    todos_candidatos: list[CandidatoNoticia] = []
    for url_feed in FEEDS_NOTICIAS_TECH:
        try:
            feed = feedparser.parse(url_feed)
            fonte_nome = feed.feed.get("title", url_feed)
            for entrada in feed.entries[:15]:
                candidato = _extrair_candidato_do_feed(entrada, fonte_nome, url_feed)
                if candidato:
                    todos_candidatos.append(candidato)
        except Exception as e:
            # Feed falhou silenciosamente — log opcional
            pass

    # 2. Deduplicar por similaridade
    todos_candidatos = _deduplicar_por_similaridade(todos_candidatos)

    # 3. Filtrar e classificar por qualidade/recência
    todos_candidatos = _classificar_e_filtrar(todos_candidatos)

    # 4. Agrupar múltiplas fontes para mesma história
    todos_candidatos = _agrupar_fontes(todos_candidatos)

    # 5. Limitar resultado
    return [c.to_dict() for c in todos_candidatos[:max_itens]]


def _extrair_candidato_do_feed(entrada: Any, fonte_nome: str, url_feed: str) -> CandidatoNoticia | None:
    """Extrai um CandidatoNoticia de uma entrada de feedparser."""
    titulo = str(entrada.get("title", "")).strip()
    if not titulo:
        return None

    resumo_raw = str(entrada.get("summary", ""))
    resumo = _limpar_resumo(resumo_raw)
    link = str(entrada.get("link", "")).strip()
    guid = str(entrada.get("id", "")).strip() or link

    # Tentar extrair data
    publicado_em = ""
    recencia_horas = -1.0
    for campo in ("published", "updated", "created"):
        val = entrada.get(campo)
        if val:
            publicado_em = str(val)
            recencia_horas = _calcular_recencia_horas(publicado_em)
            break

    # Detectar entidades no título
    entidades = _extrair_entidades_do_texto(titulo + " " + resumo)

    # Classificar fonte
    fonte_tipo = _classificar_tipo_fonte(fonte_nome, url_feed)

    # Confiabilidade base
    confiabilidade = _calcular_confiabilidade_base(fonte_nome)

    # Verificar necessidade de verificação
    necessita_verificacao = _detectar_necessidade_verificacao(titulo, resumo)

    # Classificar veracidade e tema sensível (dark tech / OSINT / ataques)
    classificacao_veracidade = _classificar_veracidade(titulo, resumo)
    tema_sensivel = _eh_tema_sensivel(titulo, resumo)

    return CandidatoNoticia(
        titulo=titulo,
        resumo=resumo,
        fonte=fonte_nome,
        link=link,
        guid=guid,
        publicado_em=publicado_em,
        categoria="tecnologia",
        entidades=entidades,
        tipo="noticia",
        recencia_horas=recencia_horas,
        fonte_tipo=fonte_tipo,
        confiabilidade=confiabilidade,
        necessita_verificacao=necessita_verificacao,
        classificacao_veracidade=classificacao_veracidade,
        tema_sensivel=tema_sensivel,
    )


def _limpar_resumo(html_ou_texto: str, max_chars: int = 300) -> str:
    """Remove tags HTML e normaliza espaços."""
    texto = re.sub(r"<[^>]+>", " ", html_ou_texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:max_chars]


def _calcular_recencia_horas(data_str: str) -> float:
    """Calcula horas desde a publicação. Retorna -1 se não conseguir parsear."""
    formatos_comuns = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%d %b %Y %H:%M:%S %Z",
    ]
    for fmt in formatos_comuns:
        try:
            dt = datetime.strptime(data_str, fmt)
            # Tornar aware se for naive
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            agora = datetime.now(timezone.utc)
            diff = (agora - dt).total_seconds() / 3600
            return round(diff, 1)
        except ValueError:
            continue
    return -1.0


def _extrair_entidades_do_texto(texto: str) -> list[str]:
    """Extrai entidades candidatas do texto (nomes próprios, siglas, marcas)."""
    entidades: list[str] = []

    # CamelCase e nomes compostos
    padrao_camel = re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|\b[A-Z]{2,}\b", texto)
    for e in padrao_camel:
        e = e.strip()
        if len(e) > 2 and e not in entidades:
            entidades.append(e)

    # Nomes de empresas/ferramentas conhecidas
    conhecidas = [
        "OpenAI", "Google", "Microsoft", "Apple", "Meta", "Amazon",
        "Tesla", "NVIDIA", "Intel", "AMD", "Samsung", "Sony",
        "Python", "JavaScript", "TypeScript", "Rust", "Go", "Java",
        "Docker", "Kubernetes", "AWS", "Azure", "GCP",
        "Linux", "Windows", "macOS", "Ubuntu", "Debian",
        "GitHub", "GitLab", "Git", "VS Code", "IntelliJ",
        "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
        "React", "Vue", "Angular", "Next.js", "Django", "Flask",
        "ChatGPT", "GPT", "Claude", "Gemini", "Llama", "Mistral",
        "CVE", "NIST", "CISA", "FBI", "NSA", "Interpol",
        "Bitcoin", "Ethereum", "Solana", "Blockchain",
        "Tor", "VPN", "Firewall", "IDS", "IPS",
        "Canva", "Figma", "Notion", "Slack", "Discord",
        "WhatsApp", "Telegram", "Signal", "Matrix",
    ]
    for nome in conhecidas:
        if re.search(rf"\b{re.escape(nome)}\b", texto, re.IGNORECASE) and nome not in entidades:
            entidades.append(nome)

    return entidades[:10]


def _classificar_tipo_fonte(fonte_nome: str, url_feed: str) -> str:
    """Classifica a fonte como primária, secundária ou não classificada."""
    fonte_lower = (fonte_nome + " " + url_feed).lower()
    primarias = [
        "blog.", "official", "docs.", "documentation",
        "github.com", "gitlab.com", "apache.org", "mozilla.org",
        "nist.gov", "cisa.gov", "cve.mitre", "cert.",
        "python.org", "nodejs.org", "react.dev", "angular.io",
    ]
    for p in primarias:
        if p in fonte_lower:
            return "primaria"
    return "secundaria"


def _calcular_confiabilidade_base(fonte_nome: str) -> int:
    """Atribui score base de confiabilidade (0–100)."""
    fonte_lower = fonte_nome.lower()
    alta = ["techcrunch", "the verge", "arstechnica", "wired", "reuters", "bloomberg"]
    media = ["hackernews", "reddit", "medium"]
    for f in alta:
        if f in fonte_lower:
            return 80
    for f in media:
        if f in fonte_lower:
            return 60
    return 50


def _detectar_necessidade_verificacao(titulo: str, resumo: str) -> bool:
    """Detecta se a notícia precisa de verificação adicional."""
    texto = (titulo + " " + resumo).lower()
    sinais = [
        "rumor", "supostamente", "alegadamente", "fontes dizem",
        "não confirmado", "não verificado", "anônimo", "anonimo",
        "especula", "especulação", "especulacao", "pode ser",
        "possivelmente", "talvez", "parece que", "indica que",
        "vazamento", "leak", "suposto", "alegação", "alegacao",
    ]
    return any(s in texto for s in sinais)


def _eh_tema_sensivel(titulo: str, resumo: str) -> bool:
    """
    Identifica se o candidato toca em temas sensíveis (dark tech, OSINT,
    ataques, vazamentos, mistérios), que exigem separação rigorosa entre
    fato, hipótese e especulação — nunca transformar rumor em fato.
    """
    texto = (titulo + " " + resumo).lower()
    return any(t in texto for t in TEMAS_SENSIVEIS_VERIFICACAO)


def _classificar_veracidade(titulo: str, resumo: str) -> str:
    """
    Classifica o grau de certeza do que está sendo reportado.

    O pesquisador nunca afirma algo como "confirmado" de forma absoluta —
    apenas descreve o que a fonte relata:

      - "especulacao": o texto usa linguagem claramente especulativa.
      - "hipotese": o texto menciona rumor, fonte anônima ou algo "supostamente".
      - "nao_verificado": sinais genéricos de incerteza, sem se enquadrar
        claramente como rumor nem especulação.
      - "fato_reportado": a fonte relata o acontecimento sem qualificadores
        de incerteza (isso NÃO é uma confirmação independente do pesquisador,
        apenas o registro de que a fonte não sinalizou dúvida).
    """
    texto = (titulo + " " + resumo).lower()

    if any(s in texto for s in _SINAIS_ESPECULACAO):
        return "especulacao"
    if any(s in texto for s in _SINAIS_HIPOTESE):
        return "hipotese"
    if _detectar_necessidade_verificacao(titulo, resumo):
        return "nao_verificado"
    return "fato_reportado"


def _classificar_prioridade(candidato: "CandidatoNoticia") -> str:
    """
    Classifica a notícia em urgente / relevante / aceitavel / fraco,
    combinando recência e confiabilidade da fonte. A decisão final de
    pauta continua sendo do editor_chefe.py — esta é apenas uma
    classificação objetiva de apoio.
    """
    recencia = candidato.recencia_horas
    confiavel = candidato.confiabilidade

    if candidato.problemas:
        # Qualquer problema relevante (spam, fora de escopo, sem link) já é
        # tratado em _classificar_e_filtrar; aqui só rebaixamos prioridade
        # quando a data não pôde ser interpretada.
        if "data não interpretável" in candidato.problemas:
            return "aceitavel" if confiavel >= 60 else "fraco"

    if recencia < 0:
        return "aceitavel" if confiavel >= 60 else "fraco"
    if recencia <= RECENCIA_URGENTE_HORAS and confiavel >= 50:
        return "urgente"
    if recencia <= RECENCIA_RELEVANTE_HORAS:
        return "relevante"
    if recencia <= RECENCIA_ACEITAVEL_HORAS:
        return "aceitavel"
    return "fraco"


# ═══════════════════════════════════════════════════════════════
# Deduplicação por similaridade
# ═══════════════════════════════════════════════════════════════

def _deduplicar_por_similaridade(candidatos: list[CandidatoNoticia]) -> list[CandidatoNoticia]:
    """
    Remove duplicatas por similaridade textual, não apenas título exato.
    Preserva o candidato com melhor qualidade quando há duplicatas.
    """
    if not candidatos:
        return []

    # Ordenar por qualidade (confiabilidade desc, recência asc)
    candidatos_ordenados = sorted(
        candidatos,
        key=lambda c: (c.confiabilidade, -c.recencia_horas if c.recencia_horas >= 0 else 9999),
        reverse=True,
    )

    unicos: list[CandidatoNoticia] = []
    for candidato in candidatos_ordenados:
        if _eh_duplicata(candidato, unicos):
            continue
        unicos.append(candidato)

    return unicos


def _eh_duplicata(candidato: CandidatoNoticia, existentes: list[CandidatoNoticia]) -> bool:
    """Verifica se o candidato é duplicata de algum existente."""
    titulo_norm = _normalizar_texto(candidato.titulo)

    for existente in existentes:
        # Mesmo GUID ou link
        if candidato.guid and candidato.guid == existente.guid:
            return True
        if candidato.link and candidato.link == existente.link:
            return True

        # Similaridade de título
        existente_norm = _normalizar_texto(existente.titulo)
        similaridade = _calcular_similaridade_jaccard(titulo_norm, existente_norm)
        if similaridade >= 0.65:
            return True

        # Mesma entidade principal + recência próxima
        if candidato.entidades and existente.entidades:
            entidades_comuns = set(c.lower() for c in candidato.entidades) & set(e.lower() for e in existente.entidades)
            if len(entidades_comuns) >= 2:
                # Se tiverem 2+ entidades em comum e recência próxima (< 12h), considerar duplicata
                if candidato.recencia_horas >= 0 and existente.recencia_horas >= 0:
                    if abs(candidato.recencia_horas - existente.recencia_horas) < 12:
                        return True

    return False


def _normalizar_texto(texto: str) -> set[str]:
    """Normaliza texto para comparação: minúsculas, remove stopwords, extrai tokens."""
    stopwords = {
        "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das",
        "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "sobre",
        "entre", "e", "ou", "mas", "que", "como", "quando", "onde", "quem",
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "new", "novo", "nova", "novos", "novas", "latest", "latest", "update",
        "announces", "announced", "launch", "launches", "releases", "released",
    }
    texto = texto.lower()
    texto = re.sub(r"[^\w\s]", " ", texto)
    tokens = [t for t in texto.split() if len(t) > 2 and t not in stopwords]
    return set(tokens)


def _calcular_similaridade_jaccard(set_a: set[str], set_b: set[str]) -> float:
    """Calcula similaridade de Jaccard entre dois conjuntos de tokens."""
    if not set_a or not set_b:
        return 0.0
    intersecao = len(set_a & set_b)
    uniao = len(set_a | set_b)
    return intersecao / uniao if uniao > 0 else 0.0


# ═══════════════════════════════════════════════════════════════
# Classificação e filtragem
# ═══════════════════════════════════════════════════════════════

def _classificar_e_filtrar(candidatos: list[CandidatoNoticia]) -> list[CandidatoNoticia]:
    """Filtra candidatos de baixa qualidade e classifica por prioridade."""
    filtrados: list[CandidatoNoticia] = []

    for c in candidatos:
        problemas: list[str] = []

        # Rejeitar candidatos sem título
        if not c.titulo or len(c.titulo) < 10:
            continue

        # Rejeitar candidatos sem link
        if not c.link:
            problemas.append("sem link")

        # Rejeitar spam
        if _eh_spam(c.titulo, c.resumo):
            problemas.append("detectado como spam/publicidade")
            continue

        # Verificar recência
        if c.recencia_horas >= 0:
            if c.recencia_horas > RECENCIA_ACEITAVEL_HORAS:
                problemas.append(f"notícia antiga ({c.recencia_horas:.0f}h)")
        else:
            problemas.append("data não interpretável")

        # Verificar relação com tecnologia
        if not _eh_tecnologia(c.titulo, c.resumo, c.entidades):
            problemas.append("possivelmente fora do escopo de tecnologia")

        c.problemas = problemas
        c.prioridade = _classificar_prioridade(c)
        filtrados.append(c)

    # Ordenar: mais recentes primeiro, depois por confiabilidade
    filtrados.sort(key=lambda c: (
        c.recencia_horas if c.recencia_horas >= 0 else 9999,
        -c.confiabilidade,
    ))

    return filtrados


def _eh_spam(titulo: str, resumo: str) -> bool:
    """Detecta conteúdo spam ou publicidade disfarçada."""
    texto = (titulo + " " + resumo).lower()
    for kw in SPAM_KEYWORDS:
        if kw in texto:
            return True
    # Muitos pontos de exclamação ou CAPS excessivo
    if titulo.count("!") > 2 or sum(1 for c in titulo if c.isupper()) > len(titulo) * 0.5:
        return True
    return False


def _eh_tecnologia(titulo: str, resumo: str, entidades: list[str]) -> bool:
    """Verifica se o candidato está relacionado a tecnologia."""
    texto = (titulo + " " + resumo).lower()
    tech_keywords = {
        "tech", "technology", "software", "hardware", "ai", "artificial intelligence",
        "machine learning", "deep learning", "neural", "algorithm", "code",
        "programming", "developer", "app", "application", "web", "internet",
        "cloud", "server", "database", "security", "cyber", "hacker",
        "vulnerability", "exploit", "patch", "update", "release", "launch",
        "python", "javascript", "java", "rust", "go", "typescript",
        "linux", "windows", "macos", "android", "ios",
        "docker", "kubernetes", "aws", "azure", "gcp",
        "github", "gitlab", "git", "api", "framework",
        "blockchain", "crypto", "bitcoin", "ethereum",
        "robot", "drone", "iot", "sensor", "chip", "processor",
        "gpu", "cpu", "ram", "ssd", "display", "screen",
        "5g", "wifi", "bluetooth", "network", "protocol",
        "privacy", "encryption", "vpn", "firewall", "malware",
        "ransomware", "phishing", "osint", "dark web", "deep web",
        "data", "analytics", "big data", "data science",
    }
    for kw in tech_keywords:
        if kw in texto:
            return True
    # Se tem entidades conhecidas de tech
    tech_entities = {
        "OpenAI", "Google", "Microsoft", "Apple", "Meta", "Amazon", "NVIDIA",
        "Python", "JavaScript", "Docker", "Kubernetes", "GitHub", "AWS",
        "ChatGPT", "GPT", "Claude", "Gemini", "Linux", "PostgreSQL",
    }
    for e in entidades:
        if e in tech_entities:
            return True
    return False


# ═══════════════════════════════════════════════════════════════
# Agrupamento de múltiplas fontes
# ═══════════════════════════════════════════════════════════════

def _agrupar_fontes(candidatos: list[CandidatoNoticia]) -> list[CandidatoNoticia]:
    """
    Quando várias fontes cobrem a mesma história, agrupa as fontes
    adicionais no candidato principal (o mais confiável/recente).
    """
    if len(candidatos) <= 1:
        return candidatos

    agrupados: list[CandidatoNoticia] = []
    processados: set[int] = set()

    for i, principal in enumerate(candidatos):
        if i in processados:
            continue

        fontes_adicionais: list[dict] = []
        for j, outro in enumerate(candidatos):
            if i == j or j in processados:
                continue
            if _sao_mesma_historia(principal, outro):
                fontes_adicionais.append({
                    "fonte": outro.fonte,
                    "titulo": outro.titulo,
                    "link": outro.link,
                })
                processados.add(j)

        if fontes_adicionais:
            principal.fontes_adicionais = fontes_adicionais
            # Se múltiplas fontes independentes cobrem a mesma história,
            # isso é um sinal (não uma prova) de maior confiabilidade —
            # nunca eleva "especulacao"/"hipotese" para "fato_reportado".
            if principal.classificacao_veracidade == "nao_verificado":
                principal.classificacao_veracidade = "fato_reportado"

        principal.total_fontes = 1 + len(fontes_adicionais)

        agrupados.append(principal)
        processados.add(i)

    return agrupados


def _sao_mesma_historia(a: CandidatoNoticia, b: CandidatoNoticia) -> bool:
    """Verifica se dois candidatos cobrem a mesma história."""
    # Mesmo GUID ou link
    if a.guid and a.guid == b.guid:
        return True
    if a.link and a.link == b.link:
        return True

    # Similaridade de título alta
    sim = _calcular_similaridade_jaccard(
        _normalizar_texto(a.titulo),
        _normalizar_texto(b.titulo),
    )
    if sim >= 0.55:
        return True

    # Entidades em comum + recência próxima
    if a.entidades and b.entidades:
        comuns = set(e.lower() for e in a.entidades) & set(e.lower() for e in b.entidades)
        if len(comuns) >= 2:
            if a.recencia_horas >= 0 and b.recencia_horas >= 0:
                if abs(a.recencia_horas - b.recencia_horas) < 24:
                    return True

    return False


# ═══════════════════════════════════════════════════════════════
# API PÚBLICA — sugerir_tema()
# ═══════════════════════════════════════════════════════════════

def sugerir_tema(categoria: str, temas_recentes: list[str] | None = None) -> str:
    """
    Sugere um tema novo e específico de artigo evergreen dentro da
    categoria, evitando repetir temas recentes.
    """
    bloqueio = ""
    if temas_recentes:
        lista = "\n".join(f"- {t}" for t in temas_recentes[:15])
        bloqueio = f"\nNÃO repita (nem algo muito parecido com) nenhum destes temas já publicados:\n{lista}\n"

    prompt = _PROMPT_SUGERIR_TEMA.format(categoria=categoria, bloqueio=bloqueio)

    try:
        tema = gerar_texto(prompt)
    except Exception:
        tema = ""

    tema = tema.strip().strip('"').strip("'")

    # Fallback se o LLM falhar ou retornar algo muito curto/genérico
    if not tema or len(tema) < 15:
        tema = _fallback_sugerir_tema(categoria)

    return tema


def _fallback_sugerir_tema(categoria: str) -> str:
    """Fallback determinístico para sugestão de tema."""
    fallbacks_por_categoria = {
        "inteligencia artificial": "Como usar embeddings para melhorar buscas em documentos internos",
        "ciberseguranca": "Como identificar phishing usando apenas análise de cabeçalhos de e-mail",
        "programacao": "Como estruturar testes de integração para APIs RESTful",
        "cloud": "Como reduzir custos de armazenamento S3 sem perder performance",
        "devops": "Como implementar rollback automático em pipelines de CI/CD",
        "privacidade": "Como verificar se seus dados vazaram em breaches conhecidos",
        "osint": "Como mapear infraestrutura de um domínio usando ferramentas públicas",
        "dark tech": "Como funcionam os mercados de credenciais na dark web",
        "hardware": "Como escolher SSD NVMe para workstations de desenvolvimento",
        "banco de dados": "Como otimar índices PostgreSQL para consultas analíticas",
        "infraestrutura": "Como configurar failover DNS para alta disponibilidade",
        "ferramentas": "Como automatizar relatórios de segurança com Python e APIs gratuitas",
    }
    cat_lower = categoria.lower()
    for key, val in fallbacks_por_categoria.items():
        if key in cat_lower:
            return val
    return f"Como {categoria.lower()} pode melhorar a produtividade de equipes técnicas"