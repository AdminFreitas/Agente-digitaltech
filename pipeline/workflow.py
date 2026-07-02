from pipeline.gerar_artigos import gerar_artigo

def main():
    tema = "Como usar índices no PostgreSQL para melhorar performance"
    categoria = "Banco de Dados"
    gerar_artigo(tema, categoria)

if __name__ == "__main__":
    main()
