import os
import subprocess
import sys

def rodar(comando, check=True, capturar=False):
    print(f"$ {' '.join(comando)}")
    if capturar:
        r = subprocess.run(comando, capture_output=True, text=True)
        print(r.stdout)
        if r.returncode != 0:
            print(r.stderr)
        return r
    r = subprocess.run(comando)
    if check and r.returncode != 0:
        print(f"ERRO: comando falhou ({r.returncode})")
        sys.exit(1)
    return r

if not os.path.isfile("app.py"):
    print("ERRO: rode dentro da pasta do repositorio do agente.")
    sys.exit(1)

print("=== 1. Adicionando dependencias que faltavam no requirements.txt ===")
with open("requirements.txt") as f:
    conteudo = f.read()
if "openai" not in conteudo:
    conteudo = conteudo.rstrip("\n") + "\nopenai>=1.0.0\nanthropic>=0.25.0\n"
    with open("requirements.txt", "w") as f:
        f.write(conteudo)
    print("OK: openai e anthropic adicionados (llm_service.py precisa deles pro fallback)")
else:
    print("AVISO: ja estavam la, pulei.")

print("\n=== 2. Movendo agentes nao usados para agents/backlog/ ===")
os.makedirs("agents/backlog", exist_ok=True)
for arq in [
    "base_agent.py", "ebook_agent.py", "fact_check_agent.py", "infographic_agent.py",
    "newsletter_agent.py", "social_media_agent.py", "translation_agent.py",
    "trend_analysis_agent.py", "video_agent.py",
]:
    rodar(["git", "mv", f"agents/{arq}", f"agents/backlog/{arq}"])
with open("agents/backlog/README.md", "w", encoding="utf-8") as f:
    f.write(
        "# Backlog de agentes\n\n"
        "Esboços escritos mas ainda não conectados a nenhum pipeline "
        "(nenhum import no projeto referencia estes arquivos). Ficam aqui "
        "como referência para quando fizer sentido implementar de verdade, "
        "em vez de misturados com os agentes que já rodam em produção.\n"
    )
rodar(["git", "add", "agents/backlog/README.md"])

print("\n=== 3. Movendo os .ts do agente GitHub Actions para scripts/agente/ ===")
os.makedirs("scripts/agente", exist_ok=True)
for arq in [
    "buscar-topico.ts", "gerar-artigo.ts", "gerar-imagem.ts", "index.ts",
    "ollama-client.ts", "publicar.ts", "types.ts",
]:
    rodar(["git", "mv", f"agents/{arq}", f"scripts/agente/{arq}"])

print("\n=== 4. Movendo o workflow para .github/workflows/ (onde o GitHub reconhece) ===")
os.makedirs(".github/workflows", exist_ok=True)
rodar(["git", "mv", "agents/agente-noticias.yml", ".github/workflows/agente-noticias.yml"])

print("\n=== 5. Consolidando documentacao solta em docs/ ===")
os.makedirs("docs", exist_ok=True)
rodar(["git", "mv", "agents/COMO-APLICAR.md", "docs/COMO-APLICAR-agente.md"])
rodar(["git", "mv", "agents/LEIA-ME-AGENTE.md", "docs/LEIA-ME-AGENTE.md"])

print("\n=== 6. Apagando duplicatas mortas e lixo confirmados por diff + grep ===")
for arq in [
    "agents/chat.py", "agents/chat_memoria.py", "agents/chat_repository.py",
    "agents/llm_service.py", "agents/ollama_service.py", "agents/settings.py",
    "agents/requirements.txt", "agents/app_patch.py",
    "services/ollama_service.py.save",
]:
    rodar(["git", "rm", arq])

print("\n=== Validando sintaxe do que sobrou em agents/ e scripts/ ===")
import py_compile
for raiz, _, arquivos in os.walk("agents"):
    if "backlog" in raiz or "__pycache__" in raiz:
        continue
    for arq in arquivos:
        if arq.endswith(".py"):
            py_compile.compile(os.path.join(raiz, arq), doraise=True)
print("Sintaxe OK nos arquivos .py ativos de agents/")

print("\n===== STATUS FINAL (revise antes de continuar) =====")
rodar(["git", "status"], check=False)
print("=====================================================\n")

confirmacao = input("Está correto? Digite 'sim' para commitar, ou qualquer outra tecla para cancelar: ")
if confirmacao.strip().lower() != "sim":
    print("Cancelado. Rode 'git reset' e 'git checkout -- .' pra desfazer tudo, se quiser.")
    sys.exit(0)

rodar(["git", "add", "-A"])
mensagem = (
    "chore: reorganiza estrutura do projeto\n\n"
    "- agents/: remove 8 duplicatas mortas (sem import em lugar nenhum) e\n"
    "  1 script de migracao ja aplicado (app_patch.py)\n"
    "- agents/backlog/: 9 agentes especializados ainda nao conectados a\n"
    "  nenhum pipeline (1112 linhas), tirados do caminho principal\n"
    "- scripts/agente/: arquivos .ts do agente via GitHub Actions, que\n"
    "  estavam soltos dentro de agents/\n"
    "- .github/workflows/: agente-noticias.yml movido pra onde o GitHub\n"
    "  de fato reconhece workflows -- estava inerte em agents/\n"
    "- docs/: documentacao solta consolidada (COMO-APLICAR-agente.md,\n"
    "  LEIA-ME-AGENTE.md)\n"
    "- requirements.txt: adiciona openai e anthropic, que faltavam apesar\n"
    "  de llm_service.py depender deles no fallback chain\n"
    "- remove services/ollama_service.py.save (arquivo de backup de editor)"
)
rodar(["git", "commit", "-m", mensagem])
print("\nCommit feito. Para enviar ao GitHub, rode:")
print("  git push origin main")
