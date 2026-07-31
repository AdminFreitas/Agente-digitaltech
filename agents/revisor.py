"""
revisor.py — Agente revisor

Recebe o artigo já escrito pelo editor.py e devolve uma versão
corrigida: gramática, clareza, repetições, coerência e estrutura
Markdown. Nunca muda o assunto principal nem os fatos do texto.

Não acessa nenhuma API diretamente — todo texto passa por
llm_service.gerar_texto().
"""

import re

from services.llm_service import gerar_texto


def revisar_artigo(artigo: dict) -> dict:
    """
    Recebe um dict de artigo (no formato produzido por
    editor.gerar_artigo_base/gerar_noticia_base) e devolve uma CÓPIA
    com `conteudo_markdown` revisado. Os demais campos (titulo, slug,
    excerpt etc.) não são alterados aqui — isso é trabalho do seo.py.
    Não modifica o dict recebido.
    """
    prompt = f"""Você é um revisor de texto técnico brasileiro.

Revise o artigo em Markdown abaixo. Corrija gramática, ortografia,
clareza e repetições. Ajuste a coerência entre parágrafos. Verifique
se a estrutura Markdown (##, ###, listas) está bem formada.

REGRAS IMPORTANTES:
1. NÃO mude o assunto nem os fatos do texto
2. NÃO adicione informação nova
3. NÃO resuma nem corte seções inteiras
4. Mantenha o Markdown válido
5. Responda APENAS com o texto revisado, sem comentários, sem
   explicações, sem blocos de código (```) envolvendo a resposta

TEXTO ORIGINAL:
{artigo['conteudo_markdown']}
"""
    conteudo_revisado = gerar_texto(prompt)
    conteudo_revisado = _remover_cerca_markdown(conteudo_revisado)

    artigo_revisado = dict(artigo)
    artigo_revisado["conteudo_markdown"] = conteudo_revisado
    return artigo_revisado


def _remover_cerca_markdown(texto: str) -> str:
    """Remove ```markdown / ``` que o modelo às vezes adiciona mesmo
    quando instruído a não usar blocos de código."""
    texto = re.sub(r"^```[a-zA-Z]*\n?", "", texto)
    texto = re.sub(r"\n?```$", "", texto)
    return texto.strip()
