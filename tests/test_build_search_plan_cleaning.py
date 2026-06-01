#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import build_search_plan  # noqa: E402
import semantic_router  # noqa: E402


class BuildSearchPlanCleaningTest(unittest.TestCase):
    def test_extract_topic_strips_activation_marker(self) -> None:
        topic = build_search_plan.extract_topic("用 INFO_ALCHEMIST AI 视频站有没有机会，我想看看要不要做相关工具站")
        self.assertEqual(topic, "AI 视频站")

    def test_extract_topic_strips_activation_marker_without_space(self) -> None:
        topic = build_search_plan.extract_topic("用 INFO_ALCHEMIST查一下新产品机会")
        self.assertEqual(topic, "新产品机会")

    def test_build_plan_sanitizes_all_queries(self) -> None:
        output, _, exit_code, _ = build_search_plan.build_plan({
            "user_query": "用 INFO_ALCHEMIST AI 视频站有没有机会，我想看看要不要做相关工具站",
            "query_type": "opportunity_research",
            "confirmed_intent": "判断要不要做一个新工具站",
            "decision_clarity": "clear",
            "action_context": "new_product_validation",
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        self.assertEqual(output["topic"], "AI 视频站")
        self.assertTrue(output["search_plan"])
        for item in output["search_plan"]:
            self.assertNotRegex(item["query"], r"INFO[\s_-]*ALCHEMIST")
            self.assertNotIn("用  ", item["query"])

    def test_activation_only_query_is_blocked(self) -> None:
        output, _, exit_code, status = build_search_plan.build_plan({
            "user_query": "用 INFO_ALCHEMIST",
            "query_type": "opportunity_research",
        }, run_id="test-run")
        self.assertEqual(exit_code, 2)
        self.assertEqual(status, "blocked")
        self.assertTrue(output["needs_confirmation"])
        self.assertEqual(output["search_plan"], [])

    def test_ai_video_vs_image_choice_uses_hard_evidence_queries(self) -> None:
        output, _, exit_code, _ = build_search_plan.build_plan({
            "user_query": "查一下我应该做AI视频站还是AI图片站？还是都做？",
            "query_type": "opportunity_research",
            "decision_clarity": "clear",
            "action_context": "choice_decision",
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        self.assertEqual(output["topic"], "AI 视频站 vs AI 图片站")
        queries = [item["query"] for item in output["search_plan"]]
        joined = "\n".join(queries)
        self.assertIn("AI video generator market size", joined)
        self.assertIn("AI image generator market size", joined)
        self.assertIn("Google Veo Imagen API pricing", joined)
        self.assertIn("a16z Top 100 Gen AI Consumer Apps", joined)
        self.assertNotIn("我应该做", joined)
        axes = {item.get("evidence_axis") for item in output["search_plan"]}
        self.assertTrue({"market", "official", "unit_economics", "competition", "user_pain", "distribution", "risk"}.issubset(axes))

    def test_tool_opportunity_plan_covers_general_evidence_axes(self) -> None:
        output, _, exit_code, _ = build_search_plan.build_plan({
            "user_query": "用 INFO_ALCHEMIST AI 视频站有没有机会，我想看看要不要做相关工具站",
            "query_type": "opportunity_research",
            "confirmed_intent": "判断要不要做一个新工具站",
            "decision_clarity": "clear",
            "action_context": "new_product_validation",
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        axes = {item.get("evidence_axis") for item in output["search_plan"]}
        self.assertTrue({"market", "official", "unit_economics", "competition", "user_pain", "distribution", "risk"}.issubset(axes))
        queries = "\n".join(item["query"] for item in output["search_plan"])
        self.assertIn("AI video generator market size", queries)
        self.assertNotIn("AI 视频站 market size", queries)

    def test_candidate_discovery_plan_starts_with_candidate_pool(self) -> None:
        route = semantic_router.route_query("现在有哪些 AI 产品可以做")
        output, intent_payload, exit_code, status = build_search_plan.build_plan({
            "user_query": "现在有哪些 AI 产品可以做",
            "semantic_route": route,
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        self.assertEqual(status, "ok")
        self.assertEqual(output["search_strategy"], "candidate_discovery")
        self.assertEqual(intent_payload["search_strategy"], "candidate_discovery")
        groups = [item.get("query_group") for item in output["search_plan"]]
        self.assertIn("candidate_pool", groups[:3])
        self.assertIn("competitor_pool", groups)
        self.assertIn("growth_seo", groups)
        self.assertIn("pricing", groups)
        self.assertIn("commercial_benchmark", groups)
        queries = "\n".join(item["query"] for item in output["search_plan"])
        self.assertIn("revenue benchmark conversion rate", queries)
        self.assertIn("Product Hunt AI tools launches", queries)
        self.assertNotIn("official API pricing documentation", queries)

    def test_domain_scan_reply_uses_narrowed_candidate_topic(self) -> None:
        route = semantic_router.resolve_reply("想看看市面上有哪些 AI 工具", "2 + 图片视频")
        output, intent_payload, exit_code, status = build_search_plan.build_plan({
            "user_query": "想看看市面上有哪些 AI 工具",
            "semantic_route": route,
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        self.assertEqual(status, "ok")
        self.assertEqual(output["topic"], "图片视频 AI 工具")
        self.assertEqual(output["action_context"], "domain_scan")
        self.assertEqual(output["search_strategy"], "candidate_discovery")
        self.assertEqual(intent_payload["search_strategy"], "candidate_discovery")
        groups = {item.get("query_group") for item in output["search_plan"]}
        self.assertIn("candidate_pool", groups)
        self.assertIn("segment_map", groups)
        queries = "\n".join(item["query"] for item in output["search_plan"])
        self.assertIn("image and video", queries.lower())

    def test_domain_scan_reply_rewrites_office_document_queries(self) -> None:
        route = semantic_router.resolve_reply("想看看市面上有哪些 AI 工具", "2 + 办公文档")
        output, _, exit_code, status = build_search_plan.build_plan({
            "user_query": "想看看市面上有哪些 AI 工具",
            "semantic_route": route,
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        self.assertEqual(status, "ok")
        self.assertEqual(output["topic"], "办公文档 AI 工具")
        queries = "\n".join(item["query"] for item in output["search_plan"]).lower()
        self.assertIn("document productivity", queries)
        self.assertNotIn("ai tools product categories", queries)

    def test_clear_target_does_not_use_candidate_discovery_plan(self) -> None:
        route = semantic_router.route_query("AI SEO brief generator 值不值得做")
        output, _, exit_code, _ = build_search_plan.build_plan({
            "user_query": "AI SEO brief generator 值不值得做",
            "semantic_route": route,
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        self.assertEqual(output["search_strategy"], "normal_evidence")
        groups = {item.get("query_group") for item in output["search_plan"]}
        self.assertNotIn("candidate_pool", groups)
        self.assertIn("commercial_benchmark", groups)

    def test_candidate_discovery_keeps_vertical_modifier_in_queries(self) -> None:
        route = semantic_router.route_query("有哪些 AI SEO 工具站值得做")
        output, _, exit_code, _ = build_search_plan.build_plan({
            "user_query": "有哪些 AI SEO 工具站值得做",
            "semantic_route": route,
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        self.assertEqual(output["topic"], "AI SEO 工具站")
        self.assertEqual(output["search_strategy"], "candidate_discovery")
        queries = "\n".join(item["query"] for item in output["search_plan"])
        self.assertIn("AI SEO tools", queries)
        self.assertNotIn("\"AI tools\" SEO landing pages", queries)
        self.assertNotIn("tools tools", queries)

    def test_specific_ai_tool_topic_is_rewritten_without_losing_modifier(self) -> None:
        output, _, exit_code, _ = build_search_plan.build_plan({
            "user_query": "用 INFO_ALCHEMIST 查一下游戏配乐 AI 工具站值不值得做",
            "query_type": "opportunity_research",
            "decision_clarity": "clear",
            "action_context": "new_product_validation",
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        queries = "\n".join(item["query"] for item in output["search_plan"])
        self.assertIn("AI game music generator", queries)
        self.assertNotIn("AI tools market size", queries)

    def test_tool_like_seo_growth_uses_seo_queries_not_api_plan(self) -> None:
        output, _, exit_code, _ = build_search_plan.build_plan({
            "user_query": "我想做睡眠计算器网站，主要判断有没有 SEO 流量机会",
            "query_type": "opportunity_research",
            "topic": "睡眠计算器网站",
            "decision_clarity": "clear",
            "action_context": "seo_growth",
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        queries = "\n".join(item["query"] for item in output["search_plan"])
        self.assertIn("\"sleep calculator\" search volume", queries)
        self.assertNotIn("official API pricing", queries)

    def test_existing_conversion_uses_conversion_queries_not_api_plan(self) -> None:
        output, _, exit_code, _ = build_search_plan.build_plan({
            "user_query": "我有一个在线简历生成器，想优化付费转化，查竞品怎么做",
            "query_type": "generic_research",
            "topic": "在线简历生成器",
            "decision_clarity": "clear",
            "action_context": "existing_product_conversion",
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        queries = "\n".join(item["query"] for item in output["search_plan"])
        self.assertIn("\"online resume builder\" pricing page", queries)
        self.assertIn("conversion rate churn retention LTV CAC ARPU benchmark", queries)
        self.assertNotIn("official API pricing", queries)

    def test_build_plan_preserves_report_mode_metadata(self) -> None:
        user_query = "以 AI 会议纪要工具 为方向，用户愿意为结果付费，还是只愿意为工具订阅付费？"
        route = semantic_router.route_query(user_query)
        output, intent_payload, exit_code, status = build_search_plan.build_plan({
            "user_query": user_query,
            "semantic_route": route,
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        self.assertEqual(status, "ok")
        self.assertEqual(output["report_mode"], "monetization_mode")
        self.assertEqual(output["report_mode_label"], "商业模式/定价")
        self.assertEqual(intent_payload["report_mode"], "monetization_mode")

    def test_ai_search_plan_draft_is_validated_and_backfilled(self) -> None:
        route = semantic_router.resolve_reply(
            "查一下现在最近有哪些比较火的辅助决策类的AI产品",
            "想借鉴它们的产品流程与逻辑，看创始人信号、产品和做法",
        )
        output, _, exit_code, status = build_search_plan.build_plan({
            "user_query": route["user_query"],
            "semantic_route": route,
            "ai_search_plan": [
                {
                    "query": "AI decision support tools founders interviews product strategy workflow",
                    "search_intent": "expert_signal",
                    "evidence_axis": "expert",
                    "reason": "查辅助决策 AI 产品创始人、产品团队和他们的具体做法。",
                },
                {
                    "query": "AI decision support tools product demo workflow recommendations action plan",
                    "search_intent": "official_capability",
                    "evidence_axis": "official",
                    "reason": "拆真实产品如何把建议变成下一步动作。",
                },
            ],
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        self.assertEqual(status, "ok")
        self.assertEqual(output["search_plan_source"], "build_search_plan.py")
        self.assertEqual(output["search_plan_generation_mode"], "ai_draft_validated_with_template_backfill")
        self.assertEqual(output["ai_search_plan_accepted_count"], 2)
        self.assertEqual(output["search_plan"][0]["planner_source"], "ai_search_plan")
        queries = "\n".join(item["query"] for item in output["search_plan"])
        self.assertIn("AI decision support tools founders interviews product strategy workflow", queries)
        self.assertIn("AI decision support tools product demo workflow recommendations action plan", queries)
        self.assertIn("user reviews", queries)

    def test_reference_topic_removes_popularity_modifiers_from_external_route(self) -> None:
        output, _, exit_code, status = build_search_plan.build_plan({
            "user_query": "现在市面上有哪些比较火的AI视频站可以参考",
            "query_type": "reference_collection",
            "topic": "比较火的AI视频站",
            "decision_clarity": "clear",
            "action_context": "reference_teardown",
            "confirmed_intent": "参考产品流程/逻辑拆解",
            "confirmed_intent_type": "reference_product_experience",
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        self.assertEqual(status, "ok")
        self.assertEqual(output["topic"], "AI视频站")
        queries = "\n".join(item["query"] for item in output["search_plan"])
        self.assertNotIn("比较火", queries)
        self.assertIn("AI video generator founders", queries)

    def test_reference_multi_dimension_keeps_relevant_query_groups(self) -> None:
        output, _, exit_code, status = build_search_plan.build_plan({
            "user_query": "查哪些 AI 视频站值得参考，重点看首页、注册、功能、定价、评论、增长",
            "query_type": "reference_collection",
            "topic": "AI 视频站",
            "decision_clarity": "clear",
            "action_context": "reference_teardown",
            "research_dimensions": [
                "product_experience",
                "business_model",
                "feature_capability",
                "seo_content_structure",
            ],
            "confirmed_intent": "参考产品流程/逻辑拆解；研究维度：产品体验 + 付费/商业模式 + 模型/功能能力 + SEO/内容结构",
            "confirmed_intent_type": "reference_multi_dimension",
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        self.assertEqual(status, "ok")
        self.assertLessEqual(len(output["search_plan"]), build_search_plan.DEFAULT_SEARCH_PLAN_LIMIT)
        groups = {item.get("query_group") for item in output["search_plan"]}
        self.assertTrue({
            "competitor_pool",
            "expert_signal",
            "product_flow",
            "pricing",
            "user_feedback",
            "growth_seo",
            "feature_capability",
        }.issubset(groups))
        self.assertTrue(all(item.get("query_group_label") for item in output["search_plan"]))
        self.assertTrue(all(item.get("query_source") == "template" for item in output["search_plan"]))

    def test_generic_ai_search_plan_item_is_dropped(self) -> None:
        output, _, exit_code, _ = build_search_plan.build_plan({
            "user_query": "查一下 AI 会议纪要工具值不值得做",
            "query_type": "opportunity_research",
            "topic": "AI 会议纪要工具",
            "decision_clarity": "clear",
            "action_context": "new_product_validation",
            "ai_search_plan": [
                {"query": "现在 最近 热门 AI 产品 工具"},
                {"query": "AI meeting notes tool user reviews complaints alternatives", "search_intent": "user_discussion"},
            ],
        }, run_id="test-run")
        self.assertEqual(exit_code, 0)
        self.assertEqual(output["ai_search_plan_accepted_count"], 1)
        queries = "\n".join(item["query"] for item in output["search_plan"])
        self.assertNotIn("现在 最近 热门 AI 产品 工具", queries)
        self.assertIn("AI meeting notes tool user reviews complaints alternatives", queries)


if __name__ == "__main__":
    unittest.main()
