#!/usr/bin/env python3
import os
from pathlib import Path


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def workspace_dir() -> Path:
    configured = os.environ.get("INFO_ALCHEMIST_WORKSPACE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    root = skill_dir()
    if root.parent.name in {"skill", "skills"}:
        return root.parent.parent
    return root


def data_dir() -> Path:
    configured = os.environ.get("INFO_ALCHEMIST_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return workspace_dir() / "info-alchemist"


def reports_dir() -> Path:
    configured = (
        os.environ.get("INFO_ALCHEMIST_MARKDOWN_REPORT_DIR", "").strip()
        or os.environ.get("INFO_ALCHEMIST_REPORT_DIR", "").strip()
    )
    if configured:
        return Path(configured).expanduser()
    return data_dir() / "reports"


def html_reports_dir() -> Path:
    configured = os.environ.get("INFO_ALCHEMIST_HTML_REPORT_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return reports_dir() / "html"


def drafts_dir() -> Path:
    configured = os.environ.get("INFO_ALCHEMIST_DRAFT_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return data_dir() / "drafts"


def runs_dir() -> Path:
    configured = os.environ.get("INFO_ALCHEMIST_RUN_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return data_dir() / "runs"


def memory_dir() -> Path:
    configured = os.environ.get("INFO_ALCHEMIST_MEMORY_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return data_dir() / "memory"


def records_file() -> Path:
    configured = os.environ.get("INFO_ALCHEMIST_RECORDS_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return memory_dir() / "alchemy_records.jsonl"


def profile_file() -> Path:
    configured = os.environ.get("INFO_ALCHEMIST_PERSONAL_PROFILE_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return memory_dir() / "personal_voi_profile.md"


def cache_dir() -> Path:
    configured = os.environ.get("INFO_ALCHEMIST_CACHE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return data_dir() / "cache"
