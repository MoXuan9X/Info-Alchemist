#!/usr/bin/env python3
import json
import os
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List


REQUIRED = [
    "date",
    "user_query",
    "trigger_reason_type",
    "decision_context",
    "default_action",
    "final_status",
    "key_evidence",
    "next_action",
    "insight",
]

TRIGGER_TYPES = {
    "fomo",
    "money_signal",
    "competitor_signal",
    "authority_signal",
    "user_need_signal",
    "efficiency_signal",
    "curiosity",
    "anxiety",
    "other",
}

FINAL_STATUSES = {"kill", "archive", "watch", "probe", "act"}


def load_record(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def validate(record: Dict[str, Any]) -> List[str]:
    errors = [f"缺少必填字段：{field}" for field in REQUIRED if field not in record]
    if record.get("trigger_reason_type") not in TRIGGER_TYPES:
        errors.append("trigger_reason_type 不合法")
    if record.get("final_status") not in FINAL_STATUSES:
        errors.append("final_status 不合法")
    return errors


def compute_record_id(record: Dict[str, Any]) -> str:
    payload = {
        "user_query": record.get("user_query", ""),
        "decision_context": record.get("decision_context", ""),
        "default_action": record.get("default_action", ""),
        "final_status": record.get("final_status", ""),
        "next_action": record.get("next_action", "")
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def existing_record_ids(target: Path) -> set[str]:
    if not target.exists():
        return set()
    ids = set()
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                ids.add(str(item.get("record_id") or compute_record_id(item)))
    return ids


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit("用法：append_memory.py <alchemy_record.json> <target.jsonl>")

    if os.environ.get("DISABLE_MEMORY") == "1":
        print(json.dumps({"written": False, "reason": "DISABLE_MEMORY=1"}, ensure_ascii=False, indent=2))
        return 0

    record = load_record(sys.argv[1])
    errors = validate(record)
    if errors:
        print(json.dumps({"written": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 1

    record = dict(record)
    record.setdefault("record_id", compute_record_id(record))

    target = Path(sys.argv[2])
    target.parent.mkdir(parents=True, exist_ok=True)
    if record["record_id"] in existing_record_ids(target):
        print(json.dumps({
            "written": False,
            "deduped": True,
            "record_id": record["record_id"],
            "target": str(target)
        }, ensure_ascii=False, indent=2))
        return 0

    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    print(json.dumps({"written": True, "record_id": record["record_id"], "target": str(target)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
