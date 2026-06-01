#!/usr/bin/env python3
import json
import re
import sys

import semantic_router


INTENT_TYPES = {
    "non_applicable",
    "direct_lookup",
    "factual_lookup",
    "curiosity",
    "open_set_research",
    "information_pile",
    "opportunity_research",
    "decision_research",
    "action_review",
}

TRIGGER_LEVELS = {"none", "direct", "light", "clarify", "full", "review"}


def read_input():
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:]).strip()
    raw = sys.stdin.read().strip()
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def has_any(text: str, patterns) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def normalize_ai_intent(data: dict) -> dict:
    ai_intent = data.get("ai_intent") or data.get("intent") or {}
    if not isinstance(ai_intent, dict):
        return {
            "intent_type": "non_applicable",
            "trigger_level": "none",
            "needs_confirmation": False,
            "classifier_type": "ai_semantic_invalid",
            "reason": "ai_intent 必须是对象。"
        }

    intent_type = str(ai_intent.get("intent_type", "")).strip()
    trigger_level = str(ai_intent.get("trigger_level", "")).strip()
    needs_confirmation = bool(ai_intent.get("needs_confirmation", False))
    reason = str(ai_intent.get("reason", "")).strip()

    errors = []
    if intent_type not in INTENT_TYPES:
        errors.append(f"intent_type 不在允许枚举中：{intent_type}")
    if trigger_level not in TRIGGER_LEVELS:
        errors.append(f"trigger_level 不在允许枚举中：{trigger_level}")
    if not reason:
        errors.append("reason 不能为空；必须解释语义判断依据。")

    if errors:
        return {
            "intent_type": "non_applicable",
            "trigger_level": "none",
            "needs_confirmation": False,
            "classifier_type": "ai_semantic_invalid",
            "errors": errors,
            "reason": "AI 语义意图输出未通过校验。"
        }

    output = {
        "intent_type": intent_type,
        "trigger_level": trigger_level,
        "needs_confirmation": needs_confirmation,
        "classifier_type": "ai_semantic",
        "reason": reason
    }
    for key in [
        "confirmed_intent",
        "decision_context",
        "default_action",
        "candidate_actions",
        "confirmed_intent_type",
        "intent_focus",
        "confidence",
        "query_type",
        "topic",
        "research_dimensions",
        "action_context",
        "decision_clarity",
        "search_strategy",
        "strategy_source",
        "strategy_reason",
        "confirmation_round",
        "max_confirmation_rounds",
    ]:
        if key in ai_intent:
            output[key] = ai_intent[key]
    return output


def classify(user_query: str) -> dict:
    text = user_query.strip()
    if not text:
        return {
            "intent_type": "non_applicable",
            "trigger_level": "none",
            "needs_confirmation": False,
            "classifier_type": "fallback_heuristic",
            "reason": "输入为空。"
        }

    semantic = semantic_router.route_query(text)
    semantic_type_map = {
        "non_applicable": "non_applicable",
        "direct_lookup": "direct_lookup",
        "factual_lookup": "factual_lookup",
        "curiosity": "curiosity",
        "reference_collection": "open_set_research",
        "latest_news": "open_set_research",
        "generic_research": "open_set_research",
        "opportunity_research": "opportunity_research",
        "decision_research": "decision_research",
        "information_pile": "information_pile",
        "action_review": "action_review",
    }
    query_type = semantic.get("query_type", "")
    if query_type in semantic_type_map:
        return {
            "intent_type": semantic_type_map[query_type],
            "trigger_level": semantic.get("trigger_level", "none"),
            "needs_confirmation": bool(semantic.get("needs_confirmation", False)),
            "classifier_type": "fallback_semantic",
            "query_type": query_type,
            "topic": semantic.get("topic", ""),
            "decision_clarity": semantic.get("decision_clarity", ""),
            "research_dimensions": semantic.get("research_dimensions", []),
            "action_context": semantic.get("action_context", ""),
            "confirmed_intent": semantic.get("confirmed_intent", ""),
            "confirmed_intent_type": semantic.get("confirmed_intent_type", ""),
            "search_strategy": semantic.get("search_strategy", "normal_evidence"),
            "strategy_source": semantic.get("strategy_source", ""),
            "strategy_reason": semantic.get("strategy_reason", ""),
            "reason": semantic.get("reason", "本地语义兜底完成意图判断。")
        }

    if has_any(text, [r"翻译", r"润色", r"改写", r"polish", r"translate", r"rewrite"]):
        return {
            "intent_type": "non_applicable",
            "trigger_level": "none",
            "needs_confirmation": False,
            "classifier_type": "fallback_heuristic",
            "reason": "这是语言处理任务，不是 VOI 决策任务。"
        }

    if has_any(text, [r"天气", r"汇率", r"几点", r"现在时间", r"今天日期", r"股价", r"weather", r"exchange rate"]):
        return {
            "intent_type": "direct_lookup",
            "trigger_level": "direct",
            "needs_confirmation": False,
            "classifier_type": "fallback_heuristic",
            "reason": "这是确定性查询，可以直接查，不需要进入完整 VOI 流程。"
        }

    if has_any(text, [r"这周看到", r"信息.*都重要", r"不知道哪些该做", r"一堆", r"很多条", r"information pile"]):
        return {
            "intent_type": "information_pile",
            "trigger_level": "full",
            "needs_confirmation": False,
            "classifier_type": "fallback_heuristic",
            "reason": "用户遇到信息堆积，需要按行动价值分流。"
        }

    if has_any(text, [
        r"(重点|主要|优先).*(SEO|选题|关键词|内容结构|产品体验|商业模式|付费|转化|功能能力|留存)",
        r"(为了|用来|想参考|想看).*(SEO|选题|关键词|内容结构|产品体验|商业模式|付费|转化|功能能力|留存)"
    ]):
        return {
            "intent_type": "open_set_research",
            "trigger_level": "full",
            "needs_confirmation": False,
            "classifier_type": "fallback_heuristic",
            "reason": "用户已经说明开放集合查询的用途或筛选维度，可以直接生成搜索计划。"
        }

    if has_any(text, [
        r"最新.*(新闻|趋势|动态)",
        r"(新闻|趋势|动态).*最新",
        r"AI.*新闻",
        r"AI.*趋势",
        r"(最近|最新|这周|近来|近期|热门|比较火|很火|火的|头部).*(AI|人工智能)?.*(工具站|网站|站点|产品|工具)",
        r"(AI|人工智能)?.*(工具站|网站|站点|产品|工具).*(最近|最新|这周|近来|近期|热门|比较火|很火|火的|头部)",
        r"(AI|人工智能)?.*(视频站|视频工具|视频生成|AI\s*video).*(参考|借鉴|对标|竞品)",
        r"哪些.*(AI|人工智能)?.*(视频站|视频工具|视频生成).*(值得参考|参考)",
        r"(最近|最新|这周|近来|近期).*(产品|竞品|市场|行业).*(动态|趋势|变化|新闻)",
        r"(产品|竞品|市场|行业).*(最近|最新|这周|近来|近期).*(动态|趋势|变化|新闻)",
        r"(生视频|生图|图像生成|视频生成).*(产品|工具|竞品).*(动态|趋势|变化|新闻)"
    ]):
        return {
            "intent_type": "open_set_research",
            "trigger_level": "clarify",
            "needs_confirmation": True,
            "classifier_type": "fallback_heuristic",
            "reason": "用户在查新闻、趋势、产品、竞品或市场动态这类开放集合信息；需要先确认用途，再决定搜索和报告结构。"
        }

    if has_any(text, [r"这两周做了很多", r"有没有结果", r"要不要继续", r"复盘", r"action review", r"continue or stop"]):
        return {
            "intent_type": "action_review",
            "trigger_level": "review",
            "needs_confirmation": False,
            "classifier_type": "fallback_heuristic",
            "reason": "用户正在复盘行动，并判断是否继续。"
        }

    if has_any(text, [r"有没有机会", r"值不值得", r"要不要做", r"能不能做", r"工具站", r"商业化", r"SEO", r"opportunit", r"worth", r"should I build"]):
        return {
            "intent_type": "opportunity_research",
            "trigger_level": "full",
            "needs_confirmation": False,
            "classifier_type": "fallback_heuristic",
            "reason": "用户在判断一个机会是否值得行动。"
        }

    if has_any(text, [r"决定", r"选哪个", r"是否", r"该不该", r"decision", r"choose"]):
        return {
            "intent_type": "decision_research",
            "trigger_level": "full",
            "needs_confirmation": False,
            "classifier_type": "fallback_heuristic",
            "reason": "查询背后存在决策，需要用 VOI 框架澄清。"
        }

    if has_any(text, [r"是什么", r"谁是", r"什么时候", r"多少钱", r"怎么用", r"what is", r"who is", r"when", r"how to"]):
        return {
            "intent_type": "factual_lookup",
            "trigger_level": "light",
            "needs_confirmation": False,
            "classifier_type": "fallback_heuristic",
            "reason": "这更像事实查询；除非出现明确决策，否则不触发完整流程。"
        }

    if has_any(text, [r"查一下", r"研究一下", r"了解一下", r"search", r"research"]):
        return {
            "intent_type": "curiosity",
            "trigger_level": "light",
            "needs_confirmation": True,
            "classifier_type": "fallback_heuristic",
            "reason": "用户想了解信息，但尚未出现会改变行动的明确决策。"
        }

    return {
        "intent_type": "non_applicable",
        "trigger_level": "none",
        "needs_confirmation": False,
        "classifier_type": "fallback_heuristic",
        "reason": "未检测到 VOI 触发条件。"
    }


def main() -> int:
    data = read_input()
    if isinstance(data, dict):
        if "ai_intent" in data or "intent" in data:
            result = normalize_ai_intent(data)
        else:
            result = classify(str(data.get("user_query", "")))
            result["classifier_type"] = "fallback_heuristic"
    else:
        result = classify(str(data))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
