"""
corrigir_sessao_curta.py
Reescreve pipeline/gerar_noticias.py e app.py por completo para que o
pipeline de noticias nunca segure uma conexao de banco aberta durante
o trabalho lento de LLM (pesquisador -> editor -> revisor -> seo).

app.py: mudanca minima e aditiva -- so acrescenta o import, a classe
GerarNoticiaInput e o endpoint /noticias/gerar. NADA no /artigos/gerar
existente foi tocado.

Como usar:
  1. Copie este arquivo para dentro de ~/projetos/agente-ads
  2. Rode: python corrigir_sessao_curta.py
"""

import os
import subprocess
import sys
import py_compile


def sobrescrever(caminho, novo_conteudo, nome_mudanca):
    if not os.path.isfile(caminho):
        print(f"ERRO: nao encontrei o arquivo {caminho}.")
        print("Rode este script DE DENTRO da pasta do repositorio do agente.")
        sys.exit(1)

    with open(caminho, "r", encoding="utf-8") as f:
        atual = f.read()

    if atual == novo_conteudo:
        print(f"AVISO: {caminho} ja esta identico ao esperado. Nada a fazer.")
        return False

    with open(caminho, "w", encoding="utf-8") as f:
        f.write(novo_conteudo)
    print(f"OK: {caminho} reescrito ({nome_mudanca})")
    return True


if not os.path.isfile("app.py"):
    print("ERRO: rode este script DE DENTRO da pasta do repositorio do agente.")
    sys.exit(1)

print("Aplicando correcao...\n")

GERAR_NOTICIAS = '"""\npipeline/gerar_noticias.py — Orquestra o fluxo de NOTÍCIAS\n\npesquisador (RSS) → EditorChefe (dedup + score, sem LLM) → editor\n(reescreve) → revisor → seo → NoticiaRepository (tabela `noticias` —\nschema próprio, sem colunas de imagem, categoria é FK)\n\nReaproveitado tanto pela API (app.py, endpoint POST /noticias/gerar)\nquanto por um script de linha de comando (bloco __main__ abaixo).\n\nNÃO recebe `db` de fora. A função abre e fecha sessões CURTAS do banco\nsó nos momentos que realmente precisa dele (listar títulos existentes,\nchecar slug duplicado, salvar no final) — nunca durante o trabalho de\nLLM (pesquisador → editor → revisor → seo pode levar vários minutos\nnesta máquina). Isso evita o erro "SSL connection has been closed\nunexpectedly" que o Neon dispara em conexões ociosas por tempo demais.\n\nSem busca de imagem aqui: a tabela `noticias` não tem nenhuma coluna\npra isso hoje. Sem publicação no GitHub também — isso ainda depende de\ndecidir se faz sentido pra notícias (github_service.py hoje só sabe\nescrever em content/artigos/), então por enquanto "publicar" uma\nnotícia só muda o status no Neon.\n"""\n\nfrom contextlib import contextmanager\n\nfrom config.database import SessionLocal\nfrom agents import pesquisador, editor, revisor, seo\nfrom agents.editor_chefe import EditorChefe\nfrom repositories.noticia_repository import NoticiaRepository\n\n\n@contextmanager\ndef _sessao_curta():\n    db = SessionLocal()\n    try:\n        yield db\n    finally:\n        db.close()\n\n\ndef gerar_e_processar_noticia(\n    categoria: str = "Tecnologia",\n    max_tentativas: int = 3,\n    publicar_imediatamente: bool = False,\n) -> dict:\n    candidatos_brutos = pesquisador.pesquisar_noticias()\n    if not candidatos_brutos:\n        raise ValueError("Nenhuma notícia encontrada nos feeds RSS configurados")\n\n    with _sessao_curta() as db:\n        titulos_existentes = NoticiaRepository(db).listar_titulos_recentes(limite=100)\n\n    editor_chefe = EditorChefe()\n    pauta = editor_chefe.montar_pauta(candidatos_brutos, categoria, titulos_existentes=titulos_existentes)\n\n    if not pauta:\n        raise ValueError("Todas as notícias encontradas já foram publicadas ou são duplicadas entre si")\n\n    artigo = None\n    item_escolhido = None\n\n    for item in pauta[:max_tentativas]:\n        candidato_artigo = editor.gerar_noticia_base(\n            {"titulo": item.titulo, "resumo": item.resumo, "fonte": item.fonte, "link": item.link},\n            categoria=categoria,\n        )\n\n        with _sessao_curta() as db:\n            ja_existe = NoticiaRepository(db).buscar_por_slug(candidato_artigo["slug"])\n\n        if ja_existe:\n            print(f"[Pipeline] \'{item.titulo}\' já publicada (slug duplicado), tentando a próxima da pauta.")\n            continue\n\n        artigo = candidato_artigo\n        item_escolhido = item\n        break\n\n    if artigo is None:\n        raise ValueError("Todos os itens tentados da pauta já foram publicados antes")\n\n    artigo = revisor.revisar_artigo(artigo)\n    artigo = seo.otimizar_seo(artigo)\n\n    with _sessao_curta() as db:\n        repo = NoticiaRepository(db)\n        noticia_id = repo.criar(\n            slug=artigo["slug"],\n            titulo=artigo.get("titulo_seo") or artigo["titulo"],\n            categoria=categoria,\n            resumo=artigo.get("meta_description") or artigo.get("excerpt", ""),\n            conteudo=artigo["conteudo_markdown"],\n            fonte=item_escolhido.fonte,\n            url_fonte=item_escolhido.link,\n            status="rascunho",\n        )\n\n        resultado = {\n            "id": noticia_id,\n            "slug": artigo["slug"],\n            "titulo": artigo["titulo"],\n            "categoria": categoria,\n            "status": "rascunho",\n            "prioridade": item_escolhido.prioridade,\n            "score": item_escolhido.score,\n            "fonte_original": item_escolhido.link,\n        }\n\n        if publicar_imediatamente:\n            repo.publicar(noticia_id)\n            resultado["status"] = "publicado"\n\n    return resultado\n\n\nif __name__ == "__main__":\n    resultado = gerar_e_processar_noticia()\n    print(f"Notícia salva: {resultado}")\n'

APP_PY = 'import logging\nfrom fastapi import FastAPI, Depends, HTTPException\nfrom sqlalchemy.orm import Session\nfrom pydantic import BaseModel, Field\nfrom config.database import get_db\nfrom repositories.produto_repository import ProdutoRepository\nfrom repositories.artigo_repository import ArtigoRepository\nfrom services.llm_service import gerar_artigo\nfrom services.imagem_service import buscar_imagem_capa\nfrom pipeline.gerar_noticias import gerar_e_processar_noticia\n\nlogger = logging.getLogger("digitaltech")\nlogging.basicConfig(level=logging.INFO)\n\napp = FastAPI(\n    title="DigitalTech — Agente ADS",\n    description="API de produtos e agente de publicação de artigos — Michel Freitas",\n    version="2.2.0"\n)\n\nclass ProdutoInput(BaseModel):\n    nome: str = Field(..., min_length=2, max_length=100)\n    descricao: str = Field(default="")\n    preco: float = Field(..., gt=0)\n    estoque: int = Field(..., ge=0)\n\nclass GerarArtigoInput(BaseModel):\n    tema: str = Field(..., min_length=5, max_length=200, description="Tema do artigo a ser gerado")\n    categoria: str = Field(default="Tecnologia", description="Categoria do artigo no blog")\n    publicar_imediatamente: bool = Field(\n        default=False,\n        description="Se True, o artigo já entra como \'publicado\'. Se False, entra como \'rascunho\'."\n    )\n\nclass GerarNoticiaInput(BaseModel):\n    categoria: str = Field(default="Tecnologia", description="Categoria da notícia no blog")\n    publicar_imediatamente: bool = Field(\n        default=False,\n        description="Se True, já marca a notícia como \'publicado\'. Se False, entra como \'rascunho\'."\n    )\n\n@app.get("/health", tags=["Sistema"])\ndef health_check():\n    return {"status": "ok", "versao": "2.2.0", "projeto": "DigitalTech ADS"}\n\n@app.get("/produtos", tags=["Produtos"])\ndef listar_produtos(db: Session = Depends(get_db)):\n    repo = ProdutoRepository(db)\n    return {"produtos": [dict(p._mapping) for p in repo.listar_todos()]}\n\n@app.get("/produtos/{produto_id}", tags=["Produtos"])\ndef buscar_produto(produto_id: int, db: Session = Depends(get_db)):\n    repo = ProdutoRepository(db)\n    produto = repo.buscar_por_id(produto_id)\n    if not produto:\n        raise HTTPException(status_code=404, detail="Produto não encontrado")\n    return dict(produto._mapping)\n\n@app.post("/produtos", status_code=201, tags=["Produtos"])\ndef criar_produto(dados: ProdutoInput, db: Session = Depends(get_db)):\n    repo = ProdutoRepository(db)\n    repo.criar(dados.nome, dados.descricao, dados.preco, dados.estoque)\n    return {"mensagem": "Produto criado com sucesso"}\n\n@app.put("/produtos/{produto_id}", tags=["Produtos"])\ndef atualizar_produto(produto_id: int, dados: ProdutoInput, db: Session = Depends(get_db)):\n    repo = ProdutoRepository(db)\n    if not repo.buscar_por_id(produto_id):\n        raise HTTPException(status_code=404, detail="Produto não encontrado")\n    repo.atualizar(produto_id, dados.nome, dados.descricao, dados.preco, dados.estoque)\n    return {"mensagem": "Produto atualizado com sucesso"}\n\n@app.delete("/produtos/{produto_id}", tags=["Produtos"])\ndef deletar_produto(produto_id: int, db: Session = Depends(get_db)):\n    repo = ProdutoRepository(db)\n    if not repo.buscar_por_id(produto_id):\n        raise HTTPException(status_code=404, detail="Produto não encontrado")\n    repo.deletar(produto_id)\n    return {"mensagem": "Produto desativado com sucesso"}\n\n@app.post("/artigos/gerar", status_code=201, tags=["Agente de Artigos"])\ndef gerar_e_salvar_artigo(dados: GerarArtigoInput, db: Session = Depends(get_db)):\n    """Gera um artigo (Ollama → OpenAI → Claude → Gemini), busca imagem de capa e salva no Neon."""\n    try:\n        artigo = gerar_artigo(dados.tema, dados.categoria)\n    except Exception as exc:\n        logger.exception("Falha ao gerar artigo")\n        raise HTTPException(status_code=502, detail="Erro ao gerar artigo.") from exc\n\n    repo = ArtigoRepository(db)\n    if repo.buscar_por_slug(artigo["slug"]):\n        raise HTTPException(status_code=409, detail=f"Já existe um artigo com o slug \'{artigo[\'slug\']}\'")\n\n    categoria_id = repo.buscar_categoria_id(artigo["categoria"])\n    if categoria_id is None:\n        raise HTTPException(\n            status_code=422,\n            detail=f"Categoria \'{artigo[\'categoria\']}\' não existe no banco. Verifique o nome ou cadastre a categoria antes.",\n        )\n\n    status_inicial = "publicado" if dados.publicar_imediatamente else "rascunho"\n    imagem = buscar_imagem_capa(\n    titulo=artigo["titulo"],\n    tema=dados.tema,\n    categoria=dados.categoria)\n\n    artigo_id = repo.criar(\n        slug=artigo["slug"],\n        titulo=artigo["titulo"],\n        categoria_id=categoria_id,\n        resumo=artigo["excerpt"],\n        conteudo_markdown=artigo["conteudo_markdown"],\n        status=status_inicial,\n        imagem_url=imagem["imagem_url"] if imagem else None,\n        imagem_autor=imagem["imagem_autor"] if imagem else None,\n        imagem_link=imagem["imagem_link"] if imagem else None,\n    )\n\n    return {\n        "id": artigo_id,\n        "slug": artigo["slug"],\n        "titulo": artigo["titulo"],\n        "categoria": artigo["categoria"],\n        "categoria_id": categoria_id,\n        "status": status_inicial,\n        "imagem": imagem["imagem_url"] if imagem else None,\n        "mensagem": "Artigo gerado e salvo no banco Neon com sucesso.",\n    }\n\n@app.post("/artigos/publicar/{artigo_id}", tags=["Agente de Artigos"])\ndef publicar_artigo_existente(artigo_id: int, db: Session = Depends(get_db)):\n    """Muda um artigo salvo como \'rascunho\' para \'publicado\'."""\n    repo = ArtigoRepository(db)\n    artigo = repo.buscar_por_id(artigo_id)\n    if not artigo:\n        raise HTTPException(status_code=404, detail="Artigo não encontrado")\n    if artigo.status == "publicado":\n        raise HTTPException(status_code=409, detail="Artigo já está publicado")\n    repo.publicar(artigo_id)\n    return {"id": artigo_id, "slug": artigo.slug, "status": "publicado", "mensagem": "Artigo publicado com sucesso."}\n\n@app.post("/noticias/gerar", status_code=201, tags=["Agente de Notícias"])\ndef gerar_e_salvar_noticia(dados: GerarNoticiaInput):\n    """\n    Busca notícias recentes via RSS e roda a cadeia completa\n    (EditorChefe → editor → revisor → seo) para a notícia de maior\n    prioridade ainda não publicada. `noticias` é uma tabela própria no\n    banco, separada de `artigos`.\n    """\n    try:\n        resultado = gerar_e_processar_noticia(\n            categoria=dados.categoria,\n            publicar_imediatamente=dados.publicar_imediatamente,\n        )\n    except ValueError as exc:\n        raise HTTPException(status_code=409, detail=str(exc)) from exc\n    except Exception as exc:\n        logger.exception("Falha ao gerar notícia")\n        raise HTTPException(status_code=502, detail="Erro ao gerar notícia.") from exc\n\n    resultado["mensagem"] = "Notícia gerada e salva no banco Neon com sucesso."\n    return resultado\n\n@app.get("/artigos", tags=["Agente de Artigos"])\ndef listar_artigos(db: Session = Depends(get_db)):\n    repo = ArtigoRepository(db)\n    artigos = repo.listar_todos()\n    return {\n        "artigos": [\n            {\n                "id": a.id, "slug": a.slug, "titulo": a.titulo,\n                "categoria": a.categoria, "status": a.status,\n                "data_publicacao": str(a.data_publicacao) if a.data_publicacao else None,\n            }\n            for a in artigos\n        ]\n    }\n\n@app.get("/artigos/{artigo_id}", tags=["Agente de Artigos"])\ndef buscar_artigo(artigo_id: int, db: Session = Depends(get_db)):\n    repo = ArtigoRepository(db)\n    artigo = repo.buscar_por_id(artigo_id)\n    if not artigo:\n        raise HTTPException(status_code=404, detail="Artigo não encontrado")\n    return dict(artigo._mapping)\n'

sobrescrever("pipeline/gerar_noticias.py", GERAR_NOTICIAS, "sessoes curtas de banco, sem receber db")
sobrescrever("app.py", APP_PY, "adiciona endpoint /noticias/gerar (nao toca em /artigos/gerar)")

print("\nValidando sintaxe...")
py_compile.compile("pipeline/gerar_noticias.py", doraise=True)
py_compile.compile("app.py", doraise=True)
print("Sintaxe OK.")

print("\n===== DIFF (revise antes de continuar) =====")
subprocess.run(["git", "diff", "--stat", "pipeline/gerar_noticias.py", "app.py"])
subprocess.run(["git", "diff", "pipeline/gerar_noticias.py", "app.py"])
print("=============================================\n")

resultado_status = subprocess.run(
    ["git", "status", "--short", "pipeline/gerar_noticias.py", "app.py"],
    capture_output=True, text=True,
)
if not resultado_status.stdout.strip():
    print("Nenhuma mudanca detectada pelo git -- os arquivos ja estavam corretos. Nada a commitar.")
    sys.exit(0)

confirmacao = input(
    "As mudancas acima estao corretas? Digite \'sim\' para commitar, "
    "ou qualquer outra tecla para cancelar: "
)

if confirmacao.strip().lower() != "sim":
    print("Cancelado. Nenhum commit foi feito.")
    sys.exit(0)

subprocess.run(["git", "add", "pipeline/gerar_noticias.py", "app.py"], check=True)
mensagem = (
    "fix: sessoes curtas de banco no pipeline de noticias\n\n"
    "gerar_e_processar_noticia() nao recebe mais db -- abre e fecha\n"
    "sessoes curtas do banco so nos momentos que precisa dele (listar\n"
    "titulos, checar slug, salvar), nunca durante pesquisador/editor/\n"
    "revisor/seo, que juntos podem levar minutos com LLM local. Isso\n"
    "evita o SSL connection has been closed unexpectedly do Neon.\n"
    "app.py: endpoint /noticias/gerar criado (nao existia). Mudanca\n"
    "aditiva -- /artigos/gerar continua exatamente como estava."
)
subprocess.run(["git", "commit", "-m", mensagem], check=True)

print("\nCommit feito. Para enviar ao GitHub, rode:")
print("  git push origin main")
print("\nDepois, teste com:")
print("  python -m pipeline.gerar_noticias")
