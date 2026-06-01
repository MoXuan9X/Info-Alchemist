# AI intent router

意图识别优先由宿主 LLM 做语义判断，不靠关键词表硬匹配。脚本 `scripts/classify_intent.py` 只用于两件事：

- 校验 LLM 输出的结构化意图对象。
- 在宿主无法做语义路由时，提供低可信 fallback。

## Required semantic question

先判断用户真正要完成的任务，而不是抓触发词：

1. 用户是在要一个确定事实，还是要筛选一批信息？
2. 搜索结果会不会改变用户接下来 7-14 天的行动？
3. 用户是否已经给出行动目的、筛选标准或默认行动？
4. 如果没有这些信息，是否需要先回问？

## Output contract

宿主 LLM 先生成结构化语义路由。LLM 负责理解用户原话，脚本负责校验、追问和生成搜索计划；不要让 LLM 直接把未经联网搜索验证的事实写成证据。

```json
{
  "semantic_intent": {
    "query_type": "reference_collection",
    "topic": "AI 图片站",
    "research_dimensions": ["seo_content_structure", "business_model"],
    "action_context": "",
    "decision_clarity": "partial",
    "needs_confirmation": true,
    "action_options": [
      {
        "id": "new_product_validation",
        "label": "判断要不要从 0 做 AI 图片站",
        "description": "查市场空白、竞品密度、成本/API、MVP 切口和商业化空间。"
      }
    ],
    "confidence": "high",
    "reason": "用户给出了 SEO 和付费模式这两个研究维度，但还没有说明这些信息要改变哪类行动。"
  }
}
```

然后可用以下命令调试：

```bash
printf '%s' '{"user_query":"帮我查哪些 AI 图片站值得参考，重点看 SEO 和付费模式","semantic_intent":{"query_type":"reference_collection","topic":"AI 图片站","research_dimensions":["seo_content_structure","business_model"],"action_context":"","decision_clarity":"partial","needs_confirmation":true,"reason":"维度明确，但行动目的不明确。"}}' | python3 scripts/semantic_router.py
```

旧版 `ai_intent` 仍可用于 `classify_intent.py` 的 `intent_type/trigger_level` 校验；新版正式流程优先消费 `semantic_intent` / `semantic_route`。

## query_type

- `reference_collection`: 用户要找一批参考对象、竞品、对标对象或做得好的案例。
- `latest_news`: 最新新闻、趋势、动态、变化。
- `opportunity_research`: 判断方向、产品、SEO、工具站、竞品机会。
- `decision_research`: 明确要在多个行动间决策。
- `information_pile`: 用户给了很多信息，并要求判断哪些重要或该做。
- `action_review`: 复盘已有行动，要判断继续、停止或转向。
- `direct_lookup`: 时间、天气、汇率等确定性查询。
- `factual_lookup`: 背景事实查询；通常不触发完整流程。
- `curiosity`: 想了解，但尚未出现行动决策。
- `non_applicable`: 翻译、润色、改写，或明显不适合 VOI。

## decision_clarity

决策是否明确不看“有没有研究维度”，而看能不能确定搜索结果会改变哪类行动。

- `unclear`: 只有主题，没有行动目的。例如“帮我查哪些 AI 图片站值得参考”。
- `partial`: 有研究维度，但没有行动目的。例如“重点看 SEO 和付费模式”。
- `clear`: 有行动目的。例如“我想判断要不要从 0 做一个 AI 图片工具站，重点看 SEO 和付费模式”。

只有 `clear` 才能直接生成搜索计划。`unclear` 和 `partial` 都要追问；如果用户回复后仍然不清楚，最多追问 3 轮。

## action_context

行动目的不是固定 1/2/3/4 菜单，而是根据 `query_type + topic + 已知上下文` 动态生成。当前参考对象调研常见 action_context：

- `new_product_validation`: 从 0 判断要不要做新产品/工具站。
- `existing_product_conversion`: 优化已有产品的注册、试用或付费转化。
- `seo_growth`: 找 SEO 新流量入口和页面机会。
- `market_watch`: 只做竞品/行业观察。
- `domain_scan`: 用户先选定一个大领域，再看该领域内有哪些代表 AI 工具、类型和候选对象。
- `reference_teardown`: 拆解参考产品的流程、逻辑、创始人/产品团队信号和可借鉴做法。
- `news_brief`: 只要资讯速览。

## intent_type

- `non_applicable`: 翻译、润色、改写，或明显不适合 VOI。
- `direct_lookup`: 时间、天气、汇率等确定性查询。
- `factual_lookup`: 背景事实查询；通常不触发完整流程。
- `curiosity`: 想了解，但尚未出现行动决策；不能用于新闻、趋势、动态、竞品、市场或产品方向查询。
- `open_set_research`: 新闻、趋势、动态、榜单、很多候选对象这类开放集合；“最近某类产品有什么新动态”“竞品/市场最近有什么变化”也属于这一类，不能判成轻量好奇。
- `information_pile`: 用户给了很多信息，并要求判断哪些重要或该做。
- `opportunity_research`: 判断方向、产品、SEO、工具站、竞品机会。
- `decision_research`: 明确要在多个行动间决策。
- `action_review`: 复盘已有行动，要判断继续、停止或转向。

## Optional confirmed_intent_type

当用户已经说明开放集合查询的行动目的时，LLM 应额外输出 `confirmed_intent_type`，让 search plan 按语义枚举分支，而不是在自然语言里找关键词：

- `reference_product_experience`
- `reference_business_model`
- `reference_seo_content_structure`
- `reference_model_function_capability`
- `reference_multi_dimension`
- `other`

示例：

```json
{
  "ai_intent": {
    "intent_type": "open_set_research",
    "trigger_level": "full",
    "needs_confirmation": false,
    "confirmed_intent": "重点参考产品体验和 SEO/内容结构。",
    "confirmed_intent_type": "reference_multi_dimension",
    "confidence": "high",
    "reason": "用户已说明参考维度，可以进入联网搜索和固定报告骨架。"
  }
}
```

## Optional ai_search_plan

当脚本模板不可能穷尽领域词时，宿主 LLM 应额外给 `ai_search_plan` 草案。AI 负责理解“真正要搜什么”，脚本负责验收、去泛词、补齐证据轴和回填模板 query；未经 `build_search_plan.py` 校验的草案不得直接搜索。

每条 query 尽量具体，避免“最近 热门 AI 产品”这类泛词。字段：

```json
{
  "ai_search_plan": [
    {
      "query": "AI decision support tools founders interviews product strategy workflow",
      "search_intent": "expert_signal",
      "evidence_axis": "expert",
      "reason": "查同类辅助决策 AI 产品创始人、产品团队和他们的具体做法。"
    },
    {
      "query": "AI decision support tools product demo workflow recommendations action plan",
      "search_intent": "official_capability",
      "evidence_axis": "official",
      "reason": "拆真实产品如何把输入、建议、checklist 和下一步动作串起来。"
    }
  ]
}
```

如果 `build_search_plan.py` 没有某个领域词，正确策略不是继续扩关键词表，而是让宿主 LLM 输出更准确的 `semantic_route.topic` 和 `ai_search_plan`；脚本只保留兜底模板和质量闸门。

## trigger_level

- `none`: 不触发。
- `direct`: 可直接回答或查一个确定事实。
- `light`: 轻量回答；除非用户补充决策，不进入完整 VOI。
- `clarify`: 先问意图或默认行动，不能搜索。
- `full`: 进入完整 Info-Alchemist。
- `review`: 进入行动复盘流程。

## Guardrails

- 不要因为出现“AI 视频站”就自动等同于某一个固定维度，例如 SEO、产品体验或商业模式。
- 不要把“市面上有哪些 AI 工具 / 想看看现在有哪些 AI 工具”默认等同于 `new_product_validation`。先问用户选 `1` 能力筛选、`2 + 领域`、`3 + 拆解维度` 或 `4` 市场速览；用户选定后再进入对应候选池。
- memory 只能作为“我猜你的行动目的是 X，对吗？”的确认问题，不能直接作为已确认意图。
- 关键词可以作为证据之一，但不能替代语义判断。
- 如果用户一句话里已经说明行动目的，例如“我想判断要不要从 0 做一个 AI 视频工具站，查哪些站值得参考，重点看新用户流程和 SEO 结构”，可以直接进入 `full`。
- 研究维度明确不等于决策明确。“重点看新用户流程和 SEO 结构”如果没有说明是为了新产品、已有转化、SEO 增长还是行业观察，仍然应追问行动目的。
- 如果用户问“哪些 AI 视频站值得参考”但没说明行动目的，先 `clarify`；如果用户确认是从 0 做新产品、优化已有转化、找 SEO 新流量或行业观察，再 `full` 并使用固定报告骨架。
- 如果上一轮是行动目的确认，用户回复选项、短确认或详细补充，例如 `1`、`3`、`1+3`、`想知道 1 和 3`、`我是想从 0 判断要不要做一个新工具站`，这不是新闲聊；应继续解析为同一条调研任务。
