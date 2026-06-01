#!/usr/bin/env python3
import json
import sys
from typing import Any, Dict, List


REQUIRED = [
    "query",
    "inferred_decision",
    "candidate_actions",
    "default_action",
    "decision_boundary",
    "voi_information_needed",
    "search_provider",
    "search_plan",
    "public_evidence",
    "final_status",
    "evidence_gaps",
    "next_minimum_action",
    "stop_search_rule",
    "memory_update",
]

FINAL_STATUSES = {"kill", "archive", "watch", "probe", "act"}
ALLOWED_SEARCH_PROVIDERS = {"tavily", "tavily+tikhub"}
BOUNDARIES = {"far_from_decision", "near_decision", "at_boundary", "already_decided"}
GAP_TYPES = {"EVPI", "EVSI"}
GAP_PRIORITIES = {"low", "medium", "high"}
MEMORY_REQUIRED = [
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


def read_json() -> Dict[str, Any]:
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as handle:
            return json.load(handle)
    raw = sys.stdin.read().strip()
    if not raw:
        raise SystemExit("请提供 VOI brief JSON 文件路径，或通过 stdin 输入 JSON。")
    return json.loads(raw)


def validate(data: Dict[str, Any]) -> List[str]:
    errors = []
    for field in REQUIRED:
        if field not in data:
            errors.append(f"缺少必填字段：{field}")

    if data.get("final_status") not in FINAL_STATUSES:
        errors.append("final_status 必须是 kill/archive/watch/probe/act 之一")

    if data.get("search_provider") not in ALLOWED_SEARCH_PROVIDERS:
        errors.append("search_provider 必须是 tavily 或 tavily+tikhub；其他搜索结果不得作为 Info-Alchemist 证据")

    actions = data.get("candidate_actions")
    if not isinstance(actions, list) or len(actions) < 2:
        errors.append("candidate_actions 至少需要两个候选行动")

    boundary = data.get("decision_boundary", {})
    if not isinstance(boundary, dict) or boundary.get("status") not in BOUNDARIES:
        errors.append("decision_boundary.status 不合法")

    for index, item in enumerate(data.get("search_plan", []) or []):
        for key in ["query", "search_intent", "reason"]:
            if key not in item:
                errors.append(f"search_plan[{index}] 缺少 {key}")

    high_gaps = []
    for index, gap in enumerate(data.get("evidence_gaps", []) or []):
        if gap.get("type") not in GAP_TYPES:
            errors.append(f"evidence_gaps[{index}].type 必须是 EVPI 或 EVSI")
        if gap.get("priority") not in GAP_PRIORITIES:
            errors.append(f"evidence_gaps[{index}].priority 必须是 low/medium/high")
        if gap.get("priority") == "high":
            high_gaps.append(gap)
        for key in ["gap", "why_it_matters", "recommended_channel"]:
            if not gap.get(key):
                errors.append(f"evidence_gaps[{index}] 缺少 {key}")

    if high_gaps and data.get("final_status") == "act":
        errors.append("存在 high priority evidence gaps 时，final_status 不能是 act")

    if not data.get("stop_search_rule"):
        errors.append("必须提供 stop_search_rule")

    memory = data.get("memory_update")
    if not isinstance(memory, dict):
        errors.append("memory_update 必须是对象")
    else:
        for field in MEMORY_REQUIRED:
            if field not in memory:
                errors.append(f"memory_update 缺少必填字段：{field}")

    return errors


def main() -> int:
    errors = validate(read_json())
    payload = {"valid": not errors, "errors": errors}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
