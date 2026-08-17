"""
llm_service.py — Fallback Chain de modelos de linguagem (v8.1 — Ollama otimizado)

Mudancas nesta versao:
  - Ollama: num_predict 1200 -> 4000 (evita corte do artigo no meio)
  - Ollama: num_ctx 4096 -> 8192 (mais espaco para prompt + resposta)
"""

import os
import re
import unicodedata
import time
from datetime import date
from dotenv import load_dotenv

load_dotenv()

# ── Chaves ─────────────────────────────────────────────────────────────────
OPENAI_KEY      = os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY")
GEMINI_KEY      = os.getenv("GEMINI_API_KEY")
DEEPSEEK_KEY    = os.getenv("DEEPSEEK_API_KEY")
GROQ_KEY        = os.getenv("GROQ_API_KEY")
HF_KEY          = os.getenv("HUGGINGFACE_API_KEY")
GROK_KEY        = os.getenv("GROK_API_KEY")
PERPLEXITY_KEY  = os.getenv("PERPLEXITY_API_KEY")
MISTRAL_KEY     = os.getenv("MISTRAL_API_KEY")
COHERE_KEY      = os.getenv("COHERE_API_KEY")
TOGETHER_KEY    = os.getenv("TOGETHER_API_KEY")
KIMI_KEY        = os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY")
OPENROUTER_KEY  = os.getenv("OPENROUTER_API_KEY")

# ── Configuracoes Ollama ───────────────────────────────────────────────────
OLLAMA_URL    = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

# ── Modelos por provedor ───────────────────────────────────────────────────
GROQ_MODEL         = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROK_MODEL         = os.getenv("GROK_MODEL", "grok-4.1-fast")
GEMINI_MODEL       = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
HUGGINGFACE_MODEL  = os.getenv("HUGGINGFACE_MODEL", "Qwen/Qwen3-8B")
OPENAI_MODEL       = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_MODEL    = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
DEEPSEEK_MODEL     = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
PERPLEXITY_MODEL   = os.getenv("PERPLEXITY_MODEL", "sonar")
MISTRAL_MODEL      = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
COHERE_MODEL       = os.getenv("COHERE_MODEL", "command-r")
TOGETHER_MODEL     = os.getenv("TOGETHER_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo")
KIMI_MODEL         = os.getenv("KIMI_MODEL", "moonshot-v1-8k")
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")

# ── Ordem de fallback ──────────────────────────────────────────────────────
FALLBACK_ORDER = os.getenv(
    "FALLBACK_ORDER",
    "ollama,gemini,groq,openai,claude,deepseek,grok,perplexity,huggingface,mistral,cohere,together,kimi,openrouter"
)
FALLBACK_LIST = [p.strip().lower() for p in FALLBACK_ORDER.split(",") if p.strip()]


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
    return f"""Voce e um escritor tecnico brasileiro especializado em tecnologia.

Escreva um artigo completo em Markdown sobre: "{tema}"
Categoria: {categoria}

REGRAS:
1. Escreva APENAS em portugues brasileiro
2. Tom profissional mas acessivel
3. Entre 300 e 500 palavras no corpo
4. Use exemplos de codigo quando relevante
5. Use ## para secoes e ### para subsecoes
6. Termine com conclusao pratica

Responda EXATAMENTE neste formato de texto simples — NAO use JSON e NAO
use blocos de codigo (```) envolvendo a resposta:

TITULO: titulo do artigo aqui, em uma linha
RESUMO: resumo de uma linha, no maximo 120 caracteres
TEMPO_LEITURA: X min
===CORPO===
o artigo completo em markdown vai aqui, pode ter varias linhas e usar ## normalmente
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
        raise ValueError("Resposta incompleta do modelo (faltou titulo ou corpo)")

    return {"titulo": titulo, "excerpt": resumo, "readTime": tempo_leitura, "corpo": corpo}


# ────────────────────────────────────────────────────────────────────────────
# Provedores individuais
# ────────────────────────────────────────────────────────────────────────────

def _tentar_openai(prompt: str) -> str:
    if not OPENAI_KEY:
        raise RuntimeError("OPENAI_API_KEY nao configurada")
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_KEY)
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        timeout=60,
    )
    return resp.choices[0].message.content


def _tentar_claude(prompt: str) -> str:
    if not ANTHROPIC_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY nao configurada")
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def _tentar_gemini(prompt: str) -> str:
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY nao configurada")
    from google import genai
    client = genai.Client(api_key=GEMINI_KEY)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    if not resp.text:
        raise RuntimeError("Resposta vazia do Gemini")
    return resp.text


def _tentar_deepseek(prompt: str) -> str:
    if not DEEPSEEK_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY nao configurada")
    import httpx
    try:
        resp = httpx.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:200]}")


def _tentar_huggingface(prompt: str) -> str:
    if not HF_KEY:
        raise RuntimeError("HUGGINGFACE_API_KEY nao configurada")
    import httpx
    try:
        resp = httpx.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {HF_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": HUGGINGFACE_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
                "temperature": 0.7,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:200]}")


def _tentar_groq(prompt: str) -> str:
    if not GROQ_KEY:
        raise RuntimeError("GROQ_API_KEY nao configurada")
    import httpx
    try:
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2000,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:200]}")


def _tentar_grok(prompt: str) -> str:
    if not GROK_KEY:
        raise RuntimeError("GROK_API_KEY nao configurada")
    import httpx
    try:
        resp = httpx.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROK_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2000,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:200]}")


# ────────────────────────────────────────────────────────────────────────────
# OLLAMA — PATCH: num_predict 4000, num_ctx 8192
# ────────────────────────────────────────────────────────────────────────────

def _tentar_ollama(prompt: str) -> str:
    import httpx
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "num_predict": 4000,      # <-- AUMENTADO: evita corte do artigo
            "temperature": 0.7,
            "num_ctx": 8192,          # <-- AUMENTADO: mais espaco de contexto
        },
        "keep_alive": "10m",
    }
    print(f"[Ollama] Enviando (timeout=400s, model={OLLAMA_MODEL})...")
    inicio = time.monotonic()
    resp = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json=payload,
        timeout=400,
    )
    resp.raise_for_status()
    tempo = time.monotonic() - inicio
    dados = resp.json()
    resposta = dados["message"]["content"]
    print(f"[Ollama] ✅ {tempo:.1f}s | prompt_eval={dados.get('prompt_eval_count', '?')} | eval={dados.get('eval_count', '?')}")
    return resposta


def _tentar_perplexity(prompt: str) -> str:
    if not PERPLEXITY_KEY:
        raise RuntimeError("PERPLEXITY_API_KEY nao configurada")
    import httpx
    try:
        resp = httpx.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {PERPLEXITY_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": PERPLEXITY_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2000,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:200]}")


def _tentar_mistral(prompt: str) -> str:
    if not MISTRAL_KEY:
        raise RuntimeError("MISTRAL_API_KEY nao configurada")
    import httpx
    try:
        resp = httpx.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {MISTRAL_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MISTRAL_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2000,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:200]}")


def _tentar_cohere(prompt: str) -> str:
    if not COHERE_KEY:
        raise RuntimeError("COHERE_API_KEY nao configurada")
    import httpx
    try:
        resp = httpx.post(
            "https://api.cohere.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {COHERE_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": COHERE_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2000,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:200]}")


def _tentar_together(prompt: str) -> str:
    if not TOGETHER_KEY:
        raise RuntimeError("TOGETHER_API_KEY nao configurada")
    import httpx
    try:
        resp = httpx.post(
            "https://api.together.xyz/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {TOGETHER_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": TOGETHER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2000,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:200]}")


def _tentar_kimi(prompt: str) -> str:
    if not KIMI_KEY:
        raise RuntimeError("KIMI_API_KEY / MOONSHOT_API_KEY nao configurada")
    import httpx
    base_url = os.getenv("KIMI_BASE_URL") or os.getenv("MOONSHOT_BASE_URL") or "https://api.moonshot.cn/v1"
    try:
        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {KIMI_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": KIMI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2000,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:200]}")


def _tentar_openrouter(prompt: str) -> str:
    if not OPENROUTER_KEY:
        raise RuntimeError("OPENROUTER_API_KEY nao configurada")
    import httpx
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api")
    try:
        resp = httpx.post(
            f"{base_url}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", ""),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "DigitalTech Agent"),
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2000,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:200]}")


# ────────────────────────────────────────────────────────────────────────────
# Mapeamento de provedores
# ────────────────────────────────────────────────────────────────────────────
_PROVEDORES_DISPONIVEIS = {
    "ollama":       ("Ollama local", _tentar_ollama),
    "openai":       ("OpenAI GPT", _tentar_openai),
    "claude":       ("Claude Haiku", _tentar_claude),
    "gemini":       ("Gemini Flash", _tentar_gemini),
    "deepseek":     ("DeepSeek", _tentar_deepseek),
    "huggingface":  ("HuggingFace", _tentar_huggingface),
    "groq":         ("Groq", _tentar_groq),
    "grok":         ("Grok", _tentar_grok),
    "perplexity":   ("Perplexity", _tentar_perplexity),
    "mistral":      ("Mistral AI", _tentar_mistral),
    "cohere":       ("Cohere", _tentar_cohere),
    "together":     ("Together AI", _tentar_together),
    "kimi":         ("Kimi / Moonshot", _tentar_kimi),
    "openrouter":   ("OpenRouter", _tentar_openrouter),
}

MODELO_POR_PROVEDOR = {
    "Ollama local":      OLLAMA_MODEL,
    "OpenAI GPT":        OPENAI_MODEL,
    "Claude Haiku":      ANTHROPIC_MODEL,
    "Gemini Flash":      GEMINI_MODEL,
    "DeepSeek":          DEEPSEEK_MODEL,
    "HuggingFace":       HUGGINGFACE_MODEL,
    "Groq":              GROQ_MODEL,
    "Grok":              GROK_MODEL,
    "Perplexity":        PERPLEXITY_MODEL,
    "Mistral AI":        MISTRAL_MODEL,
    "Cohere":            COHERE_MODEL,
    "Together AI":       TOGETHER_MODEL,
    "Kimi / Moonshot":   KIMI_MODEL,
    "OpenRouter":        OPENROUTER_MODEL,
}


def _construir_fallback_chain() -> list:
    chain = []
    for nome in FALLBACK_LIST:
        if nome in _PROVEDORES_DISPONIVEIS:
            chain.append(_PROVEDORES_DISPONIVEIS[nome])
    if not chain:
        chain.append(_PROVEDORES_DISPONIVEIS["ollama"])
    return chain


PROVEDORES = _construir_fallback_chain()


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
                print(f"[LLM] {nome} falhou apos {tempo_total:.1f}s: {e}")
                erros.append(f"{nome}: {e}")
                break

            preview = texto[:500].replace("\n", "\\n")
            print(f"[LLM] Preview: {preview}...")

            try:
                dados = _parsear_resposta(texto)
                print(f"[LLM] ✅ Sucesso com {nome} | Titulo: {dados['titulo'][:60]}...")
                return _montar_artigo(dados, categoria, nome)
            except ValueError as e:
                print(f"[LLM] {nome} retornou resposta malformada: {e}")
                erros.append(f"{nome} (tentativa {tentativa}): malformada — {e}")

    raise RuntimeError("Todos os provedores falharam:\n" + "\n".join(erros))


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