# PC Builder - Architecture

## Product Identity

Every store assigns a unique identifier to each product.

This identifier may be:
- Amazon ASIN
- Flipkart PID
- Product slug
- Internal product id
- SKU / Manufacturer Part Number

The application refers to this identifier as **pid**.

The only requirement is:

> The same pid must identify the same product across every page of a store
> (search page, category page, product page, API response, etc.).

The application does not care how the store generates the pid.

---

## Store Identity

Every store is assigned a numeric identifier.

Examples:

| sid | Store |
|-----|--------|
| 1 | Amazon |
| 2 | Flipkart |
| 3 | MDComputers |
| 4 | Vedant Computers |
| 5 | PCStudio |
| 6 | PrimeABGB |

---

## Product Identity Rule

Products are uniquely identified by

```
(sid, pid)
```

Examples

```
Amazon
sid = 1
pid = B005W3BR2A

Flipkart
sid = 2
pid = REBGG48NEQDEWA5Z

MDComputers
sid = 3
pid = deepcool-le-360mm-liquid-cooler-r-le360-bkammc-g-2
```

---

## Database Design

Products

```
id              (internal primary key)
sid
pid
name
product_url
image_url
brand
category
created_at
updated_at
```

Constraint

```
UNIQUE (sid, pid)
```

Price History

```
id
product_id
price
mrp
in_stock
scraped_at
```

`product_id` references the internal database primary key.

---

## Scraping Flow

Search Page

```
Search Page
    ↓
SearchResult
    ↓
SearchService
    ↓
Product
    ↓
PriceHistory
```

Product Page

```
Product Page
    ↓
Product
    ↓
ProductService
    ↓
Update Product
```

---

## Parser Responsibility

Every parser must return a pid.

Examples

Amazon

```
pid = ASIN
```

Flipkart

```
pid = PID
```

MDComputers

```
pid = slug
```

Vedant

```
pid = slug
```

PCStudio

```
pid = slug
```

PrimeABGB

```
pid = slug
```

If a better identifier becomes available later, only that parser changes.

The database schema and business logic remain unchanged.