#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import date
from typing import Any, Dict

# 自然语言决策词 → final_status 枚举值
决策词映射 = {
    "做": "act",
    "行动": "act",
    "立即行动": "act",
    "立刻做": "act",
    "做了": "act",
    "小步验证": "probe",
    "验证": "probe",
    "试一下": "probe",
    "先试": "probe",
    "观望": "watch",
    "持续关注": "watch",
    "关注": "watch",
    "继续看": "watch",
    "归档": "archive",
    "存档": "archive",
    "不急": "archive",
    "放弃": "kill",
    "不做": "kill",
    "砍掉": "kill",
    "kill": "kill",
    "archive": "archive",
    "watch": "watch",
    "probe": "probe",
    "act": "act",
}


def read_brief() -> Dict[str, Any]:
    """从文件路径参数或 stdin 读取 VOI brief JSON"""
    # 找到第一个非 --flag 的位置参数（brief 文件路径）
    # 因为 argparse 已处理，brief 通过 stdin 或 --brief-file 传入
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


def resolve_final_status(user_decision: str) -> str:
    """将用户自然语言决策词解析为 final_status 枚举值"""
    if not user_decision:
        return ""
    for key, value in 决策词映射.items():
        if key in user_decision:
            return value
    return "watch"  # 默认观望


def trigger_type(query: str) -> str:
    """根据查询词推断触发类型"""
    if any(token in query for token in ["机会", "热点", "新模型", "错过", "最新"]):
        return "fomo"
    if any(token in query for token in ["赚钱", "商业化", "收入", "变现"]):
        return "money_signal"
    if any(token in query for token in ["竞品", "对手", "竞争"]):
        return "competitor_signal"
    if any(token in query for token in ["用户", "需求", "抱怨"]):
        return "user_need_signal"
    return "other"


def propose(brief: Dict[str, Any], user_decision: str = "", user_insight: str = "") -> Dict[str, Any]:
    """生成一条 alchemy record 草稿"""
    evidence = brief.get("public_evidence") or []
    key_evidence = ""
    if evidence:
        key_evidence = evidence[0].get("finding", "")
    if not key_evidence:
        key_evidence = brief.get("final_status_reason", "本轮无决定性公开证据。")

    query = brief.get("query", "")

    # final_status：优先用用户明确说的决策，其次用 brief 里的推断值
    if user_decision:
        final_status = resolve_final_status(user_decision)
    else:
        final_status = brief.get("final_status", "watch")

    # insight：优先用用户说的，其次用占位提示
    if user_insight:
        insight = user_insight
    else:
        insight = "（待补充：这次决策让你对自己的决策模式学到了什么？）"

    return {
        "date": date.today().isoformat(),
        "user_query": query,
        "trigger_reason_type": trigger_type(query),
        "trigger_reason_note": "根据搜索报告和用户决策自动生成。",
        "decision_context": brief.get("inferred_decision", ""),
        "default_action": brief.get("default_action", ""),
        "final_status": final_status,
        "key_evidence": key_evidence,
        "next_action": brief.get("next_minimum_action", ""),
        "insight": insight,
        "confidence": "medium",
        "user_decision_raw": user_decision,  # 原始决策文字，便于回溯
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="根据 VOI brief 和用户决策生成 alchemy record 草稿。"
    )
    parser.add_argument(
        "--brief-file", default="",
        help="VOI brief JSON 文件路径；不传则从 stdin 读取"
    )
    parser.add_argument(
        "--final-status", default="",
        help="用户明确表达的决策词，例如：观望、小步验证、放弃、做。覆盖 brief 里的推断值。"
    )
    parser.add_argument(
        "--insight", default="",
        help="用户本次决策对自身决策模式的洞察，一句话。覆盖默认占位文字。"
    )
    args = parser.parse_args()

    if args.brief_file:
        import pathlib
        brief = json.loads(pathlib.Path(args.brief_file).read_text(encoding="utf-8"))
    else:
        raw = sys.stdin.read().strip()
        brief = json.loads(raw) if raw else {}

    record = propose(brief, user_decision=args.final_status, user_insight=args.insight)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
