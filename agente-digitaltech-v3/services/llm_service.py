"""
llm_service.py — Fallback Chain de modelos de linguagem (v3.0)

NOVA ARQUITETURA:
  1. Ollama (local, gratuito) → primeira tentativa sempre
  2. OpenRouter (hub central, uma chave só) → múltiplos modelos
  3. Se OpenRouter falhar (sem créditos, indisponível) → volta pro Ollama

CONFIGURAÇÃO:
  Edite config/provedores.yaml para trocar modelos sem alterar código.
  O agente lê a config em tempo de execução.

TAREFAS ESPECIALIZADAS:
  Cada tarefa (escrever_artigo, revisar, seo, etc.) pode ter sua própria
  ordem de prioridade de modelos, definida no YAML.
"""

import os
import re
import unicodedata
import time
import yaml
from datetime import date, datetime, timedelta
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Carrega configuração centralizada
# ---------------------------------------------------------------------------

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "provedores.yaml")


def _carregar_config() -> dict:
    """Lê config/provedores.yaml e resolve variáveis de ambiente."""
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = f.read()
    # Resolve ${VAR} do ambiente
    def _resolve_env(match):
        var = match.group(1)
        return os.getenv(var, f"${{{var}}}")
    raw = re.sub(r"\$\{([^}]+)\}", _resolve_env, raw)
    return yaml.safe_load(raw)


_CONFIG = _carregar_config()

# Estado de fallback (quando créditos acabam)
_openrouter_desativado_ate: Optional[datetime] = None


def _openrouter_esta_desativado() -> bool:
    global _openrouter_desativado_ate
    if _openrouter_desativado_ate is None:
        return False
    if datetime.now() >= _openrouter_desativado_ate:
        _openrouter_desativado_ate = None
        return False
    return True


def _desativar_openrouter():
    global _openrouter_desativado_ate
    minutos = _CONFIG.get("fallback_sem_creditos", {}).get("desativar_openrouter_minutos", 30)
    _openrouter_desativado_ate = datetime.now() + timedelta(minutes=minutos)
    print(f"[LLM] OpenRouter desativado por {minutos} minutos (sem créditos ou rate limit)")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Provedores individuais
# ---------------------------------------------------------------------------

def _tentar_ollama(prompt: str, config: dict) -> str:
    import httpx

    payload = {
        "model": config["model"],
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": config.get("options", {}),
    }

    timeout = config.get("timeout", 180)
    url = config.get("url", "http://localhost:11434")

    print(f"[Ollama] model={config['model']}, timeout={timeout}s")

    try:
        resp = httpx.post(f"{url}/api/chat", json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if "message" not in data or "content" not in data.get("message", {}):
            raise RuntimeError(f"Resposta inesperada: {data.keys()}")
        return data["message"]["content"]
    except httpx.TimeoutException as e:
        raise RuntimeError(f"Timeout Ollama ({timeout}s): {e}")


def _tentar_openrouter(prompt: str, modelo_id: str, config: dict) -> str:
    import httpx

    api_key = config.get("api_key", "")
    if not api_key or api_key.startswith("$"):
        raise RuntimeError("OPENROUTER_API_KEY não configurada")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # Adiciona headers customizados do OpenRouter
    for k, v in config.get("headers", {}).items():
        headers[k] = v

    payload = {
        "model": modelo_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2000,
    }

    url = f"{config.get('base_url', 'https://openrouter.ai/api/v1')}/chat/completions"
    timeout = config.get("timeout", 60)

    print(f"[OpenRouter] model={modelo_id}, timeout={timeout}s")

    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)

        # 402 = sem créditos, 429 = rate limit
        if resp.status_code in (402, 429):
            _desativar_openrouter()
            raise RuntimeError(f"OpenRouter {resp.status_code}: {resp.text}")

        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    except httpx.TimeoutException as e:
        raise RuntimeError(f"Timeout OpenRouter ({timeout}s): {e}")


# ---------------------------------------------------------------------------
# Resolução de provedores a partir da config
# ---------------------------------------------------------------------------

def _resolver_provedores(tarefa: str = "gerar_texto_livre") -> list[tuple[str, callable]]:
    """
    Retorna a lista de (nome, função) na ordem correta para a tarefa,
    respeitando o estado de fallback (créditos esgotados).
    """
    tarefas_cfg = _CONFIG.get("tarefas", {})
    tarefa_cfg = tarefas_cfg.get(tarefa, tarefas_cfg.get("gerar_texto_livre", {}))
    preferencia = tarefa_cfg.get("preferencia", ["local"])

    provedores = []
    local_cfg = _CONFIG.get("local", {})
    or_cfg = _CONFIG.get("openrouter", {})
    or_modelos = or_cfg.get("modelos", {})

    for item in preferencia:
        if item == "local":
            if local_cfg.get("enabled", True):
                provedores.append((
                    f"Ollama ({local_cfg.get('model', 'local')})",
                    lambda p, c=local_cfg: _tentar_ollama(p, c)
                ))
        elif item.startswith("openrouter/"):
            if _openrouter_esta_desativado():
                continue
            chave = item.split("/", 1)[1]
            modelo = or_modelos.get(chave)
            if modelo and or_cfg.get("enabled", True):
                provedores.append((
                    f"OpenRouter/{chave}",
                    lambda p, m=modelo["id"], c=or_cfg: _tentar_openrouter(p, m, c)
                ))

    return provedores


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------

def gerar_artigo(tema: str, categoria: str = "Tecnologia", tentativas_por_provedor: int = 2) -> dict:
    prompt = _montar_prompt(tema, categoria)
    erros = []

    provedores = _resolver_provedores("escrever_artigo")
    if not provedores:
        provedores = _resolver_provedores("gerar_texto_livre")

    for nome, funcao in provedores:
        for tentativa in range(1, tentativas_por_provedor + 1):
            try:
                print(f"[LLM] Tentando {nome} (tentativa {tentativa}/{tentativas_por_provedor})...")
                inicio = time.monotonic()
                texto = funcao(prompt)
                tempo_ms = int((time.monotonic() - inicio) * 1000)
            except Exception as e:
                print(f"[LLM] {nome} falhou: {e}")
                erros.append(f"{nome}: {e}")
                continue

            preview = texto[:500].replace("\n", "\\n")
            print(f"[LLM] Resposta bruta de {nome}: {preview}")

            try:
                dados = _parsear_resposta(texto)
                print(f"[LLM] Sucesso com {nome} em {tempo_ms}ms")
                return _montar_artigo(dados, categoria, nome)
            except ValueError as e:
                print(f"[LLM] {nome} retornou resposta malformada: {e}")
                erros.append(f"{nome} (tentativa {tentativa}): resposta malformada — {e}")

    raise RuntimeError("Todos os provedores falharam:\n" + "\n".join(erros))


parsear_resposta_padrao = _parsear_resposta
gerar_slug = _gerar_slug


def gerar_texto(prompt: str, tarefa: str = "gerar_texto_livre", tentativas_por_provedor: int = 2) -> str:
    erros = []
    provedores = _resolver_provedores(tarefa)

    for nome, funcao in provedores:
        for tentativa in range(1, tentativas_por_provedor + 1):
            try:
                print(f"[LLM] (gerar_texto/{tarefa}) Tentando {nome} (tentativa {tentativa}/{tentativas_por_provedor})...")
                texto = funcao(prompt)
                if texto and texto.strip():
                    return texto.strip()
                raise RuntimeError("resposta vazia")
            except Exception as e:
                print(f"[LLM] (gerar_texto/{tarefa}) {nome} falhou: {e}")
                erros.append(f"{nome} (tentativa {tentativa}): {e}")
                continue

    raise RuntimeError("Todos os provedores falharam:\n" + "\n".join(erros))


def gerar_texto_com_metadados(prompt: str, tarefa: str = "gerar_texto_livre", tentativas_por_provedor: int = 2) -> dict:
    erros = []
    provedores = _resolver_provedores(tarefa)

    for nome, funcao in provedores:
        for tentativa in range(1, tentativas_por_provedor + 1):
            try:
                print(f"[LLM] (metadados/{tarefa}) Tentando {nome} (tentativa {tentativa}/{tentativas_por_provedor})...")
                inicio = time.monotonic()
                texto = funcao(prompt)
                tempo_ms = int((time.monotonic() - inicio) * 1000)
                if texto and texto.strip():
                    return {
                        "texto": texto.strip(),
                        "provedor": nome,
                        "modelo": nome,
                        "tempo_ms": tempo_ms,
                    }
                raise RuntimeError("resposta vazia")
            except Exception as e:
                print(f"[LLM] (metadados/{tarefa}) {nome} falhou: {e}")
                erros.append(f"{nome} (tentativa {tentativa}): {e}")
                continue

    raise RuntimeError("Todos os provedores falharam:\n" + "\n".join(erros))


# ---------------------------------------------------------------------------
# Diagnóstico
# ---------------------------------------------------------------------------

def diagnosticar_ollama() -> dict:
    import httpx
    local_cfg = _CONFIG.get("local", {})
    resultado = {
        "url": local_cfg.get("url", "http://localhost:11434"),
        "modelo_configurado": local_cfg.get("model", "?"),
        "servidor_acessivel": False,
        "modelo_disponivel": False,
        "modelos_instalados": [],
        "erro": None,
    }
    try:
        resp = httpx.get(f"{resultado['url']}/api/tags", timeout=10)
        resp.raise_for_status()
        resultado["servidor_acessivel"] = True
        modelos = resp.json().get("models", [])
        resultado["modelos_instalados"] = [m.get("name", m.get("model", "?")) for m in modelos]
        nomes = [m.get("name", m.get("model", "")) for m in modelos]
        resultado["modelo_disponivel"] = any(resultado["modelo_configurado"] in n or n in resultado["modelo_configurado"] for n in nomes)
    except Exception as e:
        resultado["erro"] = f"{type(e).__name__}: {e}"
    return resultado


def testar_provedor(nome_provedor: str, prompt_teste: str = "Responda apenas: TESTE") -> dict:
    mapa = {nome: func for nome, func in _resolver_provedores("gerar_texto_livre")}
    if nome_provedor not in mapa:
        return {"erro": f"Provedor '{nome_provedor}' não encontrado. Disponíveis: {list(mapa.keys())}"}
    try:
        inicio = time.monotonic()
        texto = mapa[nome_provedor](prompt_teste)
        tempo = int((time.monotonic() - inicio) * 1000)
        return {"ok": True, "provedor": nome_provedor, "resposta": texto.strip(), "tempo_ms": tempo}
    except Exception as e:
        return {"ok": False, "provedor": nome_provedor, "erro": f"{type(e).__name__}: {e}"}


def listar_provedores_disponiveis() -> list[str]:
    """Retorna lista de nomes dos provedores que estão disponíveis agora."""
    return [nome for nome, _ in _resolver_provedores("gerar_texto_livre")]
