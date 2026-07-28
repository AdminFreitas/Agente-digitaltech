"""
ebook_agent.py
----------------
Agente responsável por gerar ebooks completos a partir de um tema/outline:

1. Gera um sumário/outline estruturado (capítulos e subtópicos).
2. Escreve o conteúdo de cada capítulo.
3. Compila tudo em um arquivo .epub (via ebooklib) e/ou .pdf (via fpdf2).
"""

import os
from typing import Optional, Dict, Any, List

from .base_agent import BaseAgent


class EbookAgent(BaseAgent):
    """Agente gerador de ebooks: outline -> capítulos -> compilação em epub/pdf."""

    def __init__(self, model: str = "claude-sonnet-4-5", **kwargs):
        system_prompt_outline = (
            "Você é um autor e editor de ebooks. Dado um tema, gere um sumário "
            "estruturado e coerente.\n\n"
            "Responda APENAS com um JSON válido no formato:\n"
            "{\n"
            '  "titulo": "<título do ebook>",\n'
            '  "subtitulo": "<subtítulo opcional>",\n'
            '  "capitulos": [\n'
            '     {"titulo": "<título do capítulo>", "topicos": ["<subtópico 1>", "<subtópico 2>"]}\n'
            "  ]\n"
            "}"
        )
        super().__init__(
            name="EbookAgent",
            system_prompt=system_prompt_outline,
            model=model,
            max_tokens=2000,
            **kwargs,
        )
        self._chapter_system_prompt = (
            "Você é um autor especializado em conteúdo didático e envolvente. "
            "Escreva o conteúdo completo de UM capítulo de ebook em markdown, "
            "usando os subtópicos fornecidos como guia (podem virar subtítulos "
            "'##'). Não repita o título do capítulo como texto solto, apenas "
            "escreva o conteúdo. Seja claro, use exemplos quando fizer sentido."
        )

    def generate_outline(self, topic: str, num_chapters: int = 6, audience: Optional[str] = None) -> Dict[str, Any]:
        """Gera o sumário estruturado do ebook."""
        publico_txt = f"\nPúblico-alvo: {audience}" if audience else ""
        prompt = f"Tema do ebook: {topic}\nNúmero aproximado de capítulos: {num_chapters}{publico_txt}"
        resposta = self._call_llm(prompt)
        try:
            return self._extract_json(resposta)
        except ValueError:
            return {"titulo": topic, "subtitulo": "", "capitulos": []}

    def write_chapter(self, chapter_title: str, topics: List[str], book_title: str) -> str:
        """Escreve o conteúdo em markdown de um capítulo específico."""
        prompt = (
            f"Ebook: {book_title}\n"
            f"Capítulo: {chapter_title}\n"
            f"Subtópicos a cobrir: {', '.join(topics) if topics else '(livre)'}\n\n"
            "Escreva o conteúdo completo deste capítulo agora."
        )
        return self._call_llm(prompt, system_prompt_override=self._chapter_system_prompt, max_tokens_override=3000)

    def generate_full_book(self, topic: str, num_chapters: int = 6, audience: Optional[str] = None) -> Dict[str, Any]:
        """Pipeline: gera outline + escreve todos os capítulos, retornando tudo estruturado."""
        outline = self.generate_outline(topic, num_chapters=num_chapters, audience=audience)
        capitulos_com_conteudo = []
        for cap in outline.get("capitulos", []):
            conteudo = self.write_chapter(
                chapter_title=cap["titulo"],
                topics=cap.get("topicos", []),
                book_title=outline.get("titulo", topic),
            )
            capitulos_com_conteudo.append({"titulo": cap["titulo"], "conteudo_markdown": conteudo})

        return {
            "titulo": outline.get("titulo", topic),
            "subtitulo": outline.get("subtitulo", ""),
            "capitulos": capitulos_com_conteudo,
        }

    def export_epub(self, book: Dict[str, Any], output_path: str = "ebook.epub", author: str = "Autor Desconhecido") -> str:
        """Exporta o livro estruturado (de `generate_full_book`) para um arquivo .epub."""
        from ebooklib import epub

        livro = epub.EpubBook()
        livro.set_identifier(book.get("titulo", "ebook").lower().replace(" ", "-"))
        livro.set_title(book.get("titulo", "Ebook"))
        livro.set_language("pt")
        livro.add_author(author)

        capitulos_epub = []
        for i, cap in enumerate(book.get("capitulos", [])):
            c = epub.EpubHtml(title=cap["titulo"], file_name=f"cap_{i+1}.xhtml", lang="pt")
            corpo_html = cap["conteudo_markdown"].replace("\n", "<br/>")
            c.content = f"<h1>{cap['titulo']}</h1>{corpo_html}"
            livro.add_item(c)
            capitulos_epub.append(c)

        livro.toc = tuple(capitulos_epub)
        livro.add_item(epub.EpubNcx())
        livro.add_item(epub.EpubNav())
        livro.spine = ["nav"] + capitulos_epub

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        epub.write_epub(output_path, livro)
        return output_path

    def export_pdf(self, book: Dict[str, Any], output_path: str = "ebook.pdf") -> str:
        """Exporta o livro estruturado (de `generate_full_book`) para um arquivo .pdf simples."""
        from fpdf import FPDF

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)

        pdf.add_page()
        pdf.set_font("Helvetica", "B", 24)
        pdf.multi_cell(0, 12, book.get("titulo", "Ebook"))
        if book.get("subtitulo"):
            pdf.set_font("Helvetica", "I", 14)
            pdf.multi_cell(0, 10, book["subtitulo"])

        for cap in book.get("capitulos", []):
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 18)
            pdf.multi_cell(0, 10, cap["titulo"])
            pdf.ln(4)
            pdf.set_font("Helvetica", "", 12)
            texto_limpo = cap["conteudo_markdown"].replace("#", "").replace("*", "")
            pdf.multi_cell(0, 7, texto_limpo)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        pdf.output(output_path)
        return output_path

    def run(
        self,
        topic: str,
        output_path: str = "ebook.epub",
        num_chapters: int = 6,
        audience: Optional[str] = None,
        author: str = "Autor Desconhecido",
        formato: str = "epub",
    ) -> str:
        """Pipeline completo: outline -> capítulos -> exportação em epub ou pdf."""
        livro = self.generate_full_book(topic, num_chapters=num_chapters, audience=audience)
        if formato == "pdf":
            return self.export_pdf(livro, output_path=output_path)
        return self.export_epub(livro, output_path=output_path, author=author)


if __name__ == "__main__":
    agent = EbookAgent()
    outline = agent.generate_outline("Guia prático de produtividade para freelancers", num_chapters=4)
    print(outline)
    # Descomente para gerar o livro completo (várias chamadas ao modelo):
    # caminho = agent.run("Guia prático de produtividade para freelancers", output_path="outputs/ebook.epub")
    # print(f"Ebook salvo em: {caminho}")
