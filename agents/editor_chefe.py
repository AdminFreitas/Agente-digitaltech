"""
editor_chefe.py — Orquestrador de pauta (Nível 1: Python puro, sem LLM)

Recebe os candidatos crus de pesquisador.pesquisar_noticias() e decide
O QUE processar e EM QUE ORDEM — nunca escreve conteúdo. Isso é
deliberadamente lógica de regras/scoring, não uma decisão de LLM: mais
barato, determinístico e fácil de testar do que pedir pra um modelo
"decidir" prioridade a cada chamada.

Fluxo:
    pesquisador.pesquisar_noticias()
            │
            ▼
    EditorChefe.montar_pauta()
        ├── valida candidatos (título, dados mínimos)
        ├── remove duplicadas ENTRE os candidatos (mesma história em
        │   feeds diferentes vira 1 item só, com quantidade_fontes)
        ├── descarta candidatos muito parecidos com algo que já existe
        │   no banco (passe os títulos recentes de QUALQUER agente,
        │   já que Agente A e Agente B escrevem na mesma tabela)
        ├── calcula score de relevância (categoria, fonte, quantas
        │   fontes cobrem a mesma história, recência, completude)
        ├── define prioridade (Urgente/Alta/Média/Baixa)
        └── ordena a fila da maior pra menor prioridade
            │
            ▼
    lista de ItemPauta — o pipeline processa um de cada vez através de
    editor.py → revisor.py → seo.py → NoticiaRepository

Nenhuma chamada de rede, LLM ou banco acontece aqui dentro — é só
Python puro sobre os dados que você já buscou. Isso é intencional:
mantém essa peça rápida e fácil de testar sem precisar de Ollama nem
de conexão com o Neon.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from typing import Any

# ---------------------------------------------------------------------------
# Constantes configuráveis — centralizadas, sem números mágicos espalhados
# ---------------------------------------------------------------------------

# Stopwords comuns em português e inglês para análise de similaridade
_STOPWORDS = frozenset({
    # Português
    "o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da",
    "dos", "das", "em", "no", "na", "nos", "nas", "por", "pelo", "pela",
    "pelos", "pelas", "para", "pra", "com", "sem", "sob", "sobre", "entre",
    "durante", "antes", "depois", "até", "desde", "após", "que", "se",
    "como", "mas", "porém", "entretanto", "todavia", "ou", "e", "nem",
    "já", "também", "ainda", "só", "apenas", "mesmo", "próprio", "outro",
    "qualquer", "todo", "todos", "cada", "muito", "mais", "menos", "tão",
    "assim", "aqui", "agora", "hoje", "ontem", "anteontem", "depois",
    # Inglês
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "can", "this",
    "that", "these", "those", "it", "its", "not", "no", "yes", "new",
    "now", "then", "here", "there", "when", "where", "why", "how", "what",
    "who", "which", "all", "any", "both", "each", "few", "more", "most",
    "other", "some", "such", "only", "own", "same", "so", "than", "too",
    "very", "just", "also", "get", "got", "gets", "up", "out", "about",
})

# Termos técnicos que aumentam peso na comparação de similaridade
_TERMOS_TECNICOS = frozenset({
    "inteligencia artificial", "ia", "ai", "machine learning", "deep learning",
    "llm", "gpt", "openai", "anthropic", "claude", "gemini", "bard",
    "python", "javascript", "typescript", "rust", "go", "java", "csharp",
    "sql", "nosql", "postgresql", "mysql", "mongodb", "redis",
    "aws", "azure", "gcp", "cloud", "kubernetes", "docker", "devops",
    "linux", "windows", "macos", "android", "ios",
    "security", "ciberseguranca", "cybersecurity", "vulnerability",
    "breach", "ransomware", "malware", "phishing", "zero day",
    "gpu", "cpu", "nvidia", "amd", "intel", "apple silicon", "m4", "m3",
    "iphone", "ipad", "macbook", "pixel", "galaxy", "xperia",
    "bitcoin", "ethereum", "blockchain", "crypto",
    "startup", "unicornio", "ipo", "acquisition", "merger",
})

# Pesos de categoria (importância temática para o DigitalTech)
PESO_CATEGORIA: dict[str, float] = {
    "inteligencia artificial": 25.0,
    "ia": 25.0,
    "ai": 25.0,
    "machine learning": 25.0,
    "banco de dados": 20.0,
    "database": 20.0,
    "sql": 20.0,
    "nosql": 20.0,
    "programacao": 18.0,
    "programming": 18.0,
    "desenvolvimento": 18.0,
    "ciberseguranca": 18.0,
    "cybersecurity": 18.0,
    "seguranca": 16.0,
    "security": 16.0,
    "cloud e devops": 15.0,
    "cloud": 15.0,
    "devops": 15.0,
    "infraestrutura": 12.0,
    "hardware": 10.0,
    "open source": 10.0,
    "opensource": 10.0,
    "carreira": 8.0,
    "career": 8.0,
}

# Pesos de fonte (confiabilidade/qualidade editorial conhecida)
PESO_FONTE: dict[str, float] = {
    "ars technica": 22.0,
    "arstechnica": 22.0,
    "techcrunch": 20.0,
    "the verge": 18.0,
    "verge": 18.0,
    "wired": 18.0,
    "hacker news": 15.0,
    "hackernews": 15.0,
    "github blog": 15.0,
    "github": 12.0,
    "stackoverflow blog": 14.0,
    "dev.to": 12.0,
    "infoq": 14.0,
    "zdnet": 13.0,
    "theregister": 13.0,
    "bleeping computer": 14.0,
    "dark reading": 14.0,
    "krebs on security": 16.0,
}

# Fallback: peso mínimo para fontes/categorias desconhecidas
# Garante que notícias importantes de fontes desconhecidas não morram
PESO_FONTE_DESCONHECIDA: float = 5.0
PESO_CATEGORIA_DESCONHECIDA: float = 5.0

# Pesos de recência (decaimento gradual)
PESO_RECENCIA: dict[str, float] = {
    "ate_6h": 20.0,
    "ate_24h": 15.0,
    "ate_48h": 10.0,
    "ate_72h": 5.0,
    "decaimento_por_dia": 1.5,  # após 72h, perde 1.5 por dia adicional
}

# Pesos para múltiplas fontes
PESO_MULTIPLAS_FONTES: float = 15.0
PESO_MULTIPLAS_FONTES_MINIMO: int = 2  # quantidade mínima para aplicar

# Bônus de completude dos dados
PESO_RESUMO_PRESENTE: float = 3.0
PESO_LINK_VALIDO: float = 2.0

# Limiares de similaridade
LIMIAR_SIMILARIDADE_DUPLICATA: float = 0.55
LIMIAR_SIMILARIDADE_DUPLICATA_RIGOROSO: float = 0.72
LIMIAR_SIMILARIDADE_ATUALIZACAO: float = 0.45  # abaixo disso, pode ser atualização

# Faixas de prioridade (limites inferiores inclusivos)
FAIXAS_PRIORIDADE: list[tuple[float, str]] = [
    (90.0, "Urgente"),
    (70.0, "Alta"),
    (50.0, "Média"),
    (0.0, "Baixa"),
]

# Diversidade da pauta: máximo de itens consecutivos da mesma categoria
# antes de forçar alternância (aplicado suavemente, sem prejudicar urgentes)
LIMITE_CONSECUTIVOS_MESMA_CATEGORIA: int = 3

# Limite de horas para o floor de "urgente por recência" (notícia muito
# recente de qualquer categoria/fonte). Nome antigo (SCORE_MINIMO_...)
# era enganoso -- isso é um limite de HORAS, não de score.
HORAS_LIMITE_URGENCIA_RECENCIA: float = 6.0  # ≤ 6h

# Score mínimo aplicado dentro do limite acima. Derivado do piso da faixa
# "Média" em FAIXAS_PRIORIDADE (em vez de duplicar o número mágico aqui) --
# garante de fato "pelo menos Média", mesmo se as faixas mudarem no futuro.
SCORE_FLOOR_URGENCIA_RECENCIA: float = next(
    limite for limite, nome in FAIXAS_PRIORIDADE if nome == "Média"
)


# ---------------------------------------------------------------------------
# Modelo de saída — retrocompatível, com campos internos de observabilidade
# ---------------------------------------------------------------------------

@dataclass
class ItemPauta:
    titulo: str
    resumo: str
    fonte: str
    link: str
    categoria: str
    score: float
    prioridade: str
    quantidade_fontes: int = 1

    # Campos internos de observabilidade (não quebram consumidores existentes)
    componentes_score: dict[str, float] = field(default_factory=dict, repr=False)
    fontes_relacionadas: list[str] = field(default_factory=list, repr=False)
    links_relacionados: list[str] = field(default_factory=list, repr=False)
    motivo_descarte: str | None = field(default=None, repr=False)
    horas_desde_publicacao: float | None = field(default=None, repr=False)
    # True quando o titulo teve similaridade MODERADA (nao rigorosa o
    # suficiente pra descartar) com algo ja publicado -- sinaliza "pode ser
    # atualizacao da mesma historia, revise antes de publicar automaticamente"
    # em vez de descartar de forma silenciosa (item 10 do pedido de revisao).
    possivel_atualizacao: bool = field(default=False, repr=False)


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------

def _normalizar(texto: str | None) -> str:
    """Normaliza texto para comparação: minúsculas, sem acento, sem pontuação."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto).strip().lower())
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", sem_acento).strip()


def _extrair_tokens(texto: str) -> set[str]:
    """Extrai tokens relevantes de um texto, removendo stopwords."""
    norm = _normalizar(texto)
    tokens = set(norm.split())
    return tokens - _STOPWORDS


def _extrair_tokens_relevantes(texto: str) -> set[str]:
    """Extrai tokens com alto valor semântico: números, termos técnicos, entidades."""
    norm = _normalizar(texto)
    tokens = set(norm.split())
    relevantes: set[str] = set()

    for token in tokens:
        if token in _STOPWORDS:
            continue
        # Números (versões, modelos, anos)
        if re.match(r"^\d+(\.\d+)?$", token) or re.match(r"^\d+[a-z]+$", token):
            relevantes.add(token)
            continue
        # Termos técnicos
        if token in _TERMOS_TECNICOS:
            relevantes.add(token)
            continue
        # Tokens com comprimento significativo (provavelmente substantivos)
        if len(token) >= 4:
            relevantes.add(token)

    return relevantes


def _extrair_ngrams(tokens: set[str], n: int = 2) -> set[str]:
    """Extrai n-grams de um conjunto de tokens para capturar expressões."""
    if len(tokens) < n:
        return set()
    lista = sorted(tokens)
    return {" ".join(lista[i : i + n]) for i in range(len(lista) - n + 1)}


def _similaridade(a: str, b: str) -> float:
    """
    Similaridade combinada entre dois textos.

    Combina três medidas:
    1. SequenceMatcher (ordem das palavras)
    2. Jaccard de tokens (ignora ordem)
    3. Jaccard de tokens relevantes (entidades, números, termos técnicos)

    A medida 3 recebe peso maior porque captura se falam do MESMO evento.
    """
    if not a or not b:
        return 0.0

    norm_a, norm_b = _normalizar(a), _normalizar(b)

    if not norm_a or not norm_b:
        return 0.0

    # 1. SequenceMatcher
    razao_sequencia = SequenceMatcher(None, norm_a, norm_b).ratio()

    # 2. Jaccard de tokens (sem stopwords)
    tokens_a, tokens_b = _extrair_tokens(a), _extrair_tokens(b)
    if tokens_a and tokens_b:
        razao_tokens = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    else:
        razao_tokens = 0.0

    # 3. Jaccard de tokens relevantes (com peso maior)
    rel_a, rel_b = _extrair_tokens_relevantes(a), _extrair_tokens_relevantes(b)
    if rel_a and rel_b:
        razao_relevantes = len(rel_a & rel_b) / len(rel_a | rel_b)
        # Bigrams para capturar expressões compostas
        bigrams_a, bigrams_b = _extrair_ngrams(rel_a, 2), _extrair_ngrams(rel_b, 2)
        if bigrams_a and bigrams_b:
            razao_bigrams = len(bigrams_a & bigrams_b) / len(bigrams_a | bigrams_b)
        else:
            razao_bigrams = 0.0
        # Média ponderada: tokens relevantes pesam mais
        razao_semantica = 0.6 * razao_relevantes + 0.4 * razao_bigrams
    else:
        razao_semantica = 0.0

    # Combinação final: dá mais peso à semântica relevante
    return max(
        razao_sequencia * 0.25 + razao_tokens * 0.25 + razao_semantica * 0.50,
        razao_sequencia,
        razao_tokens,
    )


def _similaridade_rigorosa(a: str, b: str) -> float:
    """
    Similaridade mais rigorosa para descarte de já publicadas.
    Exige maior sobreposição semântica para considerar duplicata.
    """
    if not a or not b:
        return 0.0

    rel_a, rel_b = _extrair_tokens_relevantes(a), _extrair_tokens_relevantes(b)
    if not rel_a or not rel_b:
        return _similaridade(a, b) * 0.5  # penaliza se não há tokens relevantes

    razao_relevantes = len(rel_a & rel_b) / len(rel_a | rel_b)

    # Se não compartilham tokens relevantes, provavelmente não são a mesma notícia
    if razao_relevantes < 0.3:
        return min(_similaridade(a, b), 0.4)

    # Se compartilham muitos tokens relevantes, confirma com similaridade geral
    return max(razao_relevantes * 0.7 + _similaridade(a, b) * 0.3, razao_relevantes)


def _horas_desde_publicacao(publicado_em: str | None) -> float | None:
    """
    Calcula horas desde a publicação.

    Tenta RFC 822 (formato mais comum em RSS).
    Retorna None se não conseguir parsear.
    Retorna valor negativo se a data for no futuro (tratado pelo chamador).
    """
    if not publicado_em:
        return None

    dt: datetime | None = None

    # Tenta RFC 822 (email.utils) -- erros esperados quando a string nao
    # segue o formato: ValueError/TypeError. Nao usamos "except Exception"
    # aqui de proposito, pra nao engolir um bug real de outro tipo.
    try:
        dt = parsedate_to_datetime(str(publicado_em))
    except (ValueError, TypeError):
        pass

    # Fallback: ISO 8601
    if dt is None:
        try:
            dt = datetime.fromisoformat(str(publicado_em).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    if dt is None:
        return None

    # Garante timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    agora = datetime.now(timezone.utc)
    delta = agora - dt
    return delta.total_seconds() / 3600.0


def _calcular_peso_recencia(horas: float | None) -> tuple[float, str]:
    """
    Calcula o peso de recência com decaimento gradual.

    Retorna (peso, faixa_descritiva).
    Datas futuras (horas < 0) retornam peso 0.
    """
    if horas is None:
        return 0.0, "data_desconhecida"

    if horas < -1.0:
        # Data no futuro por mais de 1h — suspeita/inválida
        return 0.0, "data_futura"

    if horas <= 0:
        # Publicado "agora" ou no futuro imediato (possível timezone)
        return PESO_RECENCIA["ate_6h"], "ate_6h"

    if horas <= 6:
        return PESO_RECENCIA["ate_6h"], "ate_6h"
    if horas <= 24:
        return PESO_RECENCIA["ate_24h"], "ate_24h"
    if horas <= 48:
        return PESO_RECENCIA["ate_48h"], "ate_48h"
    if horas <= 72:
        return PESO_RECENCIA["ate_72h"], "ate_72h"

    # Decaimento suave após 72h
    dias_adicionais = (horas - 72) / 24
    decaimento = dias_adicionais * PESO_RECENCIA["decaimento_por_dia"]
    peso = max(0.0, PESO_RECENCIA["ate_72h"] - decaimento)
    return peso, f"antiga_{int(dias_adicionais)}d"


def _fonte_normalizada_para_peso(fonte: str | None) -> float:
    """Retorna o peso de uma fonte, com fallback para desconhecidas."""
    if not fonte:
        return PESO_FONTE_DESCONHECIDA
    chave = _normalizar(fonte)
    return PESO_FONTE.get(chave, PESO_FONTE_DESCONHECIDA)


def _categoria_normalizada_para_peso(categoria: str | None) -> float:
    """Retorna o peso de uma categoria, com fallback para desconhecidas."""
    if not categoria:
        return PESO_CATEGORIA_DESCONHECIDA
    chave = _normalizar(categoria)
    return PESO_CATEGORIA.get(chave, PESO_CATEGORIA_DESCONHECIDA)


# ---------------------------------------------------------------------------
# Editor-Chefe
# ---------------------------------------------------------------------------

class EditorChefe:
    """
    Orquestrador Nível 1 (sem LLM): decide o que entra na pauta e em
    que ordem. Instancie um por execução do pipeline de notícias.
    """

    def __init__(
        self,
        peso_categoria: dict[str, float] | None = None,
        peso_fonte: dict[str, float] | None = None,
        limiar_similaridade: float = LIMIAR_SIMILARIDADE_DUPLICATA,
        limiar_similaridade_rigoroso: float = LIMIAR_SIMILARIDADE_DUPLICATA_RIGOROSO,
        peso_fonte_desconhecida: float = PESO_FONTE_DESCONHECIDA,
        peso_categoria_desconhecida: float = PESO_CATEGORIA_DESCONHECIDA,
    ):
        self.peso_categoria = peso_categoria or dict(PESO_CATEGORIA)
        self.peso_fonte = peso_fonte or dict(PESO_FONTE)
        self.limiar_similaridade = limiar_similaridade
        self.limiar_similaridade_rigoroso = limiar_similaridade_rigoroso
        self.peso_fonte_desconhecida = peso_fonte_desconhecida
        self.peso_categoria_desconhecida = peso_categoria_desconhecida

    # -- validação --------------------------------------------------------

    def _validar_candidato(self, candidato: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Valida dados mínimos de um candidato.

        Retorna (válido, motivo_descarte).
        """
        titulo = candidato.get("titulo")
        if not titulo or not str(titulo).strip():
            return False, "titulo_vazio"

        # Título muito curto (menos de 10 chars) provavelmente é lixo
        if len(str(titulo).strip()) < 10:
            return False, "titulo_muito_curto"

        return True, None

    # -- duplicatas -------------------------------------------------------

    def remover_duplicadas(self, candidatos: list[dict]) -> list[dict]:
        """
        Agrupa candidatos que falam da mesma história e devolve só UM
        representante por grupo. O representante é escolhido por qualidade,
        não apenas por recência.

        Cada representante ganha:
        - _quantidade_fontes: quantos feeds diferentes cobriram
        - _fontes_relacionadas: lista das fontes
        - _links_relacionados: lista dos links
        """
        grupos: list[list[dict]] = []

        for candidato in candidatos:
            grupo_encontrado = None
            for grupo in grupos:
                if _similaridade(candidato.get("titulo", ""), grupo[0].get("titulo", "")) >= self.limiar_similaridade:
                    grupo_encontrado = grupo
                    break
            if grupo_encontrado is not None:
                grupo_encontrado.append(candidato)
            else:
                grupos.append([candidato])

        representantes = []
        for grupo in grupos:
            escolhido = self._escolher_representante(grupo)
            escolhido["_quantidade_fontes"] = len({c.get("fonte", "").strip().lower() for c in grupo if c.get("fonte")})
            escolhido["_fontes_relacionadas"] = sorted({c.get("fonte", "") for c in grupo if c.get("fonte")})
            escolhido["_links_relacionados"] = sorted({c.get("link", "") for c in grupo if c.get("link")})
            representantes.append(escolhido)

        return representantes

    def _escolher_representante(self, grupo: list[dict]) -> dict:
        """
        Escolhe o melhor representante de um grupo de duplicatas.

        Critérios (em ordem de importância):
        1. Qualidade da fonte (maior peso = melhor)
        2. Completude dos dados (tem resumo? tem link?)
        3. Recência (mais recente = melhor)
        4. Tamanho do título (mais descritivo = melhor)
        """
        def _score_representante(c: dict) -> tuple[float, float, float, int]:
            fonte = c.get("fonte", "")
            score_fonte = _fonte_normalizada_para_peso(fonte)

            completude = 0.0
            if c.get("resumo") and str(c["resumo"]).strip():
                completude += PESO_RESUMO_PRESENTE
            if c.get("link") and str(c["link"]).strip().startswith(("http://", "https://")):
                completude += PESO_LINK_VALIDO

            horas = _horas_desde_publicacao(c.get("publicado_em", ""))
            if horas is not None and horas >= -1.0:
                recencia_score = max(0.0, 1000.0 - horas)  # mais recente = maior
            else:
                recencia_score = 0.0

            titulo_len = len(str(c.get("titulo", "")).strip())

            return (-score_fonte, -completude, -recencia_score, -titulo_len)

        grupo_ordenado = sorted(grupo, key=_score_representante)
        return dict(grupo_ordenado[0])

    def descartar_ja_publicadas(
        self,
        candidatos: list[dict],
        titulos_existentes: list[str],
    ) -> list[dict]:
        """
        Remove candidatos muito parecidos com algo já publicado.

        Usa similaridade rigorosa para evitar falsos positivos.
        Notícias que parecem "atualizações" (similaridade moderada)
        são mantidas com flag para análise.
        """
        restantes = []
        for candidato in candidatos:
            titulo_cand = str(candidato.get("titulo", ""))

            # Verifica similaridade rigorosa com cada título existente
            eh_duplicata = False
            for titulo_existente in titulos_existentes:
                sim = _similaridade_rigorosa(titulo_cand, titulo_existente)
                if sim >= self.limiar_similaridade_rigoroso:
                    eh_duplicata = True
                    break

                # Se for similaridade moderada, pode ser atualização — mantém
                # mas marca internamente (não usado agora, mas disponível)
                if sim >= LIMIAR_SIMILARIDADE_ATUALIZACAO:
                    candidato["_possivel_atualizacao"] = True

            if not eh_duplicata:
                restantes.append(candidato)

        return restantes

    # -- score ------------------------------------------------------------

    def calcular_relevancia(self, candidato: dict, categoria: str) -> tuple[float, dict[str, float]]:
        """
        Calcula o score de relevância editorial e retorna os componentes.

        O score é composto por:
        - relevância temática (categoria)
        - confiabilidade da fonte
        - cobertura por múltiplas fontes
        - recência
        - completude dos dados

        Notícias muito recentes (≤6h) recebem um floor mínimo para
        garantir que notícias urgentes não morram por falta de peso
        de categoria/fonte.
        """
        componentes: dict[str, float] = {}

        # Relevância temática
        peso_cat = _categoria_normalizada_para_peso(categoria)
        componentes["categoria"] = peso_cat

        # Confiabilidade da fonte
        peso_fon = _fonte_normalizada_para_peso(candidato.get("fonte", ""))
        componentes["fonte"] = peso_fon

        # Cobertura por múltiplas fontes
        qtd_fontes = candidato.get("_quantidade_fontes", 1)
        if qtd_fontes >= PESO_MULTIPLAS_FONTES_MINIMO:
            peso_multi = PESO_MULTIPLAS_FONTES
        else:
            peso_multi = 0.0
        componentes["multiplas_fontes"] = peso_multi

        # Recência
        horas = _horas_desde_publicacao(candidato.get("publicado_em", ""))
        peso_rec, faixa = _calcular_peso_recencia(horas)
        componentes["recencia"] = peso_rec
        # 'faixa' (ex: "ate_6h", "antiga_3d") fica só no candidato interno --
        # é string, não cabe em componentes_score (que é só numérico, pra
        # dar pra somar/exibir). Quem quiser a faixa legível pode derivá-la
        # de horas_desde_publicacao usando _calcular_peso_recencia().
        candidato["_horas_desde_publicacao"] = horas

        # Completude dos dados
        peso_compl = 0.0
        if candidato.get("resumo") and str(candidato["resumo"]).strip():
            peso_compl += PESO_RESUMO_PRESENTE
        if candidato.get("link") and str(candidato["link"]).strip().startswith(("http://", "https://")):
            peso_compl += PESO_LINK_VALIDO
        componentes["completude"] = peso_compl

        # Score bruto
        score = sum(componentes[k] for k in ("categoria", "fonte", "multiplas_fontes", "recencia", "completude"))

        # Bônus de urgência para notícias muito recentes (≤6h):
        # notícias de alta qualidade editorial ganham boost proporcional
        # à força da categoria e da fonte. Isso garante que notícias
        # realmente importantes não fiquem abaixo de "Alta".
        #
        # Condição usa `peso_rec > 0` (não só `horas <= 6`) de propósito:
        # uma data futura/suspeita já cai em horas negativo, e
        # `horas <= 6` sozinho deixava passar esse caso (-10 <= 6 é
        # verdadeiro!), dando bônus de urgência pra uma data inválida.
        # `peso_rec` já vem zerado pra "data_futura" via
        # _calcular_peso_recencia, então reaproveitá-lo fecha essa brecha.
        eh_recente_valida = peso_rec > 0 and horas is not None and horas <= 6
        if eh_recente_valida:
            boost = min(20.0, (peso_cat + peso_fon) * 0.35)
            score += boost
            componentes["urgencia_recencia"] = boost
        else:
            componentes["urgencia_recencia"] = 0.0

        # Floor absoluto: notícias muito recentes nunca morrem por
        # falta de peso de categoria/fonte. Garante pelo menos "Média"
        # de verdade (o valor antigo, 48.0, ficava ABAIXO do piso de
        # Média e não cumpria o que o comentário prometia). Mesma
        # ressalva de data futura/inválida do bônus acima se aplica aqui.
        if peso_rec > 0 and horas is not None and horas <= HORAS_LIMITE_URGENCIA_RECENCIA:
            score = max(score, SCORE_FLOOR_URGENCIA_RECENCIA)

        return round(score, 2), componentes

    def _prioridade_para_score(self, score: float) -> str:
        """Converte score numérico em rótulo de prioridade editorial."""
        for limite, nome in FAIXAS_PRIORIDADE:
            if score >= limite:
                return nome
        return "Baixa"

    # -- diversidade ------------------------------------------------------

    def _aplicar_diversidade(self, pauta: list[ItemPauta]) -> list[ItemPauta]:
        """
        Reordena suavemente para evitar monotematização.

        Algoritmo: se houver mais de N itens consecutivos da mesma
        categoria, tenta inserir o próximo melhor de outra categoria.
        Não prejudica itens Urgentes (score >= 90).
        """
        if len(pauta) <= LIMITE_CONSECUTIVOS_MESMA_CATEGORIA:
            return pauta

        resultado: list[ItemPauta] = []
        fila = list(pauta)

        while fila:
            candidato = fila[0]  # espia o primeiro sem tirar da fila ainda

            # Conta quantos consecutivos da mesma categoria já temos no final
            consecutivos = 0
            for item in reversed(resultado):
                if _normalizar(item.categoria) == _normalizar(candidato.categoria):
                    consecutivos += 1
                else:
                    break

            # Se já atingiu o limite e o candidato não é urgente, tenta
            # publicar uma alternativa de outra categoria ANTES dele --
            # sem isso, o candidato ainda entrava neste mesmo turno e a
            # sequência ficava 1 item mais longa que o limite permitido.
            if (
                consecutivos >= LIMITE_CONSECUTIVOS_MESMA_CATEGORIA
                and candidato.score < 90
                and len(fila) > 1
            ):
                indice_alternativa = next(
                    (
                        i
                        for i in range(1, len(fila))
                        if _normalizar(fila[i].categoria) != _normalizar(candidato.categoria)
                    ),
                    None,
                )
                if indice_alternativa is not None:
                    alternativa = fila.pop(indice_alternativa)
                    resultado.append(alternativa)
                    continue  # candidato continua em fila[0], reavaliado no próximo laço
                # Sem alternativa disponível: diversidade não é obrigatória, segue normal

            fila.pop(0)
            resultado.append(candidato)

        return resultado

    # -- pauta ------------------------------------------------------------

    def montar_pauta(
        self,
        candidatos: list[dict],
        categoria: str,
        titulos_existentes: list[str] | None = None,
    ) -> list[ItemPauta]:
        """
        Recebe os candidatos crus de pesquisador.pesquisar_noticias(),
        valida, remove duplicatas (entre si e contra o banco, se
        titulos_existentes for informado), calcula score e devolve a
        fila já ordenada da maior pra menor prioridade.

        Parâmetros:
            candidatos: lista de dicts com dados brutos do pesquisador.
            categoria: categoria editorial atribuída ao lote.
            titulos_existentes: títulos já publicados (de qualquer agente).

        Retorna:
            Lista de ItemPauta ordenada por prioridade editorial.
        """
        # 1. Validação
        candidatos_validos = []
        for c in candidatos:
            valido, motivo = self._validar_candidato(c)
            if valido:
                candidatos_validos.append(dict(c))
            else:
                # Preserva para diagnóstico (não entra na pauta)
                c["_motivo_descarte"] = motivo

        if not candidatos_validos:
            return []

        # 2. Remove duplicatas internas
        sem_duplicatas = self.remover_duplicadas(candidatos_validos)

        # 3. Descarta já publicadas
        if titulos_existentes:
            sem_duplicatas = self.descartar_ja_publicadas(sem_duplicatas, titulos_existentes)

        # 4. Calcula score e monta pauta
        pauta: list[ItemPauta] = []
        for candidato in sem_duplicatas:
            score, componentes = self.calcular_relevancia(candidato, categoria)

            item = ItemPauta(
                titulo=str(candidato["titulo"]),
                resumo=str(candidato.get("resumo", "")),
                fonte=str(candidato.get("fonte", "")),
                link=str(candidato.get("link", "")),
                categoria=categoria,
                score=score,
                prioridade=self._prioridade_para_score(score),
                quantidade_fontes=candidato.get("_quantidade_fontes", 1),
                componentes_score=componentes,
                fontes_relacionadas=candidato.get("_fontes_relacionadas", []),
                links_relacionados=candidato.get("_links_relacionados", []),
                motivo_descarte=candidato.get("_motivo_descarte"),
                horas_desde_publicacao=candidato.get("_horas_desde_publicacao"),
                possivel_atualizacao=candidato.get("_possivel_atualizacao", False),
            )
            pauta.append(item)

        # 5. Ordenação determinística (score → recência → fontes → fonte → título)
        #
        # Nota sobre o campo de recência do desempate: precisa ser um valor
        # que, em ORDEM CRESCENTE (como sort() já faz por padrão), coloque
        # o item mais recente primeiro. Isso significa usar 'horas' direto
        # (SEM negativo) -- menos horas = mais recente = deve vir primeiro.
        # A versão anterior negava o valor, o que invertia esse critério
        # (fazia notícia antiga/sem data vencer notícia recente no
        # desempate) e além disso usava `horas or 999999`, que tratava uma
        # notícia publicada "agora" (horas == 0.0) como se a data fosse
        # desconhecida, porque 0.0 é falsy em Python.
        def _chave_ordenacao(item: ItemPauta) -> tuple:
            horas = item.horas_desde_publicacao
            chave_recencia = horas if horas is not None else float("inf")
            return (
                -item.score,
                chave_recencia,
                -item.quantidade_fontes,
                -_fonte_normalizada_para_peso(item.fonte),
                _normalizar(item.titulo),
            )

        pauta.sort(key=_chave_ordenacao)

        # 6. Diversidade suave (não prejudica urgentes)
        pauta = self._aplicar_diversidade(pauta)

        return pauta