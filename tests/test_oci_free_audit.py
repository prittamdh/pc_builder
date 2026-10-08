"""The Oracle free-resource audit (OPS-10): pure checks on a snapshot, no OCI calls."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "oci_free_audit", Path(__file__).resolve().parent.parent / "scripts" / "oci_free_audit.py"
)
audit_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_mod)
audit = audit_mod.audit


def snapshot(**over):
    snap = {
        "instances": [
            {"display-name": "pcbuilder-prod", "shape": "VM.Standard.A1.Flex",
             "shape-config": {"ocpus": 2.0, "memory-in-gbs": 12.0}},
        ],
        "boot_volumes": [{"display-name": "boot", "size-in-gbs": 47}],
        "volumes": [{"display-name": "pcbuilder-data", "size-in-gbs": 150}],
        "buckets": [{"name": "pcbuilder-backups", "approximate-size": 3 * 2**30}],
        "resource_types": ["Instance", "BootVolume", "Volume", "Vcn", "Subnet", "Bucket"],
        "month_cost": 0.0,
    }
    snap.update(over)
    return snap


def test_todays_setup_is_clean():
    assert audit(snapshot()) == []


def test_paid_shape_is_flagged():
    inst = {"display-name": "oops", "shape": "VM.Standard.E5.Flex",
            "shape-config": {"ocpus": 1.0, "memory-in-gbs": 8.0}}
    problems = audit(snapshot(instances=snapshot()["instances"] + [inst]))
    assert any("oops" in p and "E5.Flex" in p for p in problems)


def test_a1_over_the_free_allowance_is_flagged():
    second = {"display-name": "extra", "shape": "VM.Standard.A1.Flex",
              "shape-config": {"ocpus": 1.0, "memory-in-gbs": 6.0}}
    problems = audit(snapshot(instances=snapshot()["instances"] + [second]))
    assert any("OCPU" in p for p in problems)
    assert any("memory" in p for p in problems)


def test_block_storage_over_200_gb_is_flagged():
    problems = audit(snapshot(volumes=[{"display-name": "big", "size-in-gbs": 1024}]))
    assert any("block storage" in p for p in problems)


def test_object_storage_over_20_gb_is_flagged():
    problems = audit(snapshot(buckets=[{"name": "b", "approximate-size": 25 * 2**30}]))
    assert any("Object Storage" in p for p in problems)


def test_any_spend_is_flagged():
    assert any("spend" in p for p in audit(snapshot(month_cost=0.42)))


def test_unexpected_resource_type_is_flagged():
    problems = audit(snapshot(resource_types=["Instance", "LoadBalancer", "Database"]))
    assert any("LoadBalancer" in p and "Database" in p for p in problems)


def test_free_micro_instance_is_allowed():
    micro = {"display-name": "micro", "shape": "VM.Standard.E2.1.Micro",
             "shape-config": {"ocpus": 1.0, "memory-in-gbs": 1.0}}
    assert audit(snapshot(instances=snapshot()["instances"] + [micro])) == []
