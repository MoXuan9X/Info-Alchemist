# 记忆规则

记忆必须本地、轻量、只存派生洞察。

只有以下情况写记忆：

- 用户看完报告后明确表达决策：做 / 行动 / 小步验证 / 观望 / 关注 / 归档 / 放弃 / 不做
- 用户给出明确句式：`我决定 xxx`、`先 xxx`、`这个方向放弃`、`就按这个做`、`参考 xxx 来做`
- 用户明确要求存档：`记下来`、`存到画像`、`写到记忆里`

以下情况不写记忆：

- 报告刚生成但用户还没表达决策
- 用户只是追问、补充信息、要求重新搜索
- 意图确认轮
- 普通事实查询
- 翻译
- 润色
- 低风险好奇
- 敏感或高风险数据
- 用户说不要记
- `DISABLE_MEMORY=1`

## Alchemy Record 记录

默认用单入口写入：

```bash
python3 scripts/record_decision.py \
  --query "<本轮用户原始问题>" \
  --decision "<用户决策原文>" \
  --run-log-path "<formal_run.py 返回的 run_log_path，可选>" \
  --insight "<可选：一句话洞察>"
```

`record_decision.py` 会完成三件事：从 run log 提取证据、追加当前 OpenClaw workspace 下的 `info-alchemist/memory/alchemy_records.jsonl`、刷新 `info-alchemist/memory/personal_voi_profile.md`。`propose_memory_update.py`、`append_memory.py`、`update_personal_voi_profile.py` 只保留为调试或迁移用的分步脚本。

必填字段：

- `date`
- `user_query`
- `trigger_reason_type`
- `decision_context`
- `default_action`
- `final_status`
- `key_evidence`
- `next_action`
- `insight`

字段生成规则：

- `record_decision.py` 应额外生成 `evidence_sources` 和 `decision_turning_point`；旧记录缺少这两个字段时，画像生成器可以从 `key_evidence` 和 `insight` 回退。
- `evidence_sources` 只保存可回溯来源，不保存正文摘要：最多 2 条，每条只包含 `title` 和 `url`。
- `key_evidence` 保留为兼容字段，但内容必须是 `evidence_sources` 的 Markdown 标题链接列表；不要写搜索摘要、文章正文片段或供应商 answer。
- `decision_turning_point` 用一句话解释证据如何改变行动，必须落到“因此做 / 不做 / 先验证 / 继续观察”，不要重复新闻内容。

## 记忆升级规则

- 出现 1 次：只记录事件
- 出现 2 次：标记为 `possible_pattern`
- 出现 3 次：形成 `bias_hypothesis`
- 用户确认后：升级为 `personal_guardrail`
- 后续证据不支持：降级或删除

## 决策画像输出结构

`update_personal_voi_profile.py` 生成固定 Markdown 画像，用户可见标题如下：

- 顶部信息：最近更新、已记录决策、画像成熟度、画像说明
- 近期决策记录表：日期、场景、触发因素、原始动作、决策转折、最终动作、证据来源
- 惯性决策模式表：模式线索、出现次数、首次出现、最近出现、置信度、当前判断
- 有效证据类型表：公开搜索、亲自体验/录屏/截图、点击/留资/转化数据
- 最近决策洞察、下次询证提醒
