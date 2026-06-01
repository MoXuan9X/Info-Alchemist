# Tavily 搜索

默认公开搜索实现是 Tavily。宿主在生成搜索计划后直接调用 `scripts/tavily_search.py`。TikHub 是可选垂直社媒补充源，由 `scripts/tavily_search.py` 在开启后自动调用 `scripts/tikhub_search.py` 并合并结果。

Skill 负责：

- 决定该查什么
- 解释为什么查
- 判断搜索结果是否改变行动
- 区分公开证据、私人数据缺口和实验缺口

不要让 Tavily 替代决策澄清。

正确流程：

```text
user query
-> clarify decision
-> infer search_strategy
-> define default action
-> define action-changing evidence
-> generate search_plan with scripts/build_search_plan.py
-> call tavily_search.py
-> optionally append TikHub vertical social results
-> map evidence to action
```

错误流程：

```text
user query
-> immediate Tavily search
-> generic summary
```

搜索意图枚举：

- `official_capability`
- `competitor_and_monetization`
- `user_discussion`
- `search_intent`
- `seo_page_type`
- `api_feasibility`
- `expert_signal`

`expert_signal` 用于查领域里的高影响力实践者、专家、创始人或从业者是谁，他们反复关注什么问题，以及他们现在使用哪些产品、流程或商业方式解决这些问题。

`search_strategy` 当前只有两类：`normal_evidence` 和 `candidate_discovery`。`candidate_discovery` 只用于开放候选池问题，例如“现在有哪些 AI 产品可以做”“有哪些工具站值得参考”；它会优先生成候选池/产品清单、细分赛道、竞品池、用户反馈、SEO 入口、定价和专家信号 query。已有明确目标、最新动态、明确 SEO/转化/选择/复盘问题继续走 `normal_evidence`，不额外做第二轮候选池搜索。

每条 search plan 都必须包含 `query`、`search_intent` 和 `reason`。

搜索计划必须通过 `scripts/build_search_plan.py` 生成。`scripts/tavily_search.py` 会拒绝没有 `search_plan_source: build_search_plan.py` 的手写输入。

联网搜索失败规则：

- 每条 query 单独重试，默认重试 1 次，可用 `TAVILY_QUERY_RETRIES` 调整。
- 单条 query 失败时，保留该条 `failed_queries` 和 attempts，继续搜索其他 query。
- 部分失败时，用户可见报告必须写明 `本轮联网搜索部分失败`，只使用成功 query 的公开证据。
- 全部失败时，必须立即输出中文失败诊断，并明确写“本轮联网搜索全部失败，不能生成证据报告”。

运行留痕：

- `scripts/build_search_plan.py` 写入 `info-alchemist/runs/*.json` 的 `intent` 和 `search_plan`。
- `scripts/tavily_search.py` 写入 `tavily_result`。
- 开启 TikHub 后，`tavily_result.vertical_search` 会记录平台、状态、失败 query；标准化结果会进入 `search_results`。
- `scripts/synthesize_tavily_results.py` 写入 `synthesis`。
- 最终回复前运行 `scripts/record_final_output.py --run-id <run_id>` 写入 `final_output`。

TikHub 配置：

```bash
INFO_ALCHEMIST_ENABLE_TIKHUB=1
TIKHUB_API_KEY=YOUR_TIKHUB_BEARER_TOKEN
TIKHUB_API_BASE=https://api.tikhub.io
TIKHUB_PLATFORMS=xhs,x,reddit
TIKHUB_MAX_QUERIES=0
TIKHUB_RESULTS_PER_GROUP=3
```

深度搜索默认开启 TikHub 三平台补充搜索。大陆网络按 TikHub 文档可把 `TIKHUB_API_BASE` 改成 `https://api.tikhub.dev`。为控制搜索成本，TikHub 层每轮只为小红书、X、Reddit 各选择 1 条短 query：先按平台偏好从 search plan 中选最适合的 `search_intent`，再按平台改写实际请求 `query`。小红书使用中文社媒语境词，X/Reddit 使用英文社区语境词。公众号链路不再启用，因为当前 TikHub 不再支持。单个 TikHub 渠道报错、超时或无结果只记录在 run log 的内部垂直搜索统计里，不进入用户报告；报告只呈现搜到的社媒信号。

禁止把 Brave、`web_search`、`web_fetch` 或手工打开网页当成替代搜索。如果误用了其他搜索工具，这些结果必须作废，不得进入 `public_evidence`；随后必须用同一 search plan 重新调用内部默认搜索提供方。本轮联网搜索全部失败时，停止并输出失败诊断。
