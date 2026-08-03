# Como aplicar o Passo 5 — Agente de Artigos

Execute tudo a partir da pasta do agente:
cd ~/projetos/agente-ads

## 1. Copiar os arquivos

cp ~/Documentos/passo5/services/gemini_service.py services/gemini_service.py
cp ~/Documentos/passo5/services/github_service.py services/github_service.py
cp ~/Documentos/passo5/repositories/artigo_repository.py repositories/artigo_repository.py
cp ~/Documentos/passo5/app.py app.py
cp ~/Documentos/passo5/requirements.txt requirements.txt

## 2. Criar a tabela de artigos no banco

docker compose exec db psql -U $DB_USER -d $DB_NAME \
  -f /docker-entrypoint-initdb.d/schema_artigos.sql

OU copie o SQL e execute manualmente no pgAdmin.

## 3. Instalar dependências novas

pip install -r requirements.txt

## 4. Subir o projeto com Docker

docker compose up -d

## 5. Testar na documentação interativa

Acesse: http://localhost:8000/docs

## 6. Gerar o primeiro artigo

POST /artigos/gerar
{
  "tema": "Como usar índices no PostgreSQL para melhorar performance",
  "categoria": "Dados",
  "publicar_imediatamente": false
}

## 7. Publicar no blog após revisar

POST /artigos/publicar/1
