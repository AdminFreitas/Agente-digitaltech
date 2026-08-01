# Passo 6 — Fallback Chain de modelos

Execute dentro de ~/projetos/agente-ads

## 1. Copiar o novo serviço
cp ~/Documentos/passo6/llm_service.py services/llm_service.py

## 2. Atualizar o import no app.py
python3 ~/Documentos/passo6/app_patch.py

## 3. Atualizar requirements.txt
cp ~/Documentos/passo6/requirements.txt requirements.txt

## 4. Instalar dependências novas
pip install openai anthropic

## 5. Reiniciar o container
docker compose restart api

## 6. Testar
curl -s -X POST http://localhost:8000/artigos/gerar \
  -H "Content-Type: application/json" \
  -d '{"tema": "Como usar índices no PostgreSQL", "categoria": "Dados", "publicar_imediatamente": false}' \
  | python3 -m json.tool
