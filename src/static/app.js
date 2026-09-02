/**
 * PC Builder 2 - Modern Single Page Application Client
 */

const API_BASE = '/api/v1';

// 24 divides evenly into 2, 3 and 4 columns, so the last row is never ragged.
const CATALOG_PAGE_SIZE = 24;

// Global App State
const state = {
    activeTab: 'catalog',
    products: [],
    searchQuery: '',
    selectedCategory: '',
    // Cheapest-first is the useful default for a price-comparison tool. The API
    // defaults to 'recent' so its own contract stays unchanged for other callers.
    sort: 'price_asc',
    // Active spec filters, keyed by the query-param suffix the API expects
    // ('socket', 'cores_min', ...). Empty whenever no category is chosen, since
    // specs live in per-category tables.
    specFilters: {},
    expandedFacets: {},
    page: 1,
    total: 0,
    minPrice: '',
    maxPrice: '',
    storeId: '',
    builderSelections: {
        cpu: null,
        motherboard: null,
        gpu: null,
        ram: null,
        storage: null,
        psu: null,
        case: null,
        cooler: null,
        monitor: null
    },
    activeSlotKey: null,
    activeSlotName: null
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initCatalog();
    initBuilder();
    loadStores();
    loadStats();
});

// Headline numbers. Every one is fetched, never written into the markup - a stat bar
// with invented figures is the fastest way to look like a fake site, and hardcoded
// ones go stale the moment a retailer is added.
async function loadStats() {
    const set = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.innerText = value;
    };
    try {
        const res = await fetch(`${API_BASE}/products/stats`);
        if (!res.ok) throw new Error(`${res.status}`);
        const s = await res.json();
        set('stat-products', s.products.toLocaleString('en-IN'));
        set('stat-stores', s.stores);
        set('stat-snapshots', s.price_snapshots.toLocaleString('en-IN'));
        set('stat-updated', s.last_updated ? relativeTime(new Date(s.last_updated + 'Z')) : '—');
    } catch (err) {
        // Hide rather than show placeholder dashes pretending to be data.
        const bar = document.getElementById('stat-bar');
        if (bar) bar.hidden = true;
        console.error('Stats failed to load:', err);
    }
}

function relativeTime(then) {
    const mins = Math.max(0, Math.round((Date.now() - then.getTime()) / 60000));
    if (mins < 60) return `${mins} min ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs} hr ago`;
    return `${Math.round(hrs / 24)} d ago`;
}

// Stores -------------------------------------------------------------------
// Both the Stores tab and the catalog's retailer count used to be written by hand,
// so onboarding a retailer left the page understating its own coverage.
async function loadStores() {
    const grid = document.getElementById('stores-grid');
    const countEl = document.getElementById('store-count');

    try {
        const res = await fetch(`${API_BASE}/stores`);
        if (!res.ok) throw new Error(`${res.status}`);
        const stores = await res.json();
        const active = stores.filter(s => s.active);
        // Cards need the retailer name: a price with no shop attached is the single
        // biggest reason a comparison site reads as fake.
        state.storeNames = Object.fromEntries(stores.map(s => [s.id, s.display_name || s.name]));

        if (countEl) countEl.innerText = active.length;

        const storeSel = document.getElementById('store-filter');
        if (storeSel && storeSel.options.length <= 1) {
            storeSel.innerHTML = '<option value="">All retailers</option>'
                + active.map(s => `<option value="${s.id}">${escapeHtml(s.display_name || s.name)}</option>`).join('');
            storeSel.value = state.storeId || '';
            storeSel.addEventListener('change', () => {
                state.storeId = storeSel.value;
                state.page = 1;
                loadFacets();
                fetchProducts();
            });
        }

        if (grid) {
            grid.innerHTML = active.map(s => `
                <a class="store-chip" href="https://${escapeHtml(s.domain)}"
                   target="_blank" rel="noopener noreferrer nofollow">
                    ${escapeHtml(s.display_name || s.name)}
                </a>
            `).join('');
        }
    } catch (err) {
        if (countEl) countEl.innerText = 'several';
        if (grid) {
            grid.innerHTML = '<span class="footer-note">Retailer list unavailable.</span>';
        }
        console.error('Store list failed to load:', err);
    }
}

// Navigation Handler
function initNavigation() {
    const navButtons = document.querySelectorAll('.nav-btn');
    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.dataset.tab;
            navButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            document.getElementById(`${targetTab}-tab`).classList.add('active');
            state.activeTab = targetTab;

            if (targetTab === 'catalog' && state.products.length === 0) {
                fetchProducts();
            }
        });
    });
}

// Catalog Search & Category Filters
function initCatalog() {
    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-btn');

    if (searchBtn && searchInput) {
        // Any change to what is being searched resets paging: staying on page 7 of a
        // new, shorter result set shows an empty grid and looks broken.
        const runSearch = () => {
            state.searchQuery = searchInput.value.trim();
            state.page = 1;
            fetchProducts();
        };
        searchBtn.addEventListener('click', runSearch);
        searchInput.addEventListener('keyup', (e) => {
            if (e.key === 'Enter') runSearch();
        });
    }

    const sortSelect = document.getElementById('sort-select');
    if (sortSelect) {
        sortSelect.value = state.sort;
        sortSelect.addEventListener('change', () => {
            state.sort = sortSelect.value;
            state.page = 1;
            fetchProducts();
        });
    }

    const categoryChips = document.querySelectorAll('.chip');
    categoryChips.forEach(chip => {
        chip.addEventListener('click', () => {
            categoryChips.forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            state.selectedCategory = chip.dataset.category || '';
            // Spec filters belong to one category's table, so they cannot carry over.
            state.specFilters = {};
            state.expandedFacets = {};
            state.page = 1;
            loadFacets();
            fetchProducts();
        });
    });

    const clearBtn = document.getElementById('filter-clear');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            state.specFilters = {};
            state.minPrice = '';
            state.maxPrice = '';
            state.storeId = '';
            state.page = 1;
            const budget = document.getElementById('budget-min');
            const budgetMax = document.getElementById('budget-max');
            const storeSel = document.getElementById('store-filter');
            if (budget) budget.value = '';
            if (budgetMax) budgetMax.value = '';
            if (storeSel) storeSel.value = '';
            state.expandedFacets = {};
            loadFacets();
            fetchProducts();
        });

        // Budget and store apply in every category, unlike spec filters, so they live
        // outside the facet panel and survive a category change.
        const bindPrice = (id, field) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('input', () => {
                clearTimeout(el._t);
                el._t = setTimeout(() => {
                    state[field] = el.value;
                    state.page = 1;
                    loadFacets();
                    fetchProducts();
                }, 450);
            });
        };
        bindPrice('budget-min', 'minPrice');
        bindPrice('budget-max', 'maxPrice');
    }

    // Must run on first paint too, not only on a chip click: the panel starts hidden
    // in the markup, but the layout still reserves a sidebar column until this says
    // otherwise - which left the whole grid in the 230px column, one card per row.
    restoreFromUrl();
    loadFacets();
    fetchProducts();
}

// Spec filters ---------------------------------------------------------------

// The sidebar and the grid share one CSS grid, so hiding the panel has to widen the
// layout too - otherwise the grid inherits the narrow sidebar column.
function setFilterPanelVisible(visible) {
    const panel = document.getElementById('filter-panel');
    const layout = document.querySelector('.catalog-layout');
    const toggle = document.getElementById('filter-toggle');
    if (panel) panel.hidden = !visible;
    if (layout) layout.classList.toggle('no-filters', !visible);
    // The mobile toggle only exists when there is something to toggle.
    if (toggle) toggle.hidden = !visible;
}

// On narrow screens the panel becomes a drawer: a persistent sidebar has nowhere to
// live, and stacking it above the grid pushes every result below the fold.
function toggleFilterDrawer() {
    const panel = document.getElementById('filter-panel');
    const toggle = document.getElementById('filter-toggle');
    if (!panel) return;
    const open = panel.classList.toggle('drawer-open');
    document.body.classList.toggle('drawer-locked', open);
    toggle?.setAttribute('aria-expanded', String(open));
}

async function loadFacets() {
    const panel = document.getElementById('filter-panel');
    if (!panel) return;

    if (!state.selectedCategory) {
        setFilterPanelVisible(false);
        state.facets = [];
        return;
    }

    // Facets are requested WITH the current selection so each filter's options and
    // counts describe what is actually still reachable - choosing AM5 leaves only AM5
    // chipsets below it. Skipping a filter simply leaves the ones after it wide.
    let url = `${API_BASE}/products/facets?p_category=${encodeURIComponent(state.selectedCategory)}`;
    if (state.searchQuery) url += `&q=${encodeURIComponent(state.searchQuery)}`;
    if (state.minPrice) url += `&min_price=${encodeURIComponent(state.minPrice)}`;
    if (state.maxPrice) url += `&max_price=${encodeURIComponent(state.maxPrice)}`;
    if (state.storeId) url += `&sid=${encodeURIComponent(state.storeId)}`;
    for (const [key, value] of Object.entries(state.specFilters)) {
        url += `&spec_${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
    }

    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`${res.status}`);
        const data = await res.json();
        state.facets = data.filters || [];
        setFilterPanelVisible(state.facets.length > 0);
        renderFacets(state.facets);
        renderActiveFilters();
    } catch (err) {
        setFilterPanelVisible(false);
        console.error('Could not load filters:', err);
    }
}

function labelFor(name) {
    return name.replace(/_/g, ' ').replace(/\bgb\b|\bmm\b|\bmhz\b|\bhz\b|\btdp\b|\bcl\b/gi, m => m.toUpperCase());
}

function renderFacets(facets) {
    const list = document.getElementById('filter-list');
    if (!list) return;

    list.innerHTML = facets.map(f => {
        if (f.kind === 'enum') {
            // Options arrive ordered by count, so the head of the list is the useful
            // part. A 48-entry brand dropdown is a wall; the rest stay one click away.
            const CAP = 8;
            const selected = state.specFilters[f.name];
            const shown = f.options.length > CAP && !state.expandedFacets?.[f.name]
                ? f.options.slice(0, CAP).concat(
                    f.options.slice(CAP).filter(o => String(o.value) === selected))
                : f.options;
            const opts = shown.map(o =>
                `<option value="${escapeHtml(String(o.value))}">${escapeHtml(String(o.value))} (${o.count})</option>`
            ).join('');
            const more = f.options.length > shown.length
                ? `<button class="facet-more" onclick="expandFacet('${f.name}')">
                       Show all ${f.options.length}</button>`
                : '';
            return `
                <div class="filter-group">
                    <label for="f-${f.name}">${escapeHtml(labelFor(f.name))}</label>
                    <select id="f-${f.name}" data-key="${f.name}" class="facet-enum">
                        <option value="">Any</option>${opts}
                    </select>
                    ${more}
                </div>`;
        }
        return `
            <div class="filter-group">
                <label>${escapeHtml(labelFor(f.name))}</label>
                <div class="filter-range">
                    <input type="number" class="facet-range" data-key="${f.name}_min"
                           placeholder="${f.min}" min="${f.min}" max="${f.max}">
                    <span>to</span>
                    <input type="number" class="facet-range" data-key="${f.name}_max"
                           placeholder="${f.max}" min="${f.min}" max="${f.max}">
                </div>
            </div>`;
    }).join('');

    list.querySelectorAll('.facet-enum').forEach(el => {
        el.value = state.specFilters[el.dataset.key] || '';
        el.addEventListener('change', () => {
            setSpecFilter(el.dataset.key, el.value);
        });
    });
    list.querySelectorAll('.facet-range').forEach(el => {
        el.value = state.specFilters[el.dataset.key] || '';
        // Debounced: typing "1600" shouldn't fire a request per digit.
        el.addEventListener('input', () => {
            clearTimeout(el._t);
            el._t = setTimeout(() => setSpecFilter(el.dataset.key, el.value), 400);
        });
    });
}

function expandFacet(name) {
    state.expandedFacets = state.expandedFacets || {};
    state.expandedFacets[name] = true;
    renderFacets(state.facets || []);
}

function setSpecFilter(key, value) {
    if (value === '' || value === null) delete state.specFilters[key];
    else state.specFilters[key] = value;
    state.page = 1;
    // Reload the facets, not just the results: the filters below this one are derived
    // from it, so their options have just changed.
    loadFacets();
    fetchProducts();
}

function clearSpecFilter(key) {
    delete state.specFilters[key];
    state.page = 1;
    loadFacets();
    fetchProducts();
}

// Active selections as removable chips. With filters chained, the panel alone doesn't
// make it obvious how narrow a search has become - especially once a lower filter's
// options have collapsed to one or two entries.
function renderActiveFilters() {
    const host = document.getElementById('active-filters');
    if (!host) return;

    const entries = Object.entries(state.specFilters);
    if (!entries.length) {
        host.innerHTML = '';
        host.hidden = true;
        return;
    }
    host.hidden = false;
    host.innerHTML = entries.map(([key, value]) => {
        const label = key.endsWith('_min') ? `${labelFor(key.slice(0, -4))} from ${value}`
            : key.endsWith('_max') ? `${labelFor(key.slice(0, -4))} up to ${value}`
            : `${labelFor(key)}: ${value}`;
        return `<button class="active-chip" onclick="clearSpecFilter('${key}')"
                    title="Remove this filter">${escapeHtml(label)} <span>&times;</span></button>`;
    }).join('');
}

async function fetchProducts() {
    const grid = document.getElementById('products-grid');
    if (!grid) return;

    grid.innerHTML = '<div style="color: var(--text-secondary); text-align: center; grid-column: 1/-1;">Loading products...</div>';

    // One card per MODEL, not per listing. Searching "9060 XT 16GB" used to return 56
    // near-identical cards for ~25 actual cards; collapsing them is the whole job of a
    // comparison site.
    let url = `${API_BASE}/products/models?size=${CATALOG_PAGE_SIZE}`
        + `&page=${state.page}&sort=${encodeURIComponent(state.sort)}`;
    if (state.searchQuery) url += `&q=${encodeURIComponent(state.searchQuery)}`;
    if (state.selectedCategory) url += `&p_category=${encodeURIComponent(state.selectedCategory)}`;
    if (state.minPrice) url += `&min_price=${encodeURIComponent(state.minPrice)}`;
    if (state.maxPrice) url += `&max_price=${encodeURIComponent(state.maxPrice)}`;
    if (state.storeId) url += `&sid=${encodeURIComponent(state.storeId)}`;
    for (const [key, value] of Object.entries(state.specFilters)) {
        url += `&spec_${encodeURIComponent(key)}=${encodeURIComponent(value)}`;
    }

    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`${res.status}`);
        const data = await res.json();
        const items = data.items || [];

        state.total = data.total || 0;
        const countEl = document.getElementById('result-count');
        if (countEl) {
            countEl.innerText = state.total
                ? `${state.total.toLocaleString('en-IN')} models`
                : '';
        }

        state.products = items;
        renderProducts(items);
        renderPager();
        syncUrl();
    } catch (err) {
        grid.innerHTML = `<div style="color: var(--danger); text-align: center; grid-column: 1/-1;">Failed to load catalog products: ${err.message}</div>`;
    }
}

// Opened stock is systematically cheaper than sealed, so it wins price sorts. Saying
// so on the card is the difference between a real bargain and a misleading one.
const CONDITION_LABELS = {
    open_box: 'Open Box',
    repacked: 'Repacked',
    refurbished: 'Refurbished'
};

function conditionBadge(condition) {
    const label = CONDITION_LABELS[condition];
    return label ? `<span class="condition-badge">${label}</span>` : '';
}

function renderProducts(models) {
    const grid = document.getElementById('products-grid');
    if (!grid) return;

    if (models.length === 0) {
        grid.innerHTML = '<div class="empty-state">'
            + '<strong>No components match.</strong>'
            + '<span>Try a broader search, or clear the filters.</span></div>';
        return;
    }

    grid.innerHTML = models.map(m => {
        const c = m.cheapest;
        const saving = c.mrp && Number(c.mrp) > Number(c.price)
            ? Math.round((1 - Number(c.price) / Number(c.mrp)) * 100)
            : null;
        const spread = m.offer_count > 1 && m.highest_price > m.best_price
            ? `up to ${rupees(m.highest_price)}`
            : null;
        return `
        <div class="product-card">
            <div>
                <div class="card-top">
                    <span class="product-badge">${m.p_category || 'Component'}</span>${conditionBadge(m.condition)}
                </div>
                ${m.image_url
                    ? `<img class="product-img" src="${m.image_url}" alt="${escapeHtml(m.name)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.onerror=null;this.classList.add('img-missing');this.removeAttribute('src');">`
                    : '<div class="product-img img-missing"></div>'}
                <h3 class="product-title">${escapeHtml(m.name)}</h3>
            </div>
            <div>
                <div class="product-price-row">
                    <span class="price-from">from</span>
                    <span class="product-price">${rupees(m.best_price)}</span>
                    ${saving && saving >= 5 ? `<span class="product-save">-${saving}%</span>` : ''}
                </div>
                <div class="card-meta">
                    <span class="store-name">${m.offer_count > 1
                        ? `${m.offer_count} stores &middot; cheapest ${escapeHtml(c.store)}`
                        : escapeHtml(c.store)}</span>
                    ${spread ? `<span class="price-spread">${spread}</span>` : ''}
                </div>
                <div class="card-actions">
                    <button class="btn-secondary" onclick="openCompareModal('${escapeHtml(m.name)}', ${c.id})">
                        ${m.offer_count > 1 ? 'Compare ' + m.offer_count + ' stores' : 'View offer'}
                    </button>
                    <button class="btn-secondary" onclick="openHistoryModal(${c.id})">Price history</button>
                </div>
            </div>
        </div>`;
    }).join('');
}

// Pagination. The catalog fetched a hardcoded 40 rows with no pager, so 11,449
// products were browsable only 40 at a time - everything past that was unreachable
// unless you happened to guess a narrowing search term.
function renderPager() {
    const pager = document.getElementById('pager');
    if (!pager) return;

    const pages = Math.ceil(state.total / CATALOG_PAGE_SIZE);
    if (pages <= 1) {
        pager.innerHTML = '';
        return;
    }

    const current = state.page;
    pager.innerHTML = `
        <button class="page-btn" ${current <= 1 ? 'disabled' : ''}
                onclick="goToPage(${current - 1})">Previous</button>
        <span class="page-status">Page ${current.toLocaleString('en-IN')}
            of ${pages.toLocaleString('en-IN')}</span>
        <button class="page-btn" ${current >= pages ? 'disabled' : ''}
                onclick="goToPage(${current + 1})">Next</button>`;
}

function goToPage(page) {
    state.page = Math.max(1, page);
    fetchProducts();
    document.querySelector('.catalog-layout')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Filters and search belong in the URL so a result set can be shared, bookmarked and
// reached with the back button - none of which worked while all state lived in memory.
function syncUrl() {
    const params = new URLSearchParams();
    if (state.searchQuery) params.set('q', state.searchQuery);
    if (state.selectedCategory) params.set('category', state.selectedCategory);
    if (state.sort !== 'price_asc') params.set('sort', state.sort);
    if (state.page > 1) params.set('page', state.page);
    if (state.minPrice) params.set('min', state.minPrice);
    if (state.maxPrice) params.set('max', state.maxPrice);
    if (state.storeId) params.set('store', state.storeId);
    for (const [key, value] of Object.entries(state.specFilters)) {
        params.set(`spec_${key}`, value);
    }

    const qs = params.toString();
    history.replaceState(null, '', qs ? `?${qs}` : location.pathname);
}

function restoreFromUrl() {
    const p = new URLSearchParams(location.search);
    if (!p.toString()) return;

    state.searchQuery = p.get('q') || '';
    state.selectedCategory = p.get('category') || '';
    state.sort = p.get('sort') || 'price_asc';
    state.page = Math.max(1, parseInt(p.get('page') || '1', 10) || 1);
    state.minPrice = p.get('min') || '';
    state.maxPrice = p.get('max') || '';
    state.storeId = p.get('store') || '';
    for (const [key, value] of p.entries()) {
        if (key.startsWith('spec_')) state.specFilters[key.slice(5)] = value;
    }

    const input = document.getElementById('search-input');
    if (input) input.value = state.searchQuery;
    const sortSelect = document.getElementById('sort-select');
    if (sortSelect) sortSelect.value = state.sort;
    document.querySelectorAll('.chip').forEach(chip => {
        chip.classList.toggle('active', (chip.dataset.category || '') === state.selectedCategory);
    });
}

// PC Builder Manager
function initBuilder() {
    const slots = [
        { key: 'cpu', name: 'Processor (CPU)' },
        { key: 'motherboard', name: 'Motherboard' },
        { key: 'gpu', name: 'Graphics Card (GPU)' },
        { key: 'ram', name: 'Memory (RAM)' },
        { key: 'storage', name: 'Storage (SSD/HDD)' },
        { key: 'psu', name: 'Power Supply (PSU)' },
        { key: 'case', name: 'Cabinet / Case' },
        { key: 'cooler', name: 'CPU Cooler' },
        { key: 'monitor', name: 'Monitor' }
    ];

    const container = document.getElementById('slots-container');
    if (!container) return;

    container.innerHTML = slots.map(s => `
        <div class="slot-card" id="slot-${s.key}">
            <div class="slot-info">
                <div class="slot-icon">⚙</div>
                <div>
                    <div class="slot-title">${s.name}</div>
                    <div class="slot-selected-item" id="slot-name-${s.key}">No component selected</div>
                </div>
            </div>
            <button class="btn-secondary" onclick="openSelectModal('${s.key}', '${s.name}')">Select</button>
        </div>
    `).join('');

    validateBuild();
}

async function openSelectModal(slotKey, slotName) {
    state.activeSlotKey = slotKey;
    state.activeSlotName = slotName;
    const modal = document.getElementById('select-modal');
    const title = document.getElementById('select-modal-title');

    title.innerText = `Select ${slotName}`;
    modal.classList.add('active');

    const searchBox = document.getElementById('select-modal-search');
    if (searchBox) searchBox.value = '';
    const compatToggle = document.getElementById('select-modal-compatible-only');
    if (compatToggle) compatToggle.checked = true;

    await loadSlotCandidates();
}

// Debounced so typing doesn't fire a request per keystroke.
let slotSearchTimer = null;
function onSlotSearchInput() {
    clearTimeout(slotSearchTimer);
    slotSearchTimer = setTimeout(loadSlotCandidates, 250);
}

async function loadSlotCandidates() {
    const slotKey = state.activeSlotKey;
    const slotName = state.activeSlotName || slotKey;
    const list = document.getElementById('select-modal-list');
    const countEl = document.getElementById('select-modal-count');
    const q = (document.getElementById('select-modal-search')?.value || '').trim();
    const compatibleOnly = document.getElementById('select-modal-compatible-only')?.checked !== false;

    list.innerHTML = '<div style="color: var(--text-secondary);">Loading components...</div>';
    if (countEl) countEl.innerText = '';

    const selectedIds = Object.entries(state.builderSelections)
        .filter(([k, v]) => v && k !== slotKey)
        .map(([, v]) => v.id);

    let data;
    try {
        const res = await fetch(`${API_BASE}/builder/candidates`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                slot: slotKey,
                selected_product_ids: selectedIds,
                q: q || null,
                compatible_only: compatibleOnly
            })
        });
        if (!res.ok) throw new Error(`${res.status}`);
        data = await res.json();
    } catch (err) {
        list.innerHTML = `<div style="color: var(--danger);">Could not load ${escapeHtml(slotName)}: ${escapeHtml(err.message)}</div>`;
        return;
    }

    const items = data.items || [];

    if (countEl) {
        const hidden = data.filtered_out || 0;
        const offers = data.offer_count || items.length;
        const base = `${items.length} model${items.length === 1 ? '' : 's'}`
            + ` · ${offers} offer${offers === 1 ? '' : 's'} across stores`;
        countEl.innerText = hidden > 0
            ? `${base} · ${hidden} hidden as incompatible with your current build`
            : base;
    }

    if (items.length === 0) {
        list.innerHTML = `<div style="color: var(--text-secondary);">
            No ${escapeHtml(slotName)} matches${q ? ` "${escapeHtml(q)}"` : ''}${compatibleOnly ? ' that fit your current build' : ''}.
            ${compatibleOnly ? '<br>Untick "Compatible only" to see everything.' : ''}
        </div>`;
        return;
    }

    // Two levels: pick the model, then pick the shop. Listing every offer flat asked
    // the shopper to make both decisions at once out of one repetitive list, and the
    // row they happened to click chose the retailer as a side effect.
    state.slotModels = items;
    list.innerHTML = items.map((m, idx) => `
        <div class="model-row">
            <button class="model-head" onclick="toggleModelOffers(${idx})" aria-expanded="false">
                <span class="model-name">${escapeHtml(m.name)}${conditionBadge(m.condition)}</span>
                <span class="model-price">
                    <strong>₹${Number(m.best_price || 0).toLocaleString('en-IN')}</strong>
                    <em>${m.offer_count} ${m.offer_count === 1 ? 'store' : 'stores'}</em>
                </span>
                <span class="model-caret">▾</span>
            </button>
            <div class="model-offers" id="offers-${idx}" hidden>
                ${m.offers.map((o, oi) => `
                    <div class="offer-row">
                        <span class="offer-store">${escapeHtml(o.store)}${conditionBadge(o.condition)}</span>
                        <span class="offer-price">₹${Number(o.price).toLocaleString('en-IN')}
                            ${oi === 0 && m.offer_count > 1 ? '<em class="offer-best">lowest</em>' : ''}</span>
                        <button class="btn-primary offer-pick"
                                onclick="selectComponentForSlot('${slotKey}', ${o.id}, ${JSON.stringify(o.name).replace(/"/g, '&quot;')})">
                            Choose
                        </button>
                    </div>`).join('')}
            </div>
        </div>
    `).join('');
}

// Expanding one model's store offers. Kept in JS rather than <details> so only one
// model is open at a time - the list is long and nested scrolling gets disorienting.
function toggleModelOffers(idx) {
    const target = document.getElementById(`offers-${idx}`);
    if (!target) return;
    const opening = target.hidden;
    document.querySelectorAll('.model-offers').forEach(el => { el.hidden = true; });
    document.querySelectorAll('.model-head').forEach(el => el.setAttribute('aria-expanded', 'false'));
    target.hidden = !opening;
    target.previousElementSibling?.setAttribute('aria-expanded', String(opening));
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

function selectComponentForSlot(slotKey, productId, productName) {
    let product = state.products.find(p => p.id === productId);
    if (!product) {
        // Grouped picker: the chosen offer lives inside a model, not in state.products.
        for (const model of (state.slotModels || [])) {
            const offer = (model.offers || []).find(o => o.id === productId);
            if (offer) {
                product = { id: offer.id, name: offer.name, current_price: offer.price };
                break;
            }
        }
    }
    state.builderSelections[slotKey] = product || { id: productId, name: productName };
    document.getElementById(`slot-name-${slotKey}`).innerText = productName;
    closeModal('select-modal');
    validateBuild();
}

async function validateBuild() {
    const selectedProducts = Object.values(state.builderSelections).filter(Boolean);
    const productIds = selectedProducts.map(p => p.id);

    try {
        const res = await fetch(`${API_BASE}/builder/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ selected_product_ids: productIds })
        });
        if (!res.ok) {
            // A 422 here used to fall through silently and leave the sidebar stuck on
            // "Incompatibilities Detected" for every build, including an empty one.
            throw new Error(`validate failed: ${res.status} ${await res.text()}`);
        }
        const summary = await res.json();

        // Render Summary Sidebar
        const statusEl = document.getElementById('compatibility-status');
        const warningsEl = document.getElementById('warnings-list');
        const costEl = document.getElementById('total-cost');
        const wattageEl = document.getElementById('total-wattage');

        if (summary.compatible) {
            statusEl.className = 'compatibility-status ok';
            statusEl.innerText = '✓ Compatibility Checked & Verified';
        } else {
            statusEl.className = 'compatibility-status error';
            statusEl.innerText = '⚠ Incompatibilities Detected';
        }

        warningsEl.innerHTML = (summary.warnings || []).map(w => `
            <div class="warning-item ${w.level}">${w.message}</div>
        `).join('');

        wattageEl.innerText = `${summary.estimated_wattage || 0} W`;
        costEl.innerText = `₹${Number(summary.total_min_cost || 0).toLocaleString('en-IN')}`;

    } catch (err) {
        console.error('Validation error:', err);
    }
}

// Compare Modal
async function openCompareModal(productName, productId) {
    const modal = document.getElementById('compare-modal');
    const content = document.getElementById('compare-modal-content');
    modal.classList.add('active');

    content.innerHTML = '<div>Loading price comparison across retailer stores...</div>';

    try {
        const url = `${API_BASE}/compare?q=${encodeURIComponent(productName)}`
            + (productId ? `&product_id=${productId}` : '');
        const res = await fetch(url);
        const data = await res.json();

        content.innerHTML = `
            <h2>${escapeHtml(data.query)}</h2>
            <div style="margin: 1rem 0; display: flex; gap: 1rem; align-items: center; flex-wrap: wrap;">
                <div>Lowest: <strong style="color: var(--accent-cyan);">₹${Number(data.lowest_price || 0).toLocaleString('en-IN')}</strong></div>
                <div>Highest: <strong>₹${Number(data.highest_price || 0).toLocaleString('en-IN')}</strong></div>
                <div style="color: var(--text-secondary); font-size: 0.8rem;">
                    ${data.total_offers} offer${data.total_offers === 1 ? '' : 's'} ·
                    ${data.matched_by === 'canonical_id'
                        ? 'matched as the same product across stores'
                        : 'matched by title text only'}
                </div>
            </div>
            <table class="compare-table">
                <thead>
                    <tr>
                        <th>Store</th>
                        <th>Price</th>
                        <th>Stock</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    ${(data.offers || []).map(o => `
                        <tr>
                            <td>${o.store_name}</td>
                            <td style="color: var(--accent-cyan); font-weight: 700;">₹${Number(o.price).toLocaleString('en-IN')}</td>
                            <td>${o.in_stock ? 'In Stock' : 'Out of Stock'}</td>
                            <td><a href="${o.url}" target="_blank" class="btn-primary" style="padding: 0.3rem 0.8rem; text-decoration: none; font-size: 0.85rem;">Buy</a></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (err) {
        content.innerHTML = `<div style="color: var(--danger);">Failed to load comparison data: ${err.message}</div>`;
    }
}

// History Modal
const rupees = n => '₹' + Number(n).toLocaleString('en-IN');

/**
 * Line chart of the daily low, with the day's low-high band behind it.
 *
 * Hand-built SVG rather than a charting library: the page has no build step and
 * artifacts/CSP aside, one <path> is less code than wiring a dependency.
 */
function priceChartSvg(points) {
    if (points.length < 2) return '';

    const W = 640, H = 200, padL = 62, padR = 12, padT = 14, padB = 26;
    const lows = points.map(p => p.low), highs = points.map(p => p.high);
    let min = Math.min(...lows), max = Math.max(...highs);
    // A flat line would divide by zero and render at the top edge; give it room.
    if (min === max) { min *= 0.98; max *= 1.02; }

    const x = i => padL + (i / (points.length - 1)) * (W - padL - padR);
    const y = v => padT + (1 - (v - min) / (max - min)) * (H - padT - padB);

    const lowLine = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.low).toFixed(1)}`).join('');
    const band = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.high).toFixed(1)}`).join('')
        + points.slice().reverse().map((p, i) => `L${x(points.length - 1 - i).toFixed(1)},${y(p.low).toFixed(1)}`).join('')
        + 'Z';

    const ticks = [min, (min + max) / 2, max].map(v => `
        <line x1="${padL}" y1="${y(v)}" x2="${W - padR}" y2="${y(v)}"
              stroke="rgba(148,163,184,0.15)" stroke-width="1"/>
        <text x="${padL - 8}" y="${y(v) + 4}" text-anchor="end"
              fill="#94a3b8" font-size="10">${rupees(Math.round(v))}</text>`).join('');

    const label = (i, anchor) => `<text x="${x(i)}" y="${H - 8}" text-anchor="${anchor}"
        fill="#94a3b8" font-size="10">${points[i].date.slice(5)}</text>`;

    return `
        <svg viewBox="0 0 ${W} ${H}" class="price-chart" role="img"
             aria-label="Daily price over ${points.length} days">
            ${ticks}
            <path d="${band}" fill="rgba(34,211,238,0.12)"/>
            <path d="${lowLine}" fill="none" stroke="var(--accent-cyan)" stroke-width="2"
                  stroke-linejoin="round"/>
            ${label(0, 'start')}${label(points.length - 1, 'end')}
        </svg>`;
}

async function openHistoryModal(productId) {
    const modal = document.getElementById('history-modal');
    const content = document.getElementById('history-modal-content');
    modal.classList.add('active');

    content.innerHTML = '<div>Loading price history...</div>';

    try {
        const res = await fetch(`${API_BASE}/products/${productId}/price-series?days=90`);
        if (!res.ok) throw new Error(`${res.status}`);
        const data = await res.json();
        const { points, stats } = data;

        if (!points.length) {
            content.innerHTML = '<div>No price history recorded for this listing yet.</div>';
            return;
        }

        // Judged against the price this listing has actually reached, never against
        // MRP - inflated MRP is exactly the trick this is meant to see through.
        const verdict = stats.at_lowest
            ? `<span class="verdict good">Lowest price seen in ${data.days} days</span>`
            : `<span class="verdict">${stats.pct_above_lowest}% above its ${data.days}-day low of `
              + `${rupees(stats.lowest)} (${stats.lowest_date})</span>`;

        content.innerHTML = `
            <h3 style="margin-bottom:0.2rem;">${escapeHtml(data.name)}</h3>
            <div class="price-stats">
                <div><span>Now</span><strong>${rupees(stats.current)}</strong></div>
                <div><span>${data.days}-day low</span><strong>${rupees(stats.lowest)}</strong></div>
                <div><span>${data.days}-day high</span><strong>${rupees(stats.highest)}</strong></div>
            </div>
            ${verdict}
            ${priceChartSvg(points)}
            <p class="chart-note">
                One point per day (lowest seen that day); the shaded band is each day's
                low-to-high range. Tracking began ${points[0].date}.
            </p>`;
    } catch (err) {
        content.innerHTML = `<div style="color: var(--danger);">Failed to load price history: ${escapeHtml(err.message)}</div>`;
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Saved builds -------------------------------------------------------------
// A build previously lived only in this page's memory and was lost on refresh.

async function saveBuild() {
    const btn = document.getElementById('save-build-btn');
    const selections = {};
    for (const [slot, product] of Object.entries(state.builderSelections)) {
        if (product) selections[slot] = product.id;
    }
    if (Object.keys(selections).length === 0) {
        alert('Add at least one component before saving.');
        return;
    }

    const original = btn.innerText;
    btn.disabled = true;
    btn.innerText = 'Saving...';

    try {
        const res = await fetch(`${API_BASE}/builder/builds`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                selections,
                name: document.getElementById('build-name')?.value || null
            })
        });
        if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
        const data = await res.json();

        const url = `${location.origin}/?build=${data.share_token}`;
        document.getElementById('share-link').value = url;
        document.getElementById('share-link-box').style.display = 'block';
        btn.innerText = 'Saved ✓';
        setTimeout(() => { btn.innerText = original; btn.disabled = false; }, 2000);
    } catch (err) {
        btn.innerText = 'Save failed';
        console.error('Save build failed:', err);
        setTimeout(() => { btn.innerText = original; btn.disabled = false; }, 2500);
    }
}

async function loadSharedBuild(token) {
    try {
        const res = await fetch(`${API_BASE}/builder/builds/${encodeURIComponent(token)}`);
        if (!res.ok) throw new Error(`${res.status}`);
        const data = await res.json();

        for (const [slot, item] of Object.entries(data.items || {})) {
            state.builderSelections[slot] = item;
            const el = document.getElementById(`slot-name-${slot}`);
            if (el) el.innerText = item.name;
        }
        if (data.name) {
            const nameInput = document.getElementById('build-name');
            if (nameInput) nameInput.value = data.name;
        }

        // Switch to the builder so the restored build is actually visible.
        document.querySelectorAll('.nav-btn').forEach(b => {
            if (b.dataset.tab === 'builder') b.click();
        });

        await validateBuild();

        // Stock and prices move between save and load, so say so rather than quietly
        // showing a build that can't be bought as-is.
        const notices = [];
        if ((data.unavailable || []).length) {
            notices.push(`${data.unavailable.length} component(s) no longer purchasable: ` +
                data.unavailable.map(u => `${u.slot} (${u.reason})`).join(', '));
        }
        if (data.compatibility_changed_since_save) {
            notices.push('Compatibility differs from when this build was saved.');
        }
        if (notices.length) {
            const warn = document.getElementById('warnings-list');
            if (warn) {
                warn.innerHTML = notices.map(n =>
                    `<div class="warning-item warning">${escapeHtml(n)}</div>`).join('') + warn.innerHTML;
            }
        }
    } catch (err) {
        console.error('Could not load shared build:', err);
        alert('That shared build link could not be loaded.');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const token = new URLSearchParams(location.search).get('build');
    if (token) loadSharedBuild(token);
});
