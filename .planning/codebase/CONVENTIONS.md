---
last_mapped_commit: a803b6fdb669c9fb39477658b3e08c0a134f8cf2
last_mapped_at: 2026-09-24
---
# Coding Conventions

**Analysis Date:** 2026-09-24

## Naming Patterns

**Files:**
- Lowercase with underscores: `product_service.py`, `builder.py`, `price_extraction.py`
- Exception: SQLAlchemy model files follow class name patterns but use lowercase: `product.py` contains `Product` class
- Test files: `test_<subject>.py` (e.g., `test_matching.py`, `test_price_extraction.py`)
- Route modules: descriptive lowercase (e.g., `products.py`, `builder.py`, `images.py`)
- Schema files: `<entity>.py` under `api/schemas/` (e.g., `product.py`, `store.py`)
- Service files: `<domain>_service.py` under `services/` (e.g., `builder_service.py`, `product_service.py`)

**Functions:**
- Public functions: `snake_case` (e.g., `list_products`, `validate_build`, `get_logger`)
- Private functions: start with underscore followed by `snake_case` (e.g., `_order_by`, `_search_conditions`, `_rank_candidates`)
- Nested helper functions: `snake_case` with descriptive names (e.g., `sort_key`, `_card`)
- API route handlers: verb + noun in `snake_case` (e.g., `list_products`, `validate_build`, `load_build`)

**Variables:**
- `snake_case` for all variables (e.g., `selected_product_ids`, `current_price`, `database_url`)
- Constants: UPPERCASE_WITH_UNDERSCORES (e.g., `SORT_OPTIONS`, `SLOT_CATEGORY`, `MAX_RETRIES`)
- Private module-level variables: start with underscore (e.g., `_SITE_CONFIG`, `_PSU_TIER_ORDER`)
- Boolean parameters/attributes often prefixed with `is_` or `in_` or `include_` (e.g., `in_stock`, `is_cpu_legacy`, `include_legacy`)

**Types:**
- PascalCase for all class names (e.g., `Product`, `ProductService`, `CompatibilityEngine`, `CandidateRequest`)
- SQLAlchemy model classes: PascalCase, singular names (e.g., `Product`, not `Products`)
- Pydantic model classes: descriptive PascalCase (e.g., `ProductOut`, `ProductListResponse`, `CandidateRequest`, `SaveBuildRequest`)
- Enum classes: PascalCase (e.g., `TargetType`, `ScheduleType`)
- Enum values: UPPERCASE (e.g., `TargetType.SEARCH`, `ScheduleType.DAILY`)

## Code Style

**Formatting:**
- No explicit formatter configured (pyproject.toml only specifies pytest)
- Implicit style follows PEP 8 conventions
- Line length appears flexible (observations range 80-120+ characters)
- Indentation: 4 spaces (Python standard)

**Import Organization:**
1. Standard library imports (e.g., `import os`, `from pathlib import Path`)
2. Third-party imports (e.g., `from fastapi import`, `from sqlalchemy import`)
3. Local application imports (e.g., `from api.deps import`, `from db.models.product import`)
- Each group separated by a blank line
- Within groups, imports are alphabetically ordered or logically grouped by module
- Example from `src/api/routes/products.py`:

```python
import re
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import String, func, nullslast, or_, select

from api.deps import get_db
from api.filters import has_usable_price
```

**Linting:**
- No explicit linting configuration detected in pyproject.toml
- Code appears to follow implicit PEP 8 standards based on observation

## Type Hints

**Pattern:**
- Type hints required for all function parameters and return types
- Union types use `|` syntax (Python 3.10+): `str | None`, `int | None`, `list[int]`
- Optional fields in Pydantic models: `field_name: str | None = None`
- SQLAlchemy 2.0 mapped columns use `Mapped[Type]` annotation
- Example from `src/api/routes/products.py`:

```python
def list_products(
    q: str | None = Query(None, description="Search query string"),
    sid: int | None = Query(None, description="Filter by store ID"),
    min_price: Decimal | None = Query(None, description="Minimum current price"),
    sort: str = Query("recent", description="Result ordering"),
    page: int = Query(1, ge=1, description="Page number"),
) -> ProductListResponse:
```

## Error Handling

**Patterns:**
- FastAPI routes: raise `HTTPException` with appropriate status codes
  - Status 400 for validation/bad request errors
  - Status 404 for not found errors
  - Include descriptive `detail` message for debugging
  - Example from `src/api/routes/builder.py`:
  ```python
  if not selections:
      raise HTTPException(status_code=400, detail="Cannot save an empty build.")
  if unknown_slots:
      raise HTTPException(status_code=400, detail=f"Unknown slots: {sorted(unknown_slots)}")
  ```

- Non-API code: raise standard Python exceptions
  - `KeyError` for missing configuration (e.g., unknown site: `raise KeyError(f"Unknown site: {site}")`)
  - `ValueError` for invalid parameter values
  - Custom exceptions minimal/unused (exceptions.py is empty)

- Database operations: let SQLAlchemy exceptions propagate or wrap in HTTPException at API boundary
- Import errors during compatibility checks: wrapped in try/except with conditional imports for backward compatibility

## Logging

**Framework:** Standard Python `logging` module

**Setup:**
- Centralized in `src/common/logger.py`
- Configured with basicConfig in logger module
- File and stream handlers both enabled
- Example:

```python
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
```

**Patterns:**
- Call `get_logger(__name__)` at module level to create logger instance
- Use logger for informational, warning, and error messages
- Log files written to `logs/pc_builder.log`
- Log level configurable via `LOG_LEVEL` env var (default: INFO)

## Comments

**When to Comment:**
- Explain **why** decisions were made, not **what** code does (code is self-documenting)
- Describe non-obvious edge cases and design rationale
- Mark workarounds or temporary solutions
- Document assumptions about external data (e.g., store HTML structure, API contracts)

**Style:**
- Single-line comments for brief explanations: `# Comment here`
- Multi-line sections: indent consistently with code
- Example from `src/api/routes/products.py`:

```python

# Deliberately no "discount" option. MRP is widely inflated by Indian retailers to

# manufacture a headline discount, so ordering by (mrp - price) would rank the least

# honest listings first - the opposite of what this tool is for.

SORT_OPTIONS = ("recent", "price_asc", "price_desc", "name_asc")
```

**Module-level Docstrings:**
- Always include for files with substantial functionality
- Example from `src/common/logger.py`:

```python
"""
Application logger configuration.
"""
```

**JSDoc/TSDoc:**
- Use Python docstrings instead (no JSDoc/TSDoc)
- Triple-quoted strings for function and class documentation

## Function Design

**Size:** 
- Aim for focused functions with single responsibility
- Private helper functions created for complex logic
- Example: `_order_by()`, `_search_conditions()`, `_rank_candidates()` are all private helpers that clarify intent

**Parameters:**
- Limit to 3-5 parameters for clarity; use dataclasses/Pydantic models for more complex requirements
- Use named parameters with type hints
- Avoid boolean flags; prefer descriptive parameter names (e.g., `include_legacy` instead of `show_all`)
- Example from `src/api/routes/builder.py`:

```python
def list_slot_candidates(
    slot: str,
    selected_product_ids: list[int] = [],
    q: str | None = None,
    compatible_only: bool = True,
    group_by_model: bool = True,
    db: Session = Depends(get_db),
) -> list[dict]:
```

**Return Values:**
- Explicitly type-hint all return values
- Return None for operations with side effects (e.g., `save_build`)
- Return data objects (Pydantic models or ORM models) from queries
- Raise exceptions rather than returning error codes

## Module Design

**Exports:**
- Keep module public interface clear with well-named functions/classes
- Private functions start with underscore
- No `__all__` declarations observed, but could be used for clarity

**Barrel Files:**
- Minimal use observed
- `src/common/enums/__init__.py` imports enum classes for cleaner imports
- Pattern: `from common.enums import TargetType` instead of `from common.enums.target_type import TargetType`

**File Organization:**
- Each file has a single responsibility or tight cohesion
- Models in `db/models/`, services in `services/`, routes in `api/routes/`
- Configuration isolated in `configs/`
- Common utilities in `common/`
- Database layer separated from domain/business logic

## SQLAlchemy Patterns

**Model Definition:**
- Use SQLAlchemy 2.0 declarative mapping with `Mapped` type hints
- Inherit from `Base` (defined in `db/base.py`)
- Include mixins for common fields (e.g., `TimestampMixin` for `created_at`, `updated_at`)
- Add descriptive comments for non-obvious fields
- Example from `src/db/models/product.py`:

```python
class Product(Base, TimestampMixin):
    __tablename__ = "products"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Store specific unique identifier
    pid: Mapped[str] = mapped_column(String(255), nullable=False)
    # Production/Standardized User-facing Category
    p_category: Mapped[str | None] = mapped_column(String(255), index=True)
```

**Query Patterns:**
- Use `select()` from SQLAlchemy 2.0 (not `query()`)
- Use `db.scalars()` for fetching multiple rows, `db.scalar()` for single row
- Apply filters with `.where()` method
- Example from `src/api/routes/products.py`:

```python
db.scalars(
    select(Product)
    .where(or_(*conditions))
    .order_by(*_order_by(sort))
    .offset((page - 1) * size)
    .limit(size)
)
```

## Pydantic Patterns

**Schema Definition:**
- Set `model_config = ConfigDict(from_attributes=True)` to convert ORM models to schemas
- Use field defaults for optional fields: `field: str | None = None`
- Document non-obvious fields with comments
- Example from `src/api/schemas/product.py`:

```python
class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    # None for ordinary sealed stock; "open_box" / "repacked" / "refurbished" otherwise.
    condition: str | None = None
    specifications: dict | None = None
```

**Validation:**
- Pydantic handles basic type validation automatically
- Use `Query()` from FastAPI for request validation (e.g., min/max values, descriptions)
- Example from `src/api/routes/products.py`:

```python
page: int = Query(1, ge=1, description="Page number"),
size: int = Query(20, ge=1, le=100, description="Items per page"),
```

---

*Convention analysis: 2026-09-24*
