#!/bin/bash
# ============================================================
# setup_dashboard.sh — Script de instalação automática do Dashboard
# DigitalTech para o projeto agente-ads
# ============================================================

set -e  # Para em qualquer erro

echo "=========================================="
echo "🚀 DigitalTech Dashboard — Setup"
echo "=========================================="
echo ""

# Detecta o diretório do projeto
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "📁 Diretório do projeto: $PROJECT_DIR"
echo ""

# ============================================================
# 1. VERIFICA DEPENDÊNCIAS
# ============================================================
echo "📦 Verificando dependências..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 não encontrado. Instale o Python 3.11+"
    exit 1
fi

if ! pip show fastapi &> /dev/null; then
    echo "⚠️  FastAPI não encontrado. Instalando..."
    pip install fastapi uvicorn python-dotenv
fi

echo "✅ Dependências OK"
echo ""

# ============================================================
# 2. CRIA PASTA static/ SE NÃO EXISTIR
# ============================================================
if [ ! -d "$PROJECT_DIR/static" ]; then
    echo "📂 Criando pasta static/..."
    mkdir -p "$PROJECT_DIR/static"
else
    echo "📂 Pasta static/ já existe"
fi

# ============================================================
# 3. VERIFICA SE O DASHBOARD JÁ ESTÁ NA PASTA
# ============================================================
if [ ! -f "$PROJECT_DIR/static/index.html" ]; then
    echo "⚠️  Dashboard não encontrado em static/index.html"
    echo ""
    echo "👉 Você precisa colocar o arquivo index.html dentro da pasta static/"
    echo "   Opções:"
    echo "   1. Baixe o arquivo do link que a IA gerou"
    echo "   2. Ou copie o conteúdo do arquivo e cole em static/index.html"
    echo ""
    echo "   Comando manual:"
    echo "   cp /caminho/para/o/index.html $PROJECT_DIR/static/index.html"
    echo ""
    exit 1
else
    echo "✅ Dashboard encontrado em static/index.html"
fi

# ============================================================
# 4. VERIFICA SE main.py EXISTE
# ============================================================
if [ ! -f "$PROJECT_DIR/main.py" ]; then
    echo "⚠️  main.py não encontrado na raiz do projeto"
    echo ""
    echo "👉 Você precisa ter um main.py na raiz do projeto."
    echo "   O arquivo main.py que a IA gerou deve ser colocado aqui:"
    echo "   $PROJECT_DIR/main.py"
    echo ""
    exit 1
else
    echo "✅ main.py encontrado"
fi

# ============================================================
# 5. VERIFICA SE .env EXISTE
# ============================================================
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "⚠️  Arquivo .env não encontrado"
    echo ""
    echo "👉 Crie o arquivo .env a partir do exemplo:"
    echo "   cp .env.example .env"
    echo "   nano .env  # edite com seus valores"
    echo ""
fi

# ============================================================
# 6. VERIFICA PORTA 8000
# ============================================================
echo ""
echo "🔍 Verificando porta 8000..."

if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    PID=$(lsof -Pi :8000 -sTCP:LISTEN -t)
    echo "⚠️  Porta 8000 já está em uso (PID: $PID)"
    echo ""
    echo "   Opções:"
    echo "   1. Matar o processo atual:  kill $PID"
    echo "   2. Usar outra porta:         uvicorn main:app --reload --port 8001"
    echo ""
    read -p "Deseja matar o processo atual e continuar? (s/n): " choice
    if [ "$choice" = "s" ] || [ "$choice" = "S" ]; then
        echo "🛑 Matando processo $PID..."
        kill $PID 2>/dev/null || true
        sleep 2
        echo "✅ Processo encerrado"
    else
        echo ""
        echo "👉 Rode o servidor manualmente com outra porta:"
        echo "   uvicorn main:app --reload --port 8001"
        echo ""
        exit 0
    fi
else
    echo "✅ Porta 8000 livre"
fi

# ============================================================
# 7. INICIA O SERVIDOR
# ============================================================
echo ""
echo "=========================================="
echo "🎉 Tudo pronto! Iniciando servidor..."
echo "=========================================="
echo ""
echo "📊 Dashboard:  http://localhost:8000/"
echo "📚 API Docs:   http://localhost:8000/api/docs"
echo "📖 ReDoc:     http://localhost:8000/api/redoc"
echo ""
echo "Pressione CTRL+C para parar"
echo ""

cd "$PROJECT_DIR"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
