"""
pipeline/gerar_noticias.py — Orquestra o fluxo de NOTÍCIAS

pesquisador (RSS) → EditorChefe (dedup + score, sem LLM) → editor
(reescreve) → revisor → seo → extração de og:image → NoticiaRepository
(tabela `noticias` + tabela `imagens`)

Reaproveitado tanto pela API (app.py, endpoint POST /noticias/gerar)
quanto por um script de linha de comando (bloco __main__ abaixo).

NÃO recebe `db` de fora. A função abre e fecha sessões CURTAS do banco
só nos momentos que realmente precisa dele (listar títulos existentes,
checar slug duplicado, salvar no final) — nunca durante o trabalho de
LLM (pesquisador → editor → revisor → seo pode levar vários minutos
nesta máquina) nem durante o download da matéria original para extrair
a imagem. Isso evita o erro "SSL connection has been closed
unexpectedly" que o Neon dispara em conexões ociosas por tempo demais.

Imagem: extraída da og:image da matéria original (nunca Unsplash/
Pexels/IA genérica para notícias) e gravada em dois lugares pelo
NoticiaRepository — tabela `imagens` (o que o site consulta pra
renderizar) e colunas `imagem_*` de `noticias` (metadados de
atribuição/auditoria). Se a extração falhar por qualquer motivo, a
notícia é salva mesmo assim, só sem imagem — isso nunca bloqueia a
publicação.
"""

import re
from contextlib import contextmanager

import requests

from config.database import SessionLocal
from agents import pesquisador, editor, revisor, seo
from agents.editor_chefe import EditorChefe
from repositories.noticia_repository import NoticiaRepository
from services.github_service import publicar_noticia

TIMEOUT_DOWNLOAD_IMAGEM = 10  # segundos
USER_AGENT_DOWNLOAD = "Mozilla/5.0 (compatible; DigitalTechBot/1.0; +https://www.digitaltech.digital/)"

_REGEX_OG_IMAGE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_REGEX_OG_IMAGE_INVERTIDO = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']',
    re.IGNORECASE,
)
_REGEX_OG_IMAGE_ALT = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:image:alt["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


@contextmanager
def _sessao_curta():
    """
    Abre uma sessão do banco só pelo tempo de UMA operação rápida, e
    fecha em seguida. Nunca fica aberta durante o trabalho lento do
    LLM — é exatamente isso que causava o SSL connection has been
    closed unexpectedly: a sessão ficava ociosa minutos demais entre
    duas operações de banco, com toda a geração/revisão/SEO no meio.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _extrair_imagem_og(url_materia: str) -> dict | None:
    """
    Baixa o HTML da matéria original e extrai a imagem de capa via meta
    tag Open Graph (og:image). Retorna um dict pronto pra passar como
    **kwargs pro NoticiaRepository.criar(), ou None se falhar/não
    encontrar — NUNCA levanta exceção, pra não travar a geração da
    notícia inteira por causa de uma imagem que não carregou.
    """
    try:
        resposta = requests.get(
            url_materia,
            timeout=TIMEOUT_DOWNLOAD_IMAGEM,
            headers={"User-Agent": USER_AGENT_DOWNLOAD},
        )
        resposta.raise_for_status()
        html = resposta.text
    except Exception as erro:
        print(f"[Pipeline] Falha ao baixar '{url_materia}' para extrair imagem: {erro}")
        return None

    match_imagem = _REGEX_OG_IMAGE.search(html) or _REGEX_OG_IMAGE_INVERTIDO.search(html)
    if not match_imagem:
        print(f"[Pipeline] Nenhuma og:image encontrada em '{url_materia}'.")
        return None

    imagem_url = match_imagem.group(1)
    match_alt = _REGEX_OG_IMAGE_ALT.search(html)

    return {
        "imagem_url": imagem_url,
        "imagem_original_url": imagem_url,
        "imagem_alt": match_alt.group(1) if match_alt else None,
        "imagem_fonte": "og:image",
        "imagem_autor": None,
        "imagem_link": url_materia,
        "imagem_query": None,
    }


def gerar_e_processar_noticia(
    categoria: str = "Tecnologia",
    max_tentativas: int = 3,
    publicar_imediatamente: bool = False,
) -> dict:
    """
    Busca notícias recentes via RSS, usa o EditorChefe pra descartar
    duplicadas (entre os candidatos e contra o que já está salvo em
    `noticias`) e priorizar, e roda a cadeia completa para o item de
    maior prioridade que ainda não tenha sido publicado (checagem por
    slug, feita DEPOIS de gerar o texto — o slug final depende do
    título que o editor.py produz). Tenta até `max_tentativas` itens da
    pauta antes de desistir.

    Levanta ValueError se não houver nenhuma notícia nos feeds, se o
    EditorChefe descartar tudo por duplicidade, ou se todos os
    candidatos tentados já tiverem sido publicados antes.
    """
    candidatos_brutos = pesquisador.pesquisar_noticias()
    if not candidatos_brutos:
        raise ValueError("Nenhuma notícia encontrada nos feeds RSS configurados")

    with _sessao_curta() as db:
        titulos_existentes = NoticiaRepository(db).listar_titulos_recentes(limite=100)

    editor_chefe = EditorChefe()
    pauta = editor_chefe.montar_pauta(candidatos_brutos, categoria, titulos_existentes=titulos_existentes)

    if not pauta:
        raise ValueError("Todas as notícias encontradas já foram publicadas ou são duplicadas entre si")

    artigo = None
    item_escolhido = None

    for item in pauta[:max_tentativas]:
        # ↓ chamada lenta ao LLM — nenhuma sessão de banco aberta aqui
        candidato_artigo = editor.gerar_noticia_base(
            {"titulo": item.titulo, "resumo": item.resumo, "fonte": item.fonte, "link": item.link},
            categoria=categoria,
        )

        with _sessao_curta() as db:
            ja_existe = NoticiaRepository(db).buscar_por_slug(candidato_artigo["slug"])

        if ja_existe:
            print(f"[Pipeline] '{item.titulo}' já publicada (slug duplicado), tentando a próxima da pauta.")
            continue

        artigo = candidato_artigo
        item_escolhido = item
        break

    if artigo is None:
        raise ValueError("Todos os itens tentados da pauta já foram publicados antes")

    # ↓ mais duas chamadas lentas ao LLM — ainda sem sessão de banco aberta
    artigo = revisor.revisar_artigo(artigo)
    artigo = seo.otimizar_seo(artigo)

    # ↓ download da matéria original pra extrair a og:image — também
    # sem sessão de banco aberta. Se falhar, dados_imagem fica {} e a
    # notícia é salva normalmente, só sem imagem.
    dados_imagem = _extrair_imagem_og(item_escolhido.link) or {}
    if dados_imagem and not dados_imagem.get("imagem_alt"):
        dados_imagem["imagem_alt"] = artigo.get("titulo_seo") or artigo["titulo"]

    # ATENÇÃO — suposições que precisam de confirmação:
    # 1) rss_guid: pesquisador.py monta os itens da pauta, mas eu não vi
    #    esse arquivo, então não sei se o item tem um campo `guid` de
    #    verdade (RSS feeds normalmente expõem <guid> por item). Uso
    #    getattr com fallback None -- se o atributo tiver outro nome,
    #    ajuste a linha abaixo.
    rss_guid = getattr(item_escolhido, "guid", None)

    # 2) provedor_llm / modelo_llm / tempo_geracao_ms: eu não vi o módulo
    #    que imprime "[LLM] (gerar_texto) Tentando Ollama local..." nem
    #    sei se editor.gerar_noticia_base() devolve essa informação
    #    dentro do dict `artigo`. Uso .get() com None como fallback --
    #    se esses dados vierem de outro lugar (ex.: um dict separado
    #    retornado por editor.py), me mostre esse arquivo que eu ajusto.
    provedor_llm = artigo.get("provedor_llm")
    modelo_llm = artigo.get("modelo_llm")
    tempo_geracao_ms = artigo.get("tempo_geracao_ms")

    with _sessao_curta() as db:
        repo = NoticiaRepository(db)
        noticia_id = repo.criar(
            slug=artigo["slug"],
            titulo=artigo.get("titulo_seo") or artigo["titulo"],
            categoria=categoria,
            resumo=artigo.get("meta_description") or artigo.get("excerpt", ""),
            conteudo=artigo["conteudo_markdown"],
            fonte=item_escolhido.fonte,
            url_fonte=item_escolhido.link,
            status="rascunho",
            rss_guid=rss_guid,
            provedor_llm=provedor_llm,
            modelo_llm=modelo_llm,
            tempo_geracao_ms=tempo_geracao_ms,
            **dados_imagem,
        )

        resultado = {
            "id": noticia_id,
            "slug": artigo["slug"],
            "titulo": artigo["titulo"],
            "categoria": categoria,
            "status": "rascunho",
            "prioridade": item_escolhido.prioridade,
            "score": item_escolhido.score,
            "fonte_original": item_escolhido.link,
            "imagem_encontrada": bool(dados_imagem),
        }

    # Publica no GitHub DEPOIS de fechar a sessão do banco.
    # A chamada de rede não deve segurar uma conexão do Neon aberta.
    if publicar_imediatamente:
        try:
            resultado_github = publicar_noticia(
                slug=artigo["slug"],
                conteudo_markdown=artigo["conteudo_markdown"],
                titulo=artigo.get("titulo_seo") or artigo["titulo"],
            )
        except Exception as e:
            print(f"[Pipeline] FALHA ao publicar notícia no GitHub: {e}")
        else:
            # A publicação no GitHub já foi confirmada.
            # O status no Neon não depende de um deploy separado.
            repo.publicar(noticia_id)
            resultado["status"] = "publicado"

    return resultado


if __name__ == "__main__":
    resultado = gerar_e_processar_noticia()
    print(f"Notícia salva: {resultado}")