"""
pipeline/workflow.py — Ponto de entrada de linha de comando

Roda o fluxo completo de geração de um artigo evergreen (a mesma
cadeia usada pela API): pesquisador → editor → revisor → imagem_service
→ seo → publisher. Ajuste TEMA/CATEGORIA abaixo, ou adapte para
receber por argumento de linha de comando (sys.argv) se preferir.

Requer DATABASE_URL (ou DB_HOST/DB_NAME/DB_USER/DB_PASSWORD) já
configurado no .env — a mesma sessão usada pela API é aberta aqui via
config.database.SessionLocal.
"""

from config.database import SessionLocal
from pipeline.gerar_artigos import gerar_e_processar_artigo


def main():
    tema = "Como usar índices no PostgreSQL para melhorar performance"
    categoria = "Banco de Dados"

    db = SessionLocal()
    try:
        resultado = gerar_e_processar_artigo(db, tema, categoria)
        print(f"Artigo salvo: {resultado}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
