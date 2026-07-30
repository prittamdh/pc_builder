/**
 * PC Builder 2 - Modern Single Page Application Client
 */

const API_BASE = '/api/v1';

// Global App State
const state = {
    activeTab: 'catalog',
    products: [],
    searchQuery: '',
    selectedCategory: '',
    builderSelections: {
        cpu: null,
        motherboard: null,
        gpu: null,
        ram: null,
        storage: null,
        psu: null,
        case: null
    },
    activeSlotKey: null
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initCatalog();
    initBuilder();
    initCanonical();
});

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
            } else if (targetTab === 'canonical') {
                fetchCanonicalProducts();
            }
        });
    });
}

// Catalog Search & Category Filters
function initCatalog() {
    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-btn');

    if (searchBtn && searchInput) {
        searchBtn.addEventListener('click', () => {
            state.searchQuery = searchInput.value.trim();
            fetchProducts();
        });

        searchInput.addEventListener('keyup', (e) => {
            if (e.key === 'Enter') {
                state.searchQuery = searchInput.value.trim();
                fetchProducts();
            }
        });
    }

    const categoryChips = document.querySelectorAll('.chip');
    categoryChips.forEach(chip => {
        chip.addEventListener('click', () => {
            categoryChips.forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            state.selectedCategory = chip.dataset.category || '';
            fetchProducts();
        });
    });

    fetchProducts();
}

async function fetchProducts() {
    const grid = document.getElementById('products-grid');
    if (!grid) return;

    grid.innerHTML = '<div style="color: var(--text-secondary); text-align: center; grid-column: 1/-1;">Loading products...</div>';

    let url = `${API_BASE}/products?size=40`;
    if (state.searchQuery) url += `&q=${encodeURIComponent(state.searchQuery)}`;
    if (state.selectedCategory) url += `&p_category=${encodeURIComponent(state.selectedCategory)}`;
    
    try {
        const res = await fetch(url);
        const data = await res.json();
        const items = data.items || [];

        state.products = items;
        renderProducts(items);
    } catch (err) {
        grid.innerHTML = `<div style="color: var(--danger); text-align: center; grid-column: 1/-1;">Failed to load catalog products: ${err.message}</div>`;
    }
}

function renderProducts(products) {
    const grid = document.getElementById('products-grid');
    if (!grid) return;

    if (products.length === 0) {
        grid.innerHTML = '<div style="color: var(--text-secondary); text-align: center; grid-column: 1/-1;">No hardware components found matching your query.</div>';
        return;
    }

    grid.innerHTML = products.map(p => `
        <div class="product-card">
            <div>
                <span class="product-badge">${p.p_category || p.category || 'Component'}</span>
                ${p.image_url ? `<img class="product-img" src="${p.image_url}" alt="${escapeHtml(p.name)}" referrerpolicy="no-referrer" onerror="this.onerror=null; this.src='https://placehold.co/300x300/1e293b/94a3b8?text=Hardware+Image';">` : '<div class="product-img" style="display:flex;align-items:center;justify-content:center;color:#64748b;">No Image</div>'}
                <h3 class="product-title">${escapeHtml(p.name)}</h3>
            </div>
            <div>
                <div class="product-price-row">
                    <span class="product-price">₹${p.current_price ? Number(p.current_price).toLocaleString('en-IN') : 'N/A'}</span>
                    ${p.current_mrp ? `<span class="product-mrp">₹${Number(p.current_mrp).toLocaleString('en-IN')}</span>` : ''}
                </div>
                <div class="card-actions">
                    <button class="btn-secondary" onclick="openCompareModal('${escapeHtml(p.name)}')">Compare</button>
                    <button class="btn-secondary" onclick="openHistoryModal(${p.id})">History</button>
                </div>
            </div>
        </div>
    `).join('');
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
        { key: 'case', name: 'Cabinet / Case' }
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

function openSelectModal(slotKey, slotName) {
    state.activeSlotKey = slotKey;
    const modal = document.getElementById('select-modal');
    const title = document.getElementById('select-modal-title');
    const list = document.getElementById('select-modal-list');

    title.innerText = `Select ${slotName}`;
    modal.classList.add('active');

    // Filter catalog matching slot category
    const catMap = {
        cpu: 'CPU',
        gpu: 'GPU',
        motherboard: 'MOTHERBOARD',
        ram: 'RAM',
        storage: 'SSD',
        psu: 'PSU',
        case: 'CABINET'
    };
    const targetCat = catMap[slotKey];

    const matching = state.products.filter(p => !targetCat || (p.category || '').toUpperCase().includes(targetCat));

    if (matching.length === 0) {
        list.innerHTML = '<div style="color: var(--text-secondary);">No matching components loaded. Search or select a category first.</div>';
        return;
    }

    list.innerHTML = matching.map(p => `
        <div class="slot-card" style="margin-bottom: 0.75rem; cursor: pointer;" onclick="selectComponentForSlot('${slotKey}', ${p.id}, '${escapeHtml(p.name)}')">
            <div>
                <div style="font-weight: 600;">${escapeHtml(p.name)}</div>
                <div style="color: var(--accent-cyan); font-weight: 700;">₹${Number(p.current_price || 0).toLocaleString('en-IN')}</div>
            </div>
            <button class="btn-primary" style="padding: 0.4rem 1rem; font-size: 0.85rem;">Choose</button>
        </div>
    `).join('');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

function selectComponentForSlot(slotKey, productId, productName) {
    const product = state.products.find(p => p.id === productId);
    state.builderSelections[slotKey] = product;
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
            body: JSON.stringify({ product_ids: productIds })
        });
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
async function openCompareModal(productName) {
    const modal = document.getElementById('compare-modal');
    const content = document.getElementById('compare-modal-content');
    modal.classList.add('active');

    content.innerHTML = '<div>Loading price comparison across retailer stores...</div>';

    try {
        const res = await fetch(`${API_BASE}/compare?q=${encodeURIComponent(productName)}`);
        const data = await res.json();

        content.innerHTML = `
            <h2>${escapeHtml(data.query)}</h2>
            <div style="margin: 1rem 0; display: flex; gap: 1rem;">
                <div>Lowest: <strong style="color: var(--accent-cyan);">₹${Number(data.lowest_price || 0).toLocaleString('en-IN')}</strong></div>
                <div>Highest: <strong>₹${Number(data.highest_price || 0).toLocaleString('en-IN')}</strong></div>
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
async function openHistoryModal(productId) {
    const modal = document.getElementById('history-modal');
    const content = document.getElementById('history-modal-content');
    modal.classList.add('active');

    content.innerHTML = '<div>Loading historical price snapshots...</div>';

    try {
        const res = await fetch(`${API_BASE}/products/${productId}/history`);
        const history = await res.json();

        if (history.length === 0) {
            content.innerHTML = '<div>No historical price snapshots recorded yet.</div>';
            return;
        }

        content.innerHTML = `
            <h3>Price History Snapshots</h3>
            <table class="compare-table">
                <thead>
                    <tr>
                        <th>Date & Time</th>
                        <th>Price</th>
                        <th>MRP</th>
                        <th>Stock Status</th>
                    </tr>
                </thead>
                <tbody>
                    ${history.map(h => `
                        <tr>
                            <td>${new Date(h.scraped_at).toLocaleString()}</td>
                            <td style="color: var(--accent-cyan); font-weight: 700;">₹${Number(h.price).toLocaleString('en-IN')}</td>
                            <td>${h.mrp ? '₹' + Number(h.mrp).toLocaleString('en-IN') : '-'}</td>
                            <td>${h.in_stock ? 'In Stock' : 'Out of Stock'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (err) {
        content.innerHTML = `<div style="color: var(--danger);">Failed to load price history: ${err.message}</div>`;
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Canonical Match (Test) GUI Logic
let canonicalState = {
    selectedCategory: '',
    reviewOnly: false
};

function initCanonical() {
    const chips = document.querySelectorAll('#canonical-category-chips .chip');
    chips.forEach(chip => {
        chip.addEventListener('click', () => {
            chips.forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            canonicalState.selectedCategory = chip.dataset.canonicalCat || '';
            fetchCanonicalProducts();
        });
    });

    const reviewCheckbox = document.getElementById('canonical-review-only');
    if (reviewCheckbox) {
        reviewCheckbox.addEventListener('change', () => {
            canonicalState.reviewOnly = reviewCheckbox.checked;
            fetchCanonicalProducts();
        });
    }

    const runBtn = document.getElementById('run-canonical-btn');
    if (runBtn) {
        runBtn.addEventListener('click', runCanonicalPipeline);
    }
}

async function runCanonicalPipeline() {
    const grid = document.getElementById('canonical-grid');
    const runBtn = document.getElementById('run-canonical-btn');
    if (runBtn) runBtn.innerText = '⏳ Running...';
    if (grid) grid.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 2rem;">Executing experimental matching pipeline across 10 stores...</div>';

    try {
        const res = await fetch(`${API_BASE}/canonical/run`, { method: 'POST' });
        const data = await res.json();
        if (runBtn) runBtn.innerText = '▶ Run Pipeline';
        fetchCanonicalProducts();
    } catch (err) {
        if (runBtn) runBtn.innerText = '▶ Run Pipeline';
        if (grid) grid.innerHTML = `<div style="color: var(--danger); text-align: center; padding: 2rem;">Failed to execute pipeline: ${err.message}</div>`;
    }
}

async function fetchCanonicalProducts() {
    const grid = document.getElementById('canonical-grid');
    if (!grid) return;

    grid.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 2rem;">Loading canonical product groups...</div>';

    let url = `${API_BASE}/canonical/products?limit=80`;
    if (canonicalState.selectedCategory) url += `&category=${encodeURIComponent(canonicalState.selectedCategory)}`;
    if (canonicalState.reviewOnly) url += `&needs_review=true`;

    try {
        const res = await fetch(url);
        const data = await res.json();
        renderCanonicalProducts(data.items || []);
    } catch (err) {
        grid.innerHTML = `<div style="color: var(--danger); text-align: center; padding: 2rem;">Failed to fetch canonical products: ${err.message}</div>`;
    }
}

function renderCanonicalProducts(items) {
    const grid = document.getElementById('canonical-grid');
    if (!grid) return;

    if (items.length === 0) {
        grid.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 2rem;">No canonical product groups match your filter. Click "▶ Run Pipeline" to generate groups.</div>';
        return;
    }

    grid.innerHTML = items.map(c => `
        <div class="product-card" style="display: block; margin-bottom: 1rem; border-left: 4px solid ${c.needs_review ? 'var(--danger)' : 'var(--accent-cyan)'};">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.75rem;">
                <div>
                    <span class="product-badge" style="background: ${c.needs_review ? 'rgba(239, 68, 68, 0.2)' : 'rgba(6, 182, 212, 0.2)'}; color: ${c.needs_review ? '#f87171' : '#38bdf8'}; font-weight: 700;">
                        ${c.needs_review ? '⚠ REVIEW QUEUE' : '✓ MATCHED GROUP (' + (c.listings ? c.listings.length : 0) + ' Stores)'}
                    </span>
                    <span class="product-badge" style="margin-left: 0.5rem;">${(c.category || '').toUpperCase()}</span>
                    <h3 class="product-title" style="margin-top: 0.4rem; font-size: 1.1rem; color: #f8fafc;">${escapeHtml(c.name)}</h3>
                    <div style="color: var(--text-secondary); font-size: 0.85rem; margin-top: 0.2rem;">
                        Key: <code style="background: #0f172a; padding: 0.2rem 0.5rem; border-radius: 4px; color: #a5f3fc;">${escapeHtml(c.canonical_key || 'None')}</code>
                    </div>
                </div>
            </div>

            <div style="background: rgba(15, 23, 42, 0.6); padding: 0.75rem; border-radius: 8px; margin-bottom: 0.75rem; font-size: 0.85rem; color: #cbd5e1;">
                <strong>Structured Attributes:</strong> ${escapeHtml(JSON.stringify(c.attributes))}
            </div>

            <div>
                <strong style="font-size: 0.9rem; color: var(--text-primary);">Mapped Retailer Store Listings:</strong>
                <table class="compare-table" style="margin-top: 0.5rem; font-size: 0.85rem;">
                    <thead>
                        <tr>
                            <th>Store</th>
                            <th>Listing Title</th>
                            <th>Price</th>
                            <th>Normalized Match Text</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${(c.listings || []).map(l => `
                            <tr>
                                <td style="font-weight: 600; color: #a5f3fc;">${escapeHtml(l.store_name)}</td>
                                <td style="color: #f1f5f9;">${escapeHtml(l.raw_title)}</td>
                                <td style="color: var(--accent-cyan); font-weight: 700;">₹${Number(l.price || 0).toLocaleString('en-IN')}</td>
                                <td style="color: var(--text-secondary); font-size: 0.8rem;">${escapeHtml(l.normalized_title)}</td>
                                <td><a href="${l.product_url}" target="_blank" class="btn-secondary" style="padding: 0.2rem 0.6rem; text-decoration: none; font-size: 0.8rem;">View</a></td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `).join('');
}
