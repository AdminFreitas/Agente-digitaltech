#!/usr/bin/env python3
"""
setup_db.py — Cria as tabelas do banco de dados no PostgreSQL/Neon

Uso:
    python setup_db.py

O script le o database/schema.sql e executa no banco configurado no .env.
"""

import os
import sys

# Adiciona a raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.database import engine, SessionLocal, Base, DATABASE_URL

def main():
    if not DATABASE_URL:
        print("❌ DATABASE_URL nao configurado. Verifique seu .env")
        sys.exit(1)

    print(f"📡 Conectando ao banco...")
    print(f"   URL: {DATABASE_URL.replace('://', '://***:***@')}")

    schema_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "database", "schema.sql"
    )

    if not os.path.exists(schema_path):
        print(f"❌ Schema nao encontrado: {schema_path}")
        sys.exit(1)

    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()

    print(f"📄 Schema carregado ({len(sql)} chars)")

    # Executa o SQL raw
    from sqlalchemy import text
    db = SessionLocal()
    try:
        # Divide por comandos e executa um a um (evita problemas com comments)
        comandos = [cmd.strip() for cmd in sql.split(";") if cmd.strip()]
        executados = 0
        for cmd in comandos:
            # Pula comentarios puros
            linhas = [l.strip() for l in cmd.splitlines() if l.strip() and not l.strip().startswith("--")]
            if not linhas:
                continue
            try:
                db.execute(text(cmd))
                executados += 1
            except Exception as e:
                # Ignora erros de "already exists" e conflitos de INSERT
                err = str(e).lower()
                if "already exists" in err or "duplicate key" in err or "unique constraint" in err:
                    print(f"   ⚠️  Ignorado (ja existe): {e}")
                else:
                    print(f"   ❌ Erro: {e}")
                    raise

        db.commit()
        print(f"✅ {executados} comandos executados com sucesso!")
        print("🎉 Banco de dados pronto para uso.")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Falha ao criar tabelas: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()