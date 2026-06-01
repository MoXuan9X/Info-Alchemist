# Changelog

## 0.3.5

- Enabled TikHub four-channel vertical search for deep research runs in local/default configuration: Xiaohongshu, WeChat MP, X, and Reddit across all search-plan queries.
- Changed TikHub failure handling so channel errors, timeouts, empty results, and misses stay in `vertical_search` run-log stats only; they no longer affect top-level search status, synthesis gaps, or user-visible reports.
- Required visible Markdown dividers between every `##` module in text reports, so long Feishu reports no longer collapse into dense blocks.
- Updated the final-output validator to reject reports that miss the `---` divider before any subsequent fixed section heading.
- Added report-contract test coverage for the section-divider requirement.
- Removed the personal decision profile entry from the HTML visual report navigation.
- Moved report artifacts to the current OpenClaw workspace's visible `info-alchemist/` directory: Markdown reports live under `reports/`, HTML visualizations under `reports/html/`, and run logs under `runs/`.
- Changed Markdown and HTML report filenames to use the report document title plus date, e.g. `信息炼金报告-<决策对象>-YYYYMMDD.md`.

## 0.3.4

- Added optional TikHub vertical social search via `scripts/tikhub_search.py`, covering Xiaohongshu App V2 search notes, WeChat MP articles, X, and Reddit.
- Added Xiaohongshu search fallback order: App V2 -> App -> Web V3 when the higher-priority endpoint fails or returns no extractable results.
- Changed TikHub query selection so every generated search-plan query is searched across the configured vertical channels by default.
- Fixed search-plan topic pollution from host activation text such as `用 INFO_ALCHEMIST`; generated search queries now strip activation markers before Tavily/TikHub calls.
- Fixed the semantic-router path to strip activation markers before topic extraction, so confirmation questions and formal runs use the same clean topic as the search plan.
- Added platform-specific TikHub query rewriting so Xiaohongshu/WeChat use Chinese social-search phrasing while X/Reddit use English community-search phrasing.
- Fixed vertical-search merge accounting so failed-only TikHub results no longer masquerade as usable partial success, while successful vertical results still rescue a failed primary public-search run.
- Fixed social-result synthesis to quote the actual post/article title and content, aggregating up to three returned social items instead of generic adapter text such as “返回 N 条可标准化结果”.
- Kept Tavily as the primary public-search provider; TikHub results are normalized into the existing `search_results` contract and recorded under `vertical_search`.
- Allowed the internal evidence schema to record `tavily+tikhub` while continuing to reject provider names in user-visible final reports.
- Removed a report-writing instruction that could fabricate “most likely official URLs”; reports must now use only URLs returned by evidence results and mark missing links as unverified.
- Added environment controls for TikHub enablement, base domain, platform list, query cap, result cap, retries, timeout, and concurrency.

## 0.3.3

- 修复 `formal_run.py` 中 `confirmation_payload()` 对 `clarify_intent.clarify()` 的重复调用：改为由 `run_formal()` 统一调用一次后把 `question` 传入函数，符合单责任原则。
- 修复 `AGENTS.md` 中 `route=ask_user` 输出规则：去掉让宿主额外再加 `INFO_ALCHEMIST=TRUE` 的错误指令，改为直接原样发送 `confirmation_question`（该字段已内含激活标记）。
- 同步修复 `references/host_integration.md` 第 4 条规则，与 `AGENTS.md` 保持一致。
- 将可复用的记忆写入策略收敛到 `references/memory_rules.md`，`AGENTS.md` 只保留最小调用说明。
- 将 `scripts/record_decision.py` 作为默认记忆写入单入口，合并生成记录、追加 JSONL、刷新画像。
- 修复 `record_decision.py` 对当前 run log 结构的读取，支持可选 `--run-log-path`，并提取证据、决策上下文和下一步动作。
- 修复 `scripts/update_personal_voi_profile.py` 生成中文画像时的引号语法错误。
- 重做 `scripts/update_personal_voi_profile.py` 输出结构：近期决策记录、惯性决策模式、有效证据类型、最近决策洞察、下次询证提醒。

## 0.3.2

- Added `scripts/formal_run.py` as the default one-call formal entrypoint for host integrations.
- Kept the full report contract unchanged while moving activation, confirmation, search planning, web search, synthesis, and run-log writes into one flow.
- Added batch run-log writing via `record_stages()` to avoid repeated file reads and writes during normal runs.
- Refactored `build_search_plan.py` and `tavily_search.py` so the formal entrypoint can call their core logic directly without spawning extra processes.
- Improved search-cache hit rate by excluding plan `reason` text from the cache key by default; exact query and intent still define the cached search result.
- Updated host routing docs to call `formal_run.py` by default and reserve split scripts for debugging.

## 0.2.15

- Added a dedicated intent-confirmation template for “帮我查询哪些 AI 视频站值得参考”.
- Added reference-site continuation parsing for product experience, business model, SEO/content structure, and model/function capability.
- Clarified that option replies, short confirmations, and detailed follow-up descriptions all continue the same Info-Alchemist task when they answer the prior confirmation question.
- Required `resolve_confirmation.py --query "<上一轮原始查询>" "<用户回复>"` so option numbers are interpreted against the correct confirmation template.

## 0.2.14

- Hid the default search provider name from user-visible reports, intent confirmations, continuation text, and failure diagnostics.
- User-facing language now uses `联网搜索`, `公开搜索`, `搜索计划`, `公开证据`, `搜索提供方`, and `本轮联网搜索`.
- `record_final_output.py` now rejects final reports that expose provider names such as `Tavily`, `tavily`, or `TAVILY`.

## 0.2.13

- Changed intent-confirmation output from letter labels to Chinese numbered headings: `## 1. 产品机会` through `## 4. 资讯速览`.
- Updated confirmation parsing and docs for replies like `1+3`, `想知道 1 和 3`, and `产品机会 + SEO`.

## 0.2.12

- Added a formatted intent-confirmation output contract with stronger labels, so clarification replies are not flat blocks of text.
- Added `scripts/resolve_confirmation.py` to parse short follow-up replies as Info-Alchemist continuations.
- Added `product_and_seo_opportunity` search planning for combined product opportunity plus SEO/content opportunity workflows.
- Updated host routing guidance so confirmation follow-ups must rerun Info-Alchemist instead of replying with a plain “收到”.

## 0.2.11

- Tightened the final-output activation-line requirement: `INFO_ALCHEMIST=TRUE` must be the first line.
- Kept the fixed report contract while avoiding extra prose before the activation line.

## 0.2.9

- 强制 `tavily_search.py` 只接受 `build_search_plan.py` 生成的完整搜索计划，拒绝手写 search plan。
- 新增运行留痕，记录 `intent -> search_plan -> tavily_result -> synthesis -> final_output`。
- Tavily 改成逐条 query 重试和失败记录：单条失败不拖垮整轮，全部失败时输出中文失败诊断。
- 新增 `scripts/run_log.py` 和 `scripts/record_final_output.py`。

## 0.2.8

- 强化 Tavily-only 搜索约束，移除“用户明确要求可替换搜索提供方”的歧义。
- JSON brief 继续要求 `search_provider: tavily`，非 Tavily 搜索结果不得进入公开证据。

## 0.2.7

- 用户可见激活证明改成单行 `INFO_ALCHEMIST=TRUE`。
- 用户可见报告强制使用中文标题：痛感证据、证据缺口、最终状态、下一步最小行动、停止搜索规则。
- 增加更清晰的 Markdown 报告结构，标题更大，正文更少堆叠。

## 0.2.6

- Added `references/ai_intent_router.md` and made LLM semantic routing the primary intent-recognition path.
- Changed `scripts/classify_intent.py` to validate structured `ai_intent` input and mark regex output as fallback only.
- Added `confirmed_intent_type` for latest-news search-plan branching so confirmed intent is semantic, not keyword-derived.
- Updated host integration and workspace routing to avoid keyword-list based triggering.

## 0.2.5

- Tightened host routing for open-ended latest-news queries so they enter the Info-Alchemist clarification gate before search.
- Added an explicit guard against narrowing "AI news" to a prior thread or memory topic without user confirmation.

## 0.2.4

- Moved portable routing guidance into `SKILL.md` frontmatter and `references/host_integration.md`.
- Removed hard-coded seller workspace paths from activation instructions.
- Updated OpenAI agent metadata for marketplace-style triggering.

## 0.2.2

- Added Intent Confirmation Gate for open-set queries such as "latest AI news".
- Changed latest-news classification from `information_pile/full` to `open_set_research/clarify`.
- Added `scripts/clarify_intent.py` and a two-turn AI news clarification example.

## 0.2.1

- Replaced the `tavily-python` SDK dependency with a Python standard-library HTTP client for Tavily Search.
- Kept `.env` loading from the skill directory so users only need to provide `TAVILY_API_KEY`.
- Added a latest-news search-plan branch and Tavily `topic`/`time_range`/`days` request options.

## 0.2.0

- Added explicit target users, repeat-use scenarios, dependency table, workflow, inputs, preconditions, example, output validation, cache and idempotency guidance.
- Added competitor positioning against Perplexity, Tavily Search, Notion/Obsidian, `iterate-pivot-decision`, and `evidence-synthesis`.
- Added deterministic public-search caching and JSONL memory deduplication.
- Replaced local absolute path examples with `$SKILL_DIR` or relative paths.

## 0.1.0

- Initial VOI search brief workflow with Tavily search planning, evidence synthesis, schema validation, and lightweight local memory.
