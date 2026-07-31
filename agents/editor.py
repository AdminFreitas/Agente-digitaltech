from services.llm_service import gerar_artigo as gerar_artigo_llm

def gerar_artigo_base(tema: str, categoria: str) -> str:
    resultado = gerar_artigo_llm(tema, categoria)
    return resultado["conteudo_markdown"]
import requests
from config.settings import OLLAMA_URL, OLLAMA_MODEL

def gerar_artigo_base(tema: str, categoria: str) -> str:
    prompt = f"""
Você é um redator técnico do portal DigitalTech.

Escreva um artigo completo sobre: {tema}

Categoria: {categoria}

Regras:
- Português do Brasil
- Estrutura com títulos H2 e H3
- Tom técnico e claro
- Sem enrolação
"""

    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        }
    )

    response.raise_for_status()
    return response.json()["response"]