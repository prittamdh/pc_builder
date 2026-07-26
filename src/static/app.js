/* PC Builder 2 - Application Client Logic */

const state = {
  stores: [],
  storeMap: {},
  query: 'rtx',
  selectedStore: '',
  inStockOnly: '',
  minPrice: '',
  maxPrice: '',
  debounceTimer: null,
};

// DOM Elements
const searchInput = document.getElementById('search-input');
const storeFilter = document.getElementById('store-filter');
const stockFilter = document.getElementById('stock-filter');
const minPriceInput = document.getElementById('min-price-input');
const maxPriceInput = document.getElementById('max-price-input');
const productsGrid = document.getElementById('products-grid');
const resultsCount = document.getElementById('results-count');
const activeStoresCount = document.getElementById('active-stores-count');
const totalProductsCount = document.getElementById('total-products-count');

const historyModal = document.getElementById('history-modal');
const modalCloseBtn = document.getElementById('modal-close-btn');
const modalProductTitle = document.getElementById('modal-product-title');
const modalProductSubtitle = document.getElementById('modal-product-subtitle');
const priceChartSvg = document.getElementById('price-chart-svg');

// Format Currency
function formatCurrency(val) {
  if (val === null || val === undefined) return 'N/A';
  return '₹' + Number(val).toLocaleString('en-IN');
}

// Fetch Active Stores
async function loadStores() {
  try {
    const res = await fetch('/api/v1/stores');
    if (!res.ok) return;
    const stores = await res.json();
    state.stores = stores;
    
    storeFilter.innerHTML = '<option value="">All Stores</option>';
    stores.forEach(s => {
      state.storeMap[s.id] = s;
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = s.display_name;
      storeFilter.appendChild(opt);
    });

    if (activeStoresCount) {
      activeStoresCount.textContent = stores.length;
    }
  } catch (err) {
    console.error('Failed to load stores:', err);
  }
}

// Fetch Products from API
async function fetchProducts() {
  try {
    resultsCount.textContent = 'Searching items...';

    const params = new URLSearchParams();
    if (state.query) params.append('q', state.query);
    if (state.selectedStore) params.append('sid', state.selectedStore);
    if (state.inStockOnly) params.append('in_stock', 'true');
    if (state.minPrice) params.append('min_price', state.minPrice);
    if (state.maxPrice) params.append('max_price', state.maxPrice);
    params.append('size', '40');

    const res = await fetch(`/api/v1/products?${params.toString()}`);
    if (!res.ok) throw new Error('API error');
    
    const data = await res.json();
    renderProducts(data.items, data.total);
  } catch (err) {
    console.error('Failed to fetch products:', err);
    resultsCount.textContent = 'Failed to load products.';
    productsGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--accent-red);">Error fetching items from server.</div>';
  }
}

// Render Products Grid
function renderProducts(items, total) {
  resultsCount.textContent = `Found ${total} matching hardware items`;
  if (totalProductsCount) totalProductsCount.textContent = total;

  if (!items || items.length === 0) {
    productsGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 3rem;">No components found matching your search.</div>';
    return;
  }

  productsGrid.innerHTML = items.map(p => {
    const storeName = state.storeMap[p.sid]?.display_name || `Store #${p.sid}`;
    const imgUrl = p.image_url || 'https://via.placeholder.com/250x200?text=PC+Hardware';
    const stockClass = p.in_stock ? 'stock-in' : 'stock-out';
    const stockText = p.in_stock ? 'In Stock' : 'Out of Stock';

    return `
      <div class="product-card">
        <div class="card-img-container">
          <span class="store-badge">${storeName}</span>
          <img src="${imgUrl}" alt="${p.name}" class="card-img" onerror="this.src='https://via.placeholder.com/250x200?text=Hardware'">
        </div>
        <div class="card-body">
          <h3 class="card-title" title="${p.name}">${p.name}</h3>
          
          <div class="card-price-group">
            <div>
              <span class="card-price">${formatCurrency(p.current_price)}</span>
              ${p.current_mrp ? `<span class="card-mrp">${formatCurrency(p.current_mrp)}</span>` : ''}
            </div>
            <span class="stock-tag ${stockClass}">${stockText}</span>
          </div>

          <div class="card-actions">
            <a href="${p.product_url}" target="_blank" rel="noopener" class="btn btn-primary">
              View Store ➔
            </a>
            <button class="btn btn-outline" onclick="openPriceHistory(${p.id}, '${escapeQuotes(p.name)}', '${storeName}')">
              History
            </button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function escapeQuotes(str) {
  return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// Open Price History Chart Modal
async function openPriceHistory(productId, productName, storeName) {
  modalProductTitle.textContent = productName;
  modalProductSubtitle.textContent = `Historical price trends from ${storeName}`;
  priceChartSvg.innerHTML = '<text x="300" y="100" text-anchor="middle" fill="#94a3b8">Loading history...</text>';
  
  historyModal.classList.add('active');

  try {
    const res = await fetch(`/api/v1/products/${productId}/history`);
    if (!res.ok) throw new Error('History error');
    const history = await res.json();
    renderPriceSvgChart(history);
  } catch (err) {
    priceChartSvg.innerHTML = '<text x="300" y="100" text-anchor="middle" fill="#ef4444">Failed to load price history.</text>';
  }
}

// Render SVG Trend Sparkline Chart
function renderPriceSvgChart(history) {
  if (!history || history.length === 0) {
    priceChartSvg.innerHTML = '<text x="300" y="100" text-anchor="middle" fill="#94a3b8">No historical snapshots recorded yet.</text>';
    return;
  }

  const padding = 40;
  const width = 600;
  const height = 200;

  const prices = history.map(h => Number(h.price));
  const minP = Math.min(...prices) * 0.95;
  const maxP = Math.max(...prices) * 1.05 || minP + 100;

  const points = history.map((h, i) => {
    const x = padding + (i / Math.max(1, history.length - 1)) * (width - padding * 2);
    const y = height - padding - ((Number(h.price) - minP) / (maxP - minP)) * (height - padding * 2);
    return `${x},${y}`;
  }).join(' ');

  let dotsSvg = history.map((h, i) => {
    const x = padding + (i / Math.max(1, history.length - 1)) * (width - padding * 2);
    const y = height - padding - ((Number(h.price) - minP) / (maxP - minP)) * (height - padding * 2);
    return `<circle cx="${x}" cy="${y}" r="4" fill="#6366f1"><title>₹${h.price} on ${new Date(h.scraped_at).toLocaleDateString()}</title></circle>`;
  }).join('');

  priceChartSvg.innerHTML = `
    <!-- Grid lines -->
    <line x1="${padding}" y1="${padding}" x2="${width - padding}" y2="${padding}" stroke="rgba(255,255,255,0.05)" />
    <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" stroke="rgba(255,255,255,0.1)" />
    
    <!-- Price Labels -->
    <text x="${padding}" y="${padding - 10}" fill="#94a3b8" font-size="12">Max: ₹${Math.round(maxP)}</text>
    <text x="${padding}" y="${height - 10}" fill="#94a3b8" font-size="12">Min: ₹${Math.round(minP)}</text>
    
    <!-- Sparkline -->
    <polyline fill="none" stroke="#6366f1" stroke-width="3" points="${points}" />
    ${dotsSvg}
  `;
}

// Event Listeners
searchInput.addEventListener('input', (e) => {
  clearTimeout(state.debounceTimer);
  state.query = e.target.value;
  state.debounceTimer = setTimeout(fetchProducts, 300);
});

storeFilter.addEventListener('change', (e) => {
  state.selectedStore = e.target.value;
  fetchProducts();
});

stockFilter.addEventListener('change', (e) => {
  state.inStockOnly = e.target.value;
  fetchProducts();
});

minPriceInput.addEventListener('input', (e) => {
  clearTimeout(state.debounceTimer);
  state.minPrice = e.target.value;
  state.debounceTimer = setTimeout(fetchProducts, 400);
});

maxPriceInput.addEventListener('input', (e) => {
  clearTimeout(state.debounceTimer);
  state.maxPrice = e.target.value;
  state.debounceTimer = setTimeout(fetchProducts, 400);
});

modalCloseBtn.addEventListener('click', () => {
  historyModal.classList.remove('active');
});

historyModal.addEventListener('click', (e) => {
  if (e.target === historyModal) {
    historyModal.classList.remove('active');
  }
});

// Initial Load
document.addEventListener('DOMContentLoaded', () => {
  loadStores();
  fetchProducts();
});
