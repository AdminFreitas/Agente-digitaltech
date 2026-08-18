from pathlib import Path
import py_compile
import shutil
from datetime import datetime


ARQUIVO = Path("repositories/artigo_repository.py")


def main():
    print("=" * 70)
    print("CORREÇÃO DO TEMPO DE LEITURA DOS ARTIGOS")
    print("=" * 70)
    print()

    if not ARQUIVO.exists():
        print(f"[ERRO] Arquivo não encontrado: {ARQUIVO}")
        return 1

    texto = ARQUIVO.read_text(encoding="utf-8")

    trecho_antigo = '''def _calcular_tempo_leitura(texto_markdown: str) -> str:
    palavras = len(texto_markdown.split())
    minutos = max(1, round(palavras / 200))
    return f"{minutos} min"
'''

    trecho_novo = '''def _calcular_tempo_leitura(texto_markdown: str) -> int:
    palavras = len(texto_markdown.split())
    return max(1, round(palavras / 200))
'''

    print(f"[OK] Arquivo encontrado: {ARQUIVO}")
    print()

    if trecho_novo in texto:
        print("[OK] A correção já está aplicada.")
        print("     Nenhuma alteração será feita.")
        return 0

    if trecho_antigo not in texto:
        print("[ERRO] A função esperada não foi encontrada.")
        print()
        print("O arquivo NÃO será alterado.")
        print("Isso evita modificar uma versão diferente da esperada.")
        return 1

    # Backup antes da alteração
    backup_dir = Path(".cleanup_backup") / (
        "correcao_tempo_leitura_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_file = backup_dir / ARQUIVO.name
    shutil.copy2(ARQUIVO, backup_file)

    print("[OK] Backup criado:")
    print(f"     {backup_file}")
    print()

    # Aplicar somente a alteração conhecida
    texto_corrigido = texto.replace(
        trecho_antigo,
        trecho_novo,
        1,
    )

    ARQUIVO.write_text(texto_corrigido, encoding="utf-8")

    print("[OK] Função _calcular_tempo_leitura() corrigida.")
    print()
    print("Alteração:")
    print('  ANTES: retorna "5 min"')
    print("  DEPOIS: retorna 5")
    print("  Tipo: int")
    print()

    # Validar sintaxe
    print("[VALIDAÇÃO] Verificando sintaxe Python...")

    try:
        py_compile.compile(
            str(ARQUIVO),
            doraise=True,
        )
    except Exception as erro:
        print("[ERRO] A sintaxe ficou inválida.")
        print(f"       {erro}")
        print()
        print("[RESTAURAÇÃO] Restaurando backup...")

        shutil.copy2(backup_file, ARQUIVO)

        print("[OK] Arquivo restaurado.")
        return 1

    print("[OK] Sintaxe Python válida.")
    print()

    # Confirmar que a função correta está presente
    texto_final = ARQUIVO.read_text(encoding="utf-8")

    if trecho_novo not in texto_final:
        print("[ERRO] A correção não foi confirmada no arquivo.")
        print("[RESTAURAÇÃO] Restaurando backup...")
        shutil.copy2(backup_file, ARQUIVO)
        print("[OK] Arquivo restaurado.")
        return 1

    print("=" * 70)
    print("CORREÇÃO CONCLUÍDA COM SUCESSO")
    print("=" * 70)
    print()
    print("Arquivo alterado:")
    print(f"  {ARQUIVO}")
    print()
    print("Backup:")
    print(f"  {backup_file}")
    print()
    print("Nenhum pipeline foi executado.")
    print("Nenhum artigo foi gerado.")
    print("Nenhuma notícia foi gerada.")
    print("Nenhuma publicação foi feita.")
    print()
    print("PRÓXIMO PASSO:")
    print("Executar novamente:")
    print()
    print("  python rodar_agente.py --artigo")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
