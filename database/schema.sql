-- Schema completo do projeto agente-ads
-- DigitalTech — Michel Freitas
-- Atualizado: 2026-08-02

-- ---------------------------------------------------------
-- Categorias (usada por artigos e notícias)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS categorias (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    descricao TEXT,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Categorias padrão
INSERT INTO categorias (nome, slug) VALUES
    ('Inteligência Artificial', 'inteligencia-artificial'),
    ('Banco de Dados', 'banco-de-dados'),
    ('Programação', 'programacao'),
    ('Desenvolvimento Web', 'desenvolvimento-web'),
    ('Engenharia de Software', 'engenharia-de-software'),
    ('Dados', 'dados'),
    ('Cibersegurança', 'ciberseguranca'),
    ('Cloud & DevOps', 'cloud-devops'),
    ('Carreira', 'carreira'),
    ('Hardware', 'hardware'),
    ('Open Source', 'open-source'),
    ('Tecnologia', 'tecnologia')
ON CONFLICT (slug) DO NOTHING;

-- ---------------------------------------------------------
-- Autores (mínimo necessário para foreign keys)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS autores (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    email VARCHAR(200) UNIQUE,
    bio TEXT,
    avatar_url TEXT,
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Autor padrão do agente (id=2, conforme AGENTE_AUTOR_ID no .env)
INSERT INTO autores (id, nome, email, bio) VALUES
    (2, 'Agente DigitalTech', 'agente@digitaltech.digital', 'Assistente de IA especializado em tecnologia')
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------
-- Produtos (CRUD de exemplo)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS produtos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    descricao TEXT,
    preco DECIMAL(10, 2) NOT NULL CHECK (preco >= 0),
    estoque INT NOT NULL DEFAULT 0 CHECK (estoque >= 0),
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO produtos (nome, descricao, preco, estoque) VALUES
    ('Notebook Linux', 'Notebook para desenvolvimento com Linux', 3500.00, 10),
    ('Mouse Gamer', 'Mouse ergonômico para longas horas de código', 150.00, 45),
    ('Teclado Mecânico', 'Teclado mecânico switch brown', 250.00, 0),
    ('Monitor 24"', 'Monitor Full HD para produtividade', 1200.00, 8),
    ('SSD 1TB', 'SSD NVMe para alta performance', 450.00, 20)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------
-- Histórico de chat (memória persistente)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS historico_chat (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(50) NOT NULL,
    papel VARCHAR(20) NOT NULL CHECK (papel IN ('usuario', 'agente')),
    conteudo TEXT NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------
-- Artigos (evergreen — gerados pelo agente)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS artigos (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(200) NOT NULL UNIQUE,
    titulo VARCHAR(300) NOT NULL,
    resumo TEXT NOT NULL,
    conteudo_md TEXT NOT NULL,
    conteudo_html TEXT,
    tempo_leitura VARCHAR(20) DEFAULT '5 min',
    categoria_id INTEGER REFERENCES categorias(id),
    autor_id INTEGER REFERENCES autores(id) DEFAULT 2,
    status VARCHAR(20) DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'publicado', 'erro')),
    imagem_url TEXT,
    imagem_autor VARCHAR(200),
    imagem_link TEXT,
    imagem_fonte VARCHAR(50),
    imagem_query TEXT,
    imagem_alt VARCHAR(300),
    meta_title VARCHAR(70),
    meta_description VARCHAR(165),
    data_publicacao TIMESTAMP,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------
-- Notícias (baseadas em RSS — geradas pelo agente)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS noticias (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(320) NOT NULL UNIQUE,
    titulo VARCHAR(300) NOT NULL,
    resumo TEXT NOT NULL,
    conteudo_md TEXT NOT NULL,
    tempo_leitura INTEGER DEFAULT 5,
    categoria_id INTEGER REFERENCES categorias(id),
    autor_id INTEGER REFERENCES autores(id) DEFAULT 2,
    status VARCHAR(20) DEFAULT 'rascunho' CHECK (status IN ('rascunho', 'publicado', 'erro')),
    destaque BOOLEAN DEFAULT FALSE,
    fonte VARCHAR(200),
    url_fonte TEXT,
    imagem_url TEXT,
    imagem_original_url TEXT,
    imagem_alt VARCHAR(300),
    imagem_fonte VARCHAR(50),
    imagem_autor VARCHAR(200),
    imagem_link TEXT,
    imagem_query TEXT,
    meta_title VARCHAR(70),
    meta_description VARCHAR(165),
    visualizacoes INTEGER DEFAULT 0,
    hash_conteudo VARCHAR(64) UNIQUE,
    rss_guid VARCHAR(500) UNIQUE,
    provedor_llm VARCHAR(50),
    modelo_llm VARCHAR(50),
    tempo_geracao_ms INTEGER,
    data_publicacao TIMESTAMP,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------
-- Imagens (relacionadas a notícias — usadas pelo front-end)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS imagens (
    id SERIAL PRIMARY KEY,
    noticia_id INTEGER REFERENCES noticias(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    alt VARCHAR(300),
    principal BOOLEAN DEFAULT FALSE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------
-- Índices
-- ---------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_historico_session ON historico_chat(session_id);
CREATE INDEX IF NOT EXISTS idx_produtos_ativo ON produtos(ativo);
CREATE INDEX IF NOT EXISTS idx_artigos_status ON artigos(status);
CREATE INDEX IF NOT EXISTS idx_artigos_slug ON artigos(slug);
CREATE INDEX IF NOT EXISTS idx_artigos_categoria ON artigos(categoria_id);
CREATE INDEX IF NOT EXISTS idx_noticias_status ON noticias(status);
CREATE INDEX IF NOT EXISTS idx_noticias_slug ON noticias(slug);
CREATE INDEX IF NOT EXISTS idx_noticias_categoria ON noticias(categoria_id);
CREATE INDEX IF NOT EXISTS idx_noticias_hash ON noticias(hash_conteudo);
CREATE INDEX IF NOT EXISTS idx_noticias_guid ON noticias(rss_guid);
CREATE INDEX IF NOT EXISTS idx_imagens_noticia ON imagens(noticia_id);