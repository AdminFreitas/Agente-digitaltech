"""
llm_service.py — Fallback Chain de modelos de linguagem

Tenta cada provedor na ordem. Se falhar, vai para o próximo.
Ordem: OpenAI → Claude → Gemini → Ollama (local, ilimitado)
"""

import os
import re
import json
import unicodedata
from datetime import date
from dotenv import load_dotenv

load_dotenv()

OPENAI_KEY    = os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
GEMINI_KEY    = os.getenv("GEMINI_API_KEY")
OLLAMA_URL    = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


def _gerar_slug(titulo: str) -> str:
    slug = titulo.lower()
    slug = unicodedata.normalize("NFD", slug)
    slug = slug.encode("ascii", "ignore").decode("utf-8")
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return re.sub(r"-+", "-", slug)[:80]


def _montar_prompt(tema: str, categoria: str) -> str:
    return f"""Você é um escritor técnico brasileiro especializado em tecnologia.

Escreva um artigo completo em Markdown sobre o tema: "{tema}"
Categoria: {categoria}

REGRAS:
1. Escreva APENAS em português brasileiro
2. Tom profissional mas acessível
3. Entre 500 e 800 palavras no corpo
4. Use exemplos de código quando relevante
5. Use ## para seções e ### para subseções
6. Termine com conclusão prática

FORMATO — responda APENAS com este JSON:
{{
  "titulo": "Título do artigo",
  "excerpt": "Resumo de uma linha (máx 120 caracteres)",
  "readTime": "X min",
  "corpo": "## Primeira seção\\n\\nConteúdo..."
}}"""


def _montar_artigo(dados: dict, categoria: str, provedor: str) -> dict:
    slug = _gerar_slug(dados["titulo"])
    hoje = date.today().isoformat()
    conteudo = f"""---
slug: {slug}
title: "{dados['titulo']}"
category: {categoria}
excerpt: "{dados['excerpt']}"
date: {hoje}
readTime: {dados['readTime']}
published: true
---

{dados['corpo']}
"""
    return {
        "slug": slug,
        "titulo": dados["titulo"],
        "categoria": categoria,
        "excerpt": dados["excerpt"],
        "readTime": dados["readTime"],
        "conteudo_markdown": conteudo,
        "data": hoje,
        "provedor": provedor,
    }


def _parsear_resposta(texto: str) -> dict:
    texto = texto.strip()
    texto = re.sub(r"^```json\n?", "", texto)
    texto = re.sub(r"\n?```$", "", texto)
    dados = json.loads(texto)
    if not dados.get("titulo") or not dados.get("corpo"):
        raise ValueError("Resposta incompleta do modelo")
    return dados


def _tentar_openai(prompt: str) -> str:
    if not OPENAI_KEY:
        raise RuntimeError("OPENAI_API_KEY não configurada")
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_KEY)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        timeout=60,
    )
    return resp.choices[0].message.content


def _tentar_claude(prompt: str) -> str:
    if not ANTHROPIC_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada")
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def _tentar_gemini(prompt: str) -> str:
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada")
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
    resp = model.generate_content(prompt)
    if not resp.text:
        raise RuntimeError("Resposta vazia do Gemini")
    return resp.text


def _tentar_ollama(prompt: str) -> str:
    import httpx
    resp = httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["response"]


PROVEDORES = [
    ("OpenAI GPT-4o-mini", _tentar_openai),
    ("Claude Haiku",       _tentar_claude),
    ("Gemini 1.5 Flash",   _tentar_gemini),
    ("Ollama local",       _tentar_ollama),
]


def gerar_artigo(tema: str, categoria: str = "Tecnologia") -> dict:
    """
    Tenta gerar artigo com cada provedor na ordem.
    Retorna o resultado do primeiro que funcionar.
    Lança RuntimeError se todos falharem.
    """
    prompt = _montar_prompt(tema, categoria)
    erros = []

    for nome, funcao in PROVEDORES:
        try:
            print(f"[LLM] Tentando {nome}...")
            texto = funcao(prompt)
            dados = _parsear_resposta(texto)
            print(f"[LLM] Sucesso com {nome}")
            return _montar_artigo(dados, categoria, nome)
        except Exception as e:
            print(f"[LLM] {nome} falhou: {e}")
            erros.append(f"{nome}: {e}")

    raise RuntimeError("Todos os provedores falharam:\n" + "\n".join(erros))
