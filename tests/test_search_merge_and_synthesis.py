#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import synthesize_tavily_results  # noqa: E402
import tavily_search  # noqa: E402


class SearchMergeAndSynthesisTest(unittest.TestCase):
    def test_failed_vertical_groups_do_not_create_false_partial_success(self) -> None:
        payload = {
            "search_provider": "tavily",
            "tavily_status": "failure",
            "tavily_status_label": "本轮联网搜索全部失败",
            "error_summary": "本轮联网搜索全部失败，不能生成证据报告。",
            "error": "本轮联网搜索全部失败，不能生成证据报告。",
            "failed_queries": [{"query": "AI 视频站"}],
            "search_results": [],
        }
        vertical_payload = {
            "enabled": True,
            "api_base": "https://api.tikhub.io",
            "platforms": ["reddit"],
            "status": "failure",
            "status_label": "垂直社媒搜索全部失败",
            "failed_queries": [{"query": "AI video generator", "platform": "reddit"}],
            "search_results": [
                {
                    "provider": "tikhub",
                    "platform": "reddit",
                    "status": "failed",
                    "query": "AI video generator",
                    "error": "timeout",
                    "answer": "",
                    "results": [],
                }
            ],
        }
        merged = tavily_search.merge_tikhub_payload(payload, vertical_payload)
        self.assertEqual(merged["tavily_status"], "failure")
        self.assertEqual(merged["search_provider"], "tavily")
        self.assertIn("error", merged)
        self.assertEqual(merged["vertical_search"]["successful_groups"], 0)
        self.assertEqual(merged["search_results"], [])
        self.assertEqual(merged["failed_queries"], payload["failed_queries"])

    def test_failed_vertical_groups_do_not_affect_successful_primary_search(self) -> None:
        payload = {
            "search_provider": "tavily",
            "tavily_status": "success",
            "tavily_status_label": "本轮联网搜索全部成功",
            "error_summary": "",
            "failed_queries": [],
            "search_results": [
                {
                    "status": "ok",
                    "query": "AI 视频站 official API pricing documentation",
                    "search_intent": "official_capability",
                    "answer": "",
                    "results": [
                        {
                            "title": "Official docs",
                            "url": "https://example.com/docs",
                            "content": "Official capability documentation.",
                            "score": 0.8,
                        }
                    ],
                }
            ],
        }
        vertical_payload = {
            "enabled": True,
            "api_base": "https://api.tikhub.io",
            "platforms": ["xhs", "x", "reddit"],
            "status": "failure",
            "status_label": "垂直社媒搜索全部失败",
            "failed_queries": [{"query": "AI 视频生成工具", "platform": "xhs"}],
            "search_results": [
                {
                    "provider": "tikhub",
                    "platform": "xhs",
                    "status": "failed",
                    "query": "AI 视频生成工具",
                    "error": "timeout",
                    "answer": "",
                    "results": [],
                }
            ],
        }
        merged = tavily_search.merge_tikhub_payload(payload, vertical_payload)
        self.assertEqual(merged["tavily_status"], "success")
        self.assertEqual(merged["search_provider"], "tavily")
        self.assertEqual(merged["search_results"], payload["search_results"])
        self.assertEqual(merged["failed_queries"], [])
        self.assertEqual(merged["vertical_search"]["failed_groups"], 1)

    def test_successful_vertical_groups_can_rescue_failed_primary_search(self) -> None:
        payload = {
            "search_provider": "tavily",
            "tavily_status": "failure",
            "tavily_status_label": "本轮联网搜索全部失败",
            "error_summary": "本轮联网搜索全部失败，不能生成证据报告。",
            "error": "本轮联网搜索全部失败，不能生成证据报告。",
            "failed_queries": [{"query": "AI 视频站"}],
            "search_results": [],
        }
        vertical_payload = {
            "enabled": True,
            "api_base": "https://api.tikhub.io",
            "platforms": ["reddit"],
            "status": "success",
            "status_label": "垂直社媒搜索全部成功",
            "failed_queries": [],
            "debug_trace": [
                {
                    "platform": "reddit",
                    "actual_query": "AI video generator complaints reviews alternatives",
                    "time_strategy": {"mode": "relevance_all"},
                }
            ],
            "search_results": [
                {
                    "provider": "tikhub",
                    "platform": "reddit",
                    "status": "ok",
                    "query": "AI video generator complaints reviews alternatives",
                    "answer": "Reddit 返回 1 条可标准化结果。",
                    "results": [
                        {
                            "title": "Best AI video generator?",
                            "url": "https://reddit.example/post",
                            "content": "Users compare pricing limits and output quality.",
                            "score": 0.8,
                        }
                    ],
                }
            ],
        }
        merged = tavily_search.merge_tikhub_payload(payload, vertical_payload)
        self.assertEqual(merged["tavily_status"], "partial_failure")
        self.assertEqual(merged["search_provider"], "tavily+tikhub")
        self.assertNotIn("error", merged)
        self.assertEqual(merged["vertical_search"]["successful_groups"], 1)
        self.assertEqual(merged["vertical_search"]["debug_trace"][0]["time_strategy"]["mode"], "relevance_all")

    def test_tikhub_synthesis_uses_evidence_content_not_meta_answer(self) -> None:
        output = synthesize_tavily_results.synthesize({
            "search_provider": "tavily+tikhub",
            "tavily_status": "success",
            "search_results": [
                {
                    "provider": "tikhub",
                    "platform": "reddit",
                    "status": "ok",
                    "query": "AI video generator complaints reviews alternatives",
                    "source_query": "AI 视频站 user reviews complaints reddit product hunt",
                    "search_intent": "user_discussion",
                    "answer": "Reddit 返回 1 条可标准化结果。",
                    "results": [
                        {
                            "title": "AI video pricing complaints",
                            "url": "https://reddit.example/post",
                            "content": "Users complain about credits, watermarks, and unreliable generation.",
                            "score": 0.7,
                        },
                        {
                            "title": "Alternative workflow",
                            "url": "https://reddit.example/post2",
                            "content": "Several users mention switching tools when rendering fails.",
                            "score": 0.6,
                        }
                    ],
                }
            ],
        })
        self.assertEqual(output["search_provider"], "tavily+tikhub")
        self.assertEqual(output["public_evidence"], [])
        finding = output["social_platform_signals"][0]["current_finding"]
        self.assertIn("Users complain about credits", finding)
        self.assertNotIn("返回 1 条可标准化结果", finding)
        self.assertGreaterEqual(output["social_debug_trace"][0]["usable_count"], 1)
        self.assertEqual(output["social_debug_trace"][0]["platform"], "Reddit")

    def test_tavily_synthesis_prefers_selected_source_content_over_answer(self) -> None:
        output = synthesize_tavily_results.synthesize({
            "search_provider": "tavily",
            "tavily_status": "success",
            "search_results": [
                {
                    "status": "ok",
                    "query": "OpenAI image video generation API pricing official documentation Sora",
                    "search_intent": "official_capability",
                    "evidence_axis": "official",
                    "answer": "Sora is built by Amazon and should not be trusted here.",
                    "results": [
                        {
                            "title": "Video generation - OpenAI API",
                            "url": "https://developers.openai.com/api/docs/guides/video-generation",
                            "content": "Official OpenAI documentation explains video generation models, prompting, output formats, and API constraints.",
                            "score": 0.8,
                        }
                    ],
                }
            ],
        })
        finding = output["public_evidence"][0]["finding"]
        self.assertIn("Official OpenAI documentation", finding)
        self.assertNotIn("Amazon", finding)
        scores = output["public_evidence"][0]["scores"]
        self.assertGreaterEqual(scores["evidence_quality"], 90)
        self.assertGreaterEqual(scores["voi"], 60)
        self.assertNotIn("decision_relevance", scores)
        self.assertNotIn("verifiability", scores)

    def test_synthesis_demotes_irrelevant_generic_result_even_with_high_score(self) -> None:
        output = synthesize_tavily_results.synthesize({
            "search_provider": "tavily",
            "tavily_status": "success",
            "search_results": [
                {
                    "status": "ok",
                    "query": "\"sleep calculator\" search volume keyword difficulty SEO",
                    "search_intent": "search_intent",
                    "evidence_axis": "distribution",
                    "answer": "",
                    "results": [
                        {
                            "title": "Keyword Difficulty: What Is It & How To Measure It",
                            "url": "https://www.spyfu.com/blog/keyword-difficulty",
                            "content": "A generic guide to keyword difficulty and SEO metrics.",
                            "score": 0.99,
                        },
                        {
                            "title": "Sleep Calculator: bedtime and wake-up search demand",
                            "url": "https://example.com/sleep-calculator-keywords",
                            "content": "Sleep calculator pages target bedtime calculator, sleep cycle calculator, and wake-up time calculator searches.",
                            "score": 0.5,
                        },
                    ],
                }
            ],
        })
        evidence = output["public_evidence"][0]
        self.assertIn("Sleep Calculator", evidence["source"]["title"])
        self.assertEqual(evidence["source_quality"], "medium")

    def test_synthesis_skips_low_quality_expert_signal(self) -> None:
        output = synthesize_tavily_results.synthesize({
            "search_provider": "tavily",
            "tavily_status": "success",
            "search_results": [
                {
                    "status": "ok",
                    "query": "AI 视频站 experts founders practitioners",
                    "search_intent": "expert_signal",
                    "answer": "Spam result should not become expert evidence.",
                    "results": [
                        {
                            "title": "投注网新址的四大优势 n9n9.co[手动输入网址]",
                            "url": "https://x.com/search?q=%E6%8A%95%E6%B3%A8%E7%BD%91",
                            "content": "博彩垃圾结果",
                            "score": 0.9,
                        }
                    ],
                }
            ],
        })
        self.assertEqual(output["expert_judgment"], [])
        self.assertEqual(output["public_evidence"][0]["source_quality"], "low")
        self.assertTrue(any("专家信号来源质量过低" in gap["gap"] for gap in output["evidence_gap_candidates"]))

    def test_synthesis_reports_evidence_coverage(self) -> None:
        output = synthesize_tavily_results.synthesize({
            "search_provider": "tavily",
            "tavily_status": "success",
            "search_results": [
                {
                    "status": "ok",
                    "query": "AI video generator market size",
                    "search_intent": "competitor_and_monetization",
                    "evidence_axis": "market",
                    "answer": "Market is growing.",
                    "results": [{"title": "AI video generator market report", "url": "https://www.grandviewresearch.com/example", "content": "AI video generator growth", "score": 0.8}],
                },
                {
                    "status": "ok",
                    "query": "AI video generator pricing",
                    "search_intent": "api_feasibility",
                    "evidence_axis": "unit_economics",
                    "answer": "Pricing is usage based.",
                    "results": [{"title": "AI video generator pricing", "url": "https://cloud.google.com/example", "content": "AI video generator pricing is per second.", "score": 0.8}],
                },
                {
                    "status": "failed",
                    "query": "AI video generator complaints",
                    "search_intent": "user_discussion",
                    "evidence_axis": "user_pain",
                    "error": "timeout",
                    "results": [],
                },
            ],
        })
        coverage = output["evidence_coverage"]
        self.assertIn("market", coverage["covered_axes"])
        self.assertIn("unit_economics", coverage["covered_axes"])
        self.assertIn("user_pain", coverage["missing_axes"])
        self.assertGreater(coverage["coverage_score_0_5"], 0)
        self.assertTrue(any(axis["evidence_axis"] == "user_pain" and axis["status"] == "missing" for axis in coverage["axis_coverage"]))
        self.assertNotEqual(coverage["conclusion_strength_ceiling"], "strong")

    def test_social_signal_requires_intent_specific_relevance(self) -> None:
        output = synthesize_tavily_results.synthesize({
            "search_provider": "tavily+tikhub",
            "tavily_status": "success",
            "search_results": [
                {
                    "provider": "tikhub",
                    "platform": "xhs",
                    "status": "ok",
                    "source_query": "AI video generator product onboarding workflow first use examples",
                    "query": "AI 视频生成工具 不好用 太贵 用户评价 投诉 替代",
                    "search_intent": "user_discussion",
                    "results": [
                        {
                            "title": "[小红书] 七大火热AI视频工具推荐",
                            "url": "",
                            "content": "#海螺AI #可灵AI #即梦AI #横测；作者/来源：赛博小梦；互动：liked_count=21101",
                            "score": 1.0,
                        }
                    ],
                }
            ],
        })
        self.assertEqual(output["social_platform_signals"], [])
        self.assertEqual(output["public_evidence"], [])
        self.assertTrue(any("社交搜索结果低相关" in gap["gap"] for gap in output["evidence_gap_candidates"]))

    def test_social_signal_keeps_workflow_specific_hit(self) -> None:
        output = synthesize_tavily_results.synthesize({
            "search_provider": "tavily+tikhub",
            "tavily_status": "success",
            "search_results": [
                {
                    "provider": "tikhub",
                    "platform": "x",
                    "status": "ok",
                    "source_query": "AI video generator product onboarding workflow first use examples",
                    "query": "AI video generator product onboarding workflow first use examples",
                    "search_intent": "user_discussion",
                    "results": [
                        {
                            "title": "[X] founder workflow teardown",
                            "url": "https://x.com/i/web/status/123",
                            "content": "A founder explains the AI video generator onboarding workflow, first use path, and product demo sequence.",
                            "score": 0.8,
                        }
                    ],
                }
            ],
        })
        self.assertEqual(len(output["social_platform_signals"]), 1)
        self.assertEqual(output["public_evidence"], [])

    def test_xhs_text_note_with_cdn_url_can_be_usable_social_signal(self) -> None:
        output = synthesize_tavily_results.synthesize({
            "search_provider": "tavily+tikhub",
            "tavily_status": "success",
            "search_results": [
                {
                    "provider": "tikhub",
                    "platform": "xhs",
                    "status": "ok",
                    "source_query": "AI product ideas vertical AI tools categories startups 2026",
                    "query": "AI工具 付费 体验 踩坑",
                    "search_intent": "user_discussion",
                    "results": [
                        {
                            "title": "[小红书] AI课程踩坑｜2730追回2184，花钱买教训",
                            "url": "https://sns-na-i8.xhscdn.com/1040g00832094v97em2105o753b6095q4iopvobg?imageView2/2/w/576",
                            "content": "花2730报名的AI变现课，宣传和实际差距太大，果断申请退款；互动：liked_count=11",
                            "score": 0.6,
                            "metric_total": 11,
                        }
                    ],
                }
            ],
        })
        self.assertEqual(len(output["social_platform_signals"]), 1)
        signal = output["social_platform_signals"][0]
        self.assertEqual(signal["platform"], "小红书")
        self.assertIn("AI课程踩坑", signal["current_finding"])
        self.assertEqual(output["public_evidence"], [])


if __name__ == "__main__":
    unittest.main()
