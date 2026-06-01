#!/usr/bin/env python3
import json
import re
import sys

import semantic_router
from run_log import new_run_id, record_stage


SEARCH_INTENTS = {
    "official_capability",
    "competitor_and_monetization",
    "user_discussion",
    "search_intent",
    "seo_page_type",
    "api_feasibility",
    "expert_signal",
}

DEFAULT_SEARCH_PLAN_LIMIT = 16

EVIDENCE_AXES = {
    "market": "市场/趋势",
    "official": "官方能力/限制",
    "unit_economics": "成本/单位经济",
    "competition": "竞品/替代方案",
    "user_pain": "用户痛点/抱怨",
    "distribution": "获客/SEO/页面机会",
    "risk": "平台/政策/合规风险",
    "expert": "专家/实践者信号",
}

QUERY_GROUP_LABELS = {
    "candidate_pool": "候选池/产品清单",
    "segment_map": "赛道地图/细分方向",
    "competitor_pool": "竞品池/替代方案",
    "expert_signal": "专家/实践者信号",
    "product_flow": "产品路径/首次体验",
    "feature_capability": "功能/能力/工作流",
    "pricing": "定价/商业模式",
    "commercial_benchmark": "商业基准/ROI",
    "cost_structure": "成本/价格线索",
    "official_infra_pricing": "部署/服务器价格",
    "database_storage_pricing": "数据库/存储价格",
    "media_storage_pricing": "媒体存储/CDN 价格",
    "model_api_pricing": "模型/API 价格",
    "gpu_runtime_pricing": "GPU/推理平台价格",
    "email_pricing": "邮件/通知价格",
    "scraping_pricing": "抓取/代理价格",
    "analytics_monitoring_pricing": "监控/分析价格",
    "user_feedback": "用户反馈/痛点",
    "growth_seo": "增长/SEO/页面机会",
    "market_signal": "市场/行业信号",
    "official_capability": "官方能力/限制",
    "feasibility_cost": "可行性/成本/API",
    "risk_policy": "政策/合规/平台风险",
}

QUERY_GROUP_CAPS = {
    "expert_signal": 1,
}

LATEST_NEWS_INTENT_TYPES = {
    "tool_or_product_opportunity",
    "seo_or_content_opportunity",
    "product_and_seo_opportunity",
    "competitor_or_market_signal",
    "news_brief",
    "other",
}

REFERENCE_INTENT_TYPES = {
    "reference_product_experience",
    "reference_business_model",
    "reference_seo_content_structure",
    "reference_model_function_capability",
    "reference_multi_dimension",
    "other",
}


def read_input():
    raw = sys.stdin.read().strip()
    if raw:
        return json.loads(raw)
    if len(sys.argv) > 1:
        return {"user_query": " ".join(sys.argv[1:])}
    raise SystemExit("请通过 stdin 提供 JSON，或通过命令参数提供查询。")


ACTIVATION_MARKER_RE = re.compile(
    r"(?<![A-Z0-9_])INFO[\s_-]*ALCHEMIST(?:\s*=\s*TRUE)?(?![A-Z0-9_])|信息炼金术士",
    re.I,
)


def clean_spacing(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"\s+([，,。；;：:！？?!])", r"\1", text)
    text = re.sub(r"([（(【\\[])\s+", r"\1", text)
    text = re.sub(r"\s+([）)】\\]])", r"\1", text)
    return text.strip()


def strip_activation_markers(value: str) -> str:
    text = clean_spacing(value)
    if not text:
        return ""
    had_marker = bool(ACTIVATION_MARKER_RE.search(text))
    if not had_marker:
        return text
    text = ACTIVATION_MARKER_RE.sub(" ", text)
    text = clean_spacing(text)
    # These leading words are only removed when they were attached to an activation marker.
    # Do not strip normal user topics like “用 AI 做图”.
    text = re.sub(
        r"^(?:请)?(?:用|使用|调用|走|按|通过|启动|触发|运行|启用)\s*(?:这个|该)?\s*(?:skill|技能|流程|工具)?\s*",
        "",
        text,
        flags=re.I,
    )
    text = clean_spacing(text)
    return text.strip(" ：:，,。；;")


def clean_search_text(value: str) -> str:
    text = strip_activation_markers(value)
    text = re.sub(r"\s+", " ", text).strip(" ：:，,。；;")
    return text


def extract_topic(value: str) -> str:
    text = clean_search_text(value)
    text = re.sub(r"^(帮我|请|麻烦)?(查一下|查询|搜索|搜一下|研究一下|看一下|了解一下)", "", text).strip()
    text = re.sub(r"[，,。.!？?；;]?\s*(有没有机会.*|值不值得做?.*|要不要做.*|能不能做.*|我想看看.*)$", "", text).strip()
    return clean_search_text(text) or clean_search_text(value)


def first_clean_topic(*values: str) -> str:
    for value in values:
        topic = clean_search_text(value)
        if topic:
            return topic
    return ""


def normalize_research_topic(topic: str, user_query: str = "") -> str:
    text = clean_search_text(topic)
    if text and re.search(r"(最近|最新|现在|热门|比较火|很火|火的|头部).*(AI|人工智能|工具站|网站|站点|产品|工具)|(?:AI|人工智能).*(工具站|网站|站点|产品|工具).*(最近|最新|现在|热门|比较火|很火|火的|头部)", text, re.I):
        cleaned = semantic_router.extract_popular_tool_topic(text)
        if cleaned and cleaned != text:
            return clean_search_text(cleaned)
    if not text and user_query:
        return clean_search_text(semantic_router.extract_popular_tool_topic(user_query))
    return text


def sanitize_search_plan(plan: list) -> list:
    sanitized = []
    for item in plan:
        if not isinstance(item, dict):
            continue
        output = dict(item)
        output["query"] = clean_search_text(str(output.get("query", "")))
        if output["query"] and not output.get("query_group"):
            output["query_group"] = infer_query_group(output)
        if output.get("query_group") and not output.get("query_group_label"):
            output["query_group_label"] = QUERY_GROUP_LABELS.get(output["query_group"], output["query_group"])
        if output["query"] and not output.get("query_source"):
            output["query_source"] = "ai_draft" if output.get("planner_source") == "ai_search_plan" else "template"
        if output["query"] and not output.get("evidence_axis"):
            output["evidence_axis"] = infer_evidence_axis(output)
        if output["query"] and not output.get("evidence_role"):
            output["evidence_role"] = "primary" if output.get("evidence_axis") != "expert" else "supporting"
        if output["query"]:
            sanitized.append(output)
    return sanitized


def read_ai_search_plan(data: dict) -> list:
    raw = data.get("ai_search_plan") or data.get("search_plan_draft") or data.get("search_plan_hints") or []
    if isinstance(raw, dict):
        raw = raw.get("search_plan") or raw.get("queries") or []
    return raw if isinstance(raw, list) else []


def sanitize_ai_search_plan(raw_plan: list, topic: str, limit: int = 8) -> list:
    sanitized = []
    for raw in raw_plan:
        if not isinstance(raw, dict):
            continue
        query = clean_search_text(str(raw.get("query") or ""))
        if not query or len(query) < 6:
            continue
        if re.fullmatch(r"(?:最近|最新|现在|热门|比较火|AI|产品|工具|竞品|专家|\s)+", query, re.I):
            continue
        intent = str(raw.get("search_intent") or raw.get("intent") or "").strip()
        if intent not in SEARCH_INTENTS:
            intent = "search_intent"
        output = {
            "query": query,
            "search_intent": intent,
            "reason": clean_search_text(str(raw.get("reason") or "AI 拆解出的候选搜索问题，经脚本校验后采用。")),
            "evidence_axis": str(raw.get("evidence_axis") or "").strip(),
            "evidence_role": str(raw.get("evidence_role") or "primary").strip() or "primary",
            "query_group": str(raw.get("query_group") or "").strip(),
            "query_group_label": str(raw.get("query_group_label") or "").strip(),
            "query_source": "ai_draft",
            "planner_source": "ai_search_plan",
        }
        if output["evidence_axis"] not in EVIDENCE_AXES:
            output["evidence_axis"] = infer_evidence_axis(output)
        if output["query_group"] not in QUERY_GROUP_LABELS:
            output["query_group"] = infer_query_group(output)
        if not output["query_group_label"]:
            output["query_group_label"] = QUERY_GROUP_LABELS.get(output["query_group"], output["query_group"])
        for key in ["include_domains", "exclude_domains"]:
            domains = raw.get(key)
            if isinstance(domains, list):
                output[key] = [clean_search_text(str(item)) for item in domains if clean_search_text(str(item))][:8]
        if raw.get("time_range") in {"day", "week", "month", "year"}:
            output["time_range"] = raw.get("time_range")
        try:
            max_results = int(raw.get("max_results", 0) or 0)
        except (TypeError, ValueError):
            max_results = 0
        if max_results:
            output["max_results"] = min(max(max_results, 3), 8)
        sanitized.append(output)
        if len(sanitized) >= limit:
            break
    return sanitize_search_plan(sanitized)


def merge_ai_plan_with_fallback(ai_plan: list, fallback_plan: list, limit: int = DEFAULT_SEARCH_PLAN_LIMIT) -> list:
    if not ai_plan:
        return dedupe_plan(fallback_plan, limit=limit)
    output = []
    seen_queries = set()
    covered_axes = set()

    for item in ai_plan:
        query = item.get("query", "")
        if not query or query in seen_queries:
            continue
        seen_queries.add(query)
        axis = item.get("evidence_axis", "")
        if axis:
            covered_axes.add(axis)
        output.append(item)
        if len(output) >= limit:
            return output

    for item in fallback_plan:
        query = item.get("query", "")
        axis = item.get("evidence_axis", "")
        if not query or query in seen_queries:
            continue
        # Prefer fallback queries that cover an evidence axis the AI draft missed.
        if axis and axis in covered_axes and len(output) >= max(5, len(ai_plan)):
            continue
        seen_queries.add(query)
        if axis:
            covered_axes.add(axis)
        output.append(item)
        if len(output) >= limit:
            break

    if len(output) < min(6, limit):
        for item in fallback_plan:
            query = item.get("query", "")
            if query and query not in seen_queries:
                seen_queries.add(query)
                output.append(item)
                if len(output) >= limit:
                    break
    return output


def infer_query_group(item: dict) -> str:
    intent = str(item.get("search_intent") or "")
    axis = str(item.get("evidence_axis") or "")
    text = " ".join([str(item.get("query") or ""), str(item.get("reason") or "")]).lower()
    cjk_text = re.sub(r"\s+", "", " ".join([str(item.get("query") or ""), str(item.get("reason") or "")]))

    if intent == "expert_signal" or axis == "expert":
        return "expert_signal"
    if any(token in text for token in ["vercel", "render", "railway", "fly.io", "cloudflare workers", "server pricing", "hosting pricing", "deployment pricing"]) or any(token in cjk_text for token in ["服务器价格", "部署价格", "托管价格"]):
        return "official_infra_pricing"
    if any(token in text for token in ["cloudflare stream", "mux", "video storage", "video bandwidth", "cdn pricing", "media storage"]) or any(token in cjk_text for token in ["视频存储", "视频带宽", "媒体存储", "CDN价格"]):
        return "media_storage_pricing"
    if any(token in text for token in ["supabase", "neon", "postgres pricing", "database pricing", "storage pricing", "r2 pricing", "s3 pricing"]) or any(token in cjk_text for token in ["数据库价格", "存储价格"]):
        return "database_storage_pricing"
    if any(token in text for token in ["replicate pricing", "fal.ai", "runpod", "modal gpu", "gpu serverless", "inference pricing"]) or any(token in cjk_text for token in ["GPU价格", "推理平台价格"]):
        return "gpu_runtime_pricing"
    if any(token in text for token in ["openai", "anthropic", "gemini", "veo", "runway", "kling", "luma", "pika", "model api pricing", "token pricing", "embedding pricing"]) or any(token in cjk_text for token in ["模型价格", "TOKEN价格", "API价格", "视频生成价格"]):
        return "model_api_pricing"
    if any(token in text for token in ["resend", "postmark", "sendgrid", "email api pricing", "transactional email pricing"]) or any(token in cjk_text for token in ["邮件价格", "通知价格"]):
        return "email_pricing"
    if any(token in text for token in ["apify", "browserless", "firecrawl", "proxy pricing", "web scraping pricing", "scraping cost"]) or any(token in cjk_text for token in ["抓取价格", "代理价格", "爬虫价格"]):
        return "scraping_pricing"
    if any(token in text for token in ["posthog", "sentry", "logtail", "axiom", "analytics pricing", "monitoring pricing", "observability pricing"]) or any(token in cjk_text for token in ["监控价格", "分析价格", "日志价格"]):
        return "analytics_monitoring_pricing"
    if any(token in text for token in ["roi", "ltv", "cac", "arpu", "arr", "mrr", "payback", "break-even", "breakeven", "conversion rate", "churn", "retention", "revenue benchmark", "profit margin", "gross margin"]) or any(token in cjk_text for token in ["ROI", "LTV", "CAC", "ARPU", "回本", "保本", "转化率", "留存", "续费", "流失", "收入基准", "毛利", "毛利率", "行业平均收益"]):
        return "commercial_benchmark"
    if any(token in text for token in ["pricing", "price", "freemium", "subscription", "credits", "paid plans", "upgrade", "monetization", "business model", "commercial license"]) or any(token in cjk_text for token in ["定价", "付费", "商业模式", "免费额度", "会员", "套餐", "复购", "升级"]):
        return "pricing"
    if any(token in text for token in ["complaints", "reviews", "reddit", "product hunt", "user questions", "unmet needs", "alternatives workflow quality"]) or any(token in cjk_text for token in ["用户痛点", "投诉", "差评", "评价", "抱怨", "踩坑", "未满足"]):
        return "user_feedback"
    if any(token in text for token in ["seo", "keyword", "search intent", "serp", "landing page", "landing pages", "programmatic", "traffic", "tutorial", "internal links", "search volume"]) or any(token in cjk_text for token in ["SEO", "关键词", "搜索需求", "页面", "榜单", "攻略", "内容机会", "流量"]):
        return "growth_seo"
    if any(token in text for token in ["onboarding", "first use", "homepage", "signup", "trial conversion", "product demo", "workflow output", "recommendations", "checklist", "action plan"]) or any(token in cjk_text for token in ["首页", "注册", "首次体验", "用户路径", "产品路径", "流程", "输出形态"]):
        return "product_flow"
    if any(token in text for token in ["features", "feature", "integrations", "capability", "capabilities", "use cases", "templates", "workflow", "outputs", "limitations"]) or any(token in cjk_text for token in ["功能", "能力", "集成", "使用场景", "模板", "工作流", "服务能力"]):
        return "feature_capability"
    if any(token in text for token in ["policy", "legal", "copyright", "compliance", "risk", "regulation"]) or any(token in cjk_text for token in ["政策", "合规", "风险", "版权"]):
        return "risk_policy"
    if any(token in text for token in ["api", "cost", "commercial use", "limits", "availability", "official api", "documentation"]) or any(token in cjk_text for token in ["API", "成本", "商用", "授权", "可产品化"]):
        return "feasibility_cost" if intent == "api_feasibility" or "cost" in text or "成本" in cjk_text else "official_capability"
    if any(token in text for token in ["market size", "market trends", "trend", "growth", "funding", "launches", "latest", "news", "partnerships", "acquisitions"]) or any(token in cjk_text for token in ["市场规模", "趋势", "行业", "动态", "融资", "合作", "新闻"]):
        return "market_signal"
    if any(token in text for token in ["best ", "comparison", "competitors", "alternatives", "positioning"]) or any(token in cjk_text for token in ["竞品", "对标", "品牌", "替代方案", "定位"]):
        return "competitor_pool"
    if axis == "market":
        return "market_signal"
    if axis == "competition":
        return "competitor_pool"
    if axis == "user_pain":
        return "user_feedback"
    if axis == "distribution":
        return "growth_seo"
    if axis == "official":
        return "official_capability"
    if axis == "unit_economics":
        return "cost_structure"
    if axis == "risk":
        return "risk_policy"
    return "segment_map"


def infer_evidence_axis(item: dict) -> str:
    intent = str(item.get("search_intent") or "")
    query = " ".join([str(item.get("query") or ""), str(item.get("reason") or "")]).lower()
    if intent == "expert_signal":
        return "expert"
    if intent in {"official_capability", "api_feasibility"}:
        if any(token in query for token in ["pricing", "price", "cost", "成本", "定价", "credits"]):
            return "unit_economics"
        if any(token in query for token in ["policy", "legal", "copyright", "compliance", "risk", "合规", "风险", "版权"]):
            return "risk"
        return "official"
    if intent == "user_discussion":
        return "user_pain"
    if intent == "seo_page_type" or any(token in query for token in ["seo", "keyword", "search intent", "关键词", "页面", "traffic", "serp"]):
        return "distribution"
    if intent == "competitor_and_monetization":
        if any(token in query for token in ["market", "trend", "growth", "size", "规模", "趋势"]):
            return "market"
        return "competition"
    if intent == "search_intent":
        return "distribution"
    return ""


def is_latest_news_query(text: str) -> bool:
    return bool(re.search(r"最新.*(新闻|趋势|动态)|(?:新闻|趋势|动态).*最新|latest.*(?:news|trend)|(?:news|trend).*latest|today.*news|news.*today", text, re.I))


def is_reference_site_query(text: str) -> bool:
    return semantic_router.is_reference_collection_query(text)


def normalize_news_topic(value: str) -> str:
    if "ai" in value.lower() or "人工智能" in value or re.search(r"artificial intelligence", value, re.I):
        return "AI"
    topic = extract_topic(value)
    topic = re.sub(r"(最新|今日|今天|新闻|动态|趋势|today|latest|news|trends?)", " ", topic, flags=re.I)
    topic = re.sub(r"(^|\s)的(\s|$)", " ", topic)
    topic = re.sub(r"\s+", " ", topic).strip()
    return topic or extract_topic(value)


def infer_latest_news_intent_type(confirmed_intent: str) -> str:
    intent_lc = confirmed_intent.lower()
    product_like = any(token in confirmed_intent for token in ["工具站", "产品", "小工具", "API", "开发"]) or "tool" in intent_lc or "product" in intent_lc
    seo_like = any(token in confirmed_intent for token in ["SEO", "选题", "内容", "关键词", "长尾"]) or "seo" in intent_lc or "content" in intent_lc
    if product_like and seo_like:
        return "product_and_seo_opportunity"
    if product_like:
        return "tool_or_product_opportunity"
    if seo_like:
        return "seo_or_content_opportunity"
    if any(token in confirmed_intent for token in ["竞品", "竞争", "行业", "市场"]) or "competitor" in intent_lc or "market" in intent_lc:
        return "competitor_or_market_signal"
    return "news_brief"


def infer_reference_intent_type(confirmed_intent: str) -> str:
    intent_lc = confirmed_intent.lower()
    product_experience = any(token in confirmed_intent for token in ["产品体验", "新用户", "首页", "模板", "生成流程", "试用门槛"]) or "onboarding" in intent_lc
    business_model = any(token in confirmed_intent for token in ["付费", "商业模式", "免费额度", "积分", "订阅", "水印", "商用授权"]) or "pricing" in intent_lc
    seo_structure = any(token in confirmed_intent for token in ["SEO", "内容结构", "搜索流量", "关键词", "内链"]) or "seo" in intent_lc
    model_function = any(token in confirmed_intent for token in ["模型", "功能", "文生视频", "图生视频", "视频编辑", "工作流"]) or "feature" in intent_lc
    matched = [product_experience, business_model, seo_structure, model_function]
    if sum(1 for item in matched if item) > 1:
        return "reference_multi_dimension"
    if product_experience:
        return "reference_product_experience"
    if business_model:
        return "reference_business_model"
    if seo_structure:
        return "reference_seo_content_structure"
    if model_function:
        return "reference_model_function_capability"
    return "other"


def annotate_plan_item(item: dict) -> dict:
    output = dict(item)
    if output.get("query_group") not in QUERY_GROUP_LABELS:
        output["query_group"] = infer_query_group(output)
    if not output.get("query_group_label"):
        output["query_group_label"] = QUERY_GROUP_LABELS.get(output["query_group"], output["query_group"])
    if not output.get("query_source"):
        output["query_source"] = "ai_draft" if output.get("planner_source") == "ai_search_plan" else "template"
    return output


def dedupe_plan(plan: list, limit: int = DEFAULT_SEARCH_PLAN_LIMIT, group_caps: dict | None = None) -> list:
    group_caps = group_caps or QUERY_GROUP_CAPS
    seen = set()
    unique_items = []
    for item in plan:
        query = item.get("query", "") if isinstance(item, dict) else ""
        if not query or query in seen:
            continue
        seen.add(query)
        unique_items.append(annotate_plan_item(item))

    if len(unique_items) <= limit:
        return unique_items

    output = []
    output_queries = set()
    group_counts = {}

    def can_add(item: dict, coverage_pass: bool = False) -> bool:
        if len(output) >= limit:
            return False
        query = item.get("query", "")
        if query in output_queries:
            return False
        group = item.get("query_group", "")
        cap = group_caps.get(group)
        if cap is not None and group_counts.get(group, 0) >= cap:
            return False
        if coverage_pass and group_counts.get(group, 0):
            return False
        return True

    def add_item(item: dict) -> None:
        output.append(item)
        output_queries.add(item.get("query", ""))
        group = item.get("query_group", "")
        group_counts[group] = group_counts.get(group, 0) + 1

    # First pass: preserve coverage across all relevant modules before allowing
    # repeated queries from earlier groups to consume the whole plan budget.
    for item in unique_items:
        if can_add(item, coverage_pass=True):
            add_item(item)

    for item in unique_items:
        if can_add(item):
            add_item(item)

    return output[:limit]


def evidence_query(query: str, search_intent: str, reason: str, evidence_axis: str, evidence_role: str = "primary", **kwargs) -> dict:
    output = {
        "query": query,
        "search_intent": search_intent,
        "reason": reason,
        "evidence_axis": evidence_axis,
        "evidence_role": evidence_role,
    }
    output.update(kwargs)
    return output


COST_STRUCTURE_QUERY_GROUPS = {
    "official_infra_pricing",
    "database_storage_pricing",
    "media_storage_pricing",
    "model_api_pricing",
    "gpu_runtime_pricing",
    "email_pricing",
    "scraping_pricing",
    "analytics_monitoring_pricing",
}


def is_video_cost_topic(topic: str) -> bool:
    compact = re.sub(r"\s+", "", clean_search_text(topic)).lower()
    return any(token in compact for token in ["video", "视频", "短视频", "image-to-video", "text-to-video", "veo", "runway", "kling", "luma", "pika"])


def is_image_cost_topic(topic: str) -> bool:
    compact = re.sub(r"\s+", "", clean_search_text(topic)).lower()
    return any(token in compact for token in ["image", "图片", "图像", "绘图", "生图", "midjourney", "imagen", "flux"])


def cost_structure_queries(topic: str = "") -> list[dict]:
    topic_text = search_query_topic(topic) if topic else ""
    context = f" for {topic_text}" if topic_text and topic_text != "AI tools" else ""
    if is_video_cost_topic(topic_text or topic):
        return [
            evidence_query(
                "Google Veo Runway Kling Luma Pika video generation API pricing official",
                "official_capability",
                "AI 视频站成本/价格线索：优先收集视频生成模型/API 的按秒、按 credit 或按任务官方价格，这是主导可变成本。",
                "unit_economics",
                query_group="model_api_pricing",
                query_group_label=QUERY_GROUP_LABELS["model_api_pricing"],
                cost_category="variable_task_cost",
                max_results=6,
            ),
            evidence_query(
                "Cloudflare Stream Mux Cloudflare R2 video storage bandwidth CDN pricing official",
                "official_capability",
                "AI 视频站成本/价格线索：收集视频文件存储、带宽、转码、CDN 和播放相关价格。",
                "unit_economics",
                query_group="media_storage_pricing",
                query_group_label=QUERY_GROUP_LABELS["media_storage_pricing"],
                cost_category="variable_task_cost",
                max_results=6,
            ),
            evidence_query(
                "Replicate fal.ai RunPod Modal GPU serverless inference pricing official video generation",
                "official_capability",
                "AI 视频站成本/价格线索：如果不用托管视频 API，需比较 GPU/serverless inference 的推理成本。",
                "unit_economics",
                query_group="gpu_runtime_pricing",
                query_group_label=QUERY_GROUP_LABELS["gpu_runtime_pricing"],
                cost_category="variable_task_cost",
                max_results=6,
            ),
            evidence_query(
                "AI video generation SaaS pricing credits subscription Runway Kling Luma Pika",
                "competitor_and_monetization",
                "AI 视频站成本/价格线索：查竞品按 credits、秒数、订阅额度打包方式，用于判断价格锚点和毛利压力。",
                "unit_economics",
                query_group="pricing",
                query_group_label=QUERY_GROUP_LABELS["pricing"],
                cost_category="revenue_benchmark",
                max_results=6,
            ),
        ]
    if is_image_cost_topic(topic_text or topic):
        return [
            evidence_query(
                "OpenAI image generation Google Imagen Stability AI Replicate fal.ai pricing official",
                "official_capability",
                "AI 生图产品成本/价格线索：收集图片生成 API、模型调用和推理平台官方价格。",
                "unit_economics",
                query_group="model_api_pricing",
                query_group_label=QUERY_GROUP_LABELS["model_api_pricing"],
                cost_category="variable_task_cost",
                max_results=6,
            ),
            evidence_query(
                "Cloudflare R2 S3 image storage bandwidth CDN pricing official",
                "official_capability",
                "AI 生图产品成本/价格线索：收集图片存储、带宽和 CDN 价格。",
                "unit_economics",
                query_group="media_storage_pricing",
                query_group_label=QUERY_GROUP_LABELS["media_storage_pricing"],
                cost_category="variable_task_cost",
                max_results=5,
            ),
            evidence_query(
                "AI image generator pricing credits subscription Midjourney Leonardo Canva Adobe Firefly",
                "competitor_and_monetization",
                "AI 生图产品成本/价格线索：查竞品按 credits、订阅额度和商用授权打包方式。",
                "unit_economics",
                query_group="pricing",
                query_group_label=QUERY_GROUP_LABELS["pricing"],
                cost_category="revenue_benchmark",
                max_results=6,
            ),
        ]
    return [
        evidence_query(
            f"Vercel Cloudflare Workers Render Railway pricing official{context}",
            "official_capability",
            "成本/价格线索：收集部署、服务器和边缘函数的官方价格，用于月固定成本估算。",
            "unit_economics",
            query_group="official_infra_pricing",
            query_group_label=QUERY_GROUP_LABELS["official_infra_pricing"],
            cost_category="monthly_fixed_cost",
            max_results=5,
        ),
        evidence_query(
            f"Supabase Neon Cloudflare R2 database storage pricing official{context}",
            "official_capability",
            "成本/价格线索：收集数据库、对象存储、带宽和文件存储官方价格。",
            "unit_economics",
            query_group="database_storage_pricing",
            query_group_label=QUERY_GROUP_LABELS["database_storage_pricing"],
            cost_category="monthly_fixed_cost",
            max_results=5,
        ),
        evidence_query(
            f"OpenAI Anthropic Google Gemini API pricing official tokens{context}",
            "official_capability",
            "成本/价格线索：收集模型 API 和 token 官方价格，用于单次任务成本估算。",
            "unit_economics",
            query_group="model_api_pricing",
            query_group_label=QUERY_GROUP_LABELS["model_api_pricing"],
            cost_category="variable_task_cost",
            max_results=5,
        ),
        evidence_query(
            "Resend Postmark SendGrid transactional email pricing official",
            "official_capability",
            "成本/价格线索：收集邮件、通知和 waitlist 邮件发送的官方价格。",
            "unit_economics",
            query_group="email_pricing",
            query_group_label=QUERY_GROUP_LABELS["email_pricing"],
            cost_category="monthly_fixed_cost",
            max_results=5,
        ),
        evidence_query(
            "Apify Browserless Firecrawl proxy web scraping pricing official",
            "official_capability",
            "成本/价格线索：收集抓取、代理和浏览器自动化官方价格，用于评论分析、竞品监控等方向。",
            "unit_economics",
            query_group="scraping_pricing",
            query_group_label=QUERY_GROUP_LABELS["scraping_pricing"],
            cost_category="variable_task_cost",
            max_results=5,
        ),
        evidence_query(
            "PostHog Sentry Logtail Axiom monitoring analytics pricing official",
            "official_capability",
            "成本/价格线索：收集监控、分析、日志和错误追踪官方价格。",
            "unit_economics",
            query_group="analytics_monitoring_pricing",
            query_group_label=QUERY_GROUP_LABELS["analytics_monitoring_pricing"],
            cost_category="monthly_fixed_cost",
            max_results=5,
        ),
    ]


def is_ai_media_site_choice_query(value: str) -> bool:
    text = clean_search_text(value)
    compact = re.sub(r"\s+", "", text).lower()
    if "ai" not in compact and "人工智能" not in text:
        return False
    has_video = "视频" in compact or "video" in compact
    has_image = "图片" in compact or "图像" in compact or "image" in compact
    has_site_or_product = any(token in compact for token in ["站", "网站", "工具", "产品", "generator", "tool", "site", "app"])
    has_choice = any(token in compact for token in ["还是", "还是都做", "都做", "vs", "哪个", "哪边", "shouldibuild", "choose"])
    return has_video and has_image and has_site_or_product and has_choice


def plan_for_ai_media_site_choice() -> list:
    return [
        evidence_query(
            "AI video generator market size 2026 2033 CAGR report",
            "competitor_and_monetization",
            "确认 AI 视频生成市场规模、增长率和商业场景，用于判断视频侧上限。",
            "market",
            max_results=6,
        ),
        evidence_query(
            "AI image generator market size 2026 2034 CAGR report",
            "competitor_and_monetization",
            "确认 AI 图片生成市场规模、增长率和成熟度，用于判断图片侧基本盘。",
            "market",
            max_results=6,
        ),
        evidence_query(
            "Google Veo Imagen API pricing official documentation video image generation",
            "api_feasibility",
            "用官方定价比较视频按秒计费和图片按张计费的成本差异。",
            "unit_economics",
            include_domains=["ai.google.dev", "cloud.google.com"],
            max_results=6,
        ),
        evidence_query(
            "OpenAI image video generation API pricing official documentation Sora",
            "official_capability",
            "核验 OpenAI 图片/视频能力、定价、可用性和平台风险。",
            "official",
            include_domains=["openai.com", "platform.openai.com", "help.openai.com"],
            max_results=6,
        ),
        evidence_query(
            "generative AI copyright commercial use AI generated works official guidance 2026",
            "official_capability",
            "确认 AI 生成图片/视频站的版权、商用、政策和平台依赖风险。",
            "risk",
            include_domains=["copyright.gov", "commission.europa.eu", "ftc.gov", "ico.org.uk"],
            max_results=6,
        ),
        evidence_query(
            "a16z Top 100 Gen AI Consumer Apps 2026 image video creative tools",
            "competitor_and_monetization",
            "用消费级 AI 应用榜单判断通用图片工具是否商品化、视频/创意工具是否上升。",
            "competition",
            include_domains=["a16z.com"],
            max_results=6,
        ),
        evidence_query(
            "AI image to video ecommerce product video generator use cases pricing competitors",
            "seo_page_type",
            "判断“图片作为上游素材入口、视频作为增值层”的垂直工作流是否成立。",
            "distribution",
            max_results=6,
        ),
        evidence_query(
            "AI video generator user complaints credits watermarks failed generations reddit product hunt",
            "user_discussion",
            "查视频生成的真实用户抱怨：成本、失败率、水印、等待和退订风险。",
            "user_pain",
            max_results=6,
        ),
    ]


def is_tool_like_topic(topic: str, query_type: str = "", dimensions: list | None = None) -> bool:
    text = str(topic or "")
    dimensions = dimensions or []
    if "feature_capability" in dimensions:
        return True
    return bool(re.search(
        r"\b(AI|API|SaaS|SEO|CRM|App|app|PPT|Agent|Notion|GPT|OpenAI|Claude|Anthropic|Gemini|Midjourney|Runway|Kling|Pika|Luma)\b|工具|网站|站|平台|软件|插件|模型|生成|教程站|模板市场|数据分析|浏览器|助手|系统|小程序",
        text,
        re.I,
    ))


def search_query_topic(topic: str) -> str:
    text = clean_search_text(topic)
    compact = re.sub(r"\s+", "", text).lower()
    if "睡眠计算器" in compact:
        return "sleep calculator website"
    if "简历" in compact and ("生成器" in compact or "builder" in compact or "resume" in compact):
        return "online resume builder"
    if "ai" in compact or "人工智能" in text:
        if "seo" in compact and ("工具" in compact or "站" in compact or "产品" in compact or "tool" in compact):
            return "AI SEO tools"
        if ("辅助" in compact and "决策" in compact) or "决策支持" in compact or "decision-support" in compact or "decisionsupport" in compact:
            return "AI decision support tools"
        if ("决策" in compact and ("产品" in compact or "工具" in compact or "assistant" in compact)) or "decisionmaking" in compact:
            return "AI decision-making assistant"
        if "会议纪要" in compact or "会议记录" in compact or "meetingnotes" in compact or "meetingminutes" in compact:
            return "AI meeting notes tool"
        if "游戏" in compact and ("配乐" in compact or "音乐" in compact):
            return "AI game music generator"
        if "配乐" in compact or "音乐" in compact:
            return "AI music generator"
        has_image_topic = "图片" in compact or "图像" in compact or "生图" in compact or "image" in compact
        has_video_topic = "视频" in compact or "video" in compact
        if has_image_topic and has_video_topic:
            return "AI image and video generation tools"
        if has_video_topic:
            if "图生" in compact or "image" in compact:
                return "AI image to video generator"
            return "AI video generator"
        if has_image_topic:
            return "AI image generator"
        if "办公" in compact or "文档" in compact or "office" in compact or "document" in compact or "docs" in compact:
            return "AI document productivity tools"
        if "营销" in compact or "销售" in compact or "marketing" in compact or "sales" in compact or "crm" in compact:
            return "AI sales and marketing tools"
        if "开发" in compact or "建站" in compact or "代码" in compact or "编程" in compact or "coding" in compact or "developer" in compact or "websitebuilder" in compact:
            return "AI coding and website builder tools"
        if "教育" in compact or "学习" in compact or "education" in compact or "learning" in compact:
            return "AI education and learning tools"
        if "自动化" in compact or "工作流" in compact or "workflow" in compact or "automation" in compact:
            return "AI workflow automation tools"
        if "工具" in compact or "站" in compact or "产品" in compact or "tool" in compact:
            return "AI tools"
    return text


def quote_search_phrase(value: str) -> str:
    text = clean_search_text(value)
    if not text or text.startswith("\""):
        return text
    return f"\"{text}\"" if " " in text else text


def expert_signal_query(topic: str, tool_like: bool | None = None) -> dict:
    if tool_like is None:
        tool_like = is_tool_like_topic(topic)
    expert_group = ""
    if tool_like:
        query_topic = search_query_topic(topic)
        if query_topic in {"AI decision support tools", "AI decision-making assistant"}:
            query = f"{query_topic} founders interviews product strategy workflow use cases"
            expert_group = "辅助决策 AI 产品创始人和产品团队"
        else:
            query = f"{query_topic} founders product teams practitioners problems current solutions case studies"
            expert_group = f"{topic} 创始人、产品团队和实践者"
    else:
        query = f"{topic} 行业专家 创始人 从业者 大佬 关注问题 解决方案 案例"
        expert_group = f"{topic} 行业专家、创始人和从业者"
    return {
        "query": query,
        "search_intent": "expert_signal",
        "reason": "识别该领域真实产品的创始人、产品团队或一线实践者是谁，他们的产品是什么、怎么做、关注哪些关键问题。",
        "evidence_axis": "expert",
        "evidence_role": "supporting",
        "expert_group": expert_group,
    }


def with_expert_signal(plan: list, topic: str, tool_like: bool | None = None) -> list:
    return plan + [expert_signal_query(topic, tool_like)]


def plan_for_reference_sites(
    topic: str,
    confirmed_intent: str,
    confirmed_intent_type: str = "",
    dimensions: list | None = None,
    action_context: str = "",
) -> list:
    intent_type = confirmed_intent_type if confirmed_intent_type in REFERENCE_INTENT_TYPES else ""
    if not intent_type:
        intent_type = infer_reference_intent_type(confirmed_intent)
    dimensions = dimensions or []
    topic = topic or "reference products"
    tool_like = is_tool_like_topic(topic, "reference_collection", dimensions)
    subject = search_query_topic(topic) if tool_like else topic

    shared = [
        {
            "query": f"best {subject} comparison alternatives competitors",
            "search_intent": "competitor_and_monetization",
            "reason": "先确定哪些参考对象值得纳入比较池，避免只看单个平台或单个站点。",
        }
    ]

    product_experience = [
        {
            "query": f"{subject} product onboarding workflow first use examples",
            "search_intent": "user_discussion",
            "reason": "参考真实产品如何设计首页、首次使用、输入流程、输出形态和用户继续动作。",
        },
        {
            "query": f"{subject} user reviews complaints onboarding workflow alternatives",
            "search_intent": "competitor_and_monetization",
            "reason": "查用户对真实产品流程、结果质量、替代方案和使用阻力的反馈。",
        },
    ]

    business_model = [
        {
            "query": f"{subject} pricing freemium subscription credits commercial license",
            "search_intent": "competitor_and_monetization",
            "reason": "参考免费额度、订阅、积分包、导出限制、水印和商用授权。",
        },
        {
            "query": f"{subject} monetization business model paid plans limits",
            "search_intent": "competitor_and_monetization",
            "reason": "拆解同类产品如何设计付费转化、限制和商业模式。",
        },
    ]

    seo_structure = [
        {
            "query": f"{subject} SEO landing pages alternatives vs best tools",
            "search_intent": "seo_page_type",
            "reason": "参考首页关键词布局、工具页、榜单页、替代品页和对比页结构。",
        },
        {
            "query": f"{subject} keywords search intent comparison tutorial internal links",
            "search_intent": "search_intent",
            "reason": "参考内容入口、内链结构和可承接搜索流量的页面类型。",
        },
    ]

    model_function = [
        {
            "query": f"{subject} features integrations workflow outputs limitations",
            "search_intent": "official_capability",
            "reason": "参考真实产品的核心功能、输入输出、工作流、能力边界和限制。",
        },
        {
            "query": f"{subject} product features use cases templates workflow",
            "search_intent": "competitor_and_monetization",
            "reason": "对比头部对象的功能矩阵、使用场景和功能包装方式。",
        },
    ]

    new_product_validation = [
        {
            "query": f"{subject} API cost commercial use limits product opportunity",
            "search_intent": "api_feasibility",
            "reason": "如果行动目的是从 0 做产品，先确认能力、成本、授权和可产品化边界。",
        },
        {
            "query": f"{subject} unmet needs complaints alternatives reddit product hunt",
            "search_intent": "user_discussion",
            "reason": "寻找用户抱怨、替代品和未满足需求，判断是否有小范围验证切口。",
        },
    ]

    existing_product_conversion = [
        {
            "query": f"{subject} pricing page signup trial conversion free plan upgrade",
            "search_intent": "competitor_and_monetization",
            "reason": "如果行动目的是优化已有产品转化，重点查注册、试用、免费额度、定价页和升级触发点。",
        },
        {
            "query": f"{subject} homepage value proposition onboarding conversion examples",
            "search_intent": "user_discussion",
            "reason": "参考首页价值表达、新用户路径和降低转化阻力的设计。",
        },
    ]

    seo_growth = [
        {
            "query": f"{subject} search volume keyword difficulty alternatives comparison",
            "search_intent": "search_intent",
            "reason": "如果行动目的是获取新流量，重点查关键词、搜索意图和页面切口。",
        },
        {
            "query": f"{subject} programmatic SEO landing pages best alternatives vs",
            "search_intent": "seo_page_type",
            "reason": "判断适合做榜单页、替代品页、对比页、教程页还是工具页。",
        },
    ]

    market_watch = [
        {
            "query": f"{subject} market trends competitors positioning funding launches",
            "search_intent": "competitor_and_monetization",
            "reason": "如果行动目的是行业观察，重点查头部对象、定位差异和市场变化。",
        }
    ]

    reference_teardown = [
        {
            "query": f"{subject} founders interviews product strategy workflow use cases",
            "search_intent": "expert_signal",
            "reason": "优先查真实辅助决策类 AI 产品创始人或产品团队的访谈、发布说明和产品做法。",
            "evidence_axis": "expert",
            "evidence_role": "supporting",
            "expert_group": f"{topic} 创始人和产品团队",
        },
        {
            "query": f"{subject} product demo workflow output recommendations checklist action plan",
            "search_intent": "official_capability",
            "reason": "拆真实产品如何把输入、分析、建议、checklist、方案对比和下一步动作串起来。",
            "evidence_axis": "official",
        },
        {
            "query": f"{subject} user reviews complaints alternatives workflow quality",
            "search_intent": "user_discussion",
            "reason": "查用户为什么继续用、为什么流失，以及他们对结果质量和工作流的真实反馈。",
            "evidence_axis": "user_pain",
        },
    ]

    if not tool_like:
        shared = [
            {
                "query": f"{topic} 品牌 案例 竞品 对标 定位",
                "search_intent": "competitor_and_monetization",
                "reason": "先确定哪些参考对象值得纳入比较池，避免只看单个品牌或单个案例。",
            }
        ]
        product_experience = [
            {
                "query": f"{topic} 用户体验 服务流程 首次体验 案例",
                "search_intent": "user_discussion",
                "reason": "参考服务流程、首次体验、触点设计和降低用户决策阻力的做法。",
            },
            {
                "query": f"{topic} 用户评价 投诉 差评 痛点",
                "search_intent": "user_discussion",
                "reason": "查用户真实反馈，识别体验阻力、信任问题和未满足需求。",
            },
        ]
        business_model = [
            {
                "query": f"{topic} 定价 会员 复购 渠道 商业模式",
                "search_intent": "competitor_and_monetization",
                "reason": "参考定价、会员、复购、渠道和商业模式。",
            },
            {
                "query": f"{topic} 收入模式 成本 毛利 加盟 佣金",
                "search_intent": "competitor_and_monetization",
                "reason": "拆解收入来源、成本结构、毛利空间和合作/佣金机制。",
            },
        ]
        seo_structure = [
            {
                "query": f"{topic} SEO 关键词 搜索需求 页面 内容",
                "search_intent": "search_intent",
                "reason": "判断是否存在搜索需求，以及适合承接流量的页面和内容类型。",
            },
            {
                "query": f"{topic} 榜单 对比 推荐 攻略 页面",
                "search_intent": "seo_page_type",
                "reason": "判断适合做榜单页、对比页、推荐页、攻略页还是本地落地页。",
            },
        ]
        model_function = [
            {
                "query": f"{topic} 服务能力 流程 供应链 运营 案例",
                "search_intent": "official_capability",
                "reason": "参考服务能力、运营流程、供应链和交付边界。",
            },
            {
                "query": f"{topic} 产品 服务 项目 套餐 差异化",
                "search_intent": "competitor_and_monetization",
                "reason": "对比参考对象的服务项目、套餐设计和差异化包装方式。",
            },
        ]
        new_product_validation = [
            {
                "query": f"{topic} 市场规模 趋势 机会 需求",
                "search_intent": "search_intent",
                "reason": "如果行动目的是从 0 做，先确认市场需求、增长趋势和机会窗口。",
            },
            {
                "query": f"{topic} 用户痛点 投诉 替代方案 小红书 知乎",
                "search_intent": "user_discussion",
                "reason": "寻找用户抱怨、替代方案和未满足需求，判断是否有小范围验证切口。",
            },
        ]
        existing_product_conversion = [
            {
                "query": f"{topic} 新客 转化 会员 复购 定价 活动",
                "search_intent": "competitor_and_monetization",
                "reason": "如果行动目的是优化已有业务，重点查新客转化、会员、复购、定价和活动机制。",
            },
            {
                "query": f"{topic} 用户体验 信任 服务流程 转化 案例",
                "search_intent": "user_discussion",
                "reason": "参考用户体验、信任建立、服务流程和降低转化阻力的做法。",
            },
        ]
        seo_growth = [
            {
                "query": f"{topic} 关键词 搜索需求 内容机会",
                "search_intent": "search_intent",
                "reason": "如果行动目的是获取新流量，重点查关键词、搜索意图和内容切口。",
            },
            {
                "query": f"{topic} SEO 页面 榜单 对比 攻略",
                "search_intent": "seo_page_type",
                "reason": "判断适合做榜单页、对比页、攻略页还是本地服务页。",
            },
        ]
        market_watch = [
            {
                "query": f"{topic} 行业趋势 竞品 政策 风险",
                "search_intent": "competitor_and_monetization",
                "reason": "如果行动目的是行业观察，重点查趋势、竞品变化、政策和风险。",
            }
        ]

    plan = list(shared)
    plan.append(expert_signal_query(topic, tool_like))
    if action_context == "new_product_validation":
        plan.extend(new_product_validation)
    elif action_context == "existing_product_conversion":
        plan.extend(existing_product_conversion)
    elif action_context == "seo_growth":
        plan.extend(seo_growth)
    elif action_context == "market_watch":
        plan.extend(market_watch)
    elif action_context == "reference_teardown":
        plan.extend(reference_teardown)

    if intent_type == "reference_product_experience":
        return dedupe_plan(plan + product_experience)
    if intent_type == "reference_business_model":
        return dedupe_plan(plan + business_model)
    if intent_type == "reference_seo_content_structure":
        return dedupe_plan(plan + seo_structure)
    if intent_type == "reference_model_function_capability":
        return dedupe_plan(plan + model_function)

    if intent_type == "reference_multi_dimension":
        selected_groups = []
        intent_text = confirmed_intent.lower()
        if "product_experience" in dimensions or any(token in confirmed_intent for token in ["产品体验", "新用户", "首页", "模板", "生成流程", "试用门槛"]) or "onboarding" in intent_text:
            selected_groups.extend(product_experience)
        if "business_model" in dimensions or any(token in confirmed_intent for token in ["付费", "商业模式", "免费额度", "积分", "订阅", "水印", "商用授权"]) or "pricing" in intent_text:
            selected_groups.extend(business_model)
        if "seo_content_structure" in dimensions or action_context == "seo_growth" or any(token in confirmed_intent for token in ["SEO", "内容结构", "搜索流量", "关键词", "内链"]) or "seo" in intent_text:
            selected_groups.extend(seo_structure)
        if "feature_capability" in dimensions or any(token in confirmed_intent for token in ["模型", "功能", "文生视频", "图生视频", "视频编辑", "工作流"]) or "feature" in intent_text:
            selected_groups.extend(model_function)

        if selected_groups:
            return dedupe_plan(plan + selected_groups)

    return dedupe_plan(plan + product_experience[:1] + business_model[:1] + seo_structure[:1] + model_function[:1])


def plan_for_latest_news(topic: str, confirmed_intent: str, confirmed_intent_type: str = "") -> list:
    topic_lc = topic.lower()
    intent_type = confirmed_intent_type if confirmed_intent_type in LATEST_NEWS_INTENT_TYPES else ""
    if not intent_type:
        intent_type = infer_latest_news_intent_type(confirmed_intent)
    is_ai_topic = topic_lc in {"ai", "artificial intelligence"} or bool(re.search(r"\bAI\b|人工智能|artificial intelligence", topic, re.I))
    if not is_ai_topic:
        if intent_type == "seo_or_content_opportunity":
            return with_expert_signal([
                {
                    "query": f"{topic} 最新动态 关键词 内容机会",
                    "search_intent": "search_intent",
                    "reason": "围绕已确认的 SEO/内容选题意图，查最近是否出现可承接搜索需求的新变化。",
                    "topic": "news",
                    "time_range": "week",
                    "days": 7
                },
                {
                    "query": f"{topic} 攻略 对比 榜单 搜索需求",
                    "search_intent": "seo_page_type",
                    "reason": "识别适合做攻略页、榜单页、对比页或专题页的页面类型。",
                    "topic": "news",
                    "time_range": "week",
                    "days": 7
                },
                {
                    "query": f"{topic} 用户问题 讨论 投诉 痛点",
                    "search_intent": "user_discussion",
                    "reason": "寻找用户真实问题和搜索语言，避免只追热点。",
                    "topic": "news",
                    "time_range": "week",
                    "days": 7
                }
            ], topic, tool_like=False)
        if intent_type == "competitor_or_market_signal":
            return with_expert_signal([
                {
                    "query": f"{topic} 最新动态 行业趋势 竞品",
                    "search_intent": "competitor_and_monetization",
                    "reason": "围绕已确认的竞品/行业信号意图，查市场、竞品和定位变化。",
                    "topic": "news",
                    "time_range": "week",
                    "days": 7
                },
                {
                    "query": f"{topic} 政策 风险 合规 最新",
                    "search_intent": "official_capability",
                    "reason": "覆盖可能影响方向判断的政策、合规和风险变化。",
                    "topic": "news",
                    "time_range": "week",
                    "days": 7
                }
            ], topic, tool_like=False)
        return with_expert_signal([
            {
                "query": f"{topic} 最新动态 行业趋势 机会",
                "search_intent": "search_intent",
                "reason": "围绕用户确认后的资讯或机会意图，抓取最近最可能改变关注优先级的公开信息。",
                "topic": "news",
                "time_range": "week",
                "days": 7
            },
            {
                "query": f"{topic} 竞品 品牌 公司 融资 合作",
                "search_intent": "competitor_and_monetization",
                "reason": "查找竞品、品牌、公司、融资和合作动态，判断市场结构变化。",
                "topic": "news",
                "time_range": "week",
                "days": 7
            },
            {
                "query": f"{topic} 用户需求 痛点 讨论",
                "search_intent": "user_discussion",
                "reason": "识别最近用户需求、痛点和讨论热度。",
                "topic": "news",
                "time_range": "week",
                "days": 7
            }
        ], topic, tool_like=False)
    topic_prefix = "" if topic_lc in {"ai", "artificial intelligence"} else f"{topic} "
    primary_query = "AI news today major announcements model releases"
    if topic_lc not in {"ai", "artificial intelligence"}:
        primary_query = f"{topic} AI news today major announcements model releases"

    if intent_type == "tool_or_product_opportunity":
        return with_expert_signal([
            {
                "query": f"{topic_prefix}OpenAI Google Anthropic AI API model release developer platform 2026",
                "search_intent": "api_feasibility",
                "reason": "围绕已确认的工具站/产品机会意图，查最近可被开发者接入或产品化的新能力。",
                "include_domains": ["openai.com", "developers.googleblog.com", "ai.google.dev", "anthropic.com", "microsoft.com", "meta.com"],
                "topic": "news",
                "time_range": "day",
                "days": 1
            },
            {
                "query": "new AI API model releases developers official announcements 2026",
                "search_intent": "official_capability",
                "reason": "确认新模型、新 API 或新平台能力是否真实可用。",
                "include_domains": ["openai.com", "developers.googleblog.com", "ai.google.dev", "anthropic.com", "microsoft.com", "meta.com"],
                "topic": "news",
                "time_range": "day",
                "days": 1
            },
            {
                "query": "AI tool launch user complaints unmet needs reddit product hunt this week",
                "search_intent": "user_discussion",
                "reason": "寻找用户抱怨、替代方案和未满足需求，判断是否值得 probe。",
                "topic": "news",
                "time_range": "week",
                "days": 7
            },
            {
                "query": "AI tools alternatives pricing competitors this week",
                "search_intent": "competitor_and_monetization",
                "reason": "确认竞品密度、变现入口和差异化空间。",
                "topic": "news",
                "time_range": "week",
                "days": 7
            }
        ], topic, tool_like=True)

    if intent_type == "product_and_seo_opportunity":
        return with_expert_signal([
            {
                "query": f"{topic_prefix}AI API launch developer tools product opportunity today",
                "search_intent": "api_feasibility",
                "reason": "围绕已确认的产品机会意图，查最近可被开发者接入或产品化的新能力。",
                "topic": "news",
                "time_range": "day",
                "days": 1
            },
            {
                "query": "new AI tools API launches model releases developers today",
                "search_intent": "official_capability",
                "reason": "确认新模型、新 API 或新平台能力是否真实可用。",
                "topic": "news",
                "time_range": "day",
                "days": 1
            },
            {
                "query": f"{topic_prefix}AI news today model launch tutorial comparison alternatives",
                "search_intent": "search_intent",
                "reason": "围绕已确认的 SEO/内容机会意图，查能形成教程、对比、替代品或专题页的新闻。",
                "topic": "news",
                "time_range": "day",
                "days": 1
            },
            {
                "query": "AI product launch user questions reddit how to use alternatives this week",
                "search_intent": "user_discussion",
                "reason": "寻找用户真实问题、搜索语言和未满足需求，判断是否值得做页面或小范围验证。",
                "topic": "news",
                "time_range": "week",
                "days": 7
            },
            {
                "query": "AI tools alternatives pricing competitors this week",
                "search_intent": "competitor_and_monetization",
                "reason": "确认竞品密度、变现入口和差异化空间，避免只追热点。",
                "topic": "news",
                "time_range": "week",
                "days": 7
            }
        ], topic, tool_like=True)

    if intent_type == "seo_or_content_opportunity":
        return with_expert_signal([
            {
                "query": f"{topic_prefix}AI news today model launch tutorial comparison alternatives",
                "search_intent": "search_intent",
                "reason": "围绕已确认的 SEO/内容选题意图，查能形成教程、对比、替代品或专题页的新闻。",
                "topic": "news",
                "time_range": "day",
                "days": 1
            },
            {
                "query": "new AI model API launch tutorial how to use comparison this week",
                "search_intent": "seo_page_type",
                "reason": "识别适合做教程页、榜单页、替代品页或对比页的页面类型。",
                "topic": "news",
                "time_range": "week",
                "days": 7
            },
            {
                "query": "AI product launch user questions reddit how to use alternatives this week",
                "search_intent": "user_discussion",
                "reason": "寻找用户真实问题和搜索语言，避免只追热点。",
                "topic": "news",
                "time_range": "week",
                "days": 7
            }
        ], topic, tool_like=True)

    if intent_type == "competitor_or_market_signal":
        return with_expert_signal([
            {
                "query": "AI company product launches partnerships acquisitions funding today",
                "search_intent": "competitor_and_monetization",
                "reason": "围绕已确认的竞品/行业信号意图，查公司、产品、融资和并购变化。",
                "topic": "news",
                "time_range": "day",
                "days": 1
            },
            {
                "query": "OpenAI Google Anthropic Microsoft Meta Nvidia AI business news this week",
                "search_intent": "official_capability",
                "reason": "覆盖主要平台和供应商的能力、商业化和生态变化。",
                "topic": "news",
                "time_range": "week",
                "days": 7
            }
        ], topic, tool_like=True)

    return with_expert_signal([
        {
            "query": primary_query,
            "search_intent": "search_intent",
            "reason": "围绕用户确认后的资讯速览意图，抓取最近一天最可能改变关注优先级的 AI 新闻。",
            "topic": "news",
            "time_range": "day",
            "days": 1
        },
        {
            "query": "OpenAI Google Anthropic Microsoft Meta Nvidia AI news today",
            "search_intent": "official_capability",
            "reason": "覆盖主要模型公司、平台和算力供应商的最新公告与能力变化。",
            "topic": "news",
            "time_range": "day",
            "days": 1
        },
        {
            "query": "AI regulation safety security artificial intelligence news this week",
            "search_intent": "user_discussion",
            "reason": "识别可能影响产品、合规、安全或舆论风险的政策与安全新闻。",
            "topic": "news",
            "time_range": "week",
            "days": 7
        },
        {
            "query": "AI startups funding acquisitions artificial intelligence business news this week",
            "search_intent": "competitor_and_monetization",
            "reason": "查找融资、并购、商业化和市场结构变化，判断哪些信号值得 watch/probe。",
            "topic": "news",
            "time_range": "week",
            "days": 7
        }
    ], topic, tool_like=True)


def plan_for_candidate_discovery(topic: str, action_context: str = "", dimensions: list | None = None) -> list:
    dimensions = dimensions or []
    query_topic = search_query_topic(topic)
    broad_ai = query_topic == "AI tools"
    topic_phrase = quote_search_phrase(query_topic)
    tool_topic = query_topic if re.search(r"\btools?\b", query_topic, re.I) else f"{query_topic} tools"
    segment_query = "AI product ideas vertical AI tools categories startups 2026" if broad_ai else f"{query_topic} product categories use cases startups 2026"
    best_tools_query = "best AI tools startups small business founders actually use 2026" if broad_ai else f"best {tool_topic} products 2026"
    product_hunt_query = "Product Hunt AI tools launches startups 2026" if broad_ai else f"Product Hunt {tool_topic} launches"
    directory_query = "AI tools directory categories trending tools use cases" if broad_ai else f"{tool_topic} directory categories"

    plan = [
        evidence_query(
            segment_query,
            "competitor_and_monetization",
            "候选池第一步：先找可拆分的赛道、产品形态和用户任务，避免直接跳到泛市场判断。",
            "competition",
            query_group="candidate_pool",
            query_group_label=QUERY_GROUP_LABELS["candidate_pool"],
            max_results=7,
        ),
        evidence_query(
            best_tools_query,
            "competitor_and_monetization",
            "找真实工具/产品清单，抽取代表产品、用户任务和可学习的产品形态。",
            "competition",
            query_group="candidate_pool",
            query_group_label=QUERY_GROUP_LABELS["candidate_pool"],
            max_results=7,
        ),
        evidence_query(
            product_hunt_query,
            "competitor_and_monetization",
            "用发布社区和新品榜补充近期真实工具，避免只看 SEO 内容农场或泛榜单。",
            "competition",
            query_group="candidate_pool",
            query_group_label=QUERY_GROUP_LABELS["candidate_pool"],
            max_results=7,
        ),
        evidence_query(
            directory_query,
            "seo_page_type",
            "从工具目录和分类页抽候选类别、页面形态和长尾 SEO 入口。",
            "distribution",
            query_group="segment_map",
            query_group_label=QUERY_GROUP_LABELS["segment_map"],
            max_results=6,
        ),
        evidence_query(
            f"{topic_phrase} alternatives competitors pricing",
            "competitor_and_monetization",
            "对候选池中出现的代表方向补充竞品密度、替代方案和价格锚点。",
            "competition",
            query_group="competitor_pool",
            query_group_label=QUERY_GROUP_LABELS["competitor_pool"],
            max_results=6,
        ),
        evidence_query(
            f"{topic_phrase} user reviews complaints reddit Product Hunt",
            "user_discussion",
            "找用户真实抱怨、替代方案和愿意反复使用的场景，筛掉只靠新鲜感的工具。",
            "user_pain",
            query_group="user_feedback",
            query_group_label=QUERY_GROUP_LABELS["user_feedback"],
            max_results=6,
        ),
        evidence_query(
            f"{topic_phrase} SEO landing pages generator template comparison",
            "seo_page_type",
            "判断候选方向是否能拆出工具页、模板页、对比页、榜单页或教程页。",
            "distribution",
            query_group="growth_seo",
            query_group_label=QUERY_GROUP_LABELS["growth_seo"],
            max_results=6,
        ),
        evidence_query(
            f"{topic_phrase} pricing free plan subscription credits business model",
            "competitor_and_monetization",
            "补充付费信号、免费额度、订阅/按量/积分等商业化方式。",
            "unit_economics",
            query_group="pricing",
            query_group_label=QUERY_GROUP_LABELS["pricing"],
            max_results=6,
        ),
        evidence_query(
            f"{topic_phrase} revenue benchmark conversion rate LTV CAC ARPU churn retention gross margin",
            "competitor_and_monetization",
            "做粗商业基准测算：找用户规模、价格锚点、转化率、LTV/CAC、留存和毛利线索；拿不到的数据只能标为缺失或系统假设。",
            "unit_economics",
            query_group="commercial_benchmark",
            query_group_label=QUERY_GROUP_LABELS["commercial_benchmark"],
            financial_sub_axis="commercial_benchmark",
            max_results=6,
        ),
        evidence_query(
            f"{topic_phrase} founders builders case studies lessons learned",
            "expert_signal",
            "识别候选方向里真实创始人、产品团队或独立开发者的做法和反思。",
            "expert",
            "supporting",
            query_group="expert_signal",
            query_group_label=QUERY_GROUP_LABELS["expert_signal"],
            max_results=6,
        ),
    ]
    if not broad_ai:
        plan.insert(-1, evidence_query(
            f"{topic_phrase} workflow use cases product demo templates",
            "official_capability",
            "补充候选方向的产品路径、工作流闭环和首次成功体验。",
            "official",
            query_group="product_flow",
            query_group_label=QUERY_GROUP_LABELS["product_flow"],
            max_results=6,
        ))
    if action_context == "seo_growth" or "seo_content_structure" in dimensions:
        plan.insert(1, evidence_query(
            f"{topic_phrase} keyword opportunities tool pages comparison pages",
            "search_intent",
            "如果用户重点看 SEO，优先补候选方向能否形成关键词和页面矩阵。",
            "distribution",
            query_group="growth_seo",
            query_group_label=QUERY_GROUP_LABELS["growth_seo"],
            max_results=6,
        ))
    return dedupe_plan(plan, limit=DEFAULT_SEARCH_PLAN_LIMIT)


def plan_for_topic(topic: str, info_needed, query_type: str = "", dimensions: list | None = None, action_context: str = "") -> list:
    dimensions = dimensions or []
    if not is_tool_like_topic(topic, query_type, dimensions):
        plan = [
            evidence_query(f"{topic} 市场规模 趋势 机会 需求", "search_intent", "确认市场需求、增长趋势和机会窗口，避免套用工具/API 类搜索模板。", "market"),
            evidence_query(f"{topic} 竞品 品牌 定价 商业模式", "competitor_and_monetization", "确认竞品密度、定位差异、定价和商业模式。", "competition"),
            evidence_query(f"{topic} 用户痛点 评价 投诉 替代方案", "user_discussion", "查找用户真实需求、抱怨、替代方案和未满足场景。", "user_pain"),
            evidence_query(f"{topic} 获客 渠道 SEO 关键词 内容", "search_intent", "判断是否存在可验证的获客渠道、搜索需求和内容入口。", "distribution"),
            evidence_query(f"{topic} 成本 毛利 供应链 运营", "competitor_and_monetization", "判断交付成本、毛利空间、供应链和运营难点。", "unit_economics"),
            evidence_query(f"{topic} 政策 风险 合规", "official_capability", "确认政策、合规、行业风险和不可控约束。", "risk"),
        ]
        if action_context == "seo_growth":
            plan = [
                evidence_query(f"{topic} 关键词 搜索需求 内容机会", "search_intent", "围绕 SEO/新流量目的，重点查关键词、搜索意图和内容切口。", "distribution"),
                evidence_query(f"{topic} SEO 页面 榜单 对比 攻略", "seo_page_type", "判断适合做榜单页、对比页、攻略页还是本地服务页。", "distribution"),
                evidence_query(f"{topic} 竞品 内容 流量 页面结构", "competitor_and_monetization", "参考竞品如何承接流量和设计页面结构。", "competition"),
                evidence_query(f"{topic} 用户问题 搜索意图 痛点", "user_discussion", "确认用户搜索这些内容背后的真实任务和未满足需求。", "user_pain"),
            ]
        elif action_context == "existing_product_conversion":
            plan = [
                evidence_query(f"{topic} 新客 转化 会员 复购 定价 活动", "competitor_and_monetization", "围绕已有业务优化，重点查新客转化、会员、复购、定价和活动机制。", "unit_economics"),
                evidence_query(f"{topic} 用户体验 服务流程 信任 转化 案例", "user_discussion", "参考体验流程、信任建立和降低转化阻力的做法。", "user_pain"),
                evidence_query(f"{topic} 用户评价 投诉 流失 原因", "user_discussion", "查用户流失、投诉和不续费原因。", "user_pain"),
                evidence_query(f"{topic} 竞品 定价 免费 会员 套餐", "competitor_and_monetization", "对比竞品的价格锚点、免费门槛和付费触发点。", "competition"),
            ]
        elif action_context == "market_watch":
            plan = [
                evidence_query(f"{topic} 行业趋势 竞品 动态 风险", "competitor_and_monetization", "围绕行业观察，重点查趋势、竞品变化和市场风险。", "market"),
                evidence_query(f"{topic} 政策 合规 风险 最新", "official_capability", "确认政策、合规和不可控约束是否变化。", "risk"),
                evidence_query(f"{topic} 用户讨论 需求 变化", "user_discussion", "观察用户讨论和需求变化。", "user_pain"),
                evidence_query(f"{topic} 头部品牌 公司 融资 合作", "competitor_and_monetization", "观察头部玩家、资本和合作信号是否改变市场结构。", "competition"),
            ]
        return dedupe_plan(with_expert_signal(plan, topic, tool_like=False))

    query_topic = search_query_topic(topic)
    if action_context == "seo_growth":
        exact_topic = quote_search_phrase(query_topic.replace(" website", ""))
        plan = [
            evidence_query(f"{exact_topic} search volume keyword difficulty SEO", "search_intent", "围绕 SEO/新流量目的，查关键词空间、搜索意图和竞争难度。", "distribution"),
            evidence_query(f"{exact_topic} SERP competitors landing page examples", "seo_page_type", "判断当前 SERP 是工具页、教程页、榜单页还是对比页主导。", "distribution"),
            evidence_query(f"{exact_topic} alternatives competitors traffic pages", "competitor_and_monetization", "参考竞品如何承接搜索流量和设计页面结构。", "competition"),
            evidence_query(f"{exact_topic} user questions reddit forum problems", "user_discussion", "确认用户搜索背后的真实任务、疑问和未满足需求。", "user_pain"),
            evidence_query(
                f"{exact_topic} conversion rate pricing ARPU LTV CAC benchmark",
                "competitor_and_monetization",
                "补一条商业基准：判断 SEO 流量变现是否有价格锚点、转化率、ARPU、LTV/CAC 线索；拿不到时标为缺失或系统假设。",
                "unit_economics",
                query_group="commercial_benchmark",
                query_group_label=QUERY_GROUP_LABELS["commercial_benchmark"],
                financial_sub_axis="commercial_benchmark",
            ),
        ]
        return dedupe_plan(with_expert_signal(plan, topic, tool_like=True), limit=DEFAULT_SEARCH_PLAN_LIMIT)

    if action_context == "existing_product_conversion":
        exact_topic = quote_search_phrase(query_topic)
        plan = [
            evidence_query(f"{exact_topic} pricing page free plan subscription upgrade", "competitor_and_monetization", "围绕已有产品转化，查价格锚点、免费额度、付费墙和升级触发点。", "unit_economics"),
            evidence_query(f"{exact_topic} homepage onboarding signup trial conversion examples", "user_discussion", "参考首页价值表达、注册路径、试用门槛和转化阻力。", "user_pain"),
            evidence_query(f"{exact_topic} competitors alternatives pricing", "competitor_and_monetization", "对比竞品、替代方案、定价和包装方式。", "competition"),
            evidence_query(
                f"{exact_topic} conversion rate churn retention LTV CAC ARPU benchmark",
                "competitor_and_monetization",
                "补一条商业基准：查转化率、留存、LTV/CAC、ARPU 等外部 benchmark；拿不到时报告必须标为缺失或系统假设。",
                "unit_economics",
                query_group="commercial_benchmark",
                query_group_label=QUERY_GROUP_LABELS["commercial_benchmark"],
                financial_sub_axis="commercial_benchmark",
            ),
            evidence_query(f"{exact_topic} SEO landing pages templates examples", "seo_page_type", "检查竞品是否通过模板页、样例页、对比页承接长尾流量。", "distribution"),
        ]
        return dedupe_plan(with_expert_signal(plan, topic, tool_like=True), limit=DEFAULT_SEARCH_PLAN_LIMIT)

    plan = [
        evidence_query(f"{query_topic} market size growth trend report", "competitor_and_monetization", "确认市场增长、需求成熟度和机会窗口，不只看产品可做性。", "market"),
        evidence_query(f"{query_topic} official API pricing documentation", "official_capability", "确认官方能力、API、价格和商用限制。", "official"),
        evidence_query(f"{query_topic} API commercial use limits availability cost", "api_feasibility", "判断是否能真实接入，并支撑可演示或可上线产品。", "unit_economics"),
        evidence_query(f"{query_topic} competitors alternatives pricing", "competitor_and_monetization", "确认是否已有竞品、替代方案和变现入口。", "competition"),
        evidence_query(
            f"{query_topic} revenue benchmark conversion rate LTV CAC ARPU churn gross margin",
            "competitor_and_monetization",
            "补商业基准测算：用户规模、价格锚点、转化率、LTV/CAC、留存、毛利；公开资料拿不到的数字必须标为缺失或系统假设。",
            "unit_economics",
            query_group="commercial_benchmark",
            query_group_label=QUERY_GROUP_LABELS["commercial_benchmark"],
            financial_sub_axis="commercial_benchmark",
        ),
        evidence_query(f"{query_topic} user reviews complaints reddit product hunt", "user_discussion", "查找用户真实需求、抱怨、替代品和未满足场景。", "user_pain"),
        evidence_query(f"{query_topic} tutorial how to use comparison search intent SEO", "search_intent", "判断用户搜索意图是教程、能力解释、工具入口还是比较。", "distribution"),
        evidence_query(f"{query_topic} policy legal copyright compliance platform risk", "official_capability", "确认政策、合规、版权、平台依赖和不可控风险。", "risk"),
    ]

    joined = " ".join(info_needed or [])
    if "价格" in joined or "pricing" in joined.lower():
        plan[0]["reason"] = "确认官方能力、API、价格、限流和商用限制。"
    if "搜索" in joined or "SEO" in joined.upper():
        plan.append({
            "query": f"{topic} search volume keyword intent SEO",
            "search_intent": "search_intent",
            "reason": "判断是否存在可验证的搜索需求和页面类型。"
        })

    return dedupe_plan(with_expert_signal(plan, topic, tool_like=True), limit=DEFAULT_SEARCH_PLAN_LIMIT)


def build_plan(data: dict, run_id: str = "") -> tuple[dict, dict, int, str]:
    raw_user_query = str(data.get("user_query", "")).strip()
    user_query = clean_search_text(raw_user_query)
    run_id = run_id or str(data.get("run_id", "")).strip() or new_run_id(user_query)
    semantic = data.get("semantic_route") if isinstance(data.get("semantic_route"), dict) else {}
    query_type = str(data.get("query_type") or semantic.get("query_type") or "").strip()
    dimensions = data.get("research_dimensions") or semantic.get("research_dimensions") or []
    if not isinstance(dimensions, list):
        dimensions = []
    action_context = str(data.get("action_context") or semantic.get("action_context") or "").strip()
    report_mode = str(data.get("report_mode") or semantic.get("report_mode") or "").strip()
    report_mode_label = str(data.get("report_mode_label") or semantic.get("report_mode_label") or "").strip()
    search_strategy = str(data.get("search_strategy") or semantic.get("search_strategy") or "normal_evidence").strip()
    if search_strategy not in {"normal_evidence", "candidate_discovery"}:
        search_strategy = "normal_evidence"
    strategy_source = str(data.get("strategy_source") or semantic.get("strategy_source") or "rule").strip()
    strategy_reason = str(data.get("strategy_reason") or semantic.get("strategy_reason") or "").strip()
    confirmed_intent = str(data.get("confirmed_intent") or semantic.get("confirmed_intent") or data.get("decision_context") or "").strip()
    confirmed_intent_type = str(data.get("confirmed_intent_type") or semantic.get("confirmed_intent_type") or data.get("intent_focus") or "").strip()

    if not user_query:
        output = {
            "run_id": run_id,
            "search_plan_source": "build_search_plan.py",
            "error": "缺少真实查询主题；激活词不能作为搜索主题。",
            "needs_confirmation": True,
            "allowed_to_search": False,
            "topic": "",
            "query_type": query_type or "generic_research",
            "search_strategy": search_strategy,
            "search_plan": []
        }
        intent_payload = {
            "user_query": raw_user_query,
            "topic": "",
            "query_type": query_type or "generic_research",
            "search_strategy": search_strategy,
            "confirmed_intent": confirmed_intent,
            "allowed_to_search": False,
            "reason": output["error"],
        }
        return output, intent_payload, 2, "blocked"

    if query_type == "reference_collection" or is_reference_site_query(user_query):
        topic = first_clean_topic(
            str(data.get("topic") or ""),
            str(semantic.get("topic") or ""),
            semantic_router.extract_reference_topic(user_query),
            extract_topic(user_query),
        )
        topic = normalize_research_topic(topic, user_query)
        if not confirmed_intent or (data.get("decision_clarity") or semantic.get("decision_clarity")) in {"unclear", "partial"} and not action_context:
            output = {
                "run_id": run_id,
                "search_plan_source": "build_search_plan.py",
                "error": "这是参考对象调研，需要先确认行动目的；请先运行 clarify_intent.py 或让用户确认用途。",
                "needs_confirmation": True,
                "allowed_to_search": False,
                "topic": topic,
                "query_type": "reference_collection",
                "search_plan": []
            }
            intent_payload = {
                "user_query": user_query,
                "topic": topic,
                "query_type": "reference_collection",
                "confirmed_intent": "",
                "allowed_to_search": False,
                "reason": output["error"],
            }
            return output, intent_payload, 2, "blocked"
        if search_strategy == "candidate_discovery":
            search_plan = plan_for_candidate_discovery(topic, action_context=action_context, dimensions=dimensions)
        else:
            search_plan = plan_for_reference_sites(topic, confirmed_intent, confirmed_intent_type, dimensions=dimensions, action_context=action_context)
    elif query_type == "latest_news" or is_latest_news_query(user_query):
        topic = first_clean_topic(
            str(data.get("topic") or ""),
            str(semantic.get("topic") or ""),
            normalize_news_topic(user_query),
        )
        topic = normalize_research_topic(topic, user_query)
        if not confirmed_intent or (data.get("decision_clarity") or semantic.get("decision_clarity")) in {"unclear", "partial"} and not action_context:
            output = {
                "run_id": run_id,
                "search_plan_source": "build_search_plan.py",
                "error": "这是开放集合查询，需要先确认查询意图；请先运行 clarify_intent.py 或让用户确认用途。",
                "needs_confirmation": True,
                "allowed_to_search": False,
                "topic": topic,
                "query_type": "latest_news",
                "search_plan": []
            }
            intent_payload = {
                "user_query": user_query,
                "topic": topic,
                "query_type": "latest_news",
                "confirmed_intent": "",
                "allowed_to_search": False,
                "reason": output["error"],
            }
            return output, intent_payload, 2, "blocked"
        search_plan = plan_for_latest_news(topic, confirmed_intent, confirmed_intent_type)
    else:
        topic = first_clean_topic(
            str(data.get("topic") or ""),
            str(semantic.get("topic") or ""),
            extract_topic(user_query),
        )
        topic = normalize_research_topic(topic, user_query)
        if is_ai_media_site_choice_query(user_query) or is_ai_media_site_choice_query(topic):
            topic = "AI 视频站 vs AI 图片站"
            search_plan = plan_for_ai_media_site_choice()
            if not action_context:
                action_context = "choice_decision"
            if not query_type or query_type == "curiosity":
                query_type = "decision_research"
        else:
            if search_strategy == "candidate_discovery":
                search_plan = plan_for_candidate_discovery(topic, action_context=action_context, dimensions=dimensions)
            else:
                search_plan = plan_for_topic(topic, data.get("voi_information_needed", []), query_type=query_type, dimensions=dimensions, action_context=action_context)

    fallback_search_plan = search_plan
    ai_search_plan = sanitize_ai_search_plan(read_ai_search_plan(data), topic)
    if ai_search_plan:
        search_plan = merge_ai_plan_with_fallback(ai_search_plan, sanitize_search_plan(fallback_search_plan), limit=DEFAULT_SEARCH_PLAN_LIMIT)
        search_plan_generation_mode = "ai_draft_validated_with_template_backfill"
    else:
        search_plan_generation_mode = "template"

    search_plan = sanitize_search_plan(search_plan)

    output = {
        "run_id": run_id,
        "search_plan_source": "build_search_plan.py",
        "search_plan_generation_mode": search_plan_generation_mode,
        "ai_search_plan_accepted_count": len(ai_search_plan),
        "topic": topic,
        "query_type": query_type,
        "search_strategy": search_strategy,
        "strategy_source": strategy_source,
        "strategy_reason": strategy_reason,
        "research_dimensions": dimensions,
        "action_context": action_context,
        "report_mode": report_mode,
        "report_mode_label": report_mode_label,
        "decision_clarity": data.get("decision_clarity") or semantic.get("decision_clarity", ""),
        "decision_context": data.get("decision_context", ""),
        "default_action": data.get("default_action", ""),
        "search_plan": search_plan
    }
    intent_payload = {
        "user_query": user_query,
        "topic": topic,
        "query_type": query_type,
        "search_strategy": search_strategy,
        "strategy_source": strategy_source,
        "strategy_reason": strategy_reason,
        "research_dimensions": dimensions,
        "action_context": action_context,
        "report_mode": report_mode,
        "report_mode_label": report_mode_label,
        "decision_clarity": data.get("decision_clarity") or semantic.get("decision_clarity", ""),
        "decision_context": data.get("decision_context", ""),
        "confirmed_intent": confirmed_intent,
        "confirmed_intent_type": confirmed_intent_type,
        "candidate_actions": data.get("candidate_actions", []),
        "default_action": data.get("default_action", ""),
        "voi_information_needed": data.get("voi_information_needed", []),
        "allowed_to_search": True,
    }
    return output, intent_payload, 0, "ok"


def main() -> int:
    data = read_input()
    output, intent_payload, exit_code, status = build_plan(data)
    run_id = output.get("run_id", "")
    run_info = record_stage(run_id, "intent", intent_payload, status)
    record_stage(run_id, "search_plan", output, status)
    output["run_log_path"] = run_info.get("run_log_path", "")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
