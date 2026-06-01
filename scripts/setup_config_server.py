#!/usr/bin/env python3
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler

from info_alchemist_paths import runs_dir, skill_dir


DEFAULT_CONFIG_HOST = "127.0.0.1"
DEFAULT_CONFIG_PORT = 8766
DEFAULT_CONFIG_PORT_SPAN = 100
MANAGED_ENV_KEYS = {
    "TAVILY_API_KEY",
    "INFO_ALCHEMIST_ENABLE_TIKHUB",
    "TIKHUB_API_KEY",
    "TIKHUB_API_BASE",
    "TIKHUB_PLATFORMS",
    "TIKHUB_MAX_QUERIES",
    "TIKHUB_RESULTS_PER_GROUP",
}
PLACEHOLDER_MARKERS = (
    "YOUR",
    "REPLACE",
    "PASTE",
    "TODO",
    "EXAMPLE",
    "PLACEHOLDER",
    "这里",
    "填入",
)
ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")


def env_path() -> Path:
    configured = os.environ.get("INFO_ALCHEMIST_ENV_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return skill_dir() / ".env"


def web_template_path() -> Path:
    return skill_dir() / "web" / "setup-page.html"


def config_host() -> str:
    return os.environ.get("INFO_ALCHEMIST_CONFIG_HOST", DEFAULT_CONFIG_HOST).strip() or DEFAULT_CONFIG_HOST


def config_port() -> int:
    raw = os.environ.get("INFO_ALCHEMIST_CONFIG_PORT", str(DEFAULT_CONFIG_PORT)).strip()
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_CONFIG_PORT
    return port if 1024 <= port <= 65535 else DEFAULT_CONFIG_PORT


def config_port_span() -> int:
    raw = os.environ.get("INFO_ALCHEMIST_CONFIG_PORT_SPAN", str(DEFAULT_CONFIG_PORT_SPAN)).strip()
    try:
        span = int(raw)
    except ValueError:
        return DEFAULT_CONFIG_PORT_SPAN
    return max(1, min(span, 1000))


def is_placeholder(value: str) -> bool:
    compact = value.strip()
    if not compact:
        return True
    upper = compact.upper()
    return any(marker in upper for marker in PLACEHOLDER_MARKERS)


def is_valid_tavily_key(value: str) -> bool:
    key = value.strip()
    return bool(key and key.startswith("tvly-") and not is_placeholder(key))


def is_valid_tikhub_key(value: str) -> bool:
    key = value.strip()
    return bool(key and not is_placeholder(key))


def parse_env_value(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        return cleaned[1:-1]
    return cleaned


def load_env_file(path: Path | None = None) -> Dict[str, str]:
    target = path or env_path()
    if not target.exists():
        return {}
    values: Dict[str, str] = {}
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = ENV_LINE_RE.match(raw_line)
        if not match:
            continue
        values[match.group(1)] = parse_env_value(match.group(2))
    return values


def current_env_values(path: Path | None = None) -> Dict[str, str]:
    values = load_env_file(path)
    for key in MANAGED_ENV_KEYS:
        if os.environ.get(key, "").strip():
            values[key] = os.environ[key].strip()
    return values


def has_valid_tavily_key(path: Path | None = None) -> bool:
    return is_valid_tavily_key(current_env_values(path).get("TAVILY_API_KEY", ""))


def config_status(path: Path | None = None) -> Dict[str, Any]:
    target = path or env_path()
    values = current_env_values(target)
    tikhub_enabled = values.get("INFO_ALCHEMIST_ENABLE_TIKHUB", "").strip().lower() in {"1", "true", "yes", "on"}
    return {
        "ok": True,
        "env_path": str(target),
        "has_tavily_key": is_valid_tavily_key(values.get("TAVILY_API_KEY", "")),
        "tikhub_enabled": tikhub_enabled,
        "has_tikhub_key": is_valid_tikhub_key(values.get("TIKHUB_API_KEY", "")),
    }


def reject_unsafe_value(name: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        raise ValueError(f"{name} 不能包含换行。")
    if len(value) > 4096:
        raise ValueError(f"{name} 太长，请检查是否粘贴错误。")


def env_assignment(key: str, value: str) -> str:
    reject_unsafe_value(key, value)
    if re.search(r"\s|#|'|\"", value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}="{escaped}"'
    return f"{key}={value}"


def retained_env_lines(lines: Iterable[str]) -> list[str]:
    retained: list[str] = []
    previous_blank = False
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        match = ENV_LINE_RE.match(line)
        if match and match.group(1) in MANAGED_ENV_KEYS:
            continue
        if line.strip() == "":
            if previous_blank:
                continue
            previous_blank = True
            retained.append("")
            continue
        previous_blank = False
        retained.append(line)
    while retained and retained[0] == "":
        retained.pop(0)
    while retained and retained[-1] == "":
        retained.pop()
    return retained


def write_env_values(
    tavily_api_key: str,
    enable_tikhub: bool,
    tikhub_api_key: str = "",
    path: Path | None = None,
) -> Path:
    target = path or env_path()
    existing = load_env_file(target)
    tavily_value = tavily_api_key.strip() or existing.get("TAVILY_API_KEY", "").strip()
    tikhub_value = tikhub_api_key.strip() or existing.get("TIKHUB_API_KEY", "").strip()

    if not is_valid_tavily_key(tavily_value):
        raise ValueError("请填写有效的 Tavily API key。")
    if enable_tikhub and not is_valid_tikhub_key(tikhub_value):
        raise ValueError("打开社交平台搜索时，需要填写 TikHub API key。")

    retained = retained_env_lines(target.read_text(encoding="utf-8").splitlines() if target.exists() else [])
    block = [
        "# Info-Alchemist local configuration",
        env_assignment("TAVILY_API_KEY", tavily_value),
        env_assignment("INFO_ALCHEMIST_ENABLE_TIKHUB", "1" if enable_tikhub else "0"),
    ]
    if tikhub_value:
        block.append(env_assignment("TIKHUB_API_KEY", tikhub_value))
    block.extend([
        env_assignment("TIKHUB_API_BASE", existing.get("TIKHUB_API_BASE", "https://api.tikhub.io")),
        env_assignment("TIKHUB_PLATFORMS", existing.get("TIKHUB_PLATFORMS", "xhs,x,reddit")),
        env_assignment("TIKHUB_MAX_QUERIES", existing.get("TIKHUB_MAX_QUERIES", "0")),
        env_assignment("TIKHUB_RESULTS_PER_GROUP", existing.get("TIKHUB_RESULTS_PER_GROUP", "3")),
    ])

    content_lines = block + ([""] + retained if retained else [])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(content_lines).rstrip() + "\n", encoding="utf-8")
    return target


def render_setup_page() -> str:
    status = config_status()
    template = web_template_path().read_text(encoding="utf-8")
    config_json = json.dumps(status, ensure_ascii=False).replace("</", "<\\/")
    return template.replace("__CONFIG_JSON__", config_json)


class ConfigHandler(BaseHTTPRequestHandler):
    server_version = "InfoAlchemistConfig/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/api/status"):
            self.send_json(config_status())
            return
        if self.path not in {"/", "/setup"}:
            self.send_error(404)
            return
        body = render_setup_page().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/api/save":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 16384:
            self.send_json({"ok": False, "error": "提交内容过大，请检查输入。"}, status=413)
            return
        raw_body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw_body or "{}")
            tavily_api_key = str(payload.get("tavily_api_key", "")).strip()
            enable_tikhub = bool(payload.get("enable_tikhub", False))
            tikhub_api_key = str(payload.get("tikhub_api_key", "")).strip()
            target = write_env_values(tavily_api_key, enable_tikhub, tikhub_api_key)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)
            return
        status_payload = config_status(target)
        status_payload["message"] = "配置已保存。"
        self.send_json(status_payload)


def local_url(port: int, path: str = "/setup") -> str:
    return f"http://{config_host()}:{port}{path}"


def can_open_url(url: str, timeout: float = 0.8) -> bool:
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as response:
            return 200 <= getattr(response, "status", 200) < 500
    except (OSError, URLError):
        return False


def can_bind_local_port(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
        return True
    except OSError:
        return False


def candidate_ports() -> list[int]:
    primary = config_port()
    if os.environ.get("INFO_ALCHEMIST_CONFIG_PORT", "").strip():
        return [primary]
    upper = min(primary + config_port_span(), 65536)
    return list(range(primary, upper))


def start_server(port: int) -> None:
    host = config_host()
    httpd = ThreadingHTTPServer((host, port), ConfigHandler)
    httpd.serve_forever()


def ensure_setup_server() -> Dict[str, Any]:
    if os.environ.get("INFO_ALCHEMIST_CONFIG_SERVER_DISABLED") == "1":
        return {
            "ok": True,
            "server_started": False,
            "url": web_template_path().resolve().as_uri(),
            "env_path": str(env_path()),
            "note": "配置服务已被当前环境禁用。",
        }

    for port in candidate_ports():
        status_url = local_url(port, "/api/status")
        if can_open_url(status_url):
            return {
                "ok": True,
                "server_started": False,
                "url": local_url(port),
                "env_path": str(env_path()),
            }
        if not can_bind_local_port(config_host(), port):
            continue
        log_dir = runs_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "setup_config_server.log"
        log_file = log_path.open("ab")
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--serve", "--port", str(port), "--host", config_host()],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
        log_file.close()
        for _ in range(20):
            if can_open_url(status_url, timeout=0.3):
                return {
                    "ok": True,
                    "server_started": True,
                    "url": local_url(port),
                    "env_path": str(env_path()),
                    "log_path": str(log_path),
                }
            time.sleep(0.1)
    raise RuntimeError("本地配置页面启动失败：没有找到可用端口，或当前环境不允许绑定 127.0.0.1。")


def main() -> int:
    parser = argparse.ArgumentParser(description="启动 Info-Alchemist 本地配置页面。")
    parser.add_argument("--serve", action="store_true", help="启动 HTTP 服务。")
    parser.add_argument("--host", default=config_host())
    parser.add_argument("--port", type=int, default=config_port())
    parser.add_argument("--ensure", action="store_true", help="确保配置服务可访问并输出入口。")
    parser.add_argument("--status", action="store_true", help="输出当前配置状态。")
    args = parser.parse_args()

    if args.host:
        os.environ["INFO_ALCHEMIST_CONFIG_HOST"] = args.host
    if args.port:
        os.environ["INFO_ALCHEMIST_CONFIG_PORT"] = str(args.port)

    if args.serve:
        start_server(args.port)
        return 0
    if args.status:
        print(json.dumps(config_status(), ensure_ascii=False, indent=2))
        return 0
    payload = ensure_setup_server()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
