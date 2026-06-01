#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path


def read_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data = {}
    parent_key = None
    for line in parts[1].splitlines():
        raw_line = line
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if raw_line.startswith(" ") and parent_key:
            data[f"{parent_key}.{key}"] = value
        else:
            data[key] = value
            parent_key = key if value == "" else None
    return data


def main() -> int:
    skill_dir = Path(__file__).resolve().parents[1]
    skill_md = skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    frontmatter = read_frontmatter(text)
    payload = {
        "ok": True,
        "activation_marker": "INFO_ALCHEMIST_ACTIVATION_V1",
        "skill_display_name": "Info-Alchemist",
        "skill_name": frontmatter.get("name", ""),
        "version": frontmatter.get("version") or frontmatter.get("metadata.version", ""),
        "search_provider": "tavily_search",
        "tavily_script": str(skill_dir / "scripts" / "tavily_search.py"),
        "skill_dir": str(skill_dir),
        "skill_md": str(skill_md),
        "skill_md_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()
    }
    if "--compact" in sys.argv or "--user" in sys.argv:
        print("INFO_ALCHEMIST=TRUE")
        return 0
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
