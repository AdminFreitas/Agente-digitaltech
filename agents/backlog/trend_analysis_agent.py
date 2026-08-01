"""
trend_analysis_agent.py
-------------------------
Agente responsável por analisar um conjunto de dados/textos (posts,
buscas, menções, métricas ao longo do tempo) e identificar tendências,
padrões emergentes e recomendações de ação.
"""

from typing import List, Dict, Any, Optional, Union
import statistics

from .base_agent import BaseAgent


class TrendAnalysisAgent(BaseAgent):
    """Agente de análise de tendências qualitativas e/ou numéricas."""

    def __init__(self, model: str = "claude-sonnet-4-5", **kwargs):
        system_prompt = (
            "Você é um analista de tendências e dados de mercado. Recebe uma "
            "coleção de textos (posts, comentários, títulos de notícias) e/ou "
            "estatísticas resumidas de séries temporais, e deve identificar: "
            "temas emergentes, mudanças de sentimento, sinais de alta/baixa e "
            "recomendações práticas.\n\n"
            "Responda APENAS com um JSON válido no formato:\n"
            "{\n"
            '  "tendencias_principais": [\n'
            '     {"tema": "<nome da tendência>", "descricao": "<explicação>", "forca": "alta"|"media"|"baixa"}\n'
            "  ],\n"
            '  "sentimento_geral": "positivo" | "negativo" | "neutro" | "misto",\n'
            '  "sinais_de_atencao": ["<risco ou oportunidade>", "..."],\n'
            '  "recomendacoes": ["<ação recomendada>", "..."]\n'
            "}"
        )
        super().__init__(
            name="TrendAnalysisAgent",
            system_prompt=system_prompt,
            model=model,
            max_tokens=2500,
            **kwargs,
        )

    @staticmethod
    def _resumo_estatistico(serie: List[float]) -> Dict[str, float]:
        """Calcula um resumo estatístico simples de uma série numérica (ex: menções/dia)."""
        if not serie:
            return {}
        variacao = ((serie[-1] - serie[0]) / serie[0] * 100) if serie[0] else 0.0
        return {
            "media": round(statistics.mean(serie), 2),
            "mediana": round(statistics.median(serie), 2),
            "minimo": min(serie),
            "maximo": max(serie),
            "variacao_percentual_inicio_fim": round(variacao, 2),
        }

    def run(
        self,
        texts: Optional[List[str]] = None,
        time_series: Optional[Dict[str, List[float]]] = None,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analisa tendências a partir de textos e/ou séries temporais numéricas.

        Args:
            texts: Lista de textos livres (posts, títulos, comentários).
            time_series: Dict opcional {"nome_da_metrica": [valores ao longo do tempo]}.
            context: Contexto adicional (ex: nicho, período analisado).
        """
        textos_txt = ""
        if texts:
            amostra = texts[:200]  # evita prompts gigantes
            textos_txt = "\n".join(f"- {t}" for t in amostra)

        estatisticas_txt = ""
        if time_series:
            resumos = {
                nome: self._resumo_estatistico(valores) for nome, valores in time_series.items()
            }
            estatisticas_txt = "\n".join(f"- {nome}: {resumo}" for nome, resumo in resumos.items())

        contexto_txt = f"\nContexto: {context}" if context else ""

        prompt = f"""{contexto_txt}

Textos analisados (amostra):
{textos_txt or '(nenhum texto fornecido)'}

Resumo estatístico de métricas ao longo do tempo:
{estatisticas_txt or '(nenhuma série temporal fornecida)'}"""

        resposta = self._call_llm(prompt)
        try:
            resultado = self._extract_json(resposta)
        except ValueError:
            resultado = {"erro": "Não foi possível interpretar a resposta.", "resposta_bruta": resposta}

        if time_series:
            resultado["estatisticas_calculadas"] = {
                nome: self._resumo_estatistico(valores) for nome, valores in time_series.items()
            }
        return resultado


if __name__ == "__main__":
    agent = TrendAnalysisAgent()
    resultado = agent.run(
        texts=[
            "Todo mundo comentando sobre o novo recurso de IA generativa no app",
            "Muitas reclamações sobre o tempo de resposta do suporte",
        ],
        time_series={"mencoes_diarias": [12, 18, 25, 40, 55]},
        context="Monitoramento de marca no último mês",
    )
    print(resultado)
