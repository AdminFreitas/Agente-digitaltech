#!/usr/bin/env python3
"""
fix_env.py - corrige e organiza o .env do Agente DigitalTech.

- Faz backup antes de alterar.
- Mantém somente a última ocorrência ativa de chaves duplicadas.
- Neutraliza Chave_secreta exposta.
- Garante OLLAMA_FALLBACK_MODEL.
- Valida DEFAULT_MODEL/FALLBACK_MODEL contra `ollama list`.
- Não altera API keys existentes.
"""

from __future__ import annotations
import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

KEY_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*?)(\s*)$")


def ollama_models():
    try:
        r = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0:
        return []

    models = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("name"):
            continue
        models.append(line.split()[0])
    return models


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = path.with_name(f"{path.name}.backup_{stamp}")
    shutil.copy2(path, dst)
    return dst


def set_or_add(lines, key, value):
    positions = []
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        m = KEY_RE.match(line.rstrip("\r\n"))
        if m and m.group(2) == key:
            positions.append(i)

    if positions:
        i = positions[-1]
        nl = "\n" if lines[i].endswith("\n") else ""
        lines[i] = f"{key}={value}{nl}"
    else:
        lines.append(f"{key}={value}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=".env")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = Path(args.env)
    if not path.exists():
        print(f"ERRO: não encontrei {path}", file=sys.stderr)
        sys.exit(1)

    original = path.read_text(encoding="utf-8-sig")
    lines = original.splitlines(keepends=True)
    changes = []

    # Encontra duplicatas ativas.
    occurrences = {}
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        m = KEY_RE.match(line.rstrip("\r\n"))
        if m:
            occurrences.setdefault(m.group(2), []).append(i)

    # Comenta todas menos a última ocorrência.
    for key, pos in occurrences.items():
        for i in pos[:-1]:
            body = lines[i].rstrip("\r\n")
            nl = "\n" if lines[i].endswith("\n") else ""
            lines[i] = "# " + body + nl
            changes.append(f"Duplicata comentada: {key} (linha {i+1})")

    # Neutraliza chave exposta.
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        m = KEY_RE.match(line.rstrip("\r\n"))
        if m and m.group(2).lower() == "chave_secreta":
            body = line.rstrip("\r\n")
            nl = "\n" if line.endswith("\n") else ""
            lines[i] = "# " + body + nl
            changes.append("Chave_secreta neutralizada")

    installed = ollama_models()
    if installed:
        print("Modelos Ollama encontrados:")
        for m in installed:
            print(f"  - {m}")
    else:
        print("AVISO: `ollama list` não pôde ser consultado.")

    preferred_default = ["qwen3:latest", "qwen2.5:3b", "llama3:latest"]
    preferred_fallback = ["qwen2.5:3b", "qwen3:latest", "llama3:latest"]

    def choose(preferred):
        for m in preferred:
            if m in installed:
                return m
        return installed[0] if installed else None

    fallback = choose(preferred_fallback) or "qwen2.5:3b"

    # Recalcula chaves ativas.
    active = {}
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        m = KEY_RE.match(line.rstrip("\r\n"))
        if m:
            active[m.group(2)] = (i, m.group(4).strip())

    # OLLAMA_FALLBACK_MODEL é usado diretamente pelo serviço.
    if "OLLAMA_FALLBACK_MODEL" not in active:
        lines.append(
            "\n# Adicionado automaticamente pelo fix_env.py\n"
            f"OLLAMA_FALLBACK_MODEL={fallback}\n"
        )
        changes.append(f"OLLAMA_FALLBACK_MODEL adicionado: {fallback}")
    elif installed:
        i, old = active["OLLAMA_FALLBACK_MODEL"]
        if old not in installed:
            nl = "\n" if lines[i].endswith("\n") else ""
            lines[i] = f"OLLAMA_FALLBACK_MODEL={fallback}{nl}"
            changes.append(
                f"OLLAMA_FALLBACK_MODEL corrigido: {old} -> {fallback}"
            )

    # DEFAULT_MODEL e FALLBACK_MODEL não são usados pelo ollama_service.py,
    # mas evitamos deixar valores apontando para modelos inexistentes.
    if installed:
        for key, preferred in (
            ("DEFAULT_MODEL", preferred_default),
            ("FALLBACK_MODEL", preferred_fallback),
        ):
            if key in active:
                i, old = active[key]
                if old and old not in installed:
                    replacement = choose(preferred)
                    if replacement:
                        nl = "\n" if lines[i].endswith("\n") else ""
                        lines[i] = f"{key}={replacement}{nl}"
                        changes.append(
                            f"{key} corrigido: {old} -> {replacement}"
                        )

    new_text = "".join(lines)

    if new_text == original:
        print("Nenhuma alteração necessária.")
        return

    print("\nAlterações:")
    for c in changes:
        print(f"  - {c}")

    if args.dry_run:
        print("\nDRY-RUN: nenhum arquivo foi alterado.")
        return

    bkp = backup(path)
    path.write_text(new_text, encoding="utf-8")

    print(f"\nOK: {path} corrigido.")
    print(f"BACKUP: {bkp}")
    print("\nIMPORTANTE: se Chave_secreta era uma credencial real, revogue/regere-a.")


if __name__ == "__main__":
    main()