#!/usr/bin/env python3
import json
import re
import sys
from collections import Counter
from typing import Any, Dict, List

from info_alchemist_paths import records_file
import semantic_router


def read_query() -> str:
    args = sys.argv[1:]
    if args:
        if args[0] in {"--query", "-q"}:
            return " ".join(args[1:]).strip()
        if args[0].startswith("--query="):
            return " ".join([args[0].split("=", 1)[1], *args[1:]]).strip()
        return " ".join(args).strip()
    return sys.stdin.read().strip()


def has_any(text: str, patterns: List[str]) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def load_recent_records() -> List[Dict[str, Any]]:
    path = records_file()
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records[-20:]


def infer_from_memory(records: List[Dict[str, Any]]) -> tuple[str, str]:
    if not records:
        return "unknown", "low"

    text = "\n".join(
        " ".join([
            record.get("decision_context", ""),
            record.get("next_action", ""),
            record.get("insight", ""),
        ])
        for record in records
    )
    trigger_counts = Counter(record.get("trigger_reason_type", "other") for record in records)

    if has_any(text, [r"SEO", r"选题", r"关键词", r"页面", r"长尾"]):
        return "seo_or_content_opportunity", "medium"
    if has_any(text, [r"工具站", r"产品", r"API", r"小工具"]):
        return "tool_or_product_opportunity", "medium"
    if trigger_counts.get("competitor_signal", 0) >= 2:
        return "competitor_or_market_signal", "medium"
    if trigger_counts.get("fomo", 0) >= 2:
        return "opportunity_filter", "medium"
    return "unknown", "low"


def display_query(query: str) -> str:
    compact = re.sub(r"\s+", " ", query.strip())
    if len(compact) > 60:
        return compact[:57] + "..."
    return compact or "这件事"


def display_target(query: str) -> str:
    text = display_query(query)
    text = re.sub(r"^(--query|-q)\s+", "", text).strip()
    text = re.sub(r"^--query=", "", text).strip()
    text = re.sub(
        r"^(帮我|请|麻烦|帮忙)?\s*(查询|查一下|查查|研究一下|看一下|看看|了解一下|找一下|搜一下|搜索)\s*",
        "",
        text,
        flags=re.I,
    ).strip()
    text = re.sub(r"[。！？?!]+$", "", text).strip()
    text = re.sub(r"([\u4e00-\u9fff])(?i:AI)", r"\1 AI", text)
    text = re.sub(r"(?i)AI\s*(视频|图片|新闻|工具|模型|站)", r"AI \1", text)
    text = re.sub(r"\s+", " ", text).strip()

    reference_match = re.search(
        r"^哪些\s*(.+?)\s*(值得参考|可以参考|可参考|适合参考|值得借鉴|可以借鉴)$",
        text,
        re.I,
    )
    if reference_match:
        noun = reference_match.group(1).strip()
        return f"最新的 {noun}"

    return text or display_query(query)


def generic_confirmation_question(query: str) -> str:
    target = display_target(query)
    return (
        "INFO_ALCHEMIST=TRUE\n\n"
        f"你想查询{target}，主要是想做什么样的**决策**呢？\n\n"
        "## 1. 产品机会\n"
        "找适合做工具站、产品、API 封装或小工具的机会。\n\n"
        "## 2. 竞品/行业变化\n"
        "判断模型、平台、竞品、融资、合作或生态变化会不会影响你的方向。\n\n"
        "## 3. SEO/内容机会\n"
        "筛关键词、选题、榜单页、对比页、教程页或流量切口。\n\n"
        "## 4. 资讯速览\n"
        "只想知道最近重要新闻，不需要行动判断。\n\n"
        "可以详细告诉我，我帮你更精准地搜索到你需要的**高价值信息**。"
    )


def is_reference_site_query(query: str) -> bool:
    return bool(re.search(r"(AI|人工智能)?.*(视频站|视频工具|视频生成|AI\s*video).*(参考|借鉴|对标|竞品)|哪些.*(AI|人工智能)?.*(视频站|视频工具|视频生成).*(值得参考|参考)", query, re.I))


def reference_site_confirmation_question(query: str) -> str:
    target = display_target(query)
    return (
        "INFO_ALCHEMIST=TRUE\n\n"
        f"你想查询{target}，主要是为了做什么**决策**呢？\n\n"
        "## 1. 产品体验\n\n"
        "**参考如何让新用户留下来：** 首页怎么讲清楚价值、新用户怎么开始生成、有没有模板、生成流程顺不顺、第一次试用门槛高不高。\n\n"
        "## 2. 付费/商业模式\n\n"
        "**参考如何转化付费用户：** 免费额度有多少、积分包怎么设计、订阅模式、导出限制、是否有水印、商用授权怎么设计。\n\n"
        "## 3. SEO/内容结构\n\n"
        "**参考如何拿搜索流量：** 首页的关键词布局、内容入口和内链结构布局。\n\n"
        "## 4. 模型/功能能力\n\n"
        "**参考如何功能设计：** 文生视频、图生视频、是否有视频编辑、风格模板有哪些、脚本生成、视频工作流。\n\n"
        "可以详细告诉我，我帮你更精准的搜索到你需要的**高价值信息**~"
    )


def clarify(query: str) -> Dict[str, Any]:
    text = query.strip()
    semantic = semantic_router.route_query(text)
    if semantic.get("needs_confirmation"):
        return {
            "route": "ask_user",
            "allowed_to_search": False,
            "needs_confirmation": True,
            "inferred_intent": semantic.get("query_type", "generic_research"),
            "confidence": "medium" if semantic.get("route_source") == "fallback_semantic" else "high",
            "confirmation_question": semantic.get("confirmation_question", ""),
            "decision_clarity": semantic.get("decision_clarity", ""),
            "query_type": semantic.get("query_type", ""),
            "topic": semantic.get("topic", ""),
            "research_dimensions": semantic.get("research_dimensions", []),
            "action_options": semantic.get("action_options", []),
            "confirmation_round": semantic.get("confirmation_round", 0),
            "max_confirmation_rounds": semantic.get("max_confirmation_rounds", semantic_router.MAX_CONFIRMATION_ROUNDS),
            "reason": "用户的行动目的还不够明确；需要先确认搜索结果要改变哪类行动。"
        }
    if semantic.get("trigger_level") in {"full", "review"}:
        return {
            "route": "proceed",
            "allowed_to_search": True,
            "needs_confirmation": False,
            "inferred_intent": semantic.get("query_type", "generic_research"),
            "confidence": "medium" if semantic.get("route_source") == "fallback_semantic" else "high",
            "decision_clarity": semantic.get("decision_clarity", ""),
            "query_type": semantic.get("query_type", ""),
            "topic": semantic.get("topic", ""),
            "research_dimensions": semantic.get("research_dimensions", []),
            "action_context": semantic.get("action_context", ""),
            "confirmed_intent": semantic.get("confirmed_intent", ""),
            "confirmed_intent_type": semantic.get("confirmed_intent_type", ""),
            "reason": "用户已经说明行动目的，可以围绕该意图生成 search_plan。"
        }

    explicit_intent_patterns = [
        r"SEO|选题|关键词|长尾|内容",
        r"产品机会|小工具机会|API\s*封装|要不要做|能不能做|值不值得|是否值得|开发",
        r"(做|开发|搭|搭建|上线|运营).*(工具站|网站|站点|产品|小工具)",
        r"竞品|竞争|行业变化|市场信号",
        r"资讯速览|只想了解|快速了解|概览",
    ]

    if has_any(text, explicit_intent_patterns):
        return {
            "route": "proceed",
            "allowed_to_search": True,
            "needs_confirmation": False,
            "inferred_intent": "explicit_in_query",
            "confidence": "high",
            "reason": "用户已经在查询中说明了筛选标准或决策用途，可以围绕该意图生成 search_plan。"
        }

    if is_reference_site_query(text):
        return {
            "route": "ask_user",
            "allowed_to_search": False,
            "needs_confirmation": True,
            "inferred_intent": "reference_site_research",
            "confidence": "high",
            "confirmation_question": reference_site_confirmation_question(text),
            "reason": "用户要找一批可参考的 AI 视频站；需要先确认参考维度，否则搜索会混在产品体验、商业化、SEO 和功能能力之间。"
        }

    if has_any(text, [
        r"(最近|最新|这周|近来|近期|热门|比较火|很火|火的|头部).*(AI|人工智能)?.*(工具站|网站|站点|产品|工具)",
        r"(AI|人工智能)?.*(工具站|网站|站点|产品|工具).*(最近|最新|这周|近来|近期|热门|比较火|很火|火的|头部)"
    ]):
        return {
            "route": "ask_user",
            "allowed_to_search": False,
            "needs_confirmation": True,
            "inferred_intent": "open_set_tool_research",
            "confidence": "high",
            "confirmation_question": reference_site_confirmation_question(text),
            "reason": "用户在查一批热门工具站；“热门”不是决策用途，需要先确认是看产品体验、商业模式、SEO 结构还是功能能力。"
        }

    inferred_intent, confidence = infer_from_memory(load_recent_records())
    if inferred_intent != "unknown":
        target = display_target(text)
        question = (
            "INFO_ALCHEMIST=TRUE\n\n"
            f"你想查询{target}，主要是想做什么样的**决策**呢？\n\n"
            "我猜可能是你最近常用的口径：筛出"
            f" `{inferred_intent}` 相关的高价值信息。\n\n"
            "## 1. 是，按这个口径查\n"
            "直接围绕这个决策用途生成联网搜索计划。\n\n"
            "## 2. 不是，我补充这次用途\n"
            "你告诉我这次真正要做的决策，我再重新规划搜索。\n\n"
            "可以详细告诉我，我帮你更精准地搜索到你需要的**高价值信息**。"
        )
    else:
        question = generic_confirmation_question(text)

    return {
        "route": "ask_user",
        "allowed_to_search": False,
        "needs_confirmation": True,
        "inferred_intent": inferred_intent,
        "confidence": confidence,
        "confirmation_question": question,
        "reason": "这是开放集合查询；缺少查询意图时，搜索范围和判断标准会明显跑偏。"
    }


def main() -> int:
    print(json.dumps(clarify(read_query()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
