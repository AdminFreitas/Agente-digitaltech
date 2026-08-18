"""
Modelo de dados do Agente Digital Tech
Baseado nos campos consumidos pelo index.html
"""
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, JSON, 
    create_engine, func
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class Conteudo(Base):
    __tablename__ = "conteudos"

    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String(20), nullable=False, index=True)      # artigo | noticia
    status = Column(String(20), default="rascunho", index=True) # rascunho | revisao | publicado | rejeitado
    titulo = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, index=True)
    resumo = Column(Text)
    conteudo = Column(Text)        # Markdown
    categoria = Column(String(100))
    tags = Column(JSON, default=list)
    autor = Column(String(100), default="Agente IA")
    imagem_url = Column(String(500))
    seo_title = Column(String(60))
    seo_description = Column(String(160))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

# --- Setup do banco (SQLite para começar; troque por PostgreSQL em prod) ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./agente_digital.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        