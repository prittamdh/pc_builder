---
phase: 01-launch-hardening
plan: 03
status: done
requirements-completed: [FIT-01, FIT-02, FIT-03, WEB-03, WEB-04]
---

# Plan 01-03 Summary: Honest fit verdict, e2e guard, 375px flow

## What shipped

- **FIT-01 (unverified, never a silent pass):** `compatibility_rules.py` gained
  `FIELD_LABELS` (plain-English name for every field a rule reads),
  `SLOT_LABELS`, and `rule_applies(rule, view_a, view_b)` (Pitfall 8: tower
  height does not apply to a known AIO, radiator size does not apply to a known
  air cooler; an unknown cooler type applies, so it is honestly unverified).
  `CompatibilityEngine._group_selections` stamps `product_name` on each view.
  In `validate_build`'s RULES loop a missing input now appends
  `CompatibilityWarning(level="unverified")` with the message
  "Unverified: <part> has no published <label>, so <slot>/<slot> fit could not
  be checked." (both parts named in one item when both are missing).
  `_eval_rule` is unchanged, so `filter_candidates` still only filters on known
  error-level failures and still offers parts with missing data.
  Two additions beyond the plan's letter, same principle: a blank string counts
  as missing, and a form factor the size scale can't place (e.g. "Mid Tower")
  is unverified ("has an unrecognised form factor (Mid Tower)") - before, the
  form-factor rule passed silently in that case.
- **FIT-02 (three verdicts):** `BuildSummary` gained computed fields
  `unverified_count`, `verdict` and `wattage_notes`, derived from `warnings`, so
  `builder_service.py` (data-engineer) is untouched. Verdict precedence:
  any error/warning -> "Problems found"; else unverified -> "No problems found -
  N check(s) unverified"; else "All checks passed". Empty build -> "All checks
  passed".
- **FIT-03 (named estimate):** after the PSU capacity checks, every CPU/GPU whose
  wattage used the default TDP gets a `level="estimate"` item: "Wattage
  estimate: <part> has no listed TDP, so a typical 120 W was used." (250 W for
  GPUs). `estimated_wattage` is unchanged. Estimates don't affect the verdict.
- **UI (app.js / style.css / index.html):** the sidebar renders
  `summary.verdict` with an `ok` / `unverified` (amber) / `error` class; every
  warning message goes through `escapeHtml`; the wattage reads "N W (estimate)"
  when `wattage_notes` is non-empty. The initial markup no longer shows a green
  "Compatibility Checked" before any check ran; a failed validate call shows an
  amber "Could not check compatibility" instead of leaving an old verdict; a
  sequence number stops a slow earlier validate response overwriting a newer
  verdict. Inline `onclick` handlers that embedded product names
  (catalog Compare, picker Choose) now use `escapeHtml(JSON.stringify(name))`;
  before, a `'` in a title broke Compare, and `&quot;` in a title could break
  out of the picker's JS string. `escapeHtml` now also escapes `'`.
- **WEB-03:** `tests/test_frontend_e2e.py` reads `REQUIRE_E2E` once; with it set,
  a missing playwright, missing chromium or an app that fails to boot is
  `pytest.fail`, otherwise the old skip. A meta-test proves both behaviors by
  running the module in a subprocess with an empty `PLAYWRIGHT_BROWSERS_PATH`.
- **WEB-04:** `mobile_page` fixture (375x812) and `TestMobile375`: search, compare
  from a card, open the builder picker, add a part, read one of the three
  verdicts, no horizontal overflow. The run found real overflow (415px catalog,
  461px builder); fixed in style.css inside max-width media queries (builder
  summary stacks below the slots at <=860px; search row and slot cards shrink
  at <=600px). Desktop layout unchanged.

## Live-catalog ids used by the unverified e2e (read-only)

- Unverified pair: GPU 6142 (Asus GT 710 2GB DDR5, GT710-SL-2GD5-BRK-EVO) +
  case 16878 (ZEBRONICS Zeb-Hail Mid-Tower) -> "No problems found - 1 check
  unverified", names the case and "GPU clearance".
- Fully-known pair: GPU 6142 + case 16997 (Consistent CIE109) -> "All checks
  passed".
  The test finds pairs at run time (max 40 validate calls), so it survives
  catalog changes; these are the ids it found on 2026-09-25.

## Decisions for the owner

- Verdict wording: singular "1 check unverified" for one item (matches ROADMAP
  Success Criterion 1); REQUIREMENTS FIT-02 writes the template as "N checks
  unverified". Plural is used for every other N.
- Warning-level items (PSU headroom, cooler socket, radiator) count as
  "Problems found".
- Estimate notes are informational: excluded from the verdict and the count.
- An unrecognised form factor is unverified, not passed (new; see above).

## Verification

See `.superpowers/sdd/phase-01/plan-01-03-report.md` for TDD evidence and full
test output.
