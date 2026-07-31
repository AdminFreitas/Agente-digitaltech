"""
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
    return _gerar_artigo_llm(tema, categoria)
