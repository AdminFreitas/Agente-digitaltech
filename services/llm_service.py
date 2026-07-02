"""
llm_service.py — Fallback Chain de modelos de linguagem

Tenta cada provedor na ordem. Se a resposta vier malformada, tenta o
mesmo provedor mais uma vez antes de desistir e ir para o próximo.
Ordem: Ollama (local, ilimitado) → OpenAI → Claude → Gemini
"""

import os
import re
import unicodedata
from datetime import date
from dotenv import load_dotenv

load_dotenv()

OPENAI_KEY    = os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
GEMINI_KEY    = os.getenv("GEMINI_API_KEY")
OLLAMA_URL    = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


def _remover_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


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

Responda EXATAMENTE neste formato de texto simples — NÃO use JSON e NÃO
use blocos de código (```) envolvendo a resposta:

TITULO: título do artigo aqui, em uma linha
RESUMO: resumo de uma linha, no máximo 120 caracteres
TEMPO_LEITURA: X min
===CORPO===
o artigo completo em markdown vai aqui, pode ter várias linhas e usar ## normalmente
"""


def _montar_artigo(dados: dict, categoria: str, provedor: str) -> dict:
    slug = _gerar_slug(dados["titulo"])
    hoje = date.today().isoformat()
    return {
        "slug": slug,
        "titulo": dados["titulo"],
        "categoria": categoria,
        "excerpt": dados["excerpt"],
        "readTime": dados["readTime"],
        "conteudo_markdown": dados["corpo"].strip(),
        "data": hoje,
        "provedor": provedor,
    }


def _parsear_resposta(texto: str) -> dict:
    """
    Extrai título, resumo, tempo de leitura e corpo da resposta do modelo.

    Duas tolerâncias importantes, baseadas em respostas reais observadas:
    - Compara os rótulos (TITULO/RESUMO/TEMPO_LEITURA) SEM considerar
      acentos, porque o modelo às vezes escreve "TÍTULO" (correto em
      português) e às vezes "Titulo" — não dá pra depender de uma
      grafia exata.
    - O marcador "===CORPO===" é tratado como OPCIONAL: se não
      aparecer, tudo que vier depois da última linha de cabeçalho
      reconhecida já é considerado o corpo do artigo.
    """
    texto = texto.strip()
    texto = re.sub(r"^```[a-zA-Z]*\n?", "", texto)
    texto = re.sub(r"\n?```$", "", texto)

    linhas = texto.splitlines()
    titulo = None
    resumo = ""
    tempo_leitura = "5 min"
    indice_corpo = len(linhas)

    for i, linha_original in enumerate(linhas):
        linha = linha_original.strip()
        if not linha:
            continue
        if linha == "===CORPO===":
            indice_corpo = i + 1
            break

        linha_normalizada = _remover_acentos(linha).upper()
        if linha_normalizada.startswith("TITULO:"):
            titulo = linha.split(":", 1)[1].strip()
            continue
        if linha_normalizada.startswith("RESUMO:"):
            resumo = linha.split(":", 1)[1].strip()
            continue
        if linha_normalizada.startswith("TEMPO_LEITURA:"):
            tempo_leitura = linha.split(":", 1)[1].strip()
            continue

        # Linha que não é cabeçalho reconhecido nem o marcador —
        # o modelo já começou o corpo sem usar "===CORPO===".
        indice_corpo = i
        break

    corpo = "\n".join(linhas[indice_corpo:]).strip()

    if not titulo or not corpo:
        raise ValueError("Resposta incompleta do modelo (faltou título ou corpo)")

    return {"titulo": titulo, "excerpt": resumo, "readTime": tempo_leitura, "corpo": corpo}


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
    model = genai.GenerativeModel("gemini-2.0-flash")
    resp = model.generate_content(prompt)
    if not resp.text:
        raise RuntimeError("Resposta vazia do Gemini")
    return resp.text


def _tentar_ollama(prompt: str) -> str:
    import httpx
    resp = httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
        },
        timeout=1800,
    )
    resp.raise_for_status()
    return resp.json()["response"]


PROVEDORES = [
    ("Ollama local",       _tentar_ollama),
    ("OpenAI GPT-4o-mini", _tentar_openai),
    ("Claude Haiku",       _tentar_claude),
    ("Gemini 1.5 Flash",   _tentar_gemini),
]


def gerar_artigo(tema: str, categoria: str = "Tecnologia", tentativas_por_provedor: int = 2) -> dict:
    """
    Tenta gerar artigo com cada provedor na ordem. Sempre imprime uma
    prévia da resposta bruta no log, com sucesso ou falha.
    """
    prompt = _montar_prompt(tema, categoria)
    erros = []

    for nome, funcao in PROVEDORES:
        for tentativa in range(1, tentativas_por_provedor + 1):
            try:
                print(f"[LLM] Tentando {nome} (tentativa {tentativa}/{tentativas_por_provedor})...")
                texto = funcao(prompt)
            except Exception as e:
                print(f"[LLM] {nome} falhou: {e}")
                erros.append(f"{nome}: {e}")
                break

            preview = texto[:500].replace("\n", "\\n")
            print(f"[LLM] Resposta bruta de {nome}: {preview}")

            try:
                dados = _parsear_resposta(texto)
                print(f"[LLM] Sucesso com {nome}")
                return _montar_artigo(dados, categoria, nome)
            except ValueError as e:
                print(f"[LLM] {nome} retornou resposta malformada (tentativa {tentativa}): {e}")
                erros.append(f"{nome} (tentativa {tentativa}): resposta malformada — {e}")

    raise RuntimeError("Todos os provedores falharam:\n" + "\n".join(erros))
