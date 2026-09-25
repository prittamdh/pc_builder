# PC Builder 2 - team

**Goal:** public-launch-ready, and the best Indian PC-parts site on data depth - improving the product
along the way. Phases are approved by the user; tasks inside a phase run without asking.

**How we work**
- Manager (main session): runs GSD for the project spec, phase roadmap and progress tracking; uses
  Superpowers for execution discipline (test-first, systematic debugging, review before "done");
  writes self-contained task briefs, checks every result, runs the tests, commits and merges.
- Parallel only when tasks touch different files. Every task ends with a short report.
- `PROGRESS.md` stays the project's history; GSD's planning files hold the roadmap.

| Role | Model | Owns |
|---|---|---|
| architect | opus | Specs, phase plans, design decisions, reviewing finished work. No product code. |
| data-engineer | sonnet | Scrapers, LLM extraction, matching, spec tables, migrations, DAG, scripts. |
| web-dev | sonnet | API, compatibility rules, frontend, performance/SEO/mobile, deployment. |
