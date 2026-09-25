"""Thin Apify runner. Actors are isolated behind this so a ToS cutoff is one kill-switch."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

log = logging.getLogger("workdey.apify")

BASE = "https://api.apify.com/v2"


class ApifyError(RuntimeError):
    pass


def actor_slug(actor_id: str) -> str:
    return actor_id.replace("/", "~")


def run_actor(
    token: str,
    actor_id: str,
    actor_input: dict[str, Any],
    *,
    wait_secs: int = 180,
    timeout: int = 240,
) -> tuple[str, list[dict[str, Any]]]:
    if not token:
        raise ApifyError("APIFY_API_TOKEN is missing")

    slug = actor_slug(actor_id)
    start = requests.post(
        f"{BASE}/acts/{slug}/runs",
        params={"token": token},
        json=actor_input,
        timeout=60,
    )
    if start.status_code >= 400:
        raise ApifyError(f"{actor_id} start failed {start.status_code}: {start.text[:400]}")
    body = start.json().get("data") or start.json()
    run_id = body.get("id") or body.get("data", {}).get("id")
    if not run_id:
        raise ApifyError(f"{actor_id} did not return a run id: {start.text[:300]}")

    deadline = time.time() + wait_secs
    status = body.get("status", "RUNNING")
    dataset_id = (body.get("defaultDatasetId") or "") if isinstance(body, dict) else ""

    while time.time() < deadline and status in {"READY", "RUNNING", "PENDING"}:
        time.sleep(4)
        info = requests.get(f"{BASE}/actor-runs/{run_id}", params={"token": token}, timeout=30)
        info.raise_for_status()
        data = info.json().get("data") or info.json()
        status = data.get("status", status)
        dataset_id = data.get("defaultDatasetId") or dataset_id
        if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            break

    if status != "SUCCEEDED":
        raise ApifyError(f"{actor_id} run {run_id} ended {status}")

    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        ds = requests.get(
            f"{BASE}/datasets/{dataset_id}/items",
            params={"token": token, "clean": 1, "limit": 250, "offset": offset, "format": "json"},
            timeout=timeout,
        )
        ds.raise_for_status()
        page = ds.json()
        if not isinstance(page, list) or not page:
            break
        items.extend(page)
        if len(page) < 250:
            break
        offset += len(page)
    log.info("apify %s run=%s items=%s", actor_id, run_id, len(items))
    return run_id, items


def run_task(
    token: str,
    task_id: str,
    task_input: dict[str, Any],
    *,
    wait_secs: int = 180,
    timeout: int = 240,
) -> tuple[str, list[dict[str, Any]]]:
    if not token:
        raise ApifyError("APIFY_API_TOKEN is missing")

    slug = actor_slug(task_id)
    start = requests.post(
        f"{BASE}/actor-tasks/{slug}/runs",
        params={"token": token},
        json=task_input,
        timeout=60,
    )
    if start.status_code >= 400:
        raise ApifyError(f"{task_id} start failed {start.status_code}: {start.text[:400]}")
    body = start.json().get("data") or start.json()
    run_id = body.get("id") or body.get("data", {}).get("id")
    if not run_id:
        raise ApifyError(f"{task_id} did not return a run id: {start.text[:300]}")

    deadline = time.time() + wait_secs
    status = body.get("status", "RUNNING")
    dataset_id = (body.get("defaultDatasetId") or "") if isinstance(body, dict) else ""

    while time.time() < deadline and status in {"READY", "RUNNING", "PENDING"}:
        time.sleep(4)
        info = requests.get(f"{BASE}/actor-runs/{run_id}", params={"token": token}, timeout=30)
        info.raise_for_status()
        data = info.json().get("data") or info.json()
        status = data.get("status", status)
        dataset_id = data.get("defaultDatasetId") or dataset_id
        if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            break

    if status != "SUCCEEDED":
        raise ApifyError(f"{task_id} run {run_id} ended {status}")

    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        ds = requests.get(
            f"{BASE}/datasets/{dataset_id}/items",
            params={"token": token, "clean": 1, "limit": 250, "offset": offset, "format": "json"},
            timeout=timeout,
        )
        ds.raise_for_status()
        page = ds.json()
        if not isinstance(page, list) or not page:
            break
        items.extend(page)
        if len(page) < 250:
            break
        offset += len(page)
    log.info("apify task %s run=%s items=%s", task_id, run_id, len(items))
    return run_id, items
