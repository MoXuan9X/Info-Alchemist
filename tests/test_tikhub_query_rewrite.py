#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import tikhub_search  # noqa: E402


class TikHubQueryRewriteTest(unittest.TestCase):
    def test_xhs_uses_chinese_social_query(self) -> None:
        item = {
            "query": "AI 视频站 official API pricing documentation",
            "search_intent": "official_capability",
        }
        self.assertEqual(
            tikhub_search.rewrite_query_for_platform(item, "xhs"),
            "AI视频生成工具 商用 费用",
        )

    def test_reddit_uses_english_social_query(self) -> None:
        item = {
            "query": "AI 视频站 user reviews complaints reddit product hunt",
            "search_intent": "user_discussion",
        }
        self.assertEqual(
            tikhub_search.rewrite_query_for_platform(item, "reddit"),
            "AI video generator tools complaints alternatives",
        )

    def test_platform_item_preserves_source_query(self) -> None:
        item = {
            "query": "AI 视频站 competitors alternatives pricing",
            "search_intent": "competitor_and_monetization",
        }
        output = tikhub_search.platform_item(item, "xhs")
        self.assertEqual(output["source_query"], item["query"])
        self.assertEqual(output["query"], "AI视频生成工具 对比 定价 商用")
        self.assertEqual(output["_query_debug"]["brand_source"], "none")

    def test_query_rewrite_uses_explicit_brand_names_before_defaults(self) -> None:
        item = {
            "query": "Veo Luma Runway AI video competitors alternatives pricing",
            "search_intent": "competitor_and_monetization",
        }
        output = tikhub_search.platform_item(item, "xhs", "AI 视频生成工具")
        self.assertEqual(output["query"], "Veo Luma Runway 对比 费用")
        self.assertEqual(output["_query_debug"]["brand_source"], "explicit")
        self.assertEqual(output["_query_debug"]["brand_keys"], ["veo", "luma", "runway"])

    def test_explicit_brand_pain_query_keeps_brands_and_pain_terms(self) -> None:
        item = {
            "query": "Cursor Windsurf Claude Code user complaints alternatives",
            "search_intent": "user_discussion",
        }
        context = {
            "user_query": "Cursor Windsurf Claude Code 用户吐槽和替代方案",
            "topic": "Cursor Windsurf Claude Code",
        }
        xhs = tikhub_search.platform_item(item, "xhs", "Cursor Windsurf Claude Code", context=context)
        x = tikhub_search.platform_item(item, "x", "Cursor Windsurf Claude Code", context=context)
        self.assertEqual(xhs["query"], "Cursor Windsurf Claude Code 吐槽 踩坑 替代")
        self.assertEqual(x["query"], "Cursor Windsurf Claude Code pain points complaints")
        self.assertEqual(xhs["_query_debug"]["brand_source"], "explicit")
        self.assertEqual(xhs["_query_debug"]["social_query_intent"], "user_pain")

    def test_xhs_normalization_drops_media_and_token_nodes(self) -> None:
        response = {
            "data": {
                "items": [
                    {
                        "note_card": {
                            "note_id": "abc123",
                            "display_title": "AI视频生成工具横测",
                            "desc": "可灵、Runway 和 Pika 的费用、效果和商用限制对比。",
                            "user": {"nickname": "赛博小梦"},
                            "liked_count": 120,
                        }
                    },
                    {
                        "url": "https://sns-na-i11.xhscdn.com/oss/foo.jpg?imageView2/2/w/576",
                        "title": "https://sns-na-i11.xhscdn.com/oss/foo.jpg?imageView2/2/w/576",
                    },
                    {
                        "title": "RAR2lGTj47g1m09UzkOLKZpRdt+eoHTEL1K8H3CYhgfGpr14EPtzhZ/aghX+GN2fxgowf2fsdOzAd9Lq",
                    },
                    {
                        "display_title": "1 day(s) ago",
                        "desc": "1 day(s) ago",
                    },
                    {
                        "display_title": "3",
                        "desc": "3",
                    },
                ]
            }
        }
        results = tikhub_search.normalize_results(response, "xhs")
        self.assertEqual(len(results), 1)
        self.assertIn("AI视频生成工具横测", results[0]["title"])
        self.assertIn("费用", results[0]["content"])
        self.assertIn("xiaohongshu.com/explore/abc123", results[0]["url"])

    def test_reddit_uses_relevance_all_even_for_recent_plan(self) -> None:
        params = tikhub_search.request_params(
            "reddit",
            {
                "query": "Runway Kling Pika AI video complaints alternatives",
                "search_intent": "user_discussion",
                "time_range": "week",
            },
        )
        self.assertEqual(params["sort"], "RELEVANCE")
        self.assertEqual(params["time_range"], "all")

    def test_x_uses_top_for_expert_even_when_plan_is_recent(self) -> None:
        params = tikhub_search.request_params(
            "x",
            {
                "query": "Runway Kling Pika AI video founders practitioners",
                "search_intent": "expert_signal",
                "time_range": "week",
            },
        )
        self.assertEqual(params["search_type"], "Top")

    def test_x_uses_latest_for_news_like_item(self) -> None:
        params = tikhub_search.request_params(
            "x",
            {
                "query": "Runway latest product launch today",
                "search_intent": "latest_news",
                "time_range": "week",
            },
        )
        self.assertEqual(params["search_type"], "Latest")

    def test_reddit_normalization_merges_post_url_title_and_body(self) -> None:
        response = {
            "data": {
                "search": {
                    "dynamic": {
                        "components": {
                            "main": {
                                "edges": [
                                    {
                                        "node": {
                                            "children": [
                                                {
                                                    "post": {
                                                        "postTitle": "Runway Gen-3 vs Kling AI: Which has better motion consistency?",
                                                        "url": "https://www.reddit.com/r/texttovideo/comments/abc/runway_gen3_vs_kling_ai/",
                                                        "content": {
                                                            "markdown": "Testing both on the same prompt; Kling had stronger motion while Runway was more consistent.",
                                                        },
                                                        "score": 6,
                                                        "commentCount": 5,
                                                    }
                                                }
                                            ]
                                        }
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }
        results = tikhub_search.normalize_results(response, "reddit")
        self.assertEqual(len(results), 1)
        self.assertIn("Runway Gen-3 vs Kling AI", results[0]["title"])
        self.assertIn("reddit.com/r/texttovideo", results[0]["url"])
        self.assertIn("stronger motion", results[0]["content"])
        self.assertGreater(results[0]["metric_total"], 0)

    def test_platform_tasks_use_one_short_query_per_platform(self) -> None:
        plan = [
            {
                "query": "best AI video generator comparison alternatives competitors",
                "search_intent": "competitor_and_monetization",
            },
            {
                "query": "AI video generator user reviews complaints alternatives workflow quality",
                "search_intent": "user_discussion",
            },
            {
                "query": "AI video generator founders product teams practitioners problems current solutions case studies",
                "search_intent": "expert_signal",
            },
        ]
        tasks = tikhub_search.platform_search_tasks(plan, topic="AI 视频站")
        self.assertEqual(len(tasks), 3)
        by_platform = {platform: item for item, platform in tasks}
        self.assertEqual(by_platform["xhs"]["query"], "AI视频生成工具 对比 定价 商用")
        self.assertEqual(by_platform["reddit"]["query"], "AI video generator tools complaints alternatives")
        self.assertEqual(by_platform["x"]["query"], "AI video generator tools founders practitioners")

    def test_open_opportunity_question_uses_social_opportunity_queries(self) -> None:
        plan = [
            {
                "query": "AI tools market size growth trend report",
                "search_intent": "competitor_and_monetization",
                "query_group": "market_signal",
            },
            {
                "query": "AI tools user reviews complaints reddit product hunt",
                "search_intent": "user_discussion",
                "query_group": "user_feedback",
            },
            {
                "query": "AI tools founders product teams practitioners problems current solutions case studies",
                "search_intent": "expert_signal",
                "query_group": "expert_signal",
            },
        ]
        context = {
            "user_query": "现在有哪些值得做的 AI 产品和工具站",
            "topic": "AI 产品可以做",
            "query_type": "curiosity",
            "action_context": "new_product_validation",
        }
        tasks = tikhub_search.platform_search_tasks(plan, topic="AI 产品可以做", context=context)
        by_platform = {platform: item for item, platform in tasks}
        self.assertEqual(by_platform["xhs"]["query"], "AI工具 需求 痛点 付费")
        self.assertEqual(by_platform["x"]["query"], "AI tools indie hackers revenue launch")
        self.assertEqual(by_platform["reddit"]["query"], "AI tools people pay complaints")
        self.assertEqual(by_platform["xhs"]["_query_debug"]["social_query_intent"], "opportunity_discovery")

    def test_no_brand_category_compare_does_not_invent_representative_brands(self) -> None:
        item = {
            "query": "AI video generator market size growth trend report",
            "search_intent": "competitor_and_monetization",
        }
        context = {
            "user_query": "比较火的AI 视频生成工具 竞品 对比 定价 商业模式",
            "topic": "AI 视频生成工具 竞品 对比 定价 商业模式",
            "query_type": "opportunity_research",
        }
        xhs = tikhub_search.platform_item(item, "xhs", "AI 视频生成工具", context=context)
        reddit = tikhub_search.platform_item(item, "reddit", "AI 视频生成工具", context=context)
        self.assertEqual(xhs["query"], "AI视频生成工具 对比 定价 商用")
        self.assertEqual(reddit["query"], "AI video generator tools complaints alternatives pricing")
        self.assertEqual(xhs["_query_debug"]["brand_source"], "none")
        self.assertEqual(xhs["_query_debug"]["brand_keys"], [])
        self.assertEqual(xhs["_query_debug"]["social_query_intent"], "category_compare")

    def test_ai_ppt_subject_is_preserved_for_opportunity_query(self) -> None:
        item = {
            "query": "AI tools market size growth trend report",
            "search_intent": "competitor_and_monetization",
        }
        context = {
            "user_query": "AI PPT 工具有哪些机会可以做",
            "topic": "AI PPT 工具",
        }
        xhs = tikhub_search.platform_item(item, "xhs", "AI PPT 工具", context=context)
        x = tikhub_search.platform_item(item, "x", "AI PPT 工具", context=context)
        self.assertEqual(xhs["query"], "AI PPT工具 需求 痛点 付费")
        self.assertEqual(x["query"], "AI presentation tools indie hackers revenue launch")

    def test_validation_question_uses_pain_and_willingness_queries(self) -> None:
        item = {
            "query": "AI SEO tools competitors alternatives pricing",
            "search_intent": "competitor_and_monetization",
        }
        context = {
            "user_query": "AI SEO 工具站还有机会吗？",
            "topic": "AI SEO 工具站还有机会",
        }
        xhs = tikhub_search.platform_item(item, "xhs", "AI SEO 工具站还有机会", context=context)
        reddit = tikhub_search.platform_item(item, "reddit", "AI SEO 工具站还有机会", context=context)
        self.assertEqual(xhs["query"], "AI工具站 SEO 需求 痛点 付费")
        self.assertEqual(reddit["query"], "AI SEO tools problems worth paying for")
        self.assertEqual(xhs["_query_debug"]["social_query_intent"], "validation")

    def test_worth_entering_question_uses_validation_queries(self) -> None:
        item = {
            "query": "AI image generator market size growth trend report",
            "search_intent": "competitor_and_monetization",
        }
        context = {
            "user_query": "我想做一个 AI 图片站，值得切入吗",
            "topic": "AI 图片站",
        }
        xhs = tikhub_search.platform_item(item, "xhs", "AI 图片站", context=context)
        reddit = tikhub_search.platform_item(item, "reddit", "AI 图片站", context=context)
        self.assertEqual(xhs["query"], "AI图片生成工具 需求 痛点 付费")
        self.assertEqual(reddit["query"], "AI image generator tools problems worth paying for")
        self.assertEqual(xhs["_query_debug"]["social_query_intent"], "validation")

    def test_build_process_question_uses_builder_queries(self) -> None:
        item = {
            "query": "tool website tutorial how to use comparison search intent SEO",
            "search_intent": "search_intent",
        }
        context = {
            "user_query": "怎么做一个 AI 工具站？",
            "topic": "AI 工具站",
        }
        x = tikhub_search.platform_item(item, "x", "AI 工具站", context=context)
        xhs = tikhub_search.platform_item(item, "xhs", "AI 工具站", context=context)
        self.assertEqual(x["query"], "AI tools indie hacker build in public")
        self.assertEqual(xhs["query"], "AI工具站 建站 经验")
        self.assertEqual(x["_query_debug"]["social_query_intent"], "build_process")

    def test_request_trace_includes_query_and_time_strategy(self) -> None:
        item = tikhub_search.platform_item(
            {
                "query": "AI video generator user reviews complaints alternatives workflow quality",
                "search_intent": "user_discussion",
                "time_range": "week",
            },
            "reddit",
            "AI 视频站",
        )
        trace = tikhub_search.request_trace(0, item, "reddit")
        self.assertEqual(trace["actual_query"], "AI video generator tools complaints alternatives")
        self.assertEqual(trace["request_params"]["sort"], "RELEVANCE")
        self.assertEqual(trace["time_strategy"]["mode"], "relevance_all")
        self.assertEqual(trace["query_strategy"]["brand_source"], "none")

    def test_wechat_is_ignored_even_if_configured(self) -> None:
        old = tikhub_search.os.environ.get("TIKHUB_PLATFORMS")
        try:
            tikhub_search.os.environ["TIKHUB_PLATFORMS"] = "xhs,wechat,x,reddit"
            self.assertEqual(tikhub_search.configured_platforms(), ["xhs", "x", "reddit"])
        finally:
            if old is None:
                tikhub_search.os.environ.pop("TIKHUB_PLATFORMS", None)
            else:
                tikhub_search.os.environ["TIKHUB_PLATFORMS"] = old

    def test_non_retryable_http_errors_are_detected(self) -> None:
        self.assertTrue(tikhub_search.is_non_retryable_error("X 搜索 HTTP 402：余额不足"))
        self.assertTrue(tikhub_search.is_non_retryable_error("微信公众号 搜索 HTTP 400：参数错误"))
        self.assertFalse(tikhub_search.is_non_retryable_error("网络请求失败：timed out"))


if __name__ == "__main__":
    unittest.main()
