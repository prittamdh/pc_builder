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
    
    try {
        const res = await fetch(url);
        const data = await res.json();
        
        let items = data.items || [];
        if (state.selectedCategory) {
            items = items.filter(p => (p.category || '').toUpperCase() === state.selectedCategory.toUpperCase());
        }

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
                <span class="product-badge">${p.brand || p.category || 'Component'}</span>
                ${p.image_url ? `<img class="product-img" src="${p.image_url}" alt="${p.name}">` : '<div class="product-img" style="display:flex;align-items:center;justify-content:center;color:#64748b;">No Image</div>'}
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
