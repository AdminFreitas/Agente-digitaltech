"""
noticia_repository.py — Acesso ao banco de dados para notícias

Grava e consulta notícias na tabela `noticias` do Neon. Schema
DIFERENTE de `artigos`:
- categoria é uma foreign key (`categoria_id`, tabela `categorias`),
  não texto livre — por isso _resolver_categoria_id() abaixo.
- tempo_leitura é INTEGER (minutos), não texto tipo "6 min".
- imagens ficam em DOIS lugares, de propósito:
    * tabela `imagens` (noticia_id, url, alt, principal) -- é o que o
      site (`src/lib/noticias.ts`) realmente consulta via LEFT JOIN
      para renderizar a página da notícia.
    * colunas `imagem_*` em `noticias` -- metadados de atribuição e
      auditoria (autor, link, fonte, query de busca, url original da
      matéria) que a tabela `imagens` não tem espaço para guardar.
  Os dois são gravados juntos, na mesma transação, dentro de criar().
- o conteúdo fica na coluna `conteudo_md` (renomeada de `conteudo`
  pela migração) — sem conteudo_html separado como em artigos, o
  front-end é quem renderiza o Markdown.
"""

import os
import re
import unicodedata
from sqlalchemy.orm import Session
from sqlalchemy import text

AUTOR_ID_AGENTE = int(os.getenv("AGENTE_AUTOR_ID", "2"))

# Usado só se a categoria pedida não bater com nenhuma linha real de
# `categorias` (nem exata, nem aproximada) — evita que a gravação
# quebre por causa de uma categoria mal escrita ou desatualizada.
CATEGORIA_ID_FALLBACK = 1  # "Inteligencia Artificial"


def _normalizar(texto: str) -> str:
    """minúsculas, sem acento, sem pontuação — pra comparar nomes de
    categoria com tolerância (ex.: 'Cloud & Devops' vs 'Cloud e DevOps',
    que é como está cadastrado de fato no banco)."""
    nfkd = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", sem_acento).strip()


def _similaridade_tokens(a: str, b: str) -> float:
    """Sobreposição de palavras (Jaccard) — ao contrário de checar
    substring, não quebra quando um pequeno conector muda (ex.: 'Cloud
    & Devops' vs 'Cloud e DevOps' só diferem no conector do meio)."""
    tokens_a, tokens_b = set(a.split()), set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


# Abreviações/sinônimos conhecidos usados em outros pontos do projeto
# (ex.: imagem_service.py trata "ia" como sinônimo de "inteligência
# artificial") que não têm sobreposição de palavras suficiente com o
# nome real da categoria pra bater sozinhos.
ALIASES_CATEGORIA = {
    "ia": "inteligencia artificial",
    "ai": "inteligencia artificial",
    "devops": "cloud e devops",
    "dev ops": "cloud e devops",
}

LIMIAR_SIMILARIDADE_CATEGORIA = 0.5


def _calcular_tempo_leitura_minutos(texto: str) -> int:
    palavras = len((texto or "").split())
    return max(1, round(palavras / 200))


class NoticiaRepository:
    def __init__(self, db: Session):
        self.db = db

    def _resolver_categoria_id(self, categoria: str) -> int:
        """
        Busca em `categorias` o id cujo nome mais se parece com o texto
        recebido. Tenta bater exato primeiro (normalizado), depois um
        alias conhecido (ex.: 'IA' -> 'inteligência artificial'),
        depois o nome com maior sobreposição de palavras acima do
        limiar. Se nada bater, usa CATEGORIA_ID_FALLBACK e avisa no
        log — nunca lança erro só por causa de categoria não encontrada.
        """
        alvo = _normalizar(categoria)
        alvo = ALIASES_CATEGORIA.get(alvo, alvo)
        linhas = self.db.execute(text("SELECT id, nome FROM categorias WHERE ativo = true")).fetchall()

        for linha in linhas:
            if _normalizar(linha.nome) == alvo:
                return linha.id

        melhor_linha, melhor_score = None, 0.0
        for linha in linhas:
            score = _similaridade_tokens(alvo, _normalizar(linha.nome))
            if score > melhor_score:
                melhor_linha, melhor_score = linha, score

        if melhor_linha and melhor_score >= LIMIAR_SIMILARIDADE_CATEGORIA:
            print(f"[NoticiaRepository] Categoria '{categoria}' não bateu exato — usando '{melhor_linha.nome}' (similaridade {melhor_score:.2f}).")
            return melhor_linha.id

        print(f"[NoticiaRepository] Categoria '{categoria}' não encontrada em `categorias` (nem aproximada) — usando fallback id={CATEGORIA_ID_FALLBACK}. Considere cadastrar essa categoria ou revisar o nome usado no resto do projeto.")
        return CATEGORIA_ID_FALLBACK

    def criar(
        self,
        slug: str,
        titulo: str,
        categoria: str,
        resumo: str,
        conteudo: str,
        fonte: str = "",
        url_fonte: str = "",
        status: str = "rascunho",
        meta_title: str | None = None,
        meta_description: str | None = None,
        imagem_url: str | None = None,
        imagem_original_url: str | None = None,
        imagem_alt: str | None = None,
        imagem_fonte: str | None = None,
        imagem_autor: str | None = None,
        imagem_link: str | None = None,
        imagem_query: str | None = None,
    ) -> int:
        """Salva uma nova notícia. Retorna o ID gerado.

        Se `imagem_url` for informado (deve ser a og:image extraída da
        matéria original, nunca uma foto genérica de banco de imagens),
        a imagem também é gravada como principal na tabela `imagens` e
        os metadados de atribuição são preenchidos em `noticias`,
        dentro da MESMA transação da criação da notícia. Se
        `imagem_url` não for informado, o comportamento é idêntico ao
        de antes — nenhuma linha em `imagens`, colunas `imagem_*` de
        `noticias` ficam NULL.

        Se qualquer etapa falhar (INSERT da notícia, INSERT da imagem
        ou UPDATE dos metadados), a transação inteira é desfeita — não
        fica notícia sem imagem nem imagem "órfã".
        """
        categoria_id = self._resolver_categoria_id(categoria)
        tempo_leitura = _calcular_tempo_leitura_minutos(conteudo)

        try:
            resultado = self.db.execute(
                text("""
                    INSERT INTO noticias (
                        titulo, slug, resumo, conteudo_md, autor_id, categoria_id,
                        status, destaque, tempo_leitura, fonte, url_fonte,
                        meta_title, meta_description, visualizacoes, data_publicacao
                    ) VALUES (
                        :titulo, :slug, :resumo, :conteudo_md, :autor_id, :categoria_id,
                        :status, false, :tempo_leitura, :fonte, :url_fonte,
                        :meta_title, :meta_description, 0, NOW()
                    )
                    RETURNING id
                """),
                {
                    "titulo": titulo[:300],
                    "slug": slug[:320],
                    "resumo": resumo,
                    "conteudo_md": conteudo,
                    "autor_id": AUTOR_ID_AGENTE,
                    "categoria_id": categoria_id,
                    "status": status,
                    "tempo_leitura": tempo_leitura,
                    "fonte": (fonte or "")[:200],
                    "url_fonte": url_fonte or "",
                    "meta_title": (meta_title or titulo)[:70],
                    "meta_description": (meta_description or resumo)[:165],
                },
            )
            noticia_id = resultado.fetchone()[0]

            if imagem_url:
                self.db.execute(
                    text("""
                        INSERT INTO imagens (noticia_id, url, alt, principal)
                        VALUES (:noticia_id, :url, :alt, true)
                    """),
                    {
                        "noticia_id": noticia_id,
                        "url": imagem_url,
                        "alt": imagem_alt,
                    },
                )

                self.db.execute(
                    text("""
                        UPDATE noticias
                        SET imagem_url = :imagem_url,
                            imagem_original_url = :imagem_original_url,
                            imagem_alt = :imagem_alt,
                            imagem_fonte = :imagem_fonte,
                            imagem_autor = :imagem_autor,
                            imagem_link = :imagem_link,
                            imagem_query = :imagem_query
                        WHERE id = :id
                    """),
                    {
                        "imagem_url": imagem_url,
                        "imagem_original_url": imagem_original_url,
                        "imagem_alt": imagem_alt,
                        "imagem_fonte": imagem_fonte,
                        "imagem_autor": imagem_autor,
                        "imagem_link": imagem_link,
                        "imagem_query": imagem_query,
                        "id": noticia_id,
                    },
                )

            self.db.commit()
            return noticia_id

        except Exception:
            self.db.rollback()
            raise

    def publicar(self, noticia_id: int) -> None:
        """Muda o status de uma notícia existente para 'publicado'."""
        self.db.execute(
            text("UPDATE noticias SET status = 'publicado', atualizado_em = NOW() WHERE id = :id"),
            {"id": noticia_id},
        )
        self.db.commit()

    def buscar_por_id(self, noticia_id: int):
        return self.db.execute(
            text("SELECT * FROM noticias WHERE id = :id"), {"id": noticia_id}
        ).fetchone()

    def buscar_por_slug(self, slug: str):
        return self.db.execute(
            text("SELECT * FROM noticias WHERE slug = :slug"), {"slug": slug}
        ).fetchone()

    def listar_titulos_recentes(self, limite: int = 100) -> list[str]:
        """Só os títulos, pra checagem de duplicidade (EditorChefe) sem
        trazer o conteúdo inteiro de cada notícia."""
        linhas = self.db.execute(
            text("SELECT titulo FROM noticias ORDER BY criado_em DESC LIMIT :limite"),
            {"limite": limite},
        ).fetchall()
        return [linha.titulo for linha in linhas]

    def listar_recentes(self, limite: int = 50):
        return self.db.execute(
            text("""
                SELECT id, slug, titulo, categoria_id, status, fonte, url_fonte, criado_em
                FROM noticias ORDER BY criado_em DESC LIMIT :limite
            """),
            {"limite": limite},
        ).fetchall()
