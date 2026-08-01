from config.database import SessionLocal
from pipeline.gerar_artigos import gerar_e_processar_artigo

db = SessionLocal()
resultado = gerar_e_processar_artigo(
    db=db,
    tema="Cabeamento estruturado de rede de internet",
    categoria="Tecnologia",
)
print("Artigo criado:", resultado)
db.close()
