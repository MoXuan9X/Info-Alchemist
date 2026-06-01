#!/usr/bin/env python3
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List


MAX_PROFILE_EVIDENCE_SOURCES = 2

FINAL_STATUS_LABELS = {
    "kill": "放弃",
    "archive": "归档",
    "watch": "观望",
    "probe": "小步验证",
    "act": "执行",
}

TRIGGER_LABELS = {
    "fomo": "看到热点或最新趋势",
    "money_signal": "看到商业化信号",
    "competitor_signal": "看到竞品或市场变化",
    "authority_signal": "看到权威信号",
    "user_need_signal": "看到用户需求或抱怨",
    "efficiency_signal": "看到效率提升机会",
    "curiosity": "低风险好奇",
    "anxiety": "焦虑驱动",
    "other": "需要判断下一步行动",
}


def read_records(path: str) -> List[Dict[str, Any]]:
    records = []
    source = Path(path)
    if not source.exists():
        return records
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
    return records


def cell(value: Any, fallback: str = "待补充") -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    return text.replace("\n", "<br>").replace("|", "\\|")


def markdown_link(title: str, url: str) -> str:
    safe_title = title.replace("[", "\\[").replace("]", "\\]").strip()
    return f"[{safe_title}]({url})" if url else safe_title


def compact_scene(record: Dict[str, Any]) -> str:
    query = str(record.get("user_query", ""))
    scene = scenario(record)
    if "AI" in query and any(token in query for token in ["最新", "趋势", "动态", "新闻", "机会"]):
        return "AI 趋势机会"
    return scene


def evidence_sources(record: Dict[str, Any]) -> List[Dict[str, str]]:
    raw_sources = record.get("evidence_sources") or []
    sources: List[Dict[str, str]] = []
    seen = set()
    if isinstance(raw_sources, list):
        for source in raw_sources:
            if not isinstance(source, dict):
                continue
            title = str(source.get("title", "")).strip()
            url = str(source.get("url", "")).strip()
            if not title:
                continue
            key = (title, url)
            if key in seen:
                continue
            seen.add(key)
            sources.append({"title": title, "url": url})
            if len(sources) >= MAX_PROFILE_EVIDENCE_SOURCES:
                break
    return sources


def format_evidence_sources(record: Dict[str, Any]) -> str:
    sources = evidence_sources(record)
    if sources:
        return "<br>".join(
            f"{index}. {markdown_link(source['title'], source['url'])}"
            for index, source in enumerate(sources, start=1)
        )

    fallback = str(record.get("key_evidence", "")).strip()
    if not fallback:
        return "待补充"
    if "](" in fallback:
        return fallback.replace("\n", "<br>")
    if len(fallback) > 80:
        return "见原始运行日志"
    return fallback


def decision_turning_point(record: Dict[str, Any]) -> str:
    explicit = str(record.get("decision_turning_point", "")).strip()
    if explicit:
        return explicit

    action = final_action(record)
    query = str(record.get("user_query", ""))
    if "关键词页" in action and "工具" in action:
        return "公开新闻只能说明方向热，不足以证明转化；所以先用 SEO 和小工具验证"
    if "参考" in query:
        return "公开搜索适合筛样本，不足以判断真实体验；所以要做少量深拆"
    if str(record.get("final_status", "")) == "probe":
        return "公开证据只支持小步验证，不支持直接重投入"
    if str(record.get("final_status", "")) == "watch":
        return "当前证据不足以改变行动，先设复查条件继续观察"
    insight = str(record.get("insight", "")).strip()
    if insight and "待补充" not in insight:
        return insight
    return "待补充"


def confidence(count: int) -> str:
    if count >= 5:
        return "高"
    if count >= 3:
        return "中"
    return "低"


def profile_note(count: int) -> str:
    if count < 3:
        return "当前只记录线索，不生成稳定偏差判断。"
    if count < 5:
        return "已出现重复线索，但仍需用户确认后再升级为稳定模式。"
    return "已积累多次记录，可生成下次询证提醒，但仍需继续用新证据校正。"


def scenario(record: Dict[str, Any]) -> str:
    explicit = record.get("scene") or record.get("scenario")
    if explicit:
        return str(explicit)
    query = str(record.get("user_query", ""))
    context = str(record.get("decision_context", ""))
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
    return cell(query or context, "未命名决策场景")


def information_trigger(record: Dict[str, Any]) -> str:
    explicit = record.get("information_trigger") or record.get("trigger_reason_note")
    query = str(record.get("user_query", ""))
    if explicit and explicit != "根据搜索报告和用户决策自动生成。":
        return str(explicit)
    if "参考" in query:
        return "想找值得参考的网站"
    if any(token in query for token in ["最新", "趋势", "动态", "新闻"]):
        return "想了解最新变化"
    if "机会" in query:
        return "想判断是否有机会"
    return TRIGGER_LABELS.get(str(record.get("trigger_reason_type", "other")), "需要判断下一步行动")


def default_action(record: Dict[str, Any]) -> str:
    value = str(record.get("default_action", "")).strip()
    if value:
        return value
    query = str(record.get("user_query", ""))
    if "参考" in query:
        return "继续收集更多名单"
    if any(token in query for token in ["最新", "趋势", "动态", "新闻"]):
        return "继续观察最新动态"
    return "继续收集更多信息"


def final_action(record: Dict[str, Any]) -> str:
    explicit = record.get("final_action") or record.get("user_decision_raw")
    if explicit:
        return str(explicit)
    return FINAL_STATUS_LABELS.get(str(record.get("final_status", "watch")), "观望")


def next_action(record: Dict[str, Any]) -> str:
    explicit = str(record.get("next_action", "")).strip()
    if explicit and not explicit.startswith("补齐证据缺口："):
        return explicit
    query = str(record.get("user_query", ""))
    status = str(record.get("final_status", ""))
    if "参考" in query:
        return "做产品体验拆解表"
    if status == "probe":
        return "设计最小验证动作"
    if status == "watch":
        return "设置下一次复查条件"
    if status == "kill":
        return "归档原因，不继续投入"
    return explicit or "待补充"


def recent_records_table(records: List[Dict[str, Any]]) -> str:
    rows = ["| 日期 | 场景 | 触发因素 | 原始动作 | 决策转折 | 最终动作 | 证据来源 |", "|---|---|---|---|---|---|---|"]
    for record in records[-10:]:
        rows.append(
            "| {date} | {scene} | {trigger} | {default} | {turning_point} | {final} | {sources} |".format(
                date=cell(record.get("date"), date.today().isoformat()),
                scene=cell(compact_scene(record)),
                trigger=cell(information_trigger(record)),
                default=cell(default_action(record)),
                turning_point=cell(decision_turning_point(record)),
                final=cell(final_action(record)),
                sources=cell(format_evidence_sources(record)),
            )
        )
    if not records:
        rows.append("| 待补充 | 待补充 | 待补充 | 待补充 | 待补充 | 待补充 | 待补充 |")
    return "\n".join(rows)


def pattern_clue(record: Dict[str, Any]) -> str:
    explicit = record.get("pattern_clue")
    if explicit:
        return str(explicit)
    query = str(record.get("user_query", ""))
    insight = str(record.get("insight", ""))
    if "参考" in query:
        return "参考类调研更适合从“找名单”转成“少量样本深拆”"
    if any(token in query for token in ["最新", "趋势", "动态", "新闻"]):
        return "趋势类查询需要先确认会改变哪个行动"
    if "机会" in query:
        return "机会判断需要从公开热度转向可验证行动信号"
    if insight and "待补充" not in insight:
        return insight
    return "该类查询需要先明确默认动作和改变行动的证据"


def pattern_rows(records: List[Dict[str, Any]]) -> str:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[pattern_clue(record)].append(record)
    rows = ["| 模式线索 | 出现次数 | 首次出现 | 最近出现 | 置信度 | 当前判断 |", "|---|---:|---|---|---|---|"]
    for clue, items in sorted(grouped.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        dates = [str(item.get("date", "")) for item in items if item.get("date")]
        count = len(items)
        conf = confidence(count)
        if count >= 3:
            judgment = "可作为候选稳定模式，仍需用户确认"
        elif count == 2:
            judgment = "出现重复线索，继续观察"
        else:
            judgment = "暂不升级为稳定模式"
        rows.append(f"| {cell(clue)} | {count} | {cell(min(dates) if dates else '')} | {cell(max(dates) if dates else '')} | {conf} | {judgment} |")
    if not records:
        rows.append("| 暂无线索 | 0 | 待补充 | 待补充 | 低 | 暂不生成判断 |")
    return "\n".join(rows)


def evidence_type_rows(records: List[Dict[str, Any]]) -> str:
    last_public = max(
        (
            str(record.get("date", ""))
            for record in records
            if record.get("evidence_sources") or record.get("key_evidence")
        ),
        default="待补充",
    )
    is_reference = any("参考" in str(record.get("user_query", "")) for record in records)
    public_impact = "适合筛候选对象，但不足以判断真实体验" if is_reference else "适合形成初步判断，但不足以证明真实行动价值"
    return "\n".join([
        "| 证据类型 | 对行动的影响 | 最近出现 |",
        "|---|---|---|",
        f"| 公开搜索 | {public_impact} | {cell(last_public)} |",
        "| 亲自体验 / 录屏 / 截图 | 能判断新用户路径是否顺畅 | 待补充 |",
        "| 点击 / 留资 / 转化数据 | 能判断是否值得继续投入 | 待补充 |",
    ])


def insights(records: List[Dict[str, Any]]) -> str:
    items = []
    seen = set()
    for record in records[-10:]:
        insight = str(record.get("insight", "")).strip()
        if not insight or "待补充" in insight or insight in seen:
            continue
        seen.add(insight)
        items.append(insight)
    if not items and any("参考" in str(record.get("user_query", "")) for record in records):
        items = [
            "用户在“参考类调研”里，真正需要的不是更多名单，而是可复用的设计证据。",
            "当问题是“哪些值得参考”时，最佳下一步通常是限制样本数量，做深度拆解。",
        ]
    if not items:
        return "- 暂无可用洞察。"
    return "\n".join(f"- {item}" for item in items[-5:])


def guardrails(records: List[Dict[str, Any]]) -> str:
    rows = ["| 护栏建议 | 触发条件 | 状态 |", "|---|---|---|"]
    has_reference = any("参考" in str(record.get("user_query", "")) for record in records)
    if has_reference:
        rows.append("| 参考类问题默认限制为 5 个样本，不继续无限扩展名单 | 再次出现“哪些值得参考”类问题 | 候选中 |")
        rows.append("| 如果搜索只是在增加名单，而不能改变拆解对象，应停止搜索 | 出现信息堆积倾向 | 候选中 |")
    if any(any(token in str(record.get("user_query", "")) for token in ["最新", "趋势", "动态", "新闻"]) for record in records):
        rows.append("| 最新/趋势类问题先确认用途，不直接扩展新闻列表 | 再次出现最新趋势查询 | 候选中 |")
    if len(rows) == 2:
        rows.append("| 暂不生成护栏 | 记录不足 | 候选中 |")
    return "\n".join(rows)


def build_profile(records: List[Dict[str, Any]]) -> str:
    updated = max((str(record.get("date", "")) for record in records if record.get("date")), default=date.today().isoformat())
    count = len(records)
    return f"""# 个人决策画像

最近更新：{updated}
已记录决策：{count} 条
画像成熟度：{confidence(count)}
画像说明：{profile_note(count)}

## 近期决策记录

{recent_records_table(records)}

## 惯性决策模式

{pattern_rows(records)}

## 有效证据类型

{evidence_type_rows(records)}

## 最近决策洞察

{insights(records)}

## 下次询证提醒

{guardrails(records)}
"""


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit("用法：update_personal_voi_profile.py <records.jsonl> <output.md>")

    records = read_records(sys.argv[1])
    target = Path(sys.argv[2])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_profile(records), encoding="utf-8")
    print(json.dumps({"updated": True, "records": len(records), "target": str(target)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
