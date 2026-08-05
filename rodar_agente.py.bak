#!/usr/bin/env python3
"""
rodar_agente.py — CLI unificado do Agente DigitalTech (CORRIGIDO v4.1)

Correções desta versão:
- v4: _gerar_artigo() passa 'categoria' para sugerir_tema(), não passa 'db'
  para gerar_e_processar_artigo() (ela abre sessões curtas internamente)
- v4: main() retorna exit code 1 se qualquer pipeline falhar
- v4: _publicar_pendentes() retorna True/False
- v4.1: publicação de notícias volta a usar NoticiaRepository.publicar()
  (não SQL cru — evita chutar nome de coluna e respeita lógica do repo)

Uso:
    python rodar_agente.py --artigos --sem-publicar
    python rodar_agente.py --noticias
    python rodar_agente.py --pipeline-completo
    python rodar_agente.py --diagnostico
    python rodar_agente.py --status
"""

import argparse
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.llm_service import (
    _tentar_ollama,
    _tentar_openai,
    _tentar_claude,
    _tentar_gemini,
    OPENAI_KEY,
    ANTHROPIC_KEY,
    GEMINI_KEY,
    OLLAMA_URL,
    OLLAMA_MODEL,
)


def _timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str):
    print(f"[{_timestamp()}] {msg}")


def _banner(texto: str):
    _log("=" * 60)
    _log(texto)
    _log("=" * 60)


# ---------------------------------------------------------------------------
# DIAGNÓSTICO
# ---------------------------------------------------------------------------

def _diagnostico_ollama():
    import httpx
    _log("[1/5] Verificando Ollama...")
    print(f"  URL: {OLLAMA_URL}")
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        servidor_ok = resp.status_code == 200
    except Exception as e:
        print(f"  Servidor acessível: ❌ NÃO ({e})")
        return False

    print(f"  Servidor acessível: {'✅ SIM' if servidor_ok else '❌ NÃO'}")
    if not servidor_ok:
        return False

    print(f"  Modelo configurado: {OLLAMA_MODEL}")
    modelos = resp.json().get("models", [])
    nomes = [m.get("name", m.get("model", "?")) for m in modelos]
    disponivel = any(OLLAMA_MODEL in n for n in nomes)
    print(f"  Modelo disponível: {'✅ SIM' if disponivel else '❌ NÃO'}")
    print(f"  Modelos instalados: {', '.join(nomes[:10])}")
    if not disponivel:
        return False

    _log("[2/5] Teste rápido Ollama (prompt simples)...")
    inicio = time.monotonic()
    try:
        resposta = _tentar_ollama("Responda apenas a palavra TESTE. Nada mais.")
        tempo = (time.monotonic() - inicio) * 1000
        print(f"  Resultado: ✅ OK")
        print(f"  Resposta: '{resposta.strip()[:50]}'")
        print(f"  Tempo: {tempo:.0f}ms")
        return True
    except Exception as e:
        tempo = (time.monotonic() - inicio) * 1000
        print(f"  Resultado: ❌ FALHA após {tempo:.0f}ms")
        print(f"  Erro: {e}")
        return False


def _diagnostico_apis():
    _log("[3/5] Verificando APIs externas...")
    provedores = [
        ("OpenAI GPT-4o-mini", OPENAI_KEY, _tentar_openai),
        ("Claude Haiku", ANTHROPIC_KEY, _tentar_claude),
        ("Gemini 3.6 Flash", GEMINI_KEY, _tentar_gemini),
    ]
    resultados = {}
    for nome, chave, funcao in provedores:
        if not chave:
            print(f"  {nome}: ⚠️  CHAVE AUSENTE no .env")
            resultados[nome] = {"ok": False, "erro": "Chave não configurada"}
            continue
        inicio = time.monotonic()
        try:
            resposta = funcao("Responda apenas PONG.")
            tempo = time.monotonic() - inicio
            print(f"  {nome}: ✅ OK ({tempo:.1f}s)")
            resultados[nome] = {"ok": True, "tempo": tempo}
        except Exception as e:
            tempo = time.monotonic() - inicio
            erro = str(e)[:200]
            print(f"  {nome}: ❌ FALHA ({tempo:.1f}s)")
            print(f"    → {erro}")
            resultados[nome] = {"ok": False, "erro": erro}
    return resultados


def _diagnostico_banco():
    from config.database import SessionLocal
    from sqlalchemy import text
    _log("[4/5] Verificando banco de dados...")
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1")).fetchone()
        db.close()
        print(f"  Conexão: ✅ OK")
        return True
    except Exception as e:
        print(f"  Conexão: ❌ FALHA — {e}")
        return False


def _diagnostico_github():
    _log("[5/5] Verificando GitHub...")
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print(f"  Token: ⚠️  AUSENTE no .env")
        return False
    import httpx
    try:
        resp = httpx.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            login = resp.json().get("login", "?")
            print(f"  Token: ✅ OK (usuário: {login})")
            return True
        else:
            print(f"  Token: ❌ INVÁLIDO (HTTP {resp.status_code})")
            return False
    except Exception as e:
        print(f"  Token: ❌ ERRO — {e}")
        return False


def _mostrar_diagnostico():
    _banner("DIAGNÓSTICO DO AGENTE DIGITALTECH")
    ollama_ok = _diagnostico_ollama()
    apis = _diagnostico_apis()
    banco_ok = _diagnostico_banco()
    github_ok = _diagnostico_github()

    _banner("RESUMO DO DIAGNÓSTICO")
    print(f"  Ollama:     {'✅ OK' if ollama_ok else '❌ FALHA'}")
    for nome, dados in apis.items():
        status = "✅ OK" if dados.get("ok") else "❌ FALHA"
        extra = f" ({dados.get('tempo', 0):.1f}s)" if dados.get("ok") else ""
        print(f"  {nome:<25} {status}{extra}")
    print(f"  Banco:      {'✅ OK' if banco_ok else '❌ FALHA'}")
    print(f"  GitHub:     {'✅ OK' if github_ok else '⚠️  NÃO CONFIGURADO'}")

    funcionais = [n for n, d in apis.items() if d.get("ok")]
    if ollama_ok or funcionais:
        print(f"\n  ✅ Pelo menos 1 provedor LLM funcional. Pipeline pode rodar.")
    else:
        print(f"\n  ❌ Nenhum provedor LLM funcional. Verifique Ollama, chaves e quotas.")


# ---------------------------------------------------------------------------
# STATUS DO BANCO
# ---------------------------------------------------------------------------

def _mostrar_status():
    from config.database import SessionLocal
    from sqlalchemy import text
    _banner("STATUS DO AGENTE DIGITALTECH")
    try:
        db = SessionLocal()
        artigos = db.execute(text("SELECT status, COUNT(*) as total FROM artigos GROUP BY status")).fetchall()
        print("  Artigos:")
        if artigos:
            for row in artigos:
                print(f"    {row.status}: {row.total}")
        else:
            print("    Nenhum artigo encontrado")

        noticias = db.execute(text("SELECT status, COUNT(*) as total FROM noticias GROUP BY status")).fetchall()
        print("  Notícias:")
        if noticias:
            for row in noticias:
                print(f"    {row.status}: {row.total}")
        else:
            print("    Nenhuma notícia encontrada")

        print("\n  Últimos artigos:")
        for a in db.execute(text("SELECT slug, titulo, status, criado_em FROM artigos ORDER BY criado_em DESC LIMIT 3")).fetchall():
            print(f"    [{a.status}] {a.titulo[:50]}... ({a.criado_em})")

        print("\n  Últimas notícias:")
        for n in db.execute(text("SELECT slug, titulo, status, criado_em FROM noticias ORDER BY criado_em DESC LIMIT 3")).fetchall():
            print(f"    [{n.status}] {n.titulo[:50]}... ({n.criado_em})")

        db.close()
    except Exception as e:
        print(f"  ❌ Erro ao consultar banco: {e}")


# ---------------------------------------------------------------------------
# PIPELINE DE ARTIGOS
# ---------------------------------------------------------------------------

def _gerar_artigo(publicar: bool = False):
    from agents import pesquisador
    from pipeline.gerar_artigos import gerar_e_processar_artigo

    _banner("INICIANDO GERAÇÃO DE ARTIGO")

    categoria = "Tecnologia"
    tema = pesquisador.sugerir_tema(categoria=categoria)
    _log(f"Tema sugerido ({categoria}): {tema}")

    try:
        resultado = gerar_e_processar_artigo(
            tema=tema,
            categoria=categoria,
            publicar_imediatamente=publicar,
        )
        _log(f"✅ Artigo salvo: ID={resultado['id']} | slug={resultado['slug']}")
        _log(f"   Título: {resultado['titulo']}")
        _log(f"   Status: {resultado['status']}")
        if resultado.get("github_url"):
            _log(f"   GitHub: {resultado['github_url']}")
        return True
    except ValueError as exc:
        _log(f"⚠️  {exc}")
        return False
    except Exception as exc:
        _log(f"❌ Erro ao gerar artigo: {exc}")
        return False


# ---------------------------------------------------------------------------
# PIPELINE DE NOTÍCIAS
# ---------------------------------------------------------------------------

def _gerar_noticia(publicar: bool = False):
    from pipeline.gerar_noticias import gerar_e_processar_noticia
    _banner("INICIANDO GERAÇÃO DE NOTÍCIA")
    try:
        resultado = gerar_e_processar_noticia(
            categoria="Tecnologia",
            publicar_imediatamente=publicar,
        )
        _log(f"✅ Notícia salva: ID={resultado['id']} | slug={resultado['slug']}")
        _log(f"   Título: {resultado['titulo']}")
        _log(f"   Status: {resultado['status']}")
        _log(f"   Fonte: {resultado.get('fonte_original', 'N/A')}")
        return True
    except ValueError as exc:
        _log(f"⚠️  {exc}")
        return False
    except Exception as exc:
        _log(f"❌ Erro ao gerar notícia: {exc}")
        return False


# ---------------------------------------------------------------------------
# PUBLICAR PENDENTES (v4.1 — usa NoticiaRepository.publicar())
# ---------------------------------------------------------------------------

def _publicar_pendentes():
    from agents import publisher
    from repositories.artigo_repository import ArtigoRepository
    from repositories.noticia_repository import NoticiaRepository
    from config.database import SessionLocal
    from sqlalchemy import text

    _banner("PUBLICANDO RASCUNHOS PENDENTES")

    db = SessionLocal()
    publicados = 0
    falhas = 0
    try:
        # Artigos pendentes
        pendentes_artigos = db.execute(text(
            "SELECT id, slug, titulo FROM artigos WHERE status = 'rascunho'"
        )).fetchall()

        for artigo in pendentes_artigos:
            try:
                publisher.publicar(db, artigo.id)
                _log(f"✅ Publicado artigo: {artigo.titulo[:50]}")
                publicados += 1
            except Exception as e:
                _log(f"❌ Falha ao publicar artigo {artigo.id}: {e}")
                falhas += 1

        # Notícias pendentes — CORREÇÃO v4.1: volta a usar NoticiaRepository
        noticias_repo = NoticiaRepository(db)
        pendentes_noticias = db.execute(text(
            "SELECT id, slug, titulo FROM noticias WHERE status = 'rascunho'"
        )).fetchall()

        for noticia in pendentes_noticias:
            try:
                noticias_repo.publicar(noticia.id)
                _log(f"✅ Publicada notícia: {noticia.titulo[:50]}")
                publicados += 1
            except Exception as e:
                _log(f"❌ Falha ao publicar notícia {noticia.id}: {e}")
                falhas += 1

        if publicados == 0 and falhas == 0:
            _log("Nenhum rascunho pendente encontrado.")
            return True
        elif falhas > 0:
            _log(f"Total: {publicados} publicados, {falhas} falhas")
            return False
        else:
            _log(f"Total publicado: {publicados}")
            return True
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AGENDAMENTO
# ---------------------------------------------------------------------------

def _mostrar_agendamento():
    _banner("AGENDAMENTO VIA CRON")
    print("""
  Adicione ao crontab do usuário:

    crontab -e

  Exemplos:

  # A cada 6 horas (artigo + notícia, sem publicar)
  0 */6 * * * cd ~/projetos/agente-ads && /usr/bin/python3 rodar_agente.py --executar --sem-publicar >> logs/agente.log 2>&1

  # A cada 2 horas (só notícias)
  0 */2 * * * cd ~/projetos/agente-ads && /usr/bin/python3 rodar_agente.py --noticias >> logs/noticias.log 2>&1

  # Uma vez por dia (pipeline completo com publicação)
  0 9 * * * cd ~/projetos/agente-ads && /usr/bin/python3 rodar_agente.py --pipeline-completo >> logs/pipeline.log 2>&1

  # Verifique se o diretório logs/ existe:
    mkdir -p ~/projetos/agente-ads/logs
""")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Agente DigitalTech — Geração autônoma de artigos e notícias",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Exemplos:
  python rodar_agente.py --executar              # Pipeline padrão
  python rodar_agente.py --pipeline-completo     # Tudo + publicação
  python rodar_agente.py --artigos --noticias    # Mesmo que --pipeline-completo
  python rodar_agente.py --diagnostico           # Verifica saúde do sistema
  python rodar_agente.py --status                # Mostra resumo do banco
""",
    )
    parser.add_argument("--executar", action="store_true", help="Executa artigo + notícia (padrão)")
    parser.add_argument("--agendar", action="store_true", help="Mostra instruções de agendamento via cron")
    parser.add_argument("--noticias", action="store_true", help="Gera apenas notícias via RSS")
    parser.add_argument("--artigos", action="store_true", help="Gera apenas artigos evergreen")
    parser.add_argument("--publicar", action="store_true", help="Publica rascunhos pendentes no GitHub")
    parser.add_argument("--pipeline-completo", action="store_true", help="Artigo + notícia + publicação de pendentes")
    parser.add_argument("--diagnostico", action="store_true", help="Diagnóstico completo de provedores LLM")
    parser.add_argument("--status", action="store_true", help="Mostra status do banco e GitHub")
    parser.add_argument("--sem-publicar", action="store_true", help="Gera como rascunho, sem publicar")

    args = parser.parse_args()

    if not any([
        args.executar, args.agendar, args.noticias, args.artigos,
        args.publicar, args.pipeline_completo, args.diagnostico, args.status,
    ]):
        parser.print_help()
        return 0

    if args.diagnostico:
        _mostrar_diagnostico()
        return 0

    if args.status:
        _mostrar_status()
        return 0

    if args.agendar:
        _mostrar_agendamento()
        return 0

    publicar = not args.sem_publicar

    resultados = {"artigo": None, "noticia": None, "publicacao": None}

    rodar_artigos = args.artigos or args.executar or args.pipeline_completo
    rodar_noticias = args.noticias or args.executar or args.pipeline_completo
    rodar_publicar = args.publicar or args.pipeline_completo

    if rodar_artigos:
        resultados["artigo"] = _gerar_artigo(publicar=publicar)

    if rodar_noticias:
        resultados["noticia"] = _gerar_noticia(publicar=publicar)

    if rodar_publicar:
        resultados["publicacao"] = _publicar_pendentes()

    _banner("RESUMO DA EXECUÇÃO")
    if resultados["artigo"] is not None:
        _log(f"Artigo: {'✅ OK' if resultados['artigo'] else '❌ FALHA'}")
    if resultados["noticia"] is not None:
        _log(f"Notícia: {'✅ OK' if resultados['noticia'] else '❌ FALHA'}")
    if resultados["publicacao"] is not None:
        _log(f"Publicação: {'✅ OK' if resultados['publicacao'] else '❌ FALHA'}")

    teve_falha = any(v is False for v in resultados.values() if v is not None)
    return 1 if teve_falha else 0


if __name__ == "__main__":
    sys.exit(main())
