#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import build_search_plan  # noqa: E402
import semantic_router  # noqa: E402


QUESTION_BANK = {
    "机会判断": [
        "这个方向如果今天从 0 开始做，最小可验证切口是什么？",
        "这个机会是真需求、工具热度，还是平台发布带来的短期噪音？",
        "如果我只有 7 天时间验证这个方向，最该验证哪一个假设？",
        "这个方向里，用户已经在用什么笨办法解决问题？",
        "这个方向是否存在“用户痛但巨头不愿意细做”的缝隙？",
        "这个机会更像独立产品、功能插件、内容站，还是服务型交付？",
        "当前市场里，哪类用户最可能先付费，而不是只试用？",
        "如果不做完整产品，是否能用模板、脚本、自动化流程先验证？",
        "这个方向的窗口期来自技术变化、成本下降、政策变化，还是用户行为变化？",
        "如果我现在不做，3 个月后最可能后悔错过什么？",
    ],
    "放弃判断": [
        "哪些公开证据说明这个方向应该直接放弃？",
        "这个方向是否已经进入“功能同质化，只能拼分发”的阶段？",
        "有没有明显迹象表明用户需求被头部产品顺手吃掉？",
        "这个方向的核心价值是否只是“把 API 包一层壳”？",
        "如果平台官方下场，我的产品还有什么不可替代性？",
        "这个方向是否需要过高算力、版权、合规或客服成本？",
        "哪些证据会让我从“想做”变成“暂时归档”？",
        "这个机会是否只对开发者兴奋，对真实用户无感？",
        "如果前 100 个用户来了，我能否承受交付和维护成本？",
        "这个方向有没有“看起来能做，但不值得我做”的信号？",
    ],
    "用户痛点": [
        "用户在公开社区里反复抱怨的具体问题是什么？",
        "哪些抱怨代表愿意付费，哪些只是情绪发泄？",
        "用户现在为了这个问题花了多少钱、时间或人力？",
        "用户会用什么词描述这个问题，而不是创业者会用什么词？",
        "这个痛点是高频低价、低频高价，还是低频低价？",
        "用户是在寻找更便宜、更快、更稳，还是更省心？",
        "用户是否已经形成固定工作流，我能插入哪一步？",
        "哪类用户最可能先忍不住试一个新工具？",
        "用户的替代方案是竞品、人工、Excel、Notion、脚本，还是外包？",
        "这个问题如果解决得更好，用户会立刻得到什么收益？",
    ],
    "竞品判断": [
        "竞品之间真正差异在哪里，还是只是在换文案？",
        "头部竞品最近新增功能说明它们在争夺什么用户？",
        "小竞品靠什么活下来：低价、垂直场景、模板、渠道，还是服务？",
        "哪些竞品看起来流量大，但商业模式很弱？",
        "哪些竞品产品弱但分发强，说明机会在渠道而不是功能？",
        "哪些竞品用户评价暴露了可切入的缺口？",
        "竞品的定价是否留下了低端、团队、企业或本地化空间？",
        "竞品有没有忽视某个语言、地区、职业或平台生态？",
        "哪些竞品已经证明用户愿意为这个问题付费？",
        "如果我只能比竞品强一个点，那个点应该是什么？",
    ],
    "产品切口": [
        "这个方向最适合做单点工具、工作流工具，还是系统型产品？",
        "MVP 应该砍掉哪些“看起来必要但其实不影响验证”的功能？",
        "哪个功能最能证明用户愿意继续用，而不是只试一次？",
        "产品第一版应该服务新手、专业用户，还是团队用户？",
        "这个产品的“第一次成功体验”应该是什么？",
        "用户从看到产品到获得结果，最长能接受几分钟？",
        "哪个功能可以让用户自然分享结果或邀请别人？",
        "哪个功能是付费墙前必须免费给到的？",
        "产品是否需要账号体系，还是可以先无登录验证？",
        "如果只做一个页面和一个按钮，应该验证什么？",
    ],
    "商业模式": [
        "这个产品更适合订阅、按量计费、一次性购买，还是服务打包？",
        "用户付费的理由是省钱、省时间、赚钱、避险，还是提升质量？",
        "哪个价格点能最快暴露真实付费意愿？",
        "免费额度应该验证激活，还是验证转化？",
        "这个方向有没有天然的团队版或企业版扩展空间？",
        "成本结构是否允许我用低价获客？",
        "用户是否会把这个产品当工具预算、营销预算，还是个人消费？",
        "哪种付费触发点最自然：导出、批量、高清、商用、协作、自动化？",
        "如果用户不续费，最可能是价值弱、频率低，还是替代品太多？",
        "这个产品能否先用服务收入养出软件产品？",
    ],
    "分发判断": [
        "不依赖 SEO，这个产品最可能从哪个渠道拿到前 100 个用户？",
        "哪些社区已经聚集了强需求用户？",
        "这个产品适合在 X、Reddit、小红书、公众号、Product Hunt 还是垂直论坛冷启动？",
        "用户是否会主动搜索这个问题，还是需要被场景触发？",
        "这个方向有没有适合做模板、案例、榜单、对比或教程的分发资产？",
        "哪个分发渠道最适合我个人能力和资源？",
        "我能否通过公开拆解竞品用户评论找到第一批冷启动对象？",
        "这个产品是否有可展示的结果，适合做社交传播？",
        "哪个用户群体最容易被一条 demo 视频打动？",
        "如果没有广告预算，最现实的获客路径是什么？",
    ],
    "趋势与时机": [
        "这个趋势背后的长期驱动力是什么？",
        "这波热度会让用户行为永久改变，还是只是试新鲜？",
        "成本下降是否已经足够支撑小团队做产品？",
        "平台 API、模型能力或基础设施是否成熟到可商用？",
        "这个方向是太早、刚好，还是已经太晚？",
        "哪些玩家进入说明市场被验证，哪些玩家进入说明竞争过热？",
        "这个机会是否依赖单一平台政策？",
        "哪个变化会让这个方向突然变得更值得做？",
        "哪个变化会让这个方向瞬间失效？",
        "现在最该做的是进入、等待、观察，还是只收集证据？",
    ],
    "执行优先级": [
        "我现在手上的几个想法，哪个最适合先做 7 天验证？",
        "哪个想法的失败成本最低、学习价值最高？",
        "哪个想法最符合我的能力、渠道和资产？",
        "哪个想法即使失败，也能沉淀内容、代码、用户或认知资产？",
        "哪个方向最容易让我陷入无效开发？",
        "哪个方向最需要先验证分发，而不是先验证产品？",
        "哪个方向最需要先验证成本，而不是先验证需求？",
        "哪个方向最需要先验证用户身份，而不是先验证功能？",
        "如果只能做一个实验，哪个实验最能区分继续和停止？",
        "我应该把本周时间投入开发、销售、访谈、内容，还是竞品拆解？",
    ],
    "复盘与转向": [
        "这轮尝试失败，是需求错、渠道错、定位错，还是执行不够？",
        "已有反馈里，哪些值得改变产品，哪些只是个例？",
        "用户用了但没付费，说明价值不足、时机不对，还是定价不对？",
        "用户注册了但不用，最大的断点可能在哪里？",
        "当前产品应该继续打磨、换人群、换渠道，还是归档？",
        "哪些证据说明我是在坚持，哪些说明我是在沉没成本？",
        "如果要转向，应该保留哪个资产继续复用？",
        "这个项目最有价值的学习是什么？",
        "下一轮实验应该缩小范围，还是换一个更强痛点？",
        "如果我是一个人长期经营，这个方向是否值得成为我的主线？",
    ],
}

EXPECTED_AXIS_BY_CATEGORY = {
    "机会判断": "user_pain",
    "放弃判断": "risk",
    "用户痛点": "user_pain",
    "竞品判断": "competition",
    "产品切口": "user_pain",
    "商业模式": "unit_economics",
    "分发判断": "distribution",
    "趋势与时机": "market",
    "执行优先级": "user_pain",
    "复盘与转向": "user_pain",
}


class QuestionBankRoutingTest(unittest.TestCase):
    def test_question_bank_has_100_questions(self) -> None:
        self.assertEqual(sum(len(items) for items in QUESTION_BANK.values()), 100)

    def test_standalone_contextual_questions_require_confirmation(self) -> None:
        for category, questions in QUESTION_BANK.items():
            for question in questions:
                with self.subTest(category=category, question=question):
                    route = semantic_router.route_query(question)
                    self.assertTrue(route["needs_confirmation"])
                    self.assertEqual(route["trigger_level"], "clarify")
                    self.assertIn(route["query_type"], {"opportunity_research", "action_review"})
                    self.assertIn("INFO_ALCHEMIST=TRUE", route["confirmation_question"])

    def test_question_bank_with_topic_enters_research_chain(self) -> None:
        for category, questions in QUESTION_BANK.items():
            for question in questions:
                wrapped = f"以 AI 会议纪要工具 为方向，{question}"
                with self.subTest(category=category, question=question):
                    route = semantic_router.route_query(wrapped)
                    self.assertFalse(route["needs_confirmation"])
                    self.assertEqual(route["topic"], "AI 会议纪要工具")
                    self.assertIn(route["trigger_level"], {"full", "review"})
                    output, _, exit_code, status = build_search_plan.build_plan(
                        {"user_query": wrapped, "semantic_route": route},
                        run_id="test-question-bank",
                    )
                    self.assertEqual(exit_code, 0)
                    self.assertEqual(status, "ok")
                    plan = output["search_plan"]
                    self.assertTrue(plan)
                    axes = {item.get("evidence_axis") for item in plan}
                    self.assertIn(EXPECTED_AXIS_BY_CATEGORY[category], axes)
                    queries = "\n".join(item["query"] for item in plan)
                    self.assertNotIn("这个方向", queries)
                    self.assertNotIn("这个产品", queries)
                    self.assertNotIn("这个机会", queries)
                    self.assertIn("AI meeting notes tool", queries)


if __name__ == "__main__":
    unittest.main()
