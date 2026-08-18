"""
chat.py — Interface de linha de comando para conversar com o Qwen3.
Projeto 2 do agente-ads: aprender o fluxo básico de um agente de IA.

Execute SEMPRE de dentro da pasta agente-ads:
  cd ~/projetos/agente-ads
  python chat.py
"""

import sys
import os

# Garante que o Python encontra os módulos do projeto
# independente de onde o terminal estiver
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.ollama_service import OllamaService

SYSTEM_PROMPT = """Você é um assistente técnico especializado em desenvolvimento de software.
Responda sempre em português brasileiro.
Seja direto, didático e use exemplos de código quando relevante.
Quando usar termos técnicos em inglês, coloque a tradução entre colchetes.
Exemplo: Query [consulta ao banco de dados], Framework [estrutura de desenvolvimento]."""


def main():
    servico = OllamaService()

    print("=" * 50)
    print("  DigitalTech — Agente ADS")
    print(f"  Modelo: {servico.model}")
    print("  Digite 'sair' para encerrar")
    print("  Digite 'limpar' para reiniciar a conversa")
    print("  Digite 'historico' para ver as mensagens")
    print("=" * 50)

    if not servico.verificar_conexao():
        print("\n❌ Ollama não está rodando.")
        print("   Execute em outro terminal: ollama serve")
        return

    print(f"\n✅ Ollama conectado. Modelo: {servico.model}\n")

    historico = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    while True:
        try:
            entrada = input("Você: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nEncerrando...")
            break

        if not entrada:
            continue

        if entrada.lower() == "sair":
            print("Até logo!")
            break

        if entrada.lower() == "limpar":
            historico = [{"role": "system", "content": SYSTEM_PROMPT}]
            print("✅ Histórico limpo. Nova conversa iniciada.\n")
            continue

        if entrada.lower() == "historico":
            print("\n--- Histórico da conversa ---")
            for msg in historico:
                if msg["role"] != "system":
                    prefixo = "Você" if msg["role"] == "user" else "Agente"
                    print(f"{prefixo}: {msg['content'][:100]}...")
            print("---\n")
            continue

        historico.append({"role": "user", "content": entrada})
        print("Agente: ", end="", flush=True)

        resposta = servico.chat(historico)
        print(resposta)
        print()

        historico.append({"role": "assistant", "content": resposta})


if __name__ == "__main__":
    main()
