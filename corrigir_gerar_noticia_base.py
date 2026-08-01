"""
corrigir_gerar_noticia_base.py
Adiciona a função gerar_noticia_base() em agents/editor.py, que
pipeline/gerar_noticias.py já chama mas que nunca existiu -- causaria
AttributeError na primeira tentativa de gerar uma notícia.

Como usar:
  1. Copie este arquivo para dentro de ~/projetos/agente-ads
  2. Rode: python corrigir_gerar_noticia_base.py
"""

import os
import subprocess
import sys
import py_compile


def aplicar(caminho, antigo, novo, nome_mudanca):
    if not os.path.isfile(caminho):
        print(f"ERRO: não encontrei o arquivo {caminho}.")
        print("Rode este script DE DENTRO da pasta do repositório do agente.")
        sys.exit(1)

    with open(caminho, "r", encoding="utf-8") as f:
        conteudo = f.read()

    ocorrencias = conteudo.count(antigo)
    if ocorrencias == 0:
        print(f"AVISO: trecho de '{nome_mudanca}' não encontrado em {caminho}.")
        print("Pode já ter sido aplicado antes, ou o arquivo mudou. Pulei esta edição.")
        return False
    if ocorrencias > 1:
        print(f"ERRO: trecho de '{nome_mudanca}' aparece {ocorrencias} vezes em {caminho}.")
        print("Edição abortada para não aplicar no lugar errado. Revise manualmente.")
        sys.exit(1)

    conteudo = conteudo.replace(antigo, novo)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    print(f"OK: '{nome_mudanca}' aplicado em {caminho}")
    return True


if not os.path.isfile("app.py"):
    print("ERRO: rode este script DE DENTRO da pasta do repositório do agente.")
    sys.exit(1)

print("Aplicando correção...\n")

ANTIGO = '''"""
editor.py -- Agente redator

Recebe o tema (e, opcionalmente, o briefing do pesquisador.py) e
escreve o artigo completo, reaproveitando o fallback chain de
services.llm_service.gerar_artigo(). Devolve o mesmo formato de dict
usado pelo resto do pipeline (slug, titulo, categoria, excerpt,
readTime, conteudo_markdown, data, provedor).
"""

from services.llm_service import gerar_artigo as _gerar_artigo_llm


def gerar_artigo_base(tema: str, categoria: str, briefing: dict | None = None) -> dict:
    """
    Gera o artigo completo. `briefing` (opcional) vem de
    pesquisador.pesquisar_tema() -- hoje ainda nao e injetado no
    prompt (services.llm_service.gerar_artigo nao aceita briefing
    ainda); o parametro existe para nao quebrar a assinatura chamada
    por pipeline/gerar_artigos.py, e fica pronto pra ser usado assim
    que o prompt for ajustado para aproveita-lo.
    """
    return _gerar_artigo_llm(tema, categoria)'''

NOVO = '''"""
editor.py -- Agente redator

Duas responsabilidades, uma por fluxo de conteúdo:

- gerar_artigo_base(): para ARTIGOS evergreen. Reaproveita o fallback
  chain de services.llm_service.gerar_artigo() (que já sabe montar
  prompt, tentar os 4 provedores e fazer o parsing).

- gerar_noticia_base(): para NOTÍCIAS. Recebe o material bruto do
  pesquisador (título, resumo, fonte, link vindos de RSS) e REESCREVE
  em texto original via gerar_texto() -- nunca copia o corpo da fonte
  original, só usa como referência factual.

Ambas devolvem o mesmo formato de dict (slug, titulo, categoria,
excerpt, conteudo_markdown), pra revisor.py e seo.py funcionarem sem
precisar saber qual dos dois fluxos gerou o artigo.
"""

import re
import unicodedata

from services.llm_service import gerar_artigo as _gerar_artigo_llm
from services.llm_service import gerar_texto


def gerar_artigo_base(tema: str, categoria: str, briefing: dict | None = None) -> dict:
    """
    Gera o artigo completo. `briefing` (opcional) vem de
    pesquisador.pesquisar_tema() -- hoje ainda nao e injetado no
    prompt (services.llm_service.gerar_artigo nao aceita briefing
    ainda); o parametro existe para nao quebrar a assinatura chamada
    por pipeline/gerar_artigos.py, e fica pronto pra ser usado assim
    que o prompt for ajustado para aproveita-lo.
    """
    return _gerar_artigo_llm(tema, categoria)


def gerar_noticia_base(fonte: dict, categoria: str) -> dict:
    """
    Reescreve uma notícia a partir do material bruto do pesquisador
    (fonte = {"titulo", "resumo", "fonte", "link"} vindos do RSS) em
    texto próprio -- nunca copia frases da fonte original, só usa como
    referência factual. Devolve o mesmo formato de dict usado pelo
    resto do pipeline (slug, titulo, categoria, excerpt,
    conteudo_markdown).
    """
    prompt = f"""Você é um jornalista de tecnologia brasileiro.

Com base SOMENTE nestas informações de uma notícia (nunca copie
frases da fonte -- escreva com suas próprias palavras):

Título original: {fonte['titulo']}
Resumo original: {fonte['resumo']}
Fonte: {fonte['fonte']}

Escreva uma notícia original em português, em Markdown, sobre esse
fato, categoria "{categoria}". Entre 250 e 400 palavras.

Responda EXATAMENTE neste formato de texto simples -- NÃO use JSON e
NÃO use blocos de código (```) envolvendo a resposta:

TITULO: título da notícia aqui, em uma linha
RESUMO: resumo de uma linha, no máximo 120 caracteres
===CORPO===
o texto completo da notícia em markdown vai aqui
"""
    texto = gerar_texto(prompt)
    dados = _parsear_noticia(texto)

    return {
        "slug": _gerar_slug(dados["titulo"]),
        "titulo": dados["titulo"],
        "categoria": categoria,
        "excerpt": dados["excerpt"],
        "conteudo_markdown": dados["corpo"],
    }


def _remover_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _gerar_slug(titulo: str) -> str:
    slug = unicodedata.normalize("NFD", titulo.lower())
    slug = slug.encode("ascii", "ignore").decode("utf-8")
    slug = re.sub(r"[^a-z0-9\\s-]", "", slug)
    slug = re.sub(r"\\s+", "-", slug.strip())
    return re.sub(r"-+", "-", slug)[:80]


def _parsear_noticia(texto: str) -> dict:
    """
    Mesma lógica de parsing de services.llm_service._parsear_resposta,
    duplicada aqui de propósito (versão simplificada, sem
    TEMPO_LEITURA) pra editor.py não depender de função privada de
    outro módulo. Se um dia isso incomodar, dá pra extrair pra um
    lugar compartilhado -- não é urgente agora.
    """
    texto = texto.strip()
    texto = re.sub(r"^```[a-zA-Z]*\\n?", "", texto)
    texto = re.sub(r"\\n?```$", "", texto)

    linhas = texto.splitlines()
    titulo = None
    excerpt = ""
    indice_corpo = len(linhas)

    for i, linha_original in enumerate(linhas):
        linha = linha_original.strip()
        if not linha:
            continue
        if linha == "===CORPO===":
            indice_corpo = i + 1
            break

        linha_normalizada = _remover_acentos(linha).upper()
        if linha_normalizada.startswith("TITULO:"):
            titulo = linha.split(":", 1)[1].strip()
            continue
        if linha_normalizada.startswith("RESUMO:"):
            excerpt = linha.split(":", 1)[1].strip()
            continue

        indice_corpo = i
        break

    corpo = "\\n".join(linhas[indice_corpo:]).strip()

    if not titulo or not corpo:
        raise ValueError("Resposta incompleta do modelo (faltou título ou corpo) ao gerar notícia")

    return {"titulo": titulo, "excerpt": excerpt, "corpo": corpo}'''

aplicar("agents/editor.py", ANTIGO, NOVO, "adicionar gerar_noticia_base()")

print("\nValidando sintaxe...")
py_compile.compile("agents/editor.py", doraise=True)
print("Sintaxe OK.")

print("\n===== DIFF (revise antes de continuar) =====")
subprocess.run(["git", "diff", "agents/editor.py"])
print("=============================================\n")

confirmacao = input(
    "As mudanças acima estão corretas? Digite 'sim' para commitar, "
    "ou qualquer outra tecla para cancelar: "
)

if confirmacao.strip().lower() != "sim":
    print("Cancelado. Nenhum commit foi feito.")
    sys.exit(0)

subprocess.run(["git", "add", "agents/editor.py"], check=True)
mensagem = (
    "fix: adiciona gerar_noticia_base() em editor.py\n\n"
    "pipeline/gerar_noticias.py já chamava editor.gerar_noticia_base(),\n"
    "mas essa função nunca existia -- causava AttributeError na primeira\n"
    "tentativa de gerar uma notícia. Reescreve o material bruto do RSS\n"
    "(titulo/resumo/fonte/link) em texto próprio via gerar_texto(),\n"
    "nunca copiando o corpo da fonte original, no mesmo formato de dict\n"
    "usado por gerar_artigo_base()."
)
subprocess.run(["git", "commit", "-m", mensagem], check=True)

print("\nCommit feito. Para enviar ao GitHub, rode:")
print("  git push origin main")
print("\nDepois, teste com:")
print("  python -m pipeline.gerar_noticias")
