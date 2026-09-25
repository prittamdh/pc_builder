---
last_mapped_commit: a803b6fdb669c9fb39477658b3e08c0a134f8cf2
last_mapped_at: 2026-09-24
---
# Testing Patterns

**Analysis Date:** 2026-09-24

## Test Framework

**Runner:**
- pytest 8.4.0+
- Config: `pyproject.toml` with `[tool.pytest.ini_options]`
- Test discovery path: `tests/`

**Assertion Library:**
- pytest's built-in `assert` statements (standard Python assertions)
- No external assertion library (e.g., not using pytest-assertions or Hamcrest)

**Run Commands:**

```bash

# Run all tests

pytest

# Run tests matching a pattern

pytest tests/test_matching.py

# Run specific test class or function

pytest tests/test_matching.py::TestThermalMaterialNotACooler::test_thermal_paste_is_accessory

# Watch mode (requires pytest-watch or similar)

pytest --looponfail

# Verbose output

pytest -v

# Show captured output

pytest -s
```

**Configuration:**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

## Test File Organization

**Location:**
- Co-located with source: tests in separate `tests/` directory (not alongside source code)
- Mirror source structure partially: `tests/test_<module>.py` for major components

**Naming:**
- Test files: `test_<subject>.py` (e.g., `test_matching.py`, `test_price_extraction.py`, `test_frontend_e2e.py`)
- Test functions: `test_<specific_behavior>` (e.g., `test_title_formatting_variance_same_key`)
- Test classes: PascalCase starting with `Test` (e.g., `TestThermalMaterialNotACooler`, `TestIntelGeneration`)

**Structure:**

```
tests/
├── test_all_stores.py           # Integration tests for multi-store parsing
├── test_compatibility_filtering.py
├── test_compatibility_rules.py
├── test_database.py             # (empty, DB tests skipped - live DB requirement)
├── test_form_factor.py
├── test_frontend_e2e.py         # End-to-end browser tests with Playwright
├── test_image_proxy.py
├── test_legacy_policy.py        # CPU/motherboard/RAM legacy part classification
├── test_matching.py             # Canonical key building, title parsing
├── test_motherboard_identity.py
├── test_price_extraction.py     # Parser regression tests for price/MRP
├── test_price_freshness.py
├── test_product_repository.py
├── test_scrapers.py
├── test_services.py             # (empty)
└── test_spec_value_normalizer.py # Spec field normalization tests
```

## Test Structure

**Suite Organization:**

```python

# From tests/test_matching.py

def test_title_formatting_variance_same_key():
    """Verify different title formatting across stores produce the exact same canonical key."""
    title1 = "AMD Ryzen 9 9900X Processor"
    title2 = "RYZEN9-9900X"
    
    key1 = make_canonical_key_string("CPU", build_canonical_key(title1, "CPU"))
    key2 = make_canonical_key_string("CPU", build_canonical_key(title2, "CPU"))
    
    assert key1 == key2 == "cpu:amd:ryzen_9_9900x"

class TestThermalMaterialNotACooler:
    """Thermal paste ships under the cooler category at several stores, but it can't
    fill a build's cooler slot."""

    def test_thermal_paste_is_accessory(self):
        from matching.category_classifier import CategoryClassifier as C
        assert C.get_p_category("CPU Cooler", "Noctua NT-H2 3.5g AM5 Edition Thermal Paste") == "Accessories"

    def test_real_coolers_unaffected(self):
        from matching.category_classifier import CategoryClassifier as C
        assert C.get_p_category("CPU Cooler", "Deepcool AK620 Dual Tower CPU Air Cooler") == "CPU Cooler"
```

**Patterns:**
- Standalone test functions for simple assertions
- Test classes (`class Test*:`) to group related test methods (logical cohesion)
- Docstrings on all test functions/classes explaining what they verify and why it matters
- Setup: imports and fixture calls at beginning of test or in class method
- Teardown: minimal (pytest fixtures handle cleanup)
- Assertions: simple `assert` statements, often with inline failure messages

## Fixtures

**Framework:** pytest fixtures (standard pytest, not custom factory libraries)

**Common Fixtures:**

From `tests/test_frontend_e2e.py`:

```python
@pytest.fixture(scope="module")
def base_url():
    """Boot the real app on a scratch port, so tests never touch the dev server."""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--app-dir", str(SRC)],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.5)
    else:
        proc.terminate()
        pytest.skip("app did not start")
    
    yield url
    proc.terminate()
    proc.wait(timeout=10)

@pytest.fixture(scope="module")
def browser():
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            yield b
            b.close()
    except Exception as exc:
        pytest.skip(f"chromium unavailable: {exc}")

@pytest.fixture
def page(browser, base_url):
    pg = browser.new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(base_url, wait_until="networkidle")
    pg.console_errors = errors
    yield pg
    pg.close()
```

**Patterns:**
- Fixture scope: `module` for expensive setup (e.g., starting app server, browser), default (function) otherwise
- Yield-based fixtures for setup/teardown: setup before `yield`, cleanup after
- Graceful degradation: `pytest.skip()` when dependencies unavailable (e.g., Playwright browser not installed)
- Dependency injection: fixtures accepted as parameters to other fixtures or test functions

From `tests/test_price_extraction.py`:

```python
@pytest.fixture
def parser():
    return GenericParser(
        Store(
            id=8,
            name="computechstore",
            display_name="Computech Store",
            domain="computechstore.in",
            base_url="https://computechstore.in",
            currency="INR",
            currency_symbol="₹",
            search_config={},
            product_config={},
            active=True,
        )
    )
```

**Location:**
- Defined inline in test files (`tests/test_<module>.py`)
- No `conftest.py` file (fixtures not shared across test modules)
- Simple fixtures with single responsibility

## Parametrized Tests

**Framework:** `@pytest.mark.parametrize()`

**Pattern:**

```python

# From tests/test_legacy_policy.py

class TestIntelGeneration:
    def test_four_digit_uses_one_leading_digit(self):
        assert intel_core_generation("3220") == 3
        assert intel_core_generation("9350KF") == 9
        assert intel_core_generation("8100") == 8

    def test_five_digit_uses_two_leading_digits(self):
        assert intel_core_generation("10105") == 10
        assert intel_core_generation("12100F") == 12
        assert intel_core_generation("14600K") == 14
```

Or parametrized:

```python

# From tests/test_spec_value_normalizer.py

class TestBrands:
    @pytest.mark.parametrize("value, expected", [
        ("AsRock", "ASRock"), ("Asrock", "ASRock"), ("ASRock", "ASRock"),
        ("TEAMGROUP", "TeamGroup"), ("Teamgroup", "TeamGroup"),
        ("Team Group", "TeamGroup"),
        ("G.SKILL", "G.Skill"), ("G Skill", "G.Skill"), ("Gskill", "G.Skill"),
        ("WD", "Western Digital"), ("Western Digital", "Western Digital"),
        ("Patriot Memory", "Patriot"),
        ("Hynix", "SK Hynix"), ("SK Hynix", "SK Hynix"),
        ("PROLAB DESIGN", "ProLab Design"), ("Prolab", "ProLab Design"),
        ("Ant", "Ant Esports"),
        ("Thermaltek", "Thermaltake"),  # A genuine typo in the catalog
    ])
    def test_spelling_variants_collapse(self, value, expected):
        assert norm("brand", value) == expected
```

**Usage:**
- Combine multiple test cases into single parametrized test to reduce boilerplate
- Each parameter tuple becomes one test case (reported separately in pytest output)
- Use `@pytest.mark.parametrize()` with list of tuples as parameter values
- Supports multiple parameter sets on same test

## Test Data Helpers

**Factory Pattern:**

```python

# From tests/test_price_extraction.py

def _card(title: str, price: str, mrp: str | None = None) -> str:
    """A listing card shaped like the real one.
    
    Matches what computechstore.in actually serves, checked live on 2026-08-17:
    the title comes first, amounts carry no thousands separators, the current price
    precedes the struck-through MRP, and there is no `.price` element in the card -
    which is why this parser reads the card text rather than a selector.
    """
    mrp_html = f"<del>₹{mrp}</del>" if mrp else ""
    return f"""
    <div class="product">
      <div>
        <a href="https://computechstore.in/product/{title.lower().replace(' ', '-')}/">{title}</a>
        <span><ins>₹{price}</ins>{mrp_html}</span>
        <span>In Stock</span>
      </div>
    </div>
    """
```

**Location:**
- Helper functions prefixed with underscore (e.g., `_card`, `_free_port`)
- Defined in test file alongside tests that use them
- Contain docstrings explaining what test data they produce and why

## Test Types

**Unit Tests:**
- Scope: Test individual functions in isolation (e.g., matching logic, spec normalization, parsing)
- Approach: Direct function calls with hardcoded inputs, no fixtures or dependencies
- Location: `tests/test_<module>.py` (most tests)
- Example:
  - `test_matching.py` tests canonical key building
  - `test_spec_value_normalizer.py` tests spec normalization
  - `test_legacy_policy.py` tests CPU/part classification rules

**Integration Tests:**
- Scope: Test interactions between components (parser + database, scraper + repository, routes + models)
- Approach: Use real or mock objects, may use fixtures for setup
- Location: Mixed in test files (e.g., test_price_extraction.py mocks Store objects)
- Example: `test_price_extraction.py` tests parser against HTML snippets matching real store output

**E2E Tests:**
- Scope: Test full user workflow via browser
- Framework: Playwright (sync API)
- Approach: Start real server on ephemeral port, launch browser, interact with UI
- Location: `tests/test_frontend_e2e.py`
- Graceful degradation: Skip entire module if Playwright binary not installed
- Setup/teardown: Fixtures handle server startup and browser lifecycle
- Example:

```python
playwright_api = pytest.importorskip("playwright.sync_api")

# If import fails, entire module is skipped

def test_search_results_appear(page):
    page.goto(base_url, wait_until="networkidle")
    page.fill("input[placeholder='Search']", "RTX 4070")
    page.click("button:has-text('Search')")
    # Verify UI state matches expectations
```

**Contract/Regression Tests:**
- Scope: Ensure parser doesn't regress on known bugs
- Approach: Test real data from live sites, cached as synthetic examples
- Location: `test_price_extraction.py`, `test_matching.py`
- Example from `test_price_extraction.py`:

```python
@pytest.mark.parametrize(
    "title, listed_price, decoy",
    [
        # Every decoy below is a real number that used to win over the actual price.
        # The first four were measured against the live site on 2026-08-17.
        ("Colorful iGame GeForce RTX 5080 Ultra OC 16GB", "154499", "5080"),
        ("Intel Core Ultra 5 245K LGA1851 Desktop Processor", "32500", "1851"),
    ],
)
def test_model_numbers_in_the_title_are_not_read_as_the_price(
    parser, title, listed_price, decoy
):
    results = parser._parse_computech_html(_card(title, listed_price))
    assert len(results) == 1
    assert int(results[0].price) == int(listed_price)
```

## Mocking

**Framework:** Not using pytest-mock or unittest.mock; instead passing real minimal objects

**Patterns:**
- Create minimal domain objects for test fixtures (e.g., `Store(...)` with required fields)
- Avoid mocking; prefer real small objects or in-memory implementations
- Example from `test_price_extraction.py`:

```python
@pytest.fixture
def parser():
    return GenericParser(
        Store(
            id=8,
            name="computechstore",
            display_name="Computech Store",
            domain="computechstore.in",
            base_url="https://computechstore.in",
            currency="INR",
            currency_symbol="₹",
            search_config={},
            product_config={},
            active=True,
        )
    )
```

**What NOT to Mock:**
- Core business logic that's being tested
- Database models (use fixtures with real ORM models instead)
- API schemas (test with real Pydantic models)

**What to Substitute:**
- External dependencies like HTTP clients (not observed in current tests)
- File I/O (not observed in current tests)
- Time/dates (not observed in current tests)

## Coverage

**Requirements:** Not enforced

**Configuration:** No coverage configuration in `pyproject.toml`

**Test Count:** 17 test files with 1,100+ lines of test code across them

**Observed Coverage Gaps:**
- `test_database.py` and `test_services.py` are empty (live DB requirement or deferred)
- Some integration paths may lack E2E coverage (rely on unit + integration tests)

**View Coverage:**

```bash

# Generate coverage report (if pytest-cov installed)

pytest --cov=src --cov-report=html

# Open htmlcov/index.html in browser

```

## Common Patterns

**Async Testing:**
- Not used (no async/await in test suite)
- Framework is synchronous (FastAPI can be tested sync with TestClient if needed)

**Error Testing:**

```python

# From tests/test_legacy_policy.py

def test_unparseable(self):
    assert intel_core_generation(None) is None
    assert intel_core_generation("") is None

# From tests/test_form_factor.py (inferred pattern)

def test_invalid_input_handled_gracefully(self):
    # Test function doesn't raise when given bad input
    result = some_function("")
    assert result is None or result == default_value
```

**Behavior-Driven Testing:**
- Test function names describe the behavior being verified
- Docstrings explain the business logic reason for the assertion
- Example from `test_matching.py`:

```python
def test_near_miss_different_ram_speed_must_not_match():
    """Verify two RAM kits differing only in speed produce different canonical keys."""
    ram1 = "G.Skill Trident Z5 RGB 32GB (16GBx2) DDR5 6000MHz CL30 RAM"
    ram2 = "G.Skill Trident Z5 RGB 32GB (16GBx2) DDR5 6400MHz CL30 RAM"
    
    key1 = make_canonical_key_string("RAM", build_canonical_key(ram1, "RAM"))
    key2 = make_canonical_key_string("RAM", build_canonical_key(ram2, "RAM"))
    
    assert key1 != key2
```

**Test Independence:**
- Each test is self-contained (no shared state between tests)
- Fixtures with `scope="function"` (default) guarantee fresh setup per test
- No order dependencies (pytest run order is deterministic but tests don't rely on it)

## System-Level Test Notes

**Live Database Avoidance:**
- Tests do not run against live database (marked as skipped/empty in `test_database.py`)
- Rationale: Tests focus on parsers, normalizers, business logic - not ORM integration
- If DB testing needed: would use SQLite in-memory or postgres container via Docker

**Path Setup:**
- Some tests insert source path into sys.path for imports:

```python

# From tests/test_legacy_policy.py

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from matching.legacy_policy import is_cpu_legacy, is_motherboard_legacy
```

**Documentation in Tests:**
- High-quality docstrings explain the "why" behind each test
- Real-world examples from catalogs and live websites referenced
- Example from `test_price_extraction.py`:

```python
"""Price-extraction regression tests for the Computech listing parser.

Found 2026-08-17 by adding price sorting to the catalog: the cheapest CPUs were all
priced at 1851, which is not a price but the LGA1851 socket in their titles. The card
regex made the rupee sign optional and took the first 4-6 digit number in the card,
and a card's text begins with the product title. 57% of that store's 1,906 products
carried a price identical to a number in their own name.

Verified live against computechstore.in the same day: "Colorful iGame GeForce RTX 5080
Ultra OC 16GB" parsed as Rs 5,080 against a real listed price of Rs 1,54,499.

These tests run offline against synthetic cards shaped like the real markup.
"""
```

---

*Testing analysis: 2026-09-24*
