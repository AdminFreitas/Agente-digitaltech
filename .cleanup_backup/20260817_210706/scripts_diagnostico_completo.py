#!/usr/bin/env python3
"""
scripts_diagnostico_completo.py

Varredura completa do projeto Agente DigitalTech.
NÃO modifica, move, renomeia ou exclui nenhum arquivo.
Apenas analisa e gera relatório em Markdown.

Uso:
    python scripts_diagnostico_completo.py [CAMINHO_DO_PROJETO]

Se CAMINHO_DO_PROJETO não for informado, usa o diretório atual.
"""

import os
import sys
import re
import ast
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

# ── Configuração ────────────────────────────────────────────────────────────
EXTENSOES_TEMP = {".bak", ".tmp", ".old", "~", ".swp", ".swo", ".pyc", ".pyo"}
PADROES_TEMP = re.compile(r"(_old|_backup|_bak|_copy|_copia|\.old\d*|~\d*|\s+copia\s*|\s+copy\s*)", re.IGNORECASE)
NOME_SCRIPT = Path(__file__).name

# Pastas/padrões a ignorar na análise de conteúdo (mas listar na árvore)
IGNORAR_CONTEUDO = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", ".mypy_cache"}


def human_readable(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def contar_linhas(caminho: Path) -> int:
    try:
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def extrair_imports(caminho: Path) -> set:
    """Extrai nomes de módulos importados de um arquivo .py via AST."""
    imports = set()
    try:
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
    except Exception:
        pass
    return imports


def extrair_modulos_internos(caminho: Path, raiz: Path) -> set:
    """Extrai imports relativos/internos (from pasta.modulo import ...)."""
    internos = set()
    try:
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module.split(".")[0]
                # Se o módulo corresponde a uma pasta ou .py no projeto, é interno
                if (raiz / mod).exists() or (raiz / f"{mod}.py").exists():
                    internos.add(mod)
    except Exception:
        pass
    return internos


def hash_arquivo(caminho: Path, tamanho_limite=10 * 1024 * 1024) -> str:
    """Hash MD5 parcial (primeiros 8KB) para detectar duplicados."""
    try:
        h = hashlib.md5()
        with open(caminho, "rb") as f:
            h.update(f.read(8192))
            # Se arquivo pequeno, lê tudo; se grande, lê também o final
            if caminho.stat().st_size > tamanho_limite:
                f.seek(-4096, 2)
                h.update(f.read(4096))
            elif caminho.stat().st_size > 8192:
                f.seek(0)
                h.update(f.read())
        return h.hexdigest()
    except Exception:
        return ""


# ── Classe principal ────────────────────────────────────────────────────────
class DiagnosticoProjeto:
    def __init__(self, raiz: Path):
        self.raiz = raiz.resolve()
        self.arquivos = []          # lista de dicts com metadados
        self.pastas = []            # lista de Path
        self.py_files = []          # apenas .py
        self.executaveis = []       # scripts com shebang ou .py na raiz/scripts/tools
        self.temporarios = []       # backups, .tmp, etc.
        self.vazias = []            # pastas vazias
        self.duplicados = []        # pares de arquivos com mesmo nome
        self.relatorio = []

    def varrer(self):
        print(f"[INFO] Varrendo: {self.raiz}")
        for dirpath, dirnames, filenames in os.walk(self.raiz):
            dirpath_p = Path(dirpath)
            rel = dirpath_p.relative_to(self.raiz)

            # Ignora pastas de ambiente virtual para conteúdo, mas mantém na árvore
            dirnames[:] = [d for d in dirnames if d not in IGNORAR_CONTEUDO]

            self.pastas.append(dirpath_p)

            if not filenames and not any((dirpath_p / d).exists() for d in dirnames):
                self.vazias.append(rel)

            for fname in filenames:
                caminho = dirpath_p / fname
                try:
                    stat = caminho.stat()
                    tamanho = stat.st_size
                    mtime = datetime.fromtimestamp(stat.st_mtime)
                except Exception:
                    tamanho = 0
                    mtime = datetime.min

                info = {
                    "caminho": caminho,
                    "relativo": rel / fname,
                    "tamanho": tamanho,
                    "mtime": mtime,
                    "extensao": caminho.suffix.lower(),
                    "nome": fname,
                    "pasta": rel,
                }
                self.arquivos.append(info)

                if info["extensao"] == ".py":
                    info["linhas"] = contar_linhas(caminho)
                    info["imports"] = extrair_imports(caminho)
                    info["internos"] = extrair_modulos_internos(caminho, self.raiz)
                    self.py_files.append(info)

                if self._eh_temporario(fname, caminho):
                    self.temporarios.append(info)

                if self._eh_executavel(info):
                    self.executaveis.append(info)

        self._detectar_duplicados()
        print(f"[INFO] Varredura concluída. {len(self.arquivos)} arquivos, {len(self.pastas)} pastas.")

    def _eh_temporario(self, nome: str, caminho: Path) -> bool:
        if any(nome.endswith(ext) for ext in EXTENSOES_TEMP):
            return True
        if PADROES_TEMP.search(nome):
            return True
        if ".bak" in nome.lower() or "backup" in nome.lower():
            return True
        return False

    def _eh_executavel(self, info: dict) -> bool:
        nome = info["nome"]
        rel = str(info["relativo"])
        # Scripts Python na raiz ou em pastas comuns de scripts
        if info["extensao"] == ".py":
            if rel.startswith("rodar") or rel.startswith("script") or rel.startswith("tool") or rel.startswith("diag"):
                return True
            if "/scripts/" in rel or "/tools/" in rel or "/utils/" in rel or "/util/" in rel:
                return True
            # Shebang
            try:
                with open(info["caminho"], "r", encoding="utf-8", errors="ignore") as f:
                    primeira = f.readline()
                    if primeira.startswith("#!/"):
                        return True
            except Exception:
                pass
        # Shell scripts
        if info["extensao"] in {".sh", ".bat", ".cmd", ".ps1"}:
            return True
        return False

    def _detectar_duplicados(self):
        por_nome = defaultdict(list)
        for info in self.arquivos:
            por_nome[info["nome"]].append(info)
        for nome, lista in por_nome.items():
            if len(lista) > 1:
                # Ignora __init__.py comuns
                if nome == "__init__.py":
                    continue
                # Compara hashes parciais
                hashes = defaultdict(list)
                for info in lista:
                    h = hash_arquivo(info["caminho"])
                    hashes[h].append(info)
                for h, items in hashes.items():
                    if len(items) > 1 and h:
                        self.duplicados.append({"nome": nome, "arquivos": items, "hash": h})

    # ── Seções do relatório ─────────────────────────────────────────────────

    def secao_estrutura(self) -> str:
        linhas = ["## 1. Estrutura Completa\n"]
        total_size = sum(a["tamanho"] for a in self.arquivos)
        profundidade_max = max((len(a["relativo"].parts) for a in self.arquivos), default=0)

        linhas.append(f"- **Diretório raiz:** `{self.raiz}`")
        linhas.append(f"- **Total de arquivos:** {len(self.arquivos)}")
        linhas.append(f"- **Total de pastas:** {len(self.pastas)}")
        linhas.append(f"- **Tamanho total:** {human_readable(total_size)}")
        linhas.append(f"- **Profundidade máxima:** {profundidade_max} níveis\n")

        # Árvore simplificada
        linhas.append("### Árvore de diretórios\n")
        linhas.append("```")
        arvore = self._gerar_arvore()
        linhas.extend(arvore)
        linhas.append("```\n")

        # Tamanho por pasta
        linhas.append("### Tamanho por pasta (top 20)\n")
        tamanho_pasta = defaultdict(int)
        for info in self.arquivos:
            tamanho_pasta[str(info["pasta"])] += info["tamanho"]
        for pasta, tam in sorted(tamanho_pasta.items(), key=lambda x: -x[1])[:20]:
            linhas.append(f"- `{pasta}/` → {human_readable(tam)}")
        linhas.append("")
        return "\n".join(linhas)

    def _gerar_arvore(self) -> list:
        linhas = [str(self.raiz.name) + "/"]
        pastas_ordenadas = sorted(self.pastas, key=lambda p: str(p.relative_to(self.raiz)))
        for pasta in pastas_ordenadas:
            rel = pasta.relative_to(self.raiz)
            if rel == Path("."):
                continue
            profundidade = len(rel.parts)
            prefix = "    " * (profundidade - 1) + "├── "
            arquivos_aqui = [a["nome"] for a in self.arquivos if a["pasta"] == rel]
            linhas.append(f"{prefix}{rel.name}/ ({len(arquivos_aqui)} arquivos)")
        return linhas

    def secao_python(self) -> str:
        linhas = ["## 2. Arquivos Python\n"]
        linhas.append(f"Total de arquivos `.py`: {len(self.py_files)}\n")
        linhas.append("| Arquivo | Linhas | Tamanho | Modificado |")
        linhas.append("|---------|--------|---------|------------|")
        for info in sorted(self.py_files, key=lambda x: str(x["relativo"])):
            linhas.append(
                f"| `{info['relativo']}` | {info['linhas']} | {human_readable(info['tamanho'])} | {info['mtime'].strftime('%Y-%m-%d %H:%M')} |"
            )
        linhas.append("")
        return "\n".join(linhas)

    def secao_executaveis(self) -> str:
        linhas = ["## 3. Scripts Executáveis / Utilitários\n"]
        if not self.executaveis:
            linhas.append("Nenhum script executável identificado.\n")
            return "\n".join(linhas)
        for info in sorted(self.executaveis, key=lambda x: str(x["relativo"])):
            linhas.append(f"- `{info['relativo']}` ({human_readable(info['tamanho'])}, {info['mtime'].strftime('%Y-%m-%d')})")
        linhas.append("")
        return "\n".join(linhas)

    def secao_duplicacoes(self) -> str:
        linhas = ["## 4. Possíveis Duplicações\n"]
        if not self.duplicados:
            linhas.append("Nenhuma duplicação detectada.\n")
            return "\n".join(linhas)

        for dup in self.duplicados:
            linhas.append(f"### `{dup['nome']}` (hash parcial: `{dup['hash'][:8]}...`)")
            for info in dup["arquivos"]:
                linhas.append(f"- `{info['relativo']}` ({human_readable(info['tamanho'])})")
            linhas.append("")
        return "\n".join(linhas)

    def secao_pastas_suspeitas(self) -> str:
        linhas = ["## 5. Pastas Suspeitas\n"]
        if self.vazias:
            linhas.append("### Pastas vazias ou sem arquivos relevantes")
            for v in self.vazias:
                linhas.append(f"- `{v}/`")
            linhas.append("")

        # Pastas com nomes suspeitos
        suspeitas = [p for p in self.pastas if any(x in p.name.lower() for x in ["old", "backup", "bak", "temp", "tmp", "teste", "experimento", "draft"])]
        if suspeitas:
            linhas.append("### Pastas com nomes suspeitos (old, backup, temp, etc.)")
            for p in suspeitas:
                rel = p.relative_to(self.raiz)
                linhas.append(f"- `{rel}/`")
            linhas.append("")

        if not self.vazias and not suspeitas:
            linhas.append("Nenhuma pasta suspeita identificada.\n")
        return "\n".join(linhas)

    def secao_fora_do_lugar(self) -> str:
        linhas = ["## 6. Arquivos Fora do Lugar\n"]
        fora = []
        for info in self.arquivos:
            rel = str(info["relativo"])
            nome = info["nome"]
            # Scripts .py na raiz que não são o main
            if "/" not in rel and nome.endswith(".py") and nome != NOME_SCRIPT:
                fora.append((rel, "Script Python na raiz do projeto"))
            # Arquivos de teste fora de tests/
            if nome.startswith("test_") and not rel.startswith("tests/") and not rel.startswith("test/"):
                fora.append((rel, "Arquivo de teste fora da pasta tests/"))
            # Arquivos .env ou config espalhados
            if nome.endswith(".env") and "/" in rel:
                fora.append((rel, "Arquivo .env dentro de subpasta (geralmente fica na raiz)"))
            # Arquivos de imagem/vídeo no meio do código
            if info["extensao"] in {".jpg", ".jpeg", ".png", ".gif", ".mp4", ".mov"} and not any(x in rel for x in ["assets", "img", "images", "media", "static"]):
                fora.append((rel, "Arquivo de mídia fora de pasta de assets/imagens"))

        if fora:
            for rel, motivo in fora:
                linhas.append(f"- `{rel}` → {motivo}")
        else:
            linhas.append("Nenhum arquivo aparentemente fora do lugar.\n")
        linhas.append("")
        return "\n".join(linhas)

    def secao_temporarios(self) -> str:
        linhas = ["## 7. Arquivos Temporários / Backups\n"]
        if not self.temporarios:
            linhas.append("Nenhum arquivo temporário ou backup identificado.\n")
            return "\n".join(linhas)
        for info in sorted(self.temporarios, key=lambda x: str(x["relativo"])):
            linhas.append(f"- `{info['relativo']}` ({human_readable(info['tamanho'])}, {info['mtime'].strftime('%Y-%m-%d')})")
        linhas.append("")
        return "\n".join(linhas)

    def secao_arquitetura(self) -> str:
        linhas = ["## 8. Análise da Arquitetura\n"]
        # Conta arquivos por pasta de primeiro nível
        contagem = Counter()
        for info in self.arquivos:
            partes = info["relativo"].parts
            if len(partes) > 1:
                contagem[partes[0]] += 1
            elif len(partes) == 1:
                contagem["(raiz)"] += 1

        linhas.append("### Distribuição de arquivos por pasta raiz")
        for pasta, qtd in contagem.most_common():
            linhas.append(f"- `{pasta}/` → {qtd} arquivos")
        linhas.append("")

        # Nomenclatura inconsistente
        nomes_pastas = [p.name for p in self.pastas if p != self.raiz]
        inconsistentes = []
        # singular vs plural
        for nome in nomes_pastas:
            if nome.endswith("s") and nome[:-1] in nomes_pastas:
                inconsistentes.append(f"`{nome}` vs `{nome[:-1]}`")
            if nome + "s" in nomes_pastas and nome not in [n[:-1] for n in nomes_pastas if n.endswith("s")]:
                pass  # já pego acima
        if inconsistentes:
            linhas.append("### Possíveis inconsistências de nomenclatura")
            for inc in inconsistentes:
                linhas.append(f"- {inc}")
            linhas.append("")

        # Pastas muito profundas
        profundas = [a for a in self.arquivos if len(a["relativo"].parts) > 6]
        if profundas:
            linhas.append(f"### Arquivos em pastas muito profundas (>6 níveis): {len(profundas)}")
            for info in profundas[:10]:
                linhas.append(f"- `{info['relativo']}`")
            linhas.append("")

        return "\n".join(linhas)

    def secao_dependencias(self) -> str:
        linhas = ["## 9. Dependências e Módulos Órfãos\n"]

        # Mapeia todos os módulos Python internos (pastas com __init__.py ou .py na raiz)
        modulos_internos = set()
        for info in self.py_files:
            rel = info["relativo"]
            partes = rel.parts
            if len(partes) > 1:
                modulos_internos.add(partes[0])
            else:
                modulos_internos.add(partes[0].replace(".py", ""))

        # Quem importa quem
        importadores = defaultdict(set)  # modulo -> quem o importa
        todos_imports = set()
        for info in self.py_files:
            nome_mod = str(info["relativo"]).replace(".py", "").replace("/", ".")
            for imp in info["internos"]:
                todos_imports.add(imp)
                importadores[imp].add(nome_mod)

        # Órfãos: módulos internos que ninguém importa (exceto __init__ e main)
        orfaos = []
        for info in self.py_files:
            rel = info["relativo"]
            nome_base = rel.name.replace(".py", "")
            pasta_pai = rel.parts[0] if len(rel.parts) > 1 else ""
            # Ignora __init__, main, arquivos na raiz com nome de script
            if nome_base in {"__init__", "main", "app", "manage", NOME_SCRIPT.replace(".py", "")}:
                continue
            # Se é um módulo de pasta e ninguém importa essa pasta
            if pasta_pai and pasta_pai not in importadores and pasta_pai in modulos_internos:
                if all(pasta_pai not in i["internos"] for i in self.py_files if i["relativo"] != rel):
                    orfaos.append((str(rel), f"pasta `{pasta_pai}` nunca importada"))
            # Se é um .py solto e ninguém importa
            elif not pasta_pai:
                if nome_base not in importadores and nome_base != self.raiz.name:
                    orfaos.append((str(rel), "nunca importado por nenhum arquivo"))

        if orfaos:
            linhas.append("### Scripts/módulos possivelmente órfãos (não importados por ninguém)")
            for cam, motivo in orfaos:
                linhas.append(f"- `{cam}` → {motivo}")
            linhas.append("")
        else:
            linhas.append("Nenhum módulo órfão óbvio detectado.\n")

        # Imports externos mais comuns
        externos = Counter()
        for info in self.py_files:
            for imp in info["imports"]:
                if imp not in modulos_internos and not imp.startswith("."):
                    externos[imp] += 1
        if externos:
            linhas.append("### Bibliotecas externas importadas")
            for lib, qtd in externos.most_common(20):
                linhas.append(f"- `{lib}` → importada em {qtd} arquivo(s)")
            linhas.append("")

        return "\n".join(linhas)

    def secao_resumo(self) -> str:
        linhas = ["## 10. Relatório Final e Recomendações\n"]

        # Pontos positivos
        linhas.append("### ✅ Pontos Positivos")
        if len(self.py_files) > 0:
            linhas.append(f"- Projeto possui {len(self.py_files)} arquivos Python bem estruturados.")
        if not self.duplicados:
            linhas.append("- Nenhuma duplicação de arquivo detectada.")
        if not self.temporarios:
            linhas.append("- Nenhum arquivo temporário ou backup identificado.")
        if len(self.pastas) < 15:
            linhas.append("- Estrutura de pastas relativamente enxuta.")
        linhas.append("")

        # Problemas
        linhas.append("### ⚠️ Problemas Encontrados")
        problemas = []
        if self.temporarios:
            problemas.append(f"- {len(self.temporarios)} arquivo(s) temporário/backup detectado(s).")
        if self.duplicados:
            problemas.append(f"- {len(self.duplicados)} grupo(s) de arquivo(s) duplicado(s).")
        if self.vazias:
            problemas.append(f"- {len(self.vazias)} pasta(s) vazia(s).")
        if not problemas:
            linhas.append("- Nenhum problema crítico identificado na estrutura atual.")
        else:
            linhas.extend(problemas)
        linhas.append("")

        # Prioridades
        linhas.append("### 📋 Itens de Alta Prioridade")
        if self.temporarios:
            linhas.append("1. Remover arquivos temporários e backups listados na seção 7.")
        if self.duplicados:
            linhas.append("2. Revisar duplicações na seção 4 e manter apenas a versão principal.")
        if not self.temporarios and not self.duplicados:
            linhas.append("- Nenhum item de alta prioridade.")
        linhas.append("")

        linhas.append("### 📋 Itens de Média Prioridade")
        if self.vazias:
            linhas.append("- Avaliar se as pastas vazias (seção 5) ainda são necessárias.")
        linhas.append("- Revisar arquivos fora do lugar (seção 6) e relocar se necessário.")
        linhas.append("")

        linhas.append("### 📋 Itens de Baixa Prioridade")
        linhas.append("- Padronizar nomenclatura de pastas se houver inconsistências.")
        linhas.append("- Consolidar scripts utilitários se houver muitos arquivos pequenos com funções similares.")
        linhas.append("")

        # Lista numerada final
        linhas.append("### 🗑️ Lista de Itens para Remoção ou Reorganização")
        idx = 1
        if self.temporarios:
            for info in self.temporarios:
                linhas.append(f"{idx}. **Remover:** `{info['relativo']}` — arquivo temporário/backup.")
                idx += 1
        if self.duplicados:
            for dup in self.duplicados:
                caminhos = "`, `".join(str(a["relativo"]) for a in dup["arquivos"])
                linhas.append(f"{idx}. **Revisar duplicados:** `{caminhos}` — manter apenas um.")
                idx += 1
        if self.vazias:
            for v in self.vazias:
                linhas.append(f"{idx}. **Avaliar pasta vazia:** `{v}/` — remover se não for usada.")
                idx += 1
        if idx == 1:
            linhas.append("Nenhum item identificado para remoção automática.\n")
        linhas.append("")
        return "\n".join(linhas)

    def gerar_relatorio(self) -> str:
        partes = [
            f"# Relatório de Diagnóstico do Projeto\n",
            f"**Projeto:** `{self.raiz.name}`  ",
            f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Gerado por:** `scripts_diagnostico_completo.py`\n",
            "---\n",
            self.secao_estrutura(),
            self.secao_python(),
            self.secao_executaveis(),
            self.secao_duplicacoes(),
            self.secao_pastas_suspeitas(),
            self.secao_fora_do_lugar(),
            self.secao_temporarios(),
            self.secao_arquitetura(),
            self.secao_dependencias(),
            self.secao_resumo(),
        ]
        return "\n".join(partes)

    def executar(self):
        self.varrer()
        relatorio = self.gerar_relatorio()
        saida = self.raiz / "DIAGNOSTICO_PROJETO.md"
        with open(saida, "w", encoding="utf-8") as f:
            f.write(relatorio)
        print(f"\n[SUCESSO] Relatório gerado: {saida}")
        print(f"            {len(self.arquivos)} arquivos analisados.")
        return saida


# ── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1:
        caminho = Path(sys.argv[1])
    else:
        caminho = Path.cwd()

    if not caminho.exists():
        print(f"[ERRO] Caminho não encontrado: {caminho}")
        sys.exit(1)

    diag = DiagnosticoProjeto(caminho)
    diag.executar()
