"""
verificar_schema_imagens.py
Confere as colunas reais de `noticias` e `imagens`, e os dados atuais
da notícia id=4 -- sem depender de DATABASE_URL exportado no shell
(usa o mesmo carregamento de .env que o resto do projeto já usa).

Como usar:
  1. Copie para dentro de ~/projetos/agente-ads
  2. Rode: python verificar_schema_imagens.py
"""

from config.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

print("=== Colunas de noticias ===")
for row in db.execute(text("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'noticias'
    ORDER BY ordinal_position
""")).fetchall():
    print(row)

print("\n=== Colunas de imagens ===")
existe_imagens = db.execute(text("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'imagens'
    ORDER BY ordinal_position
""")).fetchall()
if existe_imagens:
    for row in existe_imagens:
        print(row)
else:
    print("(tabela 'imagens' não existe, ou não tem colunas visíveis)")

print("\n=== Notícia id=4 ===")
noticia = db.execute(text("SELECT * FROM noticias WHERE id = 4")).fetchone()
if noticia:
    print(dict(noticia._mapping))
else:
    print("(nenhuma notícia com id=4)")

if existe_imagens:
    print("\n=== Registros em imagens ligados à notícia 4 (se a coluna existir) ===")
    try:
        imagens = db.execute(
            text("SELECT * FROM imagens WHERE noticia_id = 4")
        ).fetchall()
        if imagens:
            for img in imagens:
                print(dict(img._mapping))
        else:
            print("(nenhum registro em imagens para noticia_id=4)")
    except Exception as e:
        print(f"(consulta falhou: {e})")

db.close()
