#!/usr/bin/env python3
import json
import re
import sys
from typing import Dict, List

import semantic_router


OPTION_MAP = {
    "1": ("tool_or_product_opportunity", "产品机会"),
    "2": ("competitor_or_market_signal", "竞品/行业变化"),
    "3": ("seo_or_content_opportunity", "SEO/内容机会"),
    "4": ("news_brief", "资讯速览"),
}

REFERENCE_OPTION_MAP = {
    "1": ("reference_product_experience", "产品体验"),
    "2": ("reference_business_model", "付费/商业模式"),
    "3": ("reference_seo_content_structure", "SEO/内容结构"),
    "4": ("reference_model_function_capability", "模型/功能能力"),
}


def read_args() -> tuple[str, str]:
    args = sys.argv[1:]
    query = ""
    remaining = []
    index = 0
    while index < len(args):
        if args[index] == "--query" and index + 1 < len(args):
            query = args[index + 1].strip()
            index += 2
            continue
        remaining.append(args[index])
        index += 1
    if remaining:
        return " ".join(remaining).strip(), query
    return sys.stdin.read().strip(), query


def is_reference_site_query(query: str) -> bool:
    return bool(re.search(r"(AI|人工智能)?.*(视频站|视频工具|视频生成|AI\s*video).*(参考|借鉴|对标|竞品)|哪些.*(AI|人工智能)?.*(视频站|视频工具|视频生成).*(值得参考|参考)", query, re.I))


def unique_ordered(values: List[str]) -> List[str]:
    seen = set()
    output = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def extract_options(reply: str) -> List[str]:
    text = reply.strip().upper()
    options = []

    for match in re.finditer(r"(?<!\d)([1-4])(?!\d)", text):
        options.append(match.group(1))

    natural_rules = [
        ("1", [r"产品机会", r"工具站", r"小工具", r"API\s*封装", r"产品方向", r"新功能"]),
        ("2", [r"竞品", r"竞争", r"行业变化", r"市场变化", r"生态变化", r"融资", r"合作"]),
        ("3", [r"SEO", r"内容机会", r"内容选题", r"关键词", r"长尾", r"对比页", r"教程页", r"榜单页", r"流量切口"]),
        ("4", [r"资讯速览", r"只.*了解", r"概览", r"新闻汇总", r"重要新闻"]),
        ("1", [r"产品体验", r"新用户", r"首页", r"模板", r"生成流程", r"试用门槛", r"留.*下来"]),
        ("2", [r"付费", r"商业模式", r"免费额度", r"积分包", r"订阅", r"导出限制", r"水印", r"商用授权", r"转化"]),
        ("3", [r"内容结构", r"搜索流量", r"关键词布局", r"内容入口", r"内链"]),
        ("4", [r"模型", r"功能能力", r"功能设计", r"文生视频", r"图生视频", r"视频编辑", r"风格模板", r"脚本生成", r"视频工作流"]),
    ]
    for option, patterns in natural_rules:
        if any(re.search(pattern, reply, re.I) for pattern in patterns):
            options.append(option)

    return unique_ordered(options)


def resolve_intent_type(options: List[str]) -> str:
    option_set = set(options)
    if {"1", "3"}.issubset(option_set):
        return "product_and_seo_opportunity"
    if "1" in option_set:
        return "tool_or_product_opportunity"
    if "3" in option_set:
        return "seo_or_content_opportunity"
    if "2" in option_set:
        return "competitor_or_market_signal"
    if "4" in option_set:
        return "news_brief"
    return "other"


def resolve_reference_intent_type(options: List[str]) -> str:
    option_set = set(options)
    if len(option_set) > 1:
        return "reference_multi_dimension"
    if "1" in option_set:
        return "reference_product_experience"
    if "2" in option_set:
        return "reference_business_model"
    if "3" in option_set:
        return "reference_seo_content_structure"
    if "4" in option_set:
        return "reference_model_function_capability"
    return "other"


def resolve(reply: str, query: str = "", context: Dict[str, object] | None = None) -> Dict[str, object]:
    semantic = semantic_router.resolve_reply(query, reply, context or {})
    if semantic.get("needs_confirmation"):
        return {
            "route": "ask_user",
            "allowed_to_search": False,
            "needs_confirmation": True,
            "selected_options": semantic.get("selected_action_options", []),
            "confirmed_intent": semantic.get("confirmed_intent", ""),
            "confirmed_intent_type": semantic.get("confirmed_intent_type", "other"),
            "query_type": semantic.get("query_type", ""),
            "topic": semantic.get("topic", ""),
            "research_dimensions": semantic.get("research_dimensions", []),
            "action_context": semantic.get("action_context", ""),
            "decision_clarity": semantic.get("decision_clarity", ""),
            "action_options": semantic.get("action_options", []),
            "confirmation_question": semantic.get("confirmation_question", ""),
            "confirmation_round": semantic.get("confirmation_round", 0),
            "max_confirmation_rounds": semantic.get("max_confirmation_rounds", semantic_router.MAX_CONFIRMATION_ROUNDS),
            "reason": "没有识别到足够明确的行动目的；需要用户继续补充行动目的。"
        }

    return {
        "route": "proceed",
        "allowed_to_search": True,
        "needs_confirmation": False,
        "selected_options": semantic.get("selected_action_options", []),
        "confirmed_intent": semantic.get("confirmed_intent", ""),
        "confirmed_intent_type": semantic.get("confirmed_intent_type", "other"),
        "query_type": semantic.get("query_type", ""),
        "topic": semantic.get("topic", ""),
        "research_dimensions": semantic.get("research_dimensions", []),
        "action_context": semantic.get("action_context", ""),
        "decision_clarity": semantic.get("decision_clarity", ""),
        "confirmation_round": semantic.get("confirmation_round", 0),
        "forced_after_max_confirmation": semantic.get("forced_after_max_confirmation", False),
        "reason": "用户回复了上一轮 Info-Alchemist 意图确认选项或补充说明，应作为同一条调研任务的续跑。"
    }


def main() -> int:
    reply, query = read_args()
    print(json.dumps(resolve(reply, query=query), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
