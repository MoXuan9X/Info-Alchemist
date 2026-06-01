# 竞争格局

这个 skill 的替代品包括：

- 普通搜索引擎
- Perplexity 等 AI answer engine
- Tavily Search 等公开搜索 API
- 趋势仪表盘
- 收藏夹和稍后读工具
- Notion / Obsidian 等个人知识库
- 市场调研模板
- `iterate-pivot-decision`: 面向产品决策的迭代/转向判断框架
- `evidence-synthesis`: 把材料整合成证据性结论的证据综合 skill

## 已调研的同类 skill

| 名称 | 一句话定位 | 来源平台 | 原始链接 | 作者/组织 | 格式 | 功能类别 | 自动化方式 | 复杂度 | 推荐状态 |
|---|---|---|---|---|---|---|---|---|---|
| iterate-pivot-decision | 面向产品决策的迭代/转向判断 | skill.sh | https://skills.sh/product-on-purpose/pm-skills/iterate-pivot-decision | product-on-purpose | skill | 决策框架 | Manual/Method | L2 | Recommended |
| evidence-synthesis | 把材料整合成证据性结论 | skill.sh | https://skills.sh/gasserane/personal-skills/evidence-synthesis | gasserane | skill | 证据综合 | Manual/Research | L2 | Recommended |

差异化：

- 从决策开始，而不是从关键词开始
- 默认用 Tavily 搜公开证据，但不把判断外包给搜索提供方
- 把证据映射到行动状态
- 只记录派生 VOI 记忆
- 当最小实验比继续搜索更便宜时，帮助用户停止搜索

具体对比：

| 替代品 | 它擅长什么 | Info-Alchemist 的差异 |
|---|---|---|
| Perplexity / 普通搜索 | 快速回答和链接聚合 | 先定义默认行动和行动改变证据，再决定是否继续搜索 |
| Tavily Search | 公开搜索 API | Tavily 是默认搜索提供方，不是决策者；本 skill 负责 VOI 判断、缺口和下一步行动 |
| Notion / Obsidian | 保存资料和长期知识 | 只保存派生洞察，不保存原始文章或完整聊天 |
| `iterate-pivot-decision` | 已有产品的迭代/转向判断 | 更早介入“机会是否值得查/试”的取证阶段，并把公开搜索证据接到下一步行动 |
| `evidence-synthesis` | 证据综合成结论 | 结论必须落到放弃、归档、观察、小范围验证或执行，并给出停止搜索规则和本地决策记忆 |

定位：

```text
用户买的不是搜索工具，而是信息海关。
```
