# Execute este script dentro da pasta do agente para atualizar o import
import re

with open("app.py", "r") as f:
    conteudo = f.read()

conteudo = conteudo.replace(
    "from services.gemini_service import gerar_artigo",
    "from services.llm_service import gerar_artigo"
)

with open("app.py", "w") as f:
    f.write(conteudo)

print("app.py atualizado com sucesso")
