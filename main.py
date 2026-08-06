"""
main.py — DigitalTech Agente Editorial
========================================

Configuração completa do FastAPI com:
- CORS para o dashboard
- Endpoints da API com prefixo /api
- Serviço de arquivos estáticos (dashboard)
- Integração com o pipeline de agentes existente

ADAPTE as importações conforme a estrutura real do seu projeto.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uvicorn

# ============================================================
# IMPORTS DO SEU PROJETO (ajuste os caminhos conforme necessário)
# ============================================================
# Descomente e ajuste conforme a estrutura real do seu projeto:
#
# from src.agents.artigo_agent import ArtigoAgent
# from src.agents.noticia_agent import NoticiaAgent
# from src.core.github_publisher import GitHubPublisher
# from src.core.database import Database
# from src.config.settings import Settings
#
# agente_artigo = ArtigoAgent()
# agente_noticia = NoticiaAgent()
# github = GitHubPublisher()
# db = Database()
# settings = Settings()


# ============================================================
# APP FASTAPI
# ============================================================
app = FastAPI(
    title="DigitalTech API",
    description="Agente editorial automatizado com painel web",
    version="1.0.0",
    docs_url="/api/docs",      # Swagger UI em /api/docs
    redoc_url="/api/redoc",    # ReDoc em /api/redoc
    openapi_url="/api/openapi.json"
)


# ============================================================
# CORS — PERMITE QUE O DASHBOARD ACESSE A API
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # Produção: ["https://seu-dominio.com"]
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PUT", "PATCH"],
    allow_headers=["*"],
)


# ============================================================
# MODELOS PYDANTIC (REQUESTS / RESPONSES)
# ============================================================

class GerarArtigoRequest(BaseModel):
    tema: str = Field(..., min_length=3, description="Tema principal do artigo")
    categoria: str = Field(default="tecnologia", description="Categoria do artigo")
    tom: str = Field(default="divulgativo", description="Tom de escrita: tecnico, divulgativo, tutorial, opiniao")
    tamanho: str = Field(default="medio", description="Tamanho: curto, medio, longo")
    publicar: bool = Field(default=True, description="Publicar imediatamente no GitHub")
    modelo: str = Field(default="llama3.1:70b", description="Modelo de IA a ser usado")


class GerarNoticiaRequest(BaseModel):
    tema: str = Field(..., min_length=3, description="Tema ou fonte da notícia")
    categoria: str = Field(default="tecnologia", description="Categoria da notícia")
    publicar: bool = Field(default=True, description="Publicar imediatamente no GitHub")
    modelo: str = Field(default="llama3.1:70b", description="Modelo de IA a ser usado")


class ArtigoResponse(BaseModel):
    id: int
    titulo: str
    categoria: str
    status: str  # "rascunho" | "publicado" | "falhou"
    data_criacao: str
    url_github: Optional[str] = None
    modelo_usado: str


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    ollama: bool
    database: bool
    github: bool
    modelo_ativo: str
    artigos_gerados_hoje: int = 0


class PublicarResponse(BaseModel):
    id: int
    status: str
    url_github: Optional[str] = None
    mensagem: str


class ExcluirResponse(BaseModel):
    id: int
    mensagem: str


# ============================================================
# BANCO DE DADOS EM MEMÓRIA (substitua pelo seu DB real)
# ============================================================
# Em produção, use SQLite/PostgreSQL via SQLAlchemy ou similar.
# Aqui é apenas um exemplo para o dashboard funcionar imediatamente.

ARTIGOS_DB = [
    {
        "id": 25,
        "titulo": "Green Light IA: O futuro da automação editorial",
        "categoria": "Inteligência Artificial",
        "status": "rascunho",
        "data_criacao": "2026-08-05",
        "url_github": None,
        "modelo_usado": "llama3.1:70b"
    },
    {
        "id": 24,
        "titulo": "APIs REST: Boas práticas em 2026",
        "categoria": "Programação",
        "status": "publicado",
        "data_criacao": "2026-08-04",
        "url_github": "https://github.com/seu-usuario/digitaltech/artigos/24",
        "modelo_usado": "llama3.1:70b"
    },
    {
        "id": 23,
        "titulo": "PostgreSQL vs MySQL: Qual escolher?",
        "categoria": "Banco de Dados",
        "status": "publicado",
        "data_criacao": "2026-08-03",
        "url_github": "https://github.com/seu-usuario/digitaltech/artigos/23",
        "modelo_usado": "mistral-large"
    }
]

_next_id = 26


def _get_next_id() -> int:
    global _next_id
    _next_id += 1
    return _next_id - 1


def _check_ollama() -> bool:
    """Verifica se Ollama está respondendo."""
    # Substitua pela verificação real:
    # import requests
    # try:
    #     r = requests.get("http://localhost:11434/api/tags", timeout=2)
    #     return r.status_code == 200
    # except:
    #     return False
    return True


def _check_database() -> bool:
    """Verifica se o banco de dados está conectado."""
    # Substitua pela verificação real do seu DB
    return True


def _check_github() -> bool:
    """Verifica se a API do GitHub está autenticada."""
    # Substitua pela verificação real:
    # from github import Github
    # try:
    #     g = Github(settings.GITHUB_TOKEN)
    #     g.get_user().login
    #     return True
    # except:
    #     return False
    return True


# ============================================================
# ROTAS DA API (todas com prefixo /api)
# ============================================================

@app.get("/api/health", response_model=HealthResponse, tags=["Status"])
async def health_check():
    """
    Retorna o status de saúde completo do sistema.

    Usado pelo dashboard para mostrar:
    - API Online/Offline
    - Ollama Online/Offline
    - Banco de Dados Online/Offline
    - GitHub Conectado/Desconectado
    """
    hoje = datetime.now().strftime("%Y-%m-%d")
    artigos_hoje = len([a for a in ARTIGOS_DB if a["data_criacao"] == hoje])

    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "ollama": _check_ollama(),
        "database": _check_database(),
        "github": _check_github(),
        "modelo_ativo": "llama3.1:70b",
        "artigos_gerados_hoje": artigos_hoje
    }


@app.post("/api/artigos/gerar", response_model=ArtigoResponse, tags=["Artigos"])
async def gerar_artigo(request: GerarArtigoRequest, background_tasks: BackgroundTasks):
    """
    Gera um novo artigo usando o agente editorial.

    - **tema**: Assunto principal do artigo
    - **categoria**: Área de conhecimento
    - **tom**: Estilo de escrita (tecnico, divulgativo, tutorial, opiniao)
    - **tamanho**: Extensão do texto (curto, medio, longo)
    - **publicar**: Se True, publica no GitHub automaticamente
    - **modelo**: Qual LLM usar (llama3.1:70b, mistral-large, qwen2.5:72b)

    Retorna o artigo criado com ID, status e URL do GitHub (se publicado).
    """
    artigo_id = _get_next_id()

    # ============================================================
    # AQUI VOCÊ INTEGRA COM SEU PIPELINE REAL:
    # ============================================================
    #
    # 1. Chama o agente para gerar conteúdo
    # conteudo = await agente_artigo.gerar(
    #     tema=request.tema,
    #     categoria=request.categoria,
    #     tom=request.tom,
    #     tamanho=request.tamanho,
    #     modelo=request.modelo
    # )
    #
    # 2. Salva no banco de dados
    # db.save_artigo(artigo_id, conteudo, request.categoria, request.modelo)
    #
    # 3. Se publicar=True, envia para o GitHub
    # url_github = None
    # if request.publicar:
    #     url_github = await github.publicar_artigo(artigo_id, conteudo)
    #     status = "publicado"
    # else:
    #     status = "rascunho"
    #
    # 4. Retorna a resposta
    # ============================================================

    # Simulação (remova quando integrar seu pipeline):
    url_github = None
    status = "rascunho"

    if request.publicar:
        # Simula publicação no GitHub
        url_github = f"https://github.com/seu-usuario/digitaltech/artigos/{artigo_id}"
        status = "publicado"

    artigo = {
        "id": artigo_id,
        "titulo": request.tema,
        "categoria": request.categoria.replace("-", " ").title(),
        "status": status,
        "data_criacao": datetime.now().strftime("%Y-%m-%d"),
        "url_github": url_github,
        "modelo_usado": request.modelo
    }

    ARTIGOS_DB.insert(0, artigo)

    return artigo


@app.post("/api/noticias/gerar", response_model=ArtigoResponse, tags=["Notícias"])
async def gerar_noticia(request: GerarNoticiaRequest):
    """
    Gera uma notícia com base em fontes atuais da web.

    - **tema**: Assunto da notícia ou fonte
    - **categoria**: Área da notícia
    - **publicar**: Se True, publica no GitHub automaticamente
    - **modelo**: Qual LLM usar

    O agente busca notícias recentes, sintetiza e gera um artigo.
    """
    artigo_id = _get_next_id()

    # ============================================================
    # INTEGRAÇÃO REAL:
    # ============================================================
    # noticia = await agente_noticia.gerar(
    #     tema=request.tema,
    #     categoria=request.categoria,
    #     modelo=request.modelo
    # )
    # 
    # db.save_noticia(artigo_id, noticia, request.categoria, request.modelo)
    #
    # if request.publicar:
    #     url = await github.publicar_noticia(artigo_id, noticia)
    #     status = "publicado"
    # else:
    #     status = "rascunho"
    # ============================================================

    url_github = None
    status = "rascunho"

    if request.publicar:
        url_github = f"https://github.com/seu-usuario/digitaltech/noticias/{artigo_id}"
        status = "publicado"

    artigo = {
        "id": artigo_id,
        "titulo": request.tema,
        "categoria": request.categoria.replace("-", " ").title(),
        "status": status,
        "data_criacao": datetime.now().strftime("%Y-%m-%d"),
        "url_github": url_github,
        "modelo_usado": request.modelo
    }

    ARTIGOS_DB.insert(0, artigo)

    return artigo


@app.get("/api/artigos", response_model=List[ArtigoResponse], tags=["Artigos"])
async def listar_artigos(
    status: Optional[str] = None,
    categoria: Optional[str] = None,
    limite: int = 50
):
    """
    Lista todos os artigos e notícias gerados.

    Filtros opcionais:
    - **status**: "rascunho", "publicado" ou "falhou"
    - **categoria**: filtra por categoria
    - **limite**: quantidade máxima de resultados
    """
    resultado = ARTIGOS_DB.copy()

    if status:
        resultado = [a for a in resultado if a["status"] == status]

    if categoria:
        resultado = [a for a in resultado if categoria.lower() in a["categoria"].lower()]

    return resultado[:limite]


@app.get("/api/artigos/{artigo_id}", response_model=ArtigoResponse, tags=["Artigos"])
async def obter_artigo(artigo_id: int):
    """Retorna os detalhes de um artigo específico pelo ID."""
    for artigo in ARTIGOS_DB:
        if artigo["id"] == artigo_id:
            return artigo

    raise HTTPException(status_code=404, detail=f"Artigo #{artigo_id} não encontrado")


@app.post("/api/artigos/publicar/{artigo_id}", response_model=PublicarResponse, tags=["Artigos"])
async def publicar_artigo(artigo_id: int):
    """
    Publica um artigo rascunho no GitHub.

    O artigo deve existir e estar com status "rascunho".
    Após publicação, o status muda para "publicado" e a URL do GitHub é retornada.
    """
    for artigo in ARTIGOS_DB:
        if artigo["id"] == artigo_id:
            if artigo["status"] == "publicado":
                return {
                    "id": artigo_id,
                    "status": "publicado",
                    "url_github": artigo["url_github"],
                    "mensagem": "Artigo já estava publicado"
                }

            # ============================================================
            # INTEGRAÇÃO REAL:
            # ============================================================
            # conteudo = db.get_artigo(artigo_id)
            # url = await github.publicar_artigo(artigo_id, conteudo)
            # db.update_status(artigo_id, "publicado", url)
            # ============================================================

            artigo["status"] = "publicado"
            artigo["url_github"] = f"https://github.com/seu-usuario/digitaltech/artigos/{artigo_id}"

            return {
                "id": artigo_id,
                "status": "publicado",
                "url_github": artigo["url_github"],
                "mensagem": "Artigo publicado com sucesso no GitHub"
            }

    raise HTTPException(status_code=404, detail=f"Artigo #{artigo_id} não encontrado")


@app.delete("/api/artigos/{artigo_id}", response_model=ExcluirResponse, tags=["Artigos"])
async def excluir_artigo(artigo_id: int):
    """Remove um artigo do banco de dados."""
    global ARTIGOS_DB

    for i, artigo in enumerate(ARTIGOS_DB):
        if artigo["id"] == artigo_id:
            # ============================================================
            # INTEGRAÇÃO REAL:
            # ============================================================
            # db.delete_artigo(artigo_id)
            # if artigo["url_github"]:
            #     await github.remover_artigo(artigo_id)
            # ============================================================

            ARTIGOS_DB.pop(i)
            return {
                "id": artigo_id,
                "mensagem": "Artigo excluído com sucesso"
            }

    raise HTTPException(status_code=404, detail=f"Artigo #{artigo_id} não encontrado")


@app.get("/api/estatisticas", tags=["Status"])
async def estatisticas():
    """Retorna estatísticas gerais do agente."""
    total = len(ARTIGOS_DB)
    publicados = len([a for a in ARTIGOS_DB if a["status"] == "publicado"])
    rascunhos = len([a for a in ARTIGOS_DB if a["status"] == "rascunho"])

    return {
        "total_artigos": total,
        "publicados": publicados,
        "rascunhos": rascunhos,
        "taxa_publicacao": round(publicados / total * 100, 1) if total > 0 else 0,
        "modelos_usados": list(set(a["modelo_usado"] for a in ARTIGOS_DB))
    }


# ============================================================
# SERVIR ARQUIVOS ESTÁTICOS (DASHBOARD)
# ============================================================
#
# ⚠️  IMPORTANTE: O StaticFiles deve ser a ÚLTIMA coisa registrada.
# Ele captura QUALQUER requisição que não corresponda a uma rota
# da API e tenta servir um arquivo da pasta static/.
#
# Isso significa que:
#   GET /api/health        → vai para a rota health_check
#   GET /api/artigos       → vai para a rota listar_artigos
#   GET /                  → vai para static/index.html (dashboard)
#   GET /css/style.css     → vai para static/css/style.css
# ============================================================

app.mount("/", StaticFiles(directory="static", html=True), name="static")


# ============================================================
# RODAR O SERVIDOR
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 DigitalTech Agente Editorial")
    print("=" * 60)
    print("📊 Dashboard: http://localhost:8000/")
    print("📚 API Docs:   http://localhost:8000/api/docs")
    print("📖 ReDoc:      http://localhost:8000/api/redoc")
    print("=" * 60)

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
