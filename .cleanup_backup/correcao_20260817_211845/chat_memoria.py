"""
chat_memoria.py — Chat com memória persistente no PostgreSQL.
Projeto 3 do agente-ads.

Diferença do Projeto 2:
  Antes: histórico some ao fechar o terminal
  Agora: histórico salvo no banco — conversa pode ser retomada

Execute de dentro da pasta agente-ads:
  cd ~/projetos/agente-ads
  python chat_memoria.py
"""

import sys
import os
import uuid  # gera identificadores únicos para cada sessão

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.ollama_service import OllamaService
from repositories.chat_repository import ChatRepository
from config.database import get_db

SYSTEM_PROMPT = """Você é um assistente técnico especializado em desenvolvimento de software.
Responda sempre em português brasileiro.
Seja direto, didático e use exemplos de código quando relevante.
Quando usar termos técnicos em inglês, coloque a tradução entre colchetes.
Exemplo: Query [consulta ao banco de dados], Framework [estrutura de desenvolvimento]."""


def escolher_sessao(repo: ChatRepository) -> str:
    """
    Pergunta ao usuário se quer continuar uma sessão existente
    ou iniciar uma nova.
    """
    sessoes = repo.listar_sessoes()

    if not sessoes:
        session_id = str(uuid.uuid4())[:8]  # ID curto — ex: "a1b2c3d4"
        print(f"✅ Nova sessão iniciada: {session_id}\n")
        return session_id

    print("\nSessões anteriores encontradas:")
    for i, s in enumerate(sessoes[:5], 1):  # mostra até 5 sessões
        print(f"  [{i}] {s}")
    print(f"  [N] Nova sessão")

    escolha = input("\nEscolha uma sessão ou N para nova: ").strip().upper()

    if escolha == "N" or not escolha:
        session_id = str(uuid.uuid4())[:8]
        print(f"✅ Nova sessão iniciada: {session_id}\n")
        return session_id

    try:
        indice = int(escolha) - 1
        session_id = sessoes[indice]
        print(f"✅ Continuando sessão: {session_id}\n")
        return session_id
    except (ValueError, IndexError):
        session_id = str(uuid.uuid4())[:8]
        print(f"✅ Nova sessão iniciada: {session_id}\n")
        return session_id


def main():
    servico = OllamaService()

    print("=" * 50)
    print("  DigitalTech — Agente ADS com Memória")
    print(f"  Modelo: {servico.model}")
    print("  Digite 'sair' para encerrar")
    print("  Digite 'historico' para ver as mensagens")
    print("=" * 50)

    if not servico.verificar_conexao():
        print("\n❌ Ollama não está rodando. Execute: ollama serve")
        return

    # Obtém uma sessão do banco de dados
    db = next(get_db())
    repo = ChatRepository(db)

    session_id = escolher_sessao(repo)

    # Carrega histórico existente do banco (se houver)
    historico = [{"role": "system", "content": SYSTEM_PROMPT}]
    mensagens_salvas = repo.carregar_historico(session_id)

    if mensagens_salvas:
        historico.extend(mensagens_salvas)
        print(f"📂 {len(mensagens_salvas)} mensagens carregadas do banco.\n")

    while True:
        try:
            entrada = input("Você: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nEncerrando...")
            break

        if not entrada:
            continue

        if entrada.lower() == "sair":
            print("Até logo! Conversa salva no banco.")
            break

        if entrada.lower() == "historico":
            print(f"\n--- Sessão: {session_id} ---")
            for msg in historico:
                if msg["role"] != "system":
                    prefixo = "Você" if msg["role"] == "user" else "Agente"
                    print(f"{prefixo}: {msg['content'][:100]}...")
            print("---\n")
            continue

        # Salva mensagem do usuário no banco ANTES de enviar ao modelo
        repo.salvar_mensagem(session_id, "usuario", entrada)
        historico.append({"role": "user", "content": entrada})

        print("Agente: ", end="", flush=True)
        resposta = servico.chat(historico)
        print(resposta)
        print()

        # Salva resposta do agente no banco
        repo.salvar_mensagem(session_id, "agente", resposta)
        historico.append({"role": "assistant", "content": resposta})


if __name__ == "__main__":
    main()
