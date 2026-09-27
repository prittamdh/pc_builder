"""How often the worker runs each task (plan 02-03). /health/pipeline reads the same
table to tell a late task from an on-time one."""
from datetime import timedelta

TASK_INTERVALS: dict[str, timedelta] = {
    "reap": timedelta(minutes=1),
    "enqueue_due_targets": timedelta(minutes=5),
    "canonical_extraction": timedelta(minutes=15),
    "physical_specs": timedelta(minutes=15),
    "catalog_policy": timedelta(minutes=15),
    "price_freshness": timedelta(hours=1),
    # A model mixing sizes (8GB with 16GB) means a wrong merge; see identity_audit.py.
    "identity_audit": timedelta(days=1),
}
