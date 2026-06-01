#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from info_alchemist_paths import data_dir, reports_dir, skill_dir
from render_html_report import publish_html_report, report_filename_stem
from run_log import read_log, record_stage, run_path


REQUIRED_REPORT_LINES = [
    "INFO_ALCHEMIST=TRUE",
    "# 信息炼金报告",
    "## 核心判断",
    "## 决策问题",
    "## 专家判断",
    "## 候选行动",
    "## 高价值证据",
    "## 缺失的证据",
    "## 下一步行动",
]

REQUIRED_SECTION_HEADINGS = REQUIRED_REPORT_LINES[2:]
REQUIRED_EVIDENCE_TABLE_HEADER = "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 |"
REQUIRED_EVIDENCE_SCORE_COLUMNS = ["证据质量", "VOI"]
REPORT_TITLE_RE = re.compile(r"^#\s+(?:\[)?信息炼金报告(?:\]\([^)]+\))?\s*$")

DISALLOWED_USER_VISIBLE_TOKENS = [
    "final_status",
    "evidence_gaps",
    "painful_evidence",
    "next_minimum_action",
    "stop_search_rule",
    "final_status: probe",
    "Tavily",
    "TAVILY",
    "tavily",
    "Tavily Search",
    "TikHub",
    "TIKHUB",
    "tikhub",
]

DISALLOWED_FREEFORM_LABELS = [
    "快报",
    "简报",
    "先看行业变化",
    "继续查，",
    "如果你要",
]


def existing_final_output(run_id: str) -> dict:
    try:
        log = read_log(run_id)
    except Exception:
        return {}
    payload = log.get("final_output")
    return payload if isinstance(payload, dict) else {}


def read_text(path: str) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    return sys.stdin.read()


TEMP_REPORT_FILE_RE = re.compile(r"^(?:tmp[-_].*report.*|tmp_info_alchemist_report_.*)\.md$")


def cleanup_temp_report_source(path: str) -> str:
    if not path:
        return ""
    source_path = Path(path).expanduser()
    if not source_path.exists() or not source_path.is_file():
        return ""
    try:
        source = source_path.resolve()
        root = data_dir().resolve()
    except OSError:
        return ""
    if source.parent != root:
        return ""
    if not TEMP_REPORT_FILE_RE.match(source.name):
        return ""
    source.unlink()
    return str(source)


def estimate_tokens_from_chars(text: str) -> int:
    return len(text or "") // 3


def strip_skill_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                return "\n".join(lines[index + 1:]).strip()
    return text.strip()


def token_item(key: str, label: str, text: str, direction: str = "input") -> Dict[str, Any]:
    chars = len(text or "")
    return {
        "key": key,
        "label": label,
        "direction": direction,
        "chars": chars,
        "tokens_est": estimate_tokens_from_chars(text),
    }


def json_token_item(key: str, label: str, value: Any, direction: str = "input") -> Dict[str, Any]:
    if value in (None, "", [], {}):
        return {
            "key": key,
            "label": label,
            "direction": direction,
            "chars": 0,
            "tokens_est": 0,
            "available": False,
            "reason": "run log 中没有该环节数据。",
        }
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    item = token_item(key, label, text, direction=direction)
    item["available"] = True
    return item


def skill_markdown_token_item() -> Dict[str, Any]:
    path = skill_dir() / "SKILL.md"
    try:
        body = strip_skill_frontmatter(path.read_text(encoding="utf-8"))
    except OSError:
        body = ""
    return token_item("skill_md", "Skill 规则", body)


def read_run_log_or_empty(run_id: str) -> Dict[str, Any]:
    try:
        return read_log(run_id)
    except Exception:
        return {}


def user_input_token_item(log: Dict[str, Any]) -> Dict[str, Any]:
    intent = log.get("intent") if isinstance(log.get("intent"), dict) else {}
    fields = {
        key: intent.get(key)
        for key in [
            "user_query",
            "topic",
            "confirmed_intent",
            "confirmed_intent_type",
            "decision_context",
            "candidate_actions",
            "default_action",
            "voi_information_needed",
        ]
        if intent.get(key) not in (None, "", [], {})
    }
    return json_token_item("user_input", "用户输入", fields, direction="input")


def report_context_token_item(run_id: str) -> Dict[str, Any]:
    try:
        log = read_log(run_id)
        plan_output = log.get("search_plan") if isinstance(log.get("search_plan"), dict) else {}
        search_payload = log.get("tavily_result") if isinstance(log.get("tavily_result"), dict) else {}
        synthesis = log.get("synthesis") if isinstance(log.get("synthesis"), dict) else {}
        if not plan_output or not search_payload or not synthesis:
            return {
                "key": "report_context",
                "label": "报告上下文",
                "chars": 0,
                "tokens_est": 0,
                "direction": "input",
                "available": False,
                "reason": "缺少 search_plan / tavily_result / synthesis run log，无法重建报告上下文。",
            }
        from formal_run import report_context

        context = report_context(plan_output, search_payload, synthesis, str(run_path(run_id)))
        context_text = json.dumps(context, ensure_ascii=False, sort_keys=True)
        item = token_item("report_context", "报告上下文", context_text)
        item["available"] = True
        return item
    except Exception as exc:
        return {
            "key": "report_context",
            "label": "报告上下文",
            "chars": 0,
            "tokens_est": 0,
            "direction": "input",
            "available": False,
            "reason": f"报告上下文估算失败：{exc}",
        }


def estimate_token_usage(run_id: str, report_text: str) -> Dict[str, Any]:
    log = read_run_log_or_empty(run_id)
    search_payload = log.get("tavily_result") if isinstance(log.get("tavily_result"), dict) else {}
    synthesis = log.get("synthesis") if isinstance(log.get("synthesis"), dict) else {}
    search_summary: Any = {}
    evidence_pack: Any = {}
    try:
        from formal_run import build_evidence_pack, search_result_summary

        search_summary = search_result_summary(search_payload) if search_payload else {}
        evidence_pack = build_evidence_pack(synthesis) if synthesis else {}
    except Exception:
        search_summary = {}
        evidence_pack = {}
    breakdown: List[Dict[str, Any]] = [
        skill_markdown_token_item(),
        user_input_token_item(log),
        report_context_token_item(run_id),
        json_token_item("intent_output", "意图识别输出", log.get("intent"), direction="output"),
        json_token_item("search_plan_output", "搜索计划输出", log.get("search_plan"), direction="output"),
        json_token_item("search_summary_output", "搜索结果摘要输出", search_summary, direction="output"),
        json_token_item("evidence_pack_output", "证据整理输出", evidence_pack, direction="output"),
        token_item("final_report", "最终报告输出", report_text.strip(), direction="output"),
    ]
    total_chars = sum(int(item.get("chars", 0) or 0) for item in breakdown)
    total_tokens = sum(int(item.get("tokens_est", 0) or 0) for item in breakdown)
    input_tokens = sum(int(item.get("tokens_est", 0) or 0) for item in breakdown if item.get("direction") == "input")
    output_tokens = sum(int(item.get("tokens_est", 0) or 0) for item in breakdown if item.get("direction") == "output")
    return {
        "method": "chars_div_3",
        "method_label": "字符数 / 3 粗估",
        "is_estimate": True,
        "total_chars": total_chars,
        "total_tokens_est": total_tokens,
        "input_tokens_est": input_tokens,
        "output_tokens_est": output_tokens,
        "scope": "full_workflow_reconstructable_io",
        "breakdown": breakdown,
        "excluded": [
            "外部搜索 API 本身不计入 LLM token；只有进入 AI 上下文或全流程摘要的压缩内容计入估算。",
            "未写入 run log 的宿主模型临时回复、隐藏推理、工具调用包装文本无法静态估算。",
        ],
        "note": "这是参考 skill-scorer 的静态估算，不是模型服务账单；精确 input/output 仍以模型返回的 usage 为准。",
    }


def format_count(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def markdown_token_label(label: Any, direction: str) -> str:
    text = str(label or "").strip()
    if direction == "output":
        text = re.sub(r"输出$", "", text).strip()
        if text == "最终报告":
            text = "炼金报告"
    return text or "环节"


def token_usage_markdown(token_usage: Dict[str, Any]) -> str:
    if not token_usage:
        return ""
    lines = [
        "---",
        "## Token 消耗估算",
        f"- 合计：约 {format_count(token_usage.get('total_tokens_est'))} tokens",
        f"- 拆分：输入约 {format_count(token_usage.get('input_tokens_est'))} tokens，输出约 {format_count(token_usage.get('output_tokens_est'))} tokens",
    ]
    for item in token_usage.get("breakdown", []):
        if not isinstance(item, dict):
            continue
        available = item.get("available", True)
        suffix = "" if available else "（未取得完整 run log，暂不计入）"
        direction_label = "输出" if item.get("direction") == "output" else "输入"
        label = markdown_token_label(item.get("label") or item.get("key") or "环节", str(item.get("direction") or "input"))
        lines.append(
            f"  - {direction_label} · {label}："
            f"{format_count(item.get('chars'))} 字符，约 {format_count(item.get('tokens_est'))} tokens{suffix}"
        )
    return "\n".join(lines)


def append_token_usage_markdown(text: str, token_usage: Dict[str, Any]) -> str:
    footer = token_usage_markdown(token_usage)
    if not footer:
        return text.rstrip()
    if re.search(r"^##\s+Token 消耗估算\s*$", text, flags=re.M):
        return text.rstrip()
    return f"{text.rstrip()}\n\n{footer}"


def strip_token_usage_section(text: str) -> str:
    return re.split(r"\n\s*(?:---\s*\n)?##\s+Token 消耗估算\s*$", text.rstrip(), maxsplit=1, flags=re.M)[0].rstrip()


def markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^{re.escape(heading)}\s*$", flags=re.M)
    match = pattern.search(text)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^\s*---\s*$\n\n^##\s+|^##\s+", text[start:], flags=re.M)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip()


def compact_section_lines(section: str, *, max_lines: int, max_chars: int) -> str:
    output: list[str] = []
    total = 0
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            if output and output[-1]:
                output.append("")
            continue
        if line == "---" or line.startswith("|"):
            continue
        if re.match(r"^[-:| ]+$", line):
            continue
        if line.startswith("### "):
            line = line[4:].strip()
        if len(line) > 220:
            line = line[:217].rstrip() + "..."
        projected = total + len(line) + 1
        if projected > max_chars:
            break
        output.append(line)
        total = projected
        non_empty = [item for item in output if item.strip()]
        if len(non_empty) >= max_lines:
            break
    while output and not output[-1].strip():
        output.pop()
    return "\n".join(output).strip()


def compact_user_visible_text(report_text: str, linked_heading: str, max_chars: int = 2600) -> str:
    clean = strip_token_usage_section(report_text)
    core = compact_section_lines(markdown_section(clean, "## 核心判断"), max_lines=10, max_chars=1100)
    actions = compact_section_lines(markdown_section(clean, "## 候选行动"), max_lines=8, max_chars=650)
    next_steps = compact_section_lines(markdown_section(clean, "## 下一步行动"), max_lines=6, max_chars=550)
    parts = [
        "INFO_ALCHEMIST=TRUE",
        linked_heading.strip(),
    ]
    if core:
        parts.extend(["## 核心判断", core])
    if actions:
        parts.extend(["---", "## 候选行动", actions])
    if next_steps:
        parts.extend(["---", "## 下一步行动", next_steps])
    parts.extend(["", "完整证据、经济性表、HTML 可视化和 token 估算见上方报告链接。"])
    visible = "\n\n".join(part for part in parts if part is not None).strip()
    if len(visible) <= max_chars:
        return visible
    suffix = "\n\n完整证据、经济性表、HTML 可视化和 token 估算见上方报告链接。"
    return visible[: max_chars - len(suffix) - 3].rstrip() + "..." + suffix


def full_user_visible_text(report_text: str, linked_heading: str) -> str:
    clean = strip_token_usage_section(report_text).strip()
    linked_lines = linked_heading.strip().splitlines()
    lines = clean.splitlines()
    for index, line in enumerate(lines):
        if REPORT_TITLE_RE.match(line.strip()):
            return "\n".join(lines[:index] + linked_lines + lines[index + 1:]).strip()

    if lines and lines[0].strip() == "INFO_ALCHEMIST=TRUE":
        rest = "\n".join(lines[1:]).strip()
        parts = [lines[0].strip(), "", linked_heading.strip()]
        if rest:
            parts.extend(["", rest])
        return "\n".join(parts).strip()
    return "\n\n".join(part for part in [linked_heading.strip(), clean] if part).strip()


def save_markdown_report(run_id: str, text: str, token_usage: Optional[Dict[str, Any]] = None) -> str:
    target_dir = reports_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{report_filename_stem(text, run_id)}.md"
    output = append_token_usage_markdown(text, token_usage or {})
    target_path.write_text(output.rstrip() + "\n", encoding="utf-8")
    return str(target_path)


def save_report_draft(run_id: str, text: str) -> str:
    return save_markdown_report(run_id, text)


def previous_non_empty_line(lines: list[str], index: int) -> str:
    for line in reversed(lines[:index]):
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def evidence_table_header_errors(text: str) -> list[str]:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        header = split_table_row(stripped)
        if header[:5] != ["行动影响", "证据方向", "发现了什么", "怎么改变决策", "来源"]:
            continue
        missing = [column for column in REQUIRED_EVIDENCE_SCORE_COLUMNS if column not in header]
        if missing:
            return [f"高价值证据表格必须包含单条证据评分列：{', '.join(missing)}。"]
        return []
    return [f"高价值证据必须使用固定表格表头，且包含评分列：{REQUIRED_EVIDENCE_TABLE_HEADER} 证据质量 | VOI |"]


def validate_report_contract(text: str) -> list[str]:
    errors = []
    lines = [line.rstrip() for line in text.splitlines()]
    if not lines or lines[0] != "INFO_ALCHEMIST=TRUE":
        errors.append("最终报告第一行必须且只能是 INFO_ALCHEMIST=TRUE，前面不能有引用或解释。")

    cursor = -1
    line_positions = {}
    for required in REQUIRED_REPORT_LINES:
        index = -1
        for candidate_index in range(cursor + 1, len(lines)):
            candidate = lines[candidate_index]
            if required == "# 信息炼金报告":
                if REPORT_TITLE_RE.match(candidate):
                    index = candidate_index
                    break
            elif candidate == required:
                index = candidate_index
                break
        if index == -1:
            errors.append(f"缺少固定标题或顺序错误：{required}")
            continue
        cursor = index
        line_positions[required] = index

    for heading in REQUIRED_SECTION_HEADINGS[1:]:
        index = line_positions.get(heading)
        if index is None:
            continue
        if previous_non_empty_line(lines, index) != "---":
            errors.append(f"文字版模块之间必须用独立一行 --- 分割：请在 `{heading}` 前加入 `---`。")

    for token in DISALLOWED_USER_VISIBLE_TOKENS:
        if token in text:
            errors.append(f"用户可见报告不能包含英文字段：{token}")

    for token in DISALLOWED_FREEFORM_LABELS:
        if token in text:
            errors.append(f"用户可见报告不能用自由格式提示替代固定骨架：{token}")

    if "本轮联网搜索全部失败，不能生成证据报告" not in text:
        errors.extend(evidence_table_header_errors(text))
        if not re.search(r"\[[^\]\n]{2,120}\]\(https?://[^)\s]+", text):
            errors.append("高价值证据必须包含至少一个 Markdown 可点击来源链接，例如：[标题](https://example.com)")
        if re.search(r"链接[:：]\s*(?:\n|$)", text):
            errors.append("不能留下空的“链接：”；请把来源写成 Markdown 链接。")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="把最终中文报告写入 Info-Alchemist run log。")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--file", default="")
    parser.add_argument("--status", default="ok")
    parser.add_argument("--mode", choices=["report", "other"], default="report")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖同一 run_id 已记录的 final_output。")
    args = parser.parse_args()

    text = read_text(args.file).strip()
    if not text:
        raise SystemExit("请通过 stdin 或 --file 提供最终输出文本。")
    if args.mode == "report":
        errors = validate_report_contract(text)
        if errors:
            print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False, indent=2))
            return 2

    if not args.overwrite:
        existing = existing_final_output(args.run_id)
        if existing:
            result = {
                "run_id": args.run_id,
                "skipped": True,
                "reason": "final_output 已存在；未重复生成 HTML 或追加 run log。",
                "existing_length": existing.get("length", 0),
            }
            html_report = existing.get("html_report") if isinstance(existing.get("html_report"), dict) else {}
            if html_report:
                result.update({
                    "html_path": html_report.get("html_path", ""),
                    "html_url": html_report.get("html_url", ""),
                    "linked_heading": html_report.get("linked_heading", ""),
                })
            markdown_report_path = existing.get("markdown_report_path") or existing.get("draft_markdown_path")
            if existing.get("text"):
                existing_text = existing.get("text", "")
                source_text = existing_text
                if html_report.get("linked_heading") and markdown_report_path:
                    try:
                        archived_text = Path(str(markdown_report_path)).read_text(encoding="utf-8")
                    except OSError:
                        archived_text = ""
                    if archived_text:
                        source_text = archived_text
                if html_report.get("linked_heading"):
                    result["user_visible_text"] = full_user_visible_text(source_text, html_report["linked_heading"])
                else:
                    result["user_visible_text"] = source_text
            if markdown_report_path:
                result["markdown_report_path"] = markdown_report_path
            token_usage = existing.get("token_usage_estimate")
            if isinstance(token_usage, dict):
                result["token_usage_estimate"] = token_usage
            cleaned_source_path = cleanup_temp_report_source(args.file) if args.mode == "report" else ""
            if cleaned_source_path:
                result["cleaned_source_path"] = cleaned_source_path
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

    html_report = {}
    text_to_record = text
    token_usage: Dict[str, Any] = {}
    if args.mode == "report":
        token_usage = estimate_token_usage(args.run_id, text)
        html_report = publish_html_report(text, args.run_id, token_usage=token_usage)
        text_to_record = full_user_visible_text(text, html_report["linked_heading"])
    markdown_report_path = save_markdown_report(args.run_id, text, token_usage=token_usage) if args.mode == "report" else ""

    payload = {
        "text": text_to_record,
        "length": len(text_to_record),
    }
    if token_usage:
        payload["token_usage_estimate"] = token_usage
    if markdown_report_path:
        payload["markdown_report_path"] = markdown_report_path
    if html_report:
        payload["html_report"] = {
            "html_path": html_report["html_path"],
            "html_url": html_report["html_url"],
            "profile_html_path": html_report.get("profile_html_path", ""),
            "profile_html_url": html_report.get("profile_html_url", ""),
            "linked_heading": html_report["linked_heading"],
        }
    result = record_stage(args.run_id, "final_output", payload, args.status)
    cleaned_source_path = cleanup_temp_report_source(args.file) if args.mode == "report" else ""
    if html_report:
        result.update({
            "markdown_report_path": markdown_report_path,
            "html_path": html_report["html_path"],
            "html_url": html_report["html_url"],
            "profile_html_path": html_report.get("profile_html_path", ""),
            "profile_html_url": html_report.get("profile_html_url", ""),
            "linked_heading": html_report["linked_heading"],
            "user_visible_text": text_to_record,
        })
    if token_usage:
        result["token_usage_estimate"] = token_usage
    if cleaned_source_path:
        result["cleaned_source_path"] = cleaned_source_path
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
