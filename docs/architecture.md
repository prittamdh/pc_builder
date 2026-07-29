# PC Builder 2 - Architecture & System Design

## 1. Product & Store Identity

Every product across all 10 supported retailers is uniquely identified by the composite key:

```
(sid, pid)
```

- **`sid` (Store ID)**: Unique integer primary key representing a retailer store in `stores`.
- **`pid` (Product ID)**: Unique string slug or store identifier representing the product on the retailer's platform.

### Retailer Registry Mapping:

| `sid` | Retailer Name | Base Domain | Platform Engine | Category Pagination Endpoint Template |
| :---: | :--- | :--- | :--- | :--- |
| `1` | **MDComputers** | `mdcomputers.in` | Magento HTML | `catalogsearch/result/index/?p={page}&q={query}` |
| `2` | **PCStudio** | `pcstudio.in` | WooCommerce HTML | `?s={query}&post_type=product` |
| `3` | **Vedant Computers** | `vedantcomputers.com` | OpenCart HTML | `index.php?route=product/search&search={query}` |
| `4` | **PrimeABGB** | `primeabgb.com` | WooCommerce HTML | `page/{page}/?s={query}&post_type=product` |
| `6` | **EliteHubs** | `elitehubs.com` | Shopify JSON API | `{query}/products.json?limit=250&page={page}` |
| `7` | **Clarion Computers** | `shop.clarioncomputers.in` | FleetCart PWA API | `products?category={query}&page={page}` |
| `8` | **Computech Store** | `computechstore.in` | WooCommerce HTMX | `product-category/{query}/?page={page}&sort=newest` |
| `9` | **TPS Tech** | `tpstech.in` | Shopify JSON API | `{query}/products.json?limit=250&page={page}` |
| `10` | **ModxComputers** | `modxcomputers.com` | Next.js App Router | `{query}?in_stock=true&page={page}` |
| `11` | **TLG Gaming** | `tlggaming.com` | OpenCart Journal 3 | `{query}&page={page}` |

---

## 2. Database Schema & Models

### Core Relational Tables:

1. **`stores`**: Stores domain name, base URL, search/product config JSON, active flag.
2. **`products`**: Uniquely constrained on `(sid, pid)`. Stores `name`, `product_url`, `image_url`, `brand`, `category`, `price`, `mrp`, `in_stock`.
3. **`price_history`**: Snapshots of product prices over time (`product_id`, `price`, `mrp`, `in_stock`, `scraped_at`).
4. **`scrape_targets`**: Scheduled targets (`store_id`, `target_value`, `schedule_config`, `next_scrape_at`).
5. **`product_targets`**: Many-to-many link between products and scrape targets (`product_id`, `target_id`).

### Component Specification Schema (9 Normalized Spec Tables):

- **`cpu_specs`**: `socket`, `cores`, `threads`, `base_clock_ghz`, `boost_clock_ghz`, `tdp_w`, `integrated_graphics`.
- **`gpu_specs`**: `chipset`, `vram_gb`, `vram_type`, `tdp_w`, `recommended_psu_w`, `length_mm`.
- **`motherboard_specs`**: `socket`, `chipset`, `form_factor`, `ram_type`, `ram_slots`, `max_ram_gb`.
- **`ram_specs`**: `ram_type` (DDR4/DDR5), `capacity_gb`, `speed_mhz`, `latency`, `kit_count`.
- **`ssd_specs`**: `form_factor` (M.2, 2.5"), `interface` (NVMe, SATA), `capacity_gb`, `gen_version` (Gen3, Gen4, Gen5).
- **`psu_specs`**: `wattage_w`, `efficiency_rating` (80+ Bronze, Gold), `modularity`.
- **`cabinet_specs`**: `form_factor_support`, `max_gpu_length_mm`, `included_fans`.
- **`cooler_specs`**: `cooler_type` (Air, Liquid), `radiator_size_mm`, `supported_sockets`, `max_tdp_w`.
- **`monitor_specs`**: `screen_size_inch`, `resolution`, `refresh_rate_hz`, `panel_type`.

---

## 3. Data Integrity & In-Stock Guard

1. **100% In-Stock Guard**: Out-of-stock items (`in_stock = False`) are rejected at the `SearchService.save()` layer.
2. **Target Category Enforcement**: `products.category` is populated directly from target-level category definitions, eliminating umbrella categories like `"Accessories"`.