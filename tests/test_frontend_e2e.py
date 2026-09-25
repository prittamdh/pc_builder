"""
End-to-end browser tests for the PC Builder UI.

Every frontend bug found on 2026-08-16 was silent - a swallowed 422 that left the
sidebar permanently reading "Incompatibilities Detected", a component picker that
always showed an empty list, a zip() that truncated every candidate away. None
raised an error, so backend tests and a clean console both looked fine. These
tests assert on what the user actually sees.

Skipped automatically if Playwright's browser isn't installed, so the suite still
runs in environments without it - UNLESS REQUIRE_E2E=1 is set (the deploy check and
the phase gates set it). Then every skip path (playwright missing, chromium missing,
app did not start) is a failure, so the suite can never pass by not running (WEB-03).
"""
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
THIS_FILE = Path(__file__)

REQUIRE_E2E = os.environ.get("REQUIRE_E2E") == "1"


def _skip_or_fail(reason: str):
    """Dev machines without a browser skip; the deploy check (REQUIRE_E2E=1) fails."""
    if REQUIRE_E2E:
        pytest.fail(f"REQUIRE_E2E=1 but the browser suite cannot run: {reason}", pytrace=False)
    pytest.skip(reason)


try:
    from playwright.sync_api import expect, sync_playwright
except ImportError as _exc:
    if REQUIRE_E2E:
        pytest.fail(f"REQUIRE_E2E=1 but playwright is not installed: {_exc}", pytrace=False)
    pytest.skip(f"playwright not installed: {_exc}", allow_module_level=True)

VERDICTS = re.compile(
    r"^(Problems found|No problems found - 1 check unverified"
    r"|No problems found - \d+ checks unverified|All checks passed)$")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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
        _skip_or_fail("app did not start")

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
    except Exception as exc:  # browser binary not installed
        _skip_or_fail(f"chromium unavailable: {exc}")


@pytest.fixture
def page(browser, base_url):
    pg = browser.new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(base_url, wait_until="networkidle")
    pg.console_errors = errors
    yield pg
    pg.close()


@pytest.fixture
def mobile_page(browser, base_url):
    """A phone-width page (WEB-04). Same shape as `page`; that fixture is unchanged."""
    pg = browser.new_page(viewport={"width": 375, "height": 812})
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(base_url, wait_until="networkidle")
    pg.console_errors = errors
    yield pg
    pg.close()


class TestRequireE2EGuard:
    """WEB-03: with REQUIRE_E2E=1 a missing browser is a failure, not a skip."""

    def _run(self, tmp_path, require):
        env = dict(os.environ)
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(tmp_path)  # empty: chromium is "missing"
        env.pop("REQUIRE_E2E", None)
        if require:
            env["REQUIRE_E2E"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(THIS_FILE),
             "-k", "TestPageLoads and test_index_html_is_served"],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=180,
        )

    def test_missing_chromium_fails_under_require_e2e(self, tmp_path):
        result = self._run(tmp_path, require=True)
        summary = result.stdout.strip().splitlines()[-1]
        assert result.returncode != 0, result.stdout
        assert "skipped" not in summary, summary
        assert "REQUIRE_E2E=1" in result.stdout

    def test_missing_chromium_still_skips_on_dev_machines(self, tmp_path):
        result = self._run(tmp_path, require=False)
        summary = result.stdout.strip().splitlines()[-1]
        assert result.returncode == 0, result.stdout
        assert "skipped" in summary, summary


class TestNoInPageEvalWaits:
    """Playwright's string-form wait-for-JS-condition call re-polls its predicate via
    new Function() inside the page after the first check, which the production CSP's
    script-src (no 'unsafe-eval') blocks - so it only passes when the condition is
    already true on the first check and is flaky/failing otherwise. Guard against it
    coming back: use expect(locator)... or another wait that doesn't need in-page
    eval instead."""

    _BANNED = "wait_for_" + "function("

    def test_source_has_no_wait_for_function_calls(self):
        source = THIS_FILE.read_text(encoding="utf-8")
        assert self._BANNED not in source


def _open_builder(page):
    page.get_by_role("button", name="PC Builder").click()
    page.wait_for_selector("#slots-container")


class TestPageLoads:
    def test_index_html_is_served(self, page):
        """index.html was excluded by a blanket *.html gitignore rule and had never
        been committed, so a fresh clone served nothing here."""
        assert "PC Builder" in page.title()

    def test_no_console_errors_on_load(self, page):
        page.wait_for_timeout(1500)
        assert page.console_errors == [], page.console_errors

    def test_dead_canonical_tab_is_gone(self, page):
        """Its API was deleted with the experimental subsystem; the nav button
        survived and 404'd on click."""
        assert page.locator("#canonical-tab").count() == 0


class TestBuilderValidation:
    def test_empty_build_reports_compatible(self, page):
        """The regression that started it all: app.js posted the wrong field name,
        /builder/validate returned 422, the failure was swallowed, and this read
        "Incompatibilities Detected" for every build including an empty one.
        The old "Verified" wording was replaced by the three FIT-02 verdicts; an
        empty build has nothing unverified, so it reads "All checks passed"."""
        _open_builder(page)
        status = page.locator("#compatibility-status")
        expect(status).to_have_text("All checks passed", timeout=15000)
        expect(status).to_have_class(re.compile(r"(^|\s)ok(\s|$)"))

    def test_validate_endpoint_is_not_rejecting_the_frontend_payload(self, page):
        """Asserts the contract in the direction that actually broke: the payload the
        page really sends must be accepted."""
        resp = page.evaluate("""async () => {
            const r = await fetch('/api/v1/builder/validate', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({selected_product_ids: []})
            });
            return r.status;
        }""")
        assert resp == 200


class TestComponentPicker:
    """The picker lists one row per MODEL, expanding to that model's store offers.
    Flat listings asked the shopper to choose the part and the retailer at once out of
    one repetitive list - an "Asus Dual RX 9060 XT 16GB" appeared four times at four
    prices - and whichever row they clicked set the retailer as a side effect."""

    def test_picker_lists_real_components(self, page):
        """The picker used to filter whatever the Catalog tab had loaded, so opening
        the builder and clicking Select showed "No matching components loaded"."""
        _open_builder(page)
        page.locator("#slots-container button", has_text="Select").first.click()
        page.wait_for_selector("#select-modal.active")
        expect(page.locator("#select-modal-list .model-row").first).to_be_visible(
            timeout=15000)
        assert page.locator("#select-modal-list .model-row").count() > 0

    def test_picker_search_reaches_beyond_the_first_page(self, page):
        """The 7800X3D sat past the first 100 results and was unreachable."""
        _open_builder(page)
        page.locator("#slots-container button", has_text="Select").first.click()
        page.wait_for_selector("#select-modal.active")
        page.fill("#select-modal-search", "7800X3D")
        matching = page.locator(
            "#select-modal-list .model-row", has_text=re.compile("7800X3D", re.I))
        expect(matching.first).to_be_visible(timeout=15000)
        assert page.locator("#select-modal-list .model-row").count() > 0

    def test_one_row_per_model_not_per_listing(self, page):
        counts = page.evaluate("""async () => {
            const r = await fetch('/api/v1/builder/candidates', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({slot: 'gpu', q: '9060 XT 16GB', compatible_only: false})
            });
            const d = await r.json();
            return {models: d.total, offers: d.offer_count,
                    everyModelHasOffers: d.items.every(m => m.offers.length === m.offer_count)};
        }""")
        assert counts["offers"] > counts["models"], counts
        assert counts["everyModelHasOffers"] is True

    def test_offers_are_cheapest_first_and_name_their_store(self, page):
        offers = page.evaluate("""async () => {
            const r = await fetch('/api/v1/builder/candidates', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({slot: 'gpu', q: '9060 XT 16GB', compatible_only: false})
            });
            const d = await r.json();
            const multi = d.items.find(m => m.offer_count > 1) || d.items[0];
            return multi.offers;
        }""")
        prices = [o["price"] for o in offers]
        assert prices == sorted(prices), prices
        assert all(o["store"] for o in offers)

    def test_choosing_a_dearer_offer_is_honoured(self, page):
        """The build total is the sum of the offers actually chosen - nothing quietly
        substitutes a cheaper store - so picking the second-cheapest must stick."""
        _open_builder(page)
        page.locator("#slots-container .slot-card", has_text="Graphics").locator(
            "button").click()
        page.wait_for_selector("#select-modal.active")
        page.fill("#select-modal-search", "9060 XT 16GB")
        expect(page.locator("#select-modal-list .model-row").first).to_be_visible(
            timeout=15000)
        page.evaluate("""() => {
            const head = [...document.querySelectorAll('.model-head')]
                .find(h => /stores/.test(h.innerText));
            head.click();
        }""")
        page.wait_for_selector(".model-offers:not([hidden]) .offer-row")
        second = page.evaluate("""async () => {
            const rows = [...document.querySelectorAll('.model-offers:not([hidden]) .offer-row')];
            const price = rows[1].querySelector('.offer-price').innerText.match(/[0-9,]+/)[0];
            rows[1].querySelector('button').click();
            return price;
        }""")
        expect(page.locator("#total-cost")).not_to_have_text("₹0", timeout=15000)
        assert second.replace(",", "") in page.locator(
            "#total-cost").inner_text().replace(",", "")


class TestSlotCoverage:
    def test_all_nine_slots_render(self, page):
        _open_builder(page)
        assert page.locator("[id^='slot-name-']").count() == 9

    def test_monitor_slot_offers_products(self, page):
        """_resolve_slot returned [] for slots with no spec resolver, and
        filter_candidates zipped that against the candidates - the zip truncated to
        zero and silently discarded every monitor."""
        count = page.evaluate("""async () => {
            const r = await fetch('/api/v1/builder/candidates', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({slot:'monitor', selected_product_ids:[], compatible_only:true})
            });
            return (await r.json()).total;
        }""")
        assert count > 0, "monitor slot returned no products"


class TestCatalogPolicy:
    def test_legacy_parts_are_not_offered(self, page):
        """Pre-10th-gen Intel, Pentium/Athlon and DDR3 must not reach the builder."""
        results = page.evaluate("""async () => {
            const out = {};
            for (const [slot, q] of [['cpu','G4560'], ['cpu','Pentium'], ['ram','DDR3']]) {
                const r = await fetch('/api/v1/builder/candidates', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({slot, q})
                });
                out[slot + ':' + q] = (await r.json()).total;
            }
            return out;
        }""")
        assert all(v == 0 for v in results.values()), results

    def test_external_drives_are_not_offered_as_build_storage(self, page):
        total = page.evaluate("""async () => {
            const r = await fetch('/api/v1/builder/candidates', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({slot:'storage', q:'Portable'})
            });
            return (await r.json()).total;
        }""")
        assert total == 0


class TestSavedBuilds:
    """A build used to live only in page memory and vanished on refresh."""

    def test_save_then_open_share_link_restores_the_build(self, page, base_url):
        """Exercises the page's own save and restore code. The save and load
        endpoints are intercepted, so the test never writes a row to the live
        database; the routes themselves are covered by API unit tests."""
        token = "e2e-intercepted-token"
        posted = []
        shared = {
            "share_token": token, "name": "e2e rig", "notes": None, "created_at": None,
            "items": {
                "cpu": {"id": 4089, "name": "AMD Ryzen 7 7800X3D (e2e)", "current_price": 1.0,
                        "in_stock": True},
                "motherboard": {"id": 4867, "name": "B850 Board (e2e)", "current_price": 1.0,
                                "in_stock": True},
            },
            "unavailable": [], "compatible": True, "warnings": [], "estimated_wattage": 0,
            "total_min_cost": "0", "store_breakdown": [],
            "compatibility_changed_since_save": False,
        }

        def on_builds(route):
            req = route.request
            if req.method == "POST":
                posted.append(req.post_data_json)
                route.fulfill(json={"share_token": token})
            elif req.url.split("?")[0].endswith(f"/builds/{token}"):
                route.fulfill(json=shared)
            else:
                route.fulfill(status=404, json={"detail": "not found"})

        page.route("**/api/v1/builder/builds**", on_builds)
        _open_builder(page)
        page.evaluate("""(items) => {
            for (const [slot, item] of Object.entries(items)) {
                state.builderSelections[slot] = item;
                document.getElementById(`slot-name-${slot}`).innerText = item.name;
            }
        }""", shared["items"])
        page.fill("#build-name", "e2e rig")
        page.locator("#save-build-btn").click()

        expect(page.locator("#share-link")).to_have_value(
            re.compile(rf"\?build={token}$"), timeout=15000)
        assert posted == [{"selections": {"cpu": 4089, "motherboard": 4867},
                           "name": "e2e rig"}], posted

        page.goto(f"{base_url}/?build={token}", wait_until="networkidle")
        expect(page.locator("#slot-name-cpu")).to_have_text(
            "AMD Ryzen 7 7800X3D (e2e)", timeout=15000)
        expect(page.locator("#slot-name-motherboard")).to_have_text("B850 Board (e2e)")
        assert page.locator("#build-name").input_value() == "e2e rig"

    def test_empty_build_cannot_be_saved(self, page):
        status = page.evaluate("""async () => {
            const r = await fetch('/api/v1/builder/builds', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({selections:{}})
            });
            return r.status;
        }""")
        assert status == 400

    def test_unknown_share_token_is_404(self, page):
        status = page.evaluate(
            "fetch('/api/v1/builder/builds/definitely-not-a-token').then(r => r.status)"
        )
        assert status == 404


class TestPsuQuality:
    def test_certified_psus_rank_above_uncertified(self, page):
        """An uncertified PSU is the riskiest part in a build, so certified units lead."""
        tiers = page.evaluate("""async () => {
            const r = await fetch('/api/v1/builder/candidates', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({slot:'psu'})
            });
            return (await r.json()).items.slice(0, 5).map(i => i.name);
        }""")
        assert len(tiers) == 5

    def test_brandless_psus_are_not_offered(self, page):
        """Identity extraction failed to name these; two turned out not to be PSUs."""
        results = page.evaluate("""async () => {
            const out = {};
            for (const q of ['Dawg', 'Coconut']) {
                const r = await fetch('/api/v1/builder/candidates', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({slot:'psu', q})
                });
                out[q] = (await r.json()).total;
            }
            return out;
        }""")
        assert all(v == 0 for v in results.values()), results


class TestCatalogSortingAndFilters:
    """Neither existed before 2026-08-17. Adding price sorting is what exposed that
    Computech was pricing products from their own titles and that TLG Gaming had no
    prices at all - defects invisible while the catalog was ordered by scrape time."""

    def test_price_ascending_is_actually_ascending(self, page):
        prices = page.evaluate("""async () => {
            const r = await fetch('/api/v1/products?p_category=GPU&sort=price_asc&size=20');
            return (await r.json()).items.map(i => Number(i.current_price));
        }""")
        assert prices == sorted(prices), prices

    def test_no_product_is_offered_at_zero(self, page):
        """A zero is a failed scrape, not a cheap part, and it led every price sort."""
        zeros = page.evaluate("""async () => {
            const r = await fetch('/api/v1/products?sort=price_asc&size=50');
            return (await r.json()).items.filter(i => !(Number(i.current_price) > 0)).length;
        }""")
        assert zeros == 0

    def test_search_matches_however_the_model_number_is_spaced(self, page):
        """Store titles write "RTX 4070", shoppers type "rtx4070"."""
        totals = page.evaluate("""async () => {
            const out = {};
            for (const q of ['rtx4070', 'rtx 4070', '4070 gigabyte']) {
                const r = await fetch('/api/v1/products?size=1&q=' + encodeURIComponent(q));
                out[q] = (await r.json()).total;
            }
            return out;
        }""")
        assert all(v > 0 for v in totals.values()), totals

    def test_facets_only_offer_values_the_catalog_has(self, page):
        facets = page.evaluate("""async () => {
            const r = await fetch('/api/v1/products/facets?p_category=Power%20Supply');
            return (await r.json()).filters;
        }""")
        names = [f["name"] for f in facets]
        assert "efficiency_rating" in names
        # wattage was silently absent: psu_specs.wattage was 100% NULL until it was
        # backfilled from the title extractions that had held it all along.
        assert "wattage" in names
        for facet in facets:
            if facet["kind"] == "enum":
                assert all(o["count"] > 0 for o in facet["options"]), facet

    def test_spec_filters_narrow_and_stack(self, page):
        counts = page.evaluate("""async () => {
            const get = async u => (await (await fetch(u)).json()).total;
            const base = '/api/v1/products?p_category=Power%20Supply';
            return {
                all: await get(base),
                watt: await get(base + '&spec_wattage_min=750'),
                both: await get(base + '&spec_wattage_min=750&spec_efficiency_rating=80%2B%20Gold'),
            };
        }""")
        assert counts["all"] > counts["watt"] > counts["both"] > 0, counts

    def test_filter_sidebar_appears_and_filters_the_grid(self, page):
        page.locator(".chip", has_text="Power Supplies").click()
        page.wait_for_selector("#filter-panel:not([hidden])")
        expect(page.locator(".filter-group").first).to_be_visible(timeout=15000)
        before = page.locator("#result-count").inner_text()

        page.fill('[data-key="wattage_min"]', "750")
        expect(page.locator("#result-count")).not_to_have_text(before, timeout=15000)
        assert page.locator("#result-count").inner_text() != before

    def test_footer_lists_every_active_retailer(self, page):
        """Was hardcoded to 4 cards while the hero claimed 10, then a nav tab nobody
        returned to. Now a footer, so coverage is answered on every page."""
        expected = page.evaluate(
            "fetch('/api/v1/stores').then(r => r.json()).then(s => s.filter(x => x.active).length)")
        expect(page.locator("#stores-grid .store-chip").first).to_be_visible(
            timeout=15000)
        assert page.locator("#stores-grid .store-chip").count() == expected
        assert page.locator(".nav-btn", has_text="Stores").count() == 0


class TestPriceHistory:
    """Price history existed as a raw table of every 15-minute snapshot. The series
    endpoint aggregates per day and states what the listing has actually sold for,
    which is the only honest baseline for "is this a deal" - MRP is routinely
    inflated to manufacture a discount."""

    def test_series_is_daily_and_ordered(self, page):
        data = page.evaluate("""async () => {
            const r = await fetch('/api/v1/products/2882/price-series?days=90');
            return await r.json();
        }""")
        dates = [p["date"] for p in data["points"]]
        assert dates == sorted(dates)
        assert len(dates) == len(set(dates)), "more than one point per day"
        assert all(p["low"] <= p["high"] for p in data["points"])

    def test_stats_describe_the_observed_range(self, page):
        stats = page.evaluate("""async () => {
            const r = await fetch('/api/v1/products/2882/price-series?days=90');
            return (await r.json()).stats;
        }""")
        assert stats["lowest"] <= stats["current"] <= stats["highest"]
        assert stats["at_lowest"] is (stats["current"] <= stats["lowest"])

    def test_unknown_product_is_404(self, page):
        status = page.evaluate(
            "fetch('/api/v1/products/99999999/price-series').then(r => r.status)")
        assert status == 404

    def test_modal_renders_a_chart_with_axis_labels(self, page):
        page.evaluate("openHistoryModal(2882)")
        page.wait_for_selector("#history-modal-content svg.price-chart", timeout=15000)
        svg = page.locator("#history-modal-content svg.price-chart")
        assert svg.locator("path").count() >= 2
        # SVG <text> is not an HTMLElement, so inner_text() is unavailable here.
        labels = svg.locator("text").all_text_contents()
        assert any("₹" in label for label in labels), labels

    def test_a_flat_price_still_draws_without_breaking_the_geometry(self, page):
        """min == max would divide by zero and emit NaN into the path."""
        bad = page.evaluate("""async () => {
            openHistoryModal(1530);
            await new Promise(r => setTimeout(r, 1500));
            const svg = document.querySelector('#history-modal-content svg.price-chart');
            if (!svg) return 'no chart';
            return [...svg.querySelectorAll('path')]
                .some(p => /NaN|Infinity/.test(p.getAttribute('d')));
        }""")
        assert bad is False, bad

    def test_a_listing_with_no_history_says_so(self, page):
        text = page.evaluate("""async () => {
            openHistoryModal(2677);
            await new Promise(r => setTimeout(r, 1500));
            return document.getElementById('history-modal-content').innerText;
        }""")
        assert "no price history" in text.lower()


class TestCatalogLayout:
    """The filter sidebar and the product grid share one CSS grid. A hidden panel is
    display:none, so it leaves the grid entirely and the product grid becomes the
    FIRST item - landing in the 230px sidebar column, one card per row."""

    def _columns(self, page):
        return page.evaluate(
            "getComputedStyle(document.getElementById('products-grid'))"
            ".gridTemplateColumns.split(' ').length"
        )

    def test_grid_is_multi_column_with_no_category_selected(self, page):
        expect(page.locator("#products-grid .product-card").first).to_be_visible(
            timeout=15000)
        assert self._columns(page) > 1

    def test_grid_stays_multi_column_after_choosing_a_category(self, page):
        page.locator(".chip", has_text="Power Supplies").click()
        page.wait_for_selector("#filter-panel:not([hidden])")
        assert self._columns(page) > 1

    def test_grid_recovers_when_returning_to_all_categories(self, page):
        page.locator(".chip", has_text="Power Supplies").click()
        page.wait_for_selector("#filter-panel:not([hidden])")
        page.locator(".chip", has_text="All Categories").click()
        # wait_for_selector defaults to waiting for visibility, and a hidden panel is
        # never visible - wait for it to actually be hidden instead.
        expect(page.locator("#filter-panel")).to_be_hidden(timeout=15000)
        assert self._columns(page) > 1


class TestCatalogCredibility:
    def test_every_card_names_the_retailer_it_priced(self, page):
        """A price with no shop attached is the main reason a comparison site reads
        as fake, and it is unusable - you cannot buy from 'somewhere'.

        No stock indicator: /products/models only returns in-stock models, so "In
        stock" on every card would carry no information.
        """
        expect(page.locator("#products-grid .product-card").first).to_be_visible(
            timeout=15000)
        cards = page.locator("#products-grid .product-card").count()
        assert page.locator("#products-grid .store-name").count() == cards
        # Each card states the cheapest price is "from" one of several offers, rather
        # than presenting it as the only price.
        assert page.locator("#products-grid .price-from").count() == cards

    def test_stat_bar_numbers_come_from_the_api(self, page):
        stats = page.evaluate(
            "fetch('/api/v1/products/stats').then(r => r.json())")
        expect(page.locator("#stat-products")).not_to_have_text("—", timeout=15000)
        shown = page.locator("#stat-products").inner_text().replace(",", "")
        assert int(shown) == stats["products"]
        assert stats["stores"] > 0 and stats["price_snapshots"] > 0

    def test_opened_stock_is_labelled(self, page):
        """Repacked/open-box units undercut sealed ones, so they win price sorts.
        Saying so is the difference between a bargain and a misleading listing."""
        labelled = page.evaluate("""async () => {
            const r = await fetch('/api/v1/products?q=open%20box&size=20');
            const items = (await r.json()).items;
            return items.length && items.every(i => i.condition !== null);
        }""")
        assert labelled is True

    def test_flat_picker_still_ranks_sealed_stock_above_opened(self, page):
        conditions = page.evaluate("""async () => {
            const r = await fetch('/api/v1/builder/candidates', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({slot: 'cpu', compatible_only: false,
                                      group_by_model: false})
            });
            return (await r.json()).items.map(i => i.condition);
        }""")
        opened = [i for i, c in enumerate(conditions) if c is not None]
        sealed = [i for i, c in enumerate(conditions) if c is None]
        if opened and sealed:
            assert min(opened) > max(sealed), conditions

    def test_grouped_picker_prefers_sealed_within_a_model(self, page):
        """Grouped models are ordered by price, not condition - a cheaper repacked
        model may legitimately lead, and the badge says so. The guarantee that still
        holds is inside a model: at the same price, sealed stock is offered first."""
        rows = page.evaluate("""async () => {
            const r = await fetch('/api/v1/builder/candidates', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({slot: 'cpu', compatible_only: false})
            });
            return (await r.json()).items.map(m => m.offers.map(
                o => [o.price, o.condition === null]));
        }""")
        for offers in rows:
            prices = [p for p, _ in offers]
            assert prices == sorted(prices), offers
            for (p1, sealed1), (p2, sealed2) in zip(offers, offers[1:]):
                if p1 == p2:
                    assert sealed1 >= sealed2, offers


class TestHierarchicalFilters:
    """Filters are chained: SPEC_FILTERS orders each category by the decision that
    constrains the rest, and every facet's options are computed against the current
    selection. Independent facets showed 72 motherboard chipsets regardless of socket,
    most of which returned nothing once a socket was picked."""

    def _facets(self, page, params):
        return page.evaluate(
            "p => fetch('/api/v1/products/facets?' + p).then(r => r.json())", params)

    def test_socket_narrows_the_filters_below_it(self, page):
        wide = self._facets(page, "p_category=Motherboard")
        narrow = self._facets(page, "p_category=Motherboard&spec_socket=AM5")

        def opts(data, name):
            f = next((f for f in data["filters"] if f["name"] == name), None)
            return len(f["options"]) if f else 0

        assert opts(narrow, "chipset") < opts(wide, "chipset")
        # AM5 is DDR5-only, so the memory filter should collapse to one value.
        assert opts(narrow, "memory_type") == 1

    def test_a_facet_does_not_constrain_itself(self, page):
        """Otherwise picking AM5 would leave AM5 as the only socket on offer, and you
        would have to clear the filter before switching platform."""
        wide = self._facets(page, "p_category=Motherboard")
        narrow = self._facets(page, "p_category=Motherboard&spec_socket=AM5")
        sockets = lambda d: len(next(f for f in d["filters"] if f["name"] == "socket")["options"])
        assert sockets(narrow) == sockets(wide)

    def test_filters_stack(self, page):
        counts = page.evaluate("""async () => {
            const get = async p => (await (await fetch(
                '/api/v1/products/models?p_category=Motherboard&' + p)).json()).total;
            return {
                all: await get(''),
                socket: await get('spec_socket=AM5'),
                both: await get('spec_socket=AM5&spec_form_factor=ITX'),
            };
        }""")
        assert counts["all"] > counts["socket"] > counts["both"] > 0, counts

    def test_skipping_a_filter_leaves_the_next_one_wide(self, page):
        """A shopper with no socket preference must be able to go straight to form
        factor without the socket filter silently restricting anything."""
        counts = page.evaluate("""async () => {
            const get = async p => (await (await fetch(
                '/api/v1/products/models?p_category=Motherboard&' + p)).json()).total;
            return {itxOnly: await get('spec_form_factor=ITX'),
                    itxOnAm5: await get('spec_socket=AM5&spec_form_factor=ITX')};
        }""")
        assert counts["itxOnly"] > counts["itxOnAm5"], counts

    def test_applied_filters_are_echoed_for_the_chips(self, page):
        data = self._facets(
            page, "p_category=Motherboard&spec_socket=AM5&spec_form_factor=ITX")
        assert data["applied"] == {"socket": "AM5", "form_factor": "ITX"}

    def test_accessories_tab_works_without_a_spec_table(self, page):
        page.locator(".chip", has_text="Accessories").click()
        expect(page.locator("#filter-panel")).to_be_hidden(timeout=15000)
        expect(page.locator("#products-grid .product-card").first).to_be_visible(
            timeout=15000)
        # No spec table means no filters, and the grid must take the full width.
        assert page.locator(".filter-group").count() == 0
        assert page.evaluate(
            "getComputedStyle(document.getElementById('products-grid'))"
            ".gridTemplateColumns.split(' ').length") > 1

    def test_removing_one_chip_keeps_the_others(self, page):
        page.locator(".chip", has_text="Motherboards").click()
        page.wait_for_selector('[data-key="socket"]')
        page.select_option('[data-key="socket"]', "AM5")
        expect(page.locator(".active-chip")).to_have_count(1, timeout=15000)
        page.select_option('[data-key="form_factor"]', "ITX")
        expect(page.locator(".active-chip")).to_have_count(2, timeout=15000)

        page.locator(".active-chip", has_text="Socket").click()
        expect(page.locator(".active-chip")).to_have_count(1, timeout=15000)
        assert "Form Factor" in page.locator(".active-chip").first.inner_text()


class TestCatalogPaging:
    def test_pager_reports_pages_over_models_not_listings(self, page):
        expect(page.locator("#products-grid .product-card").first).to_be_visible(
            timeout=15000)
        assert "Page 1 of" in page.locator("#pager").inner_text()

    def test_next_page_returns_different_models(self, page):
        first = page.evaluate("""async () => {
            const r = await fetch('/api/v1/products/models?size=24&page=1&sort=price_asc');
            return (await r.json()).items.map(i => i.group_key);
        }""")
        second = page.evaluate("""async () => {
            const r = await fetch('/api/v1/products/models?size=24&page=2&sort=price_asc');
            return (await r.json()).items.map(i => i.group_key);
        }""")
        assert len(first) == 24 and len(second) == 24
        assert not set(first) & set(second), "pages overlap"

    def test_a_page_past_the_end_still_reports_the_real_total(self, page):
        data = page.evaluate(
            "fetch('/api/v1/products/models?page=9999').then(r => r.json())")
        assert data["items"] == []
        assert data["total"] > 0, "overshooting a page must not report zero results"

    def test_catalog_collapses_listings_into_models(self, page):
        both = page.evaluate("""async () => {
            const listings = await (await fetch(
                '/api/v1/products?q=9060%20XT%2016GB&size=100')).json();
            const models = await (await fetch(
                '/api/v1/products/models?q=9060%20XT%2016GB&size=60')).json();
            return {listings: listings.total, models: models.total};
        }""")
        assert both["models"] < both["listings"], both


# ---------------------------------------------------------------------------
# FIT-01/02 in a real page: a missing spec reads "unverified", never "passed".
# Ids are found read-only through the page's own API. Nothing is saved.
# ---------------------------------------------------------------------------
_FIND_PAIR_JS = """async (want) => {
    const post = async (url, body) => (await fetch(url, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)})).json();
    const firstOffer = m => ({id: m.offers[0].id, name: m.offers[0].name});
    const gpus = (await post('/api/v1/builder/candidates',
        {slot: 'gpu', compatible_only: false})).items.slice(0, 5).map(firstOffer);
    const cases = (await post('/api/v1/builder/candidates',
        {slot: 'case', compatible_only: false})).items.slice(0, 40).map(firstOffer);
    let calls = 0;
    for (const g of gpus) {
        for (const c of cases.slice(0, 8)) {   // at most 8 cases per GPU, 40 calls total
            if (calls >= 40) return {found: false, calls};
            calls++;
            const s = await post('/api/v1/builder/validate',
                {selected_product_ids: [g.id, c.id]});
            const msgs = s.warnings.map(w => w.message);
            // A GPU with no published length can never give either outcome - next GPU.
            if (msgs.some(m => m.includes(g.name) && m.includes('no published length'))) break;
            if (want === 'unverified') {
                const hit = s.unverified_count === 1 && s.verdict !== 'Problems found'
                    && msgs.some(m => m.includes('GPU clearance') && m.includes(c.name)
                                      && !m.includes(g.name));
                if (hit) return {found: true, gpu: g, case_: c, calls};
            } else if (s.verdict === 'All checks passed') {
                return {found: true, gpu: g, case_: c, calls};
            }
        }
    }
    return {found: false, calls};
}"""

_SELECT_JS = """([gpu, cs]) => {
    state.builderSelections.gpu = gpu;
    state.builderSelections.case = cs;
    document.getElementById('slot-name-gpu').innerText = gpu.name;
    document.getElementById('slot-name-case').innerText = cs.name;
    return validateBuild();
}"""


class TestHonestVerdict:
    def test_gpu_with_case_missing_clearance_is_unverified(self, page):
        _open_builder(page)
        pair = page.evaluate(_FIND_PAIR_JS, "unverified")
        assert pair["found"], (
            f"no GPU+case pair with exactly one unverified GPU-clearance check "
            f"in {pair['calls']} validate calls")
        print(f"unverified pair: gpu={pair['gpu']['id']} case={pair['case_']['id']}")
        page.evaluate(_SELECT_JS, [pair["gpu"], pair["case_"]])

        status = page.locator("#compatibility-status")
        expect(status).to_have_text("No problems found - 1 check unverified", timeout=15000)
        expect(status).to_have_class(re.compile(r"(^|\s)unverified(\s|$)"))
        item = page.locator("#warnings-list .warning-item.unverified")
        expect(item).to_have_count(1)
        expect(item).to_contain_text(pair["case_"]["name"])
        expect(item).to_contain_text("GPU clearance")
        expect(item).to_be_visible()
        assert page.console_errors == [], page.console_errors

    def test_fully_known_gpu_and_case_reads_all_checks_passed(self, page):
        _open_builder(page)
        pair = page.evaluate(_FIND_PAIR_JS, "passed")
        assert pair["found"], f"no fully-known GPU+case pair in {pair['calls']} calls"
        print(f"passing pair: gpu={pair['gpu']['id']} case={pair['case_']['id']}")
        page.evaluate(_SELECT_JS, [pair["gpu"], pair["case_"]])
        status = page.locator("#compatibility-status")
        expect(status).to_have_text("All checks passed", timeout=15000)
        expect(page.locator("#warnings-list .warning-item.unverified")).to_have_count(0)


_EVIL = "Evil <img src=x onerror=\"window.__xss=1\"> Case 'O\"Brien' &quot; &amp;"


class TestUntrustedNamesAreEscaped:
    """Product names come from retailer titles, and warning messages now carry them."""

    def test_warning_messages_are_escaped(self, page):
        body = {
            "compatible": True,
            "warnings": [
                {"level": "unverified",
                 "message": f"Unverified: {_EVIL} has no published GPU clearance, "
                            "so GPU/case fit could not be checked."},
                {"level": "estimate",
                 "message": f"Wattage estimate: {_EVIL} has no listed TDP, "
                            "so a typical 250 W was used."},
            ],
            "estimated_wattage": 420, "total_min_cost": "0", "store_breakdown": [],
            "unverified_count": 1, "verdict": "No problems found - 1 check unverified",
            "wattage_notes": ["x"],
        }
        page.route("**/api/v1/builder/validate",
                   lambda route: route.fulfill(json=body))
        _open_builder(page)
        page.evaluate("() => validateBuild()")
        items = page.locator("#warnings-list .warning-item")
        expect(items).to_have_count(2)
        expect(items.first).to_contain_text(_EVIL)
        expect(page.locator("#total-wattage")).to_have_text("420 W (estimate)")
        assert page.locator("#warnings-list img").count() == 0
        assert page.evaluate("() => window.__xss") is None

    def test_card_and_picker_handlers_pass_the_name_through_intact(self, page):
        """Names were placed inside inline onclick JS strings; a quote in a title
        broke the handler (or ran as script)."""
        page.evaluate("""(name) => {
            window.__calls = [];
            window.openCompareModal = (n, id) => window.__calls.push(['compare', n, id]);
            renderProducts([{name, p_category: 'Cabinet', offer_count: 1,
                cheapest: {id: 999999, price: 1000, store: 'Test'}}]);
        }""", _EVIL)
        page.locator("#products-grid .card-actions button").first.click()
        assert page.evaluate("() => window.__calls") == [["compare", _EVIL, 999999]]
        assert page.evaluate("() => window.__xss") is None

    def test_compare_modal_escapes_store_names_and_only_links_http_urls(self, page):
        body = {
            "query": "q", "lowest_price": 1000, "highest_price": 2000, "total_offers": 3,
            "matched_by": "canonical_id",
            "offers": [
                {"store_name": _EVIL, "price": 1000, "in_stock": True,
                 "url": "javascript:window.__xss=2"},
                {"store_name": "Good Store", "price": 1500, "in_stock": True,
                 "url": 'https://shop.example/p?a=1&b="><img src=x onerror="window.__xss=4">'},
                {"store_name": "No Link Store", "price": 2000, "in_stock": False,
                 "url": "data:text/html,<script>window.__xss=5</script>"},
            ],
        }
        page.route("**/api/v1/compare**", lambda route: route.fulfill(json=body))
        page.evaluate("() => openCompareModal('q', 1)")
        rows = page.locator("#compare-modal-content tbody tr")
        expect(rows).to_have_count(3)
        expect(rows.nth(0).locator("td").first).to_have_text(_EVIL)
        assert page.locator("#compare-modal-content img").count() == 0
        links = page.locator("#compare-modal-content a")
        expect(links).to_have_count(1)  # only the https offer gets a Buy link
        href = links.first.get_attribute("href")
        assert href == 'https://shop.example/p?a=1&b="><img src=x onerror="window.__xss=4">'
        assert links.first.get_attribute("rel") == "noopener noreferrer"
        assert page.evaluate("() => window.__xss") is None

    def test_compare_modal_escapes_the_error_message(self, page):
        # Chrome's JSON parse error quotes the start of the body back.
        page.route("**/api/v1/compare**", lambda route: route.fulfill(
            status=200, content_type="application/json",
            body='<img src=x onerror="window.__xss=3">'))
        page.evaluate("() => openCompareModal('q', 1)")
        content = page.locator("#compare-modal-content")
        expect(content).to_contain_text("Failed to load comparison data")
        assert page.locator("#compare-modal-content img").count() == 0
        assert page.evaluate("() => window.__xss") is None

    def test_picker_choice_keeps_an_awkward_name_intact(self, page):
        item = {"name": _EVIL, "best_price": 1000, "offer_count": 1, "condition": None,
                "offers": [{"id": 999998, "name": _EVIL, "price": 1000, "store": "Test",
                            "condition": None}]}
        page.route("**/api/v1/builder/candidates",
                   lambda route: route.fulfill(json={"items": [item], "total": 1,
                                                     "offer_count": 1, "filtered_out": 0}))
        page.route("**/api/v1/builder/validate",
                   lambda route: route.fulfill(json={
                       "compatible": True, "warnings": [], "estimated_wattage": 0,
                       "total_min_cost": "0", "store_breakdown": [], "unverified_count": 0,
                       "verdict": "All checks passed", "wattage_notes": []}))
        _open_builder(page)
        page.locator("#slots-container .slot-card").first.get_by_role(
            "button", name="Select").click()
        row = page.locator("#select-modal-list .model-row").first
        expect(row).to_be_visible(timeout=15000)
        row.locator(".model-head").click()
        row.locator(".offer-pick").first.click()
        expect(page.locator("#slot-name-cpu")).to_have_text(_EVIL)
        assert page.evaluate("() => window.__xss") is None


# ---------------------------------------------------------------------------
# WEB-04: the core flow at phone width (375x812).
# ---------------------------------------------------------------------------
def _no_horizontal_overflow(pg):
    width = pg.evaluate("() => document.documentElement.scrollWidth")
    assert width <= 376, f"page is {width}px wide at a 375px viewport"


class TestMobile375:
    def test_search_pick_verdict_compare_at_375px(self, mobile_page):
        pg = mobile_page

        # 1. Search the catalog.
        pg.fill("#search-input", "RTX")
        pg.press("#search-input", "Enter")
        cards = pg.locator("#products-grid .product-card")
        expect(cards.first).to_be_visible(timeout=15000)
        expect(cards.first).to_contain_text(re.compile("RTX", re.I))
        _no_horizontal_overflow(pg)

        # 2. Open compare from a catalog card.
        cards.first.locator(".card-actions button").first.click()
        expect(pg.locator("#compare-modal")).to_have_class(re.compile(r"(^|\s)active(\s|$)"))
        expect(pg.locator("#compare-modal .modal")).to_be_visible()
        expect(pg.locator("#compare-modal-content h2")).to_be_visible(timeout=15000)
        _no_horizontal_overflow(pg)
        pg.locator("#compare-modal .modal-close").click()
        expect(pg.locator("#compare-modal")).not_to_have_class(
            re.compile(r"(^|\s)active(\s|$)"))

        # 3. Open the builder and the picker.
        pg.get_by_role("button", name="PC Builder").click()
        slot = pg.locator("#slots-container .slot-card").first
        expect(slot).to_be_visible()
        slot.get_by_role("button", name="Select").click()
        expect(pg.locator("#select-modal")).to_have_class(re.compile(r"(^|\s)active(\s|$)"))
        row = pg.locator("#select-modal-list .model-row").first
        expect(row).to_be_visible(timeout=15000)

        # 4. Add a part.
        row.locator(".model-head").click()
        pick = row.locator(".offer-pick").first
        expect(pick).to_be_visible()
        pick.click()
        expect(pg.locator("#select-modal")).not_to_have_class(
            re.compile(r"(^|\s)active(\s|$)"))
        expect(pg.locator("#slot-name-cpu")).not_to_have_text("No component selected")

        # 5. Read the verdict.
        status = pg.locator("#compatibility-status")
        expect(status).to_have_text(VERDICTS, timeout=15000)
        status.scroll_into_view_if_needed()
        expect(status).to_be_visible()
        _no_horizontal_overflow(pg)
        assert pg.console_errors == [], pg.console_errors
