import logging
import os
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field
from config.database import get_db, SessionLocal
from repositories.produto_repository import ProdutoRepository
from repositories.artigo_repository import ArtigoRepository
from repositories.noticia_repository import NoticiaRepository
from agents import publisher
import re
import unicodedata
from pipeline.gerar_artigos import gerar_e_processar_artigo
from pipeline.gerar_noticias import gerar_e_processar_noticia

logger = logging.getLogger("digitaltech")
logging.basicConfig(level=logging.INFO)


def slugify(value: str) -> str:
    """Gera um slug a partir de um título. Mesma lógica do slugify() do front-end."""
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"\s+", "-", value).strip("-")
    return value[:70]

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
        description="Se True, já publica no GitHub e marca como 'publicado'. Se False, entra como 'rascunho'."
    )

class GerarNoticiaInput(BaseModel):
    categoria: str = Field(default="Tecnologia", description="Categoria da notícia no blog")
    publicar_imediatamente: bool = Field(
        default=False,
        description="Se True, já publica no GitHub e marca como 'publicado'. Se False, entra como 'rascunho'."
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
    """
    Roda a cadeia completa (pesquisador → editor → revisor → imagem →
    seo → publisher) e salva no Neon como 'rascunho'. Se
    publicar_imediatamente=True, também publica no GitHub em seguida.
    """
    try:
        resultado = gerar_e_processar_artigo(
            tema=dados.tema,
            categoria=dados.categoria,
            publicar_imediatamente=dados.publicar_imediatamente,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Falha ao gerar artigo")
        raise HTTPException(status_code=502, detail="Erro ao gerar artigo.") from exc

    resultado["mensagem"] = "Artigo gerado e salvo no banco Neon com sucesso."
    return resultado

@app.post("/artigos/publicar/{artigo_id}", tags=["Agente de Artigos"])
def publicar_artigo_existente(artigo_id: int, db: Session = Depends(get_db)):
    """Publica no GitHub e muda o status de um artigo salvo como 'rascunho' para 'publicado'."""
    repo = ArtigoRepository(db)
    artigo = repo.buscar_por_id(artigo_id)
    if not artigo:
        raise HTTPException(status_code=404, detail="Artigo não encontrado")
    if artigo.status == "publicado":
        raise HTTPException(status_code=409, detail="Artigo já está publicado")

    try:
        resultado = publisher.publicar(db, artigo_id)
    except Exception as exc:
        logger.exception("Falha ao publicar no GitHub")
        raise HTTPException(status_code=502, detail="Erro ao publicar no GitHub.") from exc

    resultado["mensagem"] = "Artigo publicado com sucesso."
    return resultado

@app.post("/noticias/gerar", status_code=201, tags=["Agente de Notícias"])
def gerar_e_salvar_noticia(dados: GerarNoticiaInput):
    """
    Busca notícias recentes via RSS e roda a cadeia completa
    (editor → revisor → imagem → seo → publisher) para a primeira
    notícia ainda não publicada. Publicar depois usa o mesmo
    /artigos/publicar/{id} — notícias ficam na mesma tabela `artigos`.
    """
    try:
        resultado = gerar_e_processar_noticia(
            categoria=dados.categoria,
            publicar_imediatamente=dados.publicar_imediatamente,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Falha ao gerar notícia")
        raise HTTPException(status_code=502, detail="Erro ao gerar notícia.") from exc

    resultado["mensagem"] = "Notícia gerada e salva no banco Neon com sucesso."
    return resultado

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


# =====================================================================
# API do painel administrativo — usa a mesma base PostgreSQL do agente
# =====================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PANEL_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

class PainelConteudoCreate(BaseModel):
    tipo: str = Field(default="artigo", pattern="^(artigo|noticia)$")
    titulo: str = Field(..., min_length=1, max_length=300)
    slug: str | None = None
    resumo: str = ""
    conteudo: str = ""
    categoria: str = "Tecnologia"
    tags: list[str] = []
    status: str = "rascunho"
    imagem_url: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None

class PainelConteudoUpdate(BaseModel):
    titulo: str | None = None
    slug: str | None = None
    resumo: str | None = None
    conteudo: str | None = None
    categoria: str | None = None
    status: str | None = None
    imagem_url: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None

class PainelGeracaoArtigo(BaseModel):
    tema: str = Field(..., min_length=3, max_length=200)
    categoria: str = "Tecnologia"
    publicar_imediatamente: bool = False

class PainelGeracaoNoticia(BaseModel):
    categoria: str = "Tecnologia"
    publicar_imediatamente: bool = False


def _painel_status(status: str | None) -> str:
    # O painel chama "revisao" ao estado editorial que o schema chama "rascunho".
    return "revisao" if status == "rascunho" else (status or "rascunho")


def _parse_ref(id: str) -> tuple[str, int]:
    """
    Converte um id do painel ("artigo:5" / "noticia:5") na tupla (tipo, id_numerico).
    Um id puramente numérico (sem prefixo) é tratado como artigo, por
    compatibilidade com links/bookmarks antigos gerados antes desta correção.
    """
    if ":" in str(id):
        tipo, raw = str(id).split(":", 1)
        if tipo in ("artigo", "noticia") and raw.isdigit():
            return tipo, int(raw)
        raise HTTPException(status_code=400, detail="ID de conteúdo inválido")
    if str(id).isdigit():
        return "artigo", int(id)
    raise HTTPException(status_code=400, detail="ID de conteúdo inválido")


def _painel_row(row, tipo: str) -> dict:
    """
    Formata uma linha (de artigos ou de noticias) no formato que o front-end
    espera. Usa .get() em tudo porque as duas tabelas não têm exatamente as
    mesmas colunas disponíveis (ex.: listagem de notícias não traz resumo/
    conteudo/imagem — só o detalhe via buscar_por_id traz).
    """
    data = dict(row._mapping if hasattr(row, "_mapping") else row)
    return {
        "id": f"{tipo}:{data.get('id')}",
        "tipo": tipo,
        "titulo": data.get("titulo") or "",
        "slug": data.get("slug") or "",
        "resumo": data.get("resumo") or "",
        "conteudo": data.get("conteudo_md") or data.get("conteudo") or "",
        "categoria": data.get("categoria") or "Tecnologia",
        "status": _painel_status(data.get("status")),
        "tags": [],
        "autor": "Agente DigitalTech",
        "imagem_url": data.get("imagem_url"),
        "imagem_destaque": data.get("imagem_url"),
        "seo_title": data.get("meta_title"),
        "seo_description": data.get("meta_description"),
        "created_at": data.get("criado_em") or data.get("data_publicacao"),
        "updated_at": data.get("atualizado_em"),
    }


def _painel_query_artigos(db: Session, artigo_id: int | None = None, limite: int = 100):
    sql = """
        SELECT a.id, a.slug, a.titulo, a.resumo, a.conteudo_md,
               a.status, a.imagem_url, a.meta_title, a.meta_description,
               a.criado_em, a.atualizado_em, c.nome AS categoria
        FROM artigos a
        LEFT JOIN categorias c ON c.id = a.categoria_id
    """
    params = {"limite": limite}
    if artigo_id is not None:
        sql += " WHERE a.id = :id"
        params["id"] = artigo_id
    sql += " ORDER BY a.criado_em DESC LIMIT :limite"
    return db.execute(text(sql), params).fetchall()


@app.get("/api/conteudos")
def painel_listar_conteudos(
    tipo: str | None = Query(None),
    status: str | None = Query(None),
    categoria: str | None = Query(None),
    tag: str | None = Query(None),
    search: str | None = Query(None),
    sort: str = Query("recent"),
    limite: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    items = [_painel_row(r, "artigo") for r in _painel_query_artigos(db, limite=limite)]
    if tipo != "artigo":
        noticia_repo = NoticiaRepository(db)
        items += [_painel_row(r, "noticia") for r in noticia_repo.listar_todos(limite=limite)]
    if tipo:
        items = [x for x in items if x["tipo"] == tipo]
    if status:
        items = [x for x in items if x["status"] == status]
    if categoria:
        items = [x for x in items if x["categoria"] == categoria]
    if tag:
        items = [x for x in items if tag.lower() in [str(t).lower() for t in x["tags"]]]
    if search:
        needle = search.lower()
        items = [x for x in items if needle in (x["titulo"] + " " + x["resumo"] + " " + x["categoria"]).lower()]
    if sort == "title":
        items.sort(key=lambda x: x["titulo"].lower())
    else:
        items.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return items[:limite]


@app.get("/api/conteudos/{id}")
def painel_obter_conteudo(id: str, db: Session = Depends(get_db)):
    tipo, ref_id = _parse_ref(id)
    if tipo == "noticia":
        row = NoticiaRepository(db).buscar_por_id(ref_id)
        if not row:
            raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
        return _painel_row(row, "noticia")
    rows = _painel_query_artigos(db, artigo_id=ref_id, limite=1)
    if not rows:
        raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
    return _painel_row(rows[0], "artigo")


@app.post("/api/conteudos", status_code=201)
def painel_criar_conteudo(payload: PainelConteudoCreate, db: Session = Depends(get_db)):
    slug = payload.slug or slugify(payload.titulo)

    if payload.tipo == "noticia":
        repo = NoticiaRepository(db)
        if repo.buscar_por_slug(slug):
            raise HTTPException(status_code=409, detail="Já existe conteúdo com este slug")
        noticia_id = repo.criar(
            slug=slug, titulo=payload.titulo, categoria=payload.categoria,
            resumo=payload.resumo, conteudo=payload.conteudo,
            status="rascunho", imagem_url=payload.imagem_url,
            meta_title=payload.meta_title, meta_description=payload.meta_description,
        )
        row = repo.buscar_por_id(noticia_id)
        return _painel_row(row, "noticia")

    repo = ArtigoRepository(db)
    categoria_id = repo.buscar_categoria_id(payload.categoria)
    if categoria_id is None:
        raise HTTPException(status_code=400, detail=f"Categoria '{payload.categoria}' não existe")
    if repo.buscar_por_slug(slug):
        raise HTTPException(status_code=409, detail="Já existe conteúdo com este slug")
    artigo_id = repo.criar(
        slug=slug, titulo=payload.titulo, categoria_id=categoria_id,
        resumo=payload.resumo, conteudo_markdown=payload.conteudo,
        status="rascunho", imagem_url=payload.imagem_url,
        meta_title=payload.meta_title, meta_description=payload.meta_description,
    )
    rows = _painel_query_artigos(db, artigo_id=artigo_id, limite=1)
    return _painel_row(rows[0], "artigo")


@app.patch("/api/conteudos/{id}")
def painel_editar_conteudo(id: str, payload: PainelConteudoUpdate, db: Session = Depends(get_db)):
    tipo, ref_id = _parse_ref(id)
    dados = payload.model_dump(exclude_unset=True)
    if "status" in dados:
        dados["status"] = "rascunho" if dados["status"] == "revisao" else dados["status"]

    if tipo == "noticia":
        repo = NoticiaRepository(db)

        if not repo.buscar_por_id(ref_id):
            raise HTTPException(
                status_code=404,
                detail="Conteúdo não encontrado"
            )

        campos_noticia = {}

        if "titulo" in dados:
            campos_noticia["titulo"] = dados["titulo"]

        if "resumo" in dados:
            campos_noticia["resumo"] = dados["resumo"]

        if "conteudo" in dados:
            campos_noticia["conteudo_md"] = dados["conteudo"]

        if "status" in dados:
            campos_noticia["status"] = dados["status"]

        if "imagem_url" in dados:
            campos_noticia["imagem_url"] = dados["imagem_url"]

        if "meta_title" in dados:
            campos_noticia["meta_title"] = dados["meta_title"]

        if "meta_description" in dados:
            campos_noticia["meta_description"] = dados["meta_description"]

        if "categoria" in dados:
            categoria_id = ArtigoRepository(db).buscar_categoria_id(
                dados["categoria"]
            )

            if categoria_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="Categoria não encontrada"
                )

            campos_noticia["categoria_id"] = categoria_id

        if campos_noticia:
            repo.atualizar(ref_id, **campos_noticia)

        row = repo.buscar_por_id(ref_id)

        return _painel_row(row, "noticia")

    rows = _painel_query_artigos(db, artigo_id=ref_id, limite=1)
    if not rows:
        raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
    if "categoria" in dados:
        categoria_id = ArtigoRepository(db).buscar_categoria_id(dados.pop("categoria"))
        if categoria_id is None:
            raise HTTPException(status_code=400, detail="Categoria não encontrada")
        dados["categoria_id"] = categoria_id
    if "conteudo" in dados:
        dados["conteudo_md"] = dados.pop("conteudo")
        import markdown as _markdown
        dados["conteudo_html"] = _markdown.markdown(dados["conteudo_md"])
    if dados:
        dados["atualizado_em"] = text("NOW()")
        assignments = []
        params = {"id": ref_id}
        for key, value in dados.items():
            if isinstance(value, type(text(""))):
                assignments.append(f"{key} = {value.text}")
            else:
                assignments.append(f"{key} = :{key}")
                params[key] = value
        db.execute(text(f"UPDATE artigos SET {', '.join(assignments)} WHERE id = :id"), params)
        db.commit()
    rows = _painel_query_artigos(db, artigo_id=ref_id, limite=1)
    return _painel_row(rows[0], "artigo")


@app.delete("/api/conteudos/{id}")
def painel_excluir_conteudo(id: str, db: Session = Depends(get_db)):
    tipo, ref_id = _parse_ref(id)
    if tipo == "noticia":
        repo = NoticiaRepository(db)
        if not repo.buscar_por_id(ref_id):
            raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
        repo.excluir(ref_id)
        return {"ok": True, "id": id}
    if not _painel_query_artigos(db, artigo_id=ref_id, limite=1):
        raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
    db.execute(text("DELETE FROM artigos WHERE id = :id"), {"id": ref_id})
    db.commit()
    return {"ok": True, "id": id}


@app.post("/api/artigos/gerar")
def painel_gerar_artigo(payload: PainelGeracaoArtigo):
    try:
        resultado = gerar_e_processar_artigo(
            tema=payload.tema,
            categoria=payload.categoria,
            publicar_imediatamente=payload.publicar_imediatamente,
        )
        resultado["tipo"] = "artigo"
        resultado["status"] = "publicado" if payload.publicar_imediatamente else "revisao"
        return resultado
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Falha ao gerar artigo pelo painel")
        raise HTTPException(status_code=502, detail="Erro ao gerar artigo") from exc


@app.post("/api/noticias/gerar")
def painel_gerar_noticia(payload: PainelGeracaoNoticia):
    try:
        resultado = gerar_e_processar_noticia(
            categoria=payload.categoria,
            publicar_imediatamente=payload.publicar_imediatamente,
        )
        resultado["tipo"] = "noticia"
        resultado["status"] = "publicado" if payload.publicar_imediatamente else "revisao"
        return resultado
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Falha ao gerar notícia pelo painel")
        raise HTTPException(status_code=502, detail="Erro ao gerar notícia") from exc


@app.post("/api/conteudos/{id}/publicar")
def painel_publicar_conteudo(id: str, db: Session = Depends(get_db)):
    tipo, ref_id = _parse_ref(id)
    try:
        if tipo == "noticia":
            repo = NoticiaRepository(db)
            if not repo.buscar_por_id(ref_id):
                raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
            # Pipeline atual: publicar() de notícia só muda o status no Neon
            # (não publica no GitHub ainda — publisher.publicar() é só p/ artigo).
            repo.publicar(ref_id)
            return {"ok": True, "id": id, "message": "Notícia marcada como publicada."}
        if not _painel_query_artigos(db, artigo_id=ref_id, limite=1):
            raise HTTPException(status_code=404, detail="Conteúdo não encontrado")
        resultado = publisher.publicar(db, ref_id)
        return {"ok": True, "id": id, "message": "Publicado", "resultado": resultado}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Falha ao publicar conteúdo pelo painel")
        raise HTTPException(status_code=502, detail="Erro ao publicar conteúdo") from exc


@app.get("/api/dashboard")
def painel_dashboard(db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT COUNT(*) FILTER (WHERE TRUE) AS total,
               COUNT(*) FILTER (WHERE status = 'rascunho') AS revisao,
               COUNT(*) FILTER (WHERE status = 'publicado') AS publicados
        FROM artigos
    """)).mappings().one()

    # NoticiaRepository não expõe contagem por status, então contamos em
    # memória sobre listar_todos(). Em volume alto isso deveria virar uma
    # query dedicada no repositório, mas para o volume de um blog é seguro.
    noticias = NoticiaRepository(db).listar_todos(limite=2000)
    noticias_revisao = sum(1 for n in noticias if _painel_status(dict(n._mapping).get("status")) == "revisao")
    noticias_publicadas = sum(1 for n in noticias if dict(n._mapping).get("status") == "publicado")

    return {
        "artigos": row["total"],
        "noticias": len(noticias),
        "revisao": row["revisao"] + noticias_revisao,
        "publicados": row["publicados"] + noticias_publicadas,
    }


@app.get("/api/categorias")
def painel_categorias(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT nome FROM categorias WHERE ativo = TRUE ORDER BY nome")).fetchall()
    return [r[0] for r in rows]


@app.get("/api/health")
def painel_health():
    if SessionLocal is None:
        return {"agente": "online", "api": "ok", "banco": "não configurado", "ia": "disponível", "github": "ok"}
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        banco = "ok"
    except Exception:
        banco = "erro"
    return {"agente": "online", "api": "ok", "banco": banco, "ia": "disponível", "github": "ok"}


if os.path.isdir(_PANEL_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_PANEL_STATIC_DIR), name="panel-static")

@app.get("/painel", include_in_schema=False)
def painel_index():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(_PANEL_STATIC_DIR, "index.html"))

@app.get("/", include_in_schema=False)
def painel_root():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(_PANEL_STATIC_DIR, "index.html"))

