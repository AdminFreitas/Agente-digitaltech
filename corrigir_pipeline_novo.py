"""
corrigir_pipeline_novo.py
Corrige 5 bugs encontrados no pipeline novo (pesquisador/editor/revisor/
seo/publisher), todos causados pela mesma raiz: parte do código foi
escrito ANTES da migração categoria -> categoria_id, e outra parte
importa uma função (gerar_texto) que nunca foi criada em llm_service.py.

Bugs corrigidos:
  1. services/llm_service.py    — falta a função gerar_texto() que
     pesquisador.py, revisor.py e seo.py importam (ImportError hoje).
  2. agents/editor.py           — tinha DUAS definições de
     gerar_artigo_base(); a segunda (versão antiga, Ollama direto)
     sobrescrevia a primeira, com assinatura e retorno errados.
  3. agents/publisher.py        — salvar_artigo() passava
     categoria=... para repo.criar(), que agora exige categoria_id.
  4. agents/publisher.py        — publicar() lia artigo_db.categoria,
     coluna que não existe mais na tabela (só categoria_id).
  5. repositories/artigo_repository.py — listar_todos() e buscar_por_id
     não sabem transformar categoria_id de volta em nome de categoria.

Como usar:
  1. Copie este arquivo para dentro de ~/projetos/agente-ads
  2. Rode: python corrigir_pipeline_novo.py
"""

import os
import subprocess
import sys
import py_compile


def aplicar(caminho, antigo, novo, nome_mudanca):
    if not os.path.isfile(caminho):
        print(f"ERRO: não encontrei o arquivo {caminho}.")
        sys.exit(1)

    with open(caminho, "r", encoding="utf-8") as f:
        conteudo = f.read()

    ocorrencias = conteudo.count(antigo)
    if ocorrencias == 0:
        print(f"AVISO: trecho de '{nome_mudanca}' não encontrado em {caminho}.")
        print("Pode já ter sido corrigido, ou o arquivo mudou. Pulei esta edição.")
        return False
    if ocorrencias > 1:
        print(f"ERRO: trecho de '{nome_mudanca}' aparece {ocorrencias} vezes em {caminho}.")
        print("Edição abortada para não aplicar no lugar errado. Revise manualmente.")
        sys.exit(1)

    conteudo = conteudo.replace(antigo, novo)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    print(f"OK: '{nome_mudanca}' aplicado em {caminho}")
    return True


def sobrescrever(caminho, novo_conteudo, nome_mudanca):
    if not os.path.isfile(caminho):
        print(f"ERRO: não encontrei o arquivo {caminho}.")
        sys.exit(1)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(novo_conteudo)
    print(f"OK: '{nome_mudanca}' — {caminho} reescrito por completo")


if not os.path.isfile("app.py"):
    print("ERRO: rode este script DE DENTRO da pasta do repositório do agente.")
    sys.exit(1)

print("Aplicando correções...\n")

# --- Bug 1: gerar_texto() ausente em services/llm_service.py -----------

ANTIGO_LLM = '''def gerar_artigo(tema: str, categoria: str = "Tecnologia", tentativas_por_provedor: int = 2) -> dict:'''

NOVO_LLM = '''def gerar_texto(prompt: str, tentativas_por_provedor: int = 2) -> str:
    """
    Envia um prompt genérico para o mesmo fallback chain usado por
    gerar_artigo() (Ollama -> OpenAI -> Claude -> Gemini), mas devolve
    o texto bruto da resposta, sem parsing de título/resumo/corpo.
    Usado pelos agentes que nao escrevem artigos completos:
    pesquisador.py, revisor.py e seo.py.
    """
    erros = []
    for nome, funcao in PROVEDORES:
        for tentativa in range(1, tentativas_por_provedor + 1):
            try:
                print(f"[LLM] (gerar_texto) Tentando {nome} (tentativa {tentativa}/{tentativas_por_provedor})...")
                return funcao(prompt)
            except Exception as e:
                print(f"[LLM] (gerar_texto) {nome} falhou: {e}")
                erros.append(f"{nome}: {e}")
                break

    raise RuntimeError("Todos os provedores falharam:\\n" + "\\n".join(erros))


def gerar_artigo(tema: str, categoria: str = "Tecnologia", tentativas_por_provedor: int = 2) -> dict:'''

aplicar("services/llm_service.py", ANTIGO_LLM, NOVO_LLM, "adicionar gerar_texto()")

# --- Bug 2: agents/editor.py com função duplicada -----------------------

NOVO_EDITOR = '''"""
editor.py -- Agente redator

Recebe o tema (e, opcionalmente, o briefing do pesquisador.py) e
escreve o artigo completo, reaproveitando o fallback chain de
services.llm_service.gerar_artigo(). Devolve o mesmo formato de dict
usado pelo resto do pipeline (slug, titulo, categoria, excerpt,
readTime, conteudo_markdown, data, provedor).
"""

from services.llm_service import gerar_artigo as _gerar_artigo_llm


def gerar_artigo_base(tema: str, categoria: str, briefing: dict | None = None) -> dict:
    """
    Gera o artigo completo. `briefing` (opcional) vem de
    pesquisador.pesquisar_tema() -- hoje ainda nao e injetado no
    prompt (services.llm_service.gerar_artigo nao aceita briefing
    ainda); o parametro existe para nao quebrar a assinatura chamada
    por pipeline/gerar_artigos.py, e fica pronto pra ser usado assim
    que o prompt for ajustado para aproveita-lo.
    """
    return _gerar_artigo_llm(tema, categoria)
'''

sobrescrever("agents/editor.py", NOVO_EDITOR, "remover função gerar_artigo_base() duplicada/antiga")

# --- Bug 3 e 4: agents/publisher.py usando categoria em vez de categoria_id --

ANTIGO_PUB_SALVAR = '''def salvar_artigo(db, artigo: dict, imagem: dict | None) -> int:
    """
    Salva o artigo no Neon como rascunho (status='rascunho'). Retorna
    o ID gerado. Não publica no GitHub ainda — isso é publicar().
    """
    repo = ArtigoRepository(db)
    return repo.criar(
        slug=artigo["slug"],
        titulo=artigo.get("titulo_seo") or artigo["titulo"],
        categoria=artigo["categoria"],
        resumo=artigo.get("meta_description") or artigo.get("excerpt", ""),
        conteudo_markdown=artigo["conteudo_markdown"],
        status="rascunho",
        imagem_url=imagem["imagem_url"] if imagem else None,
        imagem_autor=imagem["imagem_autor"] if imagem else None,
        imagem_link=imagem["imagem_link"] if imagem else None,
    )'''

NOVO_PUB_SALVAR = '''def salvar_artigo(db, artigo: dict, imagem: dict | None) -> int:
    """
    Salva o artigo no Neon como rascunho (status='rascunho'). Retorna
    o ID gerado. Não publica no GitHub ainda — isso é publicar().
    """
    repo = ArtigoRepository(db)

    categoria_id = repo.buscar_categoria_id(artigo["categoria"])
    if categoria_id is None:
        raise ValueError(
            f"Categoria '{artigo['categoria']}' não existe no banco. "
            "Verifique o nome ou cadastre a categoria antes de salvar."
        )

    return repo.criar(
        slug=artigo["slug"],
        titulo=artigo.get("titulo_seo") or artigo["titulo"],
        categoria_id=categoria_id,
        resumo=artigo.get("meta_description") or artigo.get("excerpt", ""),
        conteudo_markdown=artigo["conteudo_markdown"],
        status="rascunho",
        imagem_url=imagem["imagem_url"] if imagem else None,
        imagem_autor=imagem["imagem_autor"] if imagem else None,
        imagem_link=imagem["imagem_link"] if imagem else None,
    )'''

aplicar("agents/publisher.py", ANTIGO_PUB_SALVAR, NOVO_PUB_SALVAR, "salvar_artigo() usa categoria_id")

ANTIGO_PUB_PUBLICAR = '''    artigo = {
        "titulo": artigo_db.titulo,
        "slug": artigo_db.slug,
        "categoria": artigo_db.categoria,
        "excerpt": artigo_db.resumo,
        "conteudo_markdown": artigo_db.conteudo_md,
        "readTime": artigo_db.tempo_leitura,
        "data": str(artigo_db.data_publicacao) if artigo_db.data_publicacao else date.today().isoformat(),
    }'''

NOVO_PUB_PUBLICAR = '''    categoria_nome = repo.buscar_categoria_nome(artigo_db.categoria_id)

    artigo = {
        "titulo": artigo_db.titulo,
        "slug": artigo_db.slug,
        "categoria": categoria_nome or "Tecnologia",
        "excerpt": artigo_db.resumo,
        "conteudo_markdown": artigo_db.conteudo_md,
        "readTime": artigo_db.tempo_leitura,
        "data": str(artigo_db.data_publicacao) if artigo_db.data_publicacao else date.today().isoformat(),
    }'''

aplicar("agents/publisher.py", ANTIGO_PUB_PUBLICAR, NOVO_PUB_PUBLICAR, "publicar() usa categoria_nome via categoria_id")

# --- Bug 5: repositories/artigo_repository.py sem suporte a categoria_id -> nome --

ANTIGO_REPO_METODOS = '''    def buscar_por_id(self, artigo_id: int):
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
        ).fetchall()'''

NOVO_REPO_METODOS = '''    def buscar_categoria_nome(self, categoria_id: int) -> str | None:
        """Busca o nome de uma categoria pelo ID -- usado para montar o
        front matter do Markdown publicado no GitHub."""
        resultado = self.db.execute(
            text("SELECT nome FROM categorias WHERE id = :id"),
            {"id": categoria_id},
        ).fetchone()
        return resultado[0] if resultado else None

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
                SELECT a.id, a.slug, a.titulo, c.nome AS categoria,
                       a.status, a.data_publicacao
                FROM artigos a
                LEFT JOIN categorias c ON c.id = a.categoria_id
                ORDER BY a.criado_em DESC LIMIT :limite
            """),
            {"limite": limite},
        ).fetchall()'''

aplicar(
    "repositories/artigo_repository.py",
    ANTIGO_REPO_METODOS,
    NOVO_REPO_METODOS,
    "listar_todos()/buscar_por_id() com suporte a categoria via categoria_id",
)

# --- Validação de sintaxe -------------------------------------------------
print("\nValidando sintaxe...")
for arquivo in [
    "services/llm_service.py",
    "agents/editor.py",
    "agents/publisher.py",
    "repositories/artigo_repository.py",
]:
    py_compile.compile(arquivo, doraise=True)
print("Sintaxe OK em todos os arquivos.")

# --- Diff e commit ---------------------------------------------------------
print("\n===== DIFF (revise antes de continuar) =====")
subprocess.run(["git", "diff"])
print("=============================================\n")

confirmacao = input(
    "As mudanças acima estão corretas? Digite 'sim' para commitar, "
    "ou qualquer outra tecla para cancelar: "
)

if confirmacao.strip().lower() != "sim":
    print("Cancelado. Nenhum commit foi feito.")
    sys.exit(0)

subprocess.run(
    [
        "git", "add",
        "services/llm_service.py",
        "agents/editor.py",
        "agents/publisher.py",
        "repositories/artigo_repository.py",
    ],
    check=True,
)
mensagem = (
    "fix: corrige 5 bugs do pipeline novo (categoria_id + gerar_texto ausente)\n\n"
    "- Adiciona gerar_texto() em llm_service.py (pesquisador/revisor/seo\n"
    "  importavam uma função que não existia -- ImportError).\n"
    "- Remove definição duplicada/antiga de gerar_artigo_base() em\n"
    "  editor.py (a versão que sobrevivia não aceitava briefing= e\n"
    "  devolvia string em vez de dict).\n"
    "- publisher.py: salvar_artigo() e publicar() agora resolvem\n"
    "  categoria_id/categoria_nome corretamente, em vez de referenciar\n"
    "  a coluna 'categoria' que não existe mais na tabela artigos.\n"
    "- artigo_repository.py: listar_todos() faz JOIN com categorias\n"
    "  (a query antiga quebraria GET /artigos); adiciona\n"
    "  buscar_categoria_nome()."
)
subprocess.run(["git", "commit", "-m", mensagem], check=True)

print("\nCommit feito. Para enviar ao GitHub, rode:")
print("  git push origin main")
