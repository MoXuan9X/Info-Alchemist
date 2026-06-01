#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Tuple

from info_alchemist_paths import cache_dir
from run_log import new_run_id, record_stage
import tikhub_search


DEFAULT_CACHE_TTL_SECONDS = 86400
DEFAULT_TAVILY_API_URL = "https://api.tavily.com/search"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 12
DEFAULT_QUERY_RETRIES = 1
DEFAULT_SEARCH_CONCURRENCY = 6
DEFAULT_STDOUT_TEXT_LIMIT = 240
PLACEHOLDER_KEY_MARKERS = ("YOUR", "REPLACE", "PASTE", "TODO", "EXAMPLE", "PLACEHOLDER", "这里", "填入")
REQUEST_OPTION_FIELDS = {
    "topic",
    "time_range",
    "days",
    "start_date",
    "end_date",
    "include_domains",
    "exclude_domains",
    "country",
    "search_depth",
    "max_results"
}
def read_input() -> Dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        raise SystemExit("请通过 stdin 提供包含 search_plan 的 JSON。")
    return json.loads(raw)


def normalize_result(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "content": item.get("content", ""),
        "score": item.get("score", 0.0)
    }


def text_limit() -> int:
    raw = os.environ.get("INFO_ALCHEMIST_STDOUT_TEXT_LIMIT", str(DEFAULT_STDOUT_TEXT_LIMIT))
    try:
        return max(120, int(raw))
    except ValueError:
        return DEFAULT_STDOUT_TEXT_LIMIT


def truncate_text(value: str, limit: int) -> str:
    text = value or ""
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def compact_for_stdout(payload: Dict[str, Any]) -> Dict[str, Any]:
    if os.environ.get("INFO_ALCHEMIST_STDOUT_FULL") == "1":
        return payload
    limit = text_limit()
    compact = dict(payload)
    compact["stdout_compacted"] = True
    compact["full_results_in_run_log"] = True
    compact_results = []
    for item in payload.get("search_results", []) or []:
        compact_item = dict(item)
        compact_item["answer"] = truncate_text(compact_item.get("answer", ""), limit)
        compact_item["results"] = [
            {
                **result,
                "content": truncate_text(result.get("content", ""), limit)
            }
            for result in (item.get("results") or [])
        ]
        compact_results.append(compact_item)
    compact["search_results"] = compact_results
    return compact


def error_payload(message: str) -> Dict[str, Any]:
    return {
        "search_provider": "tavily",
        "tavily_status": "failure",
        "tavily_status_label": "本轮联网搜索全部失败",
        "error": message,
        "failed_queries": [],
        "search_results": []
    }


def canonical_search_plan(data: Dict[str, Any]) -> Dict[str, Any]:
    plan = []
    for item in data.get("search_plan", []) or []:
        canonical_item = {
            "query": item.get("query", ""),
            "search_intent": item.get("search_intent", ""),
        }
        for field in ["query_group", "query_group_label", "query_source"]:
            if item.get(field):
                canonical_item[field] = item.get(field)
        if os.environ.get("INFO_ALCHEMIST_CACHE_KEY_INCLUDE_REASON") == "1":
            canonical_item["reason"] = item.get("reason", "")
        for field in sorted(REQUEST_OPTION_FIELDS):
            if field in item:
                canonical_item[field] = item.get(field)
        plan.append(canonical_item)
    canonical = {
        "search_plan": plan,
        "time_window": data.get("time_window", "")
    }
    if tikhub_search.is_enabled():
        canonical["vertical_search"] = tikhub_search.cache_identity()
    return canonical


def cache_key(data: Dict[str, Any]) -> str:
    payload = json.dumps(canonical_search_plan(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def cache_ttl_seconds() -> int:
    raw = os.environ.get("INFO_ALCHEMIST_CACHE_TTL_SECONDS", str(DEFAULT_CACHE_TTL_SECONDS))
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_CACHE_TTL_SECONDS


def request_timeout_seconds() -> int:
    raw = os.environ.get("TAVILY_REQUEST_TIMEOUT_SECONDS", str(DEFAULT_REQUEST_TIMEOUT_SECONDS))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS


def query_retries() -> int:
    raw = os.environ.get("TAVILY_QUERY_RETRIES", str(DEFAULT_QUERY_RETRIES))
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_QUERY_RETRIES


def search_concurrency(plan_size: int) -> int:
    raw = os.environ.get("INFO_ALCHEMIST_SEARCH_CONCURRENCY", str(DEFAULT_SEARCH_CONCURRENCY))
    try:
        value = max(1, int(raw))
    except ValueError:
        value = DEFAULT_SEARCH_CONCURRENCY
    return min(value, max(1, plan_size))


def cache_path(key: str) -> Path:
    return cache_dir() / "tavily" / f"{key}.json"


def read_cache(key: str) -> Dict[str, Any] | None:
    if os.environ.get("DISABLE_CACHE") == "1":
        return None
    path = cache_path(key)
    if not path.exists():
        return None
    ttl = cache_ttl_seconds()
    if ttl and time.time() - path.stat().st_mtime > ttl:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    payload["cache"] = {"hit": True, "key": key, "ttl_seconds": ttl}
    return payload


def write_cache(key: str, payload: Dict[str, Any]) -> None:
    if (
        os.environ.get("DISABLE_CACHE") == "1"
        or "error" in payload
        or payload.get("tavily_status") not in {"success", None}
    ):
        return
    vertical_status = (payload.get("vertical_search") or {}).get("status")
    if tikhub_search.is_enabled() and vertical_status not in {"success", "partial_failure"}:
        return
    path = cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    cached = dict(payload)
    cached["cache"] = {"hit": False, "key": key, "ttl_seconds": cache_ttl_seconds()}
    path.write_text(json.dumps(cached, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


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


def tavily_api_url() -> str:
    return os.environ.get("TAVILY_API_URL", DEFAULT_TAVILY_API_URL).strip() or DEFAULT_TAVILY_API_URL


def is_valid_tavily_key(value: str) -> bool:
    key = value.strip()
    if not key or not key.startswith("tvly-"):
        return False
    upper = key.upper()
    return not any(marker in upper for marker in PLACEHOLDER_KEY_MARKERS)


def compact_error_body(body: str) -> str:
    text = " ".join(body.split())
    if not text:
        return ""
    return text[:500]


def tavily_request(item: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    query = item.get("query", "")
    body = {
        "query": query,
        "search_depth": item.get("search_depth", "advanced"),
        "include_answer": True,
        "max_results": item.get("max_results", 5)
    }
    for field in REQUEST_OPTION_FIELDS:
        if field in {"search_depth", "max_results"}:
            continue
        value = item.get(field)
        if value not in (None, "", []):
            body[field] = value
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        tavily_api_url(),
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Info-Alchemist/0.2"
        }
    )
    try:
        with urllib.request.urlopen(request, timeout=request_timeout_seconds()) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        details = compact_error_body(body_text)
        suffix = f"：{details}" if details else ""
        raise RuntimeError(f"联网搜索 HTTP {exc.code}{suffix}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"联网搜索网络请求失败：{exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"联网搜索返回了非 JSON 响应：{compact_error_body(raw)}") from exc


def search_one(index: int, item: Dict[str, Any], api_key: str) -> Tuple[int, Dict[str, Any], Dict[str, Any] | None]:
    query = item.get("query", "")
    if not query:
        return index, {}, None
    attempts = []
    response = None
    for attempt in range(query_retries() + 1):
        try:
            response = tavily_request(item=item, api_key=api_key)
            attempts.append({"attempt": attempt + 1, "status": "ok"})
            break
        except Exception as exc:
            attempts.append({"attempt": attempt + 1, "status": "error", "error": str(exc)})
            if attempt < query_retries():
                time.sleep(min(1.5 * (attempt + 1), 5))

    base = {
        "query": query,
        "search_intent": item.get("search_intent", ""),
        "reason": item.get("reason", ""),
        "evidence_axis": item.get("evidence_axis", ""),
        "evidence_role": item.get("evidence_role", ""),
        "query_group": item.get("query_group", ""),
        "query_group_label": item.get("query_group_label", ""),
        "query_source": item.get("query_source", ""),
        "attempts": attempts,
    }
    if response is None:
        error = attempts[-1].get("error", "未知联网搜索错误") if attempts else "未知联网搜索错误"
        failed_item = {
            **base,
            "status": "failed",
            "error": f"联网搜索失败：{error}",
            "answer": "",
            "results": []
        }
        failed_query = {
            "query": query,
            "search_intent": item.get("search_intent", ""),
            "error": failed_item["error"],
            "attempts": attempts,
        }
        return index, failed_item, failed_query

    return index, {
        **base,
        "status": "ok",
        "answer": response.get("answer", ""),
        "results": [normalize_result(result) for result in response.get("results", [])]
    }, None


def run_search(search_plan: List[Dict[str, Any]], api_key: str) -> Dict[str, Any]:
    indexed_results: list[Dict[str, Any] | None] = [None] * len(search_plan)
    failed_queries = []
    with ThreadPoolExecutor(max_workers=search_concurrency(len(search_plan))) as executor:
        futures = [
            executor.submit(search_one, index, item, api_key)
            for index, item in enumerate(search_plan)
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
        tavily_status = "partial_failure"
        status_label = "本轮联网搜索部分失败"
        error_summary = f"本轮联网搜索部分失败：{failed_count}/{len(normalized)} 条 query 失败，其余结果可用于证据整理。"
    elif failed_count:
        tavily_status = "failure"
        status_label = "本轮联网搜索全部失败"
        error_summary = "本轮联网搜索全部失败，不能生成证据报告。"
    else:
        tavily_status = "success"
        status_label = "本轮联网搜索全部成功"
        error_summary = ""

    payload = {
        "search_provider": "tavily",
        "tavily_status": tavily_status,
        "tavily_status_label": status_label,
        "error_summary": error_summary,
        "failed_queries": failed_queries,
        "search_results": normalized
    }
    if tavily_status == "failure":
        payload["error"] = error_summary
    return payload


def merge_tikhub_payload(payload: Dict[str, Any], vertical_payload: Dict[str, Any]) -> Dict[str, Any]:
    if not vertical_payload or vertical_payload.get("status") == "disabled":
        return payload

    merged = dict(payload)
    vertical_results = vertical_payload.get("search_results", []) or []
    vertical_ok_results = [
        item
        for item in vertical_results
        if item.get("status") == "ok" and item.get("results")
    ]
    vertical_failed = vertical_payload.get("failed_queries", []) or []
    merged["vertical_search"] = {
        "provider": "tikhub",
        "enabled": vertical_payload.get("enabled", False),
        "api_base": vertical_payload.get("api_base", ""),
        "platforms": vertical_payload.get("platforms", []),
        "status": vertical_payload.get("status", ""),
        "status_label": vertical_payload.get("status_label", ""),
        "result_groups": len(vertical_results),
        "successful_groups": len(vertical_ok_results),
        "failed_groups": len(vertical_failed),
        "failed_queries": vertical_failed,
        "debug_trace": vertical_payload.get("debug_trace", []),
    }

    if vertical_ok_results:
        merged["search_results"] = (payload.get("search_results", []) or []) + vertical_ok_results
    if vertical_ok_results:
        merged["search_provider"] = "tavily+tikhub"
        if payload.get("tavily_status") == "failure":
            merged["tavily_status"] = "partial_failure"
            merged["error_summary"] = "主公开搜索全部失败，但垂直社媒搜索返回了可用结果。"
            merged.pop("error", None)
    return merged


def validate_plan_source(data: Dict[str, Any]) -> Dict[str, Any] | None:
    if data.get("search_plan_source") == "build_search_plan.py":
        return None
    return error_payload(
        "search_plan 必须由 scripts/build_search_plan.py 生成，不能手写。"
        "请先运行 build_search_plan.py，并把完整 JSON 输出传给联网搜索脚本。"
    )


def execute_search(data: Dict[str, Any], run_id: str = "", write_run_log: bool = True) -> tuple[Dict[str, Any], int]:
    run_id = str(run_id or data.get("run_id") or os.environ.get("INFO_ALCHEMIST_RUN_ID", "")).strip()
    if not run_id:
        run_id = new_run_id(json.dumps(canonical_search_plan(data), ensure_ascii=False, sort_keys=True))

    def finish(payload: Dict[str, Any], exit_code: int, status: str = "ok") -> tuple[Dict[str, Any], int]:
        payload["run_id"] = run_id
        if write_run_log:
            run_info = record_stage(run_id, "tavily_result", payload, status)
            payload["run_log_path"] = run_info.get("run_log_path", "")
        return payload, exit_code

    source_error = validate_plan_source(data)
    if source_error:
        return finish(source_error, 2, "error")

    search_plan = data.get("search_plan", [])
    if not isinstance(search_plan, list) or not search_plan:
        return finish(error_payload("search_plan 必须是非空列表。"), 2, "error")

    load_dotenv_if_present()
    key = cache_key(data)
    cached = read_cache(key)
    if cached:
        return finish(cached, 0)

    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not is_valid_tavily_key(api_key):
        return finish(error_payload("缺少联网搜索 API Key，或仍在使用占位值。请设置环境变量，或在 skill 目录创建 .env。"), 2, "error")

    try:
        payload = run_search(search_plan, api_key)
        vertical_payload = tikhub_search.execute_search(data)
        payload = merge_tikhub_payload(payload, vertical_payload)
    except Exception as exc:
        return finish(error_payload(f"联网搜索失败：{exc}"), 1, "error")

    write_cache(key, payload)
    payload["cache"] = {"hit": False, "key": key, "ttl_seconds": cache_ttl_seconds()}
    status = "error" if payload.get("tavily_status") == "failure" else "ok"
    exit_code = 1 if payload.get("tavily_status") == "failure" else 0
    return finish(payload, exit_code, status)


def main() -> int:
    data = read_input()
    payload, exit_code = execute_search(data, write_run_log=True)
    print(json.dumps(compact_for_stdout(payload), ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
