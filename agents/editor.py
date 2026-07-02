from services.llm_service import gerar_artigo as gerar_artigo_llm

def gerar_artigo_base(tema: str, categoria: str) -> str:
    resultado = gerar_artigo_llm(tema, categoria)
    return resultado["conteudo_markdown"]
