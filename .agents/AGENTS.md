# Workspace Guidelines - PC Builder 2

## Communication & Execution Protocol
1. **Direct Execution**: Eliminate pleasantries, fluff, background history, and theoretical lectures. Deliver working code and concrete action items immediately.
2. **Technical Honesty**: Never agree out of politeness. Correct flawed logic, parameters, or schema assumptions directly with exact fixes.
3. **Zero Speculation**: State "I do not know" or "I lack the data" immediately when data is missing. Never guess or hallucinate.

## Living Documentation Maintenance Rules
1. **PROJECT_MAP.md**: Update `PROJECT_MAP.md` whenever scripts/modules are created, modified, or deprecated. Maintain core vs. deprecated script classifications.
2. **PROGRESS.md**: Update `PROGRESS.md` after completing tasks or phases, marking completed items with `✅` and tracking upcoming roadmap items.
3. **.gitignore**: Keep `.gitignore` updated to exclude temporary artifacts, log files, local caches, and scratch files.

## Architecture & Data Conventions
1. **Product Identity**: Products are uniquely identified by composite key `(sid, pid)` where `sid` is database store ID and `pid` is store-specific unique product identifier/slug.
2. **Store Configurations**: Stores dynamically configure CSS selectors, endpoints, and `page_endpoint` pagination templates in PostgreSQL `stores` table.
3. **Empirical Verification**: Never mark a task complete without running terminal verification commands (`pytest`, `alembic upgrade head`, CLI test scripts) to ensure 100% clean execution.
