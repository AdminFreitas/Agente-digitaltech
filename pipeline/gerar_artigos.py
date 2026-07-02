import os
from datetime import datetime
from agents.editor import gerar_artigo_base
from config.settings import OUTPUT_ARTIGOS

def salvar_artigo(titulo: str, conteudo: str, categoria: str):
    slug = titulo.lower().replace(" ", "-")

    os.makedirs(OUTPUT_ARTIGOS, exist_ok=True)
    caminho = os.path.join(OUTPUT_ARTIGOS, f"{slug}.md")

    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)

    return caminho

def gerar_artigo(tema: str, categoria: str):
    conteudo = gerar_artigo_base(tema, categoria)
    caminho = salvar_artigo(tema, conteudo, categoria)
    print(f"Artigo gerado em: {caminho}")
