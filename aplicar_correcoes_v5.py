#!/usr/bin/env python3
"""
aplicar_correcoes_v5.py — Script de aplicação automática

Uso:
    python aplicar_correcoes_v5.py

Arquivos necessários na MESMA pasta deste script:
- services_imagem_service_v5.py
- services_llm_service_v5.py
- rodar_agente_v41.py
- pipeline_gerar_artigos_v4.py
"""

import shutil
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CORRECOES = [
    {
        "nome": "services/imagem_service.py",
        "origem": "services_imagem_service_v5.py",
        "destino": os.path.join("services", "imagem_service.py"),
        "descricao": "Openverse primeiro, RSS para notícias, Pollinations último recurso",
    },
    {
        "nome": "services/llm_service.py",
        "origem": "services_llm_service_v5.py",
        "destino": os.path.join("services", "llm_service.py"),
        "descricao": "DeepSeek, HuggingFace, Grok + ordem configurável via .env",
    },
    {
        "nome": "rodar_agente.py",
        "origem": "rodar_agente_v41.py",
        "destino": "rodar_agente.py",
        "descricao": "CLI unificado com correções de assinatura e exit code",
    },
    {
        "nome": "pipeline/gerar_artigos.py",
        "origem": "pipeline_gerar_artigos_v4.py",
        "destino": os.path.join("pipeline", "gerar_artigos.py"),
        "descricao": "Sem 'db' como argumento, sessões curtas internas",
    },
]


def main():
    print("=" * 60)
    print("APLICADOR DE CORREÇÕES v5")
    print("=" * 60)

    todos_ok = True

    for corr in CORRECOES:
        origem_path = os.path.join(SCRIPT_DIR, corr["origem"])
        destino_path = os.path.join(SCRIPT_DIR, corr["destino"])

        print(f"\n📦 {corr['nome']}")
        print(f"   {corr['descricao']}")

        if not os.path.exists(origem_path):
            print(f"   ❌ ARQUIVO DE ORIGEM NÃO ENCONTRADO: {corr['origem']}")
            todos_ok = False
            continue

        if os.path.exists(destino_path):
            backup_path = destino_path + ".bak"
            shutil.copy2(destino_path, backup_path)
            print(f"   💾 Backup: {backup_path}")

        destino_dir = os.path.dirname(destino_path)
        if destino_dir and not os.path.exists(destino_dir):
            os.makedirs(destino_dir)

        shutil.copy2(origem_path, destino_path)

        if os.path.exists(destino_path):
            tamanho = os.path.getsize(destino_path)
            print(f"   ✅ Aplicado ({tamanho} bytes)")
        else:
            print(f"   ❌ Falha ao copiar")
            todos_ok = False

    print("\n" + "=" * 60)
    if todos_ok:
        print("✅ TODAS AS CORREÇÕES APLICADAS")
        print("\nPróximos passos:")
        print("   1. pip install google-genai")
        print("   2. Atualize seu .env com os modelos corretos (veja .env.example_v5)")
        print("   3. python scripts/diagnostico_completo.py")
        print("   4. python rodar_agente.py --diagnostico")
        print("   5. python rodar_agente.py --artigos --sem-publicar")
        return 0
    else:
        print("❌ ALGUMAS CORREÇÕES NÃO FORAM APLICADAS")
        return 1


if __name__ == "__main__":
    sys.exit(main())
