"""
llm_service.py — Fallback Chain de modelos de linguagem (CORRIGIDO v3)

Baseado em testes reais em Aspire E1-571 + qwen2.5:3b (CPU).

Ajustes desta versão:
- Ollama: timeout 400s (era 180s, insuficiente para artigo em CPU)
- Claude: mantido claude-haiku-4-5-20251001 (modelo válido, erro era 401/chave)
- Gemini: gemini-3.6-flash (modelos 1.x, 2.x e 2.5 descontinuados)
- OpenAI: sem mudança (erro 429 = quota, não código)
"""

import os
import re
import unicodedata
import time
from datetime import date
from dotenv import load_dotenv

load_dotenv()

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


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

Escreva um artigo completo em Markdown sobre: "{tema}"
Categoria: {categoria}

REGRAS:
1. Escreva APENAS em português brasileiro
2. Tom profissional mas acessível
3. Entre 300 e 500 palavras no corpo
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
        model="claude-haiku-4-5-20251001",  # modelo válido — erro 401 era chave, não nome
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def _tentar_gemini(prompt: str) -> str:
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada")
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_KEY)
    # gemini-3.6-flash: modelo GA atual (2026), substitui 1.x/2.x/2.5 descontinuados
    model = genai.GenerativeModel("gemini-3.6-flash")
    resp = model.generate_content(prompt)
    if not resp.text:
        raise RuntimeError("Resposta vazia do Gemini")
    return resp.text


def _tentar_ollama(prompt: str) -> str:
    """
    Chama Ollama via /api/chat.

    TESTES REAIS (Aspire E1-571, qwen2.5:3b, CPU):
    - "TESTE" (1 palavra): ~26s
    - sugerir_tema (texto curto): ~155s
    - artigo completo (300-500 palavras): >180s (estourava)

    Por isso timeout=400s. Se ainda estourar, aumente para 600s.
    """
    import httpx

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "num_predict": 1200,   # ~400-500 palavras em português
            "temperature": 0.7,
            "num_ctx": 4096,
        },
        "keep_alive": "10m",
    }

    print(f"[Ollama] Enviando (timeout=400s, model={OLLAMA_MODEL})...")
    inicio = time.monotonic()

    resp = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json=payload,
        timeout=400,  # 400s — baseado em medição real (155s só pra tema)
    )
    resp.raise_for_status()

    tempo = time.monotonic() - inicio
    dados = resp.json()
    resposta = dados["message"]["content"]

    print(f"[Ollama] ✅ {tempo:.1f}s | prompt_eval={dados.get('prompt_eval_count', '?')} | eval={dados.get('eval_count', '?')}")

    return resposta


PROVEDORES = [
    ("Ollama local", _tentar_ollama),
    ("OpenAI GPT-4o-mini", _tentar_openai),
    ("Claude Haiku", _tentar_claude),
    ("Gemini 3.6 Flash", _tentar_gemini),
]


def gerar_artigo(tema: str, categoria: str = "Tecnologia", tentativas_por_provedor: int = 2) -> dict:
    prompt = _montar_prompt(tema, categoria)
    erros = []

    for nome, funcao in PROVEDORES:
        for tentativa in range(1, tentativas_por_provedor + 1):
            inicio = time.monotonic()
            try:
                print(f"[LLM] Tentando {nome} (tentativa {tentativa}/{tentativas_por_provedor})...")
                texto = funcao(prompt)
                tempo_total = time.monotonic() - inicio
                print(f"[LLM] {nome} respondeu em {tempo_total:.1f}s")
            except Exception as e:
                tempo_total = time.monotonic() - inicio
                print(f"[LLM] {nome} falhou após {tempo_total:.1f}s: {e}")
                erros.append(f"{nome}: {e}")
                break

            preview = texto[:500].replace("\n", "\\n")
            print(f"[LLM] Preview: {preview}...")

            try:
                dados = _parsear_resposta(texto)
                print(f"[LLM] ✅ Sucesso com {nome} | Título: {dados['titulo'][:60]}...")
                return _montar_artigo(dados, categoria, nome)
            except ValueError as e:
                print(f"[LLM] {nome} retornou resposta malformada: {e}")
                erros.append(f"{nome} (tentativa {tentativa}): malformada — {e}")

    raise RuntimeError("Todos os provedores falharam:\n" + "\n".join(erros))


# ---------------------------------------------------------------------------
# Primitivos reutilizáveis
# ---------------------------------------------------------------------------
parsear_resposta_padrao = _parsear_resposta
gerar_slug = _gerar_slug


def gerar_texto(prompt: str, tentativas_por_provedor: int = 2) -> str:
    erros = []
    for nome, funcao in PROVEDORES:
        for tentativa in range(1, tentativas_por_provedor + 1):
            try:
                print(f"[LLM] (gerar_texto) Tentando {nome} (tentativa {tentativa}/{tentativas_por_provedor})...")
                texto = funcao(prompt)
                if texto and texto.strip():
                    return texto.strip()
                raise RuntimeError("resposta vazia")
            except Exception as e:
                print(f"[LLM] (gerar_texto) {nome} falhou: {e}")
                erros.append(f"{nome} (tentativa {tentativa}): {e}")
                break

    raise RuntimeError("Todos os provedores falharam:\n" + "\n".join(erros))


MODELO_POR_PROVEDOR = {
    "Ollama local": OLLAMA_MODEL,
    "OpenAI GPT-4o-mini": "gpt-4o-mini",
    "Claude Haiku": "claude-haiku-4-5-20251001",
    "Gemini 3.6 Flash": "gemini-3.6-flash",
}


def gerar_texto_com_metadados(prompt: str, tentativas_por_provedor: int = 2) -> dict:
    erros = []
    for nome, funcao in PROVEDORES:
        for tentativa in range(1, tentativas_por_provedor + 1):
            try:
                print(f"[LLM] (gerar_texto_com_metadados) Tentando {nome} (tentativa {tentativa}/{tentativas_por_provedor})...")
                inicio = time.monotonic()
                texto = funcao(prompt)
                tempo_ms = int((time.monotonic() - inicio) * 1000)
                if texto and texto.strip():
                    return {
                        "texto": texto.strip(),
                        "provedor": nome,
                        "modelo": MODELO_POR_PROVEDOR.get(nome, ""),
                        "tempo_ms": tempo_ms,
                    }
                raise RuntimeError("resposta vazia")
            except Exception as e:
                print(f"[LLM] (gerar_texto_com_metadados) {nome} falhou: {e}")
                erros.append(f"{nome} (tentativa {tentativa}): {e}")
                break

    raise RuntimeError("Todos os provedores falharam:\n" + "\n".join(erros))

