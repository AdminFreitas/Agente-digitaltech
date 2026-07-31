import logging
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from config.database import get_db
from repositories.produto_repository import ProdutoRepository
from repositories.artigo_repository import ArtigoRepository
from services.llm_service import gerar_artigo
from services.imagem_service import buscar_imagem_capa

logger = logging.getLogger("digitaltech")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="DigitalTech — Agente ADS",
    description="API de produtos e agente de publicação de artigos — Michel Freitas",
    version="2.2.0"
)

class ProdutoInput(BaseModel):
    nome: str = Field(..., min_length=2, max_length=100)
    descricao: str = Field(default="")
    preco: float = Field(..., gt=0)
    estoque: int = Field(..., ge=0)

class GerarArtigoInput(BaseModel):
    tema: str = Field(..., min_length=5, max_length=200, description="Tema do artigo a ser gerado")
    categoria: str = Field(default="Tecnologia", description="Categoria do artigo no blog")
    publicar_imediatamente: bool = Field(
        default=False,
        description="Se True, o artigo já entra como 'publicado'. Se False, entra como 'rascunho'."
    )

@app.get("/health", tags=["Sistema"])
def health_check():
    return {"status": "ok", "versao": "2.2.0", "projeto": "DigitalTech ADS"}

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

@app.post("/artigos/gerar", status_code=201, tags=["Agente de Artigos"])
def gerar_e_salvar_artigo(dados: GerarArtigoInput, db: Session = Depends(get_db)):
    """Gera um artigo (Ollama → OpenAI → Claude → Gemini), busca imagem de capa e salva no Neon."""
    try:
        artigo = gerar_artigo(dados.tema, dados.categoria)
    except Exception as exc:
        logger.exception("Falha ao gerar artigo")
        raise HTTPException(status_code=502, detail="Erro ao gerar artigo.") from exc

    repo = ArtigoRepository(db)
    if repo.buscar_por_slug(artigo["slug"]):
        raise HTTPException(status_code=409, detail=f"Já existe um artigo com o slug '{artigo['slug']}'")

    categoria_id = repo.buscar_categoria_id(artigo["categoria"])
    if categoria_id is None:
        raise HTTPException(
            status_code=422,
            detail=f"Categoria '{artigo['categoria']}' não existe no banco. Verifique o nome ou cadastre a categoria antes.",
        )

    status_inicial = "publicado" if dados.publicar_imediatamente else "rascunho"
    imagem = buscar_imagem_capa(dados.categoria)

    artigo_id = repo.criar(
        slug=artigo["slug"],
        titulo=artigo["titulo"],
        categoria_id=categoria_id,
        resumo=artigo["excerpt"],
        conteudo_markdown=artigo["conteudo_markdown"],
        status=status_inicial,
        imagem_url=imagem["url"] if imagem else None,
        imagem_autor=imagem["autor"] if imagem else None,
        imagem_link=imagem["link"] if imagem else None,
    )

    return {
        "id": artigo_id,
        "slug": artigo["slug"],
        "titulo": artigo["titulo"],
        "categoria": artigo["categoria"],
        "categoria_id": categoria_id,
        "status": status_inicial,
        "imagem": imagem["url"] if imagem else None,
        "mensagem": "Artigo gerado e salvo no banco Neon com sucesso.",
    }

@app.post("/artigos/publicar/{artigo_id}", tags=["Agente de Artigos"])
def publicar_artigo_existente(artigo_id: int, db: Session = Depends(get_db)):
    """Muda um artigo salvo como 'rascunho' para 'publicado'."""
    repo = ArtigoRepository(db)
    artigo = repo.buscar_por_id(artigo_id)
    if not artigo:
        raise HTTPException(status_code=404, detail="Artigo não encontrado")
    if artigo.status == "publicado":
        raise HTTPException(status_code=409, detail="Artigo já está publicado")
    repo.publicar(artigo_id)
    return {"id": artigo_id, "slug": artigo.slug, "status": "publicado", "mensagem": "Artigo publicado com sucesso."}

@app.get("/artigos", tags=["Agente de Artigos"])
def listar_artigos(db: Session = Depends(get_db)):
    repo = ArtigoRepository(db)
    artigos = repo.listar_todos()
    return {
        "artigos": [
            {
                "id": a.id, "slug": a.slug, "titulo": a.titulo,
                "categoria": a.categoria, "status": a.status,
                "data_publicacao": str(a.data_publicacao) if a.data_publicacao else None,
            }
            for a in artigos
        ]
    }

@app.get("/artigos/{artigo_id}", tags=["Agente de Artigos"])
def buscar_artigo(artigo_id: int, db: Session = Depends(get_db)):
    repo = ArtigoRepository(db)
    artigo = repo.buscar_por_id(artigo_id)
    if not artigo:
        raise HTTPException(status_code=404, detail="Artigo não encontrado")
    return dict(artigo._mapping)
