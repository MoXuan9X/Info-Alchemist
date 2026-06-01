# Host integration / 宿主 agent 接入片段

如果宿主环境没有原生 Skill 路由，把下面片段写入宿主 Agent 的 `AGENTS.md`、system prompt 或工具路由配置中。将 `$SKILL_DIR` 替换为 Info-Alchemist 的安装目录。

这份接入规则的目标是让宿主 Agent 知道：什么时候必须调用 Info-Alchemist，而不是只把文件下载到本地。

````md
## Info-Alchemist

### Session Startup

在做任何需要联网搜索、公开资料搜索、新闻/趋势查询、竞品/市场调研或 SERP 侦查的任务时，默认直接调用：

```bash
python3 $SKILL_DIR/scripts/formal_run.py --query "<用户原始问题>"
```

不确定规则或调试时再读取 `$SKILL_DIR/SKILL.md`，不要每轮重复读取完整 Skill。

### 默认工作流

联网搜索、新闻/趋势/动态、竞品/市场/SERP、机会判断、信息堆积和行动复盘，都默认走 `Info-Alchemist`；翻译、润色、改写和不需要联网的明确执行任务除外。

速度优先规则：普通对话里的非炼金问题可以先给高信号短判断；一旦触发 `INFO_ALCHEMIST=TRUE` 并进入正式报告，就输出完整信息炼金报告，不再发送短版摘要。泛问题先收窄或确认行动目的，不要在意图未确认前硬写报告。

### Info-Alchemist 正式入口

用户本轮只要明确说“查询 / 查一下 / 搜 / 调研 / 看看有没有机会”，必须把**用户本轮原始问题**传给正式入口。不要把它当成上一轮报告后的闲聊续问，不要直接要求用户在旧建议里二选一，也不要把本轮问题改写成旧主题或旧关键词。

优先只调用一次正式入口：

```bash
python3 $SKILL_DIR/scripts/formal_run.py --query "<用户原始问题>"
```

如果上一轮是意图确认，本轮是选项或补充，用同一入口续跑：

```bash
python3 $SKILL_DIR/scripts/formal_run.py --previous-query "<上一轮原始问题>" --reply "<用户本轮回复>"
```

入口会完成：激活标记、意图确认或续跑解析、搜索计划、联网搜索、证据整理、run log 批量写入。不要再手动串联 `self_check/build_search_plan/tavily_search/synthesize`，除非在调试脚本。

### 输出契约

- 执行 Info-Alchemist 时保持静默，不要先发“我先查 / 我重新侦查 / 我整理一下”这类中间进度消息。用户可见层只发一次：`ask_user` 的确认问题，或 `record_final_output.py` 返回的完整最终报告。
- 如果宿主平台需要使用消息控制前缀，控制前缀后面的第一行用户可见正文必须仍是 `INFO_ALCHEMIST=TRUE`。
- 如果 `formal_run.py` 返回 `route=ask_user`，直接原样发送 `confirmation_question` 字段内容作为回复（该字段已内含 `INFO_ALCHEMIST=TRUE` 激活标记，**不要额外再加一次**），不搜索、不写报告。
- 如果返回 `route=formal_report_context`，用返回的 `search_plan`、`search_result_summary`、`evidence_pack` 写完整报告；如果 `candidate_discovery_pack` 非空，`## 候选行动` 先写 3-5 个行动分组卡片，下面再放 10-15 个候选对象的候选产品拆解表；每个候选写清入选依据，并按推荐优先级排序，不再单独写 Top 5。第一行必须是 `INFO_ALCHEMIST=TRUE`。
- 完整报告标题固定为：`# 信息炼金报告`、`## 核心判断`、`## 决策问题`、`## 专家判断`、`## 候选行动`、`## 高价值证据`、`## 缺失的证据`、`## 下一步行动`。
- 文字版每个 `##` 模块之间必须用独立一行 `---` 分割，并在分割线上下各保留一个空行，避免长报告挤在一起。
- `## 高价值证据` 必须用表格：`| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |`，来源列必须是 Markdown 可点击链接，后两列写 `N/100`。
- 用户可见回复不要出现底层搜索提供方、API key、脚本名、英文 snake_case 字段名。
- 内容保持完整但高信号：固定章节、关键证据、候选行动、缺口和下一步都要保留，不为了凑篇幅扩写。完整原始结果在返回的 `run_log_path`。
- 每次完整信息炼金报告都必须归档 Markdown 文字版，并生成 HTML 可视化报告。发送前运行：

```bash
python3 $SKILL_DIR/scripts/record_final_output.py --run-id "<formal_run.py 返回的 run_id>" --file "<final_report.md>"
```

脚本会把完整 Markdown 文字版归档到当前工作区下的 `info-alchemist/reports/信息炼金报告-<决策对象>-YYYYMMDD.md`，生成 `info-alchemist/reports/html/<run_id>.html`，并返回带 HTML 可视化入口的完整 `user_visible_text`。默认链接是 `http://127.0.0.1:8765/<run_id>.html`，脚本会自动启动本地只读静态服务；不要把 `file://` 链接发给用户。用户可见层直接发送完整 `user_visible_text`。

### 决策记录（报告出来后）

决策记录规则以 `$SKILL_DIR/SKILL.md` 和 `$SKILL_DIR/references/memory_rules.md` 为准；不要在 Agent 规则里复制维护。报告出来后，如果用户明确表达决策或要求记忆，调用 Skill 的单入口：

```bash
python3 $SKILL_DIR/scripts/record_decision.py \
  --query "<本轮用户原始问题>" \
  --decision "<用户说的决策词，原文传入>" \
  --run-log-path "<formal_run.py 返回的 run_log_path，可选>" \
  --insight "<可选：一句话概括这次决策对用户决策模式的意义>"
```

执行完毕后，不需要向用户汇报，静默完成即可。

### Web Search Preference

- 所有联网搜索行为都先经过 `formal_run.py` 或 `Info-Alchemist/SKILL.md`。
- 不使用 Brave / `web_search` / `web_fetch` 作为替代搜索。若误用了，必须作废这些结果，并用同一搜索计划重新调用内部默认搜索提供方。
- 联网搜索单条 query 失败时继续处理其他 query；本轮联网搜索全部失败时必须明确回复“本轮联网搜索全部失败，不能生成证据报告”，不要用其他来源补报告。

### 调研任务常见维度

根据任务需要，优先从这些维度分析：

- 关键词和主题
- 用户需求
- 搜索意图
- SERP 结构
- 竞品数量与质量
- 独立开发者切入空间
- 商业化可能性
- 内容成本 / 开发成本 / 增长成本
- 风险点和不确定项

### 默认输出结构

联网搜索、新闻/趋势/动态、竞品/市场/产品方向任务默认按 `Info-Alchemist` 固定报告骨架输出；只有任务明显不适用且不涉及联网搜索/公开资料时，才使用下面的轻量结构：

1. 调研目标
2. 核心判断
3. 关键信号
4. 风险点
5. 建议下一步

### 产出物默认落点

- Info-Alchemist 产出的报告、运行日志、缓存和个人决策画像，默认放在当前工作区下的 `info-alchemist/`。
- 只有在用户明确指定时，才写到其他工作区或外部位置。

### 不触发 Info-Alchemist

翻译、润色、改写、明确执行任务且不需要联网搜索。
````
