"""
scripts/verificar_modelos_openrouter.py — Confere modelos REAIS no OpenRouter

Não confia em nenhuma lista digitada de memória (nem a minha, nem a de
nenhuma outra IA) — consulta a API pública do OpenRouter (não precisa
de chave pra LISTAR modelos, só pra usar) e confere se os IDs que
vocês colocaram em config/provedores.yaml realmente existem.

Uso:
    python scripts/verificar_modelos_openrouter.py
"""

import httpx

IDS_PARA_CONFERIR = [
    "openai/gpt-5.6-luna",
    "anthropic/claude-opus-5",
    "anthropic/claude-opus-4.8",   # alternativa correta, se a de cima não existir
    "google/gemini-3.6-flash",
    "google/gemini-3.5-flash",     # alternativa, se a de cima não existir
    "moonshotai/kimi-k3",
    "moonshotai/kimi-k2.6",        # alternativa, se a de cima não existir
    "deepseek/deepseek-v4-flash",
]


def main():
    resp = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    resp.raise_for_status()
    modelos = resp.json().get("data", [])
    ids_reais = {m["id"] for m in modelos}

    print(f"Total de modelos disponíveis no OpenRouter agora: {len(ids_reais)}\n")

    for id_desejado in IDS_PARA_CONFERIR:
        if id_desejado in ids_reais:
            print(f"✅ EXISTE: {id_desejado}")
        else:
            print(f"❌ NÃO EXISTE: {id_desejado}")

    print("\n--- Modelos reais disponíveis por provedor (amostra) ---")
    for prefixo in ["anthropic/", "openai/", "google/", "moonshotai/", "deepseek/"]:
        candidatos = sorted(i for i in ids_reais if i.startswith(prefixo))
        print(f"\n{prefixo}")
        for c in candidatos[:10]:
            print(f"  {c}")


if __name__ == "__main__":
    main()
