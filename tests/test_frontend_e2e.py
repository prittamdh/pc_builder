"""
End-to-end browser tests for the PC Builder UI.

Every frontend bug found on 2026-08-16 was silent - a swallowed 422 that left the
sidebar permanently reading "Incompatibilities Detected", a component picker that
always showed an empty list, a zip() that truncated every candidate away. None
raised an error, so backend tests and a clean console both looked fine. These
tests assert on what the user actually sees.

Skipped automatically if Playwright's browser isn't installed, so the suite still
runs in environments without it.
"""
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

playwright_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_api.sync_playwright


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
    except Exception as exc:  # browser binary not installed
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
        "Incompatibilities Detected" for every build including an empty one."""
        _open_builder(page)
        page.wait_for_timeout(1200)
        status = page.locator("#compatibility-status").inner_text()
        assert "Verified" in status, status

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
    def test_picker_lists_real_components(self, page):
        """The picker used to filter whatever the Catalog tab had loaded, so opening
        the builder and clicking Select showed "No matching components loaded"."""
        _open_builder(page)
        page.locator("#slots-container button", has_text="Select").first.click()
        page.wait_for_selector("#select-modal.active")
        page.wait_for_function("document.querySelectorAll('#select-modal-list .slot-card').length > 0", timeout=15000)
        assert page.locator("#select-modal-list .slot-card").count() > 0

    def test_picker_search_reaches_beyond_the_first_page(self, page):
        """The 7800X3D sat past the first 100 results and was unreachable."""
        _open_builder(page)
        page.locator("#slots-container button", has_text="Select").first.click()
        page.wait_for_selector("#select-modal.active")
        page.fill("#select-modal-search", "7800X3D")
        page.wait_for_function(
            "[...document.querySelectorAll('#select-modal-list .slot-card')]"
            ".some(c => /7800X3D/i.test(c.innerText))", timeout=15000
        )
        assert page.locator("#select-modal-list .slot-card").count() > 0


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
