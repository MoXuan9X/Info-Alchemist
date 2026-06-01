# 运行策略

脚本是确定性助手：

- `classify_intent.py`: 判断是否触发完整流程
- `clarify_intent.py`: 对开放集合查询生成行动目的确认问题
- `build_search_plan.py`: 生成结构化联网搜索计划
- `tavily_search.py`: 默认联网公开搜索实现
- `synthesize_tavily_results.py`: 把搜索结果整理成证据
- `run_log.py`: 写入 `info-alchemist/runs/*.json` 运行留痕
- `record_final_output.py`: 记录最终中文输出
- `validate_voi_brief.py`: 检查缺失字段和不安全的 `act`
- `record_decision.py`: 决策记忆写入单入口，合并生成记录、追加 JSONL、刷新画像
- `propose_memory_update.py` / `append_memory.py` / `update_personal_voi_profile.py`: 分步调试或迁移脚本

脚本负责生成搜索计划、搜索和整理证据。最终判断由宿主模型结合用户问题和本轮证据完成，但证据不完整时必须明确写出缺失证据，并优先选择观察或小范围验证。

## 强制链路

搜索计划必须由 `build_search_plan.py` 生成。每条 query 只要求 `query`、`search_intent`、`reason`。底层搜索脚本只接受带有 `search_plan_source: build_search_plan.py` 的完整 JSON 输入，避免宿主模型手写计划后假装可追溯。

正式流程默认使用 `formal_run.py`。分步调试时才使用：`build_search_plan.py -> tavily_search.py -> synthesize_tavily_results.py -> 宿主模型输出报告 -> record_final_output.py`。不要手写搜索计划、固定评分或额外决策脚本。

每条联网搜索 query 单独重试，默认重试 1 次。默认 6 条 query 同批并行搜索，单条请求默认超时 12 秒。正式入口返回完整搜索结果用于写报告，并同步写入 run log 和缓存；只有分步调试脚本的 stdout 默认会压缩，避免调试时拖慢宿主模型。单条失败时继续执行其他 query；全部失败时输出“本轮联网搜索全部失败，不能生成证据报告”，不生成公开证据报告。

## 运行留痕

默认写入：

```text
info-alchemist/runs/<run_id>.json
```

日志阶段包括 `intent`、`search_plan`、`tavily_result`、`synthesis`、`final_output` 和 `error`。如果需要临时关闭，设置 `DISABLE_RUN_LOG=1`。

## 缓存策略

`tavily_search.py` 默认用 `search_plan[].query`、`search_plan[].search_intent` 和可选搜索参数生成稳定指纹。命中缓存时不重复调用公开搜索 API。默认 TTL 为 86400 秒，可通过 `INFO_ALCHEMIST_CACHE_TTL_SECONDS` 调整；`DISABLE_CACHE=1` 时强制跳过缓存。需要把 `reason` 纳入缓存键时，设置 `INFO_ALCHEMIST_CACHE_KEY_INCLUDE_REASON=1`。

## 幂等策略

Alchemy Record 的 `record_id` 由 `user_query`、`decision_context`、`default_action`、`final_status`、`next_action` 和 `source_run_id` 生成。同一 `record_id` 重复写入时返回 `deduped: true`，不追加第二条。更新画像时以 JSONL 当前内容为准，因此删除记录后重新运行 `update_personal_voi_profile.py` 即可重建画像。
