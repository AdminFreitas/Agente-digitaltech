from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health():
    return {"status": "ok", "ollama": True, "database": True, "github": True}

@app.post("/api/artigos/gerar")
async def gerar_artigo():
    return {"id": 1, "titulo": "Teste", "status": "rascunho"}

app.mount("/", StaticFiles(directory="static", html=True), name="static")
