"""
translation_agent.py
---------------------
Agente responsável por traduzir textos entre idiomas, preservando tom,
formatação e terminologia específica (glossário opcional).
"""

from typing import Optional, List, Dict

from .base_agent import BaseAgent


class TranslationAgent(BaseAgent):
    """Agente de tradução profissional com suporte a glossário e tom."""

    def __init__(self, model: str = "claude-sonnet-4-5", **kwargs):
        system_prompt = (
            "Você é um tradutor profissional multilíngue. Traduza o texto do "
            "usuário mantendo o sentido original, o tom, a formatação "
            "(markdown, quebras de parágrafo, listas) e a terminologia técnica "
            "quando aplicável. Não adicione comentários, explicações ou notas "
            "de tradução: responda apenas com o texto traduzido."
        )
        super().__init__(
            name="TranslationAgent",
            system_prompt=system_prompt,
            model=model,
            **kwargs,
        )

    def run(
        self,
        text: str,
        target_language: str,
        source_language: str = "detectar automaticamente",
        tone: str = "neutro",
        glossary: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Traduz um texto.

        Args:
            text: Texto a ser traduzido.
            target_language: Idioma de destino (ex: "inglês", "espanhol").
            source_language: Idioma de origem, ou deixe o valor padrão para
                detecção automática.
            tone: Tom desejado (ex: "formal", "casual", "técnico").
            glossary: Dicionário opcional {termo_original: termo_traduzido}
                para forçar traduções específicas (nomes de produto, jargão etc).
        """
        glossary_txt = ""
        if glossary:
            pares = "\n".join(f"- '{k}' -> '{v}'" for k, v in glossary.items())
            glossary_txt = f"\n\nGlossário obrigatório (respeite estas traduções):\n{pares}"

        prompt = f"""Idioma de origem: {source_language}
Idioma de destino: {target_language}
Tom desejado: {tone}{glossary_txt}

Texto a traduzir:
---
{text}
---"""
        return self._call_llm(prompt)

    def translate_batch(
        self,
        texts: List[str],
        target_language: str,
        **kwargs,
    ) -> List[str]:
        """Traduz uma lista de textos (ex: legendas, itens de UI) para o mesmo idioma."""
        return [self.run(t, target_language, **kwargs) for t in texts]


if __name__ == "__main__":
    agent = TranslationAgent()
    resultado = agent.run(
        text="Nosso produto ajuda equipes a colaborar em tempo real.",
        target_language="inglês",
        tone="marketing, entusiasmado",
    )
    print(resultado)
