# 触发规则

预触发路由主要依赖 `SKILL.md` frontmatter 的 `description`。如果宿主 agent 不支持 native skill routing，先把 [host_integration.md](host_integration.md) 的片段复制到宿主 agent 的 `AGENTS.md`、system prompt 或工具路由配置中。

## 判断原则

意图判断优先使用 [ai_intent_router.md](ai_intent_router.md) 的 AI 语义路由。不要维护越来越长的关键词表。判断时先问：

- 用户是在查一个确定事实，还是在筛选一批信息？
- 这次查询是否服务于机会、竞品、SEO、产品、市场或行动复盘判断？
- 搜索结果是否可能改变用户 7-14 天内的行动？
- 用户是否已经给出用途、筛选标准、默认行动或候选行动？

## 完整流程

以下语义触发完整 VOI Search Brief；括号里的表达只是例子，不是关键词白名单：

- “有没有机会”
- “值不值得做”
- “要不要做”
- “能不能做”
- “帮我查一下 ... 我想决定”
- “这个方向能不能做”
- “有没有 SEO 机会”
- 用户给出一堆信息并说不知道哪些该做
- 用户复盘行动并问要不要继续
- 用户查最新新闻/趋势/动态，并已说明用途是筛机会、SEO、竞品、产品方向或行动优先级

## 轻量流程或不触发

以下情况不要触发完整流程：

- 简单事实查询
- 翻译
- 润色
- 改写
- 低风险好奇
- 用户已经明确要执行一个具体动作

## trigger_reason_type

只能使用以下枚举：

- `fomo`
- `money_signal`
- `competitor_signal`
- `authority_signal`
- `user_need_signal`
- `efficiency_signal`
- `curiosity`
- `anxiety`
- `other`
