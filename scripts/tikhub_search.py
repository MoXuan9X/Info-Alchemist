#!/usr/bin/env python3
import json
import math
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Tuple


DEFAULT_TIKHUB_API_BASE = "https://api.tikhub.io"
DEFAULT_TIKHUB_TIMEOUT_SECONDS = 12
DEFAULT_TIKHUB_CONCURRENCY = 4
DEFAULT_TIKHUB_MAX_QUERIES = 0
DEFAULT_TIKHUB_RESULTS_PER_GROUP = 3
DEFAULT_TIKHUB_QUERY_RETRIES = 0
DEFAULT_TIKHUB_WECHAT_RETRIES = 0
QUERY_REWRITE_STRATEGY_VERSION = "social-brief-v3"
PLATFORM_TIME_STRATEGY_VERSION = "platform-time-v2"

PLATFORM_CONFIG = {
    "xhs": {
        "label": "小红书",
        "path": "/api/v1/xiaohongshu/app_v2/search_notes",
    },
    "wechat": {
        "label": "微信公众号",
        "path": "/api/v1/wechat_mp/web/fetch_search_article",
    },
    "x": {
        "label": "X",
        "path": "/api/v1/twitter/web/fetch_search_timeline",
    },
    "reddit": {
        "label": "Reddit",
        "path": "/api/v1/reddit/app/fetch_dynamic_search",
    },
}

XHS_FALLBACKS = [
    {
        "name": "app_v2",
        "label": "小红书 App V2",
        "path": "/api/v1/xiaohongshu/app_v2/search_notes",
    },
    {
        "name": "app",
        "label": "小红书 App",
        "path": "/api/v1/xiaohongshu/app/search_notes",
    },
    {
        "name": "web_v3",
        "label": "小红书 Web V3",
        "path": "/api/v1/xiaohongshu/web_v3/fetch_search_notes",
    },
]

PLATFORM_ALIASES = {
    "redbook": "xhs",
    "xiaohongshu": "xhs",
    "xhs": "xhs",
    "twitter": "x",
    "x": "x",
    "reddit": "reddit",
}

TOPIC_SUFFIX_PATTERNS = [
    r"\s+official API pricing documentation$",
    r"\s+API commercial use limits availability$",
    r"\s+competitors alternatives pricing$",
    r"\s+user reviews complaints reddit product hunt$",
    r"\s+tutorial how to use comparison$",
    r"\s+best tools alternatives vs$",
    r"\s+experts founders practitioners thought leaders problems current solutions case studies$",
    r"\s+search volume keyword intent SEO$",
    r"\s+市场规模 趋势 机会 需求$",
    r"\s+竞品 品牌 定价 商业模式$",
    r"\s+用户痛点 评价 投诉 替代方案$",
    r"\s+获客 渠道 SEO 关键词 内容$",
    r"\s+成本 毛利 供应链 运营$",
    r"\s+政策 风险 合规$",
    r"\s+行业专家 创始人 从业者 大佬 关注问题 解决方案 案例$",
]

EN_TOPIC_REPLACEMENTS = [
    (r"AI\s*视频(?:站|工具|生成工具?)?", "AI video generator"),
    (r"AI\s*图片(?:站|工具|生成工具?)?", "AI image generator"),
    (r"AI\s*编程(?:工具)?", "AI coding tools"),
    (r"AI\s*写作(?:工具)?", "AI writing tools"),
    (r"AI\s*PPT\s*(?:工具)?", "AI presentation generator"),
    (r"AI\s*SEO\s*工具站", "AI SEO tools"),
    (r"AI\s*工具站", "AI tools"),
    (r"AI\s*产品(?:可以做)?", "AI tools"),
    (r"独立开发者", "indie hackers"),
    (r"工具站", "tool website"),
]

ZH_TOPIC_REPLACEMENTS = [
    (r"AI\s*视频站", "AI 视频生成工具"),
    (r"AI\s*图片站", "AI 图片生成工具"),
    (r"AI\s*产品(?:可以做)?", "AI工具站"),
]

TITLE_KEYS = [
    "title",
    "display_title",
    "article_title",
    "note_title",
    "postTitle",
]
CONTENT_KEYS = [
    "full_text",
    "text",
    "content",
    "desc",
    "description",
    "digest",
    "summary",
    "body",
    "selftext",
    "markdown",
]
AUTHOR_KEYS = [
    "author",
    "author_name",
    "nickname",
    "user_name",
    "screen_name",
    "account_name",
    "subreddit_name_prefixed",
]
URL_KEYS = [
    "url",
    "web_url",
    "link",
    "share_url",
    "note_url",
    "article_url",
    "content_url",
    "source_url",
    "expanded_url",
    "permalink",
]
ID_KEYS = [
    "note_id",
    "noteId",
    "noteIdStr",
    "tweet_id",
    "tweetId",
    "rest_id",
    "id_str",
    "conversation_id_str",
    "permalink",
]
METRIC_KEYS = [
    "like_count",
    "liked_count",
    "likes",
    "favorite_count",
    "collect_count",
    "comment_count",
    "commentCount",
    "comments",
    "reply_count",
    "replies",
    "retweet_count",
    "repost_count",
    "view_count",
    "viewCount",
    "read_count",
    "upvote_count",
    "score",
]
NESTED_CONTENT_KEYS = [
    "note",
    "note_card",
    "card",
    "article",
    "tweet",
    "legacy",
    "post",
    "submission",
    "data",
    "content",
]
MEDIA_URL_RE = re.compile(
    r"(?:xhscdn|sns-img|imageView2|redditstatic\.com|preview\.redd\.it|i\.redd\.it|pbs\.twimg\.com|"
    r"video\.twimg\.com|/avatar|profileIcon|default_profile|/image/|/img/|\.m3u8|\.mp4|\.webp|\.jpg|\.jpeg|\.png)",
    re.I,
)
SHORT_LINK_RE = re.compile(r"^https?://(?:t\.co|bit\.ly|tinyurl\.com|ow\.ly|buff\.ly)/[A-Za-z0-9_-]+/?$", re.I)
DATE_ONLY_RE = re.compile(
    r"^\d{1,4}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?$|"
    r"^\d+\s*(?:day(?:\(s\))?|days?|hour(?:\(s\))?|hours?|minute(?:\(s\))?|minutes?)\s+ago$",
    re.I,
)
NOISE_WORDS = {"community", "user", "profile", "avatar", "image", "photo", "更多", "展开", "查看", "分享"}
PLATFORM_INTENT_PRIORITY = {
    "xhs": [
        "latest_news",
        "news",
        "competitor_and_monetization",
        "user_discussion",
        "seo_page_type",
        "search_intent",
        "expert_signal",
        "official_capability",
        "api_feasibility",
    ],
    "x": [
        "latest_news",
        "news",
        "expert_signal",
        "competitor_and_monetization",
        "user_discussion",
        "official_capability",
        "api_feasibility",
        "seo_page_type",
        "search_intent",
    ],
    "reddit": [
        "latest_news",
        "news",
        "user_discussion",
        "competitor_and_monetization",
        "expert_signal",
        "official_capability",
        "api_feasibility",
        "seo_page_type",
        "search_intent",
    ],
}

BRAND_DEFS = [
    {"key": "kling", "zh": "可灵", "en": "Kling", "aliases": ["可灵", "Kling", "Kling AI"]},
    {"key": "runway", "zh": "Runway", "en": "Runway", "aliases": ["Runway", "RunwayML", "Runway ML"]},
    {"key": "pika", "zh": "Pika", "en": "Pika", "aliases": ["Pika", "Pika Labs"]},
    {"key": "veo", "zh": "Veo", "en": "Veo", "aliases": ["Veo", "Google Veo"]},
    {"key": "sora", "zh": "Sora", "en": "Sora", "aliases": ["Sora", "OpenAI Sora"]},
    {"key": "luma", "zh": "Luma", "en": "Luma", "aliases": ["Luma", "Luma Dream Machine", "Dream Machine"]},
    {"key": "wan", "zh": "Wan", "en": "Wan", "aliases": ["Wan", "Wan 2.1", "通义万相", "万相"]},
    {"key": "jimeng", "zh": "即梦", "en": "Jimeng", "aliases": ["即梦", "Jimeng"]},
    {"key": "hailuo", "zh": "海螺", "en": "Hailuo", "aliases": ["海螺", "Hailuo", "MiniMax"]},
    {"key": "midjourney", "zh": "Midjourney", "en": "Midjourney", "aliases": ["Midjourney", "MJ"]},
    {"key": "flux", "zh": "Flux", "en": "Flux", "aliases": ["Flux", "FLUX.1"]},
    {"key": "ideogram", "zh": "Ideogram", "en": "Ideogram", "aliases": ["Ideogram"]},
    {"key": "cursor", "zh": "Cursor", "en": "Cursor", "aliases": ["Cursor"]},
    {"key": "windsurf", "zh": "Windsurf", "en": "Windsurf", "aliases": ["Windsurf", "Codeium Windsurf"]},
    {"key": "claude_code", "zh": "Claude Code", "en": "Claude Code", "aliases": ["Claude Code"]},
    {"key": "github_copilot", "zh": "GitHub Copilot", "en": "GitHub Copilot", "aliases": ["GitHub Copilot", "Copilot"]},
    {"key": "gamma", "zh": "Gamma", "en": "Gamma", "aliases": ["Gamma"]},
    {"key": "tome", "zh": "Tome", "en": "Tome", "aliases": ["Tome"]},
    {"key": "beautiful_ai", "zh": "Beautiful.ai", "en": "Beautiful.ai", "aliases": ["Beautiful.ai", "Beautiful AI"]},
]
BRAND_BY_KEY = {brand["key"]: brand for brand in BRAND_DEFS}
CATEGORY_DEFAULT_BRANDS = [
    (re.compile(r"AI\s*视频|AI\s*video|video generator|text.?to.?video|image.?to.?video", re.I), ["kling", "runway", "pika"]),
    (re.compile(r"AI\s*(?:图片|图像)|AI\s*image|image generator|text.?to.?image", re.I), ["midjourney", "flux", "ideogram"]),
    (re.compile(r"AI\s*编程|AI\s*coding|coding tools?|code assistant|developer tools?", re.I), ["cursor", "windsurf", "claude_code"]),
    (re.compile(r"AI\s*PPT|presentation generator|slide deck|slides?", re.I), ["gamma", "tome", "beautiful_ai"]),
]
STABLE_SOCIAL_INTENTS = {
    "user_discussion",
    "competitor_and_monetization",
    "expert_signal",
    "seo_page_type",
    "search_intent",
}
SOCIAL_INTENT_LATEST = "latest_news"
SOCIAL_INTENT_BRAND_COMPARE = "brand_compare"
SOCIAL_INTENT_CATEGORY_COMPARE = "category_compare"
SOCIAL_INTENT_OPPORTUNITY = "opportunity_discovery"
SOCIAL_INTENT_VALIDATION = "validation"
SOCIAL_INTENT_BUILD_PROCESS = "build_process"
SOCIAL_INTENT_USER_PAIN = "user_pain"
SOCIAL_INTENT_EXPERT = "expert_signal"
SOCIAL_INTENT_GENERAL = "general"


def read_input() -> Dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        raise SystemExit("请通过 stdin 提供包含 search_plan 的 JSON。")
    return json.loads(raw)


def load_dotenv_if_present() -> None:
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[1] / ".env",
    ]
    for path in candidates:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"'")
                if key and key not in os.environ:
                    os.environ[key] = value
        return


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def is_enabled() -> bool:
    return env_flag("INFO_ALCHEMIST_ENABLE_TIKHUB", False)


def tikhub_api_base() -> str:
    base = os.environ.get("TIKHUB_API_BASE", DEFAULT_TIKHUB_API_BASE).strip() or DEFAULT_TIKHUB_API_BASE
    return base.rstrip("/")


def int_env(name: str, default: int, minimum: int = 0) -> int:
    raw = os.environ.get(name, str(default))
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def request_timeout_seconds() -> int:
    return int_env("TIKHUB_REQUEST_TIMEOUT_SECONDS", DEFAULT_TIKHUB_TIMEOUT_SECONDS, 1)


def query_retries(platform: str) -> int:
    if platform == "wechat":
        return int_env("TIKHUB_WECHAT_RETRIES", DEFAULT_TIKHUB_WECHAT_RETRIES, 0)
    return int_env("TIKHUB_QUERY_RETRIES", DEFAULT_TIKHUB_QUERY_RETRIES, 0)


def is_non_retryable_error(error: str) -> bool:
    return bool(re.search(r"HTTP\s+(?:400|401|402|403|404)", error or "", re.I))


def search_concurrency(task_count: int) -> int:
    return min(int_env("TIKHUB_SEARCH_CONCURRENCY", DEFAULT_TIKHUB_CONCURRENCY, 1), max(1, task_count))


def max_queries() -> int:
    return int_env("TIKHUB_MAX_QUERIES", DEFAULT_TIKHUB_MAX_QUERIES, 0)


def results_per_group() -> int:
    return int_env("TIKHUB_RESULTS_PER_GROUP", DEFAULT_TIKHUB_RESULTS_PER_GROUP, 1)


def configured_platforms() -> List[str]:
    raw = os.environ.get("TIKHUB_PLATFORMS", "xhs,x,reddit")
    platforms = []
    for part in raw.split(","):
        name = PLATFORM_ALIASES.get(part.strip().lower())
        if name and name not in platforms:
            platforms.append(name)
    return platforms or ["xhs", "x", "reddit"]


def cache_identity() -> Dict[str, Any]:
    return {
        "enabled": is_enabled(),
        "api_base": tikhub_api_base(),
        "platforms": configured_platforms() if is_enabled() else [],
        "max_queries": max_queries() if is_enabled() else 0,
        "results_per_group": results_per_group() if is_enabled() else 0,
        "query_rewrite_strategy": QUERY_REWRITE_STRATEGY_VERSION if is_enabled() else "",
        "platform_time_strategy": PLATFORM_TIME_STRATEGY_VERSION if is_enabled() else "",
    }


def should_search_item(item: Dict[str, Any]) -> bool:
    return bool(item.get("query"))


def selected_search_plan(search_plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    selected = []
    limit = max_queries()
    for item in search_plan:
        if should_search_item(item):
            selected.append(item)
        if limit and len(selected) >= limit:
            break
    return selected


def item_priority_for_platform(item: Dict[str, Any], platform: str) -> int:
    intent = str(item.get("search_intent") or "")
    priority = PLATFORM_INTENT_PRIORITY.get(platform, [])
    try:
        return priority.index(intent)
    except ValueError:
        return len(priority) + 1


def select_item_for_platform(search_plan: List[Dict[str, Any]], platform: str) -> Dict[str, Any] | None:
    candidates = selected_search_plan(search_plan)
    if not candidates:
        return None
    indexed = list(enumerate(candidates))
    _, item = min(indexed, key=lambda pair: (item_priority_for_platform(pair[1], platform), pair[0]))
    return item


def platform_search_tasks(
    search_plan: List[Dict[str, Any]],
    topic: str = "",
    context: Dict[str, Any] | None = None,
) -> List[Tuple[Dict[str, Any], str]]:
    tasks: List[Tuple[Dict[str, Any], str]] = []
    for platform in configured_platforms():
        item = select_item_for_platform(search_plan, platform)
        if item:
            tasks.append((platform_item(item, platform, topic, context=context), platform))
    return tasks


def clean_query_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).strip(" ：:，,。；;")


def infer_topic_from_query(query: str) -> str:
    topic = clean_query_text(query)
    for pattern in TOPIC_SUFFIX_PATTERNS:
        topic = re.sub(pattern, "", topic, flags=re.I).strip()
    return topic or clean_query_text(query)


def is_generic_bad_topic(topic: str) -> bool:
    compact = re.sub(r"\s+", "", clean_query_text(topic)).lower()
    if not compact:
        return True
    return compact in {
        "现在",
        "最近",
        "现在最近",
        "最新",
        "热门",
        "比较火",
        "火的",
        "这个方向",
        "这个产品",
        "这个机会",
        "当前市场",
        "news",
    }


def normalize_topic_for_english(topic: str) -> str:
    output = clean_query_text(topic)
    output = re.sub(r"^(?:现在|最近|最新|热门|比较火|很火|火的|头部)\s*(?:的)?\s*", "", output, flags=re.I)
    for pattern, replacement in EN_TOPIC_REPLACEMENTS:
        output = re.sub(pattern, replacement, output, flags=re.I)
    return clean_query_text(output)


def normalize_topic_for_chinese(topic: str) -> str:
    output = clean_query_text(topic)
    output = re.sub(r"^(?:现在|最近|最新|热门|比较火|很火|火的|头部)\s*(?:的)?\s*", "", output, flags=re.I)
    for pattern, replacement in ZH_TOPIC_REPLACEMENTS:
        output = re.sub(pattern, replacement, output, flags=re.I)
    return clean_query_text(output)


def compact_context_text(item: Dict[str, Any], topic: str = "", context: Dict[str, Any] | None = None) -> str:
    parts = [
        topic,
        str(item.get("_topic") or ""),
        str(item.get("topic") or ""),
        str(item.get("source_query") or ""),
        str(item.get("query") or ""),
        str(item.get("reason") or ""),
    ]
    if context:
        parts.extend([
            str(context.get("user_query") or ""),
            str(context.get("topic") or ""),
            str(context.get("query_type") or ""),
            str(context.get("report_mode") or ""),
            str(context.get("action_context") or ""),
            str(context.get("decision_context") or ""),
            " ".join(str(value) for value in (context.get("research_dimensions") or [])),
        ])
    return clean_query_text(" ".join(part for part in parts if part))


def user_facing_context_text(item: Dict[str, Any], topic: str = "", context: Dict[str, Any] | None = None) -> str:
    parts: List[str] = []
    if context:
        parts.extend([
            str(context.get("user_query") or ""),
            str(context.get("topic") or ""),
            str(context.get("decision_context") or ""),
            " ".join(str(value) for value in (context.get("research_dimensions") or [])),
        ])
        parts.append(topic)
        return clean_query_text(" ".join(part for part in parts if part))
    return clean_query_text(" ".join([
        topic,
        str(item.get("_topic") or ""),
        str(item.get("topic") or ""),
        str(item.get("source_query") or ""),
        str(item.get("query") or ""),
    ]))


def strip_social_question_terms(topic: str) -> str:
    output = clean_query_text(topic)
    output = re.sub(r"^(?:我想|帮我|查一下|了解一下|看一下|现在|目前|最近|最新|比较火的?|热门|有哪些|有什么|哪些|什么|有没有|是否|怎么|如何|能不能|可不可以|值不值得|适不适合)\s*", "", output, flags=re.I)
    output = re.sub(
        r"(?:有哪些|有什么|哪些|什么|值得做的?|可以做的?|适合做的?|"
        r"还有机会吗?|有没有机会|是否值得|值不值得|是不是红海|红海吗?|"
        r"怎么做|如何做|怎么建|如何建|吗)$",
        "",
        output,
        flags=re.I,
    )
    output = re.sub(
        r"(?:竞品|对比|比较|定价|商业模式|费用|商用|替代方案|替代|吐槽|投诉|评价|"
        r"推荐|教程|榜单|痛点|需求|踩坑|机会|方向|赛道|值得做|可以做|适合做|"
        r"怎么做|如何做|怎么建|如何建|冷启动|获客|上线|案例|经验|参考)",
        " ",
        output,
        flags=re.I,
    )
    output = re.sub(
        r"\b(?:competitors?|alternatives?|pricing|business model|commercial|reviews?|complaints?|"
        r"tutorials?|recommendations?|founders?|practitioners?|case studies|lessons learned|"
        r"market size|growth trend|report|product hunt|reddit|worth doing|startup ideas?)\b",
        " ",
        output,
        flags=re.I,
    )
    output = re.sub(r"\s+", " ", output).strip(" 的：:，,。；;？?")
    return clean_query_text(output or topic)


def social_category_subject(text: str, platform: str) -> str:
    text = clean_query_text(text)
    if not text:
        return ""
    is_zh = platform in {"xhs", "wechat"}
    if re.search(r"AI\s*PPT|PPT\s*AI|presentation generator|slide deck|slides?", text, re.I):
        return "AI PPT工具" if is_zh else "AI presentation tools"
    if re.search(r"AI\s*视频|AI\s*video|video generator|text.?to.?video|image.?to.?video", text, re.I):
        return "AI视频生成工具" if is_zh else "AI video generator tools"
    if re.search(r"AI\s*(?:图片|图像)|AI\s*image|image generator|text.?to.?image", text, re.I):
        return "AI图片生成工具" if is_zh else "AI image generator tools"
    if re.search(r"AI\s*编程|AI\s*coding|coding tools?|code assistant|developer tools?", text, re.I):
        return "AI编程工具" if is_zh else "AI coding tools"
    if re.search(r"AI\s*SEO|SEO\s*AI|AI\s*工具站.*SEO|SEO.*AI\s*工具站", text, re.I):
        return "AI工具站 SEO" if is_zh else "AI SEO tools"
    if is_broad_ai_tool_topic(text):
        if is_zh:
            return "AI工具站" if re.search(r"工具站", text, re.I) else "AI工具"
        return "AI tools"
    return ""


def is_broad_ai_tool_topic(topic: str) -> bool:
    text = clean_query_text(topic)
    if re.search(r"SEO|视频|图片|图像|编程|写作|PPT|presentation|coding|image|video|writing", text, re.I):
        return False
    return bool(
        re.search(r"\bAI\b|人工智能", text, re.I)
        and re.search(r"产品|工具|工具站|可以做|值得做|适合做|方向|机会|赛道|products?|tools?", text, re.I)
    )


def social_subject_for_platform(topic: str, platform: str, social_intent: str = "", context_text: str = "") -> str:
    combined = clean_query_text(" ".join(part for part in [context_text, topic] if part))
    category_subject = social_category_subject(combined, platform)
    if category_subject:
        if platform in {"xhs", "wechat"} and social_intent == SOCIAL_INTENT_OPPORTUNITY and category_subject == "AI工具站":
            return "AI工具"
        return category_subject
    cleaned = strip_social_question_terms(topic)
    if is_broad_ai_tool_topic(cleaned):
        if platform in {"xhs", "wechat"}:
            return "AI工具" if social_intent == SOCIAL_INTENT_OPPORTUNITY else "AI工具站"
        return "AI tools"
    if platform in {"xhs", "wechat"}:
        return normalize_topic_for_chinese(cleaned)
    return normalize_topic_for_english(cleaned)


def topic_for_item(item: Dict[str, Any]) -> str:
    for key in ["_topic", "topic"]:
        value = clean_query_text(str(item.get(key) or ""))
        if value and value != "news" and not is_generic_bad_topic(value):
            return value
    inferred = infer_topic_from_query(str(item.get("source_query") or item.get("query") or ""))
    return "" if is_generic_bad_topic(inferred) else inferred


def brand_alias_position(text: str, alias: str) -> int | None:
    if not text or not alias:
        return None
    if re.fullmatch(r"[A-Za-z0-9 ._-]+", alias):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(alias).replace(r"\ ", r"\s+") + r"(?![A-Za-z0-9])"
        match = re.search(pattern, text, re.I)
        return match.start() if match else None
    index = text.find(alias)
    return index if index >= 0 else None


def extract_brand_keys_from_texts(*texts: str) -> List[str]:
    positions: Dict[str, int] = {}
    for text in texts:
        text = str(text or "")
        for brand in BRAND_DEFS:
            best: int | None = None
            for alias in brand["aliases"]:
                position = brand_alias_position(text, alias)
                if position is not None and (best is None or position < best):
                    best = position
            if best is not None and (brand["key"] not in positions or best < positions[brand["key"]]):
                positions[brand["key"]] = best
    return [key for key, _ in sorted(positions.items(), key=lambda pair: pair[1])]


def default_brand_keys_for_topic(*texts: str) -> List[str]:
    combined = " ".join(str(text or "") for text in texts)
    for pattern, keys in CATEGORY_DEFAULT_BRANDS:
        if pattern.search(combined):
            return keys[:]
    return []


def brand_display_name(key: str, platform: str) -> str:
    brand = BRAND_BY_KEY.get(key, {})
    return str(brand.get("zh" if platform in {"xhs", "wechat"} else "en") or key)


def is_ai_video_context(*texts: str) -> bool:
    combined = " ".join(str(text or "") for text in texts)
    return bool(re.search(r"AI\s*视频|AI\s*video|video generator|text.?to.?video|image.?to.?video", combined, re.I))


def brand_subject_info(item: Dict[str, Any], topic: str, platform: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    context_text = user_facing_context_text(item, topic, context)
    texts = [context_text]
    brand_keys = extract_brand_keys_from_texts(*texts)
    source = "explicit"
    if not brand_keys:
        source = "none"
    brand_keys = brand_keys[:3]
    brand_names = [brand_display_name(key, platform) for key in brand_keys]
    subject = " ".join(brand_names)
    if subject and platform in {"x", "reddit"} and is_ai_video_context(*texts):
        subject = f"{subject} AI video"
    return {
        "version": QUERY_REWRITE_STRATEGY_VERSION,
        "topic": topic,
        "brand_source": source,
        "brand_keys": brand_keys,
        "brand_names": brand_names,
        "subject": subject,
    }


def infer_social_query_intent(
    item: Dict[str, Any],
    topic: str,
    context: Dict[str, Any] | None = None,
) -> str:
    intent = str(item.get("search_intent") or "")
    text = user_facing_context_text(item, topic, context)
    explicit_brand_keys = extract_brand_keys_from_texts(text)

    if wants_news_mode(item) or intent in {"latest_news", "news"}:
        return SOCIAL_INTENT_LATEST
    if intent in {"official_capability", "api_feasibility"}:
        return SOCIAL_INTENT_GENERAL
    if re.search(r"竞品|对比|比较|定价|商业模式|费用|商用|competitors?|pricing|business model|commercial", text, re.I):
        return SOCIAL_INTENT_BRAND_COMPARE if explicit_brand_keys else SOCIAL_INTENT_CATEGORY_COMPARE
    if re.search(r"吐槽|踩坑|投诉|评价|不好用|complaints?|reviews?|alternatives?", text, re.I):
        return SOCIAL_INTENT_USER_PAIN
    if explicit_brand_keys and re.search(r"\bvs\b|对比|比较|哪个好|哪家|替代|竞品|alternatives?|compare|pricing|complaints?", text, re.I):
        return SOCIAL_INTENT_BRAND_COMPARE
    if re.search(r"怎么做|如何做|怎么建|如何建|搭建|建站|上线|launch|how to build|build in public", text, re.I):
        return SOCIAL_INTENT_BUILD_PROCESS
    if re.search(r"有没有机会|还有机会|是否值得|值不值得|值得切入|切入吗|能不能做|可不可做|红海|可行|验证|validate|worth doing", text, re.I):
        return SOCIAL_INTENT_VALIDATION
    if re.search(r"有哪些.*值得做|值得做|可以做|适合做|做什么|什么值得做|产品机会|新产品|方向|赛道|idea", text, re.I):
        return SOCIAL_INTENT_OPPORTUNITY
    if intent == "user_discussion":
        return SOCIAL_INTENT_USER_PAIN
    if intent == "expert_signal":
        return SOCIAL_INTENT_EXPERT
    if intent == "competitor_and_monetization":
        return SOCIAL_INTENT_CATEGORY_COMPARE
    return SOCIAL_INTENT_GENERAL


def chinese_query_for_social_intent(subject: str, social_intent: str, latest: bool) -> str:
    topic = normalize_topic_for_chinese(subject)
    if social_intent == SOCIAL_INTENT_CATEGORY_COMPARE:
        return f"{topic} 对比 定价 商用"
    if social_intent == SOCIAL_INTENT_OPPORTUNITY:
        return f"{topic} 需求 痛点 付费"
    if social_intent == SOCIAL_INTENT_VALIDATION:
        return f"{topic} 需求 痛点 付费"
    if social_intent == SOCIAL_INTENT_BUILD_PROCESS:
        return f"{topic} 建站 经验"
    if social_intent == SOCIAL_INTENT_USER_PAIN:
        return f"{topic} 吐槽 踩坑 替代"
    if social_intent == SOCIAL_INTENT_LATEST or latest:
        return f"{topic} 最新"
    return f"{topic} 体验"


def english_query_for_social_intent(subject: str, social_intent: str, platform: str, latest: bool) -> str:
    topic = normalize_topic_for_english(subject)
    if social_intent == SOCIAL_INTENT_CATEGORY_COMPARE:
        if platform == "reddit":
            return f"{topic} complaints alternatives pricing"
        return f"{topic} pricing competitors"
    if social_intent == SOCIAL_INTENT_OPPORTUNITY:
        if platform == "reddit":
            return f"{topic} people pay complaints"
        return f"{topic} indie hackers revenue launch"
    if social_intent == SOCIAL_INTENT_VALIDATION:
        if platform == "reddit":
            return f"{topic} problems worth paying for"
        return f"{topic} pain points startup ideas"
    if social_intent == SOCIAL_INTENT_BUILD_PROCESS:
        if platform == "reddit":
            return f"{topic} how did you build launch"
        return f"{topic} indie hacker build in public"
    if social_intent == SOCIAL_INTENT_USER_PAIN:
        return f"{topic} pain points complaints" if platform == "x" else f"{topic} complaints alternatives"
    if social_intent == SOCIAL_INTENT_EXPERT:
        return f"{topic} founders practitioners"
    if social_intent == SOCIAL_INTENT_LATEST or latest:
        return f"{topic} latest discussion"
    return f"{topic} discussion reviews"


def query_subject(item: Dict[str, Any], topic: str, platform: str, context: Dict[str, Any] | None = None) -> Tuple[str, Dict[str, Any]]:
    info = brand_subject_info(item, topic, platform, context)
    if info["subject"]:
        return str(info["subject"]), info
    context_text = user_facing_context_text(item, topic, context)
    normalized = social_subject_for_platform(topic, platform, context_text=context_text)
    info["subject"] = normalized
    return normalized, info


def chinese_social_query(subject: str, intent: str, platform: str, latest: bool) -> str:
    topic = normalize_topic_for_chinese(subject)
    if platform == "xhs":
        if intent in {"official_capability", "api_feasibility"}:
            return f"{topic} 商用 费用"
        if intent == "competitor_and_monetization":
            return f"{topic} 对比 费用"
        if intent == "user_discussion":
            return f"{topic} 踩坑"
        if intent == "search_intent":
            return f"{topic} 教程 推荐"
        if intent == "seo_page_type":
            return f"{topic} 推荐 对比"
        if intent == "expert_signal":
            return f"{topic} 创始人"
        if latest:
            return f"{topic} 最新"
        return f"{topic} 体验"
    if intent in {"official_capability", "api_feasibility"}:
        return f"{topic} 商用 费用"
    if intent == "competitor_and_monetization":
        return f"{topic} 深度对比"
    if intent == "user_discussion":
        if platform == "wechat":
            return f"{topic} 痛点 案例"
        return f"{topic} 踩坑"
    if intent == "search_intent":
        return f"{topic} 教程 推荐"
    if intent == "seo_page_type":
        return f"{topic} 榜单 对比"
    if intent == "expert_signal":
        return f"{topic} 创始人 访谈"
    if latest:
        return f"{topic} 最新动态"
    return f"{topic} 讨论"


def english_social_query(subject: str, intent: str, latest: bool) -> str:
    topic = normalize_topic_for_english(subject)
    if intent in {"official_capability", "api_feasibility"}:
        return f"{topic} pricing limits"
    if intent == "competitor_and_monetization":
        return f"{topic} competitors alternatives pricing"
    if intent == "user_discussion":
        return f"{topic} complaints alternatives"
    if intent == "search_intent":
        return f"{topic} tutorial alternatives"
    if intent == "seo_page_type":
        return f"{topic} best alternatives"
    if intent == "expert_signal":
        return f"{topic} founders practitioners"
    if latest:
        return f"{topic} latest discussion"
    return f"{topic} discussion reviews"


def rewrite_query_for_platform_details(
    item: Dict[str, Any],
    platform: str,
    default_topic: str = "",
    context: Dict[str, Any] | None = None,
) -> Tuple[str, Dict[str, Any]]:
    source_query = clean_query_text(str(item.get("query") or ""))
    item_with_topic = dict(item)
    if default_topic and not is_generic_bad_topic(default_topic) and not item_with_topic.get("_topic") and not item_with_topic.get("topic"):
        item_with_topic["_topic"] = default_topic
    topic = topic_for_item(item_with_topic)
    if not topic:
        return source_query, {
            "version": QUERY_REWRITE_STRATEGY_VERSION,
            "topic": "",
            "brand_source": "none",
            "brand_keys": [],
            "brand_names": [],
            "subject": source_query,
            "social_query_intent": SOCIAL_INTENT_GENERAL,
        }
    intent = str(item.get("search_intent") or "")
    latest = wants_latest(item)
    social_intent = infer_social_query_intent(item_with_topic, topic, context)
    if social_intent in {
        SOCIAL_INTENT_CATEGORY_COMPARE,
        SOCIAL_INTENT_OPPORTUNITY,
        SOCIAL_INTENT_VALIDATION,
        SOCIAL_INTENT_BUILD_PROCESS,
        SOCIAL_INTENT_USER_PAIN,
    }:
        context_text = user_facing_context_text(item_with_topic, topic, context)
        if social_intent == SOCIAL_INTENT_USER_PAIN and extract_brand_keys_from_texts(context_text):
            subject, subject_info = query_subject(item_with_topic, topic, platform, context)
        else:
            subject = social_subject_for_platform(topic, platform, social_intent, context_text=context_text)
            subject_info = {
                "version": QUERY_REWRITE_STRATEGY_VERSION,
                "topic": topic,
                "brand_source": "none",
                "brand_keys": [],
                "brand_names": [],
                "subject": subject,
            }
        if platform in {"xhs", "wechat"}:
            query = chinese_query_for_social_intent(subject, social_intent, latest)
        elif platform in {"x", "reddit"}:
            query = english_query_for_social_intent(subject, social_intent, platform, latest)
        else:
            query = source_query
    else:
        subject, subject_info = query_subject(item_with_topic, topic, platform, context)
        if platform in {"xhs", "wechat"}:
            query = chinese_social_query(subject, intent, platform, latest)
        elif platform in {"x", "reddit"}:
            query = english_social_query(subject, intent, latest)
        else:
            query = source_query
    subject_info["query"] = query
    subject_info["intent"] = intent
    subject_info["social_query_intent"] = social_intent
    subject_info["latest_requested"] = latest
    return query, subject_info


def rewrite_query_for_platform(item: Dict[str, Any], platform: str, default_topic: str = "") -> str:
    query, _ = rewrite_query_for_platform_details(item, platform, default_topic)
    return query


def platform_item(
    item: Dict[str, Any],
    platform: str,
    default_topic: str = "",
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    output = dict(item)
    source_query = clean_query_text(str(item.get("query") or ""))
    output["source_query"] = source_query
    if default_topic and not is_generic_bad_topic(default_topic) and not output.get("_topic") and not output.get("topic"):
        output["_topic"] = default_topic
    output["query"], output["_query_debug"] = rewrite_query_for_platform_details(output, platform, default_topic, context)
    return output


def wants_latest(item: Dict[str, Any]) -> bool:
    query = str(item.get("query") or "")
    return (
        item.get("topic") == "news"
        or item.get("time_range") in {"day", "week"}
        or bool(re.search(r"最新|最近|今日|今天|latest|new|this week|today", query, re.I))
    )


def wants_news_mode(item: Dict[str, Any]) -> bool:
    intent = str(item.get("search_intent") or "")
    if item.get("topic") == "news" or intent in {"latest_news", "news"}:
        return True
    if intent in STABLE_SOCIAL_INTENTS:
        return False
    query = " ".join([
        str(item.get("source_query") or ""),
        str(item.get("query") or ""),
        str(item.get("reason") or ""),
    ])
    return bool(re.search(r"今日|今天|最新消息|刚发布|上线|发布|latest news|breaking|released|launch(?:ed)?|announcement", query, re.I))


def platform_time_strategy(platform: str, item: Dict[str, Any]) -> Dict[str, Any]:
    latest = wants_latest(item)
    if platform == "reddit":
        return {
            "version": PLATFORM_TIME_STRATEGY_VERSION,
            "mode": "relevance_all",
            "sort": "RELEVANCE",
            "time_range": "all",
            "latest_requested": latest,
            "reason": "Reddit 用户讨论优先按相关性和全时间搜索，避免一周窗口漏掉高相关讨论帖。",
        }
    if platform == "x":
        news_mode = wants_news_mode(item)
        return {
            "version": PLATFORM_TIME_STRATEGY_VERSION,
            "mode": "latest" if news_mode else "top",
            "search_type": "Latest" if news_mode else "Top",
            "latest_requested": latest,
            "reason": "X 只有新闻/发布类查询使用 Latest；专家、竞品和用户讨论默认 Top 以降低实时噪声。",
        }
    if platform == "xhs":
        return {
            "version": PLATFORM_TIME_STRATEGY_VERSION,
            "mode": "recent" if latest else "general",
            "sort_type": "time_descending" if latest else "general",
            "time_filter": "一周内" if latest else "不限",
            "latest_requested": latest,
            "reason": "小红书保留近期窗口，优先看本轮可行动的笔记热度和讨论。",
        }
    if platform == "wechat":
        return {
            "version": PLATFORM_TIME_STRATEGY_VERSION,
            "mode": "recent" if latest else "general",
            "sort_type": "_2" if latest else "_0",
            "latest_requested": latest,
            "reason": "公众号链路保留兼容旧日志，新请求默认不会启用该平台。",
        }
    return {"version": PLATFORM_TIME_STRATEGY_VERSION, "mode": "default", "latest_requested": latest}


def request_params(platform: str, item: Dict[str, Any], variant: str = "") -> Dict[str, Any]:
    query = str(item.get("query") or "")
    strategy = platform_time_strategy(platform, item)
    if platform == "xhs":
        if variant == "app":
            return {
                "keyword": query,
                "page": 1,
                "search_id": "",
                "session_id": "",
                "sort_type": strategy["sort_type"],
                "filter_note_type": "不限",
                "filter_note_time": strategy["time_filter"],
            }
        if variant == "web_v3":
            return {
                "keyword": query,
                "page": 1,
                "sort": strategy["sort_type"],
                "note_type": 0,
            }
        return {
            "keyword": query,
            "page": 1,
            "sort_type": strategy["sort_type"],
            "note_type": "不限",
            "time_filter": strategy["time_filter"],
            "search_id": "",
            "search_session_id": "",
            "source": "explore_feed",
            "ai_mode": 0,
        }
    if platform == "wechat":
        return {
            "keyword": query,
            "offset": 0,
            "sort_type": strategy["sort_type"],
        }
    if platform == "x":
        return {
            "keyword": query,
            "search_type": strategy["search_type"],
        }
    if platform == "reddit":
        return {
            "query": query,
            "search_type": "post",
            "sort": strategy["sort"],
            "time_range": strategy["time_range"],
            "safe_search": "unset",
            "allow_nsfw": "0",
        }
    raise ValueError(f"未知 TikHub 平台：{platform}")


def compact_error_body(body: str) -> str:
    text = " ".join((body or "").split())
    return text[:500]


def tikhub_request(platform: str, item: Dict[str, Any], api_key: str, variant: Dict[str, str] | None = None) -> Dict[str, Any]:
    config = PLATFORM_CONFIG[platform]
    params = request_params(platform, item, variant.get("name", "") if variant else "")
    query_string = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "", [])})
    path = variant.get("path", "") if variant else config["path"]
    url = f"{tikhub_api_base()}{path}?{query_string}"
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "Info-Alchemist/0.3 TikHub",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=request_timeout_seconds()) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        details = compact_error_body(body_text)
        suffix = f"：{details}" if details else ""
        raise RuntimeError(f"{PLATFORM_CONFIG[platform]['label']} 搜索 HTTP {exc.code}{suffix}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{PLATFORM_CONFIG[platform]['label']} 搜索网络请求失败：{exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"垂直社媒搜索返回了非 JSON 响应：{compact_error_body(raw)}") from exc


def parse_count(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip().replace(",", "")
    multiplier = 1
    if text.endswith(("万", "w", "W")):
        multiplier = 10000
        text = text[:-1]
    elif text.endswith(("k", "K")):
        multiplier = 1000
        text = text[:-1]
    try:
        return max(0, int(float(text) * multiplier))
    except ValueError:
        return 0


def first_text(item: Dict[str, Any], keys: List[str]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
    return ""


def first_nested_text(item: Dict[str, Any], keys: List[str]) -> str:
    direct = first_text(item, keys)
    if direct:
        return direct
    for key in NESTED_CONTENT_KEYS:
        value = item.get(key)
        if isinstance(value, dict):
            found = first_nested_text(value, keys)
            if found:
                return found
    return ""


def nested_author(item: Dict[str, Any]) -> str:
    direct = first_text(item, AUTHOR_KEYS)
    if direct:
        return direct
    for key in ["user", "author", "account", "owner", "profile", *NESTED_CONTENT_KEYS]:
        value = item.get(key)
        if isinstance(value, dict):
            found = first_text(value, AUTHOR_KEYS)
            if found:
                return found
    return ""


def nested_id(item: Dict[str, Any], keys: List[str]) -> str:
    direct = first_text(item, keys)
    if direct:
        return direct
    for key in NESTED_CONTENT_KEYS:
        value = item.get(key)
        if isinstance(value, dict):
            found = nested_id(value, keys)
            if found:
                return found
    return ""


def normalize_url(url: str, platform: str) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if platform == "reddit" and url.startswith("/"):
        return f"https://www.reddit.com{url}"
    return url


def nested_url(item: Any, platform: str, seen_nodes: set[int] | None = None) -> str:
    if seen_nodes is None:
        seen_nodes = set()
    if isinstance(item, dict):
        node_id = id(item)
        if node_id in seen_nodes:
            return ""
        seen_nodes.add(node_id)
        for key in URL_KEYS:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return normalize_url(value.strip(), platform)
        preferred_keys = [*NESTED_CONTENT_KEYS, "children", "node", "edges", "main"]
        for key in preferred_keys:
            value = item.get(key)
            if isinstance(value, (dict, list)):
                found = nested_url(value, platform, seen_nodes)
                if found:
                    return found
        for value in item.values():
            if isinstance(value, (dict, list)):
                found = nested_url(value, platform, seen_nodes)
                if found:
                    return found
    elif isinstance(item, list):
        for child in item:
            if isinstance(child, (dict, list)):
                found = nested_url(child, platform, seen_nodes)
                if found:
                    return found
    return ""


def inferred_url(item: Dict[str, Any], platform: str) -> str:
    url = nested_url(item, platform)
    if url:
        return url
    if platform == "xhs":
        note_id = nested_id(item, ["note_id", "noteId", "noteIdStr"])
        if note_id:
            return f"https://www.xiaohongshu.com/explore/{note_id}"
    if platform == "x":
        tweet_id = nested_id(item, ["tweet_id", "tweetId", "rest_id", "id_str", "conversation_id_str"])
        if tweet_id and re.fullmatch(r"\d{8,}", tweet_id):
            return f"https://x.com/i/web/status/{tweet_id}"
    if platform == "reddit":
        fullname = nested_id(item, ["permalink"])
        if fullname:
            return normalize_url(fullname, platform)
    return ""


def metric_summary(item: Any, seen_nodes: set[int] | None = None) -> Tuple[int, str]:
    if seen_nodes is None:
        seen_nodes = set()
    if not isinstance(item, dict):
        if isinstance(item, list):
            for child in item:
                total, summary = metric_summary(child, seen_nodes)
                if total:
                    return total, summary
        return 0, ""
    node_id = id(item)
    if node_id in seen_nodes:
        return 0, ""
    seen_nodes.add(node_id)
    parts = []
    total = 0
    for key in METRIC_KEYS:
        if key not in item:
            continue
        count = parse_count(item.get(key))
        if count:
            total += count
            parts.append(f"{key}={count}")
    if total:
        return total, ", ".join(parts[:5])
    for key in [*NESTED_CONTENT_KEYS, "children", "node", "edges", "main"]:
        value = item.get(key)
        if isinstance(value, (dict, list)):
            nested_total, nested_summary = metric_summary(value, seen_nodes)
            if nested_total:
                return nested_total, nested_summary
    for value in item.values():
        if isinstance(value, (dict, list)):
            nested_total, nested_summary = metric_summary(value, seen_nodes)
            if nested_total:
                return nested_total, nested_summary
    return total, ", ".join(parts[:5])


def is_media_or_short_url(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return bool(MEDIA_URL_RE.search(text) or SHORT_LINK_RE.fullmatch(text))


def is_encoded_noise(value: str) -> bool:
    text = re.sub(r"\s+", "", str(value or "").strip())
    if len(text) < 48 or re.search(r"[\u4e00-\u9fff]", text):
        return False
    if re.fullmatch(r"[A-Za-z0-9+/=_-]+", text):
        return True
    return False


def is_weak_text_only_node(title: str, body: str, url: str) -> bool:
    text = " ".join(part for part in [title, body] if part).strip()
    compact = re.sub(r"\s+", "", text).strip()
    compact_title = re.sub(r"\s+", "", title or "").strip()
    compact_body = re.sub(r"\s+", "", body or "").strip()
    if not compact:
        return not bool(url)
    title_text = str(title or "").strip()
    body_text = str(body or "").strip()
    if title_text and DATE_ONLY_RE.fullmatch(title_text) and (not body_text or DATE_ONLY_RE.fullmatch(body_text)):
        return True
    if body_text and DATE_ONLY_RE.fullmatch(body_text) and (not title_text or DATE_ONLY_RE.fullmatch(title_text)):
        return True
    if compact_title and re.fullmatch(r"\d+(?:[.,]\d+)?", compact_title) and (not compact_body or re.fullmatch(r"\d+(?:[.,]\d+)?", compact_body)):
        return True
    if compact_body and re.fullmatch(r"\d+(?:[.,]\d+)?", compact_body) and (not compact_title or re.fullmatch(r"\d+(?:[.,]\d+)?", compact_title)):
        return True
    if re.fullmatch(r"\d+(?:[.,]\d+)?", compact):
        return True
    if compact.lower() in NOISE_WORDS:
        return True
    if DATE_ONLY_RE.fullmatch(compact):
        return True
    if is_encoded_noise(compact):
        return True
    if not url and not body and len(compact) <= 24 and not re.search(r"[\u4e00-\u9fff]", compact):
        return True
    return False


def is_candidate_noise(title: str, body: str, url: str, platform: str) -> bool:
    text = " ".join([title, body, url])
    if not title and not body and not url:
        return True
    if is_media_or_short_url(url) and len(body) < 40:
        return True
    if is_media_or_short_url(title) or is_media_or_short_url(body):
        return True
    if is_weak_text_only_node(title, body, url):
        return True
    if platform == "reddit" and re.search(r"/gallery/", url or "", re.I) and len(body) < 80:
        return True
    if platform == "xhs" and MEDIA_URL_RE.search(text) and not re.search(r"[\u4e00-\u9fff]", title + body):
        return True
    return False


def candidate_from_dict(item: Dict[str, Any], platform: str) -> Dict[str, Any] | None:
    if {"code", "request_id", "message", "data"}.issubset(set(item.keys())):
        return None
    title = first_nested_text(item, TITLE_KEYS)
    body = first_nested_text(item, CONTENT_KEYS)
    author = nested_author(item)
    url = inferred_url(item, platform)
    if platform == "reddit" and url and not title and not body:
        return None
    if platform == "reddit" and body and not title and not url:
        return None
    if is_candidate_noise(title, body, url, platform):
        return None
    if not any([title, body, url]):
        return None

    metric_total, metrics = metric_summary(item)
    content_parts = []
    if body and body != title:
        content_parts.append(body)
    if author:
        content_parts.append(f"作者/来源：{author}")
    if metrics:
        content_parts.append(f"互动：{metrics}")
    content = "；".join(content_parts)
    if not content:
        content = title or url

    score = min(1.0, 0.4 + (math.log1p(metric_total) / 12.0)) if metric_total else 0.45
    label = PLATFORM_CONFIG[platform]["label"]
    display_title = title or body[:80] or url or label
    return {
        "title": f"[{label}] {display_title[:160]}",
        "url": url,
        "content": content[:800],
        "score": round(score, 4),
        "provider": "tikhub",
        "platform": platform,
        "author": author,
        "metrics": metrics,
        "metric_total": metric_total,
    }


def walk_candidates(value: Any, platform: str, output: List[Dict[str, Any]], seen_nodes: set[int]) -> None:
    if len(output) >= results_per_group() * 6:
        return
    if isinstance(value, dict):
        node_id = id(value)
        if node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        candidate = candidate_from_dict(value, platform)
        if candidate:
            output.append(candidate)
        for child in value.values():
            if isinstance(child, (dict, list)):
                walk_candidates(child, platform, output, seen_nodes)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                walk_candidates(child, platform, output, seen_nodes)


def normalize_results_with_debug(response: Dict[str, Any], platform: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    root = response.get("data") if isinstance(response, dict) and "data" in response else response
    candidates: List[Dict[str, Any]] = []
    walk_candidates(root, platform, candidates, set())
    deduped = []
    seen = set()
    seen_titles = set()
    for candidate in candidates:
        title_key = re.sub(r"^\[[^\]]+\]\s*", "", str(candidate.get("title") or ""))
        title_key = re.sub(r"\s+", "", title_key).lower()
        key = candidate.get("url") or title_key or f"{candidate.get('title')}|{candidate.get('content')[:80]}"
        if key in seen or (title_key and title_key in seen_titles):
            continue
        seen.add(key)
        if title_key:
            seen_titles.add(title_key)
        deduped.append(candidate)
        if len(deduped) >= results_per_group():
            break
    debug = {
        "raw_candidate_count": len(candidates),
        "normalized_count": len(deduped),
        "dropped_candidate_count": max(0, len(candidates) - len(deduped)),
        "sample_titles": [item.get("title", "")[:160] for item in deduped[:3]],
    }
    return deduped, debug


def normalize_results(response: Dict[str, Any], platform: str) -> List[Dict[str, Any]]:
    results, _ = normalize_results_with_debug(response, platform)
    return results


def request_trace(index: int, item: Dict[str, Any], platform: str, variant: Dict[str, str] | None = None) -> Dict[str, Any]:
    variant_name = variant.get("name", "") if variant else ""
    trace = {
        "index": index,
        "platform": platform,
        "platform_label": PLATFORM_CONFIG[platform]["label"],
        "source_query": item.get("source_query", item.get("query", "")),
        "actual_query": item.get("query", ""),
        "search_intent": item.get("search_intent", ""),
        "query_group": item.get("query_group", ""),
        "query_group_label": item.get("query_group_label", ""),
        "request_params": request_params(platform, item, variant_name),
        "time_strategy": platform_time_strategy(platform, item),
        "query_strategy": item.get("_query_debug", {}),
    }
    if variant:
        trace["api_variant"] = variant_name
        trace["api_label"] = variant.get("label", "")
    return trace


def trace_for_result(item: Dict[str, Any]) -> Dict[str, Any]:
    debug = dict(item.get("debug") or {})
    return {
        "platform": item.get("platform", ""),
        "status": item.get("status", ""),
        "source_query": item.get("source_query", item.get("query", "")),
        "actual_query": item.get("query", ""),
        "search_intent": item.get("search_intent", ""),
        "query_group": item.get("query_group", ""),
        "query_group_label": item.get("query_group_label", ""),
        "request_params": debug.get("request_params", {}),
        "time_strategy": debug.get("time_strategy", {}),
        "query_strategy": debug.get("query_strategy", {}),
        "api_variant": debug.get("api_variant", ""),
        "normalized_count": debug.get("normalized_count", len(item.get("results") or [])),
        "raw_candidate_count": debug.get("raw_candidate_count", 0),
        "dropped_candidate_count": debug.get("dropped_candidate_count", 0),
        "sample_titles": debug.get("sample_titles", []),
        "error": item.get("error", ""),
    }


def search_one(index: int, item: Dict[str, Any], platform: str, api_key: str) -> Tuple[int, Dict[str, Any], Dict[str, Any] | None]:
    if platform == "xhs":
        return search_one_xhs(index, item, api_key)

    attempts = []
    response = None
    for attempt in range(query_retries(platform) + 1):
        try:
            response = tikhub_request(platform, item, api_key)
            attempts.append({"attempt": attempt + 1, "status": "ok"})
            break
        except Exception as exc:
            error = str(exc)
            attempts.append({"attempt": attempt + 1, "status": "error", "error": error})
            if is_non_retryable_error(error):
                break
            if attempt < query_retries(platform):
                time.sleep(min(1.2 * (attempt + 1), 5) + random.uniform(0, 0.25))

    label = PLATFORM_CONFIG[platform]["label"]
    base = {
        "query": item.get("query", ""),
        "source_query": item.get("source_query", item.get("query", "")),
        "search_intent": item.get("search_intent", ""),
        "query_group": item.get("query_group", ""),
        "query_group_label": item.get("query_group_label", ""),
        "query_source": item.get("query_source", ""),
        "reason": f"垂直社媒搜索：{label}。{item.get('reason', '')}".strip(),
        "provider": "tikhub",
        "platform": platform,
        "attempts": attempts,
        "debug": request_trace(index, item, platform),
    }
    if response is None:
        error = attempts[-1].get("error", "未知垂直社媒搜索错误") if attempts else "未知垂直社媒搜索错误"
        failed_item = {
            **base,
            "status": "failed",
            "error": f"{label} 搜索失败：{error}",
            "answer": "",
            "results": [],
        }
        failed_query = {
            "query": item.get("query", ""),
            "source_query": item.get("source_query", item.get("query", "")),
            "search_intent": item.get("search_intent", ""),
            "query_group": item.get("query_group", ""),
            "query_group_label": item.get("query_group_label", ""),
            "query_source": item.get("query_source", ""),
            "provider": "tikhub",
            "platform": platform,
            "error": failed_item["error"],
            "attempts": attempts,
            "debug": failed_item.get("debug", {}),
        }
        return index, failed_item, failed_query

    normalized, normalize_debug = normalize_results_with_debug(response, platform)
    base["debug"] = {**base["debug"], **normalize_debug}
    if not normalized:
        empty_item = {
            **base,
            "status": "failed",
            "error": f"{label} 已响应，但未提取到可用结果。",
            "answer": "",
            "results": [],
        }
        empty_query = {
            "query": item.get("query", ""),
            "source_query": item.get("source_query", item.get("query", "")),
            "search_intent": item.get("search_intent", ""),
            "provider": "tikhub",
            "platform": platform,
            "error": empty_item["error"],
            "attempts": attempts,
            "debug": empty_item.get("debug", {}),
        }
        return index, empty_item, empty_query
    answer = f"{label} 返回 {len(normalized)} 条可标准化结果。"
    return index, {
        **base,
        "status": "ok",
        "answer": answer,
        "results": normalized,
    }, None


def search_one_xhs(index: int, item: Dict[str, Any], api_key: str) -> Tuple[int, Dict[str, Any], Dict[str, Any] | None]:
    attempts = []
    base = {
        "query": item.get("query", ""),
        "source_query": item.get("source_query", item.get("query", "")),
        "search_intent": item.get("search_intent", ""),
        "query_group": item.get("query_group", ""),
        "query_group_label": item.get("query_group_label", ""),
        "query_source": item.get("query_source", ""),
        "reason": f"垂直社媒搜索：小红书。{item.get('reason', '')}".strip(),
        "provider": "tikhub",
        "platform": "xhs",
        "attempts": attempts,
        "debug": request_trace(index, item, "xhs", XHS_FALLBACKS[0]),
    }

    last_error = "未知垂直社媒搜索错误"
    for variant in XHS_FALLBACKS:
        response = None
        for attempt in range(query_retries("xhs") + 1):
            try:
                response = tikhub_request("xhs", item, api_key, variant=variant)
                attempts.append({
                    "attempt": attempt + 1,
                    "status": "ok",
                    "api_variant": variant["name"],
                    "api_label": variant["label"],
                })
                break
            except Exception as exc:
                last_error = str(exc)
                attempts.append({
                    "attempt": attempt + 1,
                    "status": "error",
                    "api_variant": variant["name"],
                    "api_label": variant["label"],
                    "error": last_error,
                })
                if is_non_retryable_error(last_error):
                    break
                if attempt < query_retries("xhs"):
                    time.sleep(min(1.2 * (attempt + 1), 5) + random.uniform(0, 0.25))

        if response is None:
            if is_non_retryable_error(last_error):
                break
            continue

        normalized, normalize_debug = normalize_results_with_debug(response, "xhs")
        if normalized:
            debug = {**request_trace(index, item, "xhs", variant), **normalize_debug}
            debug["variants_attempted"] = [
                attempt.get("api_variant", "")
                for attempt in attempts
                if attempt.get("api_variant")
            ]
            return index, {
                **base,
                "status": "ok",
                "api_variant": variant["name"],
                "debug": debug,
                "answer": f"{variant['label']} 返回 {len(normalized)} 条可标准化结果。",
                "results": normalized,
            }, None

        last_error = f"{variant['label']} 已响应，但未提取到可用结果。"
        attempts.append({
            "attempt": 1,
            "status": "empty",
            "api_variant": variant["name"],
            "api_label": variant["label"],
            "error": last_error,
        })

    failed_item = {
        **base,
        "status": "failed",
        "error": f"小红书搜索失败：{last_error}",
        "debug": {
            **base["debug"],
            "variants_attempted": [
                attempt.get("api_variant", "")
                for attempt in attempts
                if attempt.get("api_variant")
            ],
        },
        "answer": "",
        "results": [],
    }
    failed_query = {
        "query": item.get("query", ""),
        "source_query": item.get("source_query", item.get("query", "")),
        "search_intent": item.get("search_intent", ""),
        "query_group": item.get("query_group", ""),
        "query_group_label": item.get("query_group_label", ""),
        "query_source": item.get("query_source", ""),
        "provider": "tikhub",
        "platform": "xhs",
        "error": failed_item["error"],
        "attempts": attempts,
        "debug": failed_item.get("debug", {}),
    }
    return index, failed_item, failed_query


def run_search(
    search_plan: List[Dict[str, Any]],
    api_key: str,
    topic: str = "",
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    tasks = platform_search_tasks(search_plan, topic, context=context)
    if not tasks:
        return {
            "enabled": True,
            "provider": "tikhub",
            "status": "skipped",
            "status_label": "没有符合 TikHub 垂直搜索条件的 query",
            "failed_queries": [],
            "search_results": [],
        }

    indexed_results: list[Dict[str, Any] | None] = [None] * len(tasks)
    failed_queries = []
    with ThreadPoolExecutor(max_workers=search_concurrency(len(tasks))) as executor:
        futures = [
            executor.submit(search_one, index, item, platform, api_key)
            for index, (item, platform) in enumerate(tasks)
        ]
        for future in as_completed(futures):
            index, normalized_item, failed_item = future.result()
            indexed_results[index] = normalized_item
            if failed_item:
                failed_queries.append(failed_item)

    normalized = [item for item in indexed_results if item]
    ok_count = sum(1 for item in normalized if item.get("status") == "ok")
    failed_count = len(failed_queries)
    if ok_count and failed_count:
        status = "partial_failure"
        label = f"垂直社媒搜索部分失败：{failed_count}/{len(normalized)} 个平台查询失败"
    elif failed_count:
        status = "failure"
        label = "垂直社媒搜索全部失败"
    else:
        status = "success"
        label = "垂直社媒搜索全部成功"

    return {
        "enabled": True,
        "provider": "tikhub",
        "api_base": tikhub_api_base(),
        "platforms": configured_platforms(),
        "status": status,
        "status_label": label,
        "failed_queries": failed_queries,
        "search_results": normalized,
        "debug_trace": [trace_for_result(item) for item in normalized],
    }


def execute_search(data: Dict[str, Any] | List[Dict[str, Any]]) -> Dict[str, Any]:
    load_dotenv_if_present()
    if not is_enabled():
        return {
            "enabled": False,
            "provider": "tikhub",
            "status": "disabled",
            "status_label": "垂直社媒搜索未启用",
            "failed_queries": [],
            "search_results": [],
        }

    search_plan = data if isinstance(data, list) else data.get("search_plan", [])
    if not isinstance(search_plan, list) or not search_plan:
        return {
            "enabled": True,
            "provider": "tikhub",
            "status": "failure",
            "status_label": "垂直社媒搜索缺少 search_plan",
            "failed_queries": [],
            "search_results": [],
        }

    api_key = os.environ.get("TIKHUB_API_KEY", "").strip()
    if not api_key or "YOUR" in api_key:
        return {
            "enabled": True,
            "provider": "tikhub",
            "status": "skipped",
            "status_label": "垂直社媒搜索已启用，但缺少 API Key",
            "failed_queries": [],
            "search_results": [],
        }

    return run_search(
        search_plan,
        api_key,
        topic=clean_query_text(str(data.get("topic", ""))) if isinstance(data, dict) else "",
        context=data if isinstance(data, dict) else None,
    )


def main() -> int:
    payload = execute_search(read_input())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if payload.get("status") == "failure" else 0


if __name__ == "__main__":
    raise SystemExit(main())
