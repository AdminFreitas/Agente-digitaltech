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
        ├── remove duplicadas ENTRE os candidatos (mesma história em
        │   feeds diferentes vira 1 item só, com quantidade_fontes)
        ├── descarta candidatos muito parecidos com algo que já existe
        │   no banco (passe os títulos recentes de QUALQUER agente,
        │   já que Agente A e Agente B escrevem na mesma tabela)
        ├── calcula score de relevância (categoria, fonte, quantas
        │   fontes cobrem a mesma história, recência)
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
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime

# ---------------------------------------------------------------------------
# Configuração de score — ajuste livremente, é só um dicionário. Os nomes de
# categoria aqui usam a mesma normalização de imagem_service/pesquisador
# (sem acento, minúsculo), pra não depender de bater a grafia exata.
# ---------------------------------------------------------------------------

PESO_CATEGORIA = {
    "inteligencia artificial": 25,
    "banco de dados": 20,
    "programacao": 18,
    "ciberseguranca": 18,
    "cloud e devops": 15,
    "hardware": 10,
    "open source": 10,
    "carreira": 8,
}

PESO_FONTE = {
    "techcrunch": 20,
    "the verge": 18,
    "ars technica": 22,
    "hacker news": 15,
}

PESO_MULTIPLAS_FONTES = 20   # quando 2+ feeds cobrem a mesma história
PESO_RECENTE_24H = 15
PESO_RECENTE_72H = 7

LIMIAR_SIMILARIDADE_DUPLICATA = 0.6  # mesmo limiar sugerido pro resto do projeto

FAIXAS_PRIORIDADE = [
    (90, "Urgente"),
    (70, "Alta"),
    (50, "Média"),
    (0, "Baixa"),
]


# ---------------------------------------------------------------------------
# Modelo de saída
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


# ---------------------------------------------------------------------------
# Utilidades de texto — mesma abordagem usada em imagem_service/pesquisador
# ---------------------------------------------------------------------------

def _normalizar(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", sem_acento).strip()


def _similaridade(a: str, b: str) -> float:
    """
    Combina duas medidas porque manchetes de veículos diferentes sobre
    o MESMO fato costumam reordenar as palavras — SequenceMatcher
    sozinho penaliza isso demais (é sensível à ordem). Jaccard de
    tokens ignora ordem, então usamos o maior dos dois valores.
    """
    norm_a, norm_b = _normalizar(a), _normalizar(b)

    razao_sequencia = SequenceMatcher(None, norm_a, norm_b).ratio()

    tokens_a, tokens_b = set(norm_a.split()), set(norm_b.split())
    if tokens_a and tokens_b:
        razao_tokens = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    else:
        razao_tokens = 0.0

    return max(razao_sequencia, razao_tokens)


def _horas_desde_publicacao(publicado_em: str) -> float | None:
    """
    Tenta ler a data de publicação do RSS (formato RFC 822, o mais
    comum nesses feeds). Se não conseguir parsear, devolve None — o
    chamador trata isso como 'sem bônus de recência', nunca como erro.
    """
    if not publicado_em:
        return None
    try:
        dt = parsedate_to_datetime(publicado_em)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        agora = datetime.now(timezone.utc)
        return (agora - dt).total_seconds() / 3600
    except Exception:
        return None


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
        peso_categoria: dict | None = None,
        peso_fonte: dict | None = None,
        limiar_similaridade: float = LIMIAR_SIMILARIDADE_DUPLICATA,
    ):
        self.peso_categoria = peso_categoria or PESO_CATEGORIA
        self.peso_fonte = peso_fonte or PESO_FONTE
        self.limiar_similaridade = limiar_similaridade

    # -- duplicadas -----------------------------------------------------

    def remover_duplicadas(self, candidatos: list[dict]) -> list[dict]:
        """
        Agrupa candidatos que falam da mesma história (título muito
        parecido) e devolve só UM representante por grupo — o mais
        recente do grupo. Cada representante ganha a chave interna
        `_quantidade_fontes` (quantos feeds diferentes cobriram essa
        história), usada depois no score.
        """
        grupos: list[list[dict]] = []

        for candidato in candidatos:
            grupo_encontrado = None
            for grupo in grupos:
                if _similaridade(candidato["titulo"], grupo[0]["titulo"]) >= self.limiar_similaridade:
                    grupo_encontrado = grupo
                    break
            if grupo_encontrado is not None:
                grupo_encontrado.append(candidato)
            else:
                grupos.append([candidato])

        representantes = []
        for grupo in grupos:
            grupo_ordenado = sorted(
                grupo,
                key=lambda c: _horas_desde_publicacao(c.get("publicado_em", "")) or 999999,
            )
            escolhido = dict(grupo_ordenado[0])
            escolhido["_quantidade_fontes"] = len({c.get("fonte", "") for c in grupo})
            representantes.append(escolhido)

        return representantes

    def descartar_ja_publicadas(self, candidatos: list[dict], titulos_existentes: list[str]) -> list[dict]:
        """
        Remove candidatos muito parecidos com algo que JÁ está salvo no
        banco. Passe aqui os títulos recentes de `noticias` — de
        QUALQUER agente, já que Agente A e Agente B escrevem na mesma
        tabela. Puramente por similaridade de texto, sem LLM e sem
        tocar no banco (quem chama é responsável por buscar os títulos).
        """
        restantes = []
        for candidato in candidatos:
            ja_existe = any(
                _similaridade(candidato["titulo"], titulo) >= self.limiar_similaridade
                for titulo in titulos_existentes
            )
            if not ja_existe:
                restantes.append(candidato)
        return restantes

    # -- score ------------------------------------------------------------

    def calcular_relevancia(self, candidato: dict, categoria: str) -> float:
        score = 0.0

        score += self.peso_categoria.get(_normalizar(categoria), 0)
        score += self.peso_fonte.get(_normalizar(candidato.get("fonte", "")), 0)

        if candidato.get("_quantidade_fontes", 1) >= 2:
            score += PESO_MULTIPLAS_FONTES

        horas = _horas_desde_publicacao(candidato.get("publicado_em", ""))
        if horas is not None:
            if horas <= 24:
                score += PESO_RECENTE_24H
            elif horas <= 72:
                score += PESO_RECENTE_72H

        return score

    def _prioridade_para_score(self, score: float) -> str:
        for limite, nome in FAIXAS_PRIORIDADE:
            if score >= limite:
                return nome
        return "Baixa"

    # -- pauta ------------------------------------------------------------

    def montar_pauta(
        self,
        candidatos: list[dict],
        categoria: str,
        titulos_existentes: list[str] | None = None,
    ) -> list[ItemPauta]:
        """
        Recebe os candidatos crus de pesquisador.pesquisar_noticias(),
        remove duplicatas (entre si e contra o banco, se
        titulos_existentes for informado), calcula score e devolve a
        fila já ordenada da maior pra menor prioridade.
        """
        sem_duplicatas_internas = self.remover_duplicadas(candidatos)

        if titulos_existentes:
            sem_duplicatas_internas = self.descartar_ja_publicadas(
                sem_duplicatas_internas, titulos_existentes
            )

        pauta = []
        for candidato in sem_duplicatas_internas:
            score = self.calcular_relevancia(candidato, categoria)
            pauta.append(ItemPauta(
                titulo=candidato["titulo"],
                resumo=candidato.get("resumo", ""),
                fonte=candidato.get("fonte", ""),
                link=candidato.get("link", ""),
                categoria=categoria,
                score=score,
                prioridade=self._prioridade_para_score(score),
                quantidade_fontes=candidato.get("_quantidade_fontes", 1),
            ))

        pauta.sort(key=lambda item: item.score, reverse=True)
        return pauta
    