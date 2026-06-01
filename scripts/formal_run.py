#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import build_search_plan
import clarify_intent
import resolve_confirmation
import semantic_router
import synthesize_tavily_results
import tavily_search
from run_log import new_run_id, record_stages


REPORT_CONTRACT = [
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

EVIDENCE_SCORING_GUIDE = {
    "scale": "所有分数使用 0-100 整数；0-19=无效，20-39=很弱，40-59=偏弱，60-74=可用，75-89=强，90-100=决定性。",
    "per_evidence_scores": {
        "证据质量": "来源和内容是否可信、可追溯、可复核；低于 60 通常不进入高价值证据主卡。",
        "VOI": "这条证据是否可能改变默认行动或优先级；高 VOI 优先展示。",
    },
    "report_usage": [
        "判断页只显示结论强度，不显示整份报告总分。",
        "证据页每条高价值证据只展示：证据质量、VOI。",
        "缺口页不展示证据覆盖度分数表。",
        "下一步页不展示 VOI × 可验证性矩阵。",
    ],
}

ECONOMICS_DISPLAY_GUIDE = {
    "trigger": (
        "不再生成独立成本结构测评或 7 天验证闸门；商业/成本只作为候选行动、定价或缺失证据里的简短判断。"
    ),
    "module_name": "经济线精简规则",
    "principles": [
        "不输出独立成本结构测评、7 天验证闸门、成本补齐清单、ROI 可计算性表、单次任务成本表或 90 天 ROI 表。",
        "成本和收入只作为候选行动、定价证据或缺失证据里的轻量判断。",
        "公开搜索拿不到 LTV、CAC、真实转化率、初始投入、月成本或单次任务成本时，必须写成缺失证据，不得装成事实。",
        "输出重点是继续、缩小、停止或补哪一个关键证据，而不是漂亮的收入预测。",
    ],
    "tables": {
        "cost_structure_table": "禁用。不要输出 `### 成本结构测评`。",
        "unit_cost_table": "禁用。不要输出独立单次任务成本表。",
        "roi_calculability_table": "禁用。不要输出 ROI 可计算性表。",
        "roi_action_table": "禁用。不要输出独立经济性行动表。",
        "scenario_table": "禁用。不要输出三档 ROI 情景表。",
        "cost_input_table": "禁用。不要输出成本补齐清单；缺口放进 `## 缺失的证据`。",
        "validation_gate_table": "禁用。不要输出 `### 7 天验证闸门` 或 7 天验证表。",
    },
    "metrics": [
        "用户规模/需求量",
        "价格锚点/ARPU",
        "访客到注册、注册到激活、免费到付费或试用到付费",
        "LTV/留存/续费或复购",
        "API/算力/人工审核/客服/维护/获客成本",
        "毛利率、保本客户数、保本流量、90 天 ROI、回本周期",
        "最敏感变量：通常是转化率、CAC、API 成本、留存或人工交付时长",
    ],
}

COST_STRUCTURE_QUERY_GROUPS = {
    "cost_structure",
    "official_infra_pricing",
    "database_storage_pricing",
    "media_storage_pricing",
    "model_api_pricing",
    "gpu_runtime_pricing",
    "email_pricing",
    "scraping_pricing",
    "analytics_monitoring_pricing",
}

COST_CATEGORY_LABELS = {
    "initial_investment": "初始投入",
    "monthly_fixed_cost": "月固定成本",
    "variable_task_cost": "单次任务成本",
    "revenue_benchmark": "收入/价格基准",
}

COST_GROUP_LABELS = {
    "official_infra_pricing": "部署/服务器",
    "database_storage_pricing": "数据库/存储",
    "media_storage_pricing": "媒体存储/CDN",
    "model_api_pricing": "模型/API",
    "gpu_runtime_pricing": "GPU/推理平台",
    "email_pricing": "邮件/通知",
    "scraping_pricing": "抓取/代理",
    "analytics_monitoring_pricing": "监控/分析",
    "pricing": "竞品定价",
    "commercial_benchmark": "商业基准",
}

REPORT_MODE_GUIDES = {
    "candidate_mode": {
        "label": "候选池调研",
        "section_focus": "核心判断先回答候选池是否足够可用；候选行动必须先给 3-5 张可执行方案卡片，再给候选产品拆解表；卡片用方案 A/B/C 或清晰行动名组织，每张卡用短标签写代表产品、典型流程、适合借鉴、先验证和避坑，避免大段解释；拆解表列 10-15 个候选方向/代表产品，按推荐顺序排序，不再单独输出 Top 5；每个候选必须写清入选依据和排序依据；候选方向可在表内带价格锚点、成本风险和获客难度，但不要单独输出成本结构测评或 7 天验证闸门；高价值证据优先展示候选池、竞品池、定价、用户反馈和 SEO 页面机会。",
    },
    "opportunity_mode": {
        "label": "机会判断",
        "section_focus": "核心判断给进入/观察/归档/小范围验证；候选行动比较独立产品、插件、内容站、服务交付或不做，可在建议里简短说明成本风险和价格锚点；缺少成本或转化输入时不写 90 天 ROI；下一步给具体动作，不输出 7 天验证闸门。",
    },
    "kill_mode": {
        "label": "放弃判断",
        "section_focus": "核心判断明确继续、缩小、转向、归档或放弃；候选行动必须包含停止/归档选项；缺失证据写清哪些证据会把结论从想做改成暂时归档。",
    },
    "pain_mode": {
        "label": "用户痛点",
        "section_focus": "核心判断回答谁最痛和痛到什么程度；候选行动围绕访谈人群、场景切口和验证方式；下一步给具体找人、问题和付费信号验证。",
    },
    "competitor_mode": {
        "label": "竞品判断",
        "section_focus": "核心判断回答差异化缺口在哪里；候选行动比较功能、渠道、定价、本地化、服务化切口；高价值证据按本轮 search_plan 命中的产品/竞品模块展示，只展示与决策目标相关的竞品池、产品路径、功能、定价、用户反馈、增长 SEO、社媒等小节。",
    },
    "teardown_mode": {
        "label": "流程借鉴",
        "section_focus": "核心判断回答哪些真实产品流程和做法值得借鉴；专家判断必须聚焦同类产品创始人、产品团队、一线实践者和用户反馈；高价值证据只展示命中的产品路径、功能工作流、定价、用户反馈、增长等相关模块，不展示用户未问到且不影响决策的板块。",
    },
    "mvp_mode": {
        "label": "MVP 切口",
        "section_focus": "核心判断回答最危险假设和第一次成功体验；候选行动必须砍掉不影响验证的功能；下一步给一个页面/一个按钮/手工服务/低代码实验。",
    },
    "monetization_mode": {
        "label": "商业模式/定价",
        "section_focus": "核心判断回答用户为何付费、价格风险和单位经济是否成立；候选行动比较订阅、按量、一次性、服务包、企业版，并给保守/基准/乐观三档测算；缺失证据强调真实付费意愿、CAC、LTV、留存和单位经济。",
    },
    "distribution_mode": {
        "label": "分发判断",
        "section_focus": "核心判断回答前 100 用户从哪里来；候选行动比较 SEO、社区、冷启动、demo、合作和内容资产；下一步必须是一个可发布的渠道实验。",
    },
    "timing_mode": {
        "label": "趋势与时机",
        "section_focus": "核心判断回答太早、刚好、太晚或只观察；候选行动比较进入、等待、观察和收集证据；下一步给触发条件和观察窗口。",
    },
    "operations_mode": {
        "label": "运营与交付",
        "section_focus": "核心判断回答一个人是否扛得住；候选行动比较自动化、外包、延后、不做和服务降级；下一步给 SOP、成本、客服和交付压力测试。",
    },
    "review_mode": {
        "label": "复盘与转向",
        "section_focus": "核心判断回答失败归因是需求、渠道、定位还是执行；候选行动比较继续打磨、换人群、换渠道、转向和归档；下一步给一轮能区分继续/停止的实验。",
    },
    "choice_mode": {
        "label": "方案选择",
        "section_focus": "核心判断先比较候选方案再给主次关系；候选行动必须列出 A、B、组合、暂不做；高价值证据优先用成本、能力、竞品、用户痛点和平台风险。",
    },
    "general_mode": {
        "label": "通用决策",
        "section_focus": "核心判断先给行动倾向；候选行动至少两个；下一步给最小可逆动作和停止规则。",
    },
}


def report_mode_guide(report_mode: str, report_mode_label: str = "") -> Dict[str, str]:
    mode = report_mode if report_mode in REPORT_MODE_GUIDES else "general_mode"
    guide = dict(REPORT_MODE_GUIDES[mode])
    if report_mode_label:
        guide["label"] = report_mode_label
    guide["mode"] = mode
    guide["html_pattern"] = (
        "为兼容 HTML 可视化，`## 决策问题` 第一行必须写 `报告模式："
        f"{guide['label']}`，第二行写 `决策对象：<topic>`；各章节内部优先使用 `###` 小标题和 Markdown 表格，"
        "不要用裸 HTML。"
    )
    return guide


def read_json_or_text(value: str) -> Dict[str, Any]:
    value = value.strip()
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"user_query": value}
    if isinstance(parsed, dict):
        return parsed
    return {"user_query": value}


def read_input(args: argparse.Namespace) -> Dict[str, Any]:
    if args.payload:
        data = read_json_or_text(args.payload)
    elif args.payload_file:
        data = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    elif any([args.query, args.previous_query, args.reply, args.confirmed_intent, args.confirmed_intent_type]):
        data = {}
    else:
        raw = sys.stdin.read().strip()
        data = read_json_or_text(raw)

    if args.query:
        data["user_query"] = args.query
    if args.previous_query:
        data["previous_query"] = args.previous_query
    if args.reply:
        data["reply"] = args.reply
    if args.confirmed_intent:
        data["confirmed_intent"] = args.confirmed_intent
    if args.confirmed_intent_type:
        data["confirmed_intent_type"] = args.confirmed_intent_type
    if args.confirmation_round is not None:
        data["confirmation_round"] = args.confirmation_round
    return data


def apply_confirmation(data: Dict[str, Any]) -> Dict[str, Any]:
    reply = str(data.get("reply") or data.get("user_reply") or "").strip()
    previous_query = str(data.get("previous_query") or data.get("original_query") or "").strip()
    if not reply:
        return data
    query_for_resolution = previous_query or str(data.get("user_query", "")).strip()
    resolved = resolve_confirmation.resolve(reply, query=query_for_resolution, context=data)
    output = dict(data)
    output["confirmation_resolution"] = resolved
    output["semantic_route"] = resolved
    if query_for_resolution:
        output["user_query"] = query_for_resolution
    if resolved.get("allowed_to_search"):
        output["confirmed_intent"] = resolved.get("confirmed_intent", "")
        output["confirmed_intent_type"] = resolved.get("confirmed_intent_type", "")
        output["query_type"] = resolved.get("query_type", "")
        output["topic"] = resolved.get("topic", "")
        output["research_dimensions"] = resolved.get("research_dimensions", [])
        output["action_context"] = resolved.get("action_context", "")
        output["decision_clarity"] = resolved.get("decision_clarity", "")
        output["search_strategy"] = resolved.get("search_strategy", "")
        output["strategy_source"] = resolved.get("strategy_source", "")
        output["strategy_reason"] = resolved.get("strategy_reason", "")
    else:
        output["confirmation_round"] = resolved.get("confirmation_round", data.get("confirmation_round", 0))
    return output


def merge_semantic_route(data: Dict[str, Any], route: Dict[str, Any]) -> Dict[str, Any]:
    output = dict(data)
    output["semantic_route"] = route
    for key in [
        "query_type",
        "topic",
        "research_dimensions",
        "action_context",
        "decision_clarity",
        "confirmed_intent",
        "confirmed_intent_type",
        "confirmation_round",
        "report_mode",
        "report_mode_label",
        "search_strategy",
        "strategy_source",
        "strategy_reason",
    ]:
        if key in route and route.get(key) not in (None, "", []):
            output[key] = route.get(key)
    return output


def confirmation_payload(data: Dict[str, Any], plan_output: Dict[str, Any], intent_payload: Dict[str, Any], question: str = "") -> Dict[str, Any]:
    # question 由调用方统一传入，避免重复调用 clarify_intent.clarify()
    return {
        "activation": "INFO_ALCHEMIST=TRUE",
        "route": "ask_user",
        "allowed_to_search": False,
        "needs_confirmation": True,
        "confirmation_question": question,
        "run_id": plan_output.get("run_id", ""),
        "run_log_path": plan_output.get("run_log_path", ""),
        "intent": intent_payload,
        "semantic_route": data.get("semantic_route", {}),
        "confirmation_round": data.get("confirmation_round", 0),
        "max_confirmation_rounds": data.get("max_confirmation_rounds", semantic_router.MAX_CONFIRMATION_ROUNDS),
        "search_plan": [],
        "note": "开放集合查询需要先确认行动目的；本轮未联网搜索。",
    }


def trim_text(value: Any, limit: int = 700) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def compact_source(source: Dict[str, Any] | None) -> Dict[str, str]:
    source = source if isinstance(source, dict) else {}
    return {
        "title": trim_text(source.get("title", ""), 160),
        "url": str(source.get("url", "") or "").strip(),
    }


def compact_public_evidence(item: Dict[str, Any]) -> Dict[str, Any]:
    scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
    return {
        "source": compact_source(item.get("source")),
        "finding": trim_text(item.get("finding", ""), 520),
        "decision_impact": item.get("decision_impact", ""),
        "source_quality": item.get("source_quality", ""),
        "source_type": item.get("source_type", ""),
        "evidence_axis": item.get("evidence_axis", ""),
        "evidence_axis_label": item.get("evidence_axis_label", ""),
        "query_group": item.get("query_group", ""),
        "query_group_label": item.get("query_group_label", ""),
        "query_source": item.get("query_source", ""),
        "scores": {
            "evidence_quality": scores.get("evidence_quality", ""),
            "voi": scores.get("voi", ""),
            "reasons": scores.get("reasons", {}) if isinstance(scores.get("reasons"), dict) else {},
        } if scores else {},
    }


def compact_expert_judgment(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "domain_expert": trim_text(item.get("domain_expert", ""), 120),
        "channel": item.get("channel", ""),
        "source": compact_source(item.get("source")),
        "selection_reason": trim_text(item.get("selection_reason", ""), 320),
        "finding": trim_text(item.get("finding", ""), 520),
        "current_solution": trim_text(item.get("current_solution", ""), 260),
        "how_to_use": trim_text(item.get("how_to_use", ""), 260),
        "confidence": item.get("confidence", ""),
        "source_quality": item.get("source_quality", ""),
        "query_group": item.get("query_group", ""),
        "query_group_label": item.get("query_group_label", ""),
    }


def compact_social_signal(item: Dict[str, Any]) -> Dict[str, Any]:
    sources = item.get("sources") if isinstance(item.get("sources"), list) else []
    return {
        "platform": item.get("platform", ""),
        "what_to_watch": trim_text(item.get("what_to_watch", ""), 180),
        "current_finding": trim_text(item.get("current_finding") or item.get("finding", ""), 520),
        "themes": item.get("themes", [])[:4] if isinstance(item.get("themes"), list) else [],
        "source": compact_source(item.get("source")),
        "sources": [compact_source(source) for source in sources[:3] if isinstance(source, dict)],
        "usable_count": item.get("usable_count", 0),
        "noise_count": item.get("noise_count", 0),
        "decision_impact": item.get("decision_impact", ""),
        "confidence": item.get("confidence", ""),
        "confidence_reason": trim_text(item.get("confidence_reason", ""), 260),
    }


def compact_gap(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "gap": trim_text(item.get("gap", ""), 260),
        "type": item.get("type", ""),
        "why_it_matters": trim_text(item.get("why_it_matters", ""), 320),
        "recommended_channel": item.get("recommended_channel", ""),
        "channel": item.get("channel", ""),
        "priority": item.get("priority", ""),
    }


def ai_facing_gaps(items: Any) -> list[Dict[str, Any]]:
    gaps = [item for item in (items or []) if isinstance(item, dict)]
    user_relevant = []
    for item in gaps:
        channel = str(item.get("recommended_channel", "") or "")
        gap = str(item.get("gap", "") or "")
        if channel == "vertical_social_search":
            continue
        if "社交搜索结果低相关" in gap or "垂直社媒搜索" in gap:
            continue
        user_relevant.append(item)
    priority_rank = {"high": 3, "medium": 2, "low": 1}
    user_relevant.sort(key=lambda item: priority_rank.get(str(item.get("priority", "")), 0), reverse=True)
    return [compact_gap(item) for item in user_relevant[:12]]


def compact_decision_risk(item: Dict[str, Any]) -> Dict[str, str]:
    return {
        "finding": trim_text(item.get("finding", ""), 260),
        "default_assumption_challenged": trim_text(item.get("default_assumption_challenged", ""), 220),
        "possible_action_change": trim_text(item.get("possible_action_change", ""), 260),
    }


def build_evidence_pack(synthesis: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "search_provider": synthesis.get("search_provider", ""),
        "tavily_status": synthesis.get("tavily_status", ""),
        "tavily_status_label": synthesis.get("tavily_status_label", ""),
        "search_failure_diagnosis": trim_text(synthesis.get("search_failure_diagnosis", ""), 500),
        "evidence_coverage": synthesis.get("evidence_coverage", {}),
        "public_evidence": [
            compact_public_evidence(item)
            for item in (synthesis.get("public_evidence") or [])
            if isinstance(item, dict)
        ],
        "expert_judgment": [
            compact_expert_judgment(item)
            for item in (synthesis.get("expert_judgment") or [])
            if isinstance(item, dict)
        ],
        "social_platform_signals": [
            compact_social_signal(item)
            for item in (synthesis.get("social_platform_signals") or [])
            if isinstance(item, dict)
        ],
        "decision_risks": [
            compact_decision_risk(item)
            for item in (synthesis.get("painful_evidence") or [])[:8]
            if isinstance(item, dict)
        ],
        "evidence_gap_candidates": ai_facing_gaps(synthesis.get("evidence_gap_candidates")),
    }


def active_search_modules(search_plan: Any) -> list[Dict[str, str]]:
    modules = []
    seen = set()
    for item in search_plan or []:
        if not isinstance(item, dict):
            continue
        group = str(item.get("query_group") or "").strip()
        if not group or group in seen:
            continue
        seen.add(group)
        modules.append({
            "query_group": group,
            "query_group_label": str(item.get("query_group_label") or group).strip(),
        })
    return modules


def compact_candidate_source_result(group: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, str]:
    return {
        "title": trim_text(result.get("title", ""), 160),
        "url": str(result.get("url", "") or "").strip(),
        "snippet": trim_text(result.get("content") or result.get("snippet") or "", 460),
        "source_query": trim_text(group.get("query", ""), 180),
        "query_group": str(group.get("query_group") or "").strip(),
        "query_group_label": str(group.get("query_group_label") or group.get("query_group") or "").strip(),
    }


def candidate_discovery_pack(plan_output: Dict[str, Any], search_payload: Dict[str, Any]) -> Dict[str, Any]:
    if plan_output.get("search_strategy") != "candidate_discovery":
        return {}
    priority = {
        "candidate_pool": 0,
        "segment_map": 1,
        "competitor_pool": 2,
        "expert_signal": 3,
        "user_feedback": 4,
        "growth_seo": 5,
        "pricing": 6,
        "product_flow": 7,
    }
    candidates: list[Dict[str, str]] = []
    for group in search_payload.get("search_results") or []:
        if not isinstance(group, dict) or group.get("status") != "ok":
            continue
        if group.get("provider") == "tikhub":
            continue
        results = group.get("results") if isinstance(group.get("results"), list) else []
        group_candidates = [
            compact_candidate_source_result(group, result)
            for result in results[:5]
            if (
                isinstance(result, dict)
                and result.get("provider") != "tikhub"
                and (result.get("title") or result.get("url"))
            )
        ]
        candidates.extend(group_candidates)
    candidates.sort(key=lambda item: priority.get(item.get("query_group", ""), 99))
    seen = set()
    deduped = []
    for item in candidates:
        key = item.get("url") or item.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= 28:
            break
    return {
        "search_strategy": "candidate_discovery",
        "strategy_reason": plan_output.get("strategy_reason", ""),
        "candidate_source_results": deduped,
        "required_output": [
            "先从 candidate_source_results 抽取候选方向、代表产品和用户任务；不要直接写抽象建议。",
            "候选行动必须先输出 3-5 个可执行方案卡片：标题用 `### 方案 A：...`、`### 方案 B：...` 或清晰行动名；每张卡片用短标签和项目符号写：代表产品、典型流程、适合借鉴、先验证、避坑。不要把卡片写成大段解释。",
            "卡片后再输出候选产品拆解表；用户可见小标题写 `### 候选产品拆解表`，表格包含 10-15 个候选对象并按推荐顺序排序；表头为：#、行动分组、候选方向、代表产品、入选依据、用户任务、付费信号、SEO/分发入口、竞品/风险、MVP/成本、建议。不要输出 `优先级` 列，排序由行顺序和行动分组共同表达。",
            "不再单独输出 Top 5 推荐；卡片负责行动归类，表格负责完整候选审计。若来源不足以支撑 10 个候选对象，必须写成缺失证据，不得凭常识补齐。",
            "代表产品名称必须使用 candidate_source_results 或 public_evidence 中已有 URL 写成 Markdown 链接。",
        ],
    }


def economics_source_result(group: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, str]:
    group_key = str(group.get("query_group") or "").strip()
    cost_category = str(group.get("cost_category") or "").strip()
    if not cost_category:
        if group_key in {"official_infra_pricing", "database_storage_pricing", "email_pricing", "analytics_monitoring_pricing"}:
            cost_category = "monthly_fixed_cost"
        elif group_key in {"model_api_pricing", "media_storage_pricing", "gpu_runtime_pricing", "scraping_pricing"}:
            cost_category = "variable_task_cost"
        elif group_key in {"pricing", "commercial_benchmark"}:
            cost_category = "revenue_benchmark"
    if group_key in COST_STRUCTURE_QUERY_GROUPS:
        source_type = "official_price"
    elif group_key == "pricing":
        source_type = "competitor_price"
    elif group_key == "commercial_benchmark":
        source_type = "benchmark"
    else:
        source_type = "economics_reference"
    return {
        "title": trim_text(result.get("title", ""), 160),
        "url": str(result.get("url", "") or "").strip(),
        "snippet": trim_text(result.get("content") or result.get("snippet") or "", 520),
        "source_query": trim_text(group.get("query", ""), 180),
        "query_group": group_key,
        "query_group_label": str(group.get("query_group_label") or group.get("query_group") or "").strip(),
        "evidence_axis": str(group.get("evidence_axis") or "").strip(),
        "financial_sub_axis": str(group.get("financial_sub_axis") or "").strip(),
        "cost_category": cost_category,
        "cost_category_label": COST_CATEGORY_LABELS.get(cost_category, cost_category),
        "cost_item": COST_GROUP_LABELS.get(group_key, str(group.get("query_group_label") or group_key).strip()),
        "source_type": source_type,
        "source_type_label": {
            "official_price": "官方价格",
            "competitor_price": "竞品定价",
            "benchmark": "商业基准",
            "economics_reference": "经济性参考",
        }.get(source_type, source_type),
    }


def economics_evidence_pack(search_payload: Dict[str, Any]) -> Dict[str, Any]:
    source_results: list[Dict[str, str]] = []
    for group in search_payload.get("search_results") or []:
        if not isinstance(group, dict) or group.get("status") != "ok":
            continue
        if group.get("provider") == "tikhub":
            continue
        is_relevant = (
            group.get("evidence_axis") == "unit_economics"
            or group.get("query_group") in {"pricing", "commercial_benchmark", *COST_STRUCTURE_QUERY_GROUPS}
            or group.get("financial_sub_axis")
        )
        if not is_relevant:
            continue
        for result in (group.get("results") or [])[:4]:
            if not isinstance(result, dict) or not (result.get("title") or result.get("url")):
                continue
            source_results.append(economics_source_result(group, result))
    seen = set()
    deduped = []
    for item in source_results:
        key = item.get("url") or item.get("title")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= 24:
            break
    return {
        "source_results": deduped,
        "known_limits": [
            "source_results 只能证明公开网页里出现过的价格、定价模型、LTV/CAC 公式或商业基准。",
            "若 source_results 没有给出某个候选行动的开发天数、月固定成本、单次 API/人工成本、CAC、LTV、转化率或留存，报告必须写“未取得公开证据”或“待用户估算”。",
            "不能把“低/中/高”“系统假设区间”写成事实；不能在缺少成本和转化输入时输出 90 天 ROI 区间。",
        ],
        "required_missing_inputs": [
            "初始投入：开发天数、人力成本或外包成本。",
            "月成本：部署、数据库、监控、模型/API、人工审核、客服和维护。",
            "单次任务成本：一次生成/分析/抓取/审核的可变成本。",
            "转化输入：访问到 CTA、CTA 到留资、试用到付费、首月留存。",
            "获客输入：SEO 起量周期、广告 CAC 或内容生产成本。",
        ],
    }


def grouped_cost_sources(source_results: list[Dict[str, str]]) -> Dict[str, list[Dict[str, str]]]:
    grouped: Dict[str, list[Dict[str, str]]] = {}
    for item in source_results:
        cost_item = item.get("cost_item") or item.get("query_group_label") or "其他成本线索"
        grouped.setdefault(cost_item, []).append(item)
    return {key: value[:4] for key, value in grouped.items()}


def cost_structure_assessment_pack(
    search_payload: Dict[str, Any],
    economics_pack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    pack = economics_pack or economics_evidence_pack(search_payload)
    source_results = pack.get("source_results") if isinstance(pack.get("source_results"), list) else []
    official_sources = [item for item in source_results if item.get("source_type") == "official_price"]
    competitor_price_sources = [item for item in source_results if item.get("source_type") == "competitor_price"]
    benchmark_sources = [item for item in source_results if item.get("source_type") == "benchmark"]
    return {
        "module_name": "经济线精简规则",
        "official_price_sources": official_sources[:18],
        "competitor_price_sources": competitor_price_sources[:8],
        "benchmark_sources": benchmark_sources[:8],
        "official_price_sources_by_cost_item": grouped_cost_sources(official_sources),
        "default_cost_model": {
            "initial_investment": [
                "产品设计、开发集成、首批内容/模板、上线配置、必要人工测试。",
                "没有公开外包或工时报价时只能写“待用户估算”，不能代填金额。",
            ],
            "monthly_fixed_cost": [
                "部署/服务器、数据库/存储、邮件/通知、监控/分析、域名和基础工具订阅。",
                "官方价格页可作为工具标价；实际月成本必须再乘用量假设。",
            ],
            "variable_task_cost": [
                "模型/API token、抓取/代理、文件处理、存储读写、失败重试和人工审核。",
                "没有任务量、token 量或抓取量时，只能给计算口径，不能给总成本。",
            ],
            "roi_inputs": [
                "价格/ARPU、访问到 CTA、CTA 到注册/留资、试用到付费、留存/LTV、CAC。",
                "缺少任一关键输入时只判断 ROI 是否可算，不输出 90 天 ROI 区间。",
            ],
        },
        "required_outputs": [
            "不要输出 `### 成本结构测评` 小节。",
            "不要输出独立单次任务成本表、ROI 可计算性表、成本补齐清单或 90 天 ROI 表。",
            "成本和收入信息只作为候选行动、定价证据或缺失证据里的轻量判断。",
            "缺成本或转化输入时只用一句话说明“当前暂不能计算 ROI，缺 X/Y/Z”。",
        ],
        "required_missing_inputs": pack.get("required_missing_inputs", []),
        "source_policy": [
            "官方价格源只能证明工具价格，不等于项目真实月成本。",
            "非官方博客、工具导航或二手总结不能作为官方价格，只能写成“价格线索”或不进成本表。",
            "没有来源 URL、用户输入或明确公开来源的数字不得进入成本表。",
            "没有证据的成本项不要生成；不要用“未取得公开证据”“缺失”“低/中/高”填表。",
        ],
    }


def search_result_summary(search_payload: Dict[str, Any]) -> Dict[str, Any]:
    groups = search_payload.get("search_results") or []
    failed_queries = search_payload.get("failed_queries") or []
    vertical = search_payload.get("vertical_search") if isinstance(search_payload.get("vertical_search"), dict) else {}
    return {
        "search_provider": search_payload.get("search_provider", ""),
        "tavily_status": search_payload.get("tavily_status", ""),
        "tavily_status_label": search_payload.get("tavily_status_label", ""),
        "error_summary": trim_text(search_payload.get("error_summary") or search_payload.get("error", ""), 500),
        "result_groups": len(groups),
        "successful_groups": sum(1 for item in groups if isinstance(item, dict) and item.get("status") == "ok"),
        "failed_groups": len(failed_queries),
        "failed_queries": [
            {
                "query": trim_text(item.get("query", ""), 180),
                "search_intent": item.get("search_intent", ""),
                "query_group": item.get("query_group", ""),
                "query_group_label": item.get("query_group_label", ""),
                "provider": item.get("provider", ""),
                "platform": item.get("platform", ""),
                "error": trim_text(item.get("error", ""), 260),
            }
            for item in failed_queries[:5]
            if isinstance(item, dict)
        ],
        "vertical_search": {
            "enabled": vertical.get("enabled", False),
            "platforms": vertical.get("platforms", []),
            "status": vertical.get("status", ""),
            "status_label": vertical.get("status_label", ""),
            "result_groups": vertical.get("result_groups", 0),
            "successful_groups": vertical.get("successful_groups", 0),
            "failed_groups": vertical.get("failed_groups", 0),
        } if vertical else {},
        "cache": {"hit": bool((search_payload.get("cache") or {}).get("hit", False))},
        "raw_results_location": "run_log_path",
    }


def should_show_economics_display(plan_output: Dict[str, Any]) -> bool:
    return False


def report_context(
    plan_output: Dict[str, Any],
    search_payload: Dict[str, Any],
    synthesis: Dict[str, Any],
    run_log_path: str,
) -> Dict[str, Any]:
    mode = str(plan_output.get("report_mode", "")).strip() or "general_mode"
    mode_label = str(plan_output.get("report_mode_label", "")).strip()
    guide = report_mode_guide(mode, mode_label)
    show_economics = should_show_economics_display(plan_output)
    economics_pack = economics_evidence_pack(search_payload) if show_economics else {}
    cost_assessment_pack = cost_structure_assessment_pack(search_payload, economics_pack) if show_economics else {}
    return {
        "activation": "INFO_ALCHEMIST=TRUE",
        "route": "formal_report_context",
        "run_id": plan_output.get("run_id", ""),
        "run_log_path": run_log_path,
        "report_mode": guide["mode"],
        "report_mode_label": guide["label"],
        "report_mode_guide": guide,
        "search_plan": plan_output.get("search_plan", []),
        "search_strategy": plan_output.get("search_strategy", "normal_evidence"),
        "strategy_source": plan_output.get("strategy_source", ""),
        "strategy_reason": plan_output.get("strategy_reason", ""),
        "active_search_modules": active_search_modules(plan_output.get("search_plan", [])),
        "search_result_summary": search_result_summary(search_payload),
        "candidate_discovery_pack": candidate_discovery_pack(plan_output, search_payload),
        "evidence_pack": build_evidence_pack(synthesis),
        "economics_display_guide": ECONOMICS_DISPLAY_GUIDE if show_economics else {},
        "economics_evidence_pack": economics_pack,
        "cost_structure_assessment_pack": cost_assessment_pack,
        "evidence_scoring_guide": EVIDENCE_SCORING_GUIDE,
        "report_contract": REPORT_CONTRACT,
        "report_format_rules": [
            "文字版每个 `##` 模块之间必须用独立一行 `---` 分割，并在分割线上下各保留一个空行。",
        ],
        "report_instruction": (
            "基于 search_plan、search_result_summary 和 evidence_pack 写中文正式报告。"
            "不要从原始搜索碎片重新概括；完整原始搜索结果只在 run_log_path 中用于审计和必要时回查。"
            "默认保持高信号、短段落、少铺陈；除非用户明确要求深查或长报告，不要为了显得完整而扩写。"
            "文字版每个 `##` 模块之间必须用独立一行 `---` 分割，并在分割线上下各保留一个空行；"
            "不要只靠空行分隔模块。"
            "顶层 7 个章节固定不改名，但必须按照 report_mode_guide 调整每节内部写法；"
            "尤其 `## 决策问题` 第一行必须写 `报告模式：<report_mode_label>`，第二行写 `决策对象：<topic>`，"
            "以便 HTML 可视化版识别报告类型并展示模式标签。"
            "固定章节仍需保留，专家判断必须放在候选行动之前，优先使用 evidence_pack.expert_judgment，"
            "展示领域专家/高影响力实践者是谁、"
            "他们关注的问题、以及他们现在采用的解法；没有明确人名时写清楚可识别的机构、社区或实践者群体。"
            "`## 专家判断` 推荐表头为 `| 领域专家 | 专家/实践者信号 | 来自渠道 | 为什么选 | 他们关注的问题 | 当前解法 | 对我们的启发 | 可信度 |`。"
            "领域专家列必须写出可称呼的专家主体：优先写可验证的人名；没有明确人名时，写可识别的机构、社区或实践者群体，"
            "例如“AI 工具站独立开发者”“Reddit 的目标用户群体”“小红书 AI 副业博主”；只有连群体主体也无法识别时，"
            "才写“未识别到明确专家主体”。可信度应按主体具体程度、来源强度和证据相关性调整；"
            "为什么选必须说明该专家主体与本领域、问题、解法或实践经验的关系。"
            "如果 search_strategy=candidate_discovery，报告必须先使用 candidate_discovery_pack 抽取候选池，"
            "`## 候选行动` 开头必须先给 3-5 个可执行方案卡片，标题用 `### 方案 A：...`、`### 方案 B：...` 或清晰行动名；"
            "每张卡片必须用短标签和项目符号写：代表产品、典型流程、适合借鉴、先验证、避坑；不要写成大段解释。"
            "卡片后再给 `### 候选产品拆解表`，列出 10-15 个候选对象并按推荐顺序排序；不要在用户可见标题里写“10-15 个”；表头固定为 "
            "`| # | 行动分组 | 候选方向 | 代表产品 | 入选依据 | 用户任务 | 付费信号 | SEO/分发入口 | 竞品/风险 | MVP/成本 | 建议 |`；"
            "不再单独输出 `### Top 5 推荐`；卡片负责行动归类，表格负责候选审计，建议列要写清优先、观察、暂缓或淘汰理由；"
            "不能只写“AI SEO、AI 文档、AI 外联”这类无来源方向。"
            "candidate_discovery 模式下，核心判断必须说明候选池质量、排序口径和最前排候选的共同特征；缺少候选对象时必须把“候选池证据不足”写入缺失证据。"
            "不要输出独立 `### 成本结构测评`、`### 7 天验证闸门`、成本补齐清单、ROI 可计算性表、单次任务成本表或 90 天 ROI 表。"
            "商业/成本信息只允许轻量融入：候选池表的 `付费信号`、`MVP/成本`、`建议`列，高价值证据里的定价/商业基准证据，"
            "或缺失证据里一句关键缺口。"
            "缺成本或转化输入时只写“当前暂不能计算 ROI，主要缺：X、Y、Z”，不要另起表。"
            "下一步行动写具体动作、记录指标和停止条件，不要命名为 7 天验证闸门。"
            "当报告模式是流程借鉴、产品拆解或参考产品流程时，专家判断只能纳入同类真实产品创始人、产品团队、"
            "一线实践者或目标用户社区；不得用泛增长、会员、UX、营销或本地服务案例替代同类产品证据，"
            "除非来源明确在运营或拆解同类产品。"
            "专家判断表格必须按可信度从高到低排序，顺序为：高、中高、中、低、待验证。"
            "涉及“做 A 还是做 B、还是都做”的产品方向选择时，报告必须先比较候选行动，"
            "并优先使用四类硬证据：官方文档/官方定价、市场规模或行业报告、头部平台/竞品动态、真实用户抱怨或社区讨论；"
            "不能只用泛博客、工具导航或搜索摘要下结论。"
            "如果 evidence_pack 里有 source_quality/source_type 字段，高价值证据优先选 source_quality=high 或 medium 的来源；"
            "source_quality=low 的来源不得进入专家判断或高价值证据，只能放入缺失证据或说明为噪声。"
            "高价值证据必须只展示与本轮决策目标相关的模块：优先读取 active_search_modules 和 public_evidence[].query_group；"
            "用户没有问到、search_plan 没有命中、或不影响本轮决策的产品/竞品板块不得硬写。"
            "`## 高价值证据` 内部可以按命中的 query_group 写 `###` 小节，例如竞品池、产品路径、功能/能力、定价、用户反馈、增长/SEO、社交平台；"
            "但不要为了凑完整而展示空模块。每个小节只放该模块中 source_quality=high 或 medium、且最能改变行动的证据。"
            "如果本轮不是产品/竞品类调研，也可以只用一张总表；无论总表还是模块小节，证据都必须按行动影响从高到低排序，顺序为：高、中高、中、低。"
            "高价值证据表格必须使用扩展表头："
            "`| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |`。"
            "证据质量和 VOI 都写成 0-100 整数，推荐格式 `N/100`，优先使用 evidence_pack.public_evidence[].scores；"
            "不要给整份报告写五维总分。证据质量看来源可信和可追溯性；"
            "VOI 看是否会改变默认行动、优先级、范围、定价、渠道或停止规则。"
            "如果 evidence_pack.evidence_coverage 存在，必须让核心判断的语气受 "
            "`conclusion_strength_ceiling` 约束：strong 可给明确建议，medium 只能给倾向性建议，"
            "weak 只能给观察/小范围验证建议；缺失的 evidence axis 必须进入 `## 缺失的证据`。"
            "`## 缺失的证据` 只写缺什么证据、为什么限制判断和补证方向，不要展示证据覆盖度分数表。"
            "`## 下一步行动` 直接写具体优先行动，不要展示 VOI × 可验证性矩阵。"
            "只有 report_mode 为 choice_mode 且决策对象确实是 AI 图片/视频这类生成站时，才显式比较：市场增长、竞争密度、API/单位成本、质量稳定性、SEO/页面机会、变现路径、平台风险；"
            "如果结论是“都做”，必须表述为同一条垂直工作流里的主次关系，而不是两个独立站并行。"
            "高价值证据必须保留可点击来源链接；如果 evidence_pack.social_platform_signals 非空，"
            "必须在高价值证据章节内新增 `### 社交平台` 小节，用表格按小红书、X、Reddit 展示平台、"
            "主要看什么、这轮发现、对行动的影响、可信度和来源；推荐表头为 "
            "`| 社交平台 | 主要看什么 | 这轮发现 | 对行动的影响 | 可信度 | 来源 |`；不要命名为“四渠道信号矩阵”。"
            "社交平台小节优先使用 evidence_pack.social_platform_signals 中按平台聚合后的"
            "current_finding、themes、confidence_reason、sources；不要重新从未聚合的低质碎片里概括。"
            "垂直社媒搜索的报错、超时、空结果和未命中只作为内部日志，不得写进用户报告；"
            "社交平台小节只呈现已搜到的有效结果。"
            "如果报告中出现竞品或工具站清单表格和名称，工具站名称必须写成 Markdown 可点击链接，"
            "格式为 [工具站名称](https://官网地址)，且只能使用搜索结果中已返回的真实 URL；"
            "没有 URL 的对象不得编造官网地址，必须标为“待补直接来源”或移到缺失证据。"
            "宿主发送前必须用 scripts/record_final_output.py 记录最终报告；该脚本会把完整 Markdown 文字版归档到"
            "当前 workspace 的 info-alchemist/reports/信息炼金报告-<决策对象>-YYYYMMDD.md，生成短文件名 HTML 可视化报告，"
            "并返回带 HTML 入口的完整 user_visible_text。用户可见层直接发送完整 user_visible_text；"
            "完整证据、经济性表和行动建议都保留在飞书正文里，token 估算只在 Markdown 归档和 HTML 页面里。默认链接从 http://127.0.0.1:8765/<run_id>.html 起自动选择可用端口，"
            "不要把 file:// 链接直接发到飞书，因为飞书会显示为蓝色但无法打开。"
            "完整搜索正文在 run_log_path 中。"
        ),
    }


def run_formal(data: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
    data = apply_confirmation(data)
    user_query = str(data.get("user_query", "")).strip()
    run_id = str(data.get("run_id", "")).strip() or new_run_id(user_query)
    data["run_id"] = run_id

    semantic_route = data.get("semantic_route") if isinstance(data.get("semantic_route"), dict) else {}
    if not semantic_route:
        semantic_route = semantic_router.route_query(user_query, data)
        data = merge_semantic_route(data, semantic_route)

    if semantic_route.get("trigger_level") in {"none", "direct", "light"} and semantic_route.get("query_type") in {"non_applicable", "direct_lookup", "factual_lookup"}:
        intent_payload = {
            "user_query": user_query,
            "topic": semantic_route.get("topic", ""),
            "query_type": semantic_route.get("query_type", ""),
            "trigger_level": semantic_route.get("trigger_level", ""),
            "allowed_to_search": False,
            "reason": semantic_route.get("reason", "这不是需要 Info-Alchemist 完整流程的问题。"),
        }
        run_info = record_stages(run_id, [
            {"stage": "intent", "status": "skipped", "payload": intent_payload},
        ])
        return {
            "activation": "INFO_ALCHEMIST=FALSE",
            "route": "pass_through",
            "allowed_to_search": False,
            "needs_confirmation": False,
            "run_id": run_id,
            "run_log_path": run_info.get("run_log_path", ""),
            "intent": intent_payload,
            "note": "这不是需要 Info-Alchemist 完整流程的问题；宿主可以按普通任务处理。",
        }, 0

    if semantic_route.get("needs_confirmation"):
        intent_payload = {
            "user_query": user_query,
            "topic": semantic_route.get("topic", ""),
            "query_type": semantic_route.get("query_type", ""),
            "research_dimensions": semantic_route.get("research_dimensions", []),
            "action_context": semantic_route.get("action_context", ""),
            "decision_clarity": semantic_route.get("decision_clarity", ""),
            "confirmation_round": semantic_route.get("confirmation_round", 0),
            "max_confirmation_rounds": semantic_route.get("max_confirmation_rounds", semantic_router.MAX_CONFIRMATION_ROUNDS),
            "allowed_to_search": False,
            "reason": semantic_route.get("reason", ""),
        }
        plan_output = {
            "run_id": run_id,
            "search_plan_source": "build_search_plan.py",
            "topic": semantic_route.get("topic", ""),
            "query_type": semantic_route.get("query_type", ""),
            "needs_confirmation": True,
            "allowed_to_search": False,
            "search_plan": [],
            "reason": "行动目的不明确，先追问用户。",
        }
        run_info = record_stages(run_id, [
            {"stage": "intent", "status": "blocked", "payload": intent_payload},
            {"stage": "search_plan", "status": "blocked", "payload": plan_output},
        ])
        plan_output["run_log_path"] = run_info.get("run_log_path", "")
        data["run_log_path"] = run_info.get("run_log_path", "")
        data["confirmation_round"] = semantic_route.get("confirmation_round", 0)
        data["max_confirmation_rounds"] = semantic_route.get("max_confirmation_rounds", semantic_router.MAX_CONFIRMATION_ROUNDS)
        return confirmation_payload(
            data,
            plan_output,
            intent_payload,
            question=semantic_route.get("confirmation_question", ""),
        ), 0

    plan_output, intent_payload, plan_exit, plan_status = build_search_plan.build_plan(data, run_id=run_id)
    if plan_exit != 0:
        # 只在此处调用一次 clarify_intent.clarify()，取得 confirmation_question 后传给 confirmation_payload
        question = clarify_intent.clarify(user_query).get("confirmation_question", "")
        run_info = record_stages(run_id, [
            {"stage": "intent", "status": plan_status, "payload": intent_payload},
            {"stage": "search_plan", "status": plan_status, "payload": plan_output},
        ])
        plan_output["run_log_path"] = run_info.get("run_log_path", "")
        return confirmation_payload(data, plan_output, intent_payload, question=question), 0

    search_payload, search_exit = tavily_search.execute_search(plan_output, run_id=run_id, write_run_log=False)
    synthesis = synthesize_tavily_results.synthesize(search_payload)
    synthesis["run_id"] = run_id

    search_status = "error" if search_payload.get("tavily_status") == "failure" else "ok"
    synthesis_status = "error" if synthesis.get("tavily_status") == "failure" else "ok"
    run_info = record_stages(run_id, [
        {"stage": "intent", "status": plan_status, "payload": intent_payload},
        {"stage": "search_plan", "status": "ok", "payload": plan_output},
        {"stage": "tavily_result", "status": search_status, "payload": search_payload},
        {"stage": "synthesis", "status": synthesis_status, "payload": synthesis},
    ])
    search_payload["run_log_path"] = run_info.get("run_log_path", "")
    synthesis["run_log_path"] = run_info.get("run_log_path", "")

    payload = report_context(plan_output, search_payload, synthesis, run_info.get("run_log_path", ""))
    if search_payload.get("tavily_status") == "failure":
        payload["route"] = "search_failed"
        payload["failure_message"] = "本轮联网搜索全部失败，不能生成证据报告。"
    return payload, 0


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 Info-Alchemist 正式流程单入口。")
    parser.add_argument("--query", default="")
    parser.add_argument("--previous-query", default="")
    parser.add_argument("--reply", default="")
    parser.add_argument("--confirmed-intent", default="")
    parser.add_argument("--confirmed-intent-type", default="")
    parser.add_argument("--confirmation-round", type=int, default=None)
    parser.add_argument("--payload", default="")
    parser.add_argument("--payload-file", default="")
    args = parser.parse_args()

    data = read_input(args)
    if not data.get("user_query") and not data.get("previous_query"):
        raise SystemExit("请提供 user_query，或使用 --query。")
    payload, exit_code = run_formal(data)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
