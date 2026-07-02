"""
artigo_repository.py — Acesso ao banco de dados para artigos

Grava e consulta artigos direto na tabela `artigos` do Neon
(o mesmo banco que o site DigitalTech lê).
"""

import os
import markdown
from sqlalchemy.orm import Session
from sqlalchemy import text

AUTOR_ID_AGENTE = int(os.getenv("AGENTE_AUTOR_ID", "2"))


def _calcular_tempo_leitura(texto_markdown: str) -> str:
    palavras = len(texto_markdown.split())
    minutos = max(1, round(palavras / 200))
    return f"{minutos} min"


class ArtigoRepository:
    def __init__(self, db: Session):
        self.db = db

    def criar(
        self,
        slug: str,
        titulo: str,
        categoria: str,
        resumo: str,
        conteudo_markdown: str,
        status: str = "rascunho",
        imagem_url: str | None = None,
        imagem_autor: str | None = None,
        imagem_link: str | None = None,
    ) -> int:
        """Salva um novo artigo. Retorna o ID gerado."""
        conteudo_html = markdown.markdown(conteudo_markdown)
        tempo_leitura = _calcular_tempo_leitura(conteudo_markdown)

        resultado = self.db.execute(
            text("""
                INSERT INTO artigos (
                    titulo, slug, resumo, conteudo_md, conteudo_html,
                    categoria, autor_id, status, tempo_leitura,
                    imagem_url, imagem_autor, imagem_link, data_publicacao
                ) VALUES (
                    :titulo, :slug, :resumo, :conteudo_md, :conteudo_html,
                    :categoria, :autor_id, :status, :tempo_leitura,
                    :imagem_url, :imagem_autor, :imagem_link, NOW()
                )
                RETURNING id
            """),
            {
                "titulo": titulo,
                "slug": slug,
                "resumo": resumo,
                "conteudo_md": conteudo_markdown,
                "conteudo_html": conteudo_html,
                "categoria": categoria,
                "autor_id": AUTOR_ID_AGENTE,
                "status": status,
                "tempo_leitura": tempo_leitura,
                "imagem_url": imagem_url,
                "imagem_autor": imagem_autor,
                "imagem_link": imagem_link,
            },
        )
        self.db.commit()
        return resultado.fetchone()[0]

    def publicar(self, artigo_id: int) -> None:
        """Muda o status de um artigo existente para 'publicado'."""
        self.db.execute(
            text("UPDATE artigos SET status = 'publicado', atualizado_em = NOW() WHERE id = :id"),
            {"id": artigo_id},
        )
        self.db.commit()

    def buscar_por_id(self, artigo_id: int):
        return self.db.execute(
            text("SELECT * FROM artigos WHERE id = :id"), {"id": artigo_id}
        ).fetchone()

    def buscar_por_slug(self, slug: str):
        return self.db.execute(
            text("SELECT * FROM artigos WHERE slug = :slug"), {"slug": slug}
        ).fetchone()

    def listar_todos(self, limite: int = 50):
        return self.db.execute(
            text("""
                SELECT id, slug, titulo, categoria, status, data_publicacao
                FROM artigos ORDER BY criado_em DESC LIMIT :limite
            """),
            {"limite": limite},
        ).fetchall()
