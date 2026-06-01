#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict

from info_alchemist_paths import runs_dir as configured_runs_dir


SCHEMA_VERSION = "info_alchemist_run_log.v1"
STAGES = {
    "intent",
    "search_plan",
    "tavily_result",
    "synthesis",
    "pipeline",
    "final_output",
    "error",
}
ERROR_STATUSES = {"error", "failed", "failure"}


def runs_dir() -> Path:
    return configured_runs_dir()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_run_id(seed: str = "") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    digest = sha256(f"{seed}|{time.time_ns()}".encode("utf-8")).hexdigest()[:10]
    return f"{stamp}-{digest}"


def safe_run_id(run_id: str) -> str:
    cleaned = "".join(ch for ch in run_id.strip() if ch.isalnum() or ch in {"-", "_"})
    if not cleaned:
        raise ValueError("run_id 不能为空。")
    if cleaned != run_id.strip():
        raise ValueError("run_id 只能包含字母、数字、短横线和下划线。")
    return cleaned


def run_path(run_id: str) -> Path:
    return runs_dir() / f"{safe_run_id(run_id)}.json"


def read_log(run_id: str) -> Dict[str, Any]:
    path = run_path(run_id)
    if not path.exists():
        timestamp = now_iso()
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": safe_run_id(run_id),
            "created_at": timestamp,
            "updated_at": timestamp,
            "events": [],
            "errors": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def write_log(log: Dict[str, Any]) -> Path:
    path = run_path(log["run_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(log, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
    return path


def record_stage(run_id: str, stage: str, payload: Dict[str, Any], status: str = "ok") -> Dict[str, Any]:
    if os.environ.get("DISABLE_RUN_LOG") == "1":
        return {"run_id": safe_run_id(run_id), "run_log_path": ""}
    if stage not in STAGES:
        raise ValueError(f"未知 run log stage：{stage}")
    log = read_log(run_id)
    event = {
        "at": now_iso(),
        "stage": stage,
        "status": status,
        "payload": payload,
    }
    log["updated_at"] = event["at"]
    log.setdefault("events", []).append(event)
    log[stage] = payload
    if stage == "error" or str(status).lower() in ERROR_STATUSES:
        log.setdefault("errors", []).append(event)
    path = write_log(log)
    return {"run_id": log["run_id"], "run_log_path": str(path)}


def record_stages(run_id: str, events: list[Dict[str, Any]]) -> Dict[str, Any]:
    if os.environ.get("DISABLE_RUN_LOG") == "1":
        return {"run_id": safe_run_id(run_id), "run_log_path": ""}
    log = read_log(run_id)
    for item in events:
        stage = item.get("stage", "")
        if stage not in STAGES:
            raise ValueError(f"未知 run log stage：{stage}")
        status = item.get("status", "ok")
        payload = item.get("payload", {})
        event = {
            "at": now_iso(),
            "stage": stage,
            "status": status,
            "payload": payload,
        }
        log["updated_at"] = event["at"]
        log.setdefault("events", []).append(event)
        log[stage] = payload
        if stage == "error" or str(status).lower() in ERROR_STATUSES:
            log.setdefault("errors", []).append(event)
    path = write_log(log)
    return {"run_id": log["run_id"], "run_log_path": str(path)}


def read_payload(args: argparse.Namespace) -> Dict[str, Any]:
    if args.payload:
        return json.loads(args.payload)
    if args.payload_file:
        return json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    raw = sys.stdin.read().strip()
    if raw:
        return json.loads(raw)
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="记录 Info-Alchemist 单次运行的审计日志。")
    parser.add_argument("stage", choices=sorted(STAGES))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--status", default="ok")
    parser.add_argument("--payload", default="")
    parser.add_argument("--payload-file", default="")
    parser.add_argument("--seed", default="")
    args = parser.parse_args()

    run_id = args.run_id.strip() or new_run_id(args.seed)
    payload = read_payload(args)
    result = record_stage(run_id=run_id, stage=args.stage, payload=payload, status=args.status)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
