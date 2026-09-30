"""Exercise a running local API: baseline, diagnostic regression, provider failure."""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from llm_regression_lab.local_profile import config_for  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18080")
    args = parser.parse_args()
    token = os.environ.get("LAB_TOKEN")
    if not token:
        raise SystemExit("Set LAB_TOKEN to a token configured in LAB_LOCAL_TOKENS.")
    dataset = {
        "schema_version": "1.0",
        "name": "local-smoke",
        "cases": [
            {
                "case_id": "peru",
                "input": "Capital of Peru?",
                "reference": "Lima",
                "contexts": ["Lima is the capital of Peru."],
                "assertions": [{"type": "equals", "value": "Lima"}],
            }
        ],
    }
    with httpx.Client(base_url=args.url, headers={"Authorization": f"Bearer {token}"}, timeout=10) as client:

        def post(path, body, key=None):
            response = client.post(path, json=body, headers={"Idempotency-Key": key} if key else {})
            response.raise_for_status()
            return response.json()

        version = post("/v1/dataset-versions", dataset)["version_id"]
        baseline = None
        for target in ("fake:reference", "fake:wrong", "fake:error"):
            config = post("/v1/config-versions", config_for(target))["version_id"]
            job = post(
                "/v1/jobs",
                {
                    "schema_version": "1.0",
                    "dataset_version": version,
                    "config_version": config,
                    "baseline_job_id": baseline,
                    "deadline_seconds": 60,
                    "source_revision": "0" * 40,
                },
                uuid4().hex,
            )
            deadline = time.monotonic() + 75
            while job["state"] not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                if time.monotonic() >= deadline:
                    raise SystemExit("Local demo timed out; check worker logs. Retain job ID: " + job["job_id"])
                time.sleep(0.2)
                response = client.get(job["links"]["self"])
                response.raise_for_status()
                job = response.json()
            response = client.get(job["links"]["gate"])
            response.raise_for_status()
            gate = response.json()
            summary = {
                "target": target,
                "job_id": job["job_id"],
                "state": job["state"],
                "gate": gate["verdict"],
                "reasons": gate["reasons"],
            }
            if job["state"] == "SUCCEEDED":
                response = client.get(job["links"]["report"])
                response.raise_for_status()
                summary["assertion_pass_rate"] = response.json()["metrics"][0]["candidate"]
            else:
                summary["execution_error"] = job["error"]["code"]
            print(json.dumps(summary))
            if target == "fake:reference":
                assert job["state"] == "SUCCEEDED" and summary["assertion_pass_rate"] == 1.0
                baseline = job["job_id"]
            elif target == "fake:wrong":
                assert job["state"] == "SUCCEEDED" and summary["assertion_pass_rate"] == 0.0
            else:
                assert job["state"] == "FAILED" and summary["execution_error"] == "PROVIDER_TIMEOUT"
            assert gate["verdict"] == "INCONCLUSIVE", "Fake results must never approve a release"
    print("PASS: local HTTP flow verified; these synthetic results are not a release gate.")


if __name__ == "__main__":
    main()
