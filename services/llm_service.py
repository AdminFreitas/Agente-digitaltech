"""
llm_service.py — Fallback Chain de modelos de linguagem

Tenta cada provedor na ordem. Se a resposta vier malformada, tenta o
mesmo provedor mais uma vez antes de desistir e ir para o próximo.
Ordem: Ollama (local, ilimitado) → OpenAI → Claude → Gemini

CORREÇÕES v2.3:
- num_predict aumentado para 1800 (antes 300, insuficiente para 500-800 palavras)
- keep_alive adicionado para manter modelo carregado entre chamadas
- Timeout ajustável via env OLLAMA_TIMEOUT (padrão 180s)
- Retry com backoff exponencial para Ollama
- Gemini: modelo atualizado para gemini-2.5-flash-lite
- Logging detalhado de payload para debug
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
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))


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


# ---------------------------------------------------------------------------
# Provedores individuais
# ---------------------------------------------------------------------------

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
        model="claude-3-haiku-20240307",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def _tentar_gemini(prompt: str) -> str:
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada")
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_KEY)   # gemini-2.5-flash foi descontinuado para novos usuários
    model = genai.GenerativeModel("gemini-3.1-flash-lite")
    resp = model.generate_content(prompt)
    if not resp.text:
        raise RuntimeError("Resposta vazia do Gemini")
    return resp.text


def _tentar_ollama(prompt: str) -> str:
    """
    Chama Ollama /api/chat com configurações otimizadas.

    CORREÇÕES:
    - num_predict: 1800 (era 300, insuficiente para artigos de 500-800 palavras)
    - keep_alive: "5m" mantém modelo carregado entre chamadas
    - Timeout configurável via OLLAMA_TIMEOUT
    """
    import httpx

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "num_predict": 1800,      # ERA 300 — insuficiente!
            "temperature": 0.7,
            "num_ctx": 4096,          # ERA 2048 — aumentado para dar mais contexto
            "top_p": 0.9,
            "keep_alive": "5m",       # NOVO: mantém modelo carregado
        },
    }

    print(f"[Ollama] Payload: model={OLLAMA_MODEL}, num_predict=1800, timeout={OLLAMA_TIMEOUT}s")

    try:
        resp = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        if "message" not in data or "content" not in data.get("message", {}):
            raise RuntimeError(f"Resposta inesperada do Ollama: {data.keys()}")

        return data["message"]["content"]

    except httpx.TimeoutException as e:
        print(f"[Ollama] TIMEOUT após {OLLAMA_TIMEOUT}s. Possíveis causas:")
        print(f"  1. Modelo não carregado na memória (primeira chamada é mais lenta)")
        print(f"  2. num_predict muito alto para a capacidade da máquina")
        print(f"  3. Ollama sobrecarregado (verifique 'ollama ps')")
        raise RuntimeError(f"Timeout Ollama ({OLLAMA_TIMEOUT}s): {e}")
    except Exception as e:
        print(f"[Ollama] Erro: {type(e).__name__}: {e}")
        raise


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------

PROVEDORES = [
    ("Ollama local", _tentar_ollama),
    ("OpenAI GPT-4o-mini", _tentar_openai),
    ("Claude Haiku", _tentar_claude),
    ("Gemini 2.5 Flash-Lite", _tentar_gemini),
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
                # NÃO dá break em timeout — tenta novamente o mesmo provedor
                if "não configurada" in str(e).lower() or "API_KEY" in str(e):
                    break
                continue

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


# ---------------------------------------------------------------------------
# Primitivos reutilizáveis por outros agentes
# ---------------------------------------------------------------------------

parsear_resposta_padrao = _parsear_resposta
gerar_slug = _gerar_slug


def gerar_texto(prompt: str, tentativas_por_provedor: int = 2) -> str:
    """
    Pede um texto livre a qualquer provedor disponível, usando a mesma
    cadeia de fallback de gerar_artigo(), mas SEM o parsing rígido de
    título/resumo/corpo — devolve a resposta bruta do modelo.
    """
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
                if "não configurada" in str(e).lower() or "API_KEY" in str(e):
                    break
                continue

    raise RuntimeError("Todos os provedores falharam:\n" + "\n".join(erros))


MODELO_POR_PROVEDOR = {
    "Ollama local": OLLAMA_MODEL,
    "OpenAI GPT-4o-mini": "gpt-4o-mini",
    "Claude Haiku": "claude-3-haiku-20240307",
    "Gemini 2.5 Flash Lite": "gemini-2.5-flash-lite",
}


def gerar_texto_com_metadados(prompt: str, tentativas_por_provedor: int = 2) -> dict:
    """
    Igual a gerar_texto(), mas além do texto devolve qual provedor/
    modelo respondeu e quanto tempo levou (em ms).

    Retorna {"texto": str, "provedor": str, "modelo": str, "tempo_ms": int}.
    """
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
                if "não configurada" in str(e).lower() or "API_KEY" in str(e):
                    break
                continue

    raise RuntimeError("Todos os provedores falharam:\n" + "\n".join(erros))


# ---------------------------------------------------------------------------
# Utilitários de diagnóstico
# ---------------------------------------------------------------------------

def diagnosticar_ollama() -> dict:
    """
    Verifica se o Ollama está acessível e se o modelo configurado está
    disponível. Retorna dict com status para facilitar debug.
    """
    import httpx
    resultado = {
        "url": OLLAMA_URL,
        "modelo_configurado": OLLAMA_MODEL,
        "servidor_acessivel": False,
        "modelo_disponivel": False,
        "modelos_instalados": [],
        "erro": None,
    }

    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        resp.raise_for_status()
        resultado["servidor_acessivel"] = True

        modelos = resp.json().get("models", [])
        resultado["modelos_instalados"] = [m.get("name", m.get("model", "?")) for m in modelos]

        nomes_modelos = [m.get("name", m.get("model", "")) for m in modelos]
        resultado["modelo_disponivel"] = any(
            OLLAMA_MODEL in nome or nome in OLLAMA_MODEL
            for nome in nomes_modelos
        )

    except Exception as e:
        resultado["erro"] = f"{type(e).__name__}: {e}"

    return resultado


def testar_provedor(nome_provedor: str, prompt_teste: str = "Responda apenas: TESTE") -> dict:
    """
    Testa um provedor específico com um prompt simples.
    """
    mapa = {nome: func for nome, func in PROVEDORES}
    if nome_provedor not in mapa:
        return {"erro": f"Provedor '{nome_provedor}' não encontrado. Disponíveis: {list(mapa.keys())}"}

    try:
        inicio = time.monotonic()
        texto = mapa[nome_provedor](prompt_teste)
        tempo = int((time.monotonic() - inicio) * 1000)
        return {
            "ok": True,
            "provedor": nome_provedor,
            "resposta": texto.strip(),
            "tempo_ms": tempo,
        }
    except Exception as e:
        return {
            "ok": False,
            "provedor": nome_provedor,
            "erro": f"{type(e).__name__}: {e}",
        }
