"""
api.py — Endpoints HTTP para controle do fluxo de notícias

Expõe rotas REST para integração com painel web ou serviços externos.
"""

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy.orm import Session
from database import get_db
from repositories.noticia_repository import NoticiaRepository

app = FastAPI(
    title="API de Notícias e Agente de IA",
    description="Interface para listagem, criação, edição e monitoramento do pipeline de notícias.",
    version="1.0.0"
)

# Habilita CORS para integração com o Front-end
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Schemas Pydantic ---

class NoticiaCreateSchema(BaseModel):
    titulo: str = Field(..., max_length=300)
    slug: str = Field(..., max_length=320)
    resumo: str
    conteudo: str
    categoria: str
    fonte: Optional[str] = ""
    url_fonte: Optional[str] = ""
    status: Optional[str] = "rascunho"
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    imagem_url: Optional[str] = None
    imagem_original_url: Optional[str] = None
    imagem_alt: Optional[str] = None
    imagem_fonte: Optional[str] = None
    imagem_autor: Optional[str] = None
    imagem_link: Optional[str] = None
    imagem_query: Optional[str] = None
    rss_guid: Optional[str] = None
    provedor_llm: Optional[str] = None
    modelo_llm: Optional[str] = None
    tempo_geracao_ms: Optional[int] = None


class NoticiaUpdateSchema(BaseModel):
    titulo: Optional[str] = None
    slug: Optional[str] = None
    resumo: Optional[str] = None
    conteudo_md: Optional[str] = None
    status: Optional[str] = None
    fonte: Optional[str] = None
    url_fonte: Optional[str] = None


# --- Helper de Serialização ---

def _row_to_dict(row) -> dict:
    """Converte um objeto Row do SQLAlchemy em um dicionário Python simples."""
    if hasattr(row, "_asdict"):
        return row._asdict()
    elif hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row)


# --- Rotas da API ---

@app.get("/health", tags=["Infraestrutura"])
def health_check():
    return {"status": "ok", "servico": "API Notícias"}


@app.get("/api/dashboard", tags=["Dashboard"])
def obter_dashboard(db: Session = Depends(get_db)):
    """Retorna estatísticas gerais e as notícias mais recentes."""
    repo = NoticiaRepository(db)
    noticias = repo.listar_todos(limite=10)
    
    lista_noticias = [_row_to_dict(n) for n in noticias]
    
    return {
        "status_pipeline": "ativo",
        "total_noticias_recentes": len(lista_noticias),
        "ultimas_noticias": lista_noticias
    }


@app.get("/api/conteudos", tags=["Notícias"])
def listar_conteudos(
    limite: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lista todas as notícias cadastradas no banco."""
    repo = NoticiaRepository(db)
    noticias = repo.listar_todos(limite=limite)
    return [_row_to_dict(n) for n in noticias]


@app.get("/api/conteudos/{noticia_id}", tags=["Notícias"])
def buscar_conteudo_por_id(noticia_id: int, db: Session = Depends(get_db)):
    """Busca os detalhes de uma notícia pelo seu ID."""
    repo = NoticiaRepository(db)
    noticia = repo.buscar_por_id(noticia_id)
    if not noticia:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Notícia com ID {noticia_id} não encontrada."
        )
    return _row_to_dict(noticia)


@app.post("/api/conteudos", status_code=status.HTTP_201_CREATED, tags=["Notícias"])
def criar_conteudo(payload: NoticiaCreateSchema, db: Session = Depends(get_db)):
    """Insere manualmente uma notícia e suas imagens associadas."""
    repo = NoticiaRepository(db)
    
    if payload.rss_guid and repo.buscar_por_rss_guid(payload.rss_guid):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe uma notícia cadastrada com este rss_guid."
        )

    try:
        noticia_id = repo.criar(
            slug=payload.slug,
            titulo=payload.titulo,
            categoria=payload.categoria,
            resumo=payload.resumo,
            conteudo=payload.conteudo,
            fonte=payload.fonte or "",
            url_fonte=payload.url_fonte or "",
            status=payload.status or "rascunho",
            meta_title=payload.meta_title,
            meta_description=payload.meta_description,
            imagem_url=payload.imagem_url,
            imagem_original_url=payload.imagem_original_url,
            imagem_alt=payload.imagem_alt,
            imagem_fonte=payload.imagem_fonte,
            imagem_autor=payload.imagem_autor,
            imagem_link=payload.imagem_link,
            imagem_query=payload.imagem_query,
            rss_guid=payload.rss_guid,
            provedor_llm=payload.provedor_llm,
            modelo_llm=payload.modelo_llm,
            tempo_geracao_ms=payload.tempo_geracao_ms,
        )
        return {"id": noticia_id, "mensagem": "Notícia criada com sucesso."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao salvar notícia: {str(e)}"
        )


@app.put("/api/conteudos/{noticia_id}", tags=["Notícias"])
def atualizar_conteudo(
    noticia_id: int, 
    payload: NoticiaUpdateSchema, 
    db: Session = Depends(get_db)
):
    """Atualiza campos de uma notícia existente."""
    repo = NoticiaRepository(db)
    
    noticia = repo.buscar_por_id(noticia_id)
    if not noticia:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Notícia com ID {noticia_id} não encontrada."
        )

    dados_atualizar = payload.model_dump(exclude_unset=True)
    if not dados_atualizar:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Nenhum campo fornecido para atualização."
        )

    try:
        repo.atualizar(noticia_id, dados_atualizar)
        return {"id": noticia_id, "mensagem": "Notícia atualizada com sucesso."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao atualizar notícia: {str(e)}"
        )


@app.delete("/api/conteudos/{noticia_id}", tags=["Notícias"])
def excluir_conteudo(noticia_id: int, db: Session = Depends(get_db)):
    """Remove uma notícia do banco de dados."""
    repo = NoticiaRepository(db)
    
    noticia = repo.buscar_por_id(noticia_id)
    if not noticia:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Notícia com ID {noticia_id} não encontrada."
        )

    try:
        repo.excluir(noticia_id)
        return {"id": noticia_id, "mensagem": "Notícia removida com sucesso."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao remover notícia: {str(e)}"
        )