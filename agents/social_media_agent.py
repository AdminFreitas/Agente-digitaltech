"""
social_media_agent.py
-----------------------
Agente responsável por gerar posts otimizados para diferentes redes sociais
a partir de um mesmo conteúdo/base (artigo, ideia, produto, evento etc).
"""

from typing import Optional, List, Dict, Any

from .base_agent import BaseAgent

PLATAFORMAS_SUPORTADAS = [
    "instagram",
    "twitter_x",
    "linkedin",
    "facebook",
    "tiktok_script",
]


class SocialMediaAgent(BaseAgent):
    """Agente gerador de posts para redes sociais, adaptado por plataforma."""

    def __init__(self, model: str = "claude-sonnet-4-5", **kwargs):
        system_prompt = (
            "Você é um social media sênior, especialista em copywriting para "
            "redes sociais. Gere conteúdo adaptado ao formato, tom e limites "
            "de cada plataforma solicitada (ex: Twitter/X é curto e direto, "
            "LinkedIn é mais profissional, Instagram usa legenda + hashtags, "
            "TikTok pede um roteiro curto de vídeo com gancho nos 3 primeiros "
            "segundos).\n\n"
            "Responda APENAS com um JSON válido no formato:\n"
            "{\n"
            '  "plataforma_nome": {\n'
            '     "texto": "<copy/legenda/roteiro>",\n'
            '     "hashtags": ["#tag1", "#tag2"],\n'
            '     "sugestao_visual": "<breve sugestão de imagem/vídeo/formato>"\n'
            "  },\n"
            "  ...\n"
            "}"
        )
        super().__init__(
            name="SocialMediaAgent",
            system_prompt=system_prompt,
            model=model,
            **kwargs,
        )

    def run(
        self,
        content: str,
        platforms: Optional[List[str]] = None,
        tone: str = "envolvente e autêntico",
        target_audience: Optional[str] = None,
        cta: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Gera posts para as plataformas solicitadas a partir de um conteúdo base.

        Args:
            content: Texto-base (artigo, resumo, anúncio, ideia central).
            platforms: Lista de plataformas (subconjunto de PLATAFORMAS_SUPORTADAS).
                Se None, gera para todas as plataformas suportadas.
            tone: Tom de voz desejado.
            target_audience: Público-alvo, se relevante.
            cta: Call-to-action específico a incluir.
        """
        platforms = platforms or PLATAFORMAS_SUPORTADAS
        publico_txt = f"\nPúblico-alvo: {target_audience}" if target_audience else ""
        cta_txt = f"\nCall-to-action a incluir: {cta}" if cta else ""

        prompt = f"""Conteúdo/base para os posts:
---
{content}
---

Plataformas solicitadas: {", ".join(platforms)}
Tom de voz: {tone}{publico_txt}{cta_txt}"""

        resposta = self._call_llm(prompt)
        try:
            return self._extract_json(resposta)
        except ValueError:
            return {"erro": "Não foi possível interpretar a resposta.", "resposta_bruta": resposta}

    def generate_content_calendar(
        self,
        topics: List[str],
        platforms: Optional[List[str]] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Gera um lote de posts para uma lista de temas (ex: calendário semanal)."""
        return [
            {"tema": topic, "posts": self.run(topic, platforms=platforms, **kwargs)}
            for topic in topics
        ]


if __name__ == "__main__":
    agent = SocialMediaAgent()
    resultado = agent.run(
        content="Lançamos uma nova funcionalidade de colaboração em tempo real no nosso app.",
        platforms=["instagram", "linkedin"],
    )
    print(resultado)
