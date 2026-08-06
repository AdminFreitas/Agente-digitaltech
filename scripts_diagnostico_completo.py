#!/usr/bin/env python3
"""
scripts/diagnostico_completo.py — Diagnóstico de TODAS as configurações

Mostra:
- Quais chaves de API estão configuradas (✅/❌)
- Quais modelos estão sendo usados
- Ordem de fallback configurada
- Teste rápido de cada provedor que tem chave

Uso:
    python scripts/diagnostico_completo.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def _banner(texto: str):
    print(f"\n{'='*60}")
    print(f"  {texto}")
    print(f"{'='*60}")


def _check_env(nome: str, mascara: bool = True) -> str:
    valor = os.getenv(nome, "")
    if valor:
        if mascara:
            return f"✅ configurada ({valor[:8]}...{valor[-4:]})"
        return f"✅ {valor}"
    return "❌ NÃO CONFIGURADA"


def main():
    _banner("DIAGNÓSTICO COMPLETO DO AGENTE DIGITALTECH")

    # 1. Configuração geral
    print("\n📋 CONFIGURAÇÃO GERAL")
    print(f"  ENVIRONMENT:        {os.getenv('ENVIRONMENT', '❌ não definido')}")
    print(f"  DEFAULT_LLM:        {os.getenv('DEFAULT_LLM', '❌ não definido (padrão: ollama)')}")
    print(f"  FALLBACK_ORDER:     {os.getenv('FALLBACK_ORDER', '❌ não definido')}")
    print(f"  AGENTE_AUTOR_ID:    {os.getenv('AGENTE_AUTOR_ID', '❌ não definido')}")

    # 2. Banco de dados
    print("\n🗄️  BANCO DE DADOS")
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        # Mascara a senha na URL
        import re
        url_mascarada = re.sub(r"://[^:]+:[^@]+@", "://***:***@", db_url)
        print(f"  DATABASE_URL:       ✅ {url_mascarada[:60]}...")
    else:
        print(f"  DATABASE_URL:       ❌ não definida")
        print(f"  DB_HOST:            {os.getenv('DB_HOST', '❌')}")
        print(f"  DB_PORT:            {os.getenv('DB_PORT', '❌')}")
        print(f"  DB_NAME:            {os.getenv('DB_NAME', '❌')}")
        print(f"  DB_USER:            {os.getenv('DB_USER', '❌')}")
        print(f"  DB_PASSWORD:        {'✅ definida' if os.getenv('DB_PASSWORD') else '❌'}")

    # 3. LLMs — chaves e modelos
    print("\n🤖 PROVEDORES DE LLM")

    provedores = [
        ("Ollama",     "OLLAMA_MODEL",  "OLLAMA_URL",     False),
        ("Gemini",     "GEMINI_MODEL",  "GEMINI_API_KEY", True),
        ("OpenAI",     "OPENAI_MODEL",  "OPENAI_API_KEY", True),
        ("Claude",     "ANTHROPIC_MODEL", "ANTHROPIC_API_KEY", True),
        ("DeepSeek",   "DEEPSEEK_MODEL", "DEEPSEEK_API_KEY", True),
        ("HuggingFace", "HUGGINGFACE_MODEL", "HUGGINGFACE_API_KEY", True),
        ("Grok",       None,            "GROK_API_KEY",   True),
    ]

    for nome, model_var, key_var, needs_key in provedores:
        print(f"\n  {nome}:")
        if model_var:
            print(f"    Modelo:           {os.getenv(model_var, '❌ não definido')}")
        if needs_key:
            print(f"    Chave:            {_check_env(key_var)}")
        else:
            print(f"    URL:              {os.getenv(key_var, '❌ não definido')}")

    # 4. Imagens
    print("\n🖼️  FONTES DE IMAGEM")
    fontes = [
        ("Unsplash",    "UNSPLASH_ACCESS_KEY"),
        ("Pexels",      "PEXELS_API_KEY"),
        ("Pixabay",     "PIXABAY_API_KEY"),
        ("Openverse",   "OPENVERSE_CLIENT_ID"),
    ]
    for nome, var in fontes:
        print(f"  {nome:<15} {_check_env(var)}")
    print(f"  {'Pollinations AI':<15} ✅ sem chave (sempre disponível)")

    # 5. GitHub
    print("\n📦 GITHUB")
    print(f"  GITHUB_TOKEN:       {_check_env('GITHUB_TOKEN')}")
    print(f"  GITHUB_OWNER:       {os.getenv('GITHUB_OWNER', '❌')}")
    print(f"  GITHUB_REPOSITORY:  {os.getenv('GITHUB_REPOSITORY', '❌')}")
    print(f"  GITHUB_BRANCH:      {os.getenv('GITHUB_BRANCH', '❌')}")

    # 6. Outros
    print("\n📰 OUTROS SERVIÇOS")
    print(f"  NEWSAPI_KEY:        {_check_env('NEWSAPI_KEY')}")
    print(f"  SUPERMEMORY_API_KEY: {_check_env('SUPERMEMORY_API_KEY')}")

    # 7. Teste rápido de conectividade
    _banner("TESTE DE CONECTIVIDADE")

    # Ollama
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    try:
        import httpx
        resp = httpx.get(f"{ollama_url}/api/tags", timeout=10)
        if resp.status_code == 200:
            modelos = [m.get("name", "?") for m in resp.json().get("models", [])]
            print(f"  Ollama:             ✅ OK ({', '.join(modelos[:5])})")
        else:
            print(f"  Ollama:             ❌ HTTP {resp.status_code}")
    except Exception as e:
        print(f"  Ollama:             ❌ {e}")

    # Banco
    try:
        from config.database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1")).fetchone()
        db.close()
        print(f"  Banco de dados:     ✅ OK")
    except Exception as e:
        print(f"  Banco de dados:     ❌ {e}")

    # GitHub
    gh_token = os.getenv("GITHUB_TOKEN")
    if gh_token:
        try:
            resp = httpx.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {gh_token}"},
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"  GitHub:             ✅ OK (usuário: {resp.json().get('login', '?')})")
            else:
                print(f"  GitHub:             ❌ HTTP {resp.status_code}")
        except Exception as e:
            print(f"  GitHub:             ❌ {e}")
    else:
        print(f"  GitHub:             ⚠️  token não configurado")

    print("\n" + "="*60)
    print("  Diagnóstico concluído.")
    print("="*60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
