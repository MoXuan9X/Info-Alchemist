#!/usr/bin/env python3
import json
import re
import sys
from typing import Any, Dict, List
from urllib.parse import urlparse

from run_log import record_stage


IMPACT_BY_INTENT = {
    "official_capability": "medium",
    "api_feasibility": "medium",
    "competitor_and_monetization": "medium",
    "user_discussion": "weak",
    "search_intent": "medium",
    "seo_page_type": "weak",
    "expert_signal": "medium",
}

PLATFORM_LABELS = {
    "xhs": "小红书",
    "wechat": "公众号",
    "x": "X",
    "reddit": "Reddit",
}

PLATFORM_DEFAULTS = {
    "小红书": {
        "what_to_watch": "普通用户痛点、消费场景、需求语言",
        "confidence": "中",
    },
    "公众号": {
        "what_to_watch": "行业分析、教程、商业化、从业者观点",
        "confidence": "中到强",
    },
    "X": {
        "what_to_watch": "创始人、开发者、AI 圈专家、产品发布",
        "confidence": "中到强",
    },
    "Reddit": {
        "what_to_watch": "海外用户痛点、替代品讨论、真实抱怨",
        "confidence": "中",
    },
}

EVIDENCE_AXIS_LABELS = {
    "market": "市场/趋势",
    "official": "官方能力/限制",
    "unit_economics": "成本/单位经济",
    "competition": "竞品/替代方案",
    "user_pain": "用户痛点/抱怨",
    "distribution": "获客/SEO/页面机会",
    "risk": "平台/政策/合规风险",
    "expert": "专家/实践者信号",
}

QUALITY_SCORE_BASE = {
    "high": 88,
    "medium": 60,
    "low": 22,
    "missing": 0,
}

IMPACT_SCORE_BASE = {
    "high": 88,
    "medium": 74,
    "weak": 54,
    "low": 18,
}


def read_json() -> Dict[str, Any]:
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as handle:
            return json.load(handle)
    raw = sys.stdin.read().strip()
    if not raw:
        raise SystemExit("请通过 stdin 或文件路径提供联网搜索结果 JSON。")
    return json.loads(raw)


def first_result(search_item: Dict[str, Any]) -> Dict[str, Any]:
    results = search_item.get("results") or []
    return results[0] if results else {}


LOW_QUALITY_PATTERNS = [
    r"投注|博彩|网赌|六合彩|casino|betting",
    r"手动输入网址",
    r"content farm|ai tools directory",
]
SOCIAL_MEDIA_NOISE_RE = re.compile(
    r"(avatar|default_profile|profile_images|pbs\.twimg\.com|redditstatic\.com|preview\.redd\.it|i\.redd\.it|"
    r"xhscdn|sns-img|imageView2|profileIcon|video\.twimg\.com|\.m3u8|\.mp4|\.webp|\.jpg|\.jpeg|\.png)",
    re.I,
)
SHORT_LINK_RE = re.compile(r"^https?://(?:t\.co|bit\.ly|tinyurl\.com|ow\.ly|buff\.ly)/[A-Za-z0-9_-]+/?$", re.I)
DATE_ONLY_RE = re.compile(
    r"^\d{1,4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?$|"
    r"^\d+\s*(?:day(?:\(s\))?|days?|hour(?:\(s\))?|hours?|minute(?:\(s\))?|minutes?)\s+ago$",
    re.I,
)
SOCIAL_NOISE_WORDS = {"community", "user", "profile", "avatar", "image", "photo", "更多", "展开", "查看", "分享"}
SOCIAL_CJK_QUERY_TERMS = ["副业", "赚钱", "踩坑", "付费", "痛点", "需求", "体验", "避雷", "被骗", "退款", "兼职"]

HIGH_AUTHORITY_DOMAINS = {
    "openai.com",
    "platform.openai.com",
    "help.openai.com",
    "ai.google.dev",
    "cloud.google.com",
    "a16z.com",
    "grandviewresearch.com",
    "fortunebusinessinsights.com",
    "artificialanalysis.ai",
    "runwayml.com",
    "adobe.com",
    "copyright.gov",
    "commission.europa.eu",
    "ftc.gov",
    "ico.org.uk",
}

GENERIC_QUERY_TERMS = {
    "ai", "api", "official", "documentation", "docs", "pricing", "price", "cost", "commercial", "use",
    "limits", "availability", "market", "size", "growth", "trend", "report", "competitors", "alternatives",
    "user", "users", "reviews", "complaints", "reddit", "product", "hunt", "search", "volume", "keyword",
    "difficulty", "seo", "serp", "landing", "pages", "page", "examples", "traffic", "questions", "forum",
    "problems", "homepage", "onboarding", "signup", "trial", "conversion", "free", "plan", "plans",
    "subscription", "upgrade", "templates", "experts", "founders", "practitioners", "thought", "leaders",
    "current", "solutions", "case", "studies", "launch", "launches", "model", "models", "release",
    "releases", "developer", "developers", "tools", "today", "week", "latest", "new", "2025", "2026",
}

GENERIC_CJK_QUERY_TERMS = {
    "现在",
    "最近",
    "最新",
    "热门",
    "比较火",
    "头部",
    "产品",
    "工具",
    "网站",
    "用户",
    "评价",
    "投诉",
    "替代",
    "竞品",
    "对比",
    "定价",
    "商业模式",
    "创始人",
    "专家",
    "从业者",
    "案例",
    "教程",
    "推荐",
    "动态",
    "讨论",
}


def result_domain(result: Dict[str, Any]) -> str:
    url = result.get("url", "")
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def is_low_quality_result(result: Dict[str, Any]) -> bool:
    text = " ".join([result.get("title", ""), result.get("url", ""), result.get("content", "")])
    return any(re.search(pattern, text, re.I) for pattern in LOW_QUALITY_PATTERNS)


def is_encoded_noise(value: str) -> bool:
    text = re.sub(r"\s+", "", str(value or "").strip())
    if len(text) < 48 or re.search(r"[\u4e00-\u9fff]", text):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9+/=_-]+", text))


def is_media_or_short_link(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return bool(SOCIAL_MEDIA_NOISE_RE.search(text) or SHORT_LINK_RE.fullmatch(text))


def is_low_quality_social_result(result: Dict[str, Any]) -> bool:
    title = str(result.get("title") or "").strip()
    url = str(result.get("url") or "").strip()
    content = str(result.get("content") or "").strip()
    text = " ".join([title, url, content])
    domain = result_domain(result)
    if is_low_quality_result(result):
        return True
    if not title and not content:
        return True
    if len(re.sub(r"\s+", "", title + content)) < 18:
        return True
    xhs_text_result = (
        "xhscdn" in domain
        and bool(re.search(r"[\u4e00-\u9fff]", title + content))
        and len(re.sub(r"\s+", "", title + content)) >= 40
        and bool(re.search(r"踩坑|避雷|被骗|骗钱|退款|付费|课程|兼职|赚钱|不好用|价格|费用", title + content))
    )
    if is_media_or_short_link(url) and len(content) < 80 and not xhs_text_result:
        return True
    if is_media_or_short_link(title) or is_media_or_short_link(content):
        return True
    if re.fullmatch(r"https?://\S+", content) and (not url or content == url or result_domain({"url": content}) in {"reddit.com", "x.com", "twitter.com"}):
        return True
    compact = re.sub(r"\s+", "", title + content).strip()
    title_plain = re.sub(r"^\[[^\]]+\]\s*", "", title).strip()
    compact_title = re.sub(r"\s+", "", title_plain).strip()
    compact_content = re.sub(r"\s+", "", content).strip()
    if title_plain and DATE_ONLY_RE.fullmatch(title_plain) and (not content or DATE_ONLY_RE.fullmatch(content)):
        return True
    if content and DATE_ONLY_RE.fullmatch(content) and (not title_plain or DATE_ONLY_RE.fullmatch(title_plain)):
        return True
    if compact_title and re.fullmatch(r"\d+(?:[.,]\d+)?", compact_title) and (not compact_content or re.fullmatch(r"\d+(?:[.,]\d+)?", compact_content)):
        return True
    if compact.lower() in SOCIAL_NOISE_WORDS or DATE_ONLY_RE.fullmatch(compact):
        return True
    if re.fullmatch(r"\d+(?:[.,]\d+)?", compact):
        return True
    if is_encoded_noise(compact):
        return True
    if re.search(r"/gallery/|/user/|/users/|/profile/", url, re.I) and len(content) < 80:
        return True
    if domain in {"reddit.com"} and re.search(r"/gallery/", url, re.I):
        return True
    return False


def query_core_terms(query: str) -> List[str]:
    terms = []
    for token in re.findall(r"[a-z0-9][a-z0-9.-]{1,}", query.lower()):
        normalized = token.strip(".-")
        if normalized and normalized not in GENERIC_QUERY_TERMS and len(normalized) > 2:
            terms.append(normalized)
    cjk_text = re.sub(r"\s+", "", query)
    if "辅助" in cjk_text and "决策" in cjk_text:
        terms.extend(["辅助", "决策"])
    if "视频" in cjk_text:
        terms.append("视频")
    if "图片" in cjk_text or "图像" in cjk_text:
        terms.append("图片")
    if "会议纪要" in cjk_text:
        terms.append("会议纪要")
    for token in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        normalized = token.strip()
        if normalized and normalized not in GENERIC_CJK_QUERY_TERMS and len(normalized) >= 3:
            terms.append(normalized)
    for token in SOCIAL_CJK_QUERY_TERMS:
        if token in cjk_text:
            terms.append(token)
    lowered = query.lower()
    concept_rules = [
        (["workflow", "onboarding", "first use", "product demo"], ["workflow", "onboarding"]),
        (["founder", "founders", "interview", "product team", "practitioner"], ["founder", "interview"]),
        (["checklist", "action plan", "recommendations"], ["checklist", "action"]),
        (["pricing", "cost", "credits"], ["pricing", "cost"]),
    ]
    for triggers, additions in concept_rules:
        if any(trigger in lowered for trigger in triggers):
            terms.extend(additions)
    return list(dict.fromkeys(terms))


def result_relevance(search_item: Dict[str, Any], result: Dict[str, Any]) -> str:
    if search_item.get("provider") == "tikhub":
        query_text = str(search_item.get("query") or "")
    else:
        query_text = " ".join([
            str(search_item.get("source_query") or ""),
            str(search_item.get("query") or ""),
            str(search_item.get("reason") or ""),
        ])
    terms = query_core_terms(query_text)
    if len(terms) < 2:
        return "unknown"
    haystack = " ".join([result.get("title", ""), result.get("url", ""), result.get("content", "")]).lower()
    matched = sum(1 for term in terms if term in haystack)
    ratio = matched / len(terms)
    if ratio >= 0.5:
        return "relevant"
    if matched == 0:
        return "low"
    return "weak"


def text_signal_strength(result: Dict[str, Any]) -> float:
    title = str(result.get("title") or "")
    content = str(result.get("content") or "")
    compact = re.sub(r"\s+", "", title + content)
    if len(compact) >= 160:
        return 0.35
    if len(compact) >= 80:
        return 0.25
    if len(compact) >= 40:
        return 0.15
    return 0.05


def substantive_social_text(result: Dict[str, Any]) -> str:
    title = str(result.get("title") or "")
    content = str(result.get("content") or "")
    if re.match(r"^\[[^\]]+\]\s*https?://", title) or title.startswith("http"):
        title = ""
    content = re.sub(r"作者/来源：[^；]+", "", content)
    content = re.sub(r"互动：[^；]+", "", content)
    content = re.sub(r"https?://\S+", " ", content)
    return re.sub(r"\s+", " ", f"{title} {content}").strip()


def social_result_scores(search_item: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    relevance = result_relevance(search_item, result)
    hard_noise = is_low_quality_social_result(result)
    relevance_score = {
        "relevant": 0.85,
        "weak": 0.45,
        "unknown": 0.35,
        "low": 0.1,
    }.get(relevance, 0.1)
    evidence_score = text_signal_strength(result)
    if result.get("url") and not is_media_or_short_link(str(result.get("url") or "")):
        evidence_score += 0.2
    if result.get("author") or "作者/来源" in str(result.get("content") or ""):
        evidence_score += 0.15
    if result.get("metric_total") or "互动：" in str(result.get("content") or ""):
        evidence_score += 0.15
    decision_signal = bool(re.search(r"价格|费用|定价|商用|商业化|营收|收入|ARR|财报|报价|估值|增速|踩坑|不好用|积分|额度|水印|失败|不稳定|一致性|对比|替代|watermark|credits|pricing|alternatives|complaints|workflow|onboarding", " ".join([
        str(result.get("title") or ""),
        str(result.get("content") or ""),
    ]), re.I))
    if decision_signal:
        evidence_score += 0.1
    if len(re.sub(r"\s+", "", substantive_social_text(result))) < 24:
        evidence_score = min(evidence_score, 0.3)
    if hard_noise:
        relevance_score = min(relevance_score, 0.15)
        evidence_score = min(evidence_score, 0.2)
    evidence_score = round(min(1.0, evidence_score), 2)
    relevance_score = round(min(1.0, relevance_score), 2)
    return {
        "relevance": relevance,
        "relevance_score": relevance_score,
        "evidence_value_score": evidence_score,
        "is_usable": (not hard_noise) and (
            (relevance_score >= 0.5 and evidence_score >= 0.35)
            or (relevance_score >= 0.45 and evidence_score >= 0.5)
            or (relevance_score >= 0.45 and evidence_score >= 0.35 and decision_signal)
        ),
        "score_reason": (
            f"相关性={relevance}；文本/来源/互动信号评分={evidence_score}"
            if not hard_noise else "媒体链接、短文本、用户节点或噪音节点"
        ),
    }


def scored_social_results(search_item: Dict[str, Any]) -> List[Dict[str, Any]]:
    output = []
    for result in search_item.get("results") or []:
        scored = dict(result)
        scored.update(social_result_scores(search_item, result))
        output.append(scored)
    return sorted(
        output,
        key=lambda item: (
            1 if item.get("is_usable") else 0,
            float(item.get("relevance_score") or 0),
            float(item.get("evidence_value_score") or 0),
            float(item.get("score") or 0),
        ),
        reverse=True,
    )


def source_quality(search_item: Dict[str, Any], result: Dict[str, Any]) -> str:
    if not result:
        return "missing"
    if is_low_quality_result(result):
        return "low"
    domain = result_domain(result)
    if domain in HIGH_AUTHORITY_DOMAINS or any(domain.endswith("." + item) for item in HIGH_AUTHORITY_DOMAINS):
        return "high"
    intent = search_item.get("search_intent", "")
    if search_item.get("provider") == "tikhub":
        social_score = social_result_scores(search_item, result)
        if not social_score.get("is_usable"):
            return "low"
        return "medium"
    relevance = result_relevance(search_item, result)
    if relevance == "low":
        return "low"
    if intent in {"official_capability", "api_feasibility"} and domain:
        return "medium"
    return "medium"


def quality_rank(search_item: Dict[str, Any], result: Dict[str, Any]) -> tuple[int, float]:
    quality = source_quality(search_item, result)
    rank = {"high": 3, "medium": 2, "low": 1, "missing": 0}.get(quality, 0)
    score = float(result.get("score") or 0)
    if search_item.get("provider") == "tikhub":
        social_score = social_result_scores(search_item, result)
        score += float(social_score.get("relevance_score") or 0) + float(social_score.get("evidence_value_score") or 0)
    domain = result_domain(result)
    if any(video_domain in domain for video_domain in ["youtube.com", "youtu.be"]) and search_item.get("search_intent") not in {"user_discussion", "expert_signal"}:
        score -= 0.5
    return rank, score


def best_result(search_item: Dict[str, Any]) -> Dict[str, Any]:
    results = search_item.get("results") or []
    if not results:
        return {}
    return sorted(results, key=lambda item: quality_rank(search_item, item), reverse=True)[0]


def source_type(search_item: Dict[str, Any], result: Dict[str, Any]) -> str:
    intent = search_item.get("search_intent", "")
    domain = result_domain(result)
    if source_quality(search_item, result) == "high":
        return "official_or_authoritative"
    if search_item.get("provider") == "tikhub":
        return "social_platform"
    if intent == "user_discussion":
        return "user_discussion"
    if intent == "expert_signal":
        return "expert_or_practitioner_signal"
    if "reddit.com" in domain or "producthunt.com" in domain:
        return "community"
    return "web_result"


def quality_score_reason(quality: str) -> str:
    return {
        "high": "来源是官方、权威机构或高可追溯资料，可直接支撑判断。",
        "medium": "来源可追溯且相关，但仍需交叉验证或只能作为阶段性证据。",
        "low": "来源相关性、可信度或文本信号不足，只能作为噪声或缺口线索。",
        "missing": "未取得可用来源，不能支撑行动判断。",
    }.get(quality, "来源质量需要人工复核。")


def impact_score_reason(impact: str) -> str:
    return {
        "high": "足以挑战默认行动或直接改变优先级。",
        "medium": "会影响判断权重，但通常还需要其他证据配合。",
        "weak": "只能提供背景或轻微信号，不足以单独改变行动。",
        "low": "对本轮行动没有明确影响。",
    }.get(impact, "行动影响需要人工复核。")


def clamp_score(value: int) -> int:
    return max(0, min(100, int(round(value))))


def evidence_quality_score(search_item: Dict[str, Any], result: Dict[str, Any], quality: str, axis: str) -> int:
    score = QUALITY_SCORE_BASE.get(quality, 0)
    if not result or quality == "missing":
        return 0
    domain = result_domain(result)
    title = str(result.get("title") or "").lower()
    url = str(result.get("url") or "").lower()
    content = str(result.get("content") or "")
    compact_len = len(re.sub(r"\s+", "", title + content))
    if quality == "high":
        if any(token in url for token in ["/docs", "/documentation", "/pricing", "/api"]):
            score += 8
        if any(token in domain for token in ["grandviewresearch", "fortunebusinessinsights", "a16z", "copyright.gov", "ftc.gov"]):
            score += 4
        return clamp_score(score)
    if search_item.get("provider") == "tikhub":
        platform = str(search_item.get("platform_label") or search_item.get("platform") or "").lower()
        if "reddit" in platform or "reddit.com" in domain:
            score += 2
        elif "xhs" in platform or "小红书" in platform:
            score -= 12
        else:
            score -= 4
        social_score = social_result_scores(search_item, result)
        score += int(float(social_score.get("evidence_value_score") or 0) * 10)
        if social_score.get("relevance") == "weak":
            score -= 8
        return clamp_score(score)
    if "producthunt.com" in domain:
        score += 6
    if "reddit.com" in domain:
        score += 4
    if any(token in domain for token in ["futurepedia", "theresanaiforthat", "aitools"]):
        score -= 14
    if any(token in title or token in url for token in ["pricing", "price", "cost", "定价", "case-study", "case study"]):
        score += 8
    if axis in {"unit_economics", "risk", "official"}:
        score += 4
    if compact_len < 80:
        score -= 12
    elif compact_len >= 240:
        score += 4
    if quality == "low":
        score = min(score, 34)
    return clamp_score(score)


def evidence_voi_score(search_item: Dict[str, Any], result: Dict[str, Any], quality: str, impact: str, axis: str) -> int:
    score = IMPACT_SCORE_BASE.get(impact, 0)
    intent = str(search_item.get("search_intent") or "")
    query = " ".join([
        str(search_item.get("query") or ""),
        str(search_item.get("reason") or ""),
        str(result.get("title") or ""),
    ]).lower()
    axis_adjustments = {
        "unit_economics": 8,
        "user_pain": 8,
        "risk": 7,
        "official": 5,
        "competition": 2,
        "expert": 3,
        "distribution": -4,
        "market": -2,
    }
    score += axis_adjustments.get(axis, 0)
    if intent == "seo_page_type":
        score -= 5
    if intent == "user_discussion":
        score += 6
    if any(token in query for token in ["pricing", "price", "cost", "定价", "付费", "complaint", "抱怨", "pain", "风险", "risk"]):
        score += 5
    if any(token in query for token in ["directory", "tools", "导航", "目录", "榜单"]):
        score -= 8
    quality_score = evidence_quality_score(search_item, result, quality, axis)
    if quality == "low":
        score = min(score, 44)
    if quality == "missing":
        score = 0
    if quality_score < 35 and score > 45:
        score = 45
    return clamp_score(score)


def evidence_scores(search_item: Dict[str, Any], result: Dict[str, Any], quality: str, impact: str, axis: str) -> Dict[str, Any]:
    quality_score = evidence_quality_score(search_item, result, quality, axis)
    voi_score = evidence_voi_score(search_item, result, quality, impact, axis)
    return {
        "evidence_quality": quality_score,
        "voi": voi_score,
        "reasons": {
            "evidence_quality": quality_score_reason(quality),
            "voi": impact_score_reason(impact),
        },
    }


def infer_evidence_axis(search_item: Dict[str, Any]) -> str:
    explicit = str(search_item.get("evidence_axis") or "").strip()
    if explicit:
        return explicit
    intent = search_item.get("search_intent", "")
    query = " ".join([search_item.get("query", ""), search_item.get("reason", "")]).lower()
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
    if intent == "seo_page_type" or any(token in query for token in ["seo", "keyword", "search intent", "关键词", "页面"]):
        return "distribution"
    if intent == "competitor_and_monetization":
        if any(token in query for token in ["market", "trend", "growth", "size", "规模", "趋势"]):
            return "market"
        return "competition"
    return ""


def evidence_coverage_status(expected_axes: List[str], covered_axes: List[str]) -> Dict[str, Any]:
    expected = [axis for axis in expected_axes if axis and axis != "expert"]
    covered = [axis for axis in covered_axes if axis and axis != "expert"]
    missing = [axis for axis in expected if axis not in covered]
    score = round(len(covered) / len(expected), 2) if expected else 0
    if score >= 0.75 and not any(axis in missing for axis in ["market", "user_pain", "unit_economics"]):
        ceiling = "strong"
    elif score >= 0.5:
        ceiling = "medium"
    else:
        ceiling = "weak"
    return {
        "expected_axes": expected,
        "covered_axes": covered,
        "missing_axes": missing,
        "coverage_score": score,
        "coverage_score_0_5": round(score * 5, 1),
        "axis_coverage": [
            {
                "evidence_axis": axis,
                "evidence_axis_label": EVIDENCE_AXIS_LABELS.get(axis, axis),
                "score": 5 if axis in covered else 1,
                "status": "covered" if axis in covered else "missing",
            }
            for axis in expected
        ],
        "conclusion_strength_ceiling": ceiling,
        "axis_labels": EVIDENCE_AXIS_LABELS,
    }


def result_snippet(result: Dict[str, Any]) -> str:
    title = result.get("title") or ""
    content = result.get("content") or ""
    if title and content and title not in content:
        return f"{title}：{content}"
    return content or title


def make_finding(search_item: Dict[str, Any], result: Dict[str, Any]) -> str:
    answer = search_item.get("answer") or ""
    if search_item.get("provider") == "tikhub":
        scored_candidates = scored_social_results(search_item)
        candidates = [item for item in scored_candidates if item.get("is_usable")]
        if candidates:
            for candidate in scored_candidates:
                if candidate in candidates:
                    continue
                if (
                    candidate.get("evidence_value_score", 0) >= 0.35
                    and candidate.get("score_reason") != "媒体链接、短文本、用户节点或噪音节点"
                ):
                    candidates.append(candidate)
                if len(candidates) >= 3:
                    break
        if not candidates and result:
            candidates = [result]
        snippets = [
            snippet
            for snippet in (result_snippet(candidate) for candidate in candidates[:3])
            if snippet
        ]
        text = "；".join(snippets) or answer
    else:
        text = result_snippet(result) or answer
    if len(text) > 360:
        text = text[:357].rstrip() + "..."
    if text:
        return text
    return f"这个查询没有返回强公开证据：{search_item.get('query', '')}"


def decision_impact_rank(value: str) -> int:
    return {"high": 4, "medium": 3, "weak": 2, "low": 1}.get(value, 0)


def infer_social_themes(items: List[Dict[str, Any]]) -> List[str]:
    text = " ".join(
        " ".join([str(item.get("title") or ""), str(item.get("content") or ""), str(item.get("query") or "")])
        for item in items
    ).lower()
    rules = [
        (r"价格|费用|定价|太贵|credits?|pricing|cost|expensive", "费用/定价"),
        (r"对比|替代|竞品|平替|runway|kling|pika|luma|可灵|即梦|alternatives?|competitors?", "替代品/对比"),
        (r"踩坑|不好用|失败|水印|不稳定|一致性|watermark|failed|unreliable|consistency|complaints?", "使用阻力/质量"),
        (r"教程|推荐|榜单|best|tutorial|guide", "教程/推荐"),
        (r"商用|授权|commercial|license", "商用边界"),
        (r"流程|工作流|onboarding|workflow|first use", "流程/工作流"),
        (r"创始人|访谈|founder|interview|practitioner", "专家/实践者"),
    ]
    themes = [label for pattern, label in rules if re.search(pattern, text, re.I)]
    return themes[:4] or ["平台提及"]


def platform_confidence(usable_count: int, avg_relevance: float, avg_evidence: float, linked_count: int) -> tuple[str, str]:
    if usable_count >= 2 and avg_relevance >= 0.75 and avg_evidence >= 0.65 and linked_count:
        return "中高", "有多条可用社媒结果，且相关性、文本证据和可追溯来源都较完整。"
    if usable_count >= 1 and avg_relevance >= 0.65 and avg_evidence >= 0.45:
        return "中", "有可用社媒结果，但仍受限于平台搜索摘要、链接完整度或样本数。"
    return "低", "可用结果少，或文本/来源/互动信号不足。"


def build_social_platform_summaries(buckets: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    summaries = []
    platform_order = {"小红书": 0, "公众号": 1, "X": 2, "Reddit": 3}
    for platform, bucket in buckets.items():
        top_items = sorted(
            bucket.get("top_items", []),
            key=lambda item: (
                float(item.get("relevance_score") or 0),
                float(item.get("evidence_value_score") or 0),
                float(item.get("score") or 0),
            ),
            reverse=True,
        )[:3]
        if not top_items:
            continue
        usable_count = len(top_items)
        total_count = max(usable_count + int(bucket.get("noise_count") or 0), int(bucket.get("total_count") or 0))
        noise_count = max(0, total_count - usable_count)
        avg_relevance = sum(float(item.get("relevance_score") or 0) for item in top_items) / usable_count
        avg_evidence = sum(float(item.get("evidence_value_score") or 0) for item in top_items) / usable_count
        linked_count = sum(1 for item in top_items if item.get("url"))
        confidence, confidence_reason = platform_confidence(usable_count, avg_relevance, avg_evidence, linked_count)
        themes = infer_social_themes(top_items)
        snippets = [result_snippet(item) for item in top_items if result_snippet(item)]
        finding = "；".join(snippets[:2])
        if len(finding) > 360:
            finding = finding[:357].rstrip() + "..."
        impact = max(bucket.get("impact_levels", ["weak"]), key=decision_impact_rank)
        source = {"title": top_items[0].get("title", platform), "url": top_items[0].get("url", "")}
        summaries.append({
            "platform": platform,
            "what_to_watch": bucket.get("what_to_watch", ""),
            "current_finding": finding,
            "finding": finding,
            "themes": themes,
            "query": "；".join(dict.fromkeys(bucket.get("queries", []))),
            "source_query": "；".join(dict.fromkeys(bucket.get("source_queries", []))),
            "source": source,
            "sources": [
                {"title": item.get("title", platform), "url": item.get("url", "")}
                for item in top_items
            ],
            "top_items": top_items,
            "usable_count": usable_count,
            "noise_count": noise_count,
            "noise_ratio": round(noise_count / total_count, 2) if total_count else 0,
            "avg_relevance_score": round(avg_relevance, 2),
            "avg_evidence_value_score": round(avg_evidence, 2),
            "decision_impact": impact,
            "confidence": confidence,
            "confidence_reason": confidence_reason,
        })
    return sorted(summaries, key=lambda item: platform_order.get(item["platform"], 99))


def synthesize(data: Dict[str, Any]) -> Dict[str, Any]:
    public_evidence = []
    expert_judgment = []
    social_platform_buckets: Dict[str, Dict[str, Any]] = {}
    social_debug_trace = []
    painful_evidence = []
    gaps = []
    failed_queries = data.get("failed_queries", []) or []
    tavily_status = data.get("tavily_status", "")
    error_summary = data.get("error_summary") or data.get("error", "")
    expected_axes = []
    covered_axes = []

    for item in data.get("search_results", []):
        is_social_item = item.get("provider") == "tikhub" and item.get("platform")
        evidence_axis = infer_evidence_axis(item)
        if not is_social_item and evidence_axis and evidence_axis not in expected_axes:
            expected_axes.append(evidence_axis)
        if item.get("status") == "failed":
            platform_label = PLATFORM_LABELS.get(item.get("platform"), item.get("platform", ""))
            gaps.append({
                "gap": f"{platform_label + ' ' if platform_label else ''}联网搜索失败：{item.get('query', '')}",
                "type": "EVPI",
                "why_it_matters": item.get("error", "该 query 没有可用公开证据。"),
                "recommended_channel": "vertical_social_search" if is_social_item else "public_search",
                "channel": platform_label,
                "priority": "high"
            })
            continue
        result = best_result(item)
        intent = item.get("search_intent", "")
        source = {
            "title": result.get("title", item.get("query", "")),
            "url": result.get("url", "")
        }
        quality = source_quality(item, result)
        impact = "weak" if quality in {"low", "missing"} else IMPACT_BY_INTENT.get(intent, "weak")

        if is_social_item:
            platform_label = PLATFORM_LABELS.get(item.get("platform"), item.get("platform", ""))
            platform_defaults = PLATFORM_DEFAULTS.get(platform_label, {})
            scored_results = scored_social_results(item)
            usable_results = [candidate for candidate in scored_results if candidate.get("is_usable")]
            social_debug_trace.append({
                "platform": platform_label,
                "query": item.get("query", ""),
                "source_query": item.get("source_query", item.get("query", "")),
                "search_intent": intent,
                "total_results": len(scored_results),
                "usable_count": len(usable_results),
                "noise_count": max(0, len(scored_results) - len(usable_results)),
                "top_usable": [
                    {
                        "title": candidate.get("title", ""),
                        "url": candidate.get("url", ""),
                        "relevance_score": candidate.get("relevance_score"),
                        "evidence_value_score": candidate.get("evidence_value_score"),
                        "score_reason": candidate.get("score_reason", ""),
                    }
                    for candidate in usable_results[:3]
                ],
                "top_rejected": [
                    {
                        "title": candidate.get("title", ""),
                        "url": candidate.get("url", ""),
                        "relevance_score": candidate.get("relevance_score"),
                        "evidence_value_score": candidate.get("evidence_value_score"),
                        "score_reason": candidate.get("score_reason", ""),
                    }
                    for candidate in scored_results
                    if not candidate.get("is_usable")
                ][:3],
            })
            if usable_results:
                bucket = social_platform_buckets.setdefault(platform_label, {
                    "platform": platform_label,
                    "what_to_watch": platform_defaults.get("what_to_watch", ""),
                    "top_items": [],
                    "queries": [],
                    "source_queries": [],
                    "noise_count": 0,
                    "total_count": 0,
                    "impact_levels": [],
                })
                bucket["queries"].append(item.get("query", ""))
                bucket["source_queries"].append(item.get("source_query", item.get("query", "")))
                bucket["total_count"] += len(scored_results)
                bucket["noise_count"] += max(0, len(scored_results) - len(usable_results))
                bucket["impact_levels"].append(IMPACT_BY_INTENT.get(intent, "weak"))
                for candidate in usable_results:
                    enriched = dict(candidate)
                    enriched["query"] = item.get("query", "")
                    enriched["source_query"] = item.get("source_query", item.get("query", ""))
                    enriched["search_intent"] = intent
                    enriched["query_group"] = item.get("query_group", "")
                    enriched["query_group_label"] = item.get("query_group_label", "")
                    bucket["top_items"].append(enriched)
            else:
                gaps.append({
                    "gap": f"{platform_label} 社交搜索结果低相关或来源质量过低：{item.get('query', '')}",
                    "type": "EVPI",
                    "why_it_matters": "低相关社交结果会把泛创业、泛增长或图片壳链接误写成目标用户/专家信号。",
                    "recommended_channel": "vertical_social_search",
                    "channel": platform_label,
                    "priority": "medium"
                })
            continue

        public_evidence.append({
            "source": source,
            "finding": make_finding(item, result),
            "decision_impact": impact,
            "source_quality": quality,
            "source_type": source_type(item, result),
            "evidence_axis": evidence_axis,
            "evidence_axis_label": EVIDENCE_AXIS_LABELS.get(evidence_axis, evidence_axis),
            "query_group": item.get("query_group", ""),
            "query_group_label": item.get("query_group_label", ""),
            "query_source": item.get("query_source", ""),
            "scores": evidence_scores(item, result, quality, impact, evidence_axis),
        })
        if evidence_axis and quality not in {"low", "missing"} and evidence_axis not in covered_axes:
            covered_axes.append(evidence_axis)

        if intent == "expert_signal" and quality != "low":
            is_vertical = item.get("provider") == "tikhub"
            expert_subject = item.get("domain_expert", "") or item.get("expert_group", "")
            expert_judgment.append({
                "domain_expert": expert_subject or "未识别到明确专家主体",
                "source": source,
                "channel": PLATFORM_LABELS.get(item.get("platform"), item.get("platform", "公开搜索")) if is_vertical else "公开搜索",
                "query": item.get("query", ""),
                "query_group": item.get("query_group", ""),
                "query_group_label": item.get("query_group_label", ""),
                "selection_reason": "被选入是因为该结果来自专家信号查询，且与领域实践者、创始人、开发者、从业者群体、社区讨论或当前解法相关；最终报告必须结合来源标题和正文说明为什么选这个专家主体。",
                "finding": make_finding(item, result),
                "current_solution": "从本条专家信号中提炼当前解法；没有明确解法时写“公开证据不足”。",
                "how_to_use": "用于判断领域内行真正关注的问题、已有解法和仍未被充分解决的切口。",
                "confidence": "低" if not expert_subject else "中",
                "source_quality": quality,
            })
        elif intent == "expert_signal" and quality == "low":
            gaps.append({
                "gap": f"专家信号来源质量过低，不能作为专家判断：{item.get('query', '')}",
                "type": "EVPI",
                "why_it_matters": "低质或垃圾来源会让报告把无关网页误判为领域专家。",
                "recommended_channel": "public_search",
                "priority": "high"
            })

        haystack = " ".join([
            item.get("query", ""),
            item.get("answer", ""),
            result.get("content", "")
        ]).lower()
        if intent == "competitor_and_monetization":
            painful_evidence.append({
                "finding": "竞品或变现证据可能说明机会已经拥挤，需要更窄的定位。",
                "default_assumption_challenged": "主题新就等于市场空白。",
                "possible_action_change": "先做对比页、细分页面或 fake-door 验证，再考虑完整工具。"
            })
        if intent == "expert_signal":
            painful_evidence.append({
                "finding": "专家或高影响力实践者的关注点可以暴露这个领域真正难解决的问题。",
                "default_assumption_challenged": "只看公开需求和竞品页面就足够判断机会。",
                "possible_action_change": "把下一步验证收窄到专家反复讨论、且已有解法仍不充分的问题。"
            })
        if any(token in haystack for token in ["expensive", "limit", "not available", "complaint", "does not support", "pricing"]):
            painful_evidence.append({
                "finding": "公开结果中出现成本、限制、可用性或抱怨信号。",
                "default_assumption_challenged": "只要 API 可用，就值得产品化。",
                "possible_action_change": "先验证单位成本和失败模式，再投入工程开发。"
            })

    if not public_evidence:
        gaps.append({
            "gap": "本轮联网搜索全部失败，不能生成证据报告。",
            "type": "EVPI",
            "why_it_matters": "没有公开证据时，决策状态不应高于 watch。",
            "recommended_channel": "public_search",
            "priority": "high"
        })

    coverage = evidence_coverage_status(expected_axes, covered_axes)
    for axis in coverage["missing_axes"]:
        gaps.append({
            "gap": f"缺少高质量证据轴：{EVIDENCE_AXIS_LABELS.get(axis, axis)}",
            "type": "EVPI",
            "why_it_matters": "证据轴缺失时，报告不应输出超过该覆盖度上限的强结论。",
            "recommended_channel": "public_search",
            "priority": "high" if axis in {"market", "user_pain", "unit_economics"} else "medium"
        })

    gaps.extend([
        {
            "gap": "用户自己的真实受众是否有搜索或购买意图。",
            "type": "EVSI",
            "why_it_matters": "公开热度不等于用户能够触达的真实需求。",
            "recommended_channel": "GSC",
            "priority": "high"
        },
        {
            "gap": "用户是否会点击、加入等候名单或试用拟议工具。",
            "type": "EVSI",
            "why_it_matters": "这比公开讨论量更接近真实行动。",
            "recommended_channel": "fake_door",
            "priority": "high"
        }
    ])

    social_platform_signals = build_social_platform_summaries(social_platform_buckets)
    return {
        "search_provider": data.get("search_provider", "tavily"),
        "tavily_status": tavily_status or ("failure" if not public_evidence else "success"),
        "tavily_status_label": data.get("tavily_status_label", ""),
        "search_failure_diagnosis": error_summary,
        "failed_queries": failed_queries,
        "evidence_coverage": coverage,
        "public_evidence": public_evidence,
        "expert_judgment": expert_judgment,
        "social_platform_signals": social_platform_signals,
        "social_platform_summary": social_platform_signals,
        "social_debug_trace": social_debug_trace,
        "painful_evidence": painful_evidence,
        "evidence_gap_candidates": gaps
    }


def main() -> int:
    data = read_json()
    output = synthesize(data)
    run_id = str(data.get("run_id", "")).strip()
    if run_id:
        run_info = record_stage(run_id, "synthesis", output, "error" if output.get("tavily_status") == "failure" else "ok")
        output["run_id"] = run_id
        output["run_log_path"] = run_info.get("run_log_path", "")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
