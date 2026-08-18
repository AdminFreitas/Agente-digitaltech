/* ================================================================
   INTEGRAÇÃO API — Agente Digital Tech
   Cole este script NO FINAL do <body> do seu index.html,
   ou substitua as funções equivalentes no arquivo original.
   ================================================================ */

const API_BASE = '';  // Mesma origem (FastAPI serve o static). 
                      // Em dev separado: 'http://localhost:8000'

// ------------------------------------------------------------------
// Helpers HTTP
// ------------------------------------------------------------------
async function apiGet(path) {
    const r = await fetch(API_BASE + path);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
}
async function apiPost(path, body = {}) {
    const r = await fetch(API_BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
}
async function apiPatch(path, body = {}) {
    const r = await fetch(API_BASE + path, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
}
async function apiDelete(path) {
    const r = await fetch(API_BASE + path, { method: 'DELETE' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
}

// ------------------------------------------------------------------
// 1. SUBSTITUIÇÃO: carregamento inicial do state
// ------------------------------------------------------------------
async function loadStateFromAPI() {
    try {
        // Carrega todos os conteúdos (artigos + notícias)
        state.items = await apiGet('/api/conteudos');
        // Carrega categorias dinamicamente
        state.categories = await apiGet('/api/categorias');
        // Atualiza dashboard
        await refreshDashboard();
        // Renderiza página atual
        renderPage(state.currentPage || 'dashboard');
        showToast('Dados sincronizados com o servidor.', 'success');
    } catch (e) {
        console.error(e);
        showToast('Erro ao sincronizar com API: ' + e.message, 'error');
    }
}

// ------------------------------------------------------------------
// 2. SUBSTITUIÇÃO: Dashboard com dados reais
// ------------------------------------------------------------------
async function refreshDashboard() {
    try {
        const stats = await apiGet('/api/dashboard');
        // Atualiza contadores que o renderDashboard() usa
        state.dashboard = stats;
    } catch (e) {
        console.warn('Dashboard stats não disponíveis', e);
    }
}

// Sobrescreve renderDashboard para usar dados reais quando disponíveis
const _originalRenderDashboard = window.renderDashboard;
window.renderDashboard = function() {
    const a = state.items.filter(x => x.tipo === 'artigo');
    const n = state.items.filter(x => x.tipo === 'noticia');
    const rev = state.items.filter(x => x.status === 'revisao');
    const stats = state.dashboard || {};

    return `
    <div class="cards-grid">
      <div class="card">
        <div class="card-title">Artigos</div>
        <div class="card-value">${stats.artigos ?? a.length}</div>
        <div class="card-meta">Criados e revisados</div>
      </div>
      <div class="card">
        <div class="card-title">Notícias</div>
        <div class="card-value">${stats.noticias ?? n.length}</div>
        <div class="card-meta">Gerenciadas no blog</div>
      </div>
      <div class="card">
        <div class="card-title">Em revisão</div>
        <div class="card-value">${stats.revisao ?? rev.length}</div>
        <div class="card-meta">Aguardando aprovação</div>
      </div>
      <div class="card">
        <div class="card-title">Publicados</div>
        <div class="card-value">${stats.publicados ?? state.items.filter(x=>x.status==='publicado').length}</div>
        <div class="card-meta">No ar</div>
      </div>
    </div>
    <!-- ... resto do dashboard permanece igual ... -->
    `;
};

// ------------------------------------------------------------------
// 3. SUBSTITUIÇÃO: listagem com filtros via API
// ------------------------------------------------------------------
const _originalFilterLibrary = window.filterLibrary;
window.filterLibrary = async function(type) {
    const label = type === 'artigos' ? 'artigo' : 'noticia';
    const q = (document.getElementById('library-search')?.value || '').toLowerCase();
    const status = document.getElementById('library-status-filter')?.value || '';
    const cat = document.getElementById('library-category-filter')?.value || '';
    const tag = (document.getElementById('library-tag-filter')?.value || '').toLowerCase();
    const sort = document.getElementById('library-sort-filter')?.value || 'recent';

    try {
        // Monta query string
        const params = new URLSearchParams();
        params.set('tipo', label);
        if (status) params.set('status', status);
        if (cat) params.set('categoria', cat);
        if (tag) params.set('tag', tag);
        if (q) params.set('search', q);
        params.set('sort', sort);

        const filtered = await apiGet(`/api/conteudos?${params.toString()}`);
        const table = document.getElementById('library-table');
        if (table) table.innerHTML = filtered.length ? renderRows(filtered) 
            : '<p style="padding:20px;color:var(--text-tertiary)">Nenhum conteúdo corresponde aos filtros atuais.</p>';
        const count = document.getElementById('library-count');
        if (count) count.textContent = filtered.length + ' itens';
    } catch (e) {
        showToast('Erro ao filtrar: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 4. SUBSTITUIÇÃO: salvar conteúdo (criar ou editar)
// ------------------------------------------------------------------
const _originalSaveContent = window.saveContent;
window.saveContent = async function() {
    const get = id => document.getElementById(id)?.value;
    const payload = {
        titulo: get('form-titulo')?.trim(),
        resumo: get('form-resumo')?.trim(),
        conteudo: get('form-conteudo')?.trim(),
        categoria: get('form-categoria') || '',
        tags: (get('form-tags') || '').split(',').map(t => t.trim()).filter(Boolean),
        status: get('form-status') || 'rascunho',
        tipo: state.editingType === 'notícia' ? 'noticia' : 'artigo',
        imagem_url: get('form-featured-url')?.trim() || null,
        seo_title: get('seo-title')?.trim() || null,
        seo_description: get('seo-description')?.trim() || null,
        slug: get('form-slug')?.trim() || null,
    };

    if (!payload.titulo) {
        showToast('O título é obrigatório.', 'warning');
        return;
    }

    try {
        if (state.editingId) {
            // Atualiza existente
            await apiPatch(`/api/conteudos/${state.editingId}`, payload);
            showToast('Conteúdo atualizado com sucesso!', 'success');
        } else {
            // Cria novo
            await apiPost('/api/conteudos', payload);
            showToast('Conteúdo criado com sucesso!', 'success');
        }
        // Recarrega e volta para a biblioteca
        await loadStateFromAPI();
        navigateTo(state.editingType === 'notícia' ? 'noticias' : 'artigos');
    } catch (e) {
        showToast('Erro ao salvar: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 5. SUBSTITUIÇÃO: excluir item
// ------------------------------------------------------------------
const _originalDeleteItem = window.deleteItem;
window.deleteItem = async function(id) {
    if (!confirm('Tem certeza que deseja excluir este conteúdo?')) return;
    try {
        await apiDelete(`/api/conteudos/${id}`);
        showToast('Conteúdo excluído.', 'success');
        await loadStateFromAPI();
        renderPage(state.currentPage);
    } catch (e) {
        showToast('Erro ao excluir: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 6. SUBSTITUIÇÃO: editar item (carrega do servidor)
// ------------------------------------------------------------------
const _originalEditItem = window.editItem;
window.editItem = async function(id) {
    try {
        const item = await apiGet(`/api/conteudos/${id}`);
        state.editingId = item.id;
        state.editingType = item.tipo === 'noticia' ? 'notícia' : 'artigo';

        // Preenche formulário (ajuste os IDs se necessário)
        const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ''; };
        set('form-titulo', item.titulo);
        set('form-resumo', item.resumo);
        set('form-conteudo', item.conteudo);
        set('form-categoria', item.categoria);
        set('form-tags', (item.tags || []).join(', '));
        set('form-status', item.status);
        set('form-slug', item.slug);
        set('form-featured-url', item.imagem_url);
        set('seo-title', item.seo_title);
        set('seo-description', item.seo_description);

        navigateTo('editor');
    } catch (e) {
        showToast('Erro ao carregar edição: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 7. SUBSTITUIÇÃO: gerar artigo com IA
// ------------------------------------------------------------------
const _originalGerarArtigo = window.gerarArtigo;
window.gerarArtigo = async function() {
    const tema = prompt('Qual o tema do artigo?', 'Pipeline de Dados Moderno');
    if (!tema) return;
    showToast('Gerando artigo com IA...', 'info');
    try {
        await apiPost('/api/artigos/gerar', { 
            tema, 
            categoria: 'Tecnologia',
            publicar_imediatamente: false 
        });
        showToast('Artigo gerado e enviado para revisão!', 'success');
        await loadStateFromAPI();
        renderPage('artigos');
    } catch (e) {
        showToast('Erro na geração: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 8. SUBSTITUIÇÃO: gerar notícia com IA
// ------------------------------------------------------------------
const _originalGerarNoticia = window.gerarNoticia;
window.gerarNoticia = async function() {
    const tema = prompt('Qual o tema da notícia?', 'Novidades do Ecossistema de IA');
    showToast('Gerando notícia com IA...', 'info');
    try {
        await apiPost('/api/noticias/gerar', { 
            tema: tema || undefined,
            publicar_imediatamente: false 
        });
        showToast('Notícia gerada e enviada para revisão!', 'success');
        await loadStateFromAPI();
        renderPage('noticias');
    } catch (e) {
        showToast('Erro na geração: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 9. SUBSTITUIÇÃO: publicar conteúdo
// ------------------------------------------------------------------
window.publicarItem = async function(id) {
    try {
        await apiPost(`/api/conteudos/${id}/publicar`);
        showToast('Conteúdo publicado com sucesso!', 'success');
        await loadStateFromAPI();
        renderPage(state.currentPage);
    } catch (e) {
        showToast('Erro ao publicar: ' + e.message, 'error');
    }
};

// ------------------------------------------------------------------
// 10. SUBSTITUIÇÃO: health check real
// ------------------------------------------------------------------
window.checkHealthReal = async function() {
    try {
        const h = await apiGet('/api/health');
        updateAgentStatus(
            h.banco === 'ok' ? 'success' : 'error',
            `API: ${h.api} | Banco: ${h.banco} | IA: ${h.ia}`
        );
    } catch (e) {
        updateAgentStatus('error', 'API indisponível');
    }
};

// ------------------------------------------------------------------
// 11. INICIALIZAÇÃO: troca o load inicial
// ------------------------------------------------------------------
// Remove dados mockados do state.items se existirem
if (window.state && Array.isArray(window.state.items)) {
    // Guarda categorias padrão se necessário
}

// Sobrescreve a inicialização da página para carregar da API
const _oldDOMLoaded = window.onload;
window.addEventListener('DOMContentLoaded', async () => {
    await loadStateFromAPI();
    // Health check periódico real (a cada 30s)
    setInterval(checkHealthReal, 30000);
    checkHealthReal();
});
