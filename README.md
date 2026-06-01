# Info-Alchemist / 信息炼金术士

Info-Alchemist / 信息炼金术士是一个基于 VOI 的公开搜索取证与个人信息决策记忆 Skill。它帮助用户把“我要查 xxx”转成“哪些信息会改变我的下一步行动”。内部公开搜索使用固定搜索提供方；Tavily、网页抓取或手工打开页面不能替代标准联网搜索证据。

普通搜索回答：查到了什么。  
信息炼金术士回答：这些信息会不会改变你的行动，以及你还缺什么证据。

## 免费快速安装

把下面这段话完整复制给你正在使用的 AI Agent。

适用：OpenClaw、Codex、Claude Code、Cursor、Gemini CLI。

```text
请帮我安装 Info-Alchemist：
https://github.com/MoXuan9X/Info-Alchemist

安装完成后，请告诉我：
1. 是否安装成功
2. 我需要在哪个文件里填写 Tavily API key
3. 怎么用一个真实问题确认 Info-Alchemist 已经生效
```

安装时，AI Agent 可能会提醒你填写 Tavily API key。Tavily 用于公开网页搜索，比如官方资料、新闻、竞品页面、定价页和文档。

TikHub 是可选项，用于小红书、X、Reddit 上的用户讨论、抱怨、口碑和社区信号。如果你暂时不需要社交平台搜索，保持 `INFO_ALCHEMIST_ENABLE_TIKHUB=0` 即可，不用填写 TikHub API key。

## Tavily API key 怎么拿

1. 打开 https://app.tavily.com/
2. 注册或登录。
3. 找到 API Keys / Dashboard。
4. 复制以 `tvly-` 开头的 key。
5. 回到你的 AI Agent，让它告诉你 `.env` 文件在哪里。
6. 把 key 填到 `TAVILY_API_KEY=` 后面。
7. 保存文件。

## Tavily 和 TikHub 分别用于什么

| 配置 | 必填吗 | 用来查什么 | 第一次安装怎么填 |
|---|---|---|---|
| `TAVILY_API_KEY` | 必填 | 公开网页搜索：官方资料、新闻、竞品页面、定价页、文档、博客等 | 填入你自己的 `tvly-...` |
| `INFO_ALCHEMIST_ENABLE_TIKHUB` | 可选 | TikHub 开关 | 不查社交平台时填 `0` |
| `TIKHUB_API_KEY` | 可选 | 社交平台搜索：小红书、X、Reddit 上的用户讨论、抱怨、口碑和社区信号 | `INFO_ALCHEMIST_ENABLE_TIKHUB=0` 时不用填 |

如果你只想先完成安装和普通网页搜索，保持：

```bash
INFO_ALCHEMIST_ENABLE_TIKHUB=0
```

只有当你需要小红书、X、Reddit 这类社交平台信号时，再改成：

```bash
INFO_ALCHEMIST_ENABLE_TIKHUB=1
TIKHUB_API_KEY=你的TikHub key
```

## 怎么确认成功

### 第一步：配置文件检查成功

AI Agent 会检查 Info-Alchemist 文件和 `.env` 配置。  
这一步只说明文件和配置准备好了。

### 第二步：真实问题触发成功

选择一个你真的想判断的问题，例如：

- 这个方向值不值得做？
- 最近有哪些竞品值得参考？
- 某个 AI 产品机会能不能做？
- 要不要继续投入这个项目？

如果 AI Agent 的回复第一行出现：

```text
INFO_ALCHEMIST=TRUE
```

才说明 Info-Alchemist 真正触发成功。

## 如果没有成功

| 现象 | 怎么办 |
|---|---|
| AI Agent 说缺少 Tavily API key | 去 https://app.tavily.com/ 获取，然后填进 `.env` |
| AI Agent 找不到 `.env` 文件 | 让它重新检查 Info-Alchemist 安装位置 |
| 问测试问题后没有 `INFO_ALCHEMIST=TRUE` | 让 AI Agent 检查它是否已经读取 Info-Alchemist |
| AI Agent 直接普通搜索 | 重新发送测试问题，并明确说“用 Info-Alchemist 判断” |

---

下面是开发者和 Agent 接入细节。普通用户完成上面的安装、配置和真实查询测试即可。

## 这个 Skill 解决什么问题

独立开发者、SEO 运营、产品经理和 AI 工具创业者每天都会看到大量新模型、新 API、新工具站、新竞品和新趋势。普通调研往往只会增加链接和观点，不会告诉用户下一步该不该做。

信息炼金术士使用 VOI，也就是 Value of Information：只有可能改变默认行动的信息，才值得继续查。

## 复用场景

这个 skill 不是一次性搜索脚本，而是一个可反复使用的信息决策门。典型复用场景：

- 每次看到新模型、新 API、新工具站、新竞品或新关键词时，用它判断是否值得继续查。
- 每次准备做工具站、对比页、榜单页、SEO 页面或小实验前，用它确认公开证据和证据缺口。
- 每次做完一轮行动后，用它复盘要继续、停止、转向还是归档。

## 和普通搜索有什么区别

普通搜索从关键词开始，以链接结束。信息炼金术士从决策开始：

1. 用户真正要决定什么？
2. 如果现在停止搜索，用户最可能做什么？
3. 哪些证据可能改变这个行动？
4. 公开搜索提供方能回答哪些公开证据？
5. 哪些证据必须通过访谈、分析数据、假门按钮、等候名单或手动测试获得？

## 意图识别怎么做

意图识别优先由宿主 LLM 做语义判断，见 `references/ai_intent_router.md`。不要把路由做成不断增长的关键词表；关键词脚本只用于离线兜底、结构校验和回归测试。

## 依赖和联网搜索配置

| 名称 | 类型 | 是否付费 | 说明 |
|---|---|---:|---|
| Tavily API | 公开搜索接口 | 可能付费 | 默认通过 `scripts/tavily_search.py` 调用 |
| TikHub API | 垂直社媒搜索接口 | 可能付费 | 可选补充小红书、X、Reddit 结果 |
| Python 标准库 | 运行时 | 否 | 搜索脚本直接使用标准库 HTTP/子进程能力 |
| 本地文件系统 | 本地记忆/缓存/报告 | 否 | 默认写入当前 OpenClaw workspace 下的 `info-alchemist/` |

当前默认搜索提供方是 Tavily。TikHub 作为可选垂直社媒补充源，不替代 Tavily；开启后会把小红书、X、Reddit 的结果标准化后追加到同一个 `search_results` 结构中。公众号链路不再启用，因为当前 TikHub 不再支持。要替换或新增搜索提供方，需要保持搜索结果 JSON 结构一致，并继续保留 `search_plan_source: build_search_plan.py`、逐条 query 失败处理、缓存和 run log 规则。

搜索计划允许宿主 AI 先给 `ai_search_plan` 草案，用于处理“流程借鉴、专家信号、产品拆解、冷启动渠道”等脚本模板容易过硬的问题。草案必须经 `build_search_plan.py` 校验后才能进入联网搜索；脚本会丢弃泛词 query、补齐证据轴，并用模板 query 回填缺失覆盖。

开放候选池问题会启用 `candidate_discovery` 搜索策略，例如“现在有哪些 AI 产品可以做”“有哪些工具站值得参考”“帮我找一些值得做的 AI 工具站”。它会先查候选池/产品清单、细分赛道、竞品池、用户反馈、SEO 入口、定价和专家信号，再要求报告输出候选池对比表。已有明确目标的问题继续用 `normal_evidence` 单轮证据链；最新动态、明确 SEO/转化/选择/复盘问题不会额外加候选池发现轮。

默认运行产物目录按当前 skill 所在 workspace 推导：

```text
<openclaw-workspace>/info-alchemist/
  reports/
    信息炼金报告-<决策对象>-YYYYMMDD.md
    html/
      <run_id>.html
      <run_id>-profile.html
  runs/
  memory/
  cache/
```

需要由宿主指定沙箱目录时，可设置 `INFO_ALCHEMIST_DATA_DIR`；也可分别用 `INFO_ALCHEMIST_REPORT_DIR` / `INFO_ALCHEMIST_MARKDOWN_REPORT_DIR`、`INFO_ALCHEMIST_HTML_REPORT_DIR`、`INFO_ALCHEMIST_RUN_DIR`、`INFO_ALCHEMIST_MEMORY_DIR`、`INFO_ALCHEMIST_CACHE_DIR` 覆盖单类产物位置。

不要把搜索 API key 写进代码、README、示例输出或提交包。推荐使用本地 `.env` 文件。

本地测试配置：

```bash
cd "$SKILL_DIR"
cp .env.example .env
```

然后编辑 `.env`：

```bash
TAVILY_API_KEY=tvly-YOUR_REAL_KEY
```

也可以只在当前终端临时配置：

```bash
export TAVILY_API_KEY=tvly-YOUR_REAL_KEY
```

启用 TikHub 垂直社媒搜索：

```bash
INFO_ALCHEMIST_ENABLE_TIKHUB=1
TIKHUB_API_KEY=YOUR_TIKHUB_BEARER_TOKEN
TIKHUB_API_BASE=https://api.tikhub.io
TIKHUB_PLATFORMS=xhs,x,reddit
TIKHUB_MAX_QUERIES=0
TIKHUB_RESULTS_PER_GROUP=3
```

深度搜索默认开启 TikHub 三平台补充搜索。为控制成本，TikHub 层每轮只为小红书、X、Reddit 各选择 1 条短 query：先按平台偏好从 search plan 中选最适合的 `search_intent`，再按平台改写实际 `query`。小红书使用中文社媒语境词，X/Reddit 使用英文社区语境词。单个 TikHub 渠道报错、超时或无结果只记录在 run log 的内部垂直搜索统计里，不进入用户报告；报告只呈现搜到的社媒信号。

`.env` 会被 git 忽略，但如果你手动打 zip，必须排除它。

## 怎么证明真的调用了 Info-Alchemist

不要只相信 AI 说“我调用了”。让它运行本地自检脚本：

```bash
cd "$SKILL_DIR"
python3 scripts/self_check.py --compact
```

有效输出会包含：

- `INFO_ALCHEMIST=TRUE`

在飞书、小龙虾或 Codex 里，如果你怀疑它是编的，就直接问：

```text
证明你真的调用了 Info-Alchemist：请运行 skill/Info-Alchemist/scripts/self_check.py --compact，并只输出 INFO_ALCHEMIST=TRUE。
```

正常的信息炼金报告开头也应该带一行 `INFO_ALCHEMIST=TRUE`。完整 JSON 自检只用于调试，不要默认展示给用户。

如果它调用了 Brave / `web_search` / `web_fetch`，这些结果不能算 Info-Alchemist 证据；必须丢弃并重新用标准搜索计划跑一次。本轮联网搜索失败时，应停止并输出失败诊断，而不是补一个伪报告。

推荐打包命令：

```bash
cd "$(dirname "$SKILL_DIR")"
zip -r Info-Alchemist.zip Info-Alchemist \
  -x "*/.env" \
  -x "*/.cache/*" \
  -x "*/memory/runs/*.json" \
  -x "*/memory/alchemy_records.jsonl" \
  -x "*/memory/personal_voi_profile.md" \
  -x "*/web/reports/*.html" \
  -x "*/__pycache__/*" \
  -x "*.pyc"
```

## 输出什么

Info-Alchemist 被触发后，不等于立刻搜索。对于“哪些 AI 视频站值得参考”这类开放集合查询，必须先确认行动目的。研究维度明确不等于决策明确；用户确认之前，不允许联网搜索，不允许输出完整报告，不允许给最终状态。

只有这些情况可以直接进入搜索：

- 用户已经明确行动目的，例如“我想判断要不要从 0 做一个 AI 视频工具站，查哪些站值得参考，重点看新用户留存和 SEO 结构”
- 用户明确来源、时间窗和筛选标准，例如“查 OpenAI 官方博客过去 7 天更新，按时间列出”
- 上一轮已经确认过行动目的，例如用户刚说“我是想从 0 判断要不要做一个新工具站”或回复了行动选项编号

除“行动目的确认”和“联网搜索失败诊断”外，完整输出是固定骨架的“信息炼金报告”。第一行必须是 `INFO_ALCHEMIST=TRUE`，前面不能有任何内容。不要写“快报”“简报”“先看行业变化”“继续查”这类自由格式。

行动目的确认本身也要显示 `INFO_ALCHEMIST=TRUE`，但不输出完整报告。宿主默认只调用一次正式入口：

```bash
python3 scripts/formal_run.py --query "<用户原始问题>"
```

如果上一轮已经确认过意图，用户本轮回复选项、短确认或详细补充，继续用同一个入口：

```bash
python3 scripts/formal_run.py --previous-query "<上一轮原始查询>" --reply "<用户本轮回复>"
```

如果上一轮返回了 `confirmation_round`，续跑时应一并传回：

```bash
python3 scripts/formal_run.py --previous-query "<上一轮原始查询>" --reply "<用户本轮回复>" --confirmation-round <上一轮轮次>
```

`formal_run.py` 会完成行动目的确认或续跑解析、搜索计划、联网搜索、证据整理和 run log 批量写入。`clarify_intent.py`、`resolve_confirmation.py`、`build_search_plan.py`、`tavily_search.py` 和 `synthesize_tavily_results.py` 仍可单独调试，但宿主不要默认手动串联这些脚本。

用户可见报告标题必须全部中文，并完整保留固定骨架：

- `# 信息炼金报告`
- `## 核心判断`
- `## 决策问题`
- `## 专家判断`
- `## 候选行动`
- `## 高价值证据`
- `## 缺失的证据`
- `## 下一步行动`

文字版每个 `##` 模块之间必须插入独立一行 `---`，并在分割线上下各保留一个空行。不要只靠空行分隔模块，否则长报告会在飞书里挤在一起。

顶层章节固定不按问题类型改名，但 `formal_run.py` 会返回 `report_mode`、`report_mode_label` 和 `report_mode_guide`。宿主写报告时必须按该模式调整章节内部写法，例如机会判断、放弃判断、用户痛点、竞品判断、MVP 切口、商业模式/定价、分发判断、趋势与时机、运营与交付、复盘与转向、方案选择。

为兼容 HTML 可视化，`## 决策问题` 第一行写 `报告模式：<模式名>`，第二行写 `决策对象：<topic>`；各章节内部优先使用稳定的 `###` 小标题和 Markdown 表格，不要写裸 HTML。报告模式只用于内部结构选择，HTML 首屏不展示模式标签。

OpenClaw 展示层必须在报告标题处提供 HTML 可视化报告入口：

1. 宿主先产出完整 Markdown 文字报告，标题仍写 `# 信息炼金报告`。
2. 发送前运行：

```bash
python3 scripts/record_final_output.py --run-id "<formal_run.py 返回的 run_id>" --file "<final_report.md>"
```

3. 该脚本会归档完整中文标题 Markdown：`info-alchemist/reports/信息炼金报告-<决策对象>-YYYYMMDD.md`，生成短文件名 HTML：`info-alchemist/reports/html/<run_id>.html`，并返回 `user_visible_text`。默认链接是本地 HTTP 地址，脚本会自动启动只读静态服务；不要直接发 `file://`，飞书会把文字染蓝但拦截打开。`user_visible_text` 是适合聊天窗口的短版回复，格式类似：

```md
INFO_ALCHEMIST=TRUE

# 信息炼金报告

[点击查看->可视化《信息炼金报告》](http://127.0.0.1:<自动选择端口>/<run_id>.html)

## 核心判断
短版结论。
```

4. 用户可见回复必须直接发送 `user_visible_text`。不要把完整 Markdown 长表格报告整段发到飞书；完整证据、经济性表和 token 估算保留在 Markdown 归档和 HTML 页面里，避免聊天窗口长消息卡住。

对用户展示的解释、理由和报告正文都应该使用中文。机器 JSON、schema 和测试可以保留英文字段名和枚举值；用户报告不要用 `painful_evidence`、`evidence_gaps`、`final_status`、`next_minimum_action`、`stop_search_rule` 作为标题或字段，也不要写 `final_status: probe` 这类状态行。用户可见状态统一写成：放弃、归档、观察、小范围验证、执行。

`## 专家判断` 必须放在 `## 候选行动` 上方，优先使用 `evidence_pack.expert_judgment` 和 `search_intent=expert_signal` 的联网搜索结果。内容要回答三件事：这个领域里可识别的专家/高影响力实践者是谁；他们正在关注什么问题；他们现在用什么产品、流程或商业方式解决。推荐表头：`| 领域专家 | 专家/实践者信号 | 来自渠道 | 为什么选 | 他们关注的问题 | 当前解法 | 对我们的启发 | 可信度 |`。`领域专家` 必须写出可称呼的专家主体：优先写可验证的人名；没有明确人名时，写可识别的机构、社区或实践者群体，例如“AI 工具站独立开发者”“Reddit 的目标用户群体”“小红书 AI 副业博主”；只有连群体主体也无法识别时，才写“未识别到明确专家主体”。可信度应按主体具体程度、来源强度和证据相关性调整；`为什么选` 必须说明该专家主体与本领域、问题、解法或实践经验的关系。表格必须按可信度从高到低排序，顺序为：高、中高、中、低、待验证。

证据评分规则见 `references/evidence_scoring.md`。不要给整份报告打总分；用户可见评分只用于解释每条高价值证据为什么值得看。

`## 高价值证据` 里的每条证据都要带可点击来源链接，推荐写成 `来源：[标题](https://example.com)`。多个来源用短列表；不要只写裸 URL，也不要写空的“链接：”。表格必须按行动影响从高到低排序，顺序为：高、中高、中、低；同等级内优先放最能改变当前决策的证据。固定表头为：`| 行动影响 | 证据方向 | 发现了什么 | 怎么改变决策 | 来源 | 证据质量 | VOI |`，后 2 列统一写 0-100 整数，推荐格式 `N/100`，分数放在证据内容之后，HTML 证据卡会在卡片底部可视化展示。

产品机会、候选池筛选、商业模式/定价、已有转化、方案选择或用户明确问收益/成本/ROI/回本时，报告内部必须展示商业测算，但不能新增顶层 `##`。推荐放法：

- `## 核心判断`：一句经济性判断，例如“当前只适合小范围验证；回本最敏感变量是付费转化和单次任务成本”。
- `## 决策问题`：写测算口径、周期、币种；初始投入和月成本必须先看本轮搜索有没有数据，不要单独输出 `数字/假设` 来源状态表。
- `## 候选行动`：有真实金额、成本、价格或保本输入时，使用 `| 候选行动 | 初始投入 | 初始投入依据 | 月成本 | 月成本依据 | 收入/价格证据 | 保本门槛 | 建议 |`；如果初始投入和月成本都缺失，不要铺重复的“未取得公开证据”大表，改用 `| 要补的数字 | 当前状态 | 怎么拿 | 用来判断什么 |`。
- 可补三档场景表：`| 指标 | 保守 | 基准 | 乐观 | 来源/假设 |`。
- `## 高价值证据`：有证据时新增 `### 商业基准 / ROI`、`### 成本结构`、`### 转化与留存`。
- `## 下一步行动`：使用 `### 7 天验证闸门`，表头为 `| 7 天验证项 | 验证方式 | 7 天记录什么 | 7 天后怎么判断 |`；没有公开证据支撑时，不要写固定百分比通过线。

ROI、LTV、CAC、转化率、留存、毛利、行业平均收益、初始投入、月成本和单次任务成本等数字必须在对应依据列里标注来源状态。公开资料拿不到时，写“未取得公开证据”或“待用户估算”，不得用低/中/高、系统假设区间或常识补成事实；缺少成本和转化输入时，不输出 90 天 ROI 区间。

`## 缺失的证据` 只写还缺什么、为什么会限制判断，以及补证方向；不要展示证据覆盖度分数表。

`## 下一步行动` 直接写具体下一步和优先顺序；不要展示 VOI × 可验证性矩阵。

如果 `evidence_pack.social_platform_signals` 非空，`## 高价值证据` 内必须新增 `### 社交平台` 小节，用表格按小红书、X、Reddit 展示平台、主要看什么、这轮发现、对行动的影响、可信度和来源；推荐表头：`| 社交平台 | 主要看什么 | 这轮发现 | 对行动的影响 | 可信度 | 来源 |`；不要命名为“四渠道信号矩阵”。

如果用户问“最近某类产品有什么新动态”“查竞品/市场变化”“找产品机会”，不属于轻量事实查询；确认行动目的后必须输出完整报告骨架。

## 记忆怎么做

记忆是本地轻量记忆，只存派生洞察，不存原始文章、完整聊天、隐私文件或敏感数据。

```text
info-alchemist/memory/
  alchemy_records.jsonl
  personal_voi_profile.md
```

`personal_voi_profile.md` 会生成面向用户阅读的“个人决策画像”，当前标题固定为：

- 顶部信息：最近更新、已记录决策、画像成熟度、画像说明
- 画像模块：近期决策记录、惯性决策模式、有效证据类型、最近决策洞察、下次询证提醒

禁用记忆写入：

```bash
export DISABLE_MEMORY=1
```

报告生成后不要自动写记忆。只有用户明确表达决策或要求存档时，调用单入口：

```bash
python3 scripts/record_decision.py \
  --query "<本轮用户原始问题>" \
  --decision "<用户决策原文>" \
  --run-log-path "<formal_run.py 返回的 run_log_path，可选>" \
  --insight "<可选：一句话洞察>"
```

详细触发规则见 `references/memory_rules.md`。

## 运行留痕怎么查

每次进入搜索流程，脚本会写入固定运行日志：

```text
info-alchemist/runs/*.json
```

日志里会记录：

- `intent`：用户查询、确认后的查询意图、默认行动等
- `search_plan`：由 `scripts/build_search_plan.py` 生成的搜索计划
- `tavily_result`：内部联网搜索逐条 query 的结果、重试次数、失败原因
- `synthesis`：证据整理结果
- `final_output`：聊天窗口短版回复、完整 Markdown 归档路径和 HTML 报告链接；完整报告发送前必须追加

如果你怀疑模型手写了搜索计划，检查 run log 和联网搜索输入是否带有：

```json
"search_plan_source": "build_search_plan.py"
```

底层搜索脚本会拒绝没有这个字段的手写 search plan。除非明确设置 `DISABLE_RUN_LOG=1`，否则不应跳过运行留痕。

搜索计划里的每条 query 只要求 `query`、`search_intent`、`reason`。高价值证据和行动判断由宿主模型根据本轮搜索结果生成，不使用固定模板。

`scripts/record_final_output.py --run-id <run_id> --file <final_report.md>` 用于校验最终中文报告骨架、归档 Markdown 文字报告、写入 run log，并生成 HTML 可视化报告。缺少 `INFO_ALCHEMIST=TRUE`、缺少固定标题、出现 `final_status` 等用户可见英文字段，都会返回错误；完整报告发送前必须完成这一步，除非明确设置 `DISABLE_RUN_LOG=1` 做调试。

## 文件结构

```text
Info-Alchemist/
  SKILL.md
  README.md
  requirements.txt
  .env.example
  references/
  assets/schemas/
  assets/examples/
  scripts/
  memory/
  web/
  tests/
```

## 离线基础测试

不需要联网搜索 key：

```bash
cd "$SKILL_DIR"
python3 scripts/classify_intent.py "帮我查一下 GPT-image-2 有没有机会，我想看看要不要做相关工具站。"
```

开放集合查询必须进入确认门：

```bash
cd "$SKILL_DIR"
python3 scripts/classify_intent.py "帮我查询哪些 AI 视频站值得参考"
python3 scripts/clarify_intent.py "帮我查询哪些 AI 视频站值得参考"
```

预期：`classify_intent.py` 输出 `trigger_level: clarify`，`clarify_intent.py` 输出确认问题，不允许直接搜索。

确认回复必须能解析为续跑意图：

```bash
cd "$SKILL_DIR"
python3 scripts/resolve_confirmation.py --query "帮我查询哪些 AI 视频站值得参考" "想知道 1 和 3"
```

预期：如果回复只是研究维度，会继续追问行动目的；如果回复是行动选项或“从 0 判断要不要做新工具站”这类行动目的，会进入续跑。

用户确认意图后，才能生成搜索计划：

```bash
cd "$SKILL_DIR"
echo '{
  "user_query": "帮我查询哪些 AI 视频站值得参考",
  "query_type": "reference_collection",
  "topic": "AI 视频站",
  "research_dimensions": ["product_experience", "seo_content_structure"],
  "action_context": "new_product_validation",
  "decision_clarity": "clear",
  "confirmed_intent": "新产品/工具站验证；研究维度：产品体验 + SEO/内容结构",
  "confirmed_intent_type": "reference_multi_dimension"
}' | python3 scripts/build_search_plan.py
```

```bash
cd "$SKILL_DIR"
echo '{
  "user_query": "GPT-image-2",
  "decision_context": "是否要做相关页面或工具站",
  "candidate_actions": ["直接开发工具站", "先做对比页", "观察", "放弃"],
  "default_action": "继续调研",
  "voi_information_needed": ["API 是否可用", "是否有搜索需求", "竞品是否在变现"]
}' | python3 scripts/build_search_plan.py
```

```bash
cd "$SKILL_DIR"
python3 scripts/validate_voi_brief.py assets/examples/output_case_01_ai_model_opportunity.json
```

## 联网搜索测试

确认 `.env` 已存在，或者当前终端已经设置 `TAVILY_API_KEY`，然后运行：

```bash
echo '{
  "user_query": "GPT-image-2",
  "decision_context": "是否要做相关页面或工具站",
  "candidate_actions": ["直接开发工具站", "先做对比页", "观察", "放弃"],
  "default_action": "继续调研",
  "voi_information_needed": ["API 是否可用", "是否有搜索需求", "竞品是否在变现"]
}' | python3 scripts/formal_run.py
```

预期输出包含 `route=formal_report_context`、`run_id`、`run_log_path`、`search_result_summary`、`evidence_pack`，开放候选池问题还会包含 `candidate_discovery_pack`。如果 key 未配置，会输出中文错误提示。不要直接手写 `search_plan` 给搜索脚本，它会拒绝。普通用户报告不要展示底层搜索提供方名称。

默认流程：`formal_run.py -> 宿主模型输出报告`。分步脚本只用于调试。

## 记忆测试

建议先写到临时文件，避免污染正式记忆：

```bash
cd "$SKILL_DIR"
python3 scripts/append_memory.py assets/examples/alchemy_record_case_01.json /private/tmp/info_alchemist_test_records.jsonl
python3 scripts/update_personal_voi_profile.py /private/tmp/info_alchemist_test_records.jsonl /private/tmp/info_alchemist_test_profile.md
```

正式写入时再使用：

```bash
python3 scripts/record_decision.py \
  --query "<本轮用户原始问题>" \
  --decision "<用户决策原文>" \
  --run-log-path "<formal_run.py 返回的 run_log_path，可选>"
```

删除或重置记忆时，只编辑当前 OpenClaw workspace 下的 `info-alchemist/memory/alchemy_records.jsonl` 和 `info-alchemist/memory/personal_voi_profile.md`。删除记录后重新运行 `update_personal_voi_profile.py`，不要把原始文章、完整聊天或敏感数据补写进去。

## 缓存和幂等

底层搜索脚本会根据 `search_plan[].query/search_intent` 生成确定性缓存键，默认缓存 86400 秒。默认 6 条 query 同批并行搜索，单条请求默认超时 12 秒、失败后重试 1 次。正式入口返回完整搜索结果用于写报告，并同步写入 run log 和缓存；只有分步调试脚本的 stdout 默认会压缩。用 `INFO_ALCHEMIST_CACHE_TTL_SECONDS` 调整缓存 TTL，用 `INFO_ALCHEMIST_SEARCH_CONCURRENCY` 调整并发，用 `TAVILY_REQUEST_TIMEOUT_SECONDS` 调整超时，用 `INFO_ALCHEMIST_STDOUT_TEXT_LIMIT` 调整 stdout 摘要长度，用 `INFO_ALCHEMIST_STDOUT_FULL=1` 输出完整搜索结果，用 `DISABLE_CACHE=1` 关闭缓存。

正式使用优先调用 `scripts/record_decision.py`。`scripts/append_memory.py` 会为记录生成 `record_id`，同一记录重复写入时返回 `deduped: true`，不会重复追加 JSONL。
