"""
newsletter_agent.py
---------------------
Agente responsável por montar newsletters a partir de uma lista de itens
(notícias, posts de blog, atualizações de produto etc), incluindo assunto
de e-mail, resumo executivo e HTML pronto para envio.
"""

from typing import List, Dict, Any, Optional

from .base_agent import BaseAgent


class NewsletterAgent(BaseAgent):
    """Agente que monta newsletters estruturadas (conteúdo + HTML)."""

    def __init__(self, model: str = "claude-sonnet-4-5", **kwargs):
        system_prompt = (
            "Você é um editor de newsletters experiente. Recebe uma lista de "
            "itens de conteúdo (título, resumo, link) e deve organizá-los em "
            "uma newsletter coesa, com uma introdução curta, seções bem "
            "definidas e uma chamada final.\n\n"
            "Responda APENAS com um JSON válido no formato:\n"
            "{\n"
            '  "assunto_email": "<linha de assunto atrativa, curta>",\n'
            '  "preview_text": "<texto de pré-visualização do e-mail>",\n'
            '  "introducao": "<parágrafo curto de abertura>",\n'
            '  "secoes": [\n'
            '     {"titulo": "<título da seção/item>", "resumo": "<resumo reescrito>", "link": "<link ou vazio>"}\n'
            "  ],\n"
            '  "fechamento": "<parágrafo de encerramento com CTA>"\n'
            "}"
        )
        super().__init__(
            name="NewsletterAgent",
            system_prompt=system_prompt,
            model=model,
            max_tokens=3000,
            **kwargs,
        )

    def run(
        self,
        items: List[Dict[str, str]],
        newsletter_name: str = "Newsletter",
        tone: str = "informativo e amigável",
        cta: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Monta o conteúdo estruturado da newsletter.

        Args:
            items: Lista de dicts, cada um com pelo menos "titulo" e "resumo",
                e opcionalmente "link".
            newsletter_name: Nome da newsletter/marca.
            tone: Tom de voz desejado.
            cta: Call-to-action principal a incluir no fechamento.
        """
        itens_txt = "\n".join(
            f"- Título: {i.get('titulo', '')}\n  Resumo: {i.get('resumo', '')}\n  Link: {i.get('link', '')}"
            for i in items
        )
        cta_txt = f"\nCall-to-action principal: {cta}" if cta else ""

        prompt = f"""Nome da newsletter: {newsletter_name}
Tom de voz: {tone}{cta_txt}

Itens de conteúdo para esta edição:
{itens_txt}"""

        resposta = self._call_llm(prompt)
        try:
            return self._extract_json(resposta)
        except ValueError:
            return {"erro": "Não foi possível interpretar a resposta.", "resposta_bruta": resposta}

    def render_html(self, newsletter_content: Dict[str, Any], brand_color: str = "#4F46E5") -> str:
        """
        Renderiza o conteúdo estruturado da newsletter (retornado por `run`)
        em um HTML simples, pronto para ser enviado por um provedor de e-mail.
        """
        secoes_html = ""
        for secao in newsletter_content.get("secoes", []):
            link_html = (
                f'<p><a href="{secao["link"]}" style="color:{brand_color};">Leia mais &rarr;</a></p>'
                if secao.get("link")
                else ""
            )
            secoes_html += f"""
            <tr>
                <td style="padding: 16px 0; border-bottom: 1px solid #eee;">
                    <h2 style="font-size:18px; margin:0 0 8px 0;">{secao.get('titulo', '')}</h2>
                    <p style="margin:0; color:#333;">{secao.get('resumo', '')}</p>
                    {link_html}
                </td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="UTF-8"><title>{newsletter_content.get('assunto_email', '')}</title></head>
<body style="font-family: Arial, sans-serif; background:#f4f4f5; margin:0; padding:24px;">
  <table width="100%" style="max-width:600px; margin:0 auto; background:#fff; border-radius:8px; overflow:hidden;">
    <tr><td style="background:{brand_color}; padding:20px; color:#fff; font-size:20px;">
        {newsletter_content.get('assunto_email', '')}
    </td></tr>
    <tr><td style="padding:20px;">
        <p style="color:#333;">{newsletter_content.get('introducao', '')}</p>
        <table width="100%">{secoes_html}</table>
        <p style="color:#333; margin-top:20px;">{newsletter_content.get('fechamento', '')}</p>
    </td></tr>
  </table>
</body>
</html>"""


if __name__ == "__main__":
    agent = NewsletterAgent()
    conteudo = agent.run(
        items=[
            {"titulo": "Nova funcionalidade X", "resumo": "Lançamos X para ajudar Y.", "link": "https://exemplo.com"},
        ],
        newsletter_name="Boletim Semanal",
    )
    print(agent.render_html(conteudo))
