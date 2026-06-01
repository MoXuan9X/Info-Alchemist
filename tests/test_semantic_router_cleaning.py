#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import semantic_router  # noqa: E402


class SemanticRouterCleaningTest(unittest.TestCase):
    def test_route_topic_strips_activation_marker(self) -> None:
        route = semantic_router.route_query("用 INFO_ALCHEMIST AI 视频站有没有机会，我想看看要不要做相关工具站")
        self.assertEqual(route["topic"], "AI 视频站")
        self.assertNotRegex(route["user_query"], r"INFO[\s_-]*ALCHEMIST")

    def test_external_route_topic_strips_activation_marker(self) -> None:
        route = semantic_router.route_query(
            "用 INFO_ALCHEMIST AI 视频站有没有机会",
            {
                "semantic_route": {
                    "query_type": "opportunity_research",
                    "topic": "用 INFO_ALCHEMIST AI 视频站",
                    "action_context": "new_product_validation",
                    "decision_clarity": "clear",
                }
            },
        )
        self.assertEqual(route["topic"], "AI 视频站")

    def test_activation_marker_without_space_is_stripped(self) -> None:
        route = semantic_router.route_query("用 INFO_ALCHEMIST查一下新产品机会")
        self.assertEqual(route["user_query"], "查一下新产品机会")
        self.assertNotRegex(route["user_query"], r"INFO[\s_-]*ALCHEMIST")
        self.assertEqual(route["topic"], "新产品机会")

    def test_query_once_prefix_is_stripped(self) -> None:
        route = semantic_router.route_query("查询一下最近很火、的AI工具站有哪些")
        self.assertNotIn("一下", route["topic"])
        self.assertEqual(route["topic"], "AI 工具站")

    def test_popular_tool_collection_requires_confirmation(self) -> None:
        route = semantic_router.route_query("查询一下最近很火、的AI工具站有哪些")
        self.assertEqual(route["query_type"], "reference_collection")
        self.assertTrue(route["needs_confirmation"])
        self.assertEqual(route["trigger_level"], "clarify")
        self.assertIn("INFO_ALCHEMIST=TRUE", route["confirmation_question"])
        self.assertIn("按具体领域看工具", route["confirmation_question"])

    def test_broad_ai_tools_query_asks_for_purpose_and_direction(self) -> None:
        route = semantic_router.route_query("想看看市面上有哪些 AI 工具")
        self.assertEqual(route["query_type"], "opportunity_research")
        self.assertEqual(route["topic"], "AI 工具")
        self.assertTrue(route["needs_confirmation"])
        self.assertEqual(route["trigger_level"], "clarify")
        self.assertEqual(route["action_context"], "")
        self.assertEqual(route["confirmation_variant"], "broad_ai_tools")
        self.assertIn("按你的能力筛可做方向", route["confirmation_question"])
        self.assertIn("2 + 领域", route["confirmation_question"])

    def test_broad_ai_tools_variants_use_same_scope_question(self) -> None:
        queries = [
            "帮我看看有哪些 AI 工具站",
            "最近有哪些 AI 工具比较火",
            "想了解一下 AI 工具市场",
            "想看 AI 工具分类",
            "what AI tools are popular now",
        ]
        for query in queries:
            with self.subTest(query=query):
                route = semantic_router.route_query(query)
                self.assertTrue(route["needs_confirmation"])
                self.assertEqual(route.get("confirmation_variant"), "broad_ai_tools")
                self.assertEqual(route["action_context"], "")
                self.assertIn("按你的能力筛可做方向", route["confirmation_question"])

    def test_broad_ai_tools_variant_reply_keeps_option_number_semantics(self) -> None:
        route = semantic_router.resolve_reply(
            "最近有哪些 AI 工具比较火",
            "1 + 我擅长建站、SEO、轻开发，想低成本验证",
        )
        self.assertFalse(route["needs_confirmation"])
        self.assertEqual(route["action_context"], "new_product_validation")
        self.assertEqual(route["search_strategy"], "candidate_discovery")
        self.assertEqual(route["report_mode"], "candidate_mode")

    def test_broad_ai_tools_reply_one_enters_candidate_discovery(self) -> None:
        route = semantic_router.resolve_reply(
            "想看看市面上有哪些 AI 工具",
            "1 + 我擅长建站、SEO、轻开发，想低成本验证",
        )
        self.assertFalse(route["needs_confirmation"])
        self.assertEqual(route["action_context"], "new_product_validation")
        self.assertEqual(route["search_strategy"], "candidate_discovery")
        self.assertEqual(route["report_mode"], "candidate_mode")
        self.assertIn("seo_content_structure", route["research_dimensions"])

    def test_broad_ai_tools_reply_two_requires_domain_when_missing(self) -> None:
        route = semantic_router.resolve_reply("想看看市面上有哪些 AI 工具", "2")
        self.assertTrue(route["needs_confirmation"])
        self.assertEqual(route["action_context"], "domain_scan")
        self.assertEqual(route["decision_clarity"], "partial")
        self.assertIn("按具体领域看工具", route["confirmation_question"])

    def test_broad_ai_tools_reply_two_with_domain_narrows_topic(self) -> None:
        route = semantic_router.resolve_reply("想看看市面上有哪些 AI 工具", "2 + 图片视频")
        self.assertFalse(route["needs_confirmation"])
        self.assertEqual(route["action_context"], "domain_scan")
        self.assertEqual(route["topic"], "图片视频 AI 工具")
        self.assertEqual(route["search_strategy"], "candidate_discovery")
        self.assertEqual(route["report_mode"], "candidate_mode")

    def test_broad_ai_tools_reply_three_uses_reference_candidate_pool(self) -> None:
        route = semantic_router.resolve_reply("想看看市面上有哪些 AI 工具", "3 + 想拆首页、定价和新用户流程")
        self.assertFalse(route["needs_confirmation"])
        self.assertEqual(route["action_context"], "reference_teardown")
        self.assertEqual(route["search_strategy"], "candidate_discovery")
        self.assertEqual(route["report_mode"], "teardown_mode")

    def test_broad_ai_tools_reply_four_uses_market_watch_candidate_pool(self) -> None:
        route = semantic_router.resolve_reply("想看看市面上有哪些 AI 工具", "4")
        self.assertFalse(route["needs_confirmation"])
        self.assertEqual(route["action_context"], "market_watch")
        self.assertEqual(route["search_strategy"], "candidate_discovery")
        self.assertEqual(route["report_mode"], "timing_mode")

    def test_popular_tool_collection_keeps_object_after_which_cue(self) -> None:
        route = semantic_router.route_query("查一下现在最近有哪些比较火的辅助决策类的AI产品")
        self.assertEqual(route["query_type"], "reference_collection")
        self.assertEqual(route["topic"], "辅助决策类 AI 产品")
        self.assertIn("辅助决策类 AI 产品", route["confirmation_question"])
        self.assertNotIn("现在最近", route["topic"])

    def test_reference_teardown_reply_sets_teardown_mode(self) -> None:
        route = semantic_router.resolve_reply(
            "查一下现在最近有哪些比较火的辅助决策类的AI产品",
            "想借鉴它们的产品流程与逻辑，看创始人信号、产品和做法",
        )
        self.assertEqual(route["topic"], "辅助决策类 AI 产品")
        self.assertEqual(route["action_context"], "reference_teardown")
        self.assertEqual(route["confirmed_intent_type"], "reference_product_experience")
        self.assertEqual(route["report_mode"], "teardown_mode")
        self.assertIn("product_experience", route["research_dimensions"])
        self.assertIn("feature_capability", route["research_dimensions"])

    def test_broad_product_opportunity_requires_confirmation(self) -> None:
        route = semantic_router.route_query("用 INFO_ALCHEMIST查一下新产品机会")
        self.assertTrue(route["needs_confirmation"])
        self.assertEqual(route["trigger_level"], "clarify")
        self.assertEqual(route["action_context"], "")
        self.assertIn("确认", route["confirmation_question"])

    def test_concrete_product_opportunity_can_run(self) -> None:
        route = semantic_router.route_query("用 INFO_ALCHEMIST查一下游戏配乐 AI 工具站值不值得做")
        self.assertFalse(route["needs_confirmation"])
        self.assertEqual(route["trigger_level"], "full")
        self.assertEqual(route["action_context"], "new_product_validation")
        self.assertEqual(route["topic"], "游戏配乐 AI 工具站")

    def test_ai_video_image_choice_topic_is_normalized(self) -> None:
        route = semantic_router.route_query("查一下我应该做AI视频站还是AI图片站？还是都做？")
        self.assertEqual(route["topic"], "AI 视频站 vs AI 图片站")
        self.assertEqual(route["action_context"], "choice_decision")

    def test_seo_growth_topic_keeps_product_before_intent_clause(self) -> None:
        route = semantic_router.route_query("我想做睡眠计算器网站，主要判断有没有 SEO 流量机会")
        self.assertEqual(route["topic"], "睡眠计算器网站")
        self.assertEqual(route["action_context"], "seo_growth")

    def test_owned_online_product_topic_keeps_online_prefix(self) -> None:
        route = semantic_router.route_query("我有一个在线简历生成器，想优化付费转化，查竞品怎么做")
        self.assertEqual(route["topic"], "在线简历生成器")
        self.assertEqual(route["action_context"], "existing_product_conversion")

    def test_latest_product_opportunity_intent_is_clear(self) -> None:
        route = semantic_router.route_query("查一下最近 AI 新模型动态，我想找可产品化的新机会")
        self.assertEqual(route["query_type"], "latest_news")
        self.assertEqual(route["action_context"], "new_product_validation")
        self.assertEqual(route["search_strategy"], "normal_evidence")
        self.assertFalse(route["needs_confirmation"])

    def test_candidate_discovery_strategy_for_open_product_pool(self) -> None:
        route = semantic_router.route_query("现在有哪些 AI 产品可以做")
        self.assertEqual(route["query_type"], "opportunity_research")
        self.assertEqual(route["topic"], "AI 产品")
        self.assertEqual(route["action_context"], "new_product_validation")
        self.assertEqual(route["report_mode"], "candidate_mode")
        self.assertEqual(route["search_strategy"], "candidate_discovery")
        self.assertFalse(route["needs_confirmation"])

    def test_concrete_target_stays_normal_evidence_strategy(self) -> None:
        route = semantic_router.route_query("AI SEO brief generator 值不值得做")
        self.assertEqual(route["search_strategy"], "normal_evidence")
        self.assertEqual(route["action_context"], "seo_growth")

    def test_candidate_discovery_preserves_vertical_modifier(self) -> None:
        route = semantic_router.route_query("有哪些 AI SEO 工具站值得做")
        self.assertEqual(route["search_strategy"], "candidate_discovery")
        self.assertEqual(route["report_mode"], "candidate_mode")
        self.assertEqual(route["topic"], "AI SEO 工具站")

    def test_local_business_topic_removes_now_and_action_prefix(self) -> None:
        route = semantic_router.route_query("查一下现在在上海开宠物烘焙店值不值得做")
        self.assertEqual(route["topic"], "上海宠物烘焙店")
        self.assertEqual(route["action_context"], "new_product_validation")

    def test_report_mode_is_inferred_from_question_archetype(self) -> None:
        cases = [
            ("以 AI 会议纪要工具 为方向，哪些公开证据说明这个方向应该直接放弃？", "kill_mode", "放弃判断"),
            ("以 AI 会议纪要工具 为方向，用户现在用什么笨办法解决这个问题？", "pain_mode", "用户痛点"),
            ("以 AI 会议纪要工具 为方向，竞品真正卖的是什么：功能、信任、渠道，还是交付确定性？", "competitor_mode", "竞品判断"),
            ("以 AI 会议纪要工具 为方向，最小可用产品应该验证哪个最危险假设？", "mvp_mode", "MVP 切口"),
            ("以 AI 会议纪要工具 为方向，用户愿意为结果付费，还是只愿意为工具订阅付费？", "monetization_mode", "商业模式/定价"),
            ("以 AI 会议纪要工具 为方向，不依赖 SEO，这个产品最可能从哪个渠道拿到前 100 个用户？", "distribution_mode", "分发判断"),
            ("以 AI 会议纪要工具 为方向，这个方向是太早、刚好，还是已经太晚？", "timing_mode", "趋势与时机"),
            ("以 AI 会议纪要工具 为方向，哪些流程必须 SOP 化，否则我会被重复事务吞没？", "operations_mode", "运营与交付"),
            ("以 AI 会议纪要工具 为方向，这轮尝试失败，是需求错、渠道错、定位错，还是执行不够？", "review_mode", "复盘与转向"),
        ]
        for query, mode, label in cases:
            with self.subTest(query=query):
                route = semantic_router.route_query(query)
                self.assertEqual(route["report_mode"], mode)
                self.assertEqual(route["report_mode_label"], label)

    def test_broad_opportunity_question_keeps_opportunity_report_mode(self) -> None:
        route = semantic_router.route_query("以 AI 会议纪要工具 为方向，当前市场中，哪些高频、刚需、付费意愿强、现有方案糟糕的问题最适合一个人用 AI 切入？")
        self.assertEqual(route["report_mode"], "opportunity_mode")
        self.assertEqual(route["report_mode_label"], "机会判断")

    def test_service_delivery_choice_is_not_operations_mode(self) -> None:
        route = semantic_router.route_query("以 AI 会议纪要工具 为方向，这个机会更像独立产品、功能插件、内容站，还是服务型交付？")
        self.assertEqual(route["action_context"], "new_product_validation")
        self.assertEqual(route["report_mode"], "opportunity_mode")

    def test_public_community_complaints_are_pain_not_distribution(self) -> None:
        route = semantic_router.route_query("以 AI 会议纪要工具 为方向，用户在公开社区里反复抱怨的具体问题是什么？")
        self.assertEqual(route["report_mode"], "pain_mode")
        self.assertEqual(route["report_mode_label"], "用户痛点")

    def test_community_user_acquisition_stays_distribution(self) -> None:
        route = semantic_router.route_query("以 AI 会议纪要工具 为方向，哪些社区已经聚集了强需求用户？")
        self.assertEqual(route["report_mode"], "distribution_mode")
        self.assertEqual(route["report_mode_label"], "分发判断")

    def test_sop_question_stays_operations_mode(self) -> None:
        route = semantic_router.route_query("以 AI 会议纪要工具 为方向，哪些流程必须 SOP 化，否则我会被重复事务吞没？")
        self.assertEqual(route["report_mode"], "operations_mode")
        self.assertEqual(route["report_mode_label"], "运营与交付")


if __name__ == "__main__":
    unittest.main()
