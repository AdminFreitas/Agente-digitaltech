#!/usr/bin/env python3
"""
aplicar_correcoes.py — Script de aplicação automática das correções v4.1

Uso:
    python aplicar_correcoes.py

O que faz:
1. Verifica se os 3 arquivos de correção estão na pasta atual
2. Faz backup dos arquivos antigos (.bak)
3. Copia os novos arquivos para as pastas corretas
4. Verifica se a cópia foi bem-sucedida
5. Mostra resumo do que foi aplicado

Arquivos necessários na MESMA pasta deste script:
- rodar_agente_v41.py
- services_llm_service_v4.py
- pipeline_gerar_artigos_v4.py
"""

import shutil
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CORRECOES = [
    {
        "nome": "rodar_agente.py",
        "origem": "rodar_agente_v41.py",
        "destino": "rodar_agente.py",
        "descricao": "CLI unificado (sugerir_tema com categoria, exit code, NoticiaRepository.publicar)",
    },
    {
        "nome": "services/llm_service.py",
        "origem": "services_llm_service_v4.py",
        "destino": os.path.join("services", "llm_service.py"),
        "descricao": "LLM service (Gemini google-genai, Ollama timeout 400s, Claude modelo correto)",
    },
    {
        "nome": "pipeline/gerar_artigos.py",
        "origem": "pipeline_gerar_artigos_v4.py",
        "destino": os.path.join("pipeline", "gerar_artigos.py"),
        "descricao": "Pipeline de artigos (sem 'db' como argumento, sessões curtas, pesquisar_tema comentado)",
    },
]


def main():
    print("=" * 60)
    print("APLICADOR DE CORREÇÕES v4.1")
    print("=" * 60)

    todos_ok = True

    for corr in CORRECOES:
        origem_path = os.path.join(SCRIPT_DIR, corr["origem"])
        destino_path = os.path.join(SCRIPT_DIR, corr["destino"])

        print(f"\n📦 {corr['nome']}")
        print(f"   {corr['descricao']}")

        # Verifica se arquivo de origem existe
        if not os.path.exists(origem_path):
            print(f"   ❌ ARQUIVO DE ORIGEM NÃO ENCONTRADO: {corr['origem']}")
            print(f"      Certifique-se de que '{corr['origem']}' está na mesma pasta deste script.")
            todos_ok = False
            continue

        # Faz backup do arquivo antigo (se existir)
        if os.path.exists(destino_path):
            backup_path = destino_path + ".bak"
            shutil.copy2(destino_path, backup_path)
            print(f"   💾 Backup criado: {backup_path}")

        # Cria pasta de destino se não existir
        destino_dir = os.path.dirname(destino_path)
        if destino_dir and not os.path.exists(destino_dir):
            os.makedirs(destino_dir)
            print(f"   📁 Pasta criada: {destino_dir}")

        # Copia o arquivo novo
        shutil.copy2(origem_path, destino_path)

        # Verifica se copiou certo
        if os.path.exists(destino_path):
            tamanho = os.path.getsize(destino_path)
            print(f"   ✅ Aplicado ({tamanho} bytes)")
        else:
            print(f"   ❌ Falha ao copiar")
            todos_ok = False

    print("\n" + "=" * 60)
    if todos_ok:
        print("✅ TODAS AS CORREÇÕES APLICADAS COM SUCESSO")
        print("\nPróximo passo:")
        print("   pip install google-genai")
        print("   python rodar_agente.py --diagnostico")
        return 0
    else:
        print("❌ ALGUMAS CORREÇÕES NÃO FORAM APLICADAS")
        print("   Verifique os erros acima e tente novamente.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
