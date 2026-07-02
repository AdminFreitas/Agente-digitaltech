import logging
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from config.database import get_db
from repositories.produto_repository import ProdutoRepository
from repositories.artigo_repository import ArtigoRepository
from services.llm_service import gerar_artigo
from services.github_service import publicar_artigo, artigo_existe

logger = logging.getLogger("digitaltech")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="DigitalTech — Agente ADS",
    description="API de produtos e agente de publicação de artigos — Michel Freitas",
    version="2.0.0"
)

# ─────────────────────────────────────────
# Schemas [Estruturas de validação]
# ─────────────────────────────────────────

class ProdutoInput(BaseModel):
    nome: str = Field(..., min_length=2, max_length=100)
    descricao: str = Field(default="")
    preco: float = Field(..., gt=0)
    estoque: int = Field(..., ge=0)

class GerarArtigoInput(BaseModel):
    tema: str = Field(..., min_length=5, max_length=200,
                      description="Tema do artigo a ser gerado")
    categoria: str = Field(default="Tecnologia",
                           description="Categoria do artigo no blog")
    publicar_imediatamente: bool = Field(
        default=False,
        description="Se True, publica no blog após gerar. Se False, apenas salva no banco."
    )

class PublicarArtigoInput(BaseModel):
    artigo_id: int = Field(..., description="ID do artigo gerado para publicar")

# ─────────────────────────────────────────
# Health check
# ─────────────────────────────────────────

@app.get("/health", tags=["Sistema"])
def health_check():
    """Verifica se a API está no ar."""
    return {"status": "ok", "versao": "2.0.0", "projeto": "DigitalTech ADS"}

# ─────────────────────────────────────────
# Rotas de Produtos (existentes)
# ─────────────────────────────────────────

@app.get("/produtos", tags=["Produtos"])
def listar_produtos(db: Session = Depends(get_db)):
    repo = ProdutoRepository(db)
    return {"produtos": [dict(p._mapping) for p in repo.listar_todos()]}

@app.get("/produtos/{produto_id}", tags=["Produtos"])
def buscar_produto(produto_id: int, db: Session = Depends(get_db)):
    repo = ProdutoRepository(db)
    produto = repo.buscar_por_id(produto_id)
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return dict(produto._mapping)

@app.post("/produtos", status_code=201, tags=["Produtos"])
def criar_produto(dados: ProdutoInput, db: Session = Depends(get_db)):
    repo = ProdutoRepository(db)
    repo.criar(dados.nome, dados.descricao, dados.preco, dados.estoque)
    return {"mensagem": "Produto criado com sucesso"}

@app.put("/produtos/{produto_id}", tags=["Produtos"])
def atualizar_produto(produto_id: int, dados: ProdutoInput, db: Session = Depends(get_db)):
    repo = ProdutoRepository(db)
    if not repo.buscar_por_id(produto_id):
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    repo.atualizar(produto_id, dados.nome, dados.descricao, dados.preco, dados.estoque)
    return {"mensagem": "Produto atualizado com sucesso"}

@app.delete("/produtos/{produto_id}", tags=["Produtos"])
def deletar_produto(produto_id: int, db: Session = Depends(get_db)):
    repo = ProdutoRepository(db)
    if not repo.buscar_por_id(produto_id):
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    repo.deletar(produto_id)
    return {"mensagem": "Produto desativado com sucesso"}

# ─────────────────────────────────────────
# Rotas do Agente de Artigos (novas)
# ─────────────────────────────────────────

@app.post("/artigos/gerar", status_code=201, tags=["Agente de Artigos"])
def gerar_e_salvar_artigo(dados: GerarArtigoInput, db: Session = Depends(get_db)):
    """
    Gera um artigo sobre o tema informado usando Gemini.
    Salva no banco com status 'gerado'.
    Se publicar_imediatamente=True, publica direto no blog.
    """
    # 1. Gera o artigo com Gemini
    try:
        artigo = gerar_artigo(dados.tema, dados.categoria)
    except Exception as exc:
        logger.exception("Falha ao gerar artigo")
        raise HTTPException(status_code=502, detail="Erro ao gerar artigo com Gemini.") from exc

    # 2. Verifica se o slug já existe no banco
    repo = ArtigoRepository(db)
    if repo.buscar_por_slug(artigo["slug"]):
        raise HTTPException(status_code=409,
                            detail=f"Já existe um artigo com o slug '{artigo['slug']}'")

    # 3. Salva no banco
    artigo_id = repo.criar(
        slug=artigo["slug"],
        titulo=artigo["titulo"],
        categoria=artigo["categoria"],
        excerpt=artigo["excerpt"],
        conteudo_markdown=artigo["conteudo_markdown"],
        read_time=artigo["readTime"],
        data_artigo=artigo["data"],
    )

    resposta = {
        "id": artigo_id,
        "slug": artigo["slug"],
        "titulo": artigo["titulo"],
        "categoria": artigo["categoria"],
        "excerpt": artigo["excerpt"],
        "status": "gerado",
        "mensagem": "Artigo gerado e salvo no banco com sucesso.",
    }

    # 4. Publica imediatamente se solicitado
    if dados.publicar_imediatamente:
        try:
            resultado = publicar_artigo(
                slug=artigo["slug"],
                conteudo_markdown=artigo["conteudo_markdown"],
                titulo=artigo["titulo"],
            )
            repo.marcar_publicado(artigo_id, resultado["github_url"], resultado["blog_url"])
            resposta["status"] = "publicado"
            resposta["blog_url"] = resultado["blog_url"]
            resposta["github_url"] = resultado["github_url"]
            resposta["mensagem"] = "Artigo gerado e publicado no blog com sucesso."
        except Exception as exc:
            repo.marcar_erro(artigo_id, str(exc)[:500])
            logger.exception("Falha na publicação imediata do artigo")
            raise HTTPException(status_code=502, detail="Artigo gerado, mas ocorreu um erro ao publicar.") from exc

    return resposta


@app.post("/artigos/publicar/{artigo_id}", tags=["Agente de Artigos"])
def publicar_artigo_existente(artigo_id: int, db: Session = Depends(get_db)):
    """
    Publica no blog um artigo já gerado e salvo no banco.
    Use quando quiser revisar antes de publicar.
    """
    repo = ArtigoRepository(db)
    artigo = repo.buscar_por_id(artigo_id)

    if not artigo:
        raise HTTPException(status_code=404, detail="Artigo não encontrado")

    if artigo.status == "publicado":
        raise HTTPException(status_code=409, detail="Artigo já está publicado")

    try:
        resultado = publicar_artigo(
            slug=artigo.slug,
            conteudo_markdown=artigo.conteudo_markdown,
            titulo=artigo.titulo,
        )
        repo.marcar_publicado(artigo_id, resultado["github_url"], resultado["blog_url"])
    except Exception as exc:
        repo.marcar_erro(artigo_id, str(exc)[:500])
        logger.exception("Falha ao publicar artigo existente")
        raise HTTPException(status_code=502, detail="Erro ao publicar o artigo.") from exc

    return {
        "id": artigo_id,
        "slug": artigo.slug,
        "status": "publicado",
        "blog_url": resultado["blog_url"],
        "github_url": resultado["github_url"],
        "mensagem": "Artigo publicado com sucesso. Deploy em andamento.",
    }


@app.get("/artigos", tags=["Agente de Artigos"])
def listar_artigos(db: Session = Depends(get_db)):
    """Lista todos os artigos gerados com seus status."""
    repo = ArtigoRepository(db)
    artigos = repo.listar_todos()
    return {
        "artigos": [
            {
                "id": a.id,
                "slug": a.slug,
                "titulo": a.titulo,
                "categoria": a.categoria,
                "status": a.status,
                "data_artigo": str(a.data_artigo),
                "publicado_em": str(a.publicado_em) if a.publicado_em else None,
            }
            for a in artigos
        ]
    }


@app.get("/artigos/{artigo_id}", tags=["Agente de Artigos"])
def buscar_artigo(artigo_id: int, db: Session = Depends(get_db)):
    """Retorna um artigo completo pelo ID."""
    repo = ArtigoRepository(db)
    artigo = repo.buscar_por_id(artigo_id)
    if not artigo:
        raise HTTPException(status_code=404, detail="Artigo não encontrado")
    return dict(artigo._mapping)
