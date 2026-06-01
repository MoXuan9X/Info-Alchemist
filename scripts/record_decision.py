#!/usr/bin/env python3
"""
record_decision.py — 决策记录单入口

用法：
    python3 scripts/record_decision.py \
        --query "<本轮用户原始问题>" \
        --decision "<用户决策词，例如：观望 / 放弃 / 做>" \
        [--run-log-path "<formal_run.py 返回的 run_log_path>"] \
        [--insight "<用户对自身决策模式的洞察，一句话>"]

说明：
    - 自动找最近一条与 query 匹配的 run log（或最新 run log）提取证据
    - 把 propose / append / update_profile 三步合并到一个脚本
    - 可显式传 run_log_path；不传时自动匹配最近 run log
    - DISABLE_MEMORY=1 时静默跳过
"""
import argparse
import json
import os
import sys
import re
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional

from info_alchemist_paths import records_file, runs_dir, profile_file, skill_dir
from update_personal_voi_profile import build_profile as render_profile

# ── 路径配置 ──
SKILL_ROOT = skill_dir()
RUNS_DIR = runs_dir()
RECORDS_FILE = records_file()
PROFILE_FILE = profile_file()

# ── 触发类型映射 ──
触发类型中文 = {
    "fomo":               "热点 FOMO",
    "money_signal":       "赚钱信号",
    "competitor_signal":  "竞品动态",
    "authority_signal":   "权威声音",
    "user_need_signal":   "用户需求",
    "efficiency_signal":  "效率提升",
    "curiosity":          "好奇心驱动",
    "anxiety":            "焦虑驱动",
    "other":              "其他",
}

# ── 最终状态映射 ──
状态中文 = {
    "kill":    "放弃",
    "archive": "归档观望",
    "watch":   "持续关注",
    "probe":   "小步验证",
    "act":     "立即行动",
}

# ── 决策词 → 枚举值 ──
决策词映射 = {
    "做": "act", "行动": "act", "立即行动": "act", "立刻做": "act", "做了": "act",
    "小步验证": "probe", "验证": "probe", "试一下": "probe", "先试": "probe",
    "深度拆解": "probe", "拆解": "probe", "选 5 个": "probe", "选5个": "probe",
    "观望": "watch", "持续关注": "watch", "关注": "watch", "继续看": "watch",
    "归档": "archive", "存档": "archive", "不急": "archive",
    "放弃": "kill", "不做": "kill", "砍掉": "kill",
    # 也接受英文枚举值直接传入
    "kill": "kill", "archive": "archive", "watch": "watch", "probe": "probe", "act": "act",
}

FINAL_STATUSES = {"kill", "archive", "watch", "probe", "act"}
MAX_EVIDENCE_SOURCES = 2


# ════════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════════

def resolve_final_status(decision_text: str) -> str:
    """将自然语言决策词解析为 final_status 枚举值"""
    for key, value in 决策词映射.items():
        if key in decision_text:
            return value
    return "watch"


def normalize_final_action(decision_text: str) -> str:
    """把用户确认语压缩成可沉淀到画像里的动作描述。"""
    text = str(decision_text).strip()
    if not text:
        return ""
    text = re.sub(r"^(好的|好|可以|OK|ok)[，,、\s]*", "", text).strip()
    text = re.sub(r"^(我|我们)(会|先|要|准备|打算)[，,、\s]*", "", text).strip()
    return text or str(decision_text).strip()


def trigger_type(query: str) -> str:
    """根据查询词推断触发类型"""
    if any(t in query for t in ["机会", "热点", "新模型", "错过", "最新", "刚出"]):
        return "fomo"
    if any(t in query for t in ["赚钱", "商业化", "收入", "变现"]):
        return "money_signal"
    if any(t in query for t in ["竞品", "对手", "竞争"]):
        return "competitor_signal"
    if any(t in query for t in ["用户", "需求", "抱怨"]):
        return "user_need_signal"
    return "other"


def stage_payload(run_log: Dict[str, Any], stage: str) -> Dict[str, Any]:
    """兼容新版顶层 stage、events 和旧版 stages 结构。"""
    direct = run_log.get(stage)
    if isinstance(direct, dict):
        return direct

    legacy_stages = run_log.get("stages", {})
    if isinstance(legacy_stages, dict):
        legacy = legacy_stages.get(stage, {})
        if isinstance(legacy, dict):
            payload = legacy.get("payload")
            return payload if isinstance(payload, dict) else legacy

    for event in reversed(run_log.get("events", []) or []):
        if event.get("stage") != stage:
            continue
        payload = event.get("payload", {})
        return payload if isinstance(payload, dict) else {}
    return {}


def query_match_score(query: str, stored_query: str) -> float:
    query = query.strip()
    stored_query = stored_query.strip()
    if not query or not stored_query:
        return 0.0
    if query == stored_query:
        return 1.0
    if query in stored_query or stored_query in query:
        return 0.9

    tokens = [token for token in re.split(r"[\s,，。！？、/|]+", query) if len(token) > 1]
    token_hits = sum(1 for token in tokens if token in stored_query)
    token_score = token_hits / len(tokens) if tokens else 0.0

    query_chars = {char for char in query if not char.isspace()}
    stored_chars = {char for char in stored_query if not char.isspace()}
    if not query_chars or not stored_chars:
        return token_score
    char_score = len(query_chars & stored_chars) / max(1, min(len(query_chars), len(stored_chars)))
    return max(token_score, char_score * 0.75)


def load_run_log(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, dict):
        data["_run_log_path"] = str(path)
        return data
    return None


def find_run_log(query: str, run_log_path: str = "") -> Optional[Dict[str, Any]]:
    """找 run log；优先使用显式路径，其次用 query 匹配，最后取最新一条。"""
    if run_log_path:
        explicit = load_run_log(Path(run_log_path))
        if explicit:
            return explicit

    if not RUNS_DIR.exists():
        return None
    candidates = sorted(RUNS_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        return None

    best: Optional[Dict[str, Any]] = None
    best_score = 0.0
    for path in candidates[:50]:
        data = load_run_log(path)
        if not data:
            continue
        intent_payload = stage_payload(data, "intent")
        stored_query = str(intent_payload.get("user_query", ""))
        score = query_match_score(query, stored_query)
        if score > best_score:
            best = data
            best_score = score
        if score >= 0.9:
            return data
    if best and best_score >= 0.45:
        return best

    return load_run_log(candidates[0])


def extract_evidence(run_log: Optional[Dict[str, Any]]) -> str:
    """从 run log 里提取最关键的一条证据摘要"""
    if not run_log:
        return ""
    synthesis = stage_payload(run_log, "synthesis")

    # 尝试从 synthesis 里的 public_evidence 提取
    evidence_list = synthesis.get("public_evidence") or []
    if evidence_list and isinstance(evidence_list, list):
        first = evidence_list[0]
        if isinstance(first, dict):
            return first.get("finding", "") or first.get("summary", "")
        if isinstance(first, str):
            return first

    # 退而取 final_status_reason
    reason = synthesis.get("final_status_reason", "")
    if reason:
        return reason

    search_payload = stage_payload(run_log, "tavily_result")
    for item in search_payload.get("search_results", []) or []:
        if item.get("status") != "ok":
            continue
        if item.get("answer"):
            return item.get("answer", "")
        results = item.get("results") or []
        if results and isinstance(results[0], dict):
            return results[0].get("content", "") or results[0].get("title", "")

    diagnosis = synthesis.get("search_failure_diagnosis") or search_payload.get("error_summary") or search_payload.get("error")
    if diagnosis:
        return diagnosis

    return ""


def clean_source_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    title = re.sub(r", according to .+$", "", title, flags=re.IGNORECASE)
    title = re.sub(
        r"\s+-\s+(Yahoo Finance|TechCrunch|Business Insider|CNBC|The National Law Review|iTnews|PR Newswire)$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    launch_match = re.search(r"^([A-Z][A-Za-z0-9]+).+\bLaunch(?:es)?\s+([A-Z][A-Za-z0-9]+)", title)
    if launch_match:
        return f"{launch_match.group(1)} launches {launch_match.group(2)}"
    return title


def extract_evidence_sources(run_log: Optional[Dict[str, Any]], limit: int = MAX_EVIDENCE_SOURCES) -> List[Dict[str, str]]:
    """提取可展示的证据来源：只保留标题和链接，不保留正文摘要。"""
    if not run_log:
        return []

    candidates: List[Dict[str, str]] = []

    def add_source(title: str, url: str, score: float) -> None:
        title = clean_source_title(str(title or ""))
        url = str(url or "").strip()
        if not title or not url:
            return
        candidates.append({"title": title, "url": url, "_score": score})

    synthesis = stage_payload(run_log, "synthesis")
    impact_weight = {"strong": 40.0, "medium": 30.0, "weak": 15.0, "none": 0.0}
    for index, item in enumerate(synthesis.get("public_evidence") or []):
        if not isinstance(item, dict):
            continue
        source = item.get("source") or {}
        if isinstance(source, dict):
            add_source(
                source.get("title", ""),
                source.get("url", ""),
                impact_weight.get(str(item.get("decision_impact", "")), 10.0) - index,
            )

    search_payload = stage_payload(run_log, "tavily_result")
    for result_group in search_payload.get("search_results", []) or []:
        if not isinstance(result_group, dict) or result_group.get("status") != "ok":
            continue
        for index, item in enumerate(result_group.get("results") or []):
            if not isinstance(item, dict):
                continue
            score = float(item.get("score") or 0.0) * 10.0 - index
            add_source(item.get("title", ""), item.get("url", ""), score)

    sources: List[Dict[str, str]] = []
    seen_urls = set()
    seen_titles = set()
    for candidate in sorted(candidates, key=lambda item: item.get("_score", 0), reverse=True):
        title = candidate["title"]
        url = candidate["url"]
        title_key = title.lower()
        if url in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title_key)
        sources.append({"title": title, "url": url})
        if len(sources) >= limit:
            break
    return sources


def format_sources_as_key_evidence(sources: List[Dict[str, str]]) -> str:
    if not sources:
        return ""
    return "\n".join(
        f"{index}. [{source['title']}]({source['url']})"
        for index, source in enumerate(sources, start=1)
    )


def derive_decision_turning_point(query: str, decision_text: str, final_status: str) -> str:
    if "关键词页" in decision_text and "工具" in decision_text:
        return "公开新闻只能说明方向热，不足以证明转化；所以先用 SEO 和小工具验证"
    if "参考" in query:
        return "公开搜索适合筛样本，不足以判断真实体验；所以要做少量深拆"
    if final_status == "probe":
        return "公开证据只支持小步验证，不支持直接重投入"
    if final_status == "watch":
        return "当前证据不足以改变行动，先设复查条件继续观察"
    if final_status == "kill":
        return "公开证据不足以支持继续投入，因此归档或放弃"
    if final_status == "act":
        return "证据已足够支持下一步行动，但结果仍要用自有数据复盘"
    return ""


def extract_query(run_log: Optional[Dict[str, Any]], fallback: str) -> str:
    if not run_log:
        return fallback
    return str(stage_payload(run_log, "intent").get("user_query") or fallback)


def extract_decision_context(run_log: Optional[Dict[str, Any]]) -> str:
    if not run_log:
        return ""
    intent = stage_payload(run_log, "intent")
    if intent.get("decision_context"):
        return str(intent.get("decision_context"))
    plan = stage_payload(run_log, "search_plan")
    topic = str(plan.get("topic", "")).strip()
    if topic:
        return f"围绕“{topic}”判断下一步行动。"
    return ""


def extract_default_action(run_log: Optional[Dict[str, Any]]) -> str:
    if not run_log:
        return ""
    intent = stage_payload(run_log, "intent")
    plan = stage_payload(run_log, "search_plan")
    return str(intent.get("default_action") or plan.get("default_action") or "")


def extract_next_action(run_log: Optional[Dict[str, Any]]) -> str:
    if not run_log:
        return ""
    synthesis = stage_payload(run_log, "synthesis")
    gaps = synthesis.get("evidence_gap_candidates") or []
    if gaps and isinstance(gaps[0], dict):
        gap = gaps[0].get("gap", "")
        if gap:
            return f"补齐证据缺口：{gap}"
    return ""


def derive_scene(query: str, run_log: Optional[Dict[str, Any]]) -> str:
    context = extract_decision_context(run_log)
    text = query + " " + context
    if "参考" in text:
        if "视频" in text:
            return "AI 视频站参考调研"
        return "参考对象调研"
    if any(token in text for token in ["最新", "趋势", "动态", "新闻"]):
        return "趋势动态调研"
    if any(token in text for token in ["机会", "值不值得", "要不要做"]):
        return "产品机会判断"
    if any(token in text for token in ["竞品", "对手", "市场"]):
        return "竞品市场调研"
    return query or "未命名决策场景"


def derive_information_trigger(query: str) -> str:
    if "参考" in query:
        return "想找值得参考的网站"
    if any(token in query for token in ["最新", "趋势", "动态", "新闻"]):
        return "想了解最新变化"
    if "机会" in query:
        return "想判断是否有机会"
    return 触发类型中文.get(trigger_type(query), "需要判断下一步行动")


def derive_default_action(query: str, run_log: Optional[Dict[str, Any]]) -> str:
    value = extract_default_action(run_log).strip()
    if value:
        return value
    if "参考" in query:
        return "继续收集更多名单"
    if any(token in query for token in ["最新", "趋势", "动态", "新闻"]):
        return "继续观察最新动态"
    return "继续收集更多信息"


def derive_next_action(query: str, decision_text: str, final_status: str, run_log: Optional[Dict[str, Any]]) -> str:
    value = extract_next_action(run_log).strip()
    if value and not value.startswith("补齐证据缺口："):
        return value
    if "参考" in query:
        return "做产品体验拆解表"
    if final_status == "probe":
        return "设计最小验证动作"
    if final_status == "watch":
        return "设置下一次复查条件"
    if final_status == "kill":
        return "归档原因，不继续投入"
    if decision_text:
        return f"执行并记录结果：{decision_text}"
    return value


def compute_record_id(record: Dict[str, Any]) -> str:
    payload = {
        "user_query": record.get("user_query", ""),
        "decision_context": record.get("decision_context", ""),
        "default_action": record.get("default_action", ""),
        "final_status": record.get("final_status", ""),
        "next_action": record.get("next_action", ""),
        "source_run_id": record.get("source_run_id", ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def existing_record_ids() -> set:
    if not RECORDS_FILE.exists():
        return set()
    ids = set()
    with RECORDS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                ids.add(str(item.get("record_id") or compute_record_id(item)))
            except Exception:
                continue
    return ids


# ════════════════════════════════════════════════════════════
# 画像生成（与 update_personal_voi_profile.py 保持一致）
# ════════════════════════════════════════════════════════════

def read_all_records() -> List[Dict[str, Any]]:
    if not RECORDS_FILE.exists():
        return []
    records = []
    with RECORDS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
    return records


def bullet(items: List[str], empty: str) -> str:
    return "\n".join(f"- {i}" for i in items) if items else empty


def build_profile(records: List[Dict[str, Any]]) -> str:
    return render_profile(records)


# ════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════

def main() -> int:
    if os.environ.get("DISABLE_MEMORY") == "1":
        print(json.dumps({"written": False, "reason": "DISABLE_MEMORY=1"}, ensure_ascii=False))
        return 0

    parser = argparse.ArgumentParser(description="决策记录单入口：propose + append + update_profile 三步合一。")
    parser.add_argument("--query", required=True, help="本轮用户原始问题")
    parser.add_argument("--decision", required=True, help="用户决策词，例如：观望 / 放弃 / 做 / 小步验证")
    parser.add_argument("--insight", default="", help="用户对自身决策模式的洞察，一句话（可选）")
    parser.add_argument("--run-log-path", default="", help="本轮 run_log_path；不传则自动匹配最近日志")
    args = parser.parse_args()

    # 步骤 1：解析决策词
    final_status = resolve_final_status(args.decision)
    final_action_text = normalize_final_action(args.decision)

    # 步骤 2：从 run log 提取证据（自动查找，无需手传路径）
    run_log = find_run_log(args.query, args.run_log_path)
    evidence_sources = extract_evidence_sources(run_log)
    key_evidence = format_sources_as_key_evidence(evidence_sources) or extract_evidence(run_log)

    # 步骤 3：组装 record
    insight = args.insight if args.insight else "（待补充：这次决策让你对自己的决策模式学到了什么？）"
    record: Dict[str, Any] = {
        "date": date.today().isoformat(),
        "user_query": extract_query(run_log, args.query),
        "trigger_reason_type": trigger_type(args.query),
        "trigger_reason_note": derive_information_trigger(args.query),
        "scene": derive_scene(args.query, run_log),
        "information_trigger": derive_information_trigger(args.query),
        "decision_context": extract_decision_context(run_log),
        "default_action": derive_default_action(args.query, run_log),
        "final_status": final_status,
        "final_action": final_action_text,
        "key_evidence": key_evidence,
        "evidence_sources": evidence_sources,
        "decision_turning_point": derive_decision_turning_point(args.query, args.decision, final_status),
        "next_action": derive_next_action(args.query, final_action_text, final_status, run_log),
        "insight": insight,
        "confidence": "medium",
        "user_decision_raw": args.decision,
        "source_run_id": str(run_log.get("run_id", "")) if run_log else "",
        "source_run_log_path": str(run_log.get("_run_log_path", "")) if run_log else "",
    }
    record["record_id"] = compute_record_id(record)

    # 步骤 4：写入 JSONL（去重）
    RECORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if record["record_id"] in existing_record_ids():
        print(json.dumps({"written": False, "deduped": True, "record_id": record["record_id"]}, ensure_ascii=False))
        return 0

    with RECORDS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    # 步骤 5：刷新个人决策画像
    all_records = read_all_records()
    PROFILE_FILE.write_text(build_profile(all_records), encoding="utf-8")

    print(json.dumps({
        "written": True,
        "record_id": record["record_id"],
        "final_status": final_status,
        "total_records": len(all_records),
        "profile_updated": str(PROFILE_FILE),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
