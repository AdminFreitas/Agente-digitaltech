#!/usr/bin/env python3
"""
rodar_agente.py — CLI oficial do Agente DigitalTech v3

Uso:
    python rodar_agente.py --executar           # Pipeline padrão
    python rodar_agente.py --agendar            # Instruções de cron
    python rodar_agente.py --noticias           # Apenas notícias
    python rodar_agente.py --artigos            # Apenas artigos
    python rodar_agente.py --publicar           # Publica rascunhos
    python rodar_agente.py --pipeline-completo  # Tudo + publicação
    python rodar_agente.py --diagnostico        # Diagnóstico LLM
    python rodar_agente.py --status             # Status do sistema
    python rodar_agente.py --provedores         # Lista provedores disponíveis
"""

import argparse
import random
import sys
import os
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.database import SessionLocal
from services.llm_service import (
    diagnosticar_ollama, testar_provedor, listar_provedores_disponiveis
)
from agents import pesquisador
from repositories.artigo_repository import ArtigoRepository
from repositories.noticia_repository import NoticiaRepository
from pipeline.gerar_artigos import gerar_e_processar_artigo
from pipeline.gerar_noticias import gerar_e_processar_noticia

PUBLICAR_IMEDIATAMENTE = os.getenv("PUBLICAR_IMEDIATAMENTE", "true").lower() in ("1", "true", "yes")

CATEGORIAS_ARTIGOS = [
    "Inteligência Artificial", "Programação", "Banco de Dados",
    "Cibersegurança", "Cloud e DevOps", "Desenvolvimento Web",
    "Engenharia de Software", "Hardware", "Open Source", "Carreira",
]


def _log(mensagem: str) -> None:
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{agora}] {mensagem}", flush=True)


def _buscar_temas_recentes(limite: int = 30) -> list[str]:
    db = SessionLocal()
    try:
        artigos = ArtigoRepository(db).listar_todos(limite=limite)
        return [a.titulo for a in artigos]
    except Exception as e:
        _log(f"AVISO: falha ao buscar temas recentes ({e})")
        return []
    finally:
        db.close()


def _rodar_artigo(publicar: Optional[bool] = None) -> bool:
    publicar_imediatamente = PUBLICAR_IMEDIATAMENTE if publicar is None else publicar
    categoria = random.choice(CATEGORIAS_ARTIGOS)
    temas_recentes = _buscar_temas_recentes(limite=30)

    try:
        tema = pesquisador.sugerir_tema(categoria, temas_recentes=temas_recentes)
    except Exception as e:
        _log(f"FALHA ao sugerir tema: {e}")
        return False

    _log(f"Tema sugerido ({categoria}): {tema}")

    try:
        db = SessionLocal()
        try:
            resultado = gerar_e_processar_artigo(
                db, tema=tema, categoria=categoria,
                publicar_imediatamente=publicar_imediatamente,
            )
            _log(f"Artigo OK: {resultado}")
            return True
        finally:
            db.close()
    except Exception as e:
        _log(f"FALHA ao gerar artigo: {e}")
        return False


def _rodar_noticia(publicar: Optional[bool] = None) -> bool:
    publicar_imediatamente = PUBLICAR_IMEDIATAMENTE if publicar is None else publicar
    try:
        resultado = gerar_e_processar_noticia(publicar_imediatamente=publicar_imediatamente)
        _log(f"Notícia OK: {resultado}")
        return True
    except ValueError as e:
        _log(f"Sem notícia nova: {e}")
        return True
    except Exception as e:
        _log(f"FALHA ao gerar notícia: {e}")
        return False


def _publicar_pendentes() -> bool:
    db = SessionLocal()
    try:
        repo = ArtigoRepository(db)
        pendentes = repo.listar_por_status("rascunho")
        if not pendentes:
            _log("Nenhum artigo em rascunho para publicar.")
            return True

        _log(f"Publicando {len(pendentes)} artigo(s) em rascunho...")
        sucessos = 0
        for artigo in pendentes:
            try:
                from agents import publisher
                resultado = publisher.publicar(db, artigo.id)
                _log(f"  ✅ {artigo.slug} → {resultado.get('blog_url', 'URL indisponível')}")
                sucessos += 1
            except Exception as e:
                _log(f"  ❌ Falha ao publicar '{artigo.slug}': {e}")

        _log(f"Publicação: {sucessos}/{len(pendentes)} sucesso(s)")
        return sucessos == len(pendentes)
    finally:
        db.close()


def _mostrar_agendamento() -> None:
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                    AGENDAMENTO VIA CRON                              ║
╠══════════════════════════════════════════════════════════════════════╣
║  crontab -e                                                          ║
║                                                                      ║
║  # Pipeline completo às 6h e 18h (BRT)                              ║
║  0 6,18 * * * cd /caminho/do/projeto && python rodar_agente.py --pipeline-completo >> logs/agente.log 2>&1
║                                                                      ║
║  # Notícias a cada 2h                                                ║
║  0 */2 * * * cd /caminho/do/projeto && python rodar_agente.py --noticias >> logs/noticias.log 2>&1
║                                                                      ║
║  # Artigos 9h, notícias 12h, publicar 15h                           ║
║  0 9 * * *  cd /caminho/do/projeto && python rodar_agente.py --artigos
║  0 12 * * * cd /caminho/do/projeto && python rodar_agente.py --noticias
║  0 15 * * * cd /caminho/do/projeto && python rodar_agente.py --publicar
╚══════════════════════════════════════════════════════════════════════╝
""")


def _mostrar_diagnostico() -> None:
    print("\n" + "="*60)
    print("DIAGNÓSTICO DO AGENTE DIGITALTECH v3")
    print("="*60)

    print("\n[1/3] Ollama (local)")
    diag = diagnosticar_ollama()
    print(f"  URL: {diag['url']}")
    print(f"  Servidor: {'✅ SIM' if diag['servidor_acessivel'] else '❌ NÃO'}")
    print(f"  Modelo: {diag['modelo_configurado']} — {'✅ Disponível' if diag['modelo_disponivel'] else '❌ NÃO encontrado'}")
    print(f"  Instalados: {', '.join(diag['modelos_instalados']) or 'Nenhum'}")
    if diag['erro']:
        print(f"  Erro: {diag['erro']}")

    if diag['servidor_acessivel']:
        print("\n[2/3] Teste rápido Ollama...")
        teste = testar_provedor("Ollama (qwen2.5:3b)", "Responda apenas: TESTE")
        print(f"  Resultado: {'✅ OK' if teste['ok'] else '❌ FALHA'}")
        if teste['ok']:
            print(f"  Resposta: '{teste['resposta']}' em {teste['tempo_ms']}ms")
        else:
            print(f"  Erro: {teste['erro']}")

    print("\n[3/3] OpenRouter (nuvem)")
    or_key = os.getenv("OPENROUTER_API_KEY", "")
    if or_key and not or_key.startswith("$"):
        print(f"  OPENROUTER_API_KEY: ✅ Configurada ({or_key[:12]}...)")
        for nome in ["OpenRouter/gpt-luna", "OpenRouter/claude-opus", "OpenRouter/gemini-flash"]:
            teste = testar_provedor(nome, "Responda apenas: OK")
            status = "✅ OK" if teste['ok'] else "❌ FALHA"
            print(f"  {nome}: {status}")
            if not teste['ok']:
                print(f"    → {teste['erro']}")
    else:
        print("  OPENROUTER_API_KEY: ❌ Não configurada")
        print("  → Cadastre-se em https://openrouter.ai/keys")

    print("\n[4/4] Banco de dados")
    try:
        db = SessionLocal()
        try:
            total = len(ArtigoRepository(db).listar_todos())
            print(f"  ✅ Conectado — {total} artigo(s)")
        finally:
            db.close()
    except Exception as e:
        print(f"  ❌ {e}")

    print("\n" + "="*60)


def _mostrar_status() -> None:
    print("\n" + "="*60)
    print("STATUS DO AGENTE DIGITALTECH")
    print("="*60)
    try:
        db = SessionLocal()
        try:
            artigos = ArtigoRepository(db).listar_todos()
            noticias = NoticiaRepository(db).listar_todos()
            rascunhos = [a for a in artigos if a.status == "rascunho"]
            publicados = [a for a in artigos if a.status == "publicado"]
            print(f"\n📊 Artigos: {len(artigos)} total | {len(publicados)} publicados | {len(rascunhos)} rascunhos")
            print(f"📰 Notícias: {len(noticias)} total")
            if rascunhos:
                print(f"\n📝 Rascunhos pendentes:")
                for a in rascunhos[-5:]:
                    print(f"    - {a.titulo}")
            print(f"\n🔧 Config:")
            print(f"  OLLAMA: {os.getenv('OLLAMA_MODEL', 'qwen2.5:3b')} @ {os.getenv('OLLAMA_URL', 'localhost:11434')}")
            print(f"  OPENROUTER: {'✅' if os.getenv('OPENROUTER_API_KEY') else '❌'}")
            print(f"  GITHUB: {'✅' if os.getenv('GITHUB_TOKEN') else '❌'}")
        finally:
            db.close()
    except Exception as e:
        print(f"❌ Erro: {e}")
    print("\n" + "="*60)


def _mostrar_provedores() -> None:
    print("\nProvedores LLM disponíveis neste momento:")
    for i, nome in enumerate(listar_provedores_disponiveis(), 1):
        print(f"  {i}. {nome}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Agente DigitalTech v3 — Geração autônoma de conteúdo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python rodar_agente.py --diagnostico           # Verifica saúde do sistema
  python rodar_agente.py --executar              # Artigo + notícia
  python rodar_agente.py --pipeline-completo     # Tudo + publicação
  python rodar_agente.py --artigos --sem-publicar # Gera rascunho
        """
    )
    parser.add_argument("--executar", action="store_true", help="Pipeline padrão (artigo + notícia)")
    parser.add_argument("--agendar", action="store_true", help="Instruções de cron")
    parser.add_argument("--noticias", action="store_true", help="Apenas notícias")
    parser.add_argument("--artigos", action="store_true", help="Apenas artigos")
    parser.add_argument("--publicar", action="store_true", help="Publica rascunhos pendentes")
    parser.add_argument("--pipeline-completo", action="store_true", help="Artigo + notícia + publicação")
    parser.add_argument("--diagnostico", action="store_true", help="Diagnóstico de provedores")
    parser.add_argument("--status", action="store_true", help="Status do sistema")
    parser.add_argument("--provedores", action="store_true", help="Lista provedores disponíveis")
    parser.add_argument("--sem-publicar", action="store_true", help="Gera como rascunho")

    args = parser.parse_args()

    if not any([args.executar, args.agendar, args.noticias, args.artigos,
                args.publicar, args.pipeline_completo, args.diagnostico,
                args.status, args.provedores]):
        parser.print_help()
        return 0

    if args.agendar:
        _mostrar_agendamento()
        return 0
    if args.diagnostico:
        _mostrar_diagnostico()
        return 0
    if args.status:
        _mostrar_status()
        return 0
    if args.provedores:
        _mostrar_provedores()
        return 0

    publicar = not args.sem_publicar
    ok_artigo = True
    ok_noticia = True
    ok_publicacao = True

    executar_artigo = args.artigos or args.executar or args.pipeline_completo
    executar_noticia = args.noticias or args.executar or args.pipeline_completo
    executar_publicar = args.publicar or args.pipeline_completo

    if executar_artigo:
        _log("="*50)
        _log("GERAÇÃO DE ARTIGO")
        _log("="*50)
        ok_artigo = _rodar_artigo(publicar=publicar)

    if executar_noticia:
        _log("="*50)
        _log("GERAÇÃO DE NOTÍCIA")
        _log("="*50)
        ok_noticia = _rodar_noticia(publicar=publicar)

    if executar_publicar:
        _log("="*50)
        _log("PUBLICAÇÃO DE PENDENTES")
        _log("="*50)
        ok_publicacao = _publicar_pendentes()

    _log("="*50)
    _log("RESUMO")
    _log(f"Artigo: {'✅' if ok_artigo else '❌'} | Notícia: {'✅' if ok_noticia else '❌'}")
    if executar_publicar:
        _log(f"Publicação: {'✅' if ok_publicacao else '❌'}")
    _log("="*50)

    return 0 if (ok_artigo and ok_noticia and ok_publicacao) else 1


if __name__ == "__main__":
    sys.exit(main())
