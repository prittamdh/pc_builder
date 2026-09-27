#!/usr/bin/env python3
"""Prove nothing on the Oracle account costs money (plan 03-03, OPS-10).

The account is pay-as-you-go, so a paid resource can be created by mistake (the
create-instance form defaults to the paid E5.Flex shape, the volume form to 1024 GB).
The ₹1 budget alert catches spend after it happens; this catches the resource itself.

Run it in OCI Cloud Shell (the >_ icon in the Oracle console), which is already signed
in as you, so the server needs no extra permissions:

    python3 oci_free_audit.py

Exit 0 and "ALL FREE" when clean; exit 1 and a list of problems otherwise. Run it
monthly, and after creating anything in the console. Standard library only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

# Always Free allowance for this account (checked 2026-09-25; see docs/DEPLOY.md).
FREE_SHAPES = {"VM.Standard.A1.Flex", "VM.Standard.E2.1.Micro"}
A1_OCPUS = 2
A1_MEMORY_GB = 12
BLOCK_STORAGE_GB = 200  # boot + block volumes together
OBJECT_STORAGE_GB = 20

# Resource types this setup is expected to have. Anything else is reported so a person
# looks at it: most OCI services have no free tier.
EXPECTED_TYPES = {
    "Instance", "BootVolume", "Volume", "Image",
    "Vcn", "Subnet", "InternetGateway", "RouteTable", "SecurityList", "DhcpOptions",
    "Vnic", "PrivateIp", "PublicIp", "NetworkSecurityGroup",
    "Bucket", "Compartment", "Policy", "DynamicResourceGroup", "Group", "User",
    "TagNamespace", "TagDefault", "OnsTopic", "OnsSubscription",
}


def audit(snap: dict) -> list[str]:
    """Problems found in a snapshot of the account; an empty list means all free."""
    problems = []

    a1_ocpus = a1_mem = 0.0
    for inst in snap["instances"]:
        shape = inst["shape"]
        if shape not in FREE_SHAPES:
            problems.append(f"instance {inst['display-name']!r} uses paid shape {shape}")
        if shape == "VM.Standard.A1.Flex":
            a1_ocpus += inst["shape-config"]["ocpus"]
            a1_mem += inst["shape-config"]["memory-in-gbs"]
    if a1_ocpus > A1_OCPUS:
        problems.append(f"A1 instances use {a1_ocpus:g} OCPU; free is {A1_OCPUS}")
    if a1_mem > A1_MEMORY_GB:
        problems.append(f"A1 instances use {a1_mem:g} GB memory; free is {A1_MEMORY_GB}")

    block = sum(v["size-in-gbs"] for v in snap["boot_volumes"] + snap["volumes"])
    if block > BLOCK_STORAGE_GB:
        problems.append(f"block storage is {block} GB (boot + volumes); free is {BLOCK_STORAGE_GB}")

    obj_gb = sum(b.get("approximate-size") or 0 for b in snap["buckets"]) / 2**30
    if obj_gb > OBJECT_STORAGE_GB:
        problems.append(f"Object Storage holds {obj_gb:.1f} GB; free is {OBJECT_STORAGE_GB}")

    if snap["month_cost"] > 0.005:
        problems.append(f"spend this month is {snap['month_cost']:.2f} (should be 0)")

    unexpected = sorted(set(snap["resource_types"]) - EXPECTED_TYPES)
    if unexpected:
        problems.append("resource types not on the free list, check them: " + ", ".join(unexpected))

    return problems


# --- collecting the snapshot (OCI CLI, as the signed-in Cloud Shell user) -------------

def oci(*args: str) -> list | dict:
    out = subprocess.run(["oci", *args], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"oci {' '.join(args[:3])} failed:\n{out.stderr.strip()}")
    return json.loads(out.stdout)["data"] if out.stdout.strip() else []


def live(items: list) -> list:
    return [i for i in items if i.get("lifecycle-state") not in ("TERMINATED", "DELETED")]


def collect(tenancy: str) -> dict:
    comps = [tenancy] + [
        c["id"] for c in oci("iam", "compartment", "list", "--compartment-id", tenancy,
                             "--compartment-id-in-subtree", "true", "--all",
                             "--lifecycle-state", "ACTIVE")
    ]
    namespace = oci("os", "ns", "get")
    snap = {"instances": [], "boot_volumes": [], "volumes": [], "buckets": []}
    for c in comps:
        snap["instances"] += live(oci("compute", "instance", "list", "--compartment-id", c, "--all"))
        snap["boot_volumes"] += live(oci("bv", "boot-volume", "list", "--compartment-id", c, "--all"))
        snap["volumes"] += live(oci("bv", "volume", "list", "--compartment-id", c, "--all"))
        for b in oci("os", "bucket", "list", "--compartment-id", c, "--namespace", namespace, "--all"):
            snap["buckets"].append(oci("os", "bucket", "get", "--bucket-name", b["name"],
                                       "--namespace", namespace, "--fields", "approximateSize"))

    found = oci("search", "resource", "structured-search", "--limit", "1000",
                "--query-text", "query all resources")
    snap["resource_types"] = [r["resource-type"] for r in live(found.get("items", []))]

    today = dt.datetime.now(dt.timezone.utc).date()
    usage = oci("usage-api", "usage-summary", "request-summarized-usages",
                "--tenant-id", tenancy, "--granularity", "DAILY", "--query-type", "COST",
                "--time-usage-started", f"{today.replace(day=1)}T00:00:00Z",
                "--time-usage-ended", f"{today + dt.timedelta(days=1)}T00:00:00Z")
    snap["month_cost"] = sum(i.get("computed-amount") or 0 for i in usage.get("items", []))
    return snap


def main() -> int:
    tenancy = os.environ.get("OCI_TENANCY") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not tenancy:
        sys.exit("run in OCI Cloud Shell (it sets OCI_TENANCY), or pass the tenancy OCID")
    snap = collect(tenancy)
    print(f"instances {len(snap['instances'])}, boot volumes {len(snap['boot_volumes'])}, "
          f"volumes {len(snap['volumes'])}, buckets {len(snap['buckets'])}, "
          f"spend this month {snap['month_cost']:.2f}")
    problems = audit(snap)
    for p in problems:
        print("PROBLEM:", p)
    print("ALL FREE" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
