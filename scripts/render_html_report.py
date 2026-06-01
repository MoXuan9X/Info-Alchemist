#!/usr/bin/env python3
import argparse
from datetime import datetime
import html
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import build_opener, ProxyHandler

from info_alchemist_paths import html_reports_dir, profile_file, runs_dir, skill_dir


TITLE_RE = re.compile(r"^#\s+(?:\[)?信息炼金报告(?:\]\([^)]+\))?\s*$")
REPORT_LINK_LABEL = "点击查看->可视化《信息炼金报告》"
REPORT_LINK_RE = re.compile(
    rf"^\[(?:查看完整 HTML 可视化报告|{re.escape(REPORT_LINK_LABEL)})\]\((?:https?://[^)\s]+|file://[^)\s]+)\)\s*$"
)
LINK_RE = re.compile(r"\[([^\]\n]{1,180})\]\((https?://[^)\s]+|file://[^)\s]+)\)")
SECTION_ANCHORS = {
    "核心判断": "core",
    "决策问题": "question",
    "专家判断": "expert",
    "候选行动": "actions",
    "高价值证据": "evidence",
    "缺失的证据": "gaps",
    "下一步行动": "next",
}
REMOVED_USER_MODULE_TITLE_RE = re.compile(r"(成本结构测评|7\s*天验证闸门)")


def default_output_dir() -> Path:
    return html_reports_dir()


def default_profile_path() -> Path:
    return profile_file()


def html_report_port() -> int:
    raw = os.environ.get("INFO_ALCHEMIST_HTML_REPORT_PORT", "8765").strip()
    try:
        port = int(raw)
    except ValueError:
        return 8765
    return port if 1024 <= port <= 65535 else 8765


def html_report_port_span() -> int:
    raw = os.environ.get("INFO_ALCHEMIST_HTML_REPORT_PORT_SPAN", "100").strip()
    try:
        span = int(raw)
    except ValueError:
        return 100
    return max(1, min(span, 1000))


def html_report_host() -> str:
    return os.environ.get("INFO_ALCHEMIST_HTML_REPORT_HOST", "127.0.0.1").strip() or "127.0.0.1"


def safe_run_id(run_id: str) -> str:
    cleaned = "".join(ch for ch in run_id.strip() if ch.isalnum() or ch in {"-", "_"})
    if not cleaned:
        raise ValueError("run_id 不能为空。")
    if cleaned != run_id.strip():
        raise ValueError("run_id 只能包含字母、数字、短横线和下划线。")
    return cleaned


def read_text(path: str) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    return sys.stdin.read()


def strip_activation(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    if lines and lines[0] == "INFO_ALCHEMIST=TRUE":
        lines = lines[1:]
    lines = [line for line in lines if not REPORT_LINK_RE.match(line.strip())]
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).strip()


def linked_heading(html_url: str) -> str:
    # Feishu parses Markdown links inside headings inconsistently. Keep the
    # heading plain and put an http(s) report entry immediately below it.
    return f"# 信息炼金报告\n\n[{REPORT_LINK_LABEL}]({html_url})"


def with_linked_heading(text: str, html_url: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    for index, line in enumerate(lines):
        if TITLE_RE.match(line):
            lines[index] = linked_heading(html_url)
            return "\n".join(lines).strip()
    if lines and lines[0] == "INFO_ALCHEMIST=TRUE":
        return "\n".join([lines[0], "", linked_heading(html_url), *lines[1:]]).strip()
    return "\n".join([linked_heading(html_url), "", *lines]).strip()


def inline_markdown(value: str) -> str:
    tokens: List[str] = []

    def link_repl(match: re.Match[str]) -> str:
        label = html.escape(match.group(1), quote=False)
        href = html.escape(match.group(2), quote=True)
        tokens.append(f'<a href="{href}" target="_blank" rel="noreferrer">{label}</a>')
        return f"__LINK_TOKEN_{len(tokens) - 1}__"

    value = LINK_RE.sub(link_repl, value)
    value = html.escape(value, quote=False)
    value = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", value)
    for index, token in enumerate(tokens):
        value = value.replace(f"__LINK_TOKEN_{index}__", token)
    return value


def split_table_row(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def table_profile(header: List[str]) -> Tuple[str, str]:
    normalized = [cell.strip() for cell in header]
    if normalized[:5] == ["行动影响", "证据方向", "发现了什么", "怎么改变决策", "来源"]:
        if len(normalized) >= 7:
            return (
                " evidence-table",
                "<colgroup><col style=\"width:8%\"><col style=\"width:12%\"><col style=\"width:31%\"><col style=\"width:27%\"><col style=\"width:14%\"><col style=\"width:4%\"><col style=\"width:4%\"></colgroup>",
            )
        return (
            " evidence-table",
            "<colgroup><col style=\"width:8%\"><col style=\"width:12%\"><col style=\"width:34%\"><col style=\"width:30%\"><col style=\"width:16%\"></colgroup>",
        )
    if len(normalized) >= 7 and "领域专家" in normalized[0] and "可信度" in normalized:
        width = 100 / len(normalized)
        cols = "".join(f"<col style=\"width:{width:.3f}%\">" for _ in normalized)
        return (" expert-table", f"<colgroup>{cols}</colgroup>")
    return ("", "")


def render_table(rows: List[str]) -> str:
    parsed = [split_table_row(row) for row in rows if row.strip()]
    if len(parsed) < 2:
        return ""
    header = parsed[0]
    body = parsed[2:] if is_table_separator(rows[1]) else parsed[1:]
    profile_class, colgroup = table_profile(header)
    thead = "".join(f"<th>{inline_markdown(cell)}</th>" for cell in header)
    tbody_rows = []
    for row in body:
        cells = "".join(f"<td>{inline_markdown(cell)}</td>" for cell in row)
        tbody_rows.append(f"<tr>{cells}</tr>")
    return f"<div class=\"table-wrap\"><table class=\"report-table{profile_class}\">{colgroup}<thead><tr>{thead}</tr></thead><tbody>{''.join(tbody_rows)}</tbody></table></div>"


def render_parsed_table(header: List[str], rows: List[List[str]], table_class: str = "") -> str:
    if not header or not rows:
        return ""
    profile_class, colgroup = table_profile(header)
    class_names = f"report-table{profile_class} {table_class}".strip()
    thead = "".join(f"<th>{inline_markdown(cell)}</th>" for cell in header)
    body = []
    for row in rows:
        cells = row + [""] * max(0, len(header) - len(row))
        body.append("".join(f"<td>{inline_markdown(cell)}</td>" for cell in cells[: len(header)]))
    return f'<div class="table-wrap"><table class="{class_names}">{colgroup}<thead><tr>{thead}</tr></thead><tbody>{"".join(f"<tr>{cells}</tr>" for cells in body)}</tbody></table></div>'


def clean_list_item(value: str) -> str:
    cleaned = value.strip()
    while True:
        next_value = re.sub(r"^[-*]\s+", "", cleaned).strip()
        if next_value == cleaned:
            return cleaned
        cleaned = next_value


def strength_rank(value: str) -> int:
    normalized = value.strip().lower()
    compact = re.sub(r"\s+", "", normalized)
    if not normalized:
        return 0
    if compact.startswith(("中高", "中强")) and len(compact) <= 6:
        return 3
    if re.search(r"\b(?:medium|mid)[-\s]?high\b", normalized):
        return 3
    if compact in {"超高", "很高", "高", "强"} or (compact.startswith("高") and len(compact) <= 4):
        return 4
    if re.fullmatch(r"(?:very\s+)?(?:high|strong)", normalized):
        return 4
    if compact in {"中", "中等", "中度"}:
        return 2
    if re.fullmatch(r"(?:medium|mid)", normalized):
        return 2
    if compact in {"低", "弱"} or (compact.startswith("低") and len(compact) <= 4):
        return 1
    if re.fullmatch(r"(?:low|weak)", normalized):
        return 1
    return 0


def strength_class(value: str) -> str:
    return {
        4: "level-high",
        3: "level-mid-high",
        2: "level-mid",
        1: "level-low",
    }.get(strength_rank(value), "level-unknown")


def row_cell_value(header: List[str], row: List[str], column_name: str, fallback_index: int = 0) -> str:
    cells = row + [""] * max(0, len(header) - len(row))
    if column_name in header:
        index = header.index(column_name)
        if index < len(cells):
            return cells[index]
    if fallback_index < len(cells):
        return cells[fallback_index]
    return ""


def sort_rows_by_strength(header: List[str], rows: List[List[str]], column_name: str, fallback_index: int = 0) -> List[List[str]]:
    return [
        row
        for _, row in sorted(
            enumerate(rows),
            key=lambda indexed: (
                -strength_rank(row_cell_value(header, indexed[1], column_name, fallback_index)),
                indexed[0],
            ),
        )
    ]


def markdown_to_html(markdown: str) -> str:
    lines = strip_activation(markdown).splitlines()
    output: List[str] = []
    list_type = ""
    index = 0

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            output.append(f"</{list_type}>")
            list_type = ""

    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if not stripped:
            close_list()
            index += 1
            continue
        if TITLE_RE.match(stripped):
            close_list()
            output.append("<h1>信息炼金报告</h1>")
            index += 1
            continue
        if stripped.startswith("|") and "|" in stripped[1:]:
            close_list()
            table_rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_rows.append(lines[index])
                index += 1
            output.append(render_table(table_rows))
            continue
        if stripped == "---":
            close_list()
            output.append("<hr>")
            index += 1
            continue
        if stripped.startswith("### "):
            close_list()
            output.append(f"<h3>{inline_markdown(stripped[4:].strip())}</h3>")
            index += 1
            continue
        if stripped.startswith("## "):
            close_list()
            title = stripped[3:].strip()
            anchor = SECTION_ANCHORS.get(title, "")
            anchor_attr = f' id="{anchor}"' if anchor else ""
            output.append(f"<h2{anchor_attr}>{inline_markdown(title)}</h2>")
            index += 1
            continue
        if stripped.startswith(">"):
            close_list()
            output.append(f"<blockquote>{inline_markdown(stripped.lstrip('>').strip())}</blockquote>")
            index += 1
            continue
        if re.match(r"^[-*]\s+", stripped):
            if list_type != "ul":
                close_list()
                list_type = "ul"
                output.append("<ul>")
            output.append(f"<li>{inline_markdown(clean_list_item(stripped))}</li>")
            index += 1
            continue
        numbered = re.match(r"^\d+[.)、]\s+", stripped)
        if numbered:
            if list_type != "ol":
                close_list()
                list_type = "ol"
                output.append("<ol>")
            output.append(f"<li>{inline_markdown(stripped[numbered.end():])}</li>")
            index += 1
            continue
        close_list()
        output.append(f"<p>{inline_markdown(stripped)}</p>")
        index += 1

    close_list()
    return "\n".join(part for part in output if part)


def split_sections(markdown: str) -> Dict[str, str]:
    sections: Dict[str, List[str]] = {}
    current = ""
    for raw_line in strip_activation(markdown).splitlines():
        line = raw_line.rstrip()
        if TITLE_RE.match(line) or line.startswith("# "):
            continue
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def is_removed_user_module_title(title: str) -> bool:
    cleaned = re.sub(r"[*_`#\s]+", "", title or "")
    return bool(REMOVED_USER_MODULE_TITLE_RE.search(cleaned))


def strip_removed_user_modules(markdown: str) -> str:
    output: List[str] = []
    skipping = False
    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("### "):
            title = stripped[4:].strip()
            skipping = is_removed_user_module_title(title)
            if skipping:
                continue
        if skipping:
            continue
        output.append(raw_line)
    return "\n".join(output).strip()


def split_any_markdown_sections(markdown: str) -> Tuple[str, Dict[str, str]]:
    intro: List[str] = []
    sections: Dict[str, List[str]] = {}
    current = ""
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
        elif line.strip():
            intro.append(line)
    return "\n".join(intro).strip(), {key: "\n".join(value).strip() for key, value in sections.items()}


def plain_text(markdown: str) -> str:
    text = LINK_RE.sub(lambda m: m.group(1), markdown)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"^#+\s+", "", text, flags=re.M)
    text = re.sub(r"^\|.*\|$", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*\d+[.)、]\s+", "", text, flags=re.M)
    text = re.sub(r"\n{2,}", "\n", text)
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def first_sentence(markdown: str, fallback: str) -> str:
    text = plain_text(markdown)
    if not text:
        return fallback
    match = re.search(r"(.{18,140}?[。！？])", text)
    if match:
        return match.group(1)
    return text[:140]


def intro_before_list(markdown: str, fallback: str) -> str:
    lines: List[str] = []
    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if lines:
                break
            continue
        if (
            re.match(r"^\d+[.)、]\s+", stripped)
            or re.match(r"^[-*]\s+", stripped)
            or stripped.startswith("|")
            or stripped.startswith("### ")
        ):
            break
        if re.match(r"^(?:\*\*)?报告模式(?:\*\*)?[:：]", stripped):
            continue
        lines.append(stripped)
    intro = plain_text("\n".join(lines))
    return intro or first_sentence(markdown, fallback)


def extract_report_mode_label(markdown: str) -> str:
    for raw_line in markdown.splitlines():
        stripped = raw_line.strip().strip("*")
        match = re.match(r"^报告模式[:：]\s*(.+)$", stripped)
        if match:
            return plain_text(match.group(1)).strip()
    return ""


def extract_decision_object(markdown: str) -> str:
    for raw_line in markdown.splitlines():
        stripped = raw_line.strip().strip("*")
        match = re.match(r"^决策对象[:：]\s*(.+)$", stripped)
        if match:
            return plain_text(match.group(1)).strip()
    return ""


def report_document_title(decision_object: str) -> str:
    subtitle = clamp_text(decision_object, 42)
    return f"信息炼金报告-{subtitle}" if subtitle else "信息炼金报告"


def report_date_suffix(run_id: str) -> str:
    match = re.match(r"^(\d{8})", run_id.strip())
    if match:
        return match.group(1)
    return datetime.now().strftime("%Y%m%d")


def safe_report_filename_part(value: str) -> str:
    cleaned = plain_text(value)
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip(" .-")
    return cleaned[:120].rstrip(" .-") or "信息炼金报告"


def report_filename_stem(report_markdown: str, run_id: str) -> str:
    sections = split_sections(report_markdown)
    report_title = report_document_title(extract_decision_object(sections.get("决策问题", "")))
    return f"{safe_report_filename_part(report_title)}-{report_date_suffix(run_id)}"


def html_report_filename_stem(run_id: str) -> str:
    return safe_run_id(run_id)


def extract_numbered_items(markdown: str, limit: int = 6) -> List[str]:
    items: List[str] = []
    for line in markdown.splitlines():
        match = re.match(r"^\s*\d+[.)、]\s+(.+)$", line.strip())
        if match:
            items.append(match.group(1).strip())
            if len(items) >= limit:
                break
    return items


def extract_bullet_items(markdown: str, limit: int = 6) -> List[str]:
    items: List[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if re.match(r"^[-*]\s+", stripped):
            items.append(clean_list_item(stripped))
            if len(items) >= limit:
                break
    return items


def extract_quote(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            return stripped.lstrip(">").strip()
    return first_sentence(markdown, fallback)


def split_h3_sections(markdown: str) -> List[Tuple[str, str]]:
    sections: List[Tuple[str, List[str]]] = []
    current_title = ""
    for line in markdown.splitlines():
        if line.startswith("### "):
            current_title = line[4:].strip()
            sections.append((current_title, []))
            continue
        if current_title and sections:
            sections[-1][1].append(line)
    return [(title, "\n".join(lines).strip()) for title, lines in sections]


def split_h4_sections(markdown: str) -> List[Tuple[str, str]]:
    sections: List[Tuple[str, List[str]]] = []
    current_title = ""
    for line in markdown.splitlines():
        if line.startswith("#### "):
            current_title = line[5:].strip()
            sections.append((current_title, []))
            continue
        if current_title and sections:
            sections[-1][1].append(line)
    return [(title, "\n".join(lines).strip()) for title, lines in sections]


def split_h3_sections_with_intro(markdown: str) -> Tuple[str, List[Tuple[str, str]]]:
    intro_lines: List[str] = []
    sections: List[Tuple[str, List[str]]] = []
    current_title = ""
    for line in markdown.splitlines():
        if line.startswith("### "):
            current_title = line[4:].strip()
            sections.append((current_title, []))
            continue
        if current_title and sections:
            sections[-1][1].append(line)
        elif line.strip() and line.strip() != "---":
            intro_lines.append(line)
    return (
        "\n".join(intro_lines).strip(),
        [(title, "\n".join(lines).strip()) for title, lines in sections],
    )


def split_numbered_blocks_with_intro(markdown: str) -> Tuple[str, List[Tuple[str, str]]]:
    intro_lines: List[str] = []
    blocks: List[Tuple[str, List[str]]] = []
    current_title = ""
    for line in markdown.splitlines():
        stripped = line.strip()
        match = re.match(r"^(\d+)[.)、]\s+(.+)$", stripped)
        if match:
            current_title = match.group(2).strip()
            blocks.append((current_title, []))
            continue
        if current_title and blocks:
            blocks[-1][1].append(line)
        elif stripped and stripped != "---":
            intro_lines.append(line)
    return (
        "\n".join(intro_lines).strip(),
        [(title, "\n".join(lines).strip()) for title, lines in blocks],
    )


def parse_first_table(markdown: str) -> Tuple[List[str], List[List[str]]]:
    rows: List[str] = []
    in_table = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            rows.append(line)
            in_table = True
            continue
        if in_table:
            break
    if len(rows) < 2:
        return [], []
    header = split_table_row(rows[0])
    start = 2 if len(rows) > 1 and is_table_separator(rows[1]) else 1
    body = [split_table_row(row) for row in rows[start:]]
    return header, body


def parse_contiguous_tables(markdown: str) -> List[Tuple[List[str], List[List[str]]]]:
    tables: List[Tuple[List[str], List[List[str]]]] = []
    rows: List[str] = []
    for line in markdown.splitlines():
        if line.strip().startswith("|"):
            rows.append(line)
            continue
        if rows:
            header = split_table_row(rows[0])
            start = 2 if len(rows) > 1 and is_table_separator(rows[1]) else 1
            tables.append((header, [split_table_row(row) for row in rows[start:]]))
            rows = []
    if rows:
        header = split_table_row(rows[0])
        start = 2 if len(rows) > 1 and is_table_separator(rows[1]) else 1
        tables.append((header, [split_table_row(row) for row in rows[start:]]))
    return tables


def table_records(markdown: str) -> List[Dict[str, str]]:
    header, rows = parse_first_table(markdown)
    if not header:
        return []
    records = []
    for row in rows:
        cells = row + [""] * max(0, len(header) - len(row))
        records.append(dict(zip(header, cells)))
    return records


def iter_table_blocks(markdown: str) -> List[Tuple[List[str], List[List[str]]]]:
    blocks: List[List[str]] = []
    current: List[str] = []
    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("|"):
            current.append(raw_line)
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    parsed: List[Tuple[List[str], List[List[str]]]] = []
    for block in blocks:
        if len(block) < 2:
            continue
        header = split_table_row(block[0])
        start = 2 if len(block) > 1 and is_table_separator(block[1]) else 1
        rows = [split_table_row(row) for row in block[start:]]
        if header and rows:
            parsed.append((header, rows))
    return parsed


def table_records_matching(markdown: str, required_columns: List[str]) -> List[Dict[str, str]]:
    for header, rows in iter_table_blocks(markdown):
        if all(column in header for column in required_columns):
            records = []
            for row in rows:
                cells = row + [""] * max(0, len(header) - len(row))
                records.append(dict(zip(header, cells)))
            return records
    return []


def clamp_text(value: str, limit: int = 120) -> str:
    text = plain_text(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def visual_list(items: List[str], class_name: str = "marker-list") -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{inline_markdown(item)}</li>" for item in items)
    return f"<ul class=\"{class_name}\">{lis}</ul>"


def build_question_cards(question_markdown: str) -> str:
    items = extract_numbered_items(question_markdown, 6)
    if not items:
        return ""
    cards = []
    for index, item in enumerate(items, start=1):
        cards.append(
            f"""
            <article class="question-item">
              <span>{index}</span>
              <p>{inline_markdown(item)}</p>
            </article>
            """
        )
    return "".join(cards)


def build_core_cards(core_markdown: str) -> str:
    items = extract_numbered_items(core_markdown, 5) or extract_bullet_items(core_markdown, 5)
    if not items:
        items = [first_sentence(core_markdown, "先看核心判断，再展开证据。")]
    cards = []
    for index, item in enumerate(items[:5], start=1):
        cards.append(
            f"""
            <article class="core-card">
              <span>{index}</span>
              <p>{inline_markdown(item)}</p>
            </article>
            """
        )
    return "".join(cards)


ECONOMICS_SIGNAL_RE = re.compile(
    r"ROI|90\s*天|回本|保本|LTV|CAC|ARPU|经济性|经济测算|财务假设|收入假设|毛利|毛利率|成本结构测评|成本项|官方价格|用量假设|初始投入|月成本|月度变动成本|单次任务成本|7\s*天验证",
    re.I,
)


def economics_source_markdown(sections: Dict[str, str]) -> str:
    return "\n\n".join(
        sections.get(key, "")
        for key in ["核心判断", "决策问题", "候选行动", "高价值证据", "缺失的证据", "下一步行动"]
    )


def economics_table_sets(markdown: str) -> Dict[str, List[Dict[str, str]]]:
    return {
        "cost_structure": (
            table_records_matching(markdown, ["成本项", "价格证据", "月成本"])
            or table_records_matching(markdown, ["成本项", "官方价格", "月成本"])
        ),
        "unit_costs": table_records_matching(markdown, ["任务", "模型成本", "单次成本"]),
        "roi_calculability": table_records_matching(markdown, ["项目", "状态", "结论"]),
        "roi_actions": table_records_matching(markdown, ["候选行动", "初始投入", "保本门槛"]),
        "scenarios": table_records_matching(markdown, ["指标", "保守", "基准", "乐观"]),
        "cost_inputs": (
            table_records_matching(markdown, ["要补的数字", "当前状态", "怎么拿"])
            or table_records_matching(markdown, ["成本项", "当前状态", "怎么补"])
        ),
        "gates": (
            table_records_matching(markdown, ["7 天验证项", "7 天记录什么", "7 天后怎么判断"])
            or table_records_matching(markdown, ["7 天验证项", "通过线", "停止线"])
            or table_records_matching(markdown, ["财务假设", "通过门槛", "失败门槛"])
        ),
    }


def has_economics_display(sections: Dict[str, str]) -> bool:
    source = economics_source_markdown(sections)
    table_sets = economics_table_sets(source)
    if any(table_sets[key] for key in ["cost_structure", "unit_costs", "roi_calculability", "roi_actions", "scenarios", "cost_inputs"]):
        return True
    return bool(ECONOMICS_SIGNAL_RE.search(source))


def economics_summary_text(sections: Dict[str, str]) -> str:
    for raw_line in sections.get("核心判断", "").splitlines():
        stripped = raw_line.strip("-* 0123456789.、")
        if stripped and ECONOMICS_SIGNAL_RE.search(stripped):
            return clamp_text(stripped, 170)
    return "先拆初始投入、月固定成本和单次任务成本；成本和转化输入齐了，再判断 ROI 是否可算。"


def cell_value(record: Dict[str, str], *keys: str, fallback: str = "待补") -> str:
    for key in keys:
        value = str(record.get(key, "") or "").strip()
        if value:
            return value
    return fallback


def records_table(
    records: List[Dict[str, str]],
    columns: List[Tuple[str, Tuple[str, ...]]],
    table_class: str,
    limit: int = 6,
) -> str:
    header = [label for label, _keys in columns]
    rows = [
        [cell_value(record, *keys, fallback="") for _label, keys in columns]
        for record in records[:limit]
    ]
    return render_parsed_table(header, rows, table_class)


def value_has_missing_marker(value: str) -> bool:
    text = str(value or "").strip()
    return bool(text) and any(marker in text for marker in MISSING_ECONOMICS_MARKERS)


def value_has_cost_evidence(value: str) -> bool:
    text = str(value or "").strip()
    if not text or value_has_missing_marker(text):
        return False
    if LINK_RE.search(text):
        return True
    if re.search(r"[$¥€£]|\b\d+(?:\.\d+)?\s*(?:/|per|每|tokens?|credits?|requests?|GB|MB|seat|月|年)", text, re.I):
        return True
    return any(marker in text for marker in ["官方", "公开", "用户提供", "pricing", "价格页", "计费"])


def is_ai_video_context(markdown: str) -> bool:
    compact = re.sub(r"\s+", "", markdown).lower()
    return any(token in compact for token in ["ai视频", "视频站", "video", "veo", "runway", "kling", "luma", "pika"])


def video_cost_record_is_material(record: Dict[str, str]) -> bool:
    cost_item = cell_value(record, "成本项", fallback="")
    combined = " ".join(str(value or "") for value in record.values()).lower()
    if any(token in cost_item for token in ["模型", "API", "GPU", "推理", "媒体", "存储", "CDN", "带宽", "审核", "人工"]):
        return True
    if any(token in combined for token in ["veo", "runway", "kling", "luma", "pika", "replicate", "fal", "runpod", "modal", "gpu", "video", "stream", "mux", "cdn", "bandwidth", "r2", "视频", "带宽"]):
        return True
    if any(token in cost_item for token in ["部署", "服务器", "邮件", "通知"]):
        return False
    return False


def cost_structure_record_has_evidence(record: Dict[str, str], context_markdown: str = "") -> bool:
    if is_ai_video_context(context_markdown) and not video_cost_record_is_material(record):
        return False
    price = cell_value(record, "价格证据", "官方价格", "价格", "公开价格", fallback="")
    source = cell_value(record, "来源", "依据", fallback="")
    if not value_has_cost_evidence(price):
        return False
    if source and value_has_missing_marker(source):
        return False
    return bool(source.strip() or LINK_RE.search(price))


def missing_only_cost_input(record: Dict[str, str]) -> bool:
    status = cell_value(record, "当前状态", fallback="")
    return value_has_missing_marker(status) or status.strip() in {"缺", "缺数据", "待补"}


def missing_roi_record(record: Dict[str, str]) -> bool:
    project = cell_value(record, "项目", fallback="")
    status = cell_value(record, "状态", "当前状态", fallback="")
    conclusion = cell_value(record, "结论", "判断", fallback="")
    combined = f"{project} {status} {conclusion}"
    return bool(re.search(r"ROI|回本|90\\s*天", project, re.I)) and value_has_missing_marker(combined)


def build_cost_structure_table(records: List[Dict[str, str]], context_markdown: str = "") -> str:
    records = [record for record in records if cost_structure_record_has_evidence(record, context_markdown)]
    if not records:
        return ""
    columns = [
        ("成本项", ("成本项",)),
        ("默认工具", ("默认工具", "工具", "供应商")),
        ("价格证据", ("价格证据", "官方价格", "价格", "公开价格")),
    ]
    if any(
        cell_value(record, "用量假设", "用量", "假设", fallback="").strip()
        and not value_has_missing_marker(cell_value(record, "用量假设", "用量", "假设", fallback=""))
        for record in records
    ):
        columns.append(("用量假设", ("用量假设", "用量", "假设")))
    if any(
        cell_value(record, "月成本", "月固定成本", fallback="").strip()
        and not value_has_missing_marker(cell_value(record, "月成本", "月固定成本", fallback=""))
        for record in records
    ):
        columns.append(("月成本", ("月成本", "月固定成本")))
    columns.append(("来源", ("来源", "依据")))
    table = records_table(
        records,
        columns,
        "economics-table",
        limit=8,
    )
    return f"""
    <section class="economics-submodule table-module economics-table-module">
      <h3>成本结构测评</h3>
      {table}
    </section>
    """


def build_unit_cost_table(records: List[Dict[str, str]]) -> str:
    if not records:
        return ""
    table = records_table(
        records,
        [
            ("任务", ("任务",)),
            ("模型成本", ("模型成本",)),
            ("抓取成本", ("抓取成本", "代理成本")),
            ("存储成本", ("存储成本",)),
            ("人工成本", ("人工成本",)),
            ("单次成本", ("单次成本", "单次任务成本")),
        ],
        "economics-table",
        limit=6,
    )
    return f"""
    <section class="economics-submodule table-module economics-table-module">
      <h3>单次任务成本</h3>
      {table}
    </section>
    """


def build_roi_calculability_table(records: List[Dict[str, str]]) -> str:
    if not records or any(missing_roi_record(record) for record in records):
        return ""
    table = records_table(
        records,
        [
            ("项目", ("项目",)),
            ("状态", ("状态", "当前状态")),
            ("结论", ("结论", "判断")),
        ],
        "economics-table",
        limit=6,
    )
    return f"""
    <section class="economics-submodule table-module economics-table-module">
      <h3>ROI 可计算性</h3>
      {table}
    </section>
    """


def build_scenario_cards(records: List[Dict[str, str]]) -> str:
    if not records:
        return ""
    table = records_table(
        records,
        [
            ("指标", ("指标",)),
            ("保守", ("保守",)),
            ("基准", ("基准",)),
            ("乐观", ("乐观",)),
            ("来源/假设", ("来源/假设", "来源", "假设")),
        ],
        "economics-table",
        limit=5,
    )
    return f"""
    <section class="economics-submodule table-module economics-table-module">
      <h3>经济性情景</h3>
      {table}
    </section>
    """


def build_roi_action_cards(records: List[Dict[str, str]]) -> str:
    if not records or not any(record_has_economic_signal(record) for record in records):
        return ""
    columns = [
        ("候选行动", ("候选行动",)),
        ("初始投入", ("初始投入",)),
        ("投入依据", ("初始投入依据", "投入依据", "来源状态")),
        ("月成本", ("月成本", "月度变动成本")),
        ("成本依据", ("月成本依据", "成本依据")),
        ("收入/价格证据", ("收入/价格证据", "收入假设", "价格证据")),
        ("保本门槛", ("保本门槛",)),
    ]
    if any(cell_value(record, "90 天 ROI 区间", "ROI", fallback="").strip() for record in records):
        columns.append(("90 天 ROI", ("90 天 ROI 区间", "ROI")))
    columns.append(("建议", ("建议",)))
    table = records_table(
        records,
        columns,
        "economics-table",
        limit=5,
    )
    return f"""
    <section class="economics-submodule table-module economics-table-module">
      <h3>行动的经济性</h3>
      {table}
    </section>
    """


MISSING_ECONOMICS_MARKERS = (
    "未取得公开证据",
    "上次搜索未返回",
    "暂不能计算",
    "不能计算",
    "待用户估算",
    "待估算",
    "待按",
    "需用量后计算",
    "需实测",
    "需要实测",
    "没有方向级",
    "未取得方向级",
    "缺失",
)


def record_has_economic_signal(record: Dict[str, str]) -> bool:
    keys = [
        "初始投入",
        "月成本",
        "月度变动成本",
        "收入/价格证据",
        "收入假设",
        "价格证据",
        "保本门槛",
        "90 天 ROI 区间",
        "ROI",
    ]
    for key in keys:
        value = str(record.get(key, "") or "").strip()
        if not value:
            continue
        if any(marker in value for marker in MISSING_ECONOMICS_MARKERS):
            continue
        if re.search(r"[$¥€£]|\d", value):
            return True
        if key in {"收入/价格证据", "收入假设", "价格证据"} and "公开" in value:
            return True
    return False


def build_cost_input_table(records: List[Dict[str, str]]) -> str:
    if not records or all(missing_only_cost_input(record) for record in records):
        return ""
    table = records_table(
        records,
        [
            ("要补的数字", ("要补的数字", "成本项")),
            ("当前状态", ("当前状态",)),
            ("怎么拿", ("怎么拿", "怎么补")),
            ("用来判断什么", ("用来判断什么", "用途", "判断")),
        ],
        "economics-table",
        limit=6,
    )
    return f"""
    <section class="economics-submodule table-module economics-table-module">
      <h3>成本补齐清单</h3>
      {table}
    </section>
    """


def build_gate_cards(records: List[Dict[str, str]]) -> str:
    if not records:
        return ""
    table = records_table(
        records,
        [
            ("财务假设", ("财务假设",)),
            ("为什么影响 ROI", ("为什么影响 ROI", "影响")),
            ("最小验证方式", ("最小验证方式", "验证方式")),
            ("通过门槛", ("通过门槛",)),
            ("失败门槛", ("失败门槛",)),
        ],
        "economics-table",
        limit=5,
    )
    return f"""
    <section class="economics-submodule table-module economics-table-module">
      <h3>下一步验证门槛</h3>
      {table}
    </section>
    """


def build_economics_screen(sections: Dict[str, str]) -> str:
    return ""


ACTION_BLOCK_LABELS = {
    "包含候选",
    "代表产品",
    "典型流程",
    "适合借",
    "适合借鉴",
    "先验证",
    "避坑",
    "判断",
    "典型特征",
    "适合原因",
    "适合你的原因",
    "适合的工具站形态",
    "可切入口",
    "可先切的子场景",
    "为什么可看",
    "为什么值得看",
    "为什么适合",
    "为什么优先",
    "为什么值得优先",
    "为什么更容易跑通",
    "为什么不能做泛视频站",
    "不建议现在做",
    "最后容易变成",
    "我的判断",
    "不是先开发，而是先做",
    "用户买的不是 AI，而是",
    "关键不是做“写文案 AI”，而是做",
    "难点",
    "风险",
    "问题",
}

ACTION_REASON_LABELS = {
    "为什么可看",
    "为什么值得看",
    "为什么适合",
    "适合原因",
    "适合你的原因",
    "为什么优先",
    "为什么值得优先",
    "为什么更容易跑通",
}

ACTION_SCOPE_LABELS = {
    "适合的工具站形态",
    "可切入口",
    "可先切的子场景",
    "典型特征",
}

ACTION_VERDICT_LABELS = {
    "判断",
    "我的判断",
    "不是先开发，而是先做",
}


def display_action_label(label: str) -> str:
    if label in {"适合借", "适合借鉴"}:
        return "适合借鉴"
    return label


def split_action_blocks(content: str) -> List[Tuple[str, str]]:
    blocks: List[Tuple[str, List[str]]] = []
    current_label = ""
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        label_match = re.match(r"^(.{2,24}?)[：:]\s*(.*)$", stripped)
        label = label_match.group(1).strip("* ") if label_match else ""
        if label in ACTION_BLOCK_LABELS:
            current_label = label
            blocks.append((current_label, []))
            rest = label_match.group(2).strip() if label_match else ""
            if rest:
                blocks[-1][1].append(rest)
            continue
        if not current_label:
            current_label = "补充说明"
            blocks.append((current_label, []))
        blocks[-1][1].append(raw_line)
    return [(label, "\n".join(lines).strip()) for label, lines in blocks if "\n".join(lines).strip()]


def action_point_list(items: List[str]) -> str:
    if not items:
        return ""
    points = "".join(
        f"""
        <li>
          <p><span>{index}</span>{inline_markdown(item)}</p>
        </li>
        """
        for index, item in enumerate(items, start=1)
    )
    return f"<ol class=\"action-point-list\">{points}</ol>"


def split_detail_parts(markdown: str) -> Tuple[List[str], List[str], List[str]]:
    paragraphs: List[str] = []
    bullets: List[str] = []
    numbers: List[str] = []
    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped == "---":
            continue
        if stripped.startswith("|"):
            continue
        if stripped.startswith("### "):
            continue
        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet_match:
            bullets.append(clean_list_item(stripped))
            continue
        number_match = re.match(r"^\d+[.)、]\s+(.+)$", stripped)
        if number_match:
            numbers.append(number_match.group(1).strip())
            continue
        paragraphs.append(stripped)
    return paragraphs, bullets, numbers


def compact_detail_html(content: str, list_class: str) -> str:
    paragraphs, bullets, numbers = split_detail_parts(content)
    output: List[str] = []
    for paragraph in paragraphs[:4]:
        output.append(f'<p class="compact-copy">{inline_markdown(paragraph)}</p>')
    if bullets:
        output.append(visual_list(bullets[:6], list_class))
    if numbers:
        output.append(action_point_list(numbers[:6]))
    return "".join(output)


STOP_SIGNAL_RE = re.compile(
    r"(如果|一旦|当|只要).*(发现|出现|看到|满足)|"
    r"(没有|也没有|缺少|只是|必须|接近|超过|重试|失败|成本|授权|不成立|不清晰|不明确|无法|不能|太高|太贵|没人|不愿意|风险|消耗)"
)
STOP_ACTION_RE = re.compile(
    r"(那|就|别做|先别|不要做|不再做|停止|暂停|放弃|砍掉|改做|改为|转向|换成|改成|先做)"
)
PIVOT_RE = re.compile(r"(改做|改为|转向|换成|改成|先做|做更窄|更窄)")


def is_stop_signal_item(text: str) -> bool:
    return bool(STOP_SIGNAL_RE.search(text))


def is_stop_action_line(text: str) -> bool:
    return bool(STOP_ACTION_RE.search(text)) and not re.search(r"(如果|一旦|当|只要).*(发现|出现|看到|满足)", text)


def strip_stop_action_prefix(text: str) -> str:
    cleaned = re.sub(r"^(那|那么)?(这个方向)?就", "", text).strip()
    cleaned = re.sub(r"^(那|那么)", "", cleaned).strip()
    return cleaned.strip(" ：:")


def split_stop_action_line(text: str) -> Tuple[str, str]:
    cleaned = strip_stop_action_prefix(text)
    fragments = [fragment.strip() for fragment in re.split(r"[，,；;]", cleaned) if fragment.strip()]
    if len(fragments) >= 2 and PIVOT_RE.search("，".join(fragments[1:])):
        pivot = re.sub(r"^(改做|改为|转向|换成|改成|先做)[:：]?", "", "，".join(fragments[1:])).strip(" ：:")
        return fragments[0].strip(" ：:"), pivot
    match = re.search(r"(.+?)(改做|改为|转向|换成|改成)[:：]?\s*(.*)$", cleaned)
    if match and re.search(r"(别做|先别|不要做|停止|暂停|放弃|砍掉|不再做)", match.group(1)):
        return match.group(1).strip(" ：:"), match.group(3).strip(" ：:")
    return cleaned, ""


def split_stop_rule_parts(content: str) -> Tuple[List[str], List[str], List[str], List[str]]:
    intro: List[str] = []
    trigger_bullets: List[str] = []
    action_lines: List[str] = []
    pivot_items: List[str] = []
    active = ""
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("### "):
            continue
        if re.search(r"(如果|一旦|当|只要).*(发现|出现|看到|满足)", stripped):
            active = "trigger"
            intro.append(stripped)
            continue
        if is_stop_action_line(stripped):
            active = "action"
            action_lines.append(stripped)
            continue
        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet_match:
            item = clean_list_item(stripped)
            if active == "action" and not is_stop_signal_item(item):
                pivot_items.append(item)
            else:
                trigger_bullets.append(item)
            continue
        intro.append(stripped)
    return intro, trigger_bullets, action_lines, pivot_items


def stop_rule_html(content: str) -> str:
    _intro, trigger_bullets, action_lines, pivot_items = split_stop_rule_parts(content)
    if not trigger_bullets or not action_lines:
        return ""
    stop_actions: List[str] = []
    pivot_lines: List[str] = []
    for line in action_lines:
        stop_action, pivot_line = split_stop_action_line(line)
        if stop_action:
            stop_actions.append(stop_action)
        if pivot_line:
            pivot_lines.append(pivot_line)
    pivot_content = "".join(
        f'<p>{inline_markdown(pivot_line)}</p>'
        for pivot_line in pivot_lines[:2]
    )
    if pivot_items:
        pivot_content += visual_list(pivot_items[:5], "next-list")
    if not pivot_content:
        pivot_content = '<p>换成更窄、更可验证的方向。</p>'
    return f"""
    <div class="stop-rule-flow">
      <section class="stop-rule-block stop-rule-signal">
        <b><span>1</span>停止信号</b>
        {visual_list(trigger_bullets[:5], "next-list")}
      </section>
      <section class="stop-rule-block stop-rule-action">
        <b><span>2</span>立即动作</b>
        <p>{inline_markdown("；".join(stop_actions[:2]))}</p>
      </section>
      <section class="stop-rule-block stop-rule-pivot">
        <b><span>3</span>转向方向</b>
        {pivot_content}
      </section>
    </div>
    """


def next_detail_html(title: str, content: str) -> str:
    if "停止" in title or "规则" in title:
        specialized = stop_rule_html(content)
        if specialized:
            return specialized
    return compact_detail_html(content, "next-list")


def module_intro_card(markdown: str, class_name: str = "module-intro") -> str:
    if not markdown.strip():
        return ""
    return f'<article class="{class_name}"><p>{inline_markdown(plain_text(markdown))}</p></article>'


def action_block_items(body: str, limit: int = 3) -> List[str]:
    paragraphs, bullets, numbers = split_detail_parts(body)
    items = bullets or numbers or paragraphs
    return [clamp_text(item, 72) for item in items[:limit] if plain_text(item)]


def action_block_text(body: str, limit: int = 108) -> str:
    paragraphs, bullets, numbers = split_detail_parts(body)
    items = paragraphs or bullets or numbers
    return clamp_text(items[0], limit) if items else ""


def first_action_block(blocks: List[Tuple[str, str]], labels: set[str]) -> Tuple[str, str]:
    for label, body in blocks:
        if label in labels and plain_text(body):
            return label, body
    return "", ""


def action_block_full_html(label: str, body: str) -> str:
    paragraphs, bullets, numbers = split_detail_parts(body)
    content = []
    for paragraph in paragraphs[:3]:
        content.append(f'<p class="action-detail-copy">{inline_markdown(paragraph)}</p>')
    items = bullets or numbers
    if items:
        content.append(visual_list(items[:8], "note-list action-detail-list"))
    if not content:
        content.append(f'<p class="action-detail-copy">{inline_markdown(clamp_text(body, 160))}</p>')
    display_label = display_action_label(label)
    label_html = "" if display_label == "补充说明" else f"<b>{inline_markdown(display_label)}</b>"
    return f'<section class="action-detail-section">{label_html}{"".join(content)}</section>'


def build_action_full_detail(content: str) -> str:
    blocks = split_action_blocks(content)
    if blocks:
        return "".join(action_block_full_html(label, body) for label, body in blocks)
    return compact_detail_html(content, "action-detail-list")


def clean_action_title(title: str) -> str:
    return re.sub(r"^\d+[）).、]\s*", "", title).strip()


def build_action_detail(content: str) -> str:
    if not content.strip():
        return '<p class="action-summary">先做小范围验证。</p>'
    blocks = split_action_blocks(content)
    if blocks and not (len(blocks) == 1 and blocks[0][0] == "补充说明"):
        _reason_label, reason_body = first_action_block(blocks, ACTION_REASON_LABELS)
        _scope_label, scope_body = first_action_block(blocks, ACTION_SCOPE_LABELS)
        _verdict_label, verdict_body = first_action_block(blocks, ACTION_VERDICT_LABELS)
        summary = action_block_text(reason_body or blocks[0][1], 112)
        items = action_block_items(scope_body, 3) or action_block_items(reason_body, 3)
        verdict = action_block_text(verdict_body, 96)
    else:
        paragraphs, bullets, numbers = split_detail_parts(content)
        summary = clamp_text(paragraphs[0], 112) if paragraphs else ""
        items = [clamp_text(item, 72) for item in (bullets or numbers)[:3]]
        verdict = ""
    rendered = []
    if summary:
        rendered.append(f'<p class="action-summary">{inline_markdown(summary)}</p>')
    if items:
        rendered.append(visual_list(items, "note-list action-brief-list"))
    if verdict:
        rendered.append(f'<div class="action-verdict">{inline_markdown(verdict)}</div>')
    return "".join(rendered) or '<p class="action-summary">先做小范围验证。</p>'


def build_top_action_cards(title: str, content: str, start_index: int = 1) -> str:
    action_items = split_h4_sections(content)
    if not action_items:
        return ""
    cards = []
    for offset, (item_title, item_content) in enumerate(action_items[:5]):
        index = start_index + offset
        rotate = ((index - 1) % 3) + 1
        cards.append(
            f"""
            <article class="sticky-note rotate-{rotate}">
              <div class="note-index">{index}</div>
              <h3>{inline_markdown(clean_action_title(item_title))}</h3>
              <div class="note-body">{build_action_full_detail(item_content)}</div>
            </article>
            """
        )
    return "".join(cards)


def build_action_followup(title: str, content: str) -> str:
    return f"""
    <section class="action-followup">
      <h3>{inline_markdown(title)}</h3>
      <div class="note-body">{build_action_full_detail(content)}</div>
    </section>
    """


def is_action_followup_title(title: str, index: int) -> bool:
    return index > 1 and ("淘汰" in title or "切法" in title or "建议" in title or "排序" in title)


def header_has_any(header: List[str], names: Tuple[str, ...]) -> bool:
    return any(name in header for name in names)


def candidate_pool_table_data(markdown: str) -> Tuple[List[str], List[List[str]]]:
    direction_names = ("候选方向", "方向", "候选产品", "产品方向", "候选行动")
    signal_names = (
        "代表产品/工具站",
        "代表产品",
        "工具站",
        "用户任务",
        "付费信号",
        "SEO 入口",
        "SEO入口",
        "SEO/分发入口",
        "竞品密度",
        "竞品/风险",
        "MVP 难度",
        "MVP难度",
        "MVP/成本",
    )
    verdict_names = ("建议", "判断", "结论")
    for header, rows in iter_table_blocks(markdown):
        if not header_has_any(header, direction_names):
            continue
        if not header_has_any(header, signal_names):
            continue
        if not header_has_any(header, verdict_names):
            continue
        return header, rows[:15]
    return [], []


def candidate_pool_table_records(markdown: str) -> List[Dict[str, str]]:
    header, rows = candidate_pool_table_data(markdown)
    if not header or not rows:
        return []
    records = []
    for row in rows:
        cells = row + [""] * max(0, len(header) - len(row))
        records.append(dict(zip(header, cells)))
    return records[:15]


def display_candidate_pool_table(header: List[str], rows: List[List[str]]) -> Tuple[List[str], List[List[str]]]:
    hidden_columns = {
        "行动分组",
        "SEO 入口",
        "SEO入口",
        "SEO/分发入口",
        "SEO/页面化入口",
        "建议",
    }
    kept_indexes = [index for index, column in enumerate(header) if column.strip() not in hidden_columns]
    display_header = [header[index] for index in kept_indexes]
    display_rows = [
        [row[index] if index < len(row) else "" for index in kept_indexes]
        for row in rows
    ]
    return display_header, display_rows


def build_candidate_pool_board(actions_markdown: str) -> str:
    header, rows = candidate_pool_table_data(actions_markdown)
    if not header or not rows:
        return ""
    display_header, display_rows = display_candidate_pool_table(header, rows)
    table_html = render_parsed_table(display_header, display_rows, "candidate-pool-table")
    return f"""
    <section class="candidate-pool-board">
      <div class="candidate-pool-head">
        <h3>候选产品拆解表</h3>
      </div>
      {table_html}
    </section>
    """


def is_candidate_pool_table_section(title: str, content: str) -> bool:
    haystack = f"{title} {content[:240]}"
    return bool(candidate_pool_table_records(content)) and (
        "候选" in haystack or "对比" in haystack or "拆解表" in haystack
    )


def build_action_module(title: str, content: str, index: int) -> str:
    if "Top" in title and split_h4_sections(content):
        return build_top_action_cards(title, content, index)
    if is_action_followup_title(title, index):
        return build_action_followup(title, content)
    detail = build_action_full_detail(content)
    rotate = ((index - 1) % 3) + 1
    return f"""
    <article class="sticky-note rotate-{rotate}">
      <div class="note-index">{index}</div>
      <h3>{inline_markdown(title)}</h3>
      <div class="note-body">{detail}</div>
    </article>
    """


def build_action_notes(actions_markdown: str, next_markdown: str) -> str:
    action_sections = split_h3_sections(actions_markdown)
    if not action_sections:
        action_sections = [(item, "") for item in (extract_numbered_items(actions_markdown, 3) or extract_numbered_items(next_markdown, 3))]
    candidate_board = build_candidate_pool_board(actions_markdown)
    modules = []
    followups = []
    next_index = 1
    for title, content in action_sections:
        if is_removed_user_module_title(title):
            continue
        if is_candidate_pool_table_section(title, content):
            continue
        if len(modules) >= 4:
            break
        top_items = split_h4_sections(content) if "Top" in title else []
        if is_action_followup_title(title, next_index):
            followups.append(build_action_followup(title, content))
            continue
        modules.append(build_action_module(title, content, next_index))
        next_index += len(top_items[:5]) if top_items else 1
    if followups:
        divider_attr = ' data-has-divider="true"' if len(followups) > 1 else ""
        modules.append(f'<div class="action-followup-pair"{divider_attr}>{"".join(followups)}</div>')
    return "".join(modules) + candidate_board


def score_number(value: str) -> int:
    text = plain_text(value)
    hundred_match = re.search(r"\b(100|[1-9]?\d)\s*(?:/|／)\s*100\b", text)
    if hundred_match:
        return max(0, min(100, int(hundred_match.group(1))))
    percent_match = re.search(r"\b(100|[1-9]?\d)\s*%", text)
    if percent_match:
        return max(0, min(100, int(percent_match.group(1))))
    five_match = re.search(r"\b([0-5])\s*(?:/|／)\s*5\b", text)
    if five_match:
        return max(0, min(100, int(five_match.group(1)) * 20))
    match = re.search(r"\b(100|[1-9]?\d)\b", text)
    if match:
        value_number = int(match.group(1))
        if value_number <= 5:
            value_number *= 20
        return max(0, min(100, value_number))
    rank = strength_rank(text)
    return {4: 90, 3: 75, 2: 55, 1: 20}.get(rank, 0)


def score_icon_svg(label: str) -> str:
    if label == "价值":
        points = "10 2.3 12 7.2 17.4 7.6 13.3 11.1 14.7 16.4 10 13.6 5.3 16.4 6.7 11.1 2.6 7.6 8 7.2"
    else:
        points = "10 2.5 17.5 10 10 17.5 2.5 10"
    return (
        '<svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">'
        f'<polygon points="{points}" />'
        "</svg>"
    )


def score_chip(label: str, value: str) -> str:
    score = score_number(value)
    display = str(score) if score else inline_markdown(value or "待评")
    icon_svg = score_icon_svg(label)
    return f"""
    <div class="evidence-score">
      <span class="score-icon">{icon_svg}</span>
      <span class="score-label">{html.escape(label)}</span>
      <b>{display}</b>
    </div>
    """


def evidence_score_panel(record: Dict[str, str]) -> str:
    score_fields = [
        ("质量", record.get("证据质量", "")),
        ("价值", record.get("VOI", "")),
    ]
    if not any(value for _, value in score_fields):
        return ""
    return f'<div class="evidence-score-grid">{"".join(score_chip(label, value) for label, value in score_fields)}</div>'


EVIDENCE_CARD_COLUMNS = ["行动影响", "证据方向", "发现了什么", "怎么改变决策", "来源"]


def is_evidence_card_table(header: List[str]) -> bool:
    return all(column in header for column in EVIDENCE_CARD_COLUMNS)


def evidence_records_from_table(header: List[str], rows: List[List[str]]) -> List[Dict[str, str]]:
    if not is_evidence_card_table(header):
        return []
    records = []
    for row in rows:
        cells = row + [""] * max(0, len(header) - len(row))
        records.append(dict(zip(header, cells)))
    return records


def evidence_cards_from_records(records: List[Dict[str, str]], limit: int = 8, preserve_order: bool = False) -> str:
    cards = []
    sorted_records = records if preserve_order else sorted(records, key=lambda record: strength_rank(record.get("行动影响", "")), reverse=True)
    for record in sorted_records[:limit]:
        impact = record.get("行动影响", "")
        lane = record.get("证据方向", "")
        finding = record.get("发现了什么", "")
        action = record.get("怎么改变决策", "")
        source = record.get("来源", "")
        impact_class = strength_class(impact)
        score_panel = evidence_score_panel(record)
        cards.append(
            f"""
            <article class="evidence-card">
              <div class="evidence-head">
                <span class="impact {impact_class}">{inline_markdown(impact or "证据")}</span>
                <strong>{inline_markdown(lane or "证据方向")}</strong>
              </div>
              <p>{inline_markdown(clamp_text(finding, 118))}</p>
              <div class="decision-shift">{inline_markdown(clamp_text(action, 92))}</div>
              <div class="source-line">{inline_markdown(source)}</div>
              {score_panel}
            </article>
            """
        )
    return "".join(cards)


def evidence_cards_from_table(header: List[str], rows: List[List[str]], limit: int = 8) -> str:
    return evidence_cards_from_records(evidence_records_from_table(header, rows), limit=limit)


def evidence_module_title(title: str) -> str:
    compact = re.sub(r"\s+", "", title)
    if "候选池" in compact or "产品路径" in compact or "竞品池" in compact:
        return "候选池"
    if "商业模式" in compact or "定价" in compact or "成本" in compact:
        return "商业模式"
    if "用户反馈" in compact or "用户痛点" in compact or "痛点" in compact or "抱怨" in compact:
        return "用户痛点"
    return title.strip() or "证据模块"


def build_evidence_module(title: str, records: List[Dict[str, str]]) -> str:
    if not records:
        return ""
    return f"""
    <section class="evidence-module">
      <h3>{inline_markdown(evidence_module_title(title))}</h3>
      <div class="evidence-grid">{evidence_cards_from_records(records, limit=3, preserve_order=True)}</div>
    </section>
    """


def build_evidence_cards(evidence_markdown: str) -> str:
    intro, sections = split_h3_sections_with_intro(evidence_markdown)
    if intro.strip():
        header, rows = parse_first_table(intro)
        if header and rows and is_evidence_card_table(header):
            return f'<div class="evidence-grid">{evidence_cards_from_table(header, rows)}</div>'
    elif not sections:
        header, rows = parse_first_table(evidence_markdown)
        if header and rows and is_evidence_card_table(header):
            return f'<div class="evidence-grid">{evidence_cards_from_table(header, rows)}</div>'

    modules: List[str] = []
    records: List[Dict[str, str]] = []
    for title, content in sections:
        section_header, section_rows = parse_first_table(content)
        if not section_header or not section_rows:
            continue
        section_records = evidence_records_from_table(section_header, section_rows)
        if not section_records:
            continue
        modules.append(build_evidence_module(title, section_records))
        records.extend(section_records)
    if modules:
        return f'<div class="evidence-module-stack">{"".join(modules)}</div>'
    if records:
        return f'<div class="evidence-grid">{evidence_cards_from_records(records, limit=8)}</div>'
    return markdown_to_html(evidence_markdown)


def table_module_html(title: str, header: List[str], rows: List[List[str]], table_class: str = "", show_title: bool = True) -> str:
    if not header or not rows:
        return ""
    title_html = f"<h3>{inline_markdown(title)}</h3>" if show_title else ""
    return f"""
    <article class="table-module">
      {title_html}
      {render_parsed_table(header, rows, table_class)}
    </article>
    """


def h3_table_sections(markdown: str) -> List[Tuple[str, List[str], List[List[str]]]]:
    _intro, sections = split_h3_sections_with_intro(markdown)
    tables: List[Tuple[str, List[str], List[List[str]]]] = []
    for title, content in sections:
        header, rows = parse_first_table(content)
        if header and rows:
            tables.append((title, header, rows))
    return tables


def is_comparison_table(title: str, header: List[str]) -> bool:
    haystack = f"{title} {' '.join(header)}"
    return "候选方向" in haystack


def build_comparison_screen(question_markdown: str) -> str:
    modules = []
    for title, header, rows in h3_table_sections(question_markdown):
        if is_comparison_table(title, header):
            modules.append(table_module_html(title, header, rows, "comparison-table"))
    if not modules:
        return ""
    return f"""
    <section id="comparison-screen" class="screen">
      <article class="sketch-board table-board">
        <div class="section-label"><span>表</span><b>候选对比</b></div>
        <h2>方向、门槛和投入要放在一张表里看。</h2>
        <div class="table-module-stack">{"".join(modules)}</div>
      </article>
    </section>
    """


def build_social_signal_screen(evidence_markdown: str) -> str:
    # Social-platform rows are already represented in the user-pain evidence cards.
    return ""


def build_gap_cards(gaps_markdown: str) -> str:
    intro, gap_sections = split_h3_sections_with_intro(gaps_markdown)
    if not gap_sections:
        intro, gap_sections = split_numbered_blocks_with_intro(gaps_markdown)
    if not gap_sections:
        bullets = extract_bullet_items(gaps_markdown, 4)
        gap_sections = [(item, "") for item in bullets]
        if not gap_sections:
            gap_sections = [("缺失证据", gaps_markdown)]
    cards = [module_intro_card(intro)]
    for index, (title, content) in enumerate(gap_sections[:4], start=1):
        detail = compact_detail_html(content, "gap-list")
        cards.append(
            f"""
            <article class="gap-card">
              <div class="question-mark">{index}</div>
              <h3>{inline_markdown(re.sub(r'^\\d+[.)、]\\s*', '', title))}</h3>
              {detail}
            </article>
            """
        )
    return "".join(cards)


def build_next_cards(next_markdown: str) -> str:
    intro, next_sections = split_h3_sections_with_intro(next_markdown)
    if not next_sections:
        intro, next_sections = split_numbered_blocks_with_intro(next_markdown)
    if not next_sections:
        next_sections = [(item, "") for item in extract_numbered_items(next_markdown, 4)]
    cards = [module_intro_card(intro)]
    visible_next_sections = [
        (title, content)
        for title, content in next_sections
        if not is_removed_user_module_title(title)
    ]
    for index, (title, content) in enumerate(visible_next_sections[:6], start=1):
        header, rows = parse_first_table(content)
        if header and rows:
            cards.append(
                f"""
                <article class="table-module next-table-module">
                  <h3>{inline_markdown(title)}</h3>
                  {render_parsed_table(header, rows, "next-action-table")}
                </article>
                """
            )
            continue
        detail = next_detail_html(title, content)
        cards.append(
            f"""
            <article class="step-card">
              <span>{index}</span>
              <h3>{inline_markdown(title)}</h3>
              {detail}
            </article>
            """
        )
    return "".join(cards)


def build_expert_panel(expert_markdown: str) -> str:
    if not expert_markdown.strip():
        return "<p>本轮没有足够明确的专家判断，需要继续补证。</p>"
    header, rows = parse_first_table(expert_markdown)
    if header and rows and "领域专家" in header[0]:
        cards = []
        sorted_rows = sort_rows_by_strength(header, rows, "可信度", max(0, len(header) - 1))
        for row in sorted_rows[:4]:
            cells = row + [""] * max(0, len(header) - len(row))
            record = dict(zip(header, cells))
            expert_name = record.get("领域专家", cells[0] if cells else "专家信号")
            signal = record.get("专家/实践者信号", "")
            why = record.get("为什么选", "")
            focus = record.get("他们关注的问题", "")
            solution = record.get("当前解法", "")
            insight = record.get("对我们的启发", "")
            confidence = record.get("可信度", "")
            channel = record.get("来自渠道", "")
            cards.append(
                f"""
                <article class="expert-card">
                  <div class="expert-head">
                    <h3>{inline_markdown(expert_name)}</h3>
                    <span class="expert-confidence {strength_class(confidence)}">{inline_markdown(confidence or "待验证")}</span>
                  </div>
                  <p>{inline_markdown(signal)}</p>
                  <div class="expert-meta">
                    <b>为什么选</b><p>{inline_markdown(why)}</p>
                    <b>关注问题</b><p>{inline_markdown(focus)}</p>
                    <b>当前解法</b><p>{inline_markdown(solution)}</p>
                  </div>
                  <div class="expert-insight">{inline_markdown(insight)}</div>
                  <div class="source-line">{inline_markdown(channel)}</div>
                </article>
                """
            )
        return f"<div class=\"expert-grid\">{''.join(cards)}</div>"
    return markdown_to_html(expert_markdown)


def read_personal_profile_markdown() -> str:
    explicit_profile = os.environ.get("INFO_ALCHEMIST_PERSONAL_PROFILE_FILE", "").strip()
    candidates = [default_profile_path()]
    if not explicit_profile:
        legacy_path = skill_dir() / "memory" / "personal_voi_profile.md"
        if legacy_path not in candidates:
            candidates.append(legacy_path)
    for path in candidates:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    return ""


def profile_meta_items(profile_intro: str) -> List[Tuple[str, str]]:
    items: List[Tuple[str, str]] = []
    for raw_line in profile_intro.splitlines():
        stripped = raw_line.strip()
        match = re.match(r"^([^：:]{2,16})[：:]\s*(.+)$", stripped)
        if match:
            items.append((match.group(1).strip(), match.group(2).strip()))
    return items


PROFILE_LABELS = {
    "最后更新": "最近更新",
    "最近更新": "最近更新",
    "累计记录": "已记录决策",
    "已记录决策": "已记录决策",
    "当前可信度": "画像成熟度",
    "画像成熟度": "画像成熟度",
    "说明": "画像说明",
    "画像说明": "画像说明",
}

CONFIDENCE_COPY = {
    "低": "样本少",
    "中": "初步可参考",
    "高": "比较稳定",
}

PROFILE_NOTE_COPY = {
    "当前只记录线索，不生成稳定偏差判断。": "目前只记录了少量决策，先当作参考，不当作定论。",
    "已出现重复线索，但仍需用户确认后再升级为稳定模式。": "已经出现重复倾向，但还需要更多决策记录确认。",
    "已积累多次记录，可生成候选护栏，但仍需继续用新证据校正。": "已经能看出一些习惯，后续仍要用新记录校正。",
    "已积累多次记录，可生成下次询证提醒，但仍需继续用新证据校正。": "已经能看出一些习惯，后续仍要用新记录校正。",
    "当前还没有足够记录生成稳定判断。": "记录还不够，先从下一次决策开始积累。",
}


def readable_profile_label(label: str) -> str:
    return PROFILE_LABELS.get(label, label)


def readable_profile_value(label: str, value: str) -> str:
    cleaned = value.strip()
    if label in {"当前可信度", "画像成熟度"}:
        return CONFIDENCE_COPY.get(cleaned, cleaned or "样本少")
    if label in {"说明", "画像说明"}:
        return PROFILE_NOTE_COPY.get(cleaned, cleaned)
    return cleaned


def section_markdown(sections: Dict[str, str], *names: str) -> str:
    for name in names:
        value = sections.get(name, "")
        if value:
            return value
    return ""


def readable_trigger(value: str) -> str:
    cleaned = value.strip()
    if cleaned in {"其他", "other"}:
        return "想判断下一步怎么做"
    if cleaned == "想了解最新变化":
        return "想看最新变化会不会影响行动"
    return cleaned or "想判断下一步怎么做"


def readable_pattern_judgment(value: str) -> str:
    cleaned = value.strip()
    mapping = {
        "暂不升级为稳定模式": "记录还少，先继续观察。",
        "出现重复线索，继续观察": "这个倾向出现过不止一次，继续观察。",
        "可作为候选稳定模式，仍需用户确认": "这个习惯已经重复出现，可以先当作参考。",
        "暂不生成判断": "记录还不够，暂时不下结论。",
    }
    return mapping.get(cleaned, cleaned or "继续观察。")


def readable_evidence_type(value: str) -> str:
    cleaned = value.strip()
    mapping = {
        "公开搜索": "公开资料 / 搜索",
        "亲自体验 / 录屏 / 截图": "自己试用 / 截图",
        "点击 / 留资 / 转化数据": "点击 / 留资 / 付费数据",
    }
    return mapping.get(cleaned, cleaned or "证据类型")


def readable_evidence_impact(value: str) -> str:
    cleaned = value.strip()
    mapping = {
        "适合形成初步判断，但不足以证明真实行动价值": "适合快速判断方向，但不能证明用户真的会买或用。",
        "适合筛候选对象，但不足以判断真实体验": "适合先筛选对象，但不能替代真实试用。",
        "能判断新用户路径是否顺畅": "能看出新用户会不会卡住。",
        "能判断是否值得继续投入": "最能判断这个方向值不值得继续投。",
    }
    return mapping.get(cleaned, cleaned or "待补充")


def readable_recent_date(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or cleaned == "待补充":
        return "还没记录到"
    return cleaned


def readable_guardrail_status(value: str) -> str:
    cleaned = value.strip()
    mapping = {
        "候选中": "先作为提醒",
        "暂不生成判断": "暂时不提醒",
    }
    return mapping.get(cleaned, cleaned or "先作为提醒")


def build_profile_summary(profile_intro: str) -> str:
    items = profile_meta_items(profile_intro)
    if not items:
        items = [
            ("最近更新", "待补充"),
            ("已记录决策", "0 条"),
            ("画像成熟度", "低"),
            ("画像说明", "当前还没有足够记录生成稳定判断。"),
        ]
    cards = []
    for label, value in items[:4]:
        display_label = readable_profile_label(label)
        display_value = readable_profile_value(label, value)
        cards.append(
            f"""
            <article class="profile-stat">
              <span>{inline_markdown(display_label)}</span>
              <strong>{inline_markdown(display_value)}</strong>
            </article>
            """
        )
    return "".join(cards)


def build_recent_decision_cards(markdown: str) -> str:
    records = table_records(markdown)
    if not records:
        return '<article class="profile-card"><h3>暂无决策记录</h3><p>等下一次记录决策后，这里会展示触发因素、转折证据和最终动作。</p></article>'
    cards = []
    for record in records[-6:]:
        date_text = record.get("日期", "待补充")
        scene = record.get("场景", "未命名场景")
        trigger = readable_trigger(record.get("触发因素", "待补充"))
        turning = record.get("决策转折", "待补充")
        final = record.get("最终动作", "待补充")
        cards.append(
            f"""
            <article class="profile-card decision-record">
              <div class="profile-card-head">
                <strong>{inline_markdown(scene)}</strong>
                <span>{inline_markdown(date_text)}</span>
              </div>
              <div class="decision-flow">
                <div class="decision-field">
                  <span class="field-label">想了解</span>
                  <p>{inline_markdown(clamp_text(trigger, 92))}</p>
                </div>
                <div class="turning-point"><strong>关键转折</strong>{inline_markdown(clamp_text(turning, 118))}</div>
                <div class="decision-field decision-final-field">
                  <span class="field-label">最后决定</span>
                  <div class="decision-final"><strong>{inline_markdown(final)}</strong></div>
                </div>
              </div>
            </article>
            """
        )
    return "".join(cards)


def build_pattern_cards(markdown: str) -> str:
    records = table_records(markdown)
    if not records:
        return '<article class="profile-card"><h3>暂无模式线索</h3><p>记录不足时不生成稳定偏差判断。</p></article>'
    cards = []
    for record in records[:4]:
        confidence_label = record.get("置信度", "低")
        confidence_text = CONFIDENCE_COPY.get(confidence_label.strip(), confidence_label)
        judgment = readable_pattern_judgment(record.get("当前判断", "继续观察"))
        cards.append(
            f"""
            <article class="profile-card pattern-card">
              <div class="profile-card-head">
                <strong>{inline_markdown(record.get("模式线索", "模式线索"))}</strong>
                <span class="profile-confidence {strength_class(confidence_label)}">{inline_markdown(confidence_text)}</span>
              </div>
              <p>{inline_markdown(judgment)}</p>
              <small>记录 {inline_markdown(record.get("出现次数", "0"))} 次 · 最近 {inline_markdown(readable_recent_date(record.get("最近出现", "待补充")))}</small>
            </article>
            """
        )
    return "".join(cards)


def build_evidence_type_cards(markdown: str) -> str:
    records = table_records(markdown)
    if not records:
        return '<article class="profile-card"><h3>证据类型待补充</h3><p>先记录哪些证据真的改变过行动。</p></article>'
    cards = []
    for record in records[:3]:
        cards.append(
            f"""
            <article class="profile-card evidence-type-card">
              <h3>{inline_markdown(readable_evidence_type(record.get("证据类型", "证据类型")))}</h3>
              <p>{inline_markdown(readable_evidence_impact(record.get("对行动的影响", "待补充")))}</p>
              <small>最近记录：{inline_markdown(readable_recent_date(record.get("最近出现", "待补充")))}</small>
            </article>
            """
        )
    return "".join(cards)


def build_profile_bullet_cards(markdown: str, empty_title: str) -> str:
    bullets = extract_bullet_items(markdown, 5)
    if not bullets:
        bullets = [plain_text(markdown)] if plain_text(markdown) else []
    if not bullets:
        return f'<article class="profile-card"><h3>{html.escape(empty_title)}</h3><p>待补充。</p></article>'
    return "".join(
        f"""
        <article class="profile-card insight-card">
          <span>{index}</span>
          <p>{inline_markdown(item)}</p>
        </article>
        """
        for index, item in enumerate(bullets[:5], start=1)
    )


def build_guardrail_cards(markdown: str) -> str:
    records = table_records(markdown)
    if not records:
        return build_profile_bullet_cards(markdown, "下次询证提醒")
    cards = []
    for record in records[:4]:
        cards.append(
            f"""
            <article class="profile-card guardrail-card">
              <h3>{inline_markdown(record.get("护栏建议", "护栏建议"))}</h3>
              <p><span class="field-label">什么时候提醒</span>{inline_markdown(record.get("触发条件", "待补充"))}</p>
              <small>{inline_markdown(readable_guardrail_status(record.get("状态", "候选中")))}</small>
            </article>
            """
        )
    return "".join(cards)


def build_profile_screen(profile_markdown: str, report_url: str = "#question-screen") -> str:
    if not profile_markdown.strip():
        profile_markdown = "# 个人决策画像\n\n最近更新：待补充\n已记录决策：0 条\n画像成熟度：低\n画像说明：还没有足够的决策记录。\n"
    intro, sections = split_any_markdown_sections(profile_markdown)
    return f"""
    <section id="profile-screen" class="screen profile-screen">
      <article class="sketch-board profile-board">
        <div class="profile-hero">
          <div>
            <h1>个人决策画像</h1>
            <p class="profile-subtitle">记录你被什么信息影响，哪些证据真的让你改变了行动。</p>
          </div>
        </div>
        <div class="profile-stats">{build_profile_summary(intro)}</div>
        <section class="profile-module">
          <div class="profile-module-title"><span>1</span><h3>近期决策记录</h3></div>
          <div class="profile-decision-grid">{build_recent_decision_cards(section_markdown(sections, "近期决策记录", "最近决策记录"))}</div>
        </section>
        <section class="profile-module">
          <div class="profile-module-title"><span>2</span><h3>惯性决策模式</h3></div>
          <div class="profile-grid">{build_pattern_cards(section_markdown(sections, "惯性决策模式", "决策模式线索"))}</div>
        </section>
        <section class="profile-module">
          <div class="profile-module-title"><span>3</span><h3>有效证据类型</h3></div>
          <div class="profile-grid three">{build_evidence_type_cards(section_markdown(sections, "有效证据类型"))}</div>
        </section>
        <section class="profile-module two-col">
          <div>
            <div class="profile-module-title"><span>4</span><h3>最近决策洞察</h3></div>
            <div class="profile-stack">{build_profile_bullet_cards(section_markdown(sections, "最近决策洞察", "最近洞察"), "最近决策洞察")}</div>
          </div>
          <div>
            <div class="profile-module-title"><span>5</span><h3>下次询证提醒</h3></div>
            <div class="profile-stack">{build_guardrail_cards(section_markdown(sections, "下次询证提醒", "候选护栏"))}</div>
          </div>
        </section>
      </article>
    </section>
    """


def int_count(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def format_int_count(value: Any) -> str:
    return f"{int_count(value):,}"


def parse_number_text(value: str) -> int:
    return int_count(re.sub(r"[^\d]", "", value or ""))


def token_direction_for_label(label: str) -> str:
    text = str(label or "")
    return "output" if "输出" in text or text.startswith("输出") else "input"


def token_usage_from_markdown(markdown: str) -> Dict[str, Any]:
    lines = markdown.splitlines()
    start = -1
    for index, line in enumerate(lines):
        if re.match(r"^##\s+Token 消耗估算\s*$", line.strip()):
            start = index + 1
            break
    if start < 0:
        return {}
    section_lines: List[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("## ") and not re.match(r"^##\s+Token 消耗估算\s*$", stripped):
            break
        if stripped:
            section_lines.append(stripped)
    if not section_lines:
        return {}
    total_tokens = 0
    method_label = "字符数 / 3 粗估"
    breakdown: List[Dict[str, Any]] = []
    excluded: List[str] = []
    note = ""
    for line in section_lines:
        cleaned = re.sub(r"^[-*]\s+", "", line).strip()
        total_match = re.search(r"合计[:：]\s*约\s*([\d,]+)\s*tokens", cleaned, re.I)
        if total_match:
            total_tokens = parse_number_text(total_match.group(1))
            continue
        method_match = re.search(r"估算方法[:：]\s*(.+)$", cleaned)
        if method_match:
            method_label = method_match.group(1).strip()
            continue
        split_match = re.search(r"拆分[:：]\s*输入约\s*([\d,]+)\s*tokens?[，,、\s]+输出约\s*([\d,]+)\s*tokens?", cleaned, re.I)
        if split_match:
            continue
        item_match = re.search(r"(?:(输入|输出)\s*[·:：]\s*)?([^：:]+)[:：]\s*([\d,]+)\s*字符，约\s*([\d,]+)\s*tokens", cleaned, re.I)
        if item_match:
            prefix = item_match.group(1)
            label = item_match.group(2).strip()
            breakdown.append({
                "label": label,
                "direction": "output" if prefix == "输出" else "input" if prefix == "输入" else token_direction_for_label(label),
                "chars": parse_number_text(item_match.group(3)),
                "tokens_est": parse_number_text(item_match.group(4)),
            })
            continue
        excluded_match = re.search(r"不计入[:：]\s*(.+)$", cleaned)
        if excluded_match:
            excluded.append(excluded_match.group(1).strip())
            continue
        note_match = re.search(r"说明[:：]\s*(.+)$", cleaned)
        if note_match:
            note = note_match.group(1).strip()
    if not total_tokens and not breakdown:
        return {}
    if not total_tokens:
        total_tokens = sum(int_count(item.get("tokens_est")) for item in breakdown)
    input_tokens = sum(int_count(item.get("tokens_est")) for item in breakdown if item.get("direction") == "input")
    output_tokens = sum(int_count(item.get("tokens_est")) for item in breakdown if item.get("direction") == "output")
    return {
        "method": "chars_div_3",
        "method_label": method_label,
        "is_estimate": True,
        "total_tokens_est": total_tokens,
        "input_tokens_est": input_tokens,
        "output_tokens_est": output_tokens,
        "breakdown": breakdown,
        "excluded": excluded,
        "note": note,
    }


def token_count_by_direction(token_usage: Dict[str, Any], direction: str) -> int:
    field = "input_tokens_est" if direction == "input" else "output_tokens_est"
    value = int_count(token_usage.get(field))
    if value:
        return value
    total = 0
    for item in token_usage.get("breakdown", []):
        if not isinstance(item, dict):
            continue
        item_direction = str(item.get("direction") or token_direction_for_label(str(item.get("label") or item.get("key") or "")))
        if item_direction == direction:
            total += int_count(item.get("tokens_est"))
    return total


def display_token_label(label: str, direction: str) -> str:
    text = str(label or "").strip()
    if direction == "output":
        text = re.sub(r"输出$", "", text).strip()
        if text == "最终报告":
            text = "炼金报告"
    return text or "环节"


def build_token_usage_html(token_usage: Optional[Dict[str, Any]]) -> str:
    if not token_usage:
        return ""
    total_tokens = format_int_count(token_usage.get("total_tokens_est"))
    input_tokens = format_int_count(token_count_by_direction(token_usage, "input"))
    output_tokens = format_int_count(token_count_by_direction(token_usage, "output"))
    input_chips: List[str] = []
    output_chips: List[str] = []
    for item in token_usage.get("breakdown", []):
        if not isinstance(item, dict):
            continue
        direction = str(item.get("direction") or token_direction_for_label(str(item.get("label") or item.get("key") or "")))
        label = html.escape(display_token_label(str(item.get("label") or item.get("key") or "环节"), direction))
        tokens = format_int_count(item.get("tokens_est"))
        unavailable = item.get("available", True) is False
        state = " token-chip-muted" if unavailable else ""
        suffix = " · 未计入" if unavailable else ""
        chip = f'<span class="token-chip{state}"><b>{label}</b> 约 {tokens} tokens{suffix}</span>'
        if direction == "output":
            output_chips.append(chip)
        else:
            input_chips.append(chip)
    rows = "".join([
        f'<span class="token-breakdown-row"><span class="token-breakdown-label">输入：</span><span class="token-chip-group">{"".join(input_chips)}</span></span>' if input_chips else "",
        f'<span class="token-breakdown-row"><span class="token-breakdown-label">输出：</span><span class="token-chip-group">{"".join(output_chips)}</span></span>' if output_chips else "",
    ])
    return f"""
    <section id="token-screen" class="token-meter" aria-label="Token 消耗估算">
      <div class="token-card">
        <div class="token-summary-line">
          <span class="token-info" tabindex="0" aria-label="查看 Token 明细">i<span class="token-tooltip" role="tooltip">{rows}</span></span>
          <strong class="token-summary"><span>Token 总消耗：</span>约 {total_tokens} tokens · 输入约 {input_tokens} · 输出约 {output_tokens}</strong>
        </div>
      </div>
    </section>
    """


def build_marker_html(
    html_url: str,
    report_title: str,
    report_mode_label: str,
    question_summary: str,
    question_cards: str,
    core_quote: str,
    core_cards: str,
    comparison_html: str,
    economics_html: str,
    expert_html: str,
    action_notes: str,
    evidence_cards: str,
    social_html: str,
    gap_cards: str,
    next_cards: str,
    profile_url: str,
    token_usage: Optional[Dict[str, Any]] = None,
) -> str:
    escaped_profile_url = html.escape(profile_url, quote=True)
    token_usage_html = build_token_usage_html(token_usage)
    comparison_nav = '<a class="pill" href="#comparison-screen">对比</a>' if comparison_html else ""
    economics_nav = '<a class="pill" href="#economics-screen">成本</a>' if economics_html else ""
    social_nav = '<a class="pill" href="#social-screen">社交</a>' if social_html else ""
    hero_title = report_title.removeprefix("信息炼金报告-") or "信息炼金报告"
    action_card_count = action_notes.count('class="sticky-note')
    notes_grid_class = "notes-grid"
    if action_card_count == 4:
        notes_grid_class += " notes-grid-four"
    elif action_card_count == 3:
        notes_grid_class += " notes-grid-three"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(report_title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --paper: #fffdf7;
      --ink: #111;
      --muted: #595961;
      --line: #171717;
      --gold: #d0a02c;
      --gold-2: #f6d45f;
      --gold-soft: #fff1a8;
      --note: #fff8d6;
      --note-2: #fffced;
      --note-border: #d8bd60;
      --note-rule: rgba(126, 110, 63, .24);
      --note-shadow: rgba(17, 17, 17, .055);
      --link: #65480a;
      --shadow: rgba(17, 17, 17, .14);
      --font: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: radial-gradient(circle at 12px 12px, rgba(208,160,44,.055) 1px, transparent 1px), var(--paper);
      background-size: 24px 24px;
      font-family: var(--font);
      letter-spacing: 0;
      overflow-x: hidden;
    }}
    a {{ color: inherit; text-decoration: none; }}
    main a {{
      color: var(--link);
      text-decoration-line: underline;
      text-decoration-color: var(--gold);
      text-decoration-thickness: 2px;
      text-underline-offset: 3px;
    }}
    main a:hover,
    main a:focus {{
      color: #111;
    }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 10;
      height: 72px;
      display: grid;
      grid-template-columns: minmax(210px, 1fr) auto minmax(210px, 1fr);
      align-items: center;
      gap: 18px;
      padding: 0 30px;
      border-bottom: 3px solid var(--line);
      background: rgba(255,253,247,.94);
      backdrop-filter: blur(18px);
    }}
    .brand {{ display: flex; align-items: center; gap: 12px; min-width: 0; }}
    .mark {{
      width: 38px;
      height: 38px;
      border: 3px solid #111;
      border-radius: 11px 13px 10px 12px;
      background: #111;
      box-shadow: inset 0 0 0 4px #fff;
      position: relative;
      flex: 0 0 auto;
    }}
    .mark::after {{
      content: "";
      position: absolute;
      right: 8px;
      bottom: 8px;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--gold);
    }}
    .brand strong {{ display: block; font-size: 18px; line-height: 1.05; }}
    .brand span {{ display: block; margin-top: 4px; color: var(--muted); font-size: 12px; font-weight: 680; }}
    .nav-pills {{
      justify-self: center;
      display: flex;
      align-items: center;
      gap: 8px;
      max-width: min(58vw, 720px);
      overflow-x: auto;
      padding: 0;
    }}
    .pill {{
      border: 2px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      background: #fff;
      font-size: 12px;
      font-weight: 850;
      white-space: nowrap;
      box-shadow: 2px 2px 0 var(--gold);
    }}
    .topbar-actions {{
      justify-self: end;
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }}
    .profile-entry,
    .topbar-return {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border: 2px solid var(--line);
      border-radius: 999px;
      background: var(--gold-soft);
      padding: 8px 9px 8px 13px;
      color: #111;
      font-size: 13px;
      line-height: 1;
      font-weight: 900;
      white-space: nowrap;
      box-shadow: 3px 3px 0 #111;
      box-sizing: border-box;
    }}
    .jump-arrow {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: #111;
      color: #fff;
      font-family: Arial, Helvetica, sans-serif;
      font-size: 12px;
      line-height: 1;
      font-weight: 900;
      align-self: center;
      transform: none;
      flex: 0 0 auto;
    }}
    .wrap {{ width: min(1180px, calc(100vw - 34px)); margin: 0 auto; padding: 18px 0 46px; }}
    .screen {{
      min-height: calc(100vh - 88px);
      display: grid;
      align-content: center;
      padding: 18px 0;
      scroll-margin-top: 84px;
    }}
    .sketch-board {{
      position: relative;
      border: 3px solid var(--line);
      border-radius: 22px 18px 24px 17px;
      background: rgba(255,255,255,.92);
      box-shadow: 7px 7px 0 rgba(208,160,44,.22), 0 18px 54px var(--shadow);
      padding: clamp(18px, 3vw, 34px);
      overflow: hidden;
    }}
    .sketch-board::after {{
      content: "";
      position: absolute;
      right: 18px;
      bottom: 14px;
      width: 62px;
      height: 16px;
      border-bottom: 3px solid rgba(17,17,17,.18);
      transform: rotate(-9deg);
    }}
    .section-label {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
      font-size: 13px;
      font-weight: 900;
    }}
    .section-label span:first-child {{
      display: grid;
      place-items: center;
      width: 26px;
      height: 26px;
      border-radius: 50%;
      color: #fff;
      background: var(--gold);
      border: 2px solid var(--line);
      box-shadow: 2px 2px 0 #111;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(54px, 7vw, 92px);
      line-height: .98;
      letter-spacing: 0;
    }}
    h2 {{ margin: 0 0 14px; font-size: clamp(30px, 4vw, 48px); line-height: 1.05; }}
    h3 {{ margin: 0; font-size: 21px; line-height: 1.22; }}
    p {{ color: #2f2f35; font-size: 16px; line-height: 1.62; }}
    strong {{ color: #000; }}
    .marker {{ background: linear-gradient(transparent 58%, rgba(246,212,95,.78) 0); padding: 0 .1em; }}
    .question-card {{
      border: 3px solid var(--line);
      border-radius: 12px 18px 13px 16px;
      padding: clamp(18px, 4vw, 34px);
      background: #fff;
      box-shadow: 4px 4px 0 rgba(17,17,17,.08);
    }}
    .question-lead {{
      max-width: 900px;
      margin: 16px 0 0;
      font-size: clamp(22px, 3vw, 36px);
      line-height: 1.28;
      font-weight: 900;
    }}
    .question-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 20px; }}
    .question-item {{
      display: grid;
      grid-template-columns: 34px 1fr;
      gap: 12px;
      align-items: start;
      border: 2px solid var(--line);
      border-radius: 14px 12px 16px 13px;
      padding: 13px 14px;
      background: #fffdf2;
    }}
    .question-item span, .core-card span {{
      display: grid;
      place-items: center;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      color: #fff;
      background: var(--gold);
      border: 2px solid #111;
      box-shadow: 2px 2px 0 #111;
      font-weight: 950;
    }}
    .question-item p {{
      margin: 0;
      color: #202026;
      font-size: 16px;
      line-height: 1.5;
      font-weight: 820;
    }}
    .core-quote {{
      max-width: 1080px;
      margin: 2px 0 16px;
      padding: 12px 14px;
      border-left: 5px solid var(--gold);
      border-radius: 0 14px 14px 0;
      background: #fffdf2;
      color: #303038;
      font-size: clamp(18px, 2vw, 27px);
      line-height: 1.35;
      font-weight: 820;
    }}
    .core-grid {{
      position: relative;
      display: grid;
      gap: 12px;
      margin-top: 18px;
      padding-left: 10px;
    }}
    .core-grid::before {{
      content: "";
      position: absolute;
      left: 26px;
      top: 18px;
      bottom: 18px;
      width: 3px;
      border-radius: 999px;
      background: linear-gradient(180deg, var(--gold), rgba(208,160,44,.18));
    }}
    .core-card {{
      position: relative;
      display: grid;
      grid-template-columns: 42px 1fr;
      gap: 14px;
      align-items: start;
      border: 2px solid #111;
      border-radius: 14px 18px 13px 16px;
      background: #fff;
      padding: 14px 16px 14px 14px;
      box-shadow: 4px 4px 0 rgba(208,160,44,.18);
    }}
    .core-card span {{ position: relative; z-index: 1; margin-top: 2px; }}
    .core-card p {{
      margin: 0;
      color: #2f2f35;
      font-size: 16px;
      line-height: 1.58;
      font-weight: 760;
    }}
    .economics-board {{
      background:
        linear-gradient(135deg, rgba(208,160,44,.12), transparent 38%),
        #fffdf7;
    }}
    .economics-hero {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 12px;
      align-items: start;
      border-bottom: 3px solid rgba(17,17,17,.12);
      padding-bottom: 16px;
      margin-bottom: 16px;
    }}
    .economics-hero h2 {{
      margin: 0;
      color: #111;
      font-size: clamp(28px, 4.2vw, 58px);
      line-height: .98;
      font-weight: 1000;
    }}
    .economics-hero p {{
      margin: 0;
      color: #2c2c31;
      max-width: 980px;
      font-size: 15px;
      line-height: 1.52;
      font-weight: 820;
    }}
    .economics-scenario-grid, .roi-action-grid, .finance-gate-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }}
    .economics-scenario-card, .roi-action-card, .finance-gate-card {{
      min-width: 0;
      border: 3px solid #111;
      border-radius: 16px;
      background: #fff;
      padding: 14px;
      box-shadow: 4px 4px 0 rgba(208,160,44,.32);
    }}
    .economics-scenario-card h3, .roi-action-card h3, .finance-gate-card h3 {{
      margin: 0 0 10px;
      color: #111;
      font-size: 16px;
      line-height: 1.2;
      font-weight: 950;
    }}
    .scenario-values, .roi-action-metrics, .gate-thresholds {{
      display: grid;
      gap: 7px;
    }}
    .scenario-values {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }}
    .roi-action-metrics, .gate-thresholds {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .scenario-values span, .roi-action-metrics span, .gate-thresholds span {{
      min-width: 0;
      border: 2px solid rgba(17,17,17,.76);
      border-radius: 10px;
      background: #fffdf2;
      padding: 7px 8px;
      color: #222;
      font-size: 12px;
      line-height: 1.28;
      font-weight: 780;
      overflow-wrap: anywhere;
    }}
    .scenario-values b, .roi-action-metrics b, .gate-thresholds b {{
      display: block;
      color: #6c5a24;
      font-size: 10px;
      line-height: 1;
      font-weight: 950;
      margin-bottom: 5px;
    }}
    .economics-scenario-card small, .roi-action-card small {{
      display: block;
      margin-top: 10px;
      color: #5d5d66;
      font-size: 12px;
      line-height: 1.35;
      font-weight: 760;
    }}
    .roi-action-card p, .finance-gate-card p {{
      margin: 10px 0 0;
      color: #24242a;
      font-size: 13px;
      line-height: 1.42;
      font-weight: 790;
    }}
    .roi-action-card p b {{
      display: inline-flex;
      margin-right: 6px;
      color: #6c5a24;
      font-size: 11px;
      font-weight: 950;
    }}
    .economics-submodule {{
      margin-top: 18px;
    }}
    .economics-submodule > h3 {{
      margin: 0 0 10px;
      color: #111;
      font-size: 20px;
      line-height: 1.15;
      font-weight: 980;
    }}
    .gate-test {{
      margin: 10px 0;
      border-left: 5px solid var(--gold);
      border-radius: 0 10px 10px 0;
      background: #fffdf2;
      padding: 8px 10px;
      color: #202026;
      font-size: 13px;
      line-height: 1.4;
      font-weight: 820;
    }}
    .gate-thresholds .pass {{ background: #f2fff5; }}
    .gate-thresholds .fail {{ background: #fff5f1; }}
    .check-list, .marker-list {{ margin: 20px 0 0; padding: 0; list-style: none; display: grid; gap: 10px; }}
    .check-list li, .marker-list li {{
      position: relative;
      padding-left: 28px;
      color: #2f2f35;
      font-size: 17px;
      line-height: 1.62;
      font-weight: 720;
    }}
    .check-list li::before, .marker-list li::before {{
      content: "";
      position: absolute;
      left: 0;
      top: .58em;
      width: 16px;
      height: 7px;
      border-left: 3px solid var(--gold);
      border-bottom: 3px solid var(--gold);
      transform: rotate(-45deg);
    }}
    .expert-board {{
      border: 3px solid #111;
      border-radius: 16px;
      background: #fff;
      padding: 16px;
      box-shadow: 5px 5px 0 rgba(208,160,44,.2);
    }}
    .expert-board p, .expert-board li {{ font-size: 14px; line-height: 1.48; }}
    .expert-board blockquote {{
      border-left: 6px solid var(--gold);
      background: #fff9d7;
      padding: 14px 18px;
      border-radius: 0 14px 14px 0;
      font-weight: 760;
    }}
    .expert-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .expert-card {{
      border: 2px solid #111;
      border-radius: 14px 18px 13px 16px;
      padding: 12px;
      background: #fff;
      box-shadow: 4px 4px 0 rgba(208,160,44,.16);
    }}
    .expert-card h3 {{ font-size: 18px; line-height: 1.2; }}
    .expert-card > p {{ margin: 8px 0 0; font-size: 13px; line-height: 1.38; }}
    .expert-head {{ display: flex; justify-content: space-between; gap: 14px; align-items: flex-start; }}
    .expert-head span {{
      flex: 0 0 auto;
      border: 2px solid #111;
      border-radius: 999px;
      padding: 3px 9px;
      font-size: 12px;
      font-weight: 900;
    }}
    .expert-confidence.level-high,
    .impact.level-high {{ background: #f6d45f; }}
    .expert-confidence.level-mid-high,
    .impact.level-mid-high {{ background: #ffe793; }}
    .expert-confidence.level-mid,
    .impact.level-mid {{ background: #fff1bd; }}
    .expert-confidence.level-low,
    .impact.level-low {{ background: #fff9df; color: #5b4612; }}
    .expert-confidence.level-unknown,
    .impact.level-unknown {{ background: #fff; color: #666; border-color: #777; }}
    .expert-meta {{
      display: grid;
      grid-template-columns: 66px 1fr;
      gap: 5px 9px;
      margin-top: 8px;
      padding-top: 8px;
      border-top: 2px dashed rgba(17,17,17,.2);
    }}
    .expert-meta b {{ color: #5b4612; font-size: 12px; }}
    .expert-meta p {{ margin: 0; font-size: 12px; line-height: 1.34; }}
    .expert-insight {{
      margin-top: 8px;
      padding: 8px;
      background: #fff9d7;
      border-radius: 12px;
      font-size: 12px;
      font-weight: 820;
      line-height: 1.34;
    }}
    .notes-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 12px; }}
    .notes-grid-three {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .notes-grid-four {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px 18px; }}
    .candidate-pool-board {{
      grid-column: 1 / -1;
      margin-top: 18px;
    }}
    .candidate-pool-head {{
      display: flex;
      justify-content: flex-start;
      align-items: center;
      gap: 12px;
      margin-bottom: 10px;
    }}
    .candidate-pool-head h3 {{ margin: 0; font-size: 19px; }}
    .candidate-pool-table {{ min-width: 1180px; }}
    .candidate-pool-table th:first-child,
    .candidate-pool-table td:first-child {{
      width: 48px;
      text-align: center;
      font-weight: 950;
    }}
    .sticky-note {{
      min-height: 0;
      border: 1.5px solid var(--note-border);
      background: linear-gradient(180deg, var(--note), var(--note-2));
      border-radius: 6px 10px 5px 8px;
      padding: 14px;
      box-shadow: 5px 7px 0 var(--note-shadow);
      position: relative;
    }}
    .rotate-1 {{ transform: rotate(-2deg); }}
    .rotate-2 {{ transform: rotate(1.5deg); }}
    .rotate-3 {{ transform: rotate(-1deg); }}
    .action-followup-pair {{
      grid-column: 1 / -1;
      position: relative;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 22px;
      margin-top: 10px;
      padding: 10px 4px 2px;
      background: transparent;
    }}
    .action-followup-pair[data-has-divider="true"]::before {{
      content: "";
      position: absolute;
      top: 4px;
      bottom: 4px;
      left: 50%;
      border-left: 2px dashed rgba(17,17,17,.28);
      transform: translateX(-1px);
    }}
    .action-followup {{
      min-width: 0;
      background: transparent;
    }}
    .action-followup + .action-followup {{
      padding-left: 4px;
    }}
    .action-followup h3 {{
      margin: 0 0 8px;
      color: #111;
      font-size: 18px;
      line-height: 1.18;
      font-weight: 980;
    }}
    .action-followup .note-body {{
      margin: 0;
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
    }}
    .action-followup .action-detail-section {{
      margin: 0;
      padding: 0;
      border-top: 0;
    }}
    .action-followup .action-detail-copy,
    .action-followup .note-list li {{
      font-size: 13px;
      line-height: 1.42;
    }}
    .note-index {{
      width: 24px;
      height: 24px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      background: var(--gold);
      border: 2px solid #2f2818;
      color: #fff;
      font-size: 13px;
      font-weight: 900;
      margin-bottom: 10px;
    }}
    .note-body {{ margin-top: 10px; }}
    .note-section, .note-verdict {{
      border: 2px solid rgba(17,17,17,.68);
      border-radius: 12px 10px 14px 11px;
      background: #fffef8;
      padding: 10px;
      margin: 0 0 9px;
    }}
    .note-section b, .note-verdict b {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border: 2px solid #111;
      border-radius: 999px;
      background: #fff;
      padding: 2px 8px;
      color: #5b4612;
      font-size: 12px;
      font-weight: 950;
    }}
    .action-point-list {{
      list-style: none;
      margin: 9px 0 0;
      padding: 0;
      display: grid;
      gap: 6px;
    }}
    .action-point-list li {{
      display: block;
    }}
    .action-point-list span {{
      display: inline-grid;
      place-items: center;
      width: 18px;
      height: 18px;
      margin-right: 7px;
      border-radius: 50%;
      background: var(--gold);
      color: #111;
      font-size: 11px;
      line-height: 1;
      font-weight: 950;
      text-indent: 0;
      vertical-align: .2em;
    }}
    .action-point-list p {{
      margin: 0;
      padding-left: 25px;
      text-indent: -25px;
      color: #1f1f24;
      font-size: 13px;
      line-height: 1.32;
      font-weight: 800;
    }}
    .note-verdict {{
      border-color: #111;
      background: #fffefa;
      box-shadow: 3px 3px 0 rgba(17,17,17,.1);
    }}
    .note-verdict p {{ margin: 10px 0 0; font-weight: 850; }}
    .note-body p, .note-body li {{ font-size: 15px; line-height: 1.56; }}
    .note-body h3 {{ margin-top: 14px; font-size: 18px; }}
    .note-body .action-point-list li {{ font-size: 13px; line-height: 1.32; }}
    .note-body .action-point-list p {{ font-size: 13px; line-height: 1.32; }}
    .action-summary {{
      margin: 0;
      color: #202026;
      font-size: 13px;
      line-height: 1.42;
      font-weight: 780;
    }}
    .action-brief-list {{
      margin-top: 8px;
      padding-left: 16px;
    }}
    .action-brief-list li {{
      margin: 4px 0;
      color: #2f2f35;
      font-size: 12px;
      line-height: 1.34;
      font-weight: 720;
    }}
    .action-verdict {{
      margin-top: 9px;
      padding: 8px 9px;
      border: 2px solid #111;
      border-radius: 11px;
      background: #fffef8;
      color: #111;
      font-size: 12px;
      line-height: 1.34;
      font-weight: 900;
    }}
    #actions-screen .sketch-board {{ padding: clamp(16px, 2.5vw, 28px); }}
    #actions-screen h2 {{ margin-bottom: 8px; font-size: clamp(28px, 3.2vw, 40px); }}
    #actions-screen .notes-grid {{ gap: 10px; margin-top: 10px; }}
    #actions-screen .sticky-note {{ padding: 12px; }}
    #actions-screen .sticky-note h3 {{ font-size: 16px; line-height: 1.18; margin-bottom: 8px; }}
    #actions-screen .note-index {{ width: 22px; height: 22px; font-size: 12px; margin-bottom: 8px; }}
    #actions-screen .note-body {{ margin-top: 7px; }}
    #actions-screen .note-body h3 {{ font-size: 14px; }}
    #actions-screen .note-body p,
    #actions-screen .note-body li {{ font-size: 12px; line-height: 1.34; }}
    #actions-screen .note-body p {{ margin: 6px 0; }}
    #actions-screen .note-body .action-summary {{ margin: 0; font-size: 12.5px; line-height: 1.34; }}
    #actions-screen .note-body .action-verdict {{ font-size: 11.5px; line-height: 1.28; }}
    #actions-screen .note-body ul {{ margin: 6px 0 0; padding-left: 17px; }}
    #actions-screen .note-section,
    #actions-screen .note-verdict {{ padding: 8px; margin-bottom: 7px; border-width: 1.8px; background: #fffef8; }}
    #actions-screen .note-section b,
    #actions-screen .note-verdict b {{ min-height: 20px; padding: 1px 7px; font-size: 11px; }}
    #actions-screen .action-point-list {{ gap: 4px; margin-top: 6px; }}
    #actions-screen .action-point-list span {{ width: 16px; height: 16px; margin-right: 6px; font-size: 10px; vertical-align: .2em; }}
    #actions-screen .action-point-list p,
    #actions-screen .note-body .action-point-list p {{ padding-left: 22px; text-indent: -22px; font-size: 11.5px; line-height: 1.24; }}
    .note-body hr {{ border: 0; border-top: 2px dashed var(--note-rule); margin: 14px 0; }}
    .note-list, .gap-list, .next-list {{ margin: 8px 0 0; padding-left: 18px; color: #333; }}
    .note-list li, .gap-list li, .next-list li {{ margin: 5px 0; font-size: 13px; line-height: 1.34; font-weight: 720; }}
    .action-detail-section {{
      margin-top: 10px;
      padding-top: 9px;
      border-top: 2px dashed var(--note-rule);
    }}
    .action-detail-section:first-child {{
      border-top: 0;
      padding-top: 0;
    }}
    .action-detail-section b {{
      display: inline-flex;
      color: #5b4612;
      font-size: 12px;
      line-height: 1.1;
      font-weight: 950;
    }}
    .action-detail-copy {{
      margin: 7px 0 0;
      color: #202026;
      font-size: 12px;
      line-height: 1.38;
      font-weight: 760;
    }}
    .action-detail-list li {{
      margin: 4px 0;
      font-size: 12px;
      line-height: 1.34;
      font-weight: 720;
    }}
    .table-board {{ align-content: start; }}
    .table-module-stack {{
      display: grid;
      gap: 16px;
      margin-top: 14px;
    }}
    .table-module {{
      min-width: 0;
      border: 2px solid #111;
      border-radius: 14px 18px 13px 16px;
      background: #fff;
      padding: 14px;
      box-shadow: 4px 4px 0 rgba(208,160,44,.18);
    }}
    .table-module h3 {{
      margin: 0 0 10px;
      color: #111;
      font-size: 18px;
      line-height: 1.2;
      font-weight: 950;
    }}
    .table-wrap {{
      width: 100%;
      overflow-x: auto;
      border: 2px solid #111;
      border-radius: 12px;
      background: #fffdf8;
    }}
    .report-table {{
      width: 100%;
      min-width: 920px;
      border-collapse: collapse;
      table-layout: fixed;
    }}
    .comparison-table {{ min-width: 1120px; }}
    .next-action-table {{ min-width: 920px; }}
    .report-table th,
    .report-table td {{
      border-bottom: 1.5px solid rgba(17,17,17,.16);
      border-right: 1.5px solid rgba(17,17,17,.1);
      padding: 9px 10px;
      text-align: left;
      vertical-align: top;
      color: #222228;
      font-size: 12px;
      line-height: 1.38;
      font-weight: 700;
      overflow-wrap: anywhere;
    }}
    .report-table th {{
      color: #111;
      background: #fff3b8;
      font-size: 11px;
      line-height: 1.2;
      font-weight: 950;
      white-space: nowrap;
    }}
    .report-table tr:last-child td {{ border-bottom: 0; }}
    .report-table th:last-child,
    .report-table td:last-child {{ border-right: 0; }}
    .next-table-module {{ grid-column: 1 / -1; }}
    .evidence-module-stack {{
      display: grid;
      gap: 18px;
      margin-top: 12px;
    }}
    .evidence-module > h3 {{
      margin: 0 0 10px;
      color: #111;
      font-size: 22px;
      line-height: 1.16;
      font-weight: 980;
    }}
    .evidence-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }}
    .evidence-card {{
      border: 2px solid #111;
      border-radius: 14px 18px 13px 16px;
      padding: 13px;
      background: #fff;
      box-shadow: 4px 4px 0 rgba(208,160,44,.18);
    }}
    .evidence-head {{ display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }}
    .impact {{
      display: inline-flex;
      min-width: 42px;
      justify-content: center;
      border: 2px solid #111;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 900;
    }}
    .evidence-card p {{ margin: 0; font-size: 13px; line-height: 1.45; }}
    .decision-shift {{
      margin-top: 9px;
      padding: 8px 10px;
      border-radius: 10px;
      background: #f7f4eb;
      font-size: 13px;
      line-height: 1.4;
      font-weight: 760;
    }}
    .source-line {{ margin-top: 8px; color: #5b4612; font-size: 12px; font-weight: 760; }}
    .evidence-score-grid {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px 13px;
      margin-top: 8px;
      padding-top: 7px;
      border-top: 1.5px dashed rgba(17,17,17,.14);
    }}
    .evidence-score {{
      min-width: 0;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      color: rgba(17,17,17,.74);
    }}
    .evidence-score .score-icon {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 10px;
      height: 10px;
      flex: 0 0 auto;
    }}
    .evidence-score .score-icon svg {{
      display: block;
      width: 10px;
      height: 10px;
      overflow: visible;
    }}
    .evidence-score .score-icon polygon {{
      fill: rgba(208,160,44,.78);
      stroke: rgba(17,17,17,.72);
      stroke-width: 1.55;
      stroke-linejoin: round;
      vector-effect: non-scaling-stroke;
    }}
    .evidence-score .score-label {{
      color: rgba(91,70,18,.8);
      font-size: 10px;
      line-height: 1.1;
      font-weight: 850;
      white-space: nowrap;
    }}
    .evidence-score b {{
      color: rgba(17,17,17,.78);
      font-size: 11px;
      line-height: 1.1;
      font-weight: 850;
    }}
    .gap-stack {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .next-stack {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .stop-rule-flow {{
      display: grid;
      gap: 8px;
      margin-top: 7px;
    }}
    .stop-rule-block {{
      border: 2px dashed rgba(17,17,17,.32);
      border-radius: 12px;
      background: #fffef8;
      padding: 8px 9px;
    }}
    .stop-rule-action {{
      background: rgba(255, 248, 212, .9);
      border-style: solid;
    }}
    .stop-rule-block b {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 22px;
      margin-bottom: 3px;
      color: #5b4612;
      font-size: 11px;
      font-weight: 950;
    }}
    .stop-rule-block b span {{
      display: inline-grid;
      place-items: center;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: var(--gold);
      color: #111;
      font-size: 10px;
      border: 2px solid #111;
      line-height: 1;
    }}
    .stop-rule-block p {{
      margin: 4px 0 0;
      color: #24242a;
      font-size: 12px;
      line-height: 1.35;
      font-weight: 800;
    }}
    .stop-rule-block .next-list {{
      margin-top: 5px;
      padding-left: 16px;
    }}
    .module-intro {{
      grid-column: 1 / -1;
      border: 2px dashed rgba(17,17,17,.36);
      border-radius: 12px;
      background: #fffdf2;
      padding: 10px 12px;
    }}
    .module-intro p {{ margin: 0; font-size: 14px; line-height: 1.48; font-weight: 760; }}
    .gap-card, .step-card {{
      border: 2px solid #111;
      border-radius: 14px;
      padding: 12px;
      background: #fff;
      box-shadow: 4px 4px 0 rgba(17,17,17,.08);
    }}
    .gap-card {{ display: grid; grid-template-columns: 38px 1fr; gap: 9px; }}
    .gap-card h3, .gap-card p, .gap-card ul {{ grid-column: 2; }}
    .gap-card h3, .step-card h3 {{ font-size: 16px; line-height: 1.28; }}
    .compact-copy {{ margin: 7px 0 0; font-size: 13px; line-height: 1.42; font-weight: 720; }}
    .question-mark {{
      grid-row: 1 / span 3;
      width: 32px;
      height: 32px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      background: #fff;
      border: 2px solid #111;
      font-size: 15px;
      font-weight: 950;
      color: var(--gold);
    }}
    .step-card {{ position: relative; padding-left: 54px; }}
    .step-card > span {{
      position: absolute;
      left: 12px;
      top: 12px;
      width: 30px;
      height: 30px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      color: #fff;
      background: #111;
      font-size: 13px;
      font-weight: 900;
      box-shadow: 3px 3px 0 var(--gold);
    }}
    .profile-screen {{ min-height: calc(100vh - 88px); }}
    .profile-board {{ display: grid; gap: 32px; }}
    .profile-hero {{
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 18px;
      border-bottom: 3px solid rgba(17,17,17,.12);
      padding-bottom: 16px;
    }}
    .profile-hero h1 {{
      max-width: 820px;
      margin: 0;
      font-size: clamp(54px, 7vw, 92px);
      line-height: .98;
      letter-spacing: 0;
    }}
    .profile-subtitle {{
      max-width: 760px;
      margin: 14px 0 0;
      color: #3f3f46;
      font-size: clamp(19px, 2vw, 27px);
      line-height: 1.35;
      font-weight: 850;
    }}
    .profile-stats {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 18px;
    }}
    .profile-stat {{
      border: 2px solid #111;
      border-radius: 14px 12px 16px 13px;
      background: #fffdf2;
      padding: 12px;
      box-shadow: 4px 4px 0 rgba(208,160,44,.2);
    }}
    .profile-stat span {{
      display: block;
      color: #5b4612;
      font-size: 12px;
      font-weight: 900;
    }}
    .profile-stat strong {{
      display: block;
      margin-top: 6px;
      font-size: 18px;
      line-height: 1.25;
    }}
    .profile-module {{ display: grid; gap: 18px; }}
    .profile-module + .profile-module {{ margin-top: 8px; }}
    .profile-module.two-col {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; }}
    .profile-module-title {{
      display: flex;
      align-items: center;
      gap: 9px;
    }}
    .profile-module-title span {{
      display: grid;
      place-items: center;
      width: 26px;
      height: 26px;
      border: 2px solid #111;
      border-radius: 50%;
      background: var(--gold);
      color: #fff;
      font-size: 13px;
      font-weight: 950;
      box-shadow: 2px 2px 0 #111;
      flex: 0 0 auto;
    }}
    .profile-module-title h3 {{ font-size: 19px; }}
    .profile-grid,
    .profile-decision-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }}
    .profile-grid.three {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .profile-stack {{ display: grid; gap: 16px; margin-top: 16px; }}
    .profile-card {{
      border: 2px solid #111;
      border-radius: 14px 18px 13px 16px;
      background: #fff;
      padding: 12px;
      box-shadow: 4px 4px 0 rgba(17,17,17,.08);
    }}
    .profile-card-head {{
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
    }}
    .profile-card-head span,
    .profile-confidence,
    .guardrail-card small,
    .evidence-type-card small,
    .pattern-card small {{
      display: inline-flex;
      width: fit-content;
      border: 2px solid #111;
      border-radius: 999px;
      background: #fff9d7;
      padding: 3px 8px;
      color: #5b4612;
      font-size: 11px;
      line-height: 1.1;
      font-weight: 900;
    }}
    .profile-card h3 {{ font-size: 17px; line-height: 1.25; }}
    .profile-card p {{
      margin: 7px 0 0;
      color: #2f2f35;
      font-size: 13px;
      line-height: 1.45;
      font-weight: 720;
    }}
    .decision-record b {{
      display: inline-flex;
      width: fit-content;
      margin-top: 8px;
      border: 2px solid #111;
      border-radius: 999px;
      background: var(--gold-soft);
      padding: 4px 9px;
      font-size: 12px;
    }}
    .turning-point {{
      margin-top: 8px;
      border-left: 5px solid var(--gold);
      border-radius: 0 12px 12px 0;
      background: #fffdf2;
      padding: 8px 10px;
      color: #202026;
      font-size: 13px;
      line-height: 1.42;
      font-weight: 820;
    }}
    .decision-final {{
      display: inline-flex;
      align-items: flex-start;
      width: fit-content;
      max-width: 100%;
      border: 2px solid #111;
      border-radius: 12px;
      background: var(--gold-soft);
      padding: 7px 9px;
      box-sizing: border-box;
    }}
    .decision-final strong {{
      min-width: 0;
      color: #111;
      font-size: 13px;
      line-height: 1.35;
      font-weight: 900;
      overflow-wrap: anywhere;
    }}
    .insight-card {{
      display: grid;
      grid-template-columns: 28px 1fr;
      gap: 10px;
      align-items: start;
    }}
    .insight-card > span {{
      display: grid;
      place-items: center;
      width: 26px;
      height: 26px;
      border-radius: 50%;
      background: #111;
      color: #fff;
      font-size: 12px;
      font-weight: 900;
      box-shadow: 2px 2px 0 var(--gold);
    }}
    .insight-card p {{ margin: 0; }}
    .token-meter {{
      padding: 6px 0 24px;
      scroll-margin-top: 84px;
    }}
    .token-card {{
      display: flex;
      align-items: center;
      justify-content: center;
      width: min(960px, 100%);
      margin: 0 auto;
      padding: 0 6px;
      color: #696971;
    }}
    .token-summary-line {{
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      max-width: 100%;
    }}
    .token-summary {{
      color: #303038;
      font-size: 13px;
      line-height: 1;
      font-weight: 850;
    }}
    .token-summary span {{
      color: inherit;
      font-weight: inherit;
    }}
    .token-info {{
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 15px;
      height: 15px;
      border-radius: 50%;
      border: 1.5px solid rgba(17,17,17,.34);
      color: #565660;
      background: rgba(17,17,17,.035);
      font-size: 10px;
      line-height: 1;
      font-weight: 850;
      cursor: help;
      outline: none;
    }}
    .token-info:focus {{
      box-shadow: 0 0 0 3px rgba(208,160,44,.22);
    }}
    .token-tooltip {{
      position: absolute;
      left: 0;
      bottom: calc(100% + 10px);
      z-index: 20;
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 6px;
      width: max-content;
      max-width: min(720px, calc(100vw - 44px));
      padding: 10px 12px;
      border: 1px solid rgba(17,17,17,.16);
      border-radius: 8px;
      background: rgba(255,253,247,.98);
      box-shadow: 0 10px 28px rgba(17,17,17,.14);
      opacity: 0;
      visibility: hidden;
      pointer-events: none;
      transform: translate(0, 4px);
      transition: opacity .14s ease, transform .14s ease, visibility .14s ease;
    }}
    .token-tooltip::after {{
      content: "";
      position: absolute;
      left: 7px;
      bottom: -6px;
      width: 10px;
      height: 10px;
      border-right: 1px solid rgba(17,17,17,.16);
      border-bottom: 1px solid rgba(17,17,17,.16);
      background: rgba(255,253,247,.98);
      transform: rotate(45deg);
    }}
    .token-info:hover .token-tooltip,
    .token-info:focus .token-tooltip {{
      opacity: 1;
      visibility: visible;
      pointer-events: auto;
      transform: translate(0, 0);
    }}
    .token-breakdown-row {{
      display: flex;
      align-items: flex-start;
      justify-content: flex-start;
      gap: 7px;
      width: max-content;
      max-width: 100%;
      min-width: 0;
    }}
    .token-breakdown-label {{
      flex: 0 0 auto;
      color: #565660;
      font-size: 11px;
      line-height: 1.55;
      font-weight: 820;
    }}
    .token-chip-group {{
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-start;
      gap: 6px;
      min-width: 0;
    }}
    .token-chip {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      border-radius: 999px;
      background: rgba(17,17,17,.045);
      padding: 3px 7px;
      color: #696971;
      font-size: 11px;
      line-height: 1.1;
      font-weight: 680;
    }}
    .token-chip b {{
      color: #505058;
      font-weight: 780;
    }}
    .token-chip-muted {{
      color: #676771;
      background: rgba(17,17,17,.03);
    }}
    #gaps-screen .sketch-board, #next-screen .sketch-board, #evidence-screen .sketch-board {{ padding: clamp(18px, 2.5vw, 30px); }}
    #gaps-screen h2, #next-screen h2, #evidence-screen h2 {{ font-size: clamp(28px, 3.5vw, 44px); margin-bottom: 8px; }}
    @media (max-width: 980px) {{
      .topbar {{ grid-template-columns: auto 1fr auto; gap: 12px; padding: 0 18px; }}
      .nav-pills {{ max-width: 52vw; }}
      .wrap {{ width: min(100vw - 24px, 860px); }}
      .notes-grid, .evidence-grid, .gap-stack, .next-stack {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
      .profile-stats, .profile-grid.three {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .profile-module.two-col {{ grid-template-columns: 1fr; }}
      .expert-grid {{ grid-template-columns: 1fr; }}
      .economics-hero {{ grid-template-columns: 1fr; align-items: start; }}
      .economics-scenario-grid, .roi-action-grid, .finance-gate-grid {{ grid-template-columns: 1fr; }}
      #actions-screen .sketch-board, #evidence-screen .sketch-board, #gaps-screen .sketch-board, #next-screen .sketch-board {{ padding: 16px; }}
      #actions-screen h2, #evidence-screen h2, #gaps-screen h2, #next-screen h2 {{ font-size: 32px; }}
      #actions-screen .sticky-note {{ padding: 10px; }}
      #actions-screen .sticky-note h3 {{ font-size: 16px; }}
      .action-followup-pair {{ grid-template-columns: 1fr; gap: 12px; }}
      .action-followup-pair::before {{ display: none; }}
      .action-followup + .action-followup {{ border-top: 2px dashed rgba(17,17,17,.28); padding: 12px 0 0; }}
      .action-followup .note-body {{ grid-template-columns: 1fr; }}
      .note-section, .note-verdict {{ padding: 8px; margin-bottom: 7px; }}
      .action-point-list {{ gap: 4px; margin-top: 7px; }}
      .action-point-list p, .note-body .action-point-list p {{ font-size: 12px; line-height: 1.25; }}
      .evidence-card, .gap-card, .step-card {{ padding: 10px; }}
      .step-card {{ padding-left: 48px; }}
      .gap-card h3, .step-card h3 {{ font-size: 15px; }}
      .compact-copy, .module-intro p, .gap-list li, .next-list li {{ font-size: 12px; line-height: 1.32; }}
      .core-quote {{ font-size: 20px; line-height: 1.38; margin-bottom: 12px; padding: 10px 12px; }}
    }}
    @media (max-width: 460px) {{
      .topbar {{ height: auto; min-height: 74px; grid-template-columns: 1fr auto; padding: 9px 14px; gap: 8px; }}
      .brand span {{ display: none; }}
      .nav-pills {{ grid-column: 1 / -1; grid-row: 2; justify-self: stretch; max-width: none; }}
      .nav-pills a:not(:first-child):not(:last-child) {{ display: none; }}
      .topbar-actions {{ grid-column: 2; grid-row: 1; }}
      .profile-entry, .topbar-return {{ padding-right: 7px; }}
      .wrap {{ width: min(100vw - 20px, 760px); }}
      .screen {{ min-height: auto; padding: 14px 0; }}
      .sketch-board {{ padding: 22px; }}
      .question-grid, .core-grid, .expert-grid, .notes-grid, .evidence-grid, .gap-stack, .next-stack {{ grid-template-columns: 1fr; }}
      .scenario-values, .roi-action-metrics, .gate-thresholds {{ grid-template-columns: 1fr; }}
      .profile-stats, .profile-grid, .profile-grid.three, .profile-decision-grid {{ grid-template-columns: 1fr; }}
      .profile-hero {{ display: grid; }}
      .token-card {{ justify-content: flex-start; }}
      .token-summary-line {{ flex-wrap: wrap; row-gap: 5px; }}
      .token-tooltip {{ width: min(420px, calc(100vw - 28px)); }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand">
      <div class="mark" aria-hidden="true"></div>
      <div>
        <strong>Info-Alchemist</strong>
        <span>信息炼金报告</span>
      </div>
    </div>
    <nav class="nav-pills" aria-label="报告导航">
      <a class="pill" href="#question-screen">问题</a>
      <a class="pill" href="#core-screen">判断</a>
      {comparison_nav}
      {economics_nav}
      <a class="pill" href="#expert-screen">专家</a>
      <a class="pill" href="#actions-screen">行动</a>
      <a class="pill" href="#evidence-screen">证据</a>
      {social_nav}
      <a class="pill" href="#gaps-screen">缺口</a>
      <a class="pill" href="#next-screen">下一步</a>
    </nav>
    <div class="topbar-actions">
      <a class="profile-entry" href="{escaped_profile_url}" aria-label="查看个人决策画像">
        <span>个人决策画像</span>
        <span class="jump-arrow" aria-hidden="true">&gt;</span>
      </a>
    </div>
  </header>
  <main class="wrap">
    <section id="question-screen" class="screen">
      <article class="sketch-board">
        <div class="section-label"><span>1</span><b>决策问题</b></div>
        <div class="question-card">
          <h1>信息炼金报告</h1>
          <p class="question-lead"><span class="marker">{html.escape(question_summary)}</span></p>
          <div class="question-grid">{question_cards}</div>
        </div>
      </article>
    </section>
	    <section id="core-screen" class="screen">
	      <article class="sketch-board">
	        <div class="section-label"><span>2</span><b>核心判断</b></div>
	        <div>
	          <p class="core-quote">{inline_markdown(core_quote)}</p>
	          <div class="core-grid">{core_cards}</div>
	        </div>
	      </article>
	    </section>
	    {comparison_html}
	    {economics_html}
	    <section id="expert-screen" class="screen">
      <article class="sketch-board">
        <div class="section-label"><span>3</span><b>专家判断</b></div>
        <h2>外部信号怎么校准判断？</h2>
        <div class="expert-board">{expert_html}</div>
      </article>
    </section>
    <section id="actions-screen" class="screen">
      <article class="sketch-board">
        <div class="section-label"><span>4</span><b>候选行动</b></div>
        <h2>行动的优先级，是下注顺序</h2>
        <div class="{notes_grid_class}">{action_notes}</div>
      </article>
    </section>
    <section id="evidence-screen" class="screen">
      <article class="sketch-board">
        <div class="section-label"><span>5</span><b>高价值证据</b></div>
        <h2>哪些证据真的会改变行动？</h2>
        {evidence_cards}
      </article>
    </section>
    {social_html}
    <section id="gaps-screen" class="screen">
      <article class="sketch-board">
        <div class="section-label"><span>6</span><b>缺失的证据</b></div>
        <h2>还缺什么，不能直接拍板？</h2>
        <div class="gap-stack">{gap_cards}</div>
      </article>
    </section>
    <section id="next-screen" class="screen">
      <article class="sketch-board">
        <div class="section-label"><span>7</span><b>下一步行动</b></div>
        <h2>下一步具体做什么？</h2>
        <div class="next-stack">{next_cards}</div>
      </article>
    </section>
    {token_usage_html}
  </main>
</body>
</html>
"""


def build_html(
    report_markdown: str,
    run_id: str,
    html_url: str,
    profile_url: str = "",
    token_usage: Optional[Dict[str, Any]] = None,
) -> str:
    sections = split_sections(report_markdown)
    sections = {key: strip_removed_user_modules(value) for key, value in sections.items()}
    core = sections.get("核心判断", "")
    question = sections.get("决策问题", "")
    expert = sections.get("专家判断", "")
    actions = sections.get("候选行动", "")
    evidence = sections.get("高价值证据", "")
    gaps = sections.get("缺失的证据", "")
    next_steps = sections.get("下一步行动", "")

    question_summary = intro_before_list(question, "这份报告用于支持一个具体行动决策。")
    report_title = report_document_title(extract_decision_object(question))
    report_mode_label = extract_report_mode_label(question)
    question_cards = build_question_cards(question)
    core_quote = extract_quote(core, "先看核心判断，再展开证据。")
    core_cards = build_core_cards(core)
    comparison_html = build_comparison_screen(question)
    economics_html = build_economics_screen(sections)
    expert_html = build_expert_panel(expert)
    action_notes = build_action_notes(actions, next_steps)
    evidence_cards = build_evidence_cards(evidence)
    social_html = build_social_signal_screen(evidence)
    gap_cards = build_gap_cards(gaps)
    next_cards = build_next_cards(next_steps)
    profile_link = profile_url or f"{run_id}-profile.html"
    display_token_usage = token_usage or token_usage_from_markdown(report_markdown)

    return build_marker_html(
        html_url=html_url,
        report_title=report_title,
        report_mode_label=report_mode_label,
        question_summary=question_summary,
        question_cards=question_cards,
        core_quote=core_quote,
        core_cards=core_cards,
        comparison_html=comparison_html,
        economics_html=economics_html,
        expert_html=expert_html,
        action_notes=action_notes,
        evidence_cards=evidence_cards,
        social_html=social_html,
        gap_cards=gap_cards,
        next_cards=next_cards,
        profile_url=profile_link,
        token_usage=display_token_usage,
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>信息炼金报告</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #101011;
      --muted: #6f6f78;
      --line: #e7e7ee;
      --gold: #b68a2d;
      --gold-dark: #705116;
      --gold-soft: #fbf6e8;
      --soft: #f7f7f8;
      --radius: 18px;
      --font: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: #fff;
      font-family: var(--font);
      letter-spacing: 0;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 10;
      height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 0 28px;
      border-bottom: 1px solid var(--line);
      background: rgba(255,255,255,.92);
      backdrop-filter: blur(18px);
    }}
    .brand {{ display: flex; align-items: center; gap: 12px; min-width: 0; }}
    .mark {{
      width: 34px;
      height: 34px;
      border: 1px solid #111;
      border-radius: 10px;
      background: #111;
      box-shadow: inset 0 0 0 4px #fff;
      position: relative;
      flex: 0 0 auto;
    }}
    .mark::after {{
      content: "";
      position: absolute;
      right: 8px;
      bottom: 8px;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--gold);
    }}
    .brand strong {{ display: block; font-size: 17px; line-height: 1.05; }}
    .brand span {{ display: block; margin-top: 4px; color: var(--muted); font-size: 12px; }}
    .pill {{
      border: 1px solid #dfc47a;
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--gold-dark);
      background: var(--gold-soft);
      font-size: 12px;
      font-weight: 760;
      white-space: nowrap;
    }}
    .wrap {{ width: min(1180px, calc(100vw - 48px)); margin: 0 auto; padding: 24px 0 42px; }}
    .hero {{ min-height: 220px; }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: #fff;
      overflow: hidden;
    }}
    .hero-main {{
      padding: 30px;
      display: grid;
      align-content: space-between;
      background: linear-gradient(180deg, rgba(182,138,45,.07), transparent 62%), #fff;
    }}
    .kicker {{
      display: inline-flex;
      align-items: center;
      gap: 9px;
      color: var(--gold-dark);
      font-size: 13px;
      font-weight: 820;
    }}
    .kicker::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--gold);
      box-shadow: 0 0 0 6px rgba(182, 138, 45, .12);
    }}
    h1 {{
      margin: 16px 0 0;
      font-size: clamp(42px, 5vw, 76px);
      line-height: 1;
      letter-spacing: 0;
    }}
    .hero-main p {{
      max-width: 900px;
      margin: 22px 0 0;
      color: #34343a;
      font-size: 21px;
      line-height: 1.55;
      font-weight: 650;
    }}
    .body {{ margin-top: 16px; }}
    .report {{ padding: 34px 40px; }}
    .report h1 {{ display: none; }}
    .report h2 {{
      margin: 34px 0 14px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
      font-size: 27px;
      line-height: 1.2;
    }}
    .report h2:first-child {{ margin-top: 0; padding-top: 0; border-top: 0; }}
    .report h3 {{ margin: 22px 0 10px; font-size: 20px; }}
    .report p, .report li {{ color: #3b3b42; font-size: 16px; line-height: 1.78; }}
    .report p {{ margin: 12px 0; }}
    .report strong {{ color: #111; }}
    .report blockquote {{
      margin: 16px 0;
      padding: 14px 16px;
      border-left: 4px solid var(--gold);
      background: var(--gold-soft);
      color: #4c3a16;
      border-radius: 0 12px 12px 0;
    }}
    .report ul, .report ol {{ padding-left: 24px; margin: 12px 0; }}
    .report hr {{ border: 0; border-top: 1px solid var(--line); margin: 22px 0; }}
    .report a {{ color: #111; border-bottom: 1px solid var(--gold); }}
    .table-wrap {{ width: 100%; overflow-x: auto; border: 1px solid var(--line); border-radius: 14px; margin: 14px 0 20px; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 960px; table-layout: fixed; }}
    th, td {{ padding: 14px 16px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-size: 14px; line-height: 1.62; word-break: normal; overflow-wrap: break-word; }}
    th {{ color: #111; background: var(--soft); font-weight: 760; }}
    .evidence-table {{ min-width: 1080px; }}
    .evidence-table th:nth-child(1), .evidence-table td:nth-child(1),
    .evidence-table th:nth-child(2), .evidence-table td:nth-child(2) {{ word-break: keep-all; overflow-wrap: normal; }}
    .evidence-table th:nth-child(5), .evidence-table td:nth-child(5) {{ overflow-wrap: anywhere; }}
    .expert-table {{ min-width: 1240px; }}
    tr:last-child td {{ border-bottom: 0; }}
    @media (max-width: 960px) {{
      .wrap {{ width: min(100vw - 24px, 760px); padding-top: 12px; }}
      .topbar {{ padding: 0 14px; }}
      .report {{ padding: 24px 22px; }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand">
      <div class="mark" aria-hidden="true"></div>
      <div>
        <strong>Info-Alchemist</strong>
        <span>信息炼金报告</span>
      </div>
    </div>
  </header>
  <main class="wrap">
    <section class="hero">
      <article class="panel hero-main">
        <div>
          <div class="kicker">决策问题</div>
          <h1>信息炼金报告</h1>
          <p>{html.escape(question_summary)}</p>
        </div>
      </article>
    </section>
    <section class="body">
      <article class="panel report">
        {rendered_report}
      </article>
    </section>
  </main>
</body>
</html>
"""


def build_profile_html(profile_markdown: str, report_url: str) -> str:
    profile_screen = build_profile_screen(profile_markdown, report_url)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>个人决策画像</title>
  <style>
    :root {{
      color-scheme: light;
      --paper: #fffdf7;
      --ink: #111;
      --muted: #595961;
      --line: #171717;
      --gold: #d0a02c;
      --gold-soft: #fff1a8;
      --shadow: rgba(17, 17, 17, .14);
      --font: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: radial-gradient(circle at 12px 12px, rgba(208,160,44,.055) 1px, transparent 1px), var(--paper);
      background-size: 24px 24px;
      font-family: var(--font);
      letter-spacing: 0;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 10;
      height: 72px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 0 30px;
      border-bottom: 3px solid var(--line);
      background: rgba(255,253,247,.94);
      backdrop-filter: blur(18px);
    }}
    .brand {{ display: flex; align-items: center; gap: 12px; min-width: 0; }}
    .mark {{
      width: 38px;
      height: 38px;
      border: 3px solid #111;
      border-radius: 11px 13px 10px 12px;
      background: #111;
      box-shadow: inset 0 0 0 4px #fff;
      position: relative;
      flex: 0 0 auto;
    }}
    .mark::after {{
      content: "";
      position: absolute;
      right: 8px;
      bottom: 8px;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--gold);
    }}
    .brand strong {{ display: block; font-size: 18px; line-height: 1.05; }}
    .brand span {{ display: block; margin-top: 4px; color: var(--muted); font-size: 12px; font-weight: 680; }}
    .wrap {{ width: min(1180px, calc(100vw - 34px)); margin: 0 auto; padding: 18px 0 46px; }}
    .screen {{ min-height: calc(100vh - 88px); display: grid; align-content: center; padding: 18px 0; }}
    .sketch-board {{
      position: relative;
      border: 3px solid var(--line);
      border-radius: 22px 18px 24px 17px;
      background: rgba(255,255,255,.92);
      box-shadow: 7px 7px 0 rgba(208,160,44,.22), 0 18px 54px var(--shadow);
      padding: clamp(18px, 3vw, 34px);
      overflow: hidden;
    }}
    .section-label {{ display: inline-flex; align-items: center; gap: 10px; margin-bottom: 12px; font-size: 13px; font-weight: 900; }}
    .section-label span:first-child, .profile-module-title span {{
      display: grid;
      place-items: center;
      width: 26px;
      height: 26px;
      border-radius: 50%;
      color: #fff;
      background: var(--gold);
      border: 2px solid var(--line);
      box-shadow: 2px 2px 0 #111;
      flex: 0 0 auto;
    }}
    .pill {{
      border: 2px solid var(--line);
      border-radius: 999px;
      padding: 9px 13px;
      background: #fff;
      font-size: 12px;
      font-weight: 850;
      white-space: nowrap;
      box-shadow: 2px 2px 0 var(--gold);
    }}
    .topbar-return {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: var(--gold-soft);
      box-shadow: 2px 2px 0 #111;
      padding-right: 9px;
    }}
    .profile-entry,
    .topbar-return {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border: 2px solid var(--line);
      border-radius: 999px;
      background: var(--gold-soft);
      padding: 8px 9px 8px 13px;
      color: #111;
      font-size: 13px;
      line-height: 1;
      font-weight: 900;
      white-space: nowrap;
      box-shadow: 3px 3px 0 #111;
      box-sizing: border-box;
    }}
    .jump-arrow {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: #111;
      color: #fff;
      font-family: Arial, Helvetica, sans-serif;
      font-size: 12px;
      line-height: 1;
      font-weight: 900;
      align-self: center;
      transform: none;
      flex: 0 0 auto;
    }}
    h2 {{ margin: 0 0 14px; font-size: clamp(30px, 4vw, 48px); line-height: 1.05; }}
    h3 {{ margin: 0; font-size: 21px; line-height: 1.22; }}
    p {{ color: #2f2f35; font-size: 16px; line-height: 1.62; }}
    .profile-board {{ display: grid; gap: 32px; }}
    .profile-hero {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 18px;
      border-bottom: 3px solid rgba(17,17,17,.12);
      padding-bottom: 16px;
    }}
    .profile-hero h1 {{
      max-width: 820px;
      margin: 0;
      font-size: clamp(54px, 7vw, 92px);
      line-height: .98;
      letter-spacing: 0;
    }}
    .profile-subtitle {{
      max-width: 760px;
      margin: 14px 0 0;
      color: #3f3f46;
      font-size: clamp(19px, 2vw, 27px);
      line-height: 1.35;
      font-weight: 850;
    }}
    .profile-stats {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px; }}
    .profile-stat, .profile-card {{
      border: 2px solid #111;
      border-radius: 14px 18px 13px 16px;
      background: #fff;
      padding: 12px;
      box-shadow: 4px 4px 0 rgba(17,17,17,.08);
    }}
    .profile-stat {{ background: #fffdf2; box-shadow: 4px 4px 0 rgba(208,160,44,.2); }}
    .profile-stat span {{ display: block; color: #5b4612; font-size: 12px; font-weight: 900; }}
    .profile-stat strong {{ display: block; margin-top: 6px; font-size: 18px; line-height: 1.25; }}
    .profile-stat:nth-child(4) strong {{ font-size: 15px; line-height: 1.42; }}
    .profile-module {{ display: grid; gap: 18px; }}
    .profile-module + .profile-module {{ margin-top: 8px; }}
    .profile-module.two-col {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; }}
    .profile-module-title {{ display: flex; align-items: center; gap: 9px; }}
    .profile-module-title h3 {{ font-size: 19px; }}
    .profile-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }}
    .profile-decision-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }}
    .profile-grid.three {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .profile-stack {{ display: grid; gap: 16px; margin-top: 16px; }}
    .decision-record {{ padding: 16px 18px; }}
    .profile-card-head {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 10px;
    }}
    .profile-card-head strong {{
      flex: 1 1 auto;
      min-width: 0;
      color: #111;
      font-size: 16px;
      line-height: 1.28;
      font-weight: 950;
      text-align: left;
    }}
    .decision-record .profile-card-head {{
      align-items: center;
      margin-bottom: 0;
    }}
    .decision-record .profile-card-head strong {{
      font-size: 18px;
      line-height: 1.22;
    }}
    .profile-card-head span, .profile-confidence, .guardrail-card small, .evidence-type-card small, .pattern-card small {{
      display: inline-flex;
      flex: 0 0 auto;
      width: fit-content;
      border: 2px solid #111;
      border-radius: 999px;
      background: #fff9d7;
      padding: 3px 8px;
      color: #5b4612;
      font-size: 11px;
      line-height: 1.1;
      font-weight: 900;
    }}
    .profile-card h3 {{ font-size: 17px; line-height: 1.25; }}
    .profile-card p {{ margin: 7px 0 0; color: #2f2f35; font-size: 13px; line-height: 1.45; font-weight: 720; }}
    .decision-flow {{
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }}
    .decision-field {{
      padding: 0 2px;
      color: #2f2f35;
    }}
    .decision-field p {{
      margin: 0;
      color: #25252b;
      font-size: 15px;
      line-height: 1.48;
      font-weight: 850;
    }}
    .field-label {{
      display: block;
      margin-bottom: 4px;
      color: #6c5a24;
      font-size: 11px;
      line-height: 1.15;
      font-weight: 850;
    }}
    .decision-final {{
      display: inline-flex;
      align-items: flex-start;
      width: fit-content;
      max-width: 100%;
      border: 2px solid #111;
      border-radius: 12px;
      background: var(--gold-soft);
      padding: 7px 9px;
      box-sizing: border-box;
    }}
    .decision-final strong {{
      min-width: 0;
      color: #111;
      font-size: 14px;
      line-height: 1.35;
      font-weight: 900;
      overflow-wrap: anywhere;
    }}
    .turning-point {{
      border-left: 5px solid var(--gold);
      border-radius: 0 12px 12px 0;
      background: #fffdf2;
      padding: 10px 12px;
      color: #202026;
      font-size: 15px;
      line-height: 1.48;
      font-weight: 820;
    }}
    .turning-point strong {{
      display: block;
      margin-bottom: 4px;
      color: #5b4612;
      font-size: 11px;
      line-height: 1.15;
      font-weight: 950;
    }}
    .insight-card {{ display: grid; grid-template-columns: 28px 1fr; gap: 10px; align-items: start; }}
    .insight-card > span {{
      display: grid;
      place-items: center;
      width: 26px;
      height: 26px;
      border-radius: 50%;
      background: #111;
      color: #fff;
      font-size: 12px;
      font-weight: 900;
      box-shadow: 2px 2px 0 var(--gold);
    }}
    .insight-card p {{ margin: 0; }}
    @media (max-width: 980px) {{
      .wrap {{ width: min(100vw - 24px, 860px); }}
      .profile-stats, .profile-grid.three {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .profile-module.two-col {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 460px) {{
      .topbar {{ padding: 0 14px; }}
      .wrap {{ width: min(100vw - 20px, 760px); }}
      .screen {{ min-height: auto; padding: 14px 0; }}
      .sketch-board {{ padding: 22px; }}
      .profile-stats, .profile-grid, .profile-grid.three, .profile-decision-grid {{ grid-template-columns: 1fr; }}
      .profile-hero {{ display: grid; }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand">
      <div class="mark" aria-hidden="true"></div>
      <div>
        <strong>Info-Alchemist</strong>
        <span>个人决策画像</span>
      </div>
    </div>
    <a class="pill topbar-return" href="{html.escape(report_url, quote=True)}">
      <span>信息炼金报告</span>
      <span class="jump-arrow" aria-hidden="true">&gt;</span>
    </a>
  </header>
  <main class="wrap">
    {profile_screen}
  </main>
</body>
</html>
"""


def configured_base_url() -> str:
    return os.environ.get("INFO_ALCHEMIST_HTML_BASE_URL", "").strip()


def should_use_file_url() -> bool:
    return os.environ.get("INFO_ALCHEMIST_HTML_REPORT_URL_MODE", "").strip().lower() == "file"


def join_base_url(base_url: str, filename: str) -> str:
    return f"{base_url.rstrip('/')}/{quote(filename)}"


def local_http_url(filename: str, port: int | None = None) -> str:
    return f"http://{html_report_host()}:{port or html_report_port()}/{quote(filename)}"


LOCAL_URL_OPENER = build_opener(ProxyHandler({}))


def can_open_url(url: str, timeout: float = 0.5) -> bool:
    try:
        with LOCAL_URL_OPENER.open(url, timeout=timeout) as response:
            return 200 <= getattr(response, "status", 200) < 400
    except (OSError, URLError, TimeoutError):
        return False


def can_bind_local_port(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
        return True
    except OSError:
        return False


def ensure_local_report_server(directory: Path, check_url: str, port: int | None = None) -> bool:
    if can_open_url(check_url):
        return True

    selected_port = port or html_report_port()
    selected_host = html_report_host()
    if not can_bind_local_port(selected_host, selected_port):
        return False

    log_dir = runs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "html_report_server.log"
    log_file = log_path.open("ab")
    command = [
        sys.executable,
        "-m",
        "http.server",
        str(selected_port),
        "--bind",
        selected_host,
        "--directory",
        str(directory.resolve()),
    ]
    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
    )
    log_file.close()
    for _ in range(20):
        if can_open_url(check_url, timeout=0.3):
            return True
        time.sleep(0.1)
    return False


def candidate_local_report_ports() -> List[int]:
    primary = html_report_port()
    if os.environ.get("INFO_ALCHEMIST_HTML_REPORT_PORT", "").strip():
        return [primary]
    upper = min(primary + html_report_port_span(), 65536)
    return list(range(primary, upper))


def report_url_for(target_path: Path, target_dir: Path) -> str:
    file_url = target_path.resolve().as_uri()
    if should_use_file_url():
        return file_url

    base_url = configured_base_url()
    if base_url:
        return join_base_url(base_url, target_path.name)

    for port in candidate_local_report_ports():
        candidate = local_http_url(target_path.name, port=port)
        if ensure_local_report_server(target_dir, candidate, port=port):
            return candidate
    raise RuntimeError(
        "本地 HTML 报告服务启动失败：没有找到可用端口，或当前环境不允许绑定 127.0.0.1。"
        f"HTML 文件已生成：{target_path.resolve()}。如需强制 file:// 输出，请显式设置 "
        "INFO_ALCHEMIST_HTML_REPORT_URL_MODE=file。"
    )


def sibling_report_url(report_url: str, sibling_path: Path) -> str:
    if report_url.startswith("file://"):
        return sibling_path.resolve().as_uri()
    return re.sub(r"[^/#?]+(?:[#?].*)?$", quote(sibling_path.name), report_url)


def publish_html_report(
    report_markdown: str,
    run_id: str,
    output_dir: str = "",
    token_usage: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    safe_id = safe_run_id(run_id)
    filename_stem = html_report_filename_stem(safe_id)
    target_dir = Path(output_dir).expanduser() if output_dir else default_output_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{filename_stem}.html"
    profile_target_path = target_dir / f"{filename_stem}-profile.html"
    initial_url = join_base_url(configured_base_url(), target_path.name) if configured_base_url() and not should_use_file_url() else local_http_url(target_path.name)
    if should_use_file_url():
        initial_url = target_path.resolve().as_uri()
    profile_markdown = read_personal_profile_markdown()
    html_text = build_html(report_markdown, safe_id, initial_url, profile_target_path.name, token_usage=token_usage)
    profile_html_text = build_profile_html(profile_markdown, target_path.name)
    target_path.write_text(html_text, encoding="utf-8")
    profile_target_path.write_text(profile_html_text, encoding="utf-8")
    html_url = report_url_for(target_path, target_dir)
    profile_url = sibling_report_url(html_url, profile_target_path)
    if html_url != initial_url:
        html_text = build_html(report_markdown, safe_id, html_url, profile_target_path.name, token_usage=token_usage)
        profile_html_text = build_profile_html(profile_markdown, target_path.name)
        target_path.write_text(html_text, encoding="utf-8")
        profile_target_path.write_text(profile_html_text, encoding="utf-8")
    result = {
        "html_path": str(target_path.resolve()),
        "html_url": html_url,
        "profile_html_path": str(profile_target_path.resolve()),
        "profile_html_url": profile_url,
        "linked_heading": linked_heading(html_url),
        "linked_text": with_linked_heading(report_markdown, html_url),
    }
    if token_usage:
        result["token_usage_estimate"] = token_usage
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="把 Info-Alchemist Markdown 报告渲染为可点击 HTML 报告。")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--file", default="")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    text = read_text(args.file).strip()
    if not text:
        raise SystemExit("请通过 stdin 或 --file 提供报告文本。")
    result = publish_html_report(text, args.run_id, output_dir=args.output_dir)
    print(json.dumps({k: v for k, v in result.items() if k != "linked_text"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
