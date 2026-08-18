"""
API FastAPI do Agente Digital Tech
Serve o static/index.html e expõe endpoints consumidos pelo painel.
"""
import os
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models import init_db, get_db, Conteudo
from repositories.artigo_repository import ArtigoRepository

# Inicializa banco SQLite na primeira execução
init_db()

app = FastAPI(
    title="Agente Digital Tech API",
    version="1.0.0",
    description="Backend do painel administrativo do agente de conteúdo"
)

# CORS liberado para desenvolvimento (ajuste origins em produção)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve o index.html e assets estáticos
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ------------------------------------------------------------------
# Schemas Pydantic (espelham o state.items do index.html)
# ------------------------------------------------------------------
class ConteudoBase(BaseModel):
    tipo: str = Field(..., pattern="^(artigo|noticia)$")
    titulo: str
    slug: Optional[str] = None
    resumo: Optional[str] = ""
    conteudo: Optional[str] = ""
    categoria: Optional[str] = ""
    tags: Optional[list] = []
    autor: Optional[str] = "Agente IA"
    imagem_url: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None

class ConteudoCreate(ConteudoBase):
    status: str = "rascunho"

class ConteudoUpdate(BaseModel):
    titulo: Optional[str] = None
    resumo: Optional[str] = None
    conteudo: Optional[str] = None
    status: Optional[str] = None
    categoria: Optional[str] = None
    tags: Optional[list] = None
    imagem_url: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    slug: Optional[str] = None

class ConteudoOut(ConteudoBase):
    id: int
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class DashboardStats(BaseModel):
    artigos: int
    noticias: int
    revisao: int
    publicados: int

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def slugify(texto: str) -> str:
    import unicodedata, re
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^\w\s-]", "", texto).strip().lower()
    return re.sub(r"[\s_-]+", "-", texto)

# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.get("/")
def root():
    """Serve o painel administrativo."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        from fastapi.responses import FileResponse
        return FileResponse(index_path)
    return {"message": "Agente Digital Tech API — coloque o index.html em /static/"}

# ---------- Conteúdos (Artigos + Notícias) ----------

@app.get("/api/conteudos", response_model=list[ConteudoOut])
def listar_conteudos(
    tipo: Optional[str] = Query(None, regex="^(artigo|noticia)$"),
    status: Optional[str] = Query(None),
    categoria: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: Optional[str] = Query("recent"),
    db: Session = Depends(get_db)
):
    """Lista conteúdos com filtros — usado por renderLibrary / filterLibrary."""
    repo = ArtigoRepository(db)
    return repo.listar(
        tipo=tipo,
        status=status,
        categoria=categoria,
        tag=tag,
        search=search,
        sort=sort
    )

@app.get("/api/conteudos/{id}", response_model=ConteudoOut)
def obter_conteudo(id: int, db: Session = Depends(get_db)):
    """Detalhe de um item — usado na edição."""
    repo = ArtigoRepository(db)
    item = repo.buscar_por_id(id)
    if not item:
        raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
    return item

@app.post("/api/conteudos", response_model=ConteudoOut, status_code=201)
def criar_conteudo(payload: ConteudoCreate, db: Session = Depends(get_db)):
    """Cria artigo ou notícia manualmente."""
    repo = ArtigoRepository(db)
    dados = payload.model_dump()
    if not dados.get("slug"):
        dados["slug"] = slugify(dados["titulo"])
    # Evita slug duplicado
    if repo.buscar_por_slug(dados["slug"]):
        dados["slug"] += f"-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return repo.criar(dados)

@app.patch("/api/conteudos/{id}", response_model=ConteudoOut)
def editar_conteudo(id: int, payload: ConteudoUpdate, db: Session = Depends(get_db)):
    """Edita campos — usado pelo botão Salvar do formulário."""
    repo = ArtigoRepository(db)
    dados = {k: v for k, v in payload.model_dump().items() if v is not None}
    item = repo.atualizar(id, dados)
    if not item:
        raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
    return item

@app.delete("/api/conteudos/{id}")
def excluir_conteudo(id: int, db: Session = Depends(get_db)):
    """Exclui item — usado pelo botão Excluir da tabela."""
    repo = ArtigoRepository(db)
    if not repo.excluir(id):
        raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
    return {"ok": True, "message": "Conteúdo excluído"}

# ---------- Geração via Agente ----------

@app.post("/api/artigos/gerar", response_model=ConteudoOut)
def gerar_artigo(
    tema: str,
    categoria: Optional[str] = "Tecnologia",
    publicar_imediatamente: bool = False,
    db: Session = Depends(get_db)
):
    """
    Gera artigo com IA e persiste no banco.
    TODO: integre aqui sua função real gerar_e_processar_artigo()
    """
    repo = ArtigoRepository(db)
    # ---- MOCK temporário (substitua pela chamada real ao seu agente) ----
    import random
    item = repo.criar({
        "tipo": "artigo",
        "titulo": f"{tema.title()}: Guia Completo",
        "slug": slugify(tema),
        "resumo": f"Um artigo aprofundado sobre {tema} gerado automaticamente pelo agente.",
        "conteudo": f"# {tema.title()}\n\nConteúdo gerado pela IA...",
        "categoria": categoria,
        "tags": [tema.lower(), "ia", "automação"],
        "status": "publicado" if publicar_imediatamente else "revisao",
        "imagem_url": None,
        "seo_title": f"{tema.title()} | DigitalTech",
        "seo_description": f"Descubra tudo sobre {tema} em nosso guia completo.",
    })
    return item

@app.post("/api/noticias/gerar", response_model=ConteudoOut)
def gerar_noticia(
    tema: Optional[str] = None,
    publicar_imediatamente: bool = False,
    db: Session = Depends(get_db)
):
    """
    Gera notícia com IA e persiste no banco.
    TODO: integre aqui sua função real gerar_noticia_base()
    """
    repo = ArtigoRepository(db)
    tema = tema or "Novidades do Ecossistema de IA"
    item = repo.criar({
        "tipo": "noticia",
        "titulo": f"{tema} — {datetime.now().strftime('%d/%m')}",
        "slug": slugify(tema),
        "resumo": f"Resumo da notícia sobre {tema}.",
        "conteudo": f"## {tema}\n\nNotícia gerada automaticamente...",
        "categoria": "Notícias",
        "tags": ["notícia", "ia", "tech"],
        "status": "publicado" if publicar_imediatamente else "revisao",
    })
    return item

# ---------- Publicação ----------

@app.post("/api/conteudos/{id}/publicar")
def publicar_conteudo(id: int, db: Session = Depends(get_db)):
    """Muda status para publicado e dispara pipeline de publicação (GitHub, etc)."""
    repo = ArtigoRepository(db)
    item = repo.atualizar(id, {"status": "publicado"})
    if not item:
        raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
    # TODO: insira aqui sua lógica real de publicação no GitHub/WordPress
    return {"ok": True, "message": "Publicado", "item": ConteudoOut.model_validate(item)}

# ---------- Dashboard / Health ----------

@app.get("/api/dashboard", response_model=DashboardStats)
def dashboard(db: Session = Depends(get_db)):
    """Retorna contadores para os cards do Dashboard."""
    repo = ArtigoRepository(db)
    return {
        "artigos": repo.contar_por_tipo("artigo"),
        "noticias": repo.contar_por_tipo("noticia"),
        "revisao": repo.contar_por_status("revisao"),
        "publicados": repo.contar_por_status("publicado"),
    }

@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    """Verifica saúde dos serviços — usado pelo módulo Operacional."""
    try:
        db.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "agente": "online",
        "api": "ok",
        "banco": "ok" if db_ok else "erro",
        "ia": "disponível",   # TODO: verifique sua LLM
        "github": "ok",       # TODO: verifique conectividade
    }

# ---------- Categorias & Tags ----------

@app.get("/api/categorias")
def listar_categorias(db: Session = Depends(get_db)):
    """Retorna categorias distintas para os filtros do painel."""
    from sqlalchemy import distinct
    cats = db.query(distinct(Conteudo.categoria)).filter(Conteudo.categoria != None).all()
    return [c[0] for c in cats if c[0]]

# ------------------------------------------------------------------
# Execução local
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)