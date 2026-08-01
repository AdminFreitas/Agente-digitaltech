"""
infographic_agent.py
-----------------------
Agente responsável por transformar um conteúdo bruto (texto, dados, relatório)
em uma estrutura de infográfico e renderizá-la como imagem PNG usando matplotlib.

Não depende de nenhum serviço externo de design: a geração visual é feita
localmente, o que garante que o agente funcione de forma autocontida.
"""

import os
from typing import Optional, Dict, Any, List

import matplotlib
matplotlib.use("Agg")  # backend sem interface gráfica, seguro para servidores
import matplotlib.pyplot as plt

from .base_agent import BaseAgent


class InfographicAgent(BaseAgent):
    """Agente que estrutura conteúdo e gera um infográfico em PNG."""

    def __init__(self, model: str = "claude-sonnet-4-5", **kwargs):
        system_prompt = (
            "Você é um designer de informação (data storyteller). Dado um "
            "conteúdo bruto, extraia os pontos-chave em uma estrutura enxuta "
            "e visual para um infográfico vertical.\n\n"
            "Responda APENAS com um JSON válido no formato:\n"
            "{\n"
            '  "titulo": "<título curto e impactante>",\n'
            '  "subtitulo": "<subtítulo/contexto>",\n'
            '  "estatisticas": [\n'
            '     {"valor": "<número ou dado curto, ex: 87%>", "rotulo": "<o que representa>"}\n'
            "  ],\n"
            '  "pontos_chave": ["<insight curto 1>", "<insight curto 2>", "..."],\n'
            '  "fonte": "<fonte dos dados, se houver>"\n'
            "}\n"
            "Limite a no máximo 4 estatísticas e 5 pontos-chave, todos bem curtos "
            "(cabem em um card visual)."
        )
        super().__init__(
            name="InfographicAgent",
            system_prompt=system_prompt,
            model=model,
            **kwargs,
        )

    def structure_content(self, raw_content: str) -> Dict[str, Any]:
        """Usa o modelo para transformar conteúdo bruto na estrutura do infográfico."""
        resposta = self._call_llm(f"Conteúdo bruto:\n---\n{raw_content}\n---")
        try:
            return self._extract_json(resposta)
        except ValueError:
            return {
                "titulo": "Infográfico",
                "subtitulo": "",
                "estatisticas": [],
                "pontos_chave": [raw_content[:200]],
                "fonte": "",
            }

    def render_image(
        self,
        structured_content: Dict[str, Any],
        output_path: str = "infografico.png",
        accent_color: str = "#4F46E5",
    ) -> str:
        """Renderiza a estrutura do infográfico como uma imagem PNG vertical."""
        fig_height = 6 + len(structured_content.get("pontos_chave", [])) * 0.6
        fig, ax = plt.subplots(figsize=(6, fig_height))
        ax.axis("off")

        y = 1.0
        ax.text(0.5, y, structured_content.get("titulo", ""), fontsize=22, weight="bold",
                ha="center", va="top", color="#111827", wrap=True)
        y -= 0.08
        if structured_content.get("subtitulo"):
            ax.text(0.5, y, structured_content["subtitulo"], fontsize=13, ha="center",
                    va="top", color="#6B7280")
            y -= 0.08

        # Estatísticas em destaque, lado a lado
        stats = structured_content.get("estatisticas", [])
        if stats:
            n = len(stats)
            largura = 1.0 / n
            for i, stat in enumerate(stats):
                x_centro = largura * i + largura / 2
                ax.text(x_centro, y - 0.05, stat.get("valor", ""), fontsize=20, weight="bold",
                        ha="center", va="top", color=accent_color)
                ax.text(x_centro, y - 0.12, stat.get("rotulo", ""), fontsize=10, ha="center",
                        va="top", color="#374151", wrap=True)
            y -= 0.22

        # Linha divisória
        ax.axhline(y, color="#E5E7EB", linewidth=1)
        y -= 0.05

        # Pontos-chave como lista com marcadores
        for ponto in structured_content.get("pontos_chave", []):
            ax.text(0.05, y, "●", fontsize=12, color=accent_color, va="top")
            ax.text(0.10, y, ponto, fontsize=12, va="top", color="#111827", wrap=True)
            y -= 0.09

        if structured_content.get("fonte"):
            ax.text(0.5, 0.02, f"Fonte: {structured_content['fonte']}", fontsize=9,
                    ha="center", color="#9CA3AF")

        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        plt.tight_layout()
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
        plt.close(fig)
        return output_path

    def run(
        self,
        raw_content: str,
        output_path: str = "infografico.png",
        accent_color: str = "#4F46E5",
    ) -> str:
        """Pipeline completo: estrutura o conteúdo e gera a imagem final."""
        estrutura = self.structure_content(raw_content)
        return self.render_image(estrutura, output_path=output_path, accent_color=accent_color)


if __name__ == "__main__":
    agent = InfographicAgent()
    caminho = agent.run(
        raw_content=(
            "Nossa pesquisa com 500 usuários mostrou que 87% preferem o novo "
            "fluxo de checkout, reduzindo o tempo médio de compra em 40%. "
            "A taxa de abandono de carrinho caiu de 32% para 18%."
        ),
        output_path="outputs/infografico_checkout.png",
    )
    print(f"Infográfico salvo em: {caminho}")
