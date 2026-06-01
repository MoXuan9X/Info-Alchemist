#!/usr/bin/env python3
import json
import sys
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import record_final_output  # noqa: E402
import render_html_report  # noqa: E402
import run_log  # noqa: E402
import formal_run  # noqa: E402
import info_alchemist_paths  # noqa: E402
import record_decision  # noqa: E402


VALID_REPORT = "\n".join([
    "INFO_ALCHEMIST=TRUE",
    "# 信息炼金报告",
    "## 核心判断",
    "这是一份测试报告。",
    "---",
    "## 决策问题",
    "是否要继续验证？",
    "---",
    "## 专家判断",
    "先看证据。",
    "---",
    "## 候选行动",
    "1. 做小范围验证。",
    "---",
    "## 高价值证据",
    "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |",
    "| medium | 讨论 | 有讨论 | 先验证 | [来源](https://example.com) | 64/100 | 78/100 |",
    "---",
    "## 缺失的证据",
    "- 缺少真实点击。",
    "---",
    "## 下一步行动",
    "1. 发一个测试页。",
])


class ReportContractTest(unittest.TestCase):
    def test_default_artifact_paths_live_under_skill_workspace(self) -> None:
        keys = [
            "INFO_ALCHEMIST_WORKSPACE_DIR",
            "INFO_ALCHEMIST_DATA_DIR",
            "INFO_ALCHEMIST_REPORT_DIR",
            "INFO_ALCHEMIST_MARKDOWN_REPORT_DIR",
            "INFO_ALCHEMIST_DRAFT_DIR",
            "INFO_ALCHEMIST_HTML_REPORT_DIR",
            "INFO_ALCHEMIST_RUN_DIR",
            "INFO_ALCHEMIST_MEMORY_DIR",
            "INFO_ALCHEMIST_RECORDS_FILE",
            "INFO_ALCHEMIST_PERSONAL_PROFILE_FILE",
            "INFO_ALCHEMIST_CACHE_DIR",
        ]
        old_env = {key: os.environ.get(key) for key in keys}
        try:
            for key in keys:
                os.environ.pop(key, None)
            if SKILL_DIR.parent.name in {"skill", "skills"}:
                workspace = SKILL_DIR.parent.parent
            else:
                workspace = SKILL_DIR
            self.assertEqual(info_alchemist_paths.workspace_dir(), workspace)
            self.assertEqual(info_alchemist_paths.data_dir(), workspace / "info-alchemist")
            self.assertEqual(info_alchemist_paths.reports_dir(), workspace / "info-alchemist" / "reports")
            self.assertEqual(info_alchemist_paths.html_reports_dir(), workspace / "info-alchemist" / "reports" / "html")
            self.assertEqual(info_alchemist_paths.drafts_dir(), workspace / "info-alchemist" / "drafts")
            self.assertEqual(info_alchemist_paths.runs_dir(), workspace / "info-alchemist" / "runs")
            self.assertEqual(info_alchemist_paths.records_file(), workspace / "info-alchemist" / "memory" / "alchemy_records.jsonl")
            self.assertEqual(info_alchemist_paths.profile_file(), workspace / "info-alchemist" / "memory" / "personal_voi_profile.md")
            self.assertEqual(info_alchemist_paths.cache_dir(), workspace / "info-alchemist" / "cache")
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_profile_markdown_falls_back_to_legacy_skill_memory(self) -> None:
        keys = [
            "INFO_ALCHEMIST_DATA_DIR",
            "INFO_ALCHEMIST_MEMORY_DIR",
            "INFO_ALCHEMIST_PERSONAL_PROFILE_FILE",
        ]
        old_env = {key: os.environ.get(key) for key in keys}
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["INFO_ALCHEMIST_DATA_DIR"] = tmpdir
                os.environ.pop("INFO_ALCHEMIST_MEMORY_DIR", None)
                os.environ.pop("INFO_ALCHEMIST_PERSONAL_PROFILE_FILE", None)
                text = render_html_report.read_personal_profile_markdown()
                legacy_path = SKILL_DIR / "memory" / "personal_voi_profile.md"
                if legacy_path.exists():
                    self.assertIn("## 近期决策记录", text)
                    self.assertIn("AI 趋势机会", text)
                else:
                    self.assertEqual(text, "")
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_record_final_output_archives_markdown_report_under_reports_dir(self) -> None:
        old_data_dir = os.environ.get("INFO_ALCHEMIST_DATA_DIR")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["INFO_ALCHEMIST_DATA_DIR"] = tmpdir
                report = VALID_REPORT.replace("是否要继续验证？", "决策对象：AI 会议纪要工具\n是否要继续验证？")
                report_path = record_final_output.save_markdown_report("20260104T120000Z-report-run", report)
                self.assertEqual(Path(report_path), Path(tmpdir) / "reports" / "信息炼金报告-AI 会议纪要工具-20260104.md")
                self.assertEqual(Path(report_path).read_text(encoding="utf-8"), report + "\n")
        finally:
            if old_data_dir is None:
                os.environ.pop("INFO_ALCHEMIST_DATA_DIR", None)
            else:
                os.environ["INFO_ALCHEMIST_DATA_DIR"] = old_data_dir

    def test_markdown_fallback_records_token_usage_footer(self) -> None:
        old_data_dir = os.environ.get("INFO_ALCHEMIST_DATA_DIR")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["INFO_ALCHEMIST_DATA_DIR"] = tmpdir
                token_usage = {
                    "method_label": "字符数 / 3 粗估",
                    "total_tokens_est": 3210,
                    "input_tokens_est": 3000,
                    "output_tokens_est": 210,
                    "breakdown": [
                        {"key": "skill_md", "label": "Skill 规则", "direction": "input", "chars": 6000, "tokens_est": 2000},
                        {"key": "report_context", "label": "报告上下文", "direction": "input", "chars": 3000, "tokens_est": 1000},
                        {"key": "final_report", "label": "最终报告输出", "direction": "output", "chars": 630, "tokens_est": 210},
                    ],
                    "excluded": ["外部搜索 API 本身不计入 LLM token。"],
                    "note": "精确值以模型返回的 usage 为准。",
                }
                report_path = record_final_output.save_markdown_report("20260104T120000Z-token-run", VALID_REPORT, token_usage=token_usage)
                saved = Path(report_path).read_text(encoding="utf-8")
        finally:
            if old_data_dir is None:
                os.environ.pop("INFO_ALCHEMIST_DATA_DIR", None)
            else:
                os.environ["INFO_ALCHEMIST_DATA_DIR"] = old_data_dir
        self.assertIn("## Token 消耗估算", saved)
        self.assertIn("合计：约 3,210 tokens", saved)
        self.assertIn("拆分：输入约 3,000 tokens，输出约 210 tokens", saved)
        self.assertIn("  - 输入 · Skill 规则：6,000 字符，约 2,000 tokens", saved)
        self.assertIn("  - 输出 · 炼金报告：630 字符，约 210 tokens", saved)
        self.assertNotIn("输出 · 最终报告输出", saved)
        self.assertNotIn("估算方法", saved)
        self.assertNotIn("不计入", saved)
        self.assertNotIn("说明：", saved)

    def test_user_visible_text_is_compact_and_keeps_report_link(self) -> None:
        linked_heading = "# 信息炼金报告\n\n[点击查看->可视化《信息炼金报告》](http://127.0.0.1:8765/unit-report.html)"
        long_report = record_final_output.append_token_usage_markdown(
            VALID_REPORT + "\n\n" + "\n".join([f"- 额外证据 {index}" for index in range(80)]),
            {"total_tokens_est": 1234, "input_tokens_est": 1000, "output_tokens_est": 234},
        )
        visible = record_final_output.compact_user_visible_text(long_report, linked_heading, max_chars=1400)
        self.assertLessEqual(len(visible), 1400)
        self.assertTrue(visible.startswith("INFO_ALCHEMIST=TRUE"))
        self.assertIn("http://127.0.0.1:8765/unit-report.html", visible)
        self.assertIn("## 核心判断", visible)
        self.assertIn("## 下一步行动", visible)
        self.assertNotIn("Token 消耗估算", visible)

    def test_user_visible_text_defaults_to_full_report_with_report_link(self) -> None:
        linked_heading = "# 信息炼金报告\n\n[点击查看->可视化《信息炼金报告》](http://127.0.0.1:8765/unit-report.html)"
        long_report = record_final_output.append_token_usage_markdown(
            VALID_REPORT + "\n\n" + "\n".join([f"- 额外证据 {index}" for index in range(80)]),
            {"total_tokens_est": 1234, "input_tokens_est": 1000, "output_tokens_est": 234},
        )
        visible = record_final_output.full_user_visible_text(long_report, linked_heading)
        self.assertTrue(visible.startswith("INFO_ALCHEMIST=TRUE"))
        self.assertIn("http://127.0.0.1:8765/unit-report.html", visible)
        self.assertIn("## 专家判断", visible)
        self.assertIn("## 高价值证据", visible)
        self.assertIn("- 额外证据 79", visible)
        self.assertNotIn("Token 消耗估算", visible)

    def test_record_final_output_cleans_temp_report_source_in_data_root_only(self) -> None:
        old_data_dir = os.environ.get("INFO_ALCHEMIST_DATA_DIR")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["INFO_ALCHEMIST_DATA_DIR"] = tmpdir
                root = Path(tmpdir)
                temp_source = root / "tmp-20260529-ai-products-report.md"
                temp_source.write_text(VALID_REPORT, encoding="utf-8")
                cleaned = record_final_output.cleanup_temp_report_source(str(temp_source))
                self.assertEqual(Path(cleaned), temp_source.resolve())
                self.assertFalse(temp_source.exists())

                report_source = root / "reports" / "tmp-20260529-ai-products-report.md"
                report_source.parent.mkdir(parents=True, exist_ok=True)
                report_source.write_text(VALID_REPORT, encoding="utf-8")
                self.assertEqual(record_final_output.cleanup_temp_report_source(str(report_source)), "")
                self.assertTrue(report_source.exists())
        finally:
            if old_data_dir is None:
                os.environ.pop("INFO_ALCHEMIST_DATA_DIR", None)
            else:
                os.environ["INFO_ALCHEMIST_DATA_DIR"] = old_data_dir

    def test_token_usage_estimate_rebuilds_ai_report_context_from_run_log(self) -> None:
        old_data_dir = os.environ.get("INFO_ALCHEMIST_DATA_DIR")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["INFO_ALCHEMIST_DATA_DIR"] = tmpdir
                run_log.record_stage(
                    "token-estimate-run",
                    "search_plan",
                    {
                        "run_id": "token-estimate-run",
                        "report_mode": "distribution_mode",
                        "report_mode_label": "分发判断",
                        "search_plan": [{"query": "AI tool SEO", "search_intent": "seo_page_type"}],
                    },
                )
                run_log.record_stage(
                    "token-estimate-run",
                    "tavily_result",
                    {
                        "search_provider": "tavily+tikhub",
                        "tavily_status": "success",
                        "search_results": [{"status": "ok", "results": []}],
                    },
                )
                run_log.record_stage(
                    "token-estimate-run",
                    "synthesis",
                    {
                        "evidence_coverage": {"conclusion_strength_ceiling": "medium"},
                        "public_evidence": [],
                        "social_platform_signals": [],
                        "evidence_gap_candidates": [],
                    },
                )
                usage = record_final_output.estimate_token_usage("token-estimate-run", VALID_REPORT)
        finally:
            if old_data_dir is None:
                os.environ.pop("INFO_ALCHEMIST_DATA_DIR", None)
            else:
                os.environ["INFO_ALCHEMIST_DATA_DIR"] = old_data_dir
        labels = [item["label"] for item in usage["breakdown"]]
        self.assertEqual(labels, [
            "Skill 规则",
            "用户输入",
            "报告上下文",
            "意图识别输出",
            "搜索计划输出",
            "搜索结果摘要输出",
            "证据整理输出",
            "最终报告输出",
        ])
        context_item = usage["breakdown"][2]
        self.assertTrue(context_item["available"])
        self.assertGreater(usage["input_tokens_est"], 0)
        self.assertGreater(usage["output_tokens_est"], 0)
        self.assertEqual(usage["method"], "chars_div_3")

    def test_report_filename_stem_matches_markdown_title_and_run_date(self) -> None:
        report = VALID_REPORT.replace(
            "是否要继续验证？",
            "决策对象：哪类 AI 视频产品在成本结构上更适合独立开发者\n是否要继续验证？",
        )
        self.assertEqual(
            render_html_report.report_filename_stem(report, "20260104T120000Z-cost"),
            "信息炼金报告-哪类 AI 视频产品在成本结构上更适合独立开发者-20260104",
        )

    def test_html_report_filename_stem_uses_run_id_for_short_urls(self) -> None:
        self.assertEqual(
            render_html_report.html_report_filename_stem("20260104T120000Z-cost"),
            "20260104T120000Z-cost",
        )

    def test_personal_profile_docs_use_current_user_facing_titles(self) -> None:
        old_evidence_title = "对你有效" + "的证据"
        doc_paths = [
            SKILL_DIR / "README.md",
            SKILL_DIR / "SKILL.md",
            SKILL_DIR / "CHANGELOG.md",
            SKILL_DIR / "references" / "memory_rules.md",
            SKILL_DIR / "memory" / "README.md",
            SKILL_DIR / "assets" / "submission" / "commercial_value.md",
        ]
        joined = "\n".join(path.read_text(encoding="utf-8") for path in doc_paths)
        for title in [
            "最近更新",
            "已记录决策",
            "画像成熟度",
            "画像说明",
            "近期决策记录",
            "惯性决策模式",
            "有效证据类型",
            "最近决策洞察",
            "下次询证提醒",
        ]:
            self.assertIn(title, joined)
        for old_title in [
            "最后更新、累计记录、当前可信度、说明",
            "最近决策记录",
            "决策模式线索",
            old_evidence_title,
            "最近洞察",
            "候选护栏",
            "怎么理解",
        ]:
            self.assertNotIn(old_title, joined)

    def test_user_visible_report_rejects_tikhub_provider_name(self) -> None:
        text = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "TikHub 结果显示有讨论。",
            "---",
            "## 决策问题",
            "---",
            "## 专家判断",
            "---",
            "## 候选行动",
            "---",
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |",
            "| medium | 讨论 | 有讨论 | 先验证 | [来源](https://example.com) | 64/100 | 78/100 |",
            "---",
            "## 缺失的证据",
            "---",
            "## 下一步行动",
        ])
        errors = record_final_output.validate_report_contract(text)
        self.assertTrue(any("TikHub" in error for error in errors))

    def test_user_visible_report_requires_section_dividers(self) -> None:
        text = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "这是一份测试报告。",
            "## 决策问题",
            "是否要继续验证？",
            "## 专家判断",
            "先看证据。",
            "## 候选行动",
            "1. 做小范围验证。",
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |",
            "| medium | 讨论 | 有讨论 | 先验证 | [来源](https://example.com) | 64/100 | 78/100 |",
            "## 缺失的证据",
            "- 缺少真实点击。",
            "## 下一步行动",
            "1. 发一个测试页。",
        ])
        errors = record_final_output.validate_report_contract(text)
        self.assertTrue(any("请在 `## 决策问题` 前加入 `---`" in error for error in errors))

    def test_publish_html_report_uses_configured_http_base_url(self) -> None:
        old_base = os.environ.get("INFO_ALCHEMIST_HTML_BASE_URL")
        old_mode = os.environ.get("INFO_ALCHEMIST_HTML_REPORT_URL_MODE")
        os.environ["INFO_ALCHEMIST_HTML_BASE_URL"] = "https://reports.example.test/info-alchemist/"
        os.environ.pop("INFO_ALCHEMIST_HTML_REPORT_URL_MODE", None)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                report = VALID_REPORT.replace("是否要继续验证？", "决策对象：AI 会议纪要工具\n是否要继续验证？")
                result = render_html_report.publish_html_report(report, "20260104T120000Z-unit-report", output_dir=tmpdir)
        finally:
            if old_base is None:
                os.environ.pop("INFO_ALCHEMIST_HTML_BASE_URL", None)
            else:
                os.environ["INFO_ALCHEMIST_HTML_BASE_URL"] = old_base
            if old_mode is None:
                os.environ.pop("INFO_ALCHEMIST_HTML_REPORT_URL_MODE", None)
            else:
                os.environ["INFO_ALCHEMIST_HTML_REPORT_URL_MODE"] = old_mode
        filename = "20260104T120000Z-unit-report.html"
        self.assertEqual(Path(result["html_path"]).name, filename)
        self.assertEqual(result["html_url"], f"https://reports.example.test/info-alchemist/{quote(filename)}")
        self.assertIn(f"[点击查看->可视化《信息炼金报告》](https://reports.example.test/info-alchemist/{quote(filename)})", result["linked_heading"])

    def test_report_url_raises_when_local_server_fails_without_file_mode(self) -> None:
        original = render_html_report.ensure_local_report_server
        old_mode = os.environ.get("INFO_ALCHEMIST_HTML_REPORT_URL_MODE")
        render_html_report.ensure_local_report_server = lambda _directory, _url, port=None: False
        try:
            os.environ.pop("INFO_ALCHEMIST_HTML_REPORT_URL_MODE", None)
            with tempfile.TemporaryDirectory() as tmpdir:
                target = Path(tmpdir) / "unit-report.html"
                target.write_text("<html></html>", encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "本地 HTML 报告服务启动失败"):
                    render_html_report.report_url_for(target, Path(tmpdir))
        finally:
            render_html_report.ensure_local_report_server = original
            if old_mode is None:
                os.environ.pop("INFO_ALCHEMIST_HTML_REPORT_URL_MODE", None)
            else:
                os.environ["INFO_ALCHEMIST_HTML_REPORT_URL_MODE"] = old_mode

    def test_report_url_uses_file_when_file_mode_is_explicit(self) -> None:
        old_mode = os.environ.get("INFO_ALCHEMIST_HTML_REPORT_URL_MODE")
        try:
            os.environ["INFO_ALCHEMIST_HTML_REPORT_URL_MODE"] = "file"
            with tempfile.TemporaryDirectory() as tmpdir:
                target = Path(tmpdir) / "unit-report.html"
                target.write_text("<html></html>", encoding="utf-8")
                url = render_html_report.report_url_for(target, Path(tmpdir))
        finally:
            if old_mode is None:
                os.environ.pop("INFO_ALCHEMIST_HTML_REPORT_URL_MODE", None)
            else:
                os.environ["INFO_ALCHEMIST_HTML_REPORT_URL_MODE"] = old_mode
        self.assertTrue(url.startswith("file://"))

    def test_report_url_tries_next_local_port_when_primary_fails(self) -> None:
        original = render_html_report.ensure_local_report_server
        old_port = os.environ.get("INFO_ALCHEMIST_HTML_REPORT_PORT")
        os.environ.pop("INFO_ALCHEMIST_HTML_REPORT_PORT", None)
        try:
            render_html_report.ensure_local_report_server = lambda _directory, _url, port=None: port == 8766
            with tempfile.TemporaryDirectory() as tmpdir:
                target = Path(tmpdir) / "unit-report.html"
                target.write_text("<html></html>", encoding="utf-8")
                url = render_html_report.report_url_for(target, Path(tmpdir))
        finally:
            render_html_report.ensure_local_report_server = original
            if old_port is None:
                os.environ.pop("INFO_ALCHEMIST_HTML_REPORT_PORT", None)
            else:
                os.environ["INFO_ALCHEMIST_HTML_REPORT_PORT"] = old_port
        self.assertEqual(url, "http://127.0.0.1:8766/unit-report.html")

    def test_existing_final_output_prevents_duplicate_publish(self) -> None:
        old_run_dir = os.environ.get("INFO_ALCHEMIST_RUN_DIR")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["INFO_ALCHEMIST_RUN_DIR"] = tmpdir
                run_log.record_stage(
                    "duplicate-run",
                    "final_output",
                    {
                        "length": 123,
                        "html_report": {
                            "html_path": "/tmp/report.html",
                            "html_url": "file:///tmp/report.html",
                            "linked_heading": "# 信息炼金报告",
                        },
                    },
                )
                existing = record_final_output.existing_final_output("duplicate-run")
        finally:
            if old_run_dir is None:
                os.environ.pop("INFO_ALCHEMIST_RUN_DIR", None)
            else:
                os.environ["INFO_ALCHEMIST_RUN_DIR"] = old_run_dir
        self.assertEqual(existing["length"], 123)
        self.assertEqual(existing["html_report"]["html_url"], "file:///tmp/report.html")

    def test_run_log_only_records_real_error_statuses(self) -> None:
        old_run_dir = os.environ.get("INFO_ALCHEMIST_RUN_DIR")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                os.environ["INFO_ALCHEMIST_RUN_DIR"] = tmpdir
                run_log.record_stage("status-run", "intent", {"ok": False}, "blocked")
                run_log.record_stage("status-run", "final_output", {"ok": True}, "completed")
                run_log.record_stage("status-run", "tavily_result", {"ok": False}, "error")
                log = run_log.read_log("status-run")
        finally:
            if old_run_dir is None:
                os.environ.pop("INFO_ALCHEMIST_RUN_DIR", None)
            else:
                os.environ["INFO_ALCHEMIST_RUN_DIR"] = old_run_dir
        self.assertEqual(len(log["events"]), 3)
        self.assertEqual(len(log["errors"]), 1)
        self.assertEqual(log["errors"][0]["stage"], "tavily_result")

    def test_html_renderer_cleans_duplicate_bullet_markers(self) -> None:
        html = render_html_report.markdown_to_html("- - 面向某一类用户")
        self.assertIn("<li>面向某一类用户</li>", html)
        self.assertNotIn("<li>- 面向", html)

    def test_evidence_table_uses_fixed_column_profile(self) -> None:
        html = render_html_report.markdown_to_html("\n".join([
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 |",
            "|---|---|---|---|---|",
            "| 高 | 市场趋势 | 发现 | 先验证 | [来源](https://example.com) |",
        ]))
        self.assertIn("evidence-table", html)
        self.assertIn("<col style=\"width:34%\">", html)

    def test_build_html_uses_visual_screens_not_markdown_body(self) -> None:
        html = render_html_report.build_html(VALID_REPORT, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn("sketch-board", html)
        self.assertIn("evidence-card", html)
        self.assertIn("evidence-score-grid", html)
        self.assertIn("质量", html)
        self.assertIn("价值", html)
        self.assertIn("<b>78</b>", html)
        self.assertNotIn(">4/5<", html)
        self.assertNotIn("--score-width", html)
        self.assertIn("main a {", html)
        self.assertIn("text-decoration-line: underline;", html)
        self.assertIn("text-decoration-color: var(--gold);", html)
        self.assertNotIn(".source-line a { border-bottom", html)
        self.assertIn("sticky-note", html)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", html)
        self.assertIn('class="profile-entry" href="unit-report-profile.html"', html)
        self.assertIn('aria-label="查看个人决策画像"', html)
        self.assertIn(">个人决策画像</span>", html)
        self.assertNotIn("topbar-actions::before", html)
        self.assertNotIn("profile-avatar", html)
        self.assertNotIn('id="profile-screen"', html)
        self.assertNotIn('返回信息炼金报告', html)
        self.assertNotIn(">可视化报告</a>", html)
        self.assertNotIn("class=\"panel report\"", html)
        self.assertNotIn("class=\"target\"", html)
        self.assertNotIn("决策路径", html)
        self.assertNotIn("score-row", html)
        self.assertNotIn('id="economics-screen"', html)

    def test_visual_report_hides_removed_cost_and_gate_modules(self) -> None:
        report = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "经济性判断：当前只适合小范围验证；回本取决于付费转化率和单次任务成本。",
            "---",
            "## 决策问题",
            "报告模式：机会判断",
            "决策对象：AI SEO 工具站",
            "测算口径：90 天，人民币；公开证据和系统假设分开标注。",
            "| 数字/假设 | 当前取值 | 来源状态 | 可信度 | 缺口 |",
            "|---|---|---|---|---|",
            "| 付费转化率 | 2% | 系统假设 | 低 | 需要 fake door |",
            "---",
            "## 专家判断",
            "先看证据。",
            "---",
            "## 候选行动",
            "### 成本结构测评",
            "| 成本项 | 默认工具 | 价格证据 | 用量假设 | 月成本 | 来源 |",
            "|---|---|---|---|---|---|",
            "| 模型/API | OpenAI API | $5 / 1M input tokens | 每次任务 10k tokens | 需用量后计算 | [OpenAI pricing](https://example.com/openai-pricing) |",
            "| 部署/服务器 | Vercel | 未取得公开证据 | 待用户估算 | 待用户估算 | 缺失 |",
            "",
            "| 项目 | 状态 | 结论 |",
            "|---|---|---|",
            "| ROI | 缺少月成本和转化率 | 暂不能计算 ROI |",
            "",
            "| 要补的数字 | 当前状态 | 怎么拿 | 用来判断什么 |",
            "|---|---|---|---|",
            "| 单用户月调用量 | 缺失 | 做 10-20 个任务样本 | 算模型/API 月成本 |",
            "",
            "| 候选行动 | 初始投入 | 初始投入依据 | 月成本 | 月成本依据 | 收入/价格证据 | 保本门槛 | 建议 |",
            "|---|---:|---|---:|---|---|---|---|",
            "| [AI SEO brief 小工具](https://example.com/tool) | ¥3,000 | 用户提供 | 未取得公开证据 | 缺失 | ¥99/月，公开定价页 | 36 个付费用户 | 先做假门 |",
            "",
            "| 指标 | 保守 | 基准 | 乐观 | 来源/假设 |",
            "|---|---:|---:|---:|---|",
            "| 回本周期 | >6 月 | 2-3 月 | <1 月 | 系统假设，待验证 |",
            "| 毛利率 | 40% | 70% | 85% | API 成本估算 |",
            "---",
            "## 高价值证据",
            "### 商业基准 / ROI",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |",
            "|---|---|---|---|---|---|---|",
            "| 高 | 定价 | 竞品有付费套餐 | 先测付费墙 | [来源](https://example.com/pricing) | 72/100 | 90/100 |",
            "---",
            "## 缺失的证据",
            "- 真实 CAC、LTV、付费转化率都缺失，不能当成事实。",
            "---",
            "## 下一步行动",
            "### 7 天验证闸门",
            "| 7 天验证项 | 验证方式 | 7 天记录什么 | 7 天后怎么判断 |",
            "|---|---|---|---|",
            "| 用户愿意为结果付费 | ¥49 假付费按钮 | 价格点击、留言 | 有人明确接受价格再做 demo |",
        ])
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertNotIn('id="economics-screen"', html)
        self.assertNotIn('href="#economics-screen">成本</a>', html)
        self.assertNotIn("成本结构测评", html)
        self.assertNotIn("7 天验证闸门", html)
        self.assertNotIn("先拆成本结构，再判断 ROI 是否可算。", html)
        self.assertNotIn("OpenAI pricing", html)
        self.assertNotIn("单用户月调用量", html)
        self.assertNotIn("用户愿意为结果付费", html)
        self.assertNotIn('class="report-table next-action-table"', html)
        self.assertIn("竞品有付费套餐", html)
        self.assertNotIn('class="roi-action-card"', html)
        self.assertNotIn('class="finance-gate-card"', html)

    def test_visual_report_filters_generic_fixed_costs_for_ai_video(self) -> None:
        report = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "AI 视频站最敏感变量是单次生成成本和失败重试率。",
            "---",
            "## 决策问题",
            "报告模式：机会判断",
            "决策对象：AI 视频站",
            "---",
            "## 专家判断",
            "先看证据。",
            "---",
            "## 候选行动",
            "### 成本结构测评",
            "| 成本项 | 默认工具 | 价格证据 | 用量假设 | 月成本 | 来源 |",
            "|---|---|---|---|---|---|",
            "| 部署/服务器 | Vercel | $20/seat/月 | 低并发 | 需用量后计算 | [Vercel](https://example.com/vercel) |",
            "| 邮件/通知 | Resend | 3,000 封/月免费 | waitlist | 需用量后计算 | [Resend](https://example.com/resend) |",
            "| 模型/API | Gemini Veo | $0.05/秒起 | 生成秒数和重试率决定成本 | 需用量后计算 | [Gemini pricing](https://example.com/veo) |",
            "| 媒体存储/CDN | Cloudflare R2 | 按存储和请求计费 | 视频文件量、带宽和保留时长决定成本 | 需用量后计算 | [R2](https://example.com/r2) |",
            "---",
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |",
            "|---|---|---|---|---|---|---|",
            "| 高 | 成本 | 视频生成按秒计费 | 先测短视频生成 | [来源](https://example.com/source) | 80/100 | 85/100 |",
            "---",
            "## 缺失的证据",
            "- 重试率。",
            "---",
            "## 下一步行动",
            "1. 做一个 5 秒生成测试。",
        ])
        html = render_html_report.build_html(report, "video-report", "http://127.0.0.1:8765/video-report.html")
        self.assertNotIn('id="economics-screen"', html)
        self.assertNotIn("成本结构测评", html)
        self.assertNotIn("Gemini Veo", html)
        self.assertNotIn("媒体存储/CDN", html)
        self.assertNotIn("部署/服务器", html)
        self.assertNotIn("邮件/通知", html)
        self.assertIn("视频生成按秒计费", html)

    def test_visual_report_hides_removed_cost_modules_when_written_as_numbered_cards(self) -> None:
        report = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "先做小范围验证。",
            "---",
            "## 决策问题",
            "报告模式：机会判断",
            "决策对象：AI 视频站",
            "---",
            "## 专家判断",
            "先看证据。",
            "---",
            "## 候选行动",
            "1. **成本结构测评**",
            "当前暂不能计算 ROI，主要缺：",
            "- 1 个付费用户平均会消耗多少生成秒数；",
            "- SEO 自然流量起量周期，或广告 CAC。",
            "2. 做电商商品视频模板页",
            "先测试商品图转 5 秒视频。",
            "---",
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |",
            "|---|---|---|---|---|---|---|",
            "| 高 | 定价 | 竞品有 credits 套餐 | 先测付费墙 | [来源](https://example.com/pricing) | 72/100 | 90/100 |",
            "---",
            "## 缺失的证据",
            "- 真实转化率。",
            "---",
            "## 下一步行动",
            "1. **7 天验证闸门**",
            "记录价格点击和留资。",
            "2. 发一个模板页",
            "记录注册和生成成功率。",
        ])
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertNotIn("成本结构测评", html)
        self.assertNotIn("当前暂不能计算 ROI", html)
        self.assertNotIn("生成秒数", html)
        self.assertNotIn("广告 CAC", html)
        self.assertNotIn("7 天验证闸门", html)
        self.assertNotIn("价格点击和留资", html)
        self.assertIn("做电商商品视频模板页", html)
        self.assertIn("发一个模板页", html)

    def test_evidence_cards_ignore_later_tables_in_same_section(self) -> None:
        report = VALID_REPORT.replace(
            "---\n## 缺失的证据",
            "\n### 社交平台\n\n"
            "| 社交平台 | 主要看什么 | 这轮发现 | 对行动的影响 | 可信度 | 来源 |\n"
            "|---|---|---|---|---|---|\n"
            "| X | 发布动态 | 有线索 | 后续深挖 | 中 | 未核验 |\n"
            "---\n## 缺失的证据",
        )
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn("evidence-score-grid", html)
        self.assertNotIn("--score-width", html)
        self.assertNotIn("社交平台</span>", html)
        self.assertNotIn('id="social-screen"', html)
        self.assertNotIn('class="report-table social-table"', html)
        self.assertNotIn("发布动态", html)

    def test_visual_report_renders_modular_evidence_tables(self) -> None:
        report = VALID_REPORT.replace(
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |\n"
            "| medium | 讨论 | 有讨论 | 先验证 | [来源](https://example.com) | 64/100 | 78/100 |",
            "### 竞品池\n\n"
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 高 | 竞品 | 头部工具密集 | 先做差异化 | [竞品来源](https://example.com/c) | 72/100 | 90/100 |\n\n"
            "### 定价/商业模式\n\n"
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 中 | 定价 | 免费额度有限 | 先测付费墙 | [定价来源](https://example.com/p) | 64/100 | 78/100 |\n\n"
            "### 社交平台\n\n"
            "| 社交平台 | 主要看什么 | 这轮发现 | 对行动的影响 | 可信度 | 来源 |\n"
            "|---|---|---|---|---|---|\n"
            "| Reddit | 用户抱怨 | 有噪声 | 不作为主证据 | 低 | 未核验 |",
        )
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn("evidence-module-stack", html)
        self.assertIn('class="evidence-module"', html)
        self.assertIn("候选池", html)
        self.assertIn("商业模式", html)
        self.assertNotIn('id="social-screen"', html)
        self.assertNotIn('class="report-table social-table"', html)
        self.assertNotIn("Reddit", html)
        self.assertNotIn("用户抱怨", html)
        self.assertIn("竞品来源", html)
        self.assertIn("定价来源", html)

    def test_visual_report_keeps_three_named_evidence_modules(self) -> None:
        report = VALID_REPORT.replace(
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |\n"
            "| medium | 讨论 | 有讨论 | 先验证 | [来源](https://example.com) | 64/100 | 78/100 |",
            "### 候选池 / 产品路径\n\n"
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 高 | 竞品 | A | A 决策 | [A](https://example.com/a) | 72/100 | 90/100 |\n"
            "| 高 | 竞品 | B | B 决策 | [B](https://example.com/b) | 72/100 | 90/100 |\n"
            "| 中 | SEO | C | C 决策 | [C](https://example.com/c) | 64/100 | 78/100 |\n\n"
            "### 定价 / 商业模式\n\n"
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 高 | 成本 | D | D 决策 | [D](https://example.com/d) | 72/100 | 90/100 |\n\n"
            "### 用户反馈 / 痛点\n\n"
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |\n"
            "|---|---|---|---|---|---|---|\n"
            "| 高 | 用户痛点 | E | E 决策 | [E](https://example.com/e) | 72/100 | 90/100 |\n\n"
            "### 社交平台\n\n"
            "| 社交平台 | 主要看什么 | 这轮发现 | 对行动的影响 | 可信度 | 来源 |\n"
            "|---|---|---|---|---|---|\n"
            "| Reddit | 抱怨 | 渠道线索 | 单独看 | 中 | [R](https://example.com/r) |",
        )
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn("<h3>候选池</h3>", html)
        self.assertIn("<h3>商业模式</h3>", html)
        self.assertIn("<h3>用户痛点</h3>", html)
        self.assertEqual(html.count('class="evidence-module"'), 3)
        self.assertNotIn('id="social-screen"', html)
        self.assertNotIn('class="report-table social-table"', html)

    def test_visual_report_renders_comparison_tables_and_drops_social_module(self) -> None:
        report = VALID_REPORT.replace(
            "是否要继续验证？",
            "是否要继续验证？\n\n"
            "### 候选方向粗判断\n\n"
            "| 候选方向 | 用户任务 | SEO 入口 | 建议 |\n"
            "|---|---|---|---|\n"
            "| 评论分析 | 抓取评论 | review summary | 优先 |\n\n"
            "### ROI 行动表\n\n"
            "| 候选行动 | 初始投入 | 初始投入依据 | 月成本 | 月成本依据 | 收入/价格证据 | 保本门槛 | 建议 |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| 评论/舆情分析 MVP | 未取得公开证据 | 缺失 | 未取得公开证据 | 缺失 | $19/月公开价格锚点 | 30 个付费用户 | 最值得先测 |",
        ).replace(
            "---\n## 缺失的证据",
            "\n### 社交平台\n\n"
            "| 社交平台 | 主要看什么 | 这轮发现 | 对行动的影响 | 可信度 | 来源 |\n"
            "|---|---|---|---|---|---|\n"
            "| Reddit | 抱怨 | 有高意图词 | 作为选题池 | 中 | [来源](https://example.com/r) |\n"
            "---\n## 缺失的证据",
        ).replace(
            "1. 发一个测试页。",
            "### 7 天验证闸门\n\n"
            "| 7 天验证项 | 验证方式 | 7 天记录什么 | 7 天后怎么判断 |\n"
            "|---|---|---|---|\n"
            "| 用户愿意付费 | pricing block | 点击、留资、留言 | 有明确价格信号再继续 demo |",
        )
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn('href="#comparison-screen">对比</a>', html)
        self.assertIn('id="comparison-screen"', html)
        self.assertIn("候选方向粗判断", html)
        self.assertIn("comparison-table", html)
        self.assertNotIn('href="#economics-screen">成本</a>', html)
        self.assertNotIn('id="economics-screen"', html)
        self.assertNotIn("行动的经济性", html)
        self.assertNotIn("评论/舆情分析 MVP", html)
        self.assertNotIn('href="#social-screen">社交</a>', html)
        self.assertNotIn('id="social-screen"', html)
        self.assertNotIn('class="report-table social-table"', html)
        self.assertNotIn("Reddit", html)
        self.assertNotIn("<h3>社交平台</h3>", html)
        self.assertNotIn("<b>社交平台</b>", html)
        self.assertNotIn('class="report-table next-action-table"', html)
        self.assertNotIn("7 天验证闸门", html)

    def test_visual_report_keeps_gaps_and_next_steps_as_plain_cards(self) -> None:
        report = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "结论上限是小范围验证。",
            "---",
            "## 决策问题",
            "是否继续？",
            "---",
            "## 专家判断",
            "先看证据。",
            "---",
            "## 候选行动",
            "1. 做小范围验证。",
            "---",
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |",
            "|---|---|---|---|---|---|---|",
            "| 高 | 用户痛点 | 有明确抱怨 | 先验证痛点 | [来源](https://example.com) | 72/100 | 90/100 |",
            "---",
            "## 缺失的证据",
            "1. **用户痛点**：还缺真实访谈。",
            "2. **风险**：还缺平台规则。",
            "---",
            "## 下一步行动",
            "1. 用户是否点击假门按钮：落地页 fake door。",
        ])
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertNotIn("coverage-panel", html)
        self.assertNotIn("coverage-card", html)
        self.assertNotIn("matrix-panel", html)
        self.assertNotIn("matrix-card", html)
        self.assertIn("gap-card", html)
        self.assertIn("step-card", html)
        self.assertIn("落地页 fake door", html)

    def test_visual_report_renders_token_usage_footer(self) -> None:
        token_usage = {
            "method_label": "字符数 / 3 粗估",
            "total_tokens_est": 4321,
            "input_tokens_est": 3700,
            "output_tokens_est": 621,
            "breakdown": [
                {"key": "skill_md", "label": "Skill 规则", "direction": "input", "chars": 6000, "tokens_est": 2000},
                {"key": "report_context", "label": "报告上下文", "direction": "input", "chars": 5100, "tokens_est": 1700},
                {"key": "final_report", "label": "最终报告输出", "direction": "output", "chars": 1863, "tokens_est": 621},
            ],
            "excluded": ["外部搜索 API 本身不计入 LLM token。"],
            "note": "精确值以模型返回的 usage 为准。",
        }
        html = render_html_report.build_html(
            VALID_REPORT,
            "unit-report",
            "http://127.0.0.1:8765/unit-report.html",
            token_usage=token_usage,
        )
        self.assertIn('id="token-screen"', html)
        self.assertIn("Token 总消耗", html)
        self.assertIn("Token 总消耗：</span>约 4,321 tokens · 输入约 3,700 · 输出约 621", html)
        self.assertNotIn("Token 消耗估算：</span>", html)
        self.assertIn("约 4,321 tokens", html)
        self.assertIn("<b>报告上下文</b> 约 1,700 tokens", html)
        self.assertIn("<b>炼金报告</b> 约 621 tokens", html)
        self.assertNotIn("<b>最终报告</b>", html)
        self.assertNotIn("<b>最终报告输出</b>", html)
        self.assertIn('class="token-info"', html)
        self.assertIn('class="token-tooltip"', html)
        self.assertIn('<span class="token-breakdown-label">输入：</span>', html)
        self.assertIn('<span class="token-breakdown-label">输出：</span>', html)
        self.assertLess(html.index('class="token-info"'), html.index('class="token-summary"'))
        self.assertLess(html.index("输入："), html.index("<b>Skill 规则</b>"))
        self.assertLess(html.index("输出："), html.index("<b>炼金报告</b>"))
        self.assertLess(html.index("<b>报告上下文</b>"), html.index("输出："))
        self.assertIn('class="token-summary"', html)
        self.assertNotIn('class="token-total"', html)
        self.assertNotIn("外部搜索 API 本身不计入 LLM token。", html)
        self.assertNotIn("这是参考 skill-scorer", html)
        self.assertNotIn("token-badge", html)
        self.assertNotIn(".token-card {\n      display: grid;", html)
        self.assertNotIn("box-shadow: 5px 5px 0 rgba(208,160,44,.22)", html)

    def test_visual_report_can_parse_token_usage_from_markdown_fallback(self) -> None:
        markdown = record_final_output.append_token_usage_markdown(
            VALID_REPORT,
            {
                "method_label": "字符数 / 3 粗估",
                "total_tokens_est": 1234,
                "input_tokens_est": 1000,
                "output_tokens_est": 234,
                "breakdown": [
                    {"key": "skill_md", "label": "Skill 规则", "direction": "input", "chars": 3000, "tokens_est": 1000},
                    {"key": "final_report", "label": "最终报告输出", "direction": "output", "chars": 702, "tokens_est": 234},
                ],
                "excluded": ["外部搜索 API 本身不计入 LLM token。"],
                "note": "精确值以模型返回的 usage 为准。",
            },
        )
        html = render_html_report.build_html(markdown, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn('id="token-screen"', html)
        self.assertIn("约 1,234 tokens", html)
        self.assertIn("输入约 1,000 · 输出约 234", html)
        self.assertIn("<b>炼金报告</b> 约 234 tokens", html)

    def test_topbar_jump_buttons_share_the_same_visual_rule(self) -> None:
        report_html = render_html_report.build_html(
            VALID_REPORT,
            "unit-report",
            "http://127.0.0.1:8765/unit-report.html",
        )
        profile_html = render_html_report.build_profile_html("# 个人决策画像", "unit-report.html")
        shared_rule = ".profile-entry,\n    .topbar-return {"
        for html in [report_html, profile_html]:
            self.assertIn(shared_rule, html)
            self.assertIn("transform: none;", html)
            self.assertNotIn("translateY(-1px)", html)

    def test_record_decision_normalizes_final_action_for_profile_memory(self) -> None:
        self.assertEqual(
            record_decision.normalize_final_action("好的，我会先从模板型的AI视频站做起"),
            "先从模板型的AI视频站做起",
        )
        self.assertEqual(
            record_decision.normalize_final_action("我准备先做关键词页"),
            "先做关键词页",
        )

    def test_visual_report_renders_personal_profile_from_configured_markdown(self) -> None:
        old_profile = os.environ.get("INFO_ALCHEMIST_PERSONAL_PROFILE_FILE")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                profile_path = Path(tmpdir) / "profile.md"
                profile_path.write_text(
                    "\n".join([
                        "# 个人决策画像",
                        "",
                        "最近更新：2026-05-26",
                        "已记录决策：3 条",
                        "画像成熟度：中",
                        "画像说明：出现重复线索。",
                        "",
                        "## 近期决策记录",
                        "| 日期 | 场景 | 触发因素 | 原始动作 | 决策转折 | 最终动作 | 证据来源 |",
                        "|---|---|---|---|---|---|---|",
                        "| 2026-05-26 | AI 视频站 | 热点触发 | 继续搜索 | 成本结构改变判断 | 做模板型站 | 来源 |",
                        "",
                        "## 惯性决策模式",
                        "| 模式线索 | 出现次数 | 首次出现 | 最近出现 | 置信度 | 当前判断 |",
                        "|---|---:|---|---|---|---|",
                        "| 倾向先低成本验证 | 3 | 2026-05-20 | 2026-05-26 | 中 | 可作为候选稳定模式 |",
                        "",
                        "## 有效证据类型",
                        "| 证据类型 | 对行动的影响 | 最近出现 |",
                        "|---|---|---|",
                        "| 公开搜索 | 适合形成初步判断 | 2026-05-26 |",
                        "",
                        "## 最近决策洞察",
                        "- 低成本验证比追热点更能改变行动。",
                        "",
                        "## 下次询证提醒",
                        "| 护栏建议 | 触发条件 | 状态 |",
                        "|---|---|---|",
                        "| 先定义停止规则 | 再次做机会判断 | 候选中 |",
                    ]),
                    encoding="utf-8",
                )
                profile_markdown = profile_path.read_text(encoding="utf-8")
                html = render_html_report.build_profile_html(profile_markdown, "unit-report.html")
        finally:
            if old_profile is None:
                os.environ.pop("INFO_ALCHEMIST_PERSONAL_PROFILE_FILE", None)
            else:
                os.environ["INFO_ALCHEMIST_PERSONAL_PROFILE_FILE"] = old_profile
        self.assertIn('href="unit-report.html"', html)
        self.assertIn("<span>信息炼金报告</span>", html)
        self.assertIn('class="jump-arrow" aria-hidden="true">&gt;</span>', html)
        self.assertIn("topbar-return", html)
        self.assertNotIn("返回信息炼金报告", html)
        self.assertIn("AI 视频站", html)
        self.assertIn("成本结构改变判断", html)
        self.assertIn("倾向先低成本验证", html)
        self.assertIn("低成本验证比追热点更能改变行动。", html)
        self.assertIn("先定义停止规则", html)
        self.assertIn("<strong>AI 视频站</strong>", html)
        self.assertIn("<span>2026-05-26</span>", html)
        self.assertIn("decision-flow", html)
        self.assertIn(
            ".profile-decision-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }",
            html,
        )
        self.assertIn("decision-field", html)
        self.assertIn("decision-final", html)
        self.assertNotIn("decision-final-label", html)
        self.assertIn(".decision-final {\n      display: inline-flex;", html)
        self.assertIn("width: fit-content;", html)
        self.assertIn("max-width: 100%;", html)
        self.assertIn('<span class="field-label">最后决定</span>', html)
        self.assertIn('<div class="decision-final"><strong>做模板型站</strong></div>', html)
        self.assertLess(html.index('<span class="field-label">最后决定</span>'), html.index('<div class="decision-final"><strong>做模板型站</strong></div>'))
        self.assertIn('<span class="profile-confidence', html)
        self.assertLess(html.index("<strong>AI 视频站</strong>"), html.index("<span>2026-05-26</span>"))
        self.assertLess(html.index("<strong>倾向先低成本验证</strong>"), html.index('<span class="profile-confidence'))
        self.assertIn("画像说明", html)
        self.assertIn("近期决策记录", html)
        self.assertIn("惯性决策模式", html)
        self.assertIn("有效证据类型", html)
        self.assertIn("最近决策洞察", html)
        self.assertIn("下次询证提醒", html)
        self.assertNotIn("怎么理解", html)
        self.assertNotIn("对你有效" + "的证据", html)

    def test_report_context_includes_mode_guide_for_markdown_and_html(self) -> None:
        context = formal_run.report_context(
            {
                "run_id": "unit-report",
                "report_mode": "distribution_mode",
                "report_mode_label": "分发判断",
                "search_plan": [
                    {
                        "query": "AI tool SEO landing pages",
                        "query_group": "growth_seo",
                        "query_group_label": "增长/SEO/页面机会",
                    }
                ],
            },
            {
                "search_provider": "tavily+tikhub",
                "tavily_status": "success",
                "search_results": [
                    {
                        "status": "ok",
                        "answer": "raw answer should not be exposed",
                        "results": [
                            {
                                "title": "Raw title",
                                "url": "https://example.com/raw",
                                "content": "raw content should not be exposed to the host model",
                            }
                        ],
                    }
                ],
                "vertical_search": {
                    "enabled": True,
                    "platforms": ["xhs", "x", "reddit"],
                    "status": "success",
                    "result_groups": 3,
                    "successful_groups": 3,
                    "failed_groups": 0,
                    "failed_queries": [{"query": "raw failed query should not be exposed"}],
                },
            },
            {
                "evidence_coverage": {"conclusion_strength_ceiling": "medium"},
                "public_evidence": [
                    {
                        "source": {"title": "Useful source", "url": "https://example.com/useful"},
                        "finding": "有明确分发证据。",
                        "decision_impact": "medium",
                        "source_quality": "medium",
                        "source_type": "web_result",
                        "evidence_axis": "distribution",
                        "evidence_axis_label": "获客/SEO/页面机会",
                        "query_group": "growth_seo",
                        "query_group_label": "增长/SEO/页面机会",
                    }
                ],
                "social_platform_signals": [
                    {
                        "platform": "X",
                        "current_finding": "有实践者讨论。",
                        "sources": [{"title": "X source", "url": "https://x.com/example"}],
                        "top_items": [{"content": "raw social item should not be exposed"}],
                    }
                ],
                "evidence_gap_candidates": [
                    {
                        "gap": "缺少真实点击。",
                        "type": "EVSI",
                        "why_it_matters": "公开热度不等于点击。",
                        "recommended_channel": "fake_door",
                        "priority": "high",
                    },
                    {
                        "gap": "小红书 社交搜索结果低相关：AI",
                        "recommended_channel": "vertical_social_search",
                        "priority": "medium",
                    },
                ],
            },
            "/tmp/unit-report.json",
        )
        self.assertEqual(context["report_mode"], "distribution_mode")
        self.assertEqual(context["report_mode_label"], "分发判断")
        self.assertIn("前 100 用户", context["report_mode_guide"]["section_focus"])
        self.assertIn("报告模式：分发判断", context["report_mode_guide"]["html_pattern"])
        self.assertIn("`## 决策问题` 第一行必须写 `报告模式：<report_mode_label>`", context["report_instruction"])
        self.assertIn("evidence_pack", context)
        self.assertIn("search_result_summary", context)
        self.assertEqual(context["economics_display_guide"], {})
        self.assertEqual(context["active_search_modules"][0]["query_group"], "growth_seo")
        self.assertIn("只展示与本轮决策目标相关的模块", context["report_instruction"])
        self.assertNotIn("search_result", context)
        self.assertNotIn("synthesis", context)
        self.assertEqual(context["search_result_summary"]["result_groups"], 1)
        self.assertEqual(context["evidence_pack"]["public_evidence"][0]["source"]["title"], "Useful source")
        self.assertEqual(context["evidence_pack"]["public_evidence"][0]["query_group"], "growth_seo")
        self.assertEqual(context["evidence_pack"]["evidence_coverage"]["conclusion_strength_ceiling"], "medium")
        self.assertEqual(context["evidence_pack"]["social_platform_signals"][0]["sources"][0]["url"], "https://x.com/example")
        self.assertNotIn("top_items", context["evidence_pack"]["social_platform_signals"][0])
        self.assertEqual(context["evidence_pack"]["evidence_gap_candidates"][0]["gap"], "缺少真实点击。")
        self.assertNotIn("raw content should not be exposed", json.dumps(context, ensure_ascii=False))
        self.assertNotIn("raw social item should not be exposed", json.dumps(context, ensure_ascii=False))

    def test_candidate_discovery_context_exposes_candidate_sources(self) -> None:
        context = formal_run.report_context(
            {
                "run_id": "candidate-report",
                "report_mode": "candidate_mode",
                "report_mode_label": "候选池调研",
                "search_strategy": "candidate_discovery",
                "strategy_reason": "用户在找候选产品池。",
                "search_plan": [
                    {
                        "query": "best AI tools startups small business founders actually use 2026",
                        "query_group": "candidate_pool",
                        "query_group_label": "候选池/产品清单",
                    }
                ],
            },
            {
                "search_provider": "tavily",
                "tavily_status": "success",
                "search_results": [
                    {
                        "status": "ok",
                        "query": "best AI tools startups small business founders actually use 2026",
                        "query_group": "candidate_pool",
                        "query_group_label": "候选池/产品清单",
                        "results": [
                            {
                                "title": "20 AI Tools Founders Actually Use",
                                "url": "https://example.com/founder-tools",
                                "content": "Gamma, Cursor, Granola, Otter and other tools show concrete founder workflows.",
                            }
                        ],
                    },
                    {
                        "status": "ok",
                        "query": "\"AI tools\" pricing free plan subscription credits business model",
                        "query_group": "pricing",
                        "query_group_label": "定价/商业模式",
                        "evidence_axis": "unit_economics",
                        "results": [
                            {
                                "title": "AI app pricing models",
                                "url": "https://example.com/pricing",
                                "content": "Subscription and credit models are common, but this source does not include initial development cost.",
                            }
                        ],
                    },
                    {
                        "status": "ok",
                        "query": "OpenAI API pricing official",
                        "query_group": "model_api_pricing",
                        "query_group_label": "模型/API 价格",
                        "evidence_axis": "unit_economics",
                        "cost_category": "variable_task_cost",
                        "results": [
                            {
                                "title": "OpenAI API pricing",
                                "url": "https://example.com/openai-pricing",
                                "content": "Official model API token pricing page.",
                            }
                        ],
                    },
                ],
            },
            {"public_evidence": [], "evidence_gap_candidates": []},
            "/tmp/candidate-report.json",
        )
        self.assertEqual(context["search_strategy"], "candidate_discovery")
        self.assertEqual(context["report_mode"], "candidate_mode")
        pack = context["candidate_discovery_pack"]
        self.assertEqual(pack["search_strategy"], "candidate_discovery")
        self.assertEqual(pack["candidate_source_results"][0]["title"], "20 AI Tools Founders Actually Use")
        self.assertIn("候选产品拆解表", "".join(pack["required_output"]))
        self.assertIn("可执行方案卡片", "".join(pack["required_output"]))
        self.assertIn("10-15 个候选对象", "".join(pack["required_output"]))
        self.assertIn("入选依据", "".join(pack["required_output"]))
        self.assertIn("卡片负责行动归类", "".join(pack["required_output"]))
        self.assertIn("代表产品、入选依据", "".join(pack["required_output"]))
        self.assertIn("不再单独输出 Top 5", "".join(pack["required_output"]))
        self.assertEqual(context["economics_display_guide"], {})
        self.assertEqual(context["economics_evidence_pack"], {})
        self.assertEqual(context["cost_structure_assessment_pack"], {})
        self.assertIn("不要输出独立 `### 成本结构测评`", context["report_instruction"])
        self.assertIn("不要命名为 7 天验证闸门", context["report_instruction"])
        self.assertIn("candidate_discovery", context["report_instruction"])

    def test_candidate_discovery_context_excludes_raw_tikhub_results(self) -> None:
        context = formal_run.report_context(
            {
                "run_id": "candidate-report",
                "report_mode": "candidate_mode",
                "report_mode_label": "候选池调研",
                "search_strategy": "candidate_discovery",
                "search_plan": [
                    {
                        "query": "AI tools people actually pay for complaints",
                        "query_group": "user_feedback",
                        "query_group_label": "用户反馈/痛点",
                    }
                ],
            },
            {
                "search_provider": "tavily+tikhub",
                "tavily_status": "success",
                "search_results": [
                    {
                        "provider": "tikhub",
                        "platform": "reddit",
                        "status": "ok",
                        "query": "AI tools people actually pay for complaints",
                        "query_group": "user_feedback",
                        "query_group_label": "用户反馈/痛点",
                        "results": [
                            {
                                "title": "[Reddit] Raw social result",
                                "url": "https://reddit.example/raw",
                                "content": "Raw social result should not become a candidate source.",
                                "provider": "tikhub",
                            }
                        ],
                    },
                    {
                        "status": "ok",
                        "query": "best AI tools startups",
                        "query_group": "candidate_pool",
                        "query_group_label": "候选池/产品清单",
                        "results": [
                            {
                                "title": "20 AI Tools Founders Actually Use",
                                "url": "https://example.com/founder-tools",
                                "content": "Concrete founder workflows.",
                            }
                        ],
                    },
                ],
            },
            {"public_evidence": [], "evidence_gap_candidates": []},
            "/tmp/candidate-report.json",
        )
        sources = context["candidate_discovery_pack"]["candidate_source_results"]
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["url"], "https://example.com/founder-tools")
        self.assertNotIn("reddit.example", json.dumps(context, ensure_ascii=False))

    def test_html_renderer_hides_report_mode_badge(self) -> None:
        report = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "先验证分发。",
            "---",
            "## 决策问题",
            "报告模式：分发判断",
            "决策对象：AI 会议纪要工具",
            "这一轮真正要回答的是：前 100 个用户从哪里来。",
            "---",
            "## 专家判断",
            "先看证据。",
            "---",
            "## 候选行动",
            "1. 做渠道实验。",
            "---",
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 |",
            "|---|---|---|---|---|",
            "| 高 | 分发 | 有搜索需求 | 先做页面 | [来源](https://example.com) |",
            "---",
            "## 缺失的证据",
            "- 缺少真实点击。",
            "---",
            "## 下一步行动",
            "1. 发布一个 demo。",
        ])
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn("<title>信息炼金报告-AI 会议纪要工具</title>", html)
        self.assertNotIn("mode-badge", html)
        self.assertNotIn("分发判断", html)
        self.assertNotIn("<span class=\"marker\">报告模式：分发判断", html)

    def test_visual_report_preserves_question_and_core_items(self) -> None:
        report = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "一句话总结：先找真实需求。",
            "1. 新产品机会是有的，但不是追热点。",
            "2. 不建议从大而全平台起步。",
            "3. 优先放在垂直小需求。",
            "---",
            "## 决策问题",
            "这一轮真正要回答的是：",
            "1. 哪个机会最接近真实需求？",
            "2. 哪个机会最适合低成本验证？",
            "3. 哪个机会能先验证点击和留资？",
            "4. 哪个机会短期能跑通获客？",
            "---",
            "## 专家判断",
            "先看证据。",
            "---",
            "## 候选行动",
            "### 方向 A：垂直任务型小工具",
            "- 面向某一类用户",
            "---",
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 |",
            "|---|---|---|---|---|",
            "| 高 | 市场趋势 | 有需求 | 先验证 | [来源](https://example.com) |",
            "---",
            "## 缺失的证据",
            "### 1. 真实受众会不会行动",
            "- 没有点击",
            "---",
            "## 下一步行动",
            "### 第一步：先挑 3 个机会类型",
            "- 垂直任务型小工具",
        ])
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn("question-item", html)
        self.assertIn("core-card", html)
        self.assertIn("哪个机会最接近真实需求？", html)
        self.assertIn("这一轮真正要回答的是：", html)
        self.assertIn("不建议从大而全平台起步。", html)
        self.assertNotIn("class=\"target\"", html)

    def test_action_cards_split_internal_blocks(self) -> None:
        report = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "先小范围验证。",
            "---",
            "## 决策问题",
            "是否继续？",
            "---",
            "## 专家判断",
            "先看证据。",
            "---",
            "## 候选行动",
            "### 方向 A：垂直任务型小工具",
            "典型特征：",
            "- 面向某一类用户",
            "- 解决某一个高频任务",
            "为什么优先：",
            "- 更容易讲清价值",
            "- 更容易测试转化",
            "我的判断： **这是当前最适合独立开发者筛新机会的形态。**",
            "---",
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 |",
            "|---|---|---|---|---|",
            "| 高 | 市场趋势 | 有需求 | 先验证 | [来源](https://example.com) |",
            "---",
            "## 缺失的证据",
            "- 点击",
            "---",
            "## 下一步行动",
            "1. 做落地页。",
        ])
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn('class="sticky-note rotate-1"', html)
        self.assertNotIn('class="action-module action-module-compact"', html)
        self.assertIn("action-detail-section", html)
        self.assertIn("action-detail-list", html)
        self.assertIn("<span>1</span>", html)
        self.assertNotIn('class="note-section"', html)
        self.assertNotIn('class="note-verdict"', html)
        self.assertIn("典型特征", html)
        self.assertIn("我的判断", html)
        self.assertIn("这是当前最适合独立开发者筛新机会的形态。", html)

    def test_action_top_five_keeps_h4_recommendations(self) -> None:
        report = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "先小范围验证。",
            "## 决策问题",
            "是否继续？",
            "## 专家判断",
            "先看证据。",
            "## 候选行动",
            "### Top 5 推荐",
            "#### 1）评论分析工具",
            "适合你的原因：",
            "- 能做 SEO",
            "可先切的子场景：",
            "- Amazon 评论总结",
            "#### 2）SEO 页面生成器",
            "适合你的原因：",
            "- 和建站目标贴合",
            "### 明确淘汰项",
            "- 泛 AI 工具导航站：红海。",
            "### 我对你更现实的切法",
            "先做评论分析。",
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 |",
            "|---|---|---|---|---|",
            "| 高 | 市场趋势 | 有需求 | 先验证 | [来源](https://example.com) |",
            "## 缺失的证据",
            "- 点击",
            "## 下一步行动",
            "1. 做落地页。",
        ])
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn('class="sticky-note rotate-1"', html)
        self.assertNotIn('<div class="action-card-grid">', html)
        self.assertNotIn('class="action-module">', html)
        self.assertIn("评论分析工具", html)
        self.assertNotIn("<h3>1）评论分析工具</h3>", html)
        self.assertIn("SEO 页面生成器", html)
        self.assertEqual(html.count('class="sticky-note'), 2)
        self.assertIn('class="action-followup-pair"', html)
        self.assertIn('class="action-followup"', html)
        self.assertIn(".action-followup-pair::before", html)
        self.assertNotIn('<div class="note-index">3</div>', html)
        self.assertNotIn('<div class="note-index">4</div>', html)
        self.assertIn("Amazon 评论总结", html)
        self.assertIn("泛 AI 工具导航站", html)
        self.assertIn("先做评论分析", html)

    def test_candidate_discovery_action_screen_keeps_ranked_candidate_pool_without_top_five(self) -> None:
        directions = [
            "AI 评论分析工具",
            "AI 落地页 / SEO 页面生成器",
            "AI 外联与销售跟进助手",
            "AI 轻自动化 / 个人工作流代理",
            "AI 定价 / 竞品监控工具",
            "AI 文档结构化工具",
            "AI 多语言本地化页面工具",
            "AI 表单到数据库清洗工具",
            "AI 会议纪要再加工工具",
            "AI 竞品监控工具",
            "AI 客服知识库工具",
            "AI 数据报表解释工具",
        ]
        groups = ["方案 A"] * 5 + ["方案 B"] * 3 + ["方案 C"] * 3 + ["方案 D"]
        candidate_rows = "\n".join(
            f"| {index} | {groups[index - 1]} | {direction} | [示例产品 {index}](https://example.com/{index}) | 来自候选池/产品清单与用户任务交叉出现 | 任务 {index} | 付费信号 {index} | SEO 入口 {index} | 中 | 低成本文本 MVP | {'先试' if index <= 5 else '观察'} |"
            for index, direction in enumerate(directions, start=1)
        )
        report = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "先按优先级看 12 个候选。",
            "## 决策问题",
            "报告模式：候选池调研",
            "决策对象：现在有哪些 AI 产品可以做",
            "## 专家判断",
            "先看证据。",
            "## 候选行动",
            "### 方案 A：先验证轻量工具站",
            "代表产品：",
            "- [示例产品 1](https://example.com/1)",
            "- [示例产品 2](https://example.com/2)",
            "典型流程：",
            "- 上传素材 -> 生成结果 -> 付费导出。",
            "适合借鉴：",
            "- 单结果承诺。",
            "- 低成本文本 MVP。",
            "先验证：",
            "- 用户是否愿意上传真实素材。",
            "避坑：",
            "- 不要做泛平台。",
            "### 方案 B：拆解销售流程站",
            "代表产品：",
            "- [示例产品 6](https://example.com/6)",
            "典型流程：",
            "- 输入线索 -> 生成跟进方案 -> 进入销售动作。",
            "适合借鉴：",
            "- B2B 付费场景。",
            "先验证：",
            "- 谁愿意为这个流程付费。",
            "避坑：",
            "- 交付链条长。",
            "### 方案 C：观察监控工具站",
            "代表产品：",
            "- [示例产品 9](https://example.com/9)",
            "典型流程：",
            "- 输入对象 -> 周期监控 -> 输出变化。",
            "适合借鉴：",
            "- 作为后续模块。",
            "先验证：",
            "- 是否有明确付费场景。",
            "避坑：",
            "- 入口不清晰。",
            "### 候选产品拆解表",
            "| # | 行动分组 | 候选方向 | 代表产品 | 入选依据 | 用户任务 | 付费信号 | SEO/分发入口 | 竞品/风险 | MVP/成本 | 建议 |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
            candidate_rows,
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 |",
            "|---|---|---|---|---|",
            "| 高 | 候选池 | 有候选 | 先筛选 | [来源](https://example.com) |",
            "## 缺失的证据",
            "- 真实付费率",
            "## 下一步行动",
            "1. 做候选打分。",
        ])
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn("candidate-pool-board", html)
        self.assertIn('class="report-table candidate-pool-table"', html)
        self.assertEqual(html.count("<tr>"), 13)
        self.assertNotIn('class="candidate-pool-card"', html)
        table_index = html.index('<section class="candidate-pool-board">')
        self.assertLess(html.index("方案 A：先验证轻量工具站"), table_index)
        self.assertLess(html.index("方案 B：拆解销售流程站"), table_index)
        self.assertLess(html.index("方案 C：观察监控工具站"), table_index)
        self.assertIn("候选产品拆解表", html)
        self.assertNotIn("<span>12 个候选</span>", html)
        self.assertIn("AI 评论分析工具", html)
        self.assertIn("AI 数据报表解释工具", html)
        self.assertNotIn("<th>行动分组</th>", html)
        self.assertNotIn("<th>SEO 入口</th>", html)
        self.assertNotIn("<th>SEO/分发入口</th>", html)
        self.assertNotIn("<th>建议</th>", html)
        self.assertNotIn("SEO 入口 12", html)
        self.assertNotIn("<th>优先级</th>", html)
        self.assertIn("入选依据", html)
        self.assertIn("来自候选池/产品清单", html)
        self.assertIn("低成本文本 MVP", html)
        self.assertIn("<b>适合借鉴</b>", html)
        self.assertNotIn("<b>可借鉴</b>", html)
        self.assertNotIn("<b>适合借</b>", html)
        self.assertIn("AI 落地页 / SEO 页面生成器", html)
        self.assertNotIn("Top 5 推荐", html)
        self.assertIn("代表产品", html)
        self.assertNotIn("代表产品/工具站", html)
        self.assertNotIn("<h3>候选池对比（10-15 个）</h3>", html)

    def test_visual_report_sorts_strength_badges_high_to_low(self) -> None:
        report = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "先看强信号。",
            "---",
            "## 决策问题",
            "是否继续？",
            "---",
            "## 专家判断",
            "| 领域专家 | 专家/实践者信号 | 来自渠道 | 为什么选 | 他们关注的问题 | 当前解法 | 对我们的启发 | 可信度 |",
            "|---|---|---|---|---|---|---|---|",
            "| 专家中 | 信号 | 来源 | 理由 | 问题 | 解法 | 启发 | 中 |",
            "| 专家高 | 信号 | 来源 | 理由 | 问题 | 解法 | 启发 | 高 |",
            "| 专家低 | 信号 | 来源 | 理由 | 问题 | 解法 | 启发 | 低 |",
            "| 专家中高 | 信号 | 来源 | 理由 | 问题 | 解法 | 启发 | 中高 |",
            "---",
            "## 候选行动",
            "1. 做小范围验证。",
            "---",
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 |",
            "|---|---|---|---|---|",
            "| 中 | 证据中 | 中证据 | 中行动 | [来源](https://example.com/mid) |",
            "| 高 | 证据高 | 高证据 | 高行动 | [来源](https://example.com/high) |",
            "| 低 | 证据低 | 低证据 | 低行动 | [来源](https://example.com/low) |",
            "| 中高 | 证据中高 | 中高证据 | 中高行动 | [来源](https://example.com/midhigh) |",
            "---",
            "## 缺失的证据",
            "- 点击",
            "---",
            "## 下一步行动",
            "1. 做落地页。",
        ])
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertLess(html.index("<h3>专家高</h3>"), html.index("<h3>专家中高</h3>"))
        self.assertLess(html.index("<h3>专家中高</h3>"), html.index("<h3>专家中</h3>"))
        self.assertLess(html.index("<h3>专家中</h3>"), html.index("<h3>专家低</h3>"))
        self.assertLess(html.index("<strong>证据高</strong>"), html.index("<strong>证据中高</strong>"))
        self.assertLess(html.index("<strong>证据中高</strong>"), html.index("<strong>证据中</strong>"))
        self.assertLess(html.index("<strong>证据中</strong>"), html.index("<strong>证据低</strong>"))
        self.assertIn("expert-confidence level-high", html)
        self.assertIn("expert-confidence level-mid-high", html)
        self.assertIn("impact level-high", html)
        self.assertIn("impact level-mid-high", html)

    def test_gap_and_next_modules_preserve_detail_text(self) -> None:
        report = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "先小范围验证。",
            "## 决策问题",
            "是否继续？",
            "## 专家判断",
            "先看证据。",
            "## 候选行动",
            "1. 做小范围验证。",
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 |",
            "|---|---|---|---|---|",
            "| 高 | 市场趋势 | 有需求 | 先验证 | [来源](https://example.com) |",
            "## 缺失的证据",
            "当前仍缺两类最关键证据：",
            "### 1. 你自己的真实受众是否会行动",
            "公开资料只能说明“这个方向合理”，",
            "不能说明“你的目标用户会不会点”。",
            "最关键还要看：",
            "- 有没有点击",
            "- 有没有留资",
            "### 2. 候选方向的单位经济是否成立",
            "比如：",
            "- 获取一个潜在用户要多少钱",
            "- 转化率大概多少",
            "如果没有这两类证据，方向只能算“值得验证”。",
            "## 下一步行动",
            "我建议你不要继续停留在“笼统找新机会”。",
            "### 第一步：先挑 3 个机会类型",
            "建议优先从这 3 类里挑：",
            "1. **垂直任务型小工具**",
            "2. **内容先行、产品后置的验证型站点**",
            "### 方案 1",
            "**给你 10 个可验证的新产品机会，按赚钱概率排序**",
        ])
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn("module-intro", html)
        self.assertIn("公开资料只能说明", html)
        self.assertIn("如果没有这两类证据", html)
        self.assertIn("给你 10 个可验证的新产品机会", html)
        self.assertIn("垂直任务型小工具", html)

    def test_next_stop_rule_splits_condition_and_action(self) -> None:
        report = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "先小范围验证。",
            "---",
            "## 决策问题",
            "是否继续？",
            "---",
            "## 专家判断",
            "先看证据。",
            "---",
            "## 候选行动",
            "1. 做小范围验证。",
            "---",
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 |",
            "|---|---|---|---|---|",
            "| 高 | 市场趋势 | 有需求 | 先验证 | [来源](https://example.com) |",
            "---",
            "## 缺失的证据",
            "- 点击",
            "---",
            "## 下一步行动",
            "### 停止规则",
            "如果你发现：",
            "- 用户必须重试很多次才满意",
            "- 商用授权必须上高价套餐才成立",
            "- 单个用户一月的生成消耗接近或超过订阅价格",
            "那这个方向就别做开放生成产品，改做：",
            "- 更窄场景工具",
            "- 半自动工作流",
            "- 结果导向型服务",
        ])
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn("stop-rule-flow", html)
        self.assertIn("停止信号", html)
        self.assertIn("立即动作", html)
        self.assertIn("转向方向", html)
        self.assertIn("用户必须重试很多次才满意", html)
        self.assertIn("更窄场景工具", html)
        self.assertIn("别做开放生成产品", html)

    def test_next_stop_rule_handles_action_before_signal_bullets(self) -> None:
        report = "\n".join([
            "INFO_ALCHEMIST=TRUE",
            "# 信息炼金报告",
            "## 核心判断",
            "先拆流程。",
            "---",
            "## 决策问题",
            "是否做站？",
            "---",
            "## 专家判断",
            "先看证据。",
            "---",
            "## 候选行动",
            "1. 做小范围验证。",
            "---",
            "## 高价值证据",
            "| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 |",
            "|---|---|---|---|---|",
            "| 高 | 流程 | 有需求 | 先验证 | [来源](https://example.com) |",
            "---",
            "## 缺失的证据",
            "- 点击",
            "---",
            "## 下一步行动",
            "### 停止规则",
            "如果拆完 3 个站后你发现：",
            "那就先别做站，先做**更窄的工作流工具或 skill**。",
            "- 你真正想做的只是“再包一层生成能力”",
            "- 没有新的流程创新",
            "- 也没有更窄的目标用户",
        ])
        html = render_html_report.build_html(report, "unit-report", "http://127.0.0.1:8765/unit-report.html")
        self.assertIn("stop-rule-flow", html)
        self.assertIn("停止信号", html)
        self.assertIn("你真正想做的只是", html)
        self.assertIn("没有新的流程创新", html)
        self.assertIn("立即动作", html)
        self.assertIn("先别做站", html)
        self.assertIn("转向方向", html)
        self.assertIn("更窄的工作流工具或 skill", html)


if __name__ == "__main__":
    unittest.main()
