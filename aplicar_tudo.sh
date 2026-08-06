#!/bin/bash
# =============================================================================
# aplicar_tudo.sh — Script de instalação automática das correções v5
# =============================================================================
# Uso:
#   chmod +x aplicar_tudo.sh
#   ./aplicar_tudo.sh
#
# O que faz:
#   1. Faz backup (.bak) dos 4 arquivos antigos
#   2. Copia os novos arquivos para as pastas corretas
#   3. Instala dependências do requirements.txt
#   4. Verifica se as cópias foram bem-sucedidas
#   5. Mostra resumo e próximos passos
# =============================================================================

set -e  # Para execução se algum comando falhar

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}   $1"; }
log_warn()  { echo -e "${YELLOW}[AVISO]${NC} $1"; }
log_error() { echo -e "${RED}[ERRO]${NC}  $1"; }

# =============================================================================
# 1. VERIFICAÇÃO DE ARQUIVOS
# =============================================================================
echo ""
echo "============================================================================="
echo "  APLICADOR DE CORREÇÕES v5 — Agente DigitalTech"
echo "============================================================================="

ARQUIVOS_NECESSARIOS=(
    "services_imagem_service_v5.py"
    "services_llm_service_v5.py"
    "rodar_agente_v41.py"
    "pipeline_gerar_artigos_v4.py"
    "requirements_v4.txt"
)

log_info "Verificando arquivos necessários..."
for arquivo in "${ARQUIVOS_NECESSARIOS[@]}"; do
    if [ ! -f "$SCRIPT_DIR/$arquivo" ]; then
        log_error "Arquivo não encontrado: $arquivo"
        log_error "Certifique-se de que todos os arquivos estão na raiz do projeto."
        exit 1
    fi
done
log_ok "Todos os arquivos encontrados."

# =============================================================================
# 2. BACKUP DOS ARQUIVOS ANTIGOS
# =============================================================================
echo ""
log_info "Fazendo backup dos arquivos antigos..."

fazer_backup() {
    local origem="$1"
    if [ -f "$origem" ]; then
        cp "$origem" "${origem}.bak"
        log_ok "Backup: ${origem}.bak"
    else
        log_warn "Arquivo antigo não existe (novo): $origem"
    fi
}

fazer_backup "$SCRIPT_DIR/services/imagem_service.py"
fazer_backup "$SCRIPT_DIR/services/llm_service.py"
fazer_backup "$SCRIPT_DIR/rodar_agente.py"
fazer_backup "$SCRIPT_DIR/pipeline/gerar_artigos.py"
fazer_backup "$SCRIPT_DIR/requirements.txt"

# =============================================================================
# 3. CÓPIA DOS NOVOS ARQUIVOS
# =============================================================================
echo ""
log_info "Copiando novos arquivos..."

# Cria pastas se não existiren
mkdir -p "$SCRIPT_DIR/services"
mkdir -p "$SCRIPT_DIR/pipeline"
mkdir -p "$SCRIPT_DIR/scripts"

cp "$SCRIPT_DIR/services_imagem_service_v5.py" "$SCRIPT_DIR/services/imagem_service.py"
log_ok "services/imagem_service.py → Openverse primeiro, RSS para notícias"

cp "$SCRIPT_DIR/services_llm_service_v5.py" "$SCRIPT_DIR/services/llm_service.py"
log_ok "services/llm_service.py → DeepSeek, HuggingFace, Grok + ordem configurável"

cp "$SCRIPT_DIR/rodar_agente_v41.py" "$SCRIPT_DIR/rodar_agente.py"
log_ok "rodar_agente.py → Assinaturas corrigidas, exit code, NoticiaRepository"

cp "$SCRIPT_DIR/pipeline_gerar_artigos_v4.py" "$SCRIPT_DIR/pipeline/gerar_artigos.py"
log_ok "pipeline/gerar_artigos.py → Sem 'db' como argumento, sessões curtas"

cp "$SCRIPT_DIR/requirements_v4.txt" "$SCRIPT_DIR/requirements.txt"
log_ok "requirements.txt → google-genai adicionado"

# =============================================================================
# 4. VERIFICAÇÃO DAS CÓPIAS
# =============================================================================
echo ""
log_info "Verificando se as cópias foram bem-sucedidas..."

verificar() {
    local arquivo="$1"
    local esperado="$2"
    if grep -q "$esperado" "$arquivo" 2>/dev/null; then
        log_ok "$arquivo verificado"
        return 0
    else
        log_error "$arquivo NÃO contém '$esperado'"
        return 1
    fi
}

ERROS=0

verificar "$SCRIPT_DIR/services/imagem_service.py" "Openverse" || ((ERROS++))
verificar "$SCRIPT_DIR/services/imagem_service.py" "buscar_imagem_noticia" || ((ERROS++))
verificar "$SCRIPT_DIR/services/llm_service.py" "google import genai" || ((ERROS++))
verificar "$SCRIPT_DIR/services/llm_service.py" "_tentar_deepseek" || ((ERROS++))
verificar "$SCRIPT_DIR/rodar_agente.py" "sugerir_tema(categoria=categoria)" || ((ERROS++))
verificar "$SCRIPT_DIR/rodar_agente.py" "gerar_e_processar_artigo(" || ((ERROS++))
verificar "$SCRIPT_DIR/pipeline/gerar_artigos.py" "def gerar_e_processar_artigo(" || ((ERROS++))
verificar "$SCRIPT_DIR/pipeline/gerar_artigos.py" "_sessao_curta" || ((ERROS++))

if [ $ERROS -gt 0 ]; then
    log_error "$ERROS arquivo(s) não passaram na verificação."
    log_error "Verifique se os arquivos de origem estão corretos."
    exit 1
fi

log_ok "Todos os arquivos verificados com sucesso."

# =============================================================================
# 5. INSTALAÇÃO DE DEPENDÊNCIAS
# =============================================================================
echo ""
log_info "Instalando dependências do requirements.txt..."

if [ -f "$SCRIPT_DIR/.venv/bin/pip" ]; then
    PIP="$SCRIPT_DIR/.venv/bin/pip"
    log_info "Usando pip do .venv"
elif command -v pip &> /dev/null; then
    PIP="pip"
    log_warn "Usando pip do sistema (recomendado: ativar .venv primeiro)"
else
    log_error "pip não encontrado. Instale o pip primeiro."
    exit 1
fi

$PIP install -r "$SCRIPT_DIR/requirements.txt"
log_ok "Dependências instaladas."

# =============================================================================
# 6. RESUMO E PRÓXIMOS PASSOS
# =============================================================================
echo ""
echo "============================================================================="
echo "  ✅ TODAS AS CORREÇÕES APLICADAS COM SUCESSO"
echo "============================================================================="
echo ""
echo "  Arquivos alterados:"
echo "    • services/imagem_service.py     (Openverse primeiro, RSS notícias)"
echo "    • services/llm_service.py        (DeepSeek, HF, Grok, ordem .env)"
echo "    • rodar_agente.py                 (Assinaturas corrigidas)"
echo "    • pipeline/gerar_artigos.py       (Sessões curtas, sem db arg)"
echo "    • requirements.txt                (google-genai adicionado)"
echo ""
echo "  ⚠️  PRÓXIMOS PASSOS OBRIGATÓRIOS:"
echo ""
echo "  1. Edite seu .env e corrija os modelos:"
echo ""
echo "     GEMINI_MODEL=gemini-3.6-flash"
echo "     OPENAI_MODEL=gpt-4o-mini"
echo "     ANTHROPIC_MODEL=claude-haiku-4-5-20251001"
echo ""
echo "     # Adicione estas linhas novas:"
echo "     DEFAULT_LLM=ollama"
echo "     FALLBACK_ORDER=ollama,gemini,deepseek,huggingface,openai,claude,grok"
echo ""
echo "  2. Teste o diagnóstico:"
echo "       python rodar_agente.py --diagnostico"
echo ""
echo "  3. Teste a geração de artigo:"
echo "       python rodar_agente.py --artigos --sem-publicar"
echo ""
echo "  4. Se tudo funcionar, teste notícias:"
echo "       python rodar_agente.py --noticias --sem-publicar"
echo ""
echo "============================================================================="
