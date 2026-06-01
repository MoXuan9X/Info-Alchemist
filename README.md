# Info-Alchemist / 信息炼金术士

Info-Alchemist 是一个给 AI Agent 用的本地调研能力（Skill）。

它不是帮你堆链接，而是帮你判断：这些信息会不会改变下一步行动。

适合用来问：

- 这个方向值不值得做？
- 最近有哪些竞品值得参考？
- 某个 AI 产品机会能不能做？
- 要不要继续投入这个项目？
- 这个页面或工具站有没有机会？

## 它解决什么问题

普通搜索通常回答“查到了什么”。Info-Alchemist 更关注“查到的信息是否足以改变行动”。

它会把一个模糊问题拆成：

- 你真正要做的决策是什么？
- 如果现在不继续查，你默认会怎么做？
- 哪些证据可能改变这个决定？
- 哪些公开证据已经能查到？
- 哪些关键证据还必须靠测试、访谈、留资、转化数据或亲自体验补齐？

## 你会得到什么

Info-Alchemist 会输出一份中文“信息炼金报告”。报告重点不是资料汇总，而是行动判断。

报告通常包含：

- **核心判断**：现在更适合做、先小范围验证、继续观察，还是放弃。
- **决策问题**：这次真正要判断的对象、边界和默认行动。
- **专家判断**：公开资料里能识别到的专家、实践者、社区或高影响力信号。
- **候选行动**：接下来可以选的几个行动方案，以及优先顺序。
- **高价值证据**：真正会影响决策的证据、来源链接、证据质量和信息价值。
- **缺失的证据**：现在还不能确定什么，为什么会限制判断。
- **下一步行动**：最小验证动作，例如做页面、跑小实验、访谈用户、收集转化数据。

如果报告生成了 HTML 页面，AI Agent 还会给你一个可视化报告入口，方便复看和分享。

## 个人决策画像

Info-Alchemist 还可以在本地生成个人决策画像。

它不是保存完整聊天，也不是保存原始文章，而是记录你做决策后的派生洞察，例如：

- 你经常被什么信息触发去调研。
- 你默认容易采取什么行动。
- 哪类证据最容易改变你的决定。
- 最近哪些决策值得复盘。
- 下次遇到类似问题时应该优先验证什么。

个人决策画像默认保存在本地，不上传到远程服务。只有当你明确让 AI Agent 记录一次决策时，才会写入本地记忆。

## 免费快速安装

把下面这段话完整复制给你正在使用的 AI Agent。

适用：OpenClaw、Codex、Claude Code、Cursor、Gemini CLI。

```text
请帮我安装 Info-Alchemist：
https://github.com/MoXuan9X/Info-Alchemist

安装完成后，请告诉我：
1. 是否安装成功
2. 我需要在哪个文件里填写 Tavily API key
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

如果你只想先完成安装和普通网页搜索，保持 `INFO_ALCHEMIST_ENABLE_TIKHUB=0`。

只有当你需要小红书、X、Reddit 这类社交平台信号时，再把它改成 `INFO_ALCHEMIST_ENABLE_TIKHUB=1`，并填写 TikHub API key。

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

## 开发者和 Agent 接入

普通用户完成上面的安装、配置和真实查询测试即可。

如果你要把 Info-Alchemist 接入自己的 Agent，或想了解完整运行规则，请看：

- `SKILL.md`
- `references/host_integration.md`
- `references/tavily_search.md`
- `references/memory_rules.md`
- `references/evidence_scoring.md`

## License

MIT
