#!/usr/bin/env python3
import json
import re
import sys
from typing import Any, Dict, List


MAX_CONFIRMATION_ROUNDS = 3
ACTIVATION_MARKER_RE = re.compile(
    r"(?<![A-Z0-9_])INFO[\s_-]*ALCHEMIST(?:\s*=\s*TRUE)?(?![A-Z0-9_])|信息炼金术士",
    re.I,
)

QUERY_TYPES = {
    "reference_collection",
    "latest_news",
    "opportunity_research",
    "decision_research",
    "information_pile",
    "action_review",
    "direct_lookup",
    "factual_lookup",
    "curiosity",
    "generic_research",
    "non_applicable",
}

DECISION_CLARITIES = {"unclear", "partial", "clear"}

SEARCH_STRATEGIES = {"normal_evidence", "candidate_discovery"}
GENERIC_AI_TOOL_TOPICS = {
    "ai工具",
    "ai工具站",
    "ai产品",
    "ai产品和工具站",
    "ai网站",
    "ai站点",
    "ai应用",
    "人工智能工具",
    "人工智能产品",
}

GENERIC_AI_TOOL_PREFIXES = (
    "市面上",
    "市场上",
    "最近",
    "最新",
    "现在",
    "目前",
    "当下",
    "海外",
    "国内",
    "有哪些",
    "哪些",
    "有什么",
    "有啥",
    "热门",
    "热门的",
    "比较火",
    "比较火的",
    "很火",
    "很火的",
    "最火",
    "最火的",
    "火的",
    "主流",
    "主流的",
    "流行",
    "流行的",
)

GENERIC_AI_TOOL_SUFFIXES = (
    "有哪些",
    "哪些",
    "有什么",
    "有啥",
    "最近",
    "最新",
    "现在",
    "目前",
    "当下",
    "比较火",
    "很火",
    "最火",
    "火的",
    "热门",
    "主流",
    "流行",
    "市场",
    "市场情况",
    "市场概览",
    "行业",
    "行业情况",
    "现状",
    "生态",
    "分类",
    "类型",
    "类别",
    "趋势",
    "方向",
    "榜单",
    "清单",
    "名单",
    "玩家",
    "赛道",
)

GENERIC_AI_TOOL_ENGLISH_STOPWORDS_RE = re.compile(
    r"\b(?:what|which|are|is|the|latest|recent|recently|now|current|popular|trending|best|top|new|market|overview|landscape|categories?|types?|list|of|out|there)\b",
    re.I,
)

SPECIFIC_AI_TOOL_MODIFIER_RE = re.compile(
    r"\b(?:seo|marketing|sales|image|images|video|videos|document|documents|docs|office|coding|code|developer|developers|website\s*builder|education|learning|workflow|automation|meeting|meetings|music|resume|legal|healthcare|finance|customer\s*support)\b|内容\s*SEO|营销|销售|图片|图像|生图|视频|办公|文档|开发|建站|教育|学习|自动化|工作流|会议|代码|编程|音乐|配乐|游戏|决策|简历|客服|法律|医疗|财务",
    re.I,
)

REPORT_MODE_LABELS = {
    "candidate_mode": "候选池调研",
    "opportunity_mode": "机会判断",
    "kill_mode": "放弃判断",
    "pain_mode": "用户痛点",
    "competitor_mode": "竞品判断",
    "teardown_mode": "流程借鉴",
    "mvp_mode": "MVP 切口",
    "monetization_mode": "商业模式/定价",
    "distribution_mode": "分发判断",
    "timing_mode": "趋势与时机",
    "operations_mode": "运营与交付",
    "review_mode": "复盘与转向",
    "choice_mode": "方案选择",
    "general_mode": "通用决策",
    "none": "非报告",
}

DIMENSION_RULES = [
    (
        "product_experience",
        "产品体验",
        [
            r"产品体验",
            r"新用户",
            r"首页",
            r"模板",
            r"注册",
            r"登录",
            r"试用",
            r"生成流程",
            r"留存",
            r"体验",
            r"MVP",
            r"最小可验证",
            r"第一次成功体验",
            r"账号体系",
            r"无登录",
            r"一个页面",
            r"一个按钮",
            r"激活",
            r"留存",
            r"入住体验",
            r"服务体验",
            r"信任",
            r"活动运营",
            r"onboarding",
            r"user experience",
        ],
    ),
    (
        "business_model",
        "付费/商业模式",
        [
            r"付费",
            r"商业模式",
            r"免费额度",
            r"积分",
            r"订阅",
            r"定价",
            r"商业化",
            r"会员",
            r"复购",
            r"续费",
            r"佣金",
            r"获客",
            r"渠道",
            r"分发",
            r"冷启动",
            r"前\s*100\s*个用户",
            r"B2B",
            r"选址",
            r"水印",
            r"商用",
            r"转化",
            r"pricing",
            r"monetization",
            r"subscription",
        ],
    ),
    (
        "seo_content_structure",
        "SEO/内容结构",
        [
            r"SEO",
            r"内容结构",
            r"搜索流量",
            r"关键词",
            r"内链",
            r"页面",
            r"榜单页",
            r"对比页",
            r"教程页",
            r"流量入口",
            r"内容机会",
            r"社区",
            r"Product Hunt",
            r"小红书",
            r"公众号",
            r"垂直论坛",
            r"demo\s*视频",
            r"SERP",
            r"keyword",
        ],
    ),
    (
        "feature_capability",
        "模型/功能能力",
        [
            r"模型",
            r"功能",
            r"能力",
            r"API",
            r"算力",
            r"基础设施",
            r"平台官方",
            r"平台政策",
            r"自动化",
            r"脚本",
            r"集成",
            r"文生",
            r"图生",
            r"视频编辑",
            r"工作流",
            r"feature",
            r"capability",
            r"integration",
        ],
    ),
]


def has_any(text: str, patterns: List[str]) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def unique(values: List[str]) -> List[str]:
    seen = set()
    output = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text.strip()


def strip_activation_markers(value: str) -> str:
    text = clean_text(value)
    if not text or not ACTIVATION_MARKER_RE.search(text):
        return text
    text = ACTIVATION_MARKER_RE.sub(" ", text)
    text = clean_text(text)
    text = re.sub(r"\s+([，,。；;：:！？?!])", r"\1", text)
    text = re.sub(
        r"^(?:请)?(?:用|使用|调用|走|按|通过|启动|触发|运行|启用)\s*(?:这个|该)?\s*(?:skill|技能|流程|工具)?\s*",
        "",
        text,
        flags=re.I,
    )
    return clean_text(text).strip(" ：:，,。；;")


def strip_query_prefix(value: str) -> str:
    text = strip_activation_markers(value)
    text = re.sub(
        r"^(帮我|请|麻烦|帮忙)?\s*(查询一下|查询|查一下|查查|研究一下|研究|看一下|看看|了解一下|找一下|搜一下|搜索|查|找)\s*",
        "",
        text,
        flags=re.I,
    ).strip()
    text = re.sub(r"[。！？?!]+$", "", text).strip()
    return text or clean_text(value)


def display_target(value: str) -> str:
    text = strip_query_prefix(value)
    text = re.sub(r"([\u4e00-\u9fff])(?i:AI)", r"\1 AI", text)
    text = re.sub(r"(?i)AI\s*(视频|图片|新闻|工具|模型|站)", r"AI \1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "这件事"


def is_ai_media_site_choice_query(value: str) -> bool:
    text = strip_activation_markers(value)
    compact = re.sub(r"\s+", "", text).lower()
    if "ai" not in compact and "人工智能" not in text:
        return False
    has_video = "视频" in compact or "video" in compact
    has_image = "图片" in compact or "图像" in compact or "image" in compact
    has_site_or_product = any(token in compact for token in ["站", "网站", "工具", "产品", "generator", "tool", "site", "app"])
    has_choice = any(token in compact for token in ["还是", "都做", "vs", "哪个", "哪边", "shouldibuild", "choose"])
    return has_video and has_image and has_site_or_product and has_choice


EVALUATION_QUESTION_PATTERNS = [
    r"最小可验证|7\s*天|验证.*假设|笨办法|巨头不愿意|先付费|独立产品|功能插件|内容站|服务型交付|模板|脚本|自动化流程|窗口期|错过",
    r"真需求|工具热度|短期噪音|公开证据.*放弃|直接放弃|功能同质化|头部产品|API\s*包一层|官方下场|不可替代性|过高.*(?:算力|版权|合规|客服)|暂时归档|开发者兴奋|真实用户无感|交付和维护成本|不值得我做",
    r"公开社区|反复抱怨|愿意付费|情绪发泄|花了多少钱|花了.*时间|人力|用什么词描述|高频低价|低频高价|更便宜|更快|更稳|更省心|固定工作流|替代方案|外包|哪类用户.*新工具|立刻得到什么收益",
    r"竞品|头部竞品|小竞品|流量大|商业模式.*弱|分发强|定价.*空间|低端|团队|企业|本地化|证明用户愿意.*付费|比竞品强",
    r"单点工具|工作流工具|系统型产品|MVP|哪个功能.*继续用|第一次成功体验|最长能接受几分钟|自然分享|邀请别人|付费墙|账号体系|无登录|一个页面|一个按钮",
    r"订阅|按量计费|一次性购买|服务打包|省钱|省时间|赚钱|避险|提升质量|价格点|免费额度|团队版|企业版|成本结构|工具预算|营销预算|个人消费|付费触发点|不续费|服务收入",
    r"不依赖\s*SEO|前\s*100\s*个用户|哪些社区|冷启动|主动搜索|场景触发|分发资产|哪个分发渠道|公开拆解|社交传播|demo\s*视频|广告预算|获客路径",
    r"长期驱动力|试新鲜|成本下降|基础设施|太早|刚好|太晚|玩家进入|竞争过热|单一平台政策|突然变得更值得|瞬间失效|进入、等待、观察|只收集证据",
    r"几个想法|哪个想法|失败成本|学习价值|符合我的能力|沉淀.*资产|无效开发|先验证分发|先验证成本|先验证用户身份|区分继续和停止|本周时间|开发、销售、访谈、内容|竞品拆解",
    r"这轮尝试失败|已有反馈|用了但没付费|注册了但不用|继续打磨|换人群|换渠道|归档|沉没成本|转向|保留哪个资产|最有价值的学习|下一轮实验|长期经营|主线",
    r"高频|刚需|现有方案糟糕|Excel|微信群|人工沟通|临时外包|低效环节|损失钱|损失.*时间|损失.*声誉|市场太碎|客单太低|定制太重|增长太慢|替代方案付钱|服务解决|产品化为工具|新技术变化|不经济|不可能|不值得做|能力结构|新的焦虑|新的任务|付费需求|技术兴奋|伪问题",
    r"理想客户|职位|场景|任务|预算|决策压力|什么时刻|必须解决|不能再拖|采用现有竞品|不适配.*工作流|使用者|付款者|决策者|影响者|阻碍者|显性需求|隐藏恐惧|MVP\s*入口|可衡量|安全边界|购买前|最需要被证明|不要服务|贡献最低价值",
    r"新增需求|替换旧工具|政策、技术、平台变化|市场是否足够大|切入点是否足够小|价值链|利润池|信息不对称|利益受损|如何反击|真正卖的是什么|交付确定性|社群讨论|工单反馈|同一种不满|赢家通吃|小而深|垂直产品|原生能力|开源项目|预算归属",
    r"一句话定位|5\s*秒|这和我有关|专家系统|数据层|内容资产|托管服务|做不到|做不好|做太慢|做太贵|更智能|降低了多少成本|差异化|现在购买|继续观望|滩头阵地|小战场|复制我的功能|不可复制|我的品牌|掌控感|转述给老板|转述给同事|转述给朋友",
    r"最危险假设|展示最多功能|功能删除后|价值就崩|第一次使用|顿悟|核心闭环|输入、处理、输出|反馈、复用|保留人工|一次性结果|复用资产|低代码|现成\s*API|拼装验证|留存.*原因|数据积累|流程绑定|团队协作|第一天就放弃|完整但粗糙|端到端系统",
    r"交给\s*AI|不该交给\s*AI|错误成本|人类责任|AI\s*工作流|输入标准|判断标准|输出标准|复核机制|Prompt|知识库|评测集|私有生产资料|通用模型能力|深度编排|人机协同|AI\s*做苦力|人做判断|生成结果|准确率|可用率|节省时间|客户满意度|RAG|微调|规则引擎|人工审核|传统软件逻辑|模型成本上涨|API\s*限流|模型更替|数字员工",
    r"目标用户在哪些社区|搜索词|采购路径|线下关系|内容获客|社群获客|工具获客|插件获客|渠道合作|教育市场|建立信任|引导转化|案例|数据|演示|背书|诊断报告|获客入口|白白送价值|增长飞轮|强购买意图|泛泛兴趣|高质量案例|垂直人群|主动推荐|社交货币|渠道.*热闹|付费客户",
    r"结果付费|工具订阅|按席位|用量|项目|节省金额|托管服务收费|定价.*太低|定价.*太高|毛利|人工复核成本|获客成本|低质量用户|高意愿客户|预算来自|高客单服务|重复部分产品化|哪些功能应该免费|必须收费|适合企业版|试用期|拖延付款|一个月只成交|活得下去",
    r"OPC|注意力|深度工作|SOP|重复事务|客服|销售|交付|财务|法务|清单防呆|情绪和疲劳|交付质量|团队监督|外包|自动化、延后|客户期望|一家公司的服务|哪些指标|每天看|每周|每月|个人知识库|未来的燃料|生病|断网|工具故障|客户爆发|备用机制",
    r"死于没有需求|没有分发|没有信任|没有现金流|没有壁垒|核心假设|完全错了|不受我控制|隐私|版权|合规|安全或伦理风险|放大错误|幻觉|责任|护城河|流程嵌入|审美|专业判断|定制泥潭|一人公司|小团队|触发条件|行业洞察|工程实现|五年后|复利起点",
]

CONTEXTUAL_TOPIC_REFERENCES = [
    r"这个方向",
    r"这个机会",
    r"这个产品",
    r"当前市场",
    r"当前产品",
    r"这个项目",
    r"这轮尝试",
    r"已有反馈",
    r"我现在手上的几个想法",
    r"哪个想法",
    r"哪个方向",
]


def is_evaluation_question(value: str) -> bool:
    text = strip_activation_markers(value)
    return has_any(text, EVALUATION_QUESTION_PATTERNS)


def has_contextual_topic_reference(value: str) -> bool:
    text = strip_activation_markers(value)
    return has_any(text, CONTEXTUAL_TOPIC_REFERENCES)


def extract_context_topic(value: str) -> str:
    text = strip_activation_markers(value)
    patterns = [
        r"(?:^|[，,。；;]\s*)(?:以|围绕|关于|针对|基于)\s*(?P<topic>[^，,。；;？?]+?)\s*(?:为方向|为机会|为产品|这个方向|这个机会|这个产品|方向|机会|产品)?\s*[，,。；;]",
        r"(?P<topic>[^，,。；;？?]{2,40}?)(?:这个方向|这个机会|这个产品|这个项目)\s*[，,。；;]",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            topic = normalize_topic_phrase(match.group("topic"))
            topic = re.sub(r"^(?:以|围绕|关于|针对|基于)\s*", "", topic).strip()
            if topic and is_valid_context_topic(topic):
                return topic
    return ""


def is_valid_context_topic(topic: str) -> bool:
    text = clean_text(topic)
    if not text:
        return False
    return not has_any(text, [
        r"^(如果|哪些|哪个|哪类|这个|用户|竞品|产品|当前|已有|这轮|我现在|反馈|是否|有没有)",
        r"(验证|判断|说明|应该|最该|能否|是否|哪些|哪个|哪类)",
        r"(理想客户|一句话定位|差异化|增长飞轮|交付质量|个人知识库|护城河|方案糟糕|核心假设|品牌应该)",
    ])


def infer_evaluation_action_context(value: str) -> str:
    text = strip_activation_markers(value)
    if has_any(text, [r"这轮尝试失败|已有反馈|用了但没付费|注册了但不用|继续打磨|换人群|换渠道|归档|沉没成本|转向|下一轮实验|长期经营|主线"]):
        return "action_review"
    if has_any(text, [r"前\s*100\s*个用户来了|承受.*(?:交付|维护|客服|成本)|交付和维护成本|维护成本"]):
        return "market_watch"
    if has_any(text, [r"OPC|SOP|重复事务|客服|交付质量|交付压力|交付成本|交付边界|财务|法务|清单防呆|外包|客户期望|指标|个人知识库|生病|断网|工具故障|备用机制"]):
        return "market_watch"
    if has_any(text, [r"付费转化|不续费|价格点|免费额度|订阅|按量计费|一次性购买|服务打包|团队版|企业版|付费触发点|结果付费|工具订阅|按席位|用量|节省金额|毛利|人工复核成本|获客成本|预算来自|高客单服务|试用期|一个月只成交"]):
        return "existing_product_conversion"
    if has_any(text, [r"SEO|搜索词|关键词|SERP|分发资产|内容获客|社群获客|工具获客|插件获客|渠道合作|获客入口|增长飞轮|强购买意图|社交传播|demo\s*视频|广告预算|获客路径|早期用户|前\s*100\s*个用户|100\s*个早期用户|从哪里获得|哪里获得|哪里拿到|从哪.*用户|冷启动"]):
        return "seo_growth"
    if has_any(text, [r"趋势|时机|长期驱动力|热度|成本下降|太早|太晚|玩家进入|竞争过热|单一平台|进入、等待、观察|只收集证据|价值链|利润池|赢家通吃|预算归属|风险|合规|版权|护城河|不受我控制|定制泥潭"]):
        return "market_watch"
    return "new_product_validation"


def strip_intent_suffix(value: str) -> str:
    text = clean_text(value)
    text = re.split(r"[，,。；;]\s*(?:帮我|请|麻烦|查一下|查查|查询|搜索|研究一下|研究|看一下|看看|重点看|主要看|主要判断|主要决定|主要想|我想看|我想找|想找|想决定|判断)", text, maxsplit=1)[0]
    text = re.sub(r"(?:重点看|主要看|主要判断|主要决定|主要想|我想看|我想找|想找|看看|查一下|查询|研究一下).*$", "", text).strip()
    text = re.sub(r"^(?:还有没有|有没有|是否还有|是否有|值不值得|要不要|能不能|可不可以|有没有\s*B2B)\s*(?:做|做商业化|商业化)?\s*(?:机会|风险)?.*$", "", text).strip()
    text = re.sub(r"(?:这个方向|这个市场|相关机会和风险|市场机会和风险)$", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip(" ：:，,。；;")
    return text


def normalize_topic_phrase(value: str) -> str:
    text = strip_intent_suffix(strip_query_prefix(value))
    replacements = [
        r"^我想判断\s*",
        r"^我想决定\s*",
        r"^我想看看\s*",
        r"^我想\s*",
        r"^想判断\s*",
        r"^想决定\s*",
        r"^要不要\s*",
        r"^是否\s*",
        r"^已有\s*",
        r"^现有\s*",
        r"^(?:开|开一家|开一个|做|做一个|做一家|开发|开发一个|推出|推出一个|上线|上线一个)\s*",
        r"^一个\s*",
        r"^一家\s*",
        r"^面向[^，,。；;的]+的\s*",
    ]
    for pattern in replacements:
        text = re.sub(pattern, "", text, flags=re.I).strip()
    text = re.sub(r"^现在(?=在|开|做|开发|推出|上线)", "", text).strip()
    text = re.sub(
        r"^在(?=(?:北京|上海|广州|深圳|杭州|成都|南京|苏州|武汉|西安|重庆|天津|长沙|郑州|青岛|厦门|纽约|东京|新加坡|美国|日本|欧洲|东南亚|国内|海外|本地|社区|校园|县城|一线城市|二线城市|下沉市场))",
        "",
        text,
        flags=re.I,
    ).strip()
    text = re.sub(
        r"^(?P<scope>(?:北京|上海|广州|深圳|杭州|成都|南京|苏州|武汉|西安|重庆|天津|长沙|郑州|青岛|厦门|纽约|东京|新加坡|美国|日本|欧洲|东南亚|国内|海外|本地|社区|校园|县城|一线城市|二线城市|下沉市场)[^，,。；;]{0,8}?)(?:开一家|开一个|开|做一家|做一个|做|开发一个|开发|推出一个|推出|上线一个|上线)\s*",
        r"\g<scope>",
        text,
        flags=re.I,
    ).strip()
    text = re.sub(r"\b现在\b", "", text).strip()
    text = re.sub(r"(?:这个方向|这个市场)$", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip(" ：:，,。；;")
    return text or strip_query_prefix(value)


def extract_owned_product_topic(value: str) -> str:
    text = clean_text(value)
    patterns = [
        r"我(?:有|现在有|已有|经营|运营)\s*(?:一个|一家)?\s*(?P<topic>[^，,。；;]+?)(?:，|,|。|；|;|想|要)",
        r"我们(?:有|现在有|已有|经营|运营)\s*(?:一个|一家)?\s*(?P<topic>[^，,。；;]+?)(?:，|,|。|；|;|想|要)",
        r"(?:已有|现有|我的|我们(?:的)?)\s*(?P<topic>[^，,。；;]+?)(?:，|,|。|；|;|想|要|的)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            topic = normalize_topic_phrase(match.group("topic"))
            if is_plausible_owned_product_topic(topic):
                return topic
    return ""


def is_plausible_owned_product_topic(topic: str) -> bool:
    text = clean_text(topic).strip(" “”…\"'")
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 2:
        return False
    if not is_valid_context_topic(text):
        return False
    return not has_any(text, [
        r"^(理想客户|一句话定位|差异化|增长飞轮|交付质量|个人知识库|护城河)$",
        r"(现有方案|方案糟糕|功能|品牌|定位|客户|用户|市场|赛道|反馈|核心假设|利润池|价值链)",
        r"(是什么|在哪里|来自|还是|如果|哪些|哪个|哪类)",
    ])


def extract_reference_topic(value: str) -> str:
    raw_text = clean_text(value)
    owned_topic = extract_owned_product_topic(value)
    patterns = [
        r"(?:哪些|有哪些|有什么|找几个|找一些|一批)\s*(?P<topic>[^，,。；;?？]+?)\s*(?:值得参考|可以参考|可参考|适合参考|值得借鉴|可以借鉴|值得对标|可以对标|做得好|商业化做得好)(?:[，,。；;?？].*)?$",
        r"(?P<topic>[^，,。；;?？]+?)\s*(?:有哪些|哪些|有什么)\s*(?:值得参考|可以参考|可参考|值得借鉴|可以借鉴|值得对标|可以对标|做得好|商业化做得好)(?:[，,。；;?？].*)?$",
        r"(?P<topic>[^，,。；;?？]+?)\s*(?:值得参考|可以参考|可参考|适合参考|值得借鉴|可以借鉴|值得对标|可以对标)(?:的?[^，,。；;?？]*)?(?:[，,。；;?？].*)?$",
        r"(?:找几个|找一些|找一批|找|查)\s*(?P<topic>[^，,。；;?？]+?)\s*(?:参考|借鉴|对标)(?:[，,。；;?？].*)?$",
        r"(?:参考|借鉴|对标)\s*(?P<topic>[^，,。；;?？]+)",
    ]
    for text in unique([raw_text, strip_query_prefix(value)]):
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                topic = match.group("topic").strip(" ：:，,。")
                topic = re.sub(r"^(哪些|有哪些|有什么)\s*", "", topic).strip()
                if owned_topic and re.search(r"^(竞品|它们|他们|同行|同类)", topic):
                    return owned_topic
                return normalize_topic_phrase(topic) or strip_query_prefix(value)
    return ""


def is_reference_collection_query(value: str) -> bool:
    text = clean_text(value)
    return bool(
        extract_reference_topic(text)
        and has_any(text, [r"参考|借鉴|对标|竞品|做得好|商业化做得好"])
    )


def is_latest_news_query(value: str) -> bool:
    text = strip_query_prefix(value)
    return bool(
        has_any(
            text,
            [
                r"最新.*(新闻|趋势|动态|变化)",
                r"(新闻|趋势|动态|变化).*最新",
                r"(最近|这周|近来|近期).*(新闻|趋势|动态|变化)",
                r"latest.*(?:news|trend|update)",
                r"(?:news|trend|update).*latest",
                r"today.*news|news.*today",
            ],
        )
    )


def is_popular_tool_collection_query(value: str) -> bool:
    text = strip_query_prefix(value)
    has_list_cue = has_any(text, [r"哪些|有哪些|有什么|有啥|名单|榜单|推荐|排行|list|best|top|what|which"])
    has_popular_tool = (
        has_any(text, [r"最近|最新|这周|近来|近期|热门|比较火|很火|火的|头部|popular|trending|latest|recent|best|top"])
        and has_any(text, [r"AI|artificial intelligence|人工智能|工具站|网站|站点|产品|products?|工具|tools?|SaaS|App|apps?|应用"])
    )
    return bool(
        has_popular_tool
        and (has_list_cue or (is_generic_ai_tool_topic(text) and not has_explicit_action_purpose(text)))
    )


def clean_popular_tool_topic(value: str) -> str:
    text = clean_text(value)
    text = re.sub(r"[、，,]+\s*的", "的", text)
    text = re.sub(r"^(?:现在|最近|最新|这周|近来|近期|当下|目前)\s*", "", text)
    text = re.sub(r"^(?:最近|最新|热门|比较火|很火|最火|火的|头部|主流|流行)\s*(?:的)?\s*", "", text)
    text = re.sub(r"^(?:有哪些|哪些|有什么|有啥)\s*", "", text)
    text = re.sub(r"(?:有哪些|哪些|有什么|有啥|名单|榜单|推荐|排行|list|best|top).*$", "", text, flags=re.I)
    text = re.sub(r"^(?:最近|最新|热门|比较火|很火|最火|火的|头部|主流|流行)\s*(?:的)?\s*", "", text)
    text = re.sub(r"类\s*的\s*AI", "类 AI", text, flags=re.I)
    text = re.sub(r"的\s*AI\s*(工具站|网站|站点|产品|工具|App|应用)", r"AI \1", text, flags=re.I)
    text = re.sub(r"([\u4e00-\u9fff])(?i:AI)", r"\1 AI", text)
    text = re.sub(r"(?i)AI\s*(工具站|网站|站点|产品|工具|App|应用)", r"AI \1", text)
    text = re.sub(r"\s+", " ", text).strip(" ：:，,。；;、")
    return text


def extract_popular_tool_topic(value: str) -> str:
    text = strip_query_prefix(value)
    after_cue = re.search(r"(?:有哪些|有什么|有啥)\s*(?P<topic>[^，,。；;?？]+)", text, re.I)
    if after_cue:
        topic = clean_popular_tool_topic(after_cue.group("topic"))
        if topic in {"市场", "市场情况", "现状", "生态", "分类", "类型", "类别", "趋势", "方向"} and is_generic_ai_tool_topic(text):
            return "AI 工具"
        if topic:
            return topic
    before_cue = re.split(r"(?:有哪些|哪些|有什么|有啥|名单|榜单|推荐|排行|list|best|top)", text, maxsplit=1, flags=re.I)[0]
    topic = clean_popular_tool_topic(before_cue)
    return topic or display_target(value)


def extract_news_topic(value: str) -> str:
    text = strip_query_prefix(value)
    if re.search(r"\bAI\b|人工智能|artificial intelligence", text, re.I):
        if has_any(text, [r"工具站|网站|站点|产品(?!化)|工具|应用|app|apps?|tools?|products?|websites?|sites?"]):
            if SPECIFIC_AI_TOOL_MODIFIER_RE.search(text):
                return extract_candidate_discovery_topic(text)
            return "AI 工具"
        return "AI"
    text = re.split(r"[，,。；;]\s*(?:我想|想|看看|主要|重点)", text, maxsplit=1)[0]
    topic = re.sub(r"(最近|最新|今日|今天|这周|新闻|动态|趋势|变化|today|latest|news|trends?|updates?)", " ", text, flags=re.I)
    topic = re.sub(r"有什么|有啥|哪些|有哪些|新", " ", topic)
    topic = re.sub(r"(^|\s)的(\s|$)", " ", topic)
    topic = re.sub(r"\s+", " ", topic).strip(" ：:，,。")
    return normalize_topic_phrase(topic) or text


def extract_generic_topic(value: str) -> str:
    raw_text = strip_query_prefix(value)
    text = strip_intent_suffix(raw_text) if re.search(
        r"[，,。；;]\s*(?:帮我|请|麻烦|查一下|查查|查询|搜索|研究一下|研究|看一下|看看|重点看|主要看|主要判断|主要决定|主要想|我想看|我想找|想找|想决定|判断)",
        raw_text,
    ) else raw_text
    patterns = [
        r"(?P<topic>[^，,。；;]+?)\s*(?:还有没有|有没有|是否还有|是否有|值不值得|要不要|能不能|可不可以).*(?:机会|做|商业化|风险)",
        r"(?:要不要|是否|值不值得|能不能|可不可以)\s*(?:在)?\s*(?:开|开一家|开一个|做|做一个|做一家|开发|开发一个|推出|推出一个|上线|上线一个|把现有[^，,。；;]*加)?\s*(?P<topic>[^，,。；;]+)",
        r"(?:我想|想)\s*(?:判断|决定)?\s*(?:要不要|是否)?\s*(?:在)?\s*(?:开|开一家|开一个|做|做一家|做一个|开发|开发一个|推出|推出一个|上线|上线一个)?\s*(?P<topic>[^，,。；;]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            topic = normalize_topic_phrase(match.group("topic"))
            if topic:
                return topic
    return normalize_topic_phrase(text) or strip_query_prefix(value)


def extract_dimensions(value: str) -> List[str]:
    text = clean_text(value)
    dimensions = []
    for key, _label, patterns in DIMENSION_RULES:
        if has_any(text, patterns):
            dimensions.append(key)
    return unique(dimensions)


def is_generic_opportunity_topic(topic: str) -> bool:
    text = normalize_topic_phrase(topic)
    compact = re.sub(r"\s+", "", text).lower()
    if not compact:
        return True
    exact_generic = {
        "机会",
        "新机会",
        "产品机会",
        "新产品机会",
        "产品方向",
        "新产品方向",
        "赚钱机会",
        "赚钱方向",
        "创业机会",
        "创业方向",
        "副业机会",
        "副业方向",
        "ai机会",
        "ai产品机会",
        "ai产品方向",
        "ai工具机会",
        "ai工具方向",
        "ai工具站",
        "ai工具站机会",
        "ai网站机会",
        "saas机会",
        "saas产品机会",
    }
    if compact in exact_generic:
        return True
    if re.fullmatch(
        r"(?:ai|人工智能|新|最新|可验证|可赚钱|赚钱|副业|创业|商业|产品|工具|工具站|网站|站点|应用|app|saas|项目|方向|机会|机会点|赛道|需求|idea|ideas|opportunity|opportunities)+",
        compact,
        re.I,
    ):
        return True
    return False


def should_confirm_broad_opportunity(text: str, topic: str, query_type: str) -> bool:
    if query_type != "opportunity_research":
        return False
    if is_candidate_discovery_query(text):
        return False
    if not is_generic_opportunity_topic(topic):
        return False
    return True


def is_generic_ai_tool_topic(topic: str) -> bool:
    text = normalize_topic_phrase(topic)
    if not text:
        return False
    if not re.search(r"(?<![A-Za-z])AI(?![A-Za-z])|artificial intelligence|人工智能", text, re.I):
        return False
    if SPECIFIC_AI_TOOL_MODIFIER_RE.search(text):
        return False
    compact = re.sub(r"\s+", "", text).lower()
    compact = compact.replace("artificialintelligence", "ai")
    for prefix in GENERIC_AI_TOOL_PREFIXES:
        compact = re.sub(f"^(?:{re.escape(prefix)})+", "", compact, flags=re.I)
    compact = re.sub(r"^的", "", compact)
    previous = None
    while previous != compact:
        previous = compact
        for suffix in GENERIC_AI_TOOL_SUFFIXES:
            compact = re.sub(f"(?:{re.escape(suffix)})+$", "", compact, flags=re.I)
    english_compact = GENERIC_AI_TOOL_ENGLISH_STOPWORDS_RE.sub(" ", text.lower())
    english_compact = re.sub(r"\s+", " ", english_compact).strip()
    if compact in GENERIC_AI_TOOL_TOPICS:
        return True
    if re.fullmatch(r"(?:ai|人工智能)(?:产品|products?|工具|tools?|工具站|网站|websites?|站点|sites?|应用|app|apps|applications?|saas)s?", compact, re.I):
        return True
    return bool(
        re.fullmatch(
            r"(?:ai|artificial intelligence)\s*(?:tools?|products?|apps?|applications?|websites?|sites?|saas)",
            english_compact,
            re.I,
        )
    )


def has_candidate_action_purpose(value: str) -> bool:
    return has_any(value, [
        r"可以做|能做|值得做|值得探索|找.*机会|产品机会|工具站机会|低成本验证|按.*能力|适合.*(?:独立开发|一个人|我|我们)",
    ])


def should_confirm_broad_ai_tool_scope(text: str, topic: str, query_type: str, action_context: str) -> bool:
    if not is_generic_ai_tool_topic(topic):
        return False
    if has_candidate_action_purpose(text):
        return False
    if action_context in {"seo_growth", "existing_product_conversion", "choice_decision"} and has_explicit_action_purpose(text):
        return False
    if query_type in {"reference_collection", "opportunity_research", "generic_research", "curiosity", "latest_news"}:
        return True
    return False


def is_candidate_discovery_query(value: str) -> bool:
    text = strip_activation_markers(value)
    if not text:
        return False
    if has_any(text, [r"以\s*[^，,。；;？?]{2,40}\s*为方向"]):
        return False
    object_pattern = r"(?:AI|artificial intelligence|人工智能|产品|products?|工具站|工具|tools?|网站|websites?|sites?|站点|应用|apps?|app|SaaS|竞品|对标|参考对象)"
    candidate_patterns = [
        rf"(?:有哪些|哪些|哪类|有什么).{{0,18}}{object_pattern}",
        rf"{object_pattern}.{{0,18}}(?:有哪些|哪些|哪类|有什么)",
        rf"(?:找|列|整理|看看|推荐).{{0,12}}(?:一些|几个|一批)?.{{0,12}}{object_pattern}",
        rf"(?:想看|看看|了解|研究).{{0,12}}{object_pattern}.{{0,12}}(?:市场|现状|生态|分类|类型|类别|趋势|方向)",
        rf"{object_pattern}.{{0,12}}(?:市场|现状|生态|分类|类型|类别|趋势|方向)",
        rf"(?:what|which|best|top|latest|popular|trending).{{0,30}}{object_pattern}",
        rf"{object_pattern}.{{0,30}}(?:popular|trending|latest|best|top|list|market overview|overview|landscape|categories?|types?)",
        rf"{object_pattern}.{{0,18}}(?:ideas?|opportunities?)",
        rf"(?:值得做|可以做|能做).{{0,12}}{object_pattern}",
        rf"{object_pattern}.{{0,12}}(?:值得做|可以做|能做)",
        r"(?:有哪些|哪些|哪类|有什么).{0,12}(?:方向|赛道).{0,12}(?:值得|探索|可以|能|做)",
        r"(?:值得|可以|能).{0,8}(?:探索|做).{0,12}(?:方向|赛道)",
        r"(?:方向不明确|找细分方向|找细分机会|机会列表|候选池|产品池|竞品池)",
    ]
    if not has_any(text, candidate_patterns):
        return False
    # These ask to evaluate or optimize a concrete target; keep them on the
    # ordinary evidence chain even if they contain words like “竞品” or “方向”.
    concrete_patterns = [
        r"(?:这个|该|我的|我们|已有|现有|当前).{0,12}(?:产品|功能|方向|工具|网站|站点)",
        r"(?:值不值得|要不要|该不该|能不能).{0,8}(?:做|继续|投入)",
        r"(?:怎么|如何).{0,8}(?:定价|获客|转化|增长|优化|拆解)",
    ]
    if has_any(text, concrete_patterns) and not has_any(text, [r"有哪些|哪些|哪类|有什么|找.*(?:候选|产品|工具|竞品|方向)"]):
        return False
    return True


def extract_candidate_discovery_topic(value: str) -> str:
    text = strip_activation_markers(value)
    compact = re.sub(r"\s+", "", text)
    text_lc = text.lower()
    if re.search(r"AI|artificial intelligence|人工智能", text, re.I):
        has_tool_site = "工具站" in compact or "网站" in compact or "站点" in compact or "website" in text_lc or "site" in text_lc
        has_tool = "工具" in compact or re.search(r"\btools?\b", text_lc)
        has_product = "产品" in compact or "应用" in compact or re.search(r"\b(?:products?|apps?|applications?)\b", text_lc)
        if re.search(r"\bseo\b", text, re.I) or "关键词" in compact or "搜索流量" in compact:
            if has_tool_site:
                return "AI SEO 工具站"
            if has_product:
                return "AI SEO 产品"
            return "AI SEO 工具"
        if "辅助" in compact and "决策" in compact:
            return "辅助决策类 AI 产品"
        if "视频" in compact:
            return "AI 视频站" if "站" in compact or "网站" in compact else "AI 视频产品"
        if "图片" in compact or "图像" in compact or "生图" in compact:
            return "AI 图片产品"
        if has_tool_site and has_product:
            return "AI 产品和工具站"
        if has_tool_site:
            return "AI 工具站"
        if has_tool:
            return "AI 工具"
        if has_product:
            return "AI 产品"
        return "AI 产品"
    popular = extract_popular_tool_topic(text)
    if popular and popular != display_target(text):
        return popular
    topic = extract_generic_topic(text)
    return topic if topic and not is_generic_opportunity_topic(topic) else display_target(text)


def infer_search_strategy(
    value: str,
    query_type: str,
    action_context: str,
    topic: str = "",
) -> Dict[str, str]:
    text = strip_activation_markers(value)
    if action_context == "domain_scan" or (
        action_context in {"new_product_validation", "reference_teardown", "market_watch"}
        and is_generic_ai_tool_topic(topic)
    ):
        return {
            "search_strategy": "candidate_discovery",
            "strategy_source": "rule",
            "strategy_reason": "泛 AI 工具方向确认后，先发现候选池再进入对应分析模式。",
        }
    if query_type == "latest_news":
        return {
            "search_strategy": "normal_evidence",
            "strategy_source": "rule",
            "strategy_reason": "用户在查最新动态，沿用资讯/机会证据链，不额外做候选池发现。",
        }
    if action_context in {"existing_product_conversion", "seo_growth", "choice_decision", "action_review"}:
        return {
            "search_strategy": "normal_evidence",
            "strategy_source": "rule",
            "strategy_reason": "用户目标已指向转化、SEO、方案选择或复盘，沿用单轮证据链。",
        }
    if is_candidate_discovery_query(text):
        return {
            "search_strategy": "candidate_discovery",
            "strategy_source": "rule",
            "strategy_reason": "用户在寻找候选产品、工具、竞品、参考对象或细分方向，需要先发现候选池。",
        }
    return {
        "search_strategy": "normal_evidence",
        "strategy_source": "rule",
        "strategy_reason": "用户已有明确目标或不是候选对象发现问题，沿用单轮证据链。",
    }


def dimension_labels(dimensions: List[str]) -> List[str]:
    label_by_key = {key: label for key, label, _patterns in DIMENSION_RULES}
    return [label_by_key.get(item, item) for item in dimensions]


def report_mode_label(report_mode: str) -> str:
    return REPORT_MODE_LABELS.get(report_mode, report_mode or REPORT_MODE_LABELS["general_mode"])


def infer_report_mode(value: str, query_type: str, action_context: str, dimensions: List[str] | None = None) -> str:
    text = strip_activation_markers(value)
    dimensions = dimensions or []
    if query_type in {"non_applicable", "direct_lookup", "factual_lookup"}:
        return "none"
    generic_topic = extract_candidate_discovery_topic(text) if is_generic_ai_tool_topic(text) else ""
    if action_context in {"new_product_validation", "domain_scan"} and generic_topic:
        return "candidate_mode"
    if query_type != "latest_news" and is_candidate_discovery_query(text) and action_context in {"", "new_product_validation", "domain_scan"}:
        return "candidate_mode"
    if action_context == "choice_decision" or is_ai_media_site_choice_query(text):
        return "choice_mode"
    if query_type == "action_review" or action_context == "action_review":
        return "review_mode"
    if action_context == "market_watch" and is_generic_ai_tool_topic(text):
        return "timing_mode"
    if action_context == "reference_teardown" or has_any(text, [
        r"流程.*借鉴|逻辑.*借鉴|产品流程|产品逻辑|产品路径|用户路径|产品拆解|拆解.*产品|它们.*做法|他们.*做法|创始人.*信号|产品团队.*信号",
    ]):
        return "teardown_mode"
    if has_any(text, [
        r"直接放弃|公开证据.*放弃|功能同质化|头部产品.*吃掉|官方下场|不可替代性|API\s*包一层|暂时归档|不值得我做|开发者兴奋|真实用户无感|过高.*(?:算力|版权|合规|客服)|沉没成本",
    ]):
        return "kill_mode"
    if query_type != "reference_collection" and has_any(text, [
        r"用户在公开社区.*抱怨|反复抱怨|哪些抱怨|情绪发泄|为了这个问题花|用什么词描述|高频低价|低频高价|更便宜.*更快|更快.*更稳|更省心|固定工作流|替代方案是|哪类用户.*新工具|立刻得到什么收益|理想客户|显性需求|隐藏恐惧|笨办法.*真实需求|为什么没有采用现有竞品|使用者|付款者|决策者|安全边界|最好不要服务",
    ]):
        return "pain_mode"
    if query_type == "reference_collection" or has_any(text, [
        r"竞品真正|头部竞品|小竞品|竞品之间|竞品用户|竞品复制|竞品的定价|产品弱但分发强|比竞品强|差异化|一句话定位|价值主张|我的品牌|定位",
    ]):
        return "competitor_mode"
    if action_context == "seo_growth" or "seo_content_structure" in dimensions or has_any(text, [
        r"分发|获客|冷启动|前\s*100\s*个用户|渠道|社区|搜索词|关键词|SEO|内容资产|demo\s*视频|广告预算|社交传播|Product Hunt|小红书|公众号|垂直论坛",
    ]):
        return "distribution_mode"
    if action_context == "existing_product_conversion" or has_any(text, [
        r"商业模式|定价|订阅|按量计费|一次性购买|服务打包|结果付费|工具订阅|免费额度|价格点|付费触发点|不续费|毛利|获客成本|预算来自|企业版|团队版",
    ]):
        return "monetization_mode"
    if has_any(text, [
        r"OPC|SOP|重复事务|客服|交付质量|交付压力|交付成本|交付边界|财务|法务|清单防呆|外包|自动化、延后|客户期望|指标|个人知识库|生病|断网|工具故障|备用机制",
    ]):
        return "operations_mode"
    if "product_experience" in dimensions or has_any(text, [
        r"MVP|最小可验证|最小可用|最危险假设|第一次成功体验|核心闭环|一个页面|一个按钮|账号体系|无登录|付费墙|留存|第一次使用|端到端系统|低代码|现成\s*API",
    ]):
        return "mvp_mode"
    if has_any(text, [
        r"用户痛点|公开社区|反复抱怨|笨办法|用户现在|理想客户|显性需求|隐藏恐惧|使用者|付款者|决策者|固定工作流|替代方案|愿意付费|情绪发泄|花了多少钱|人力|用什么词描述",
    ]):
        return "pain_mode"
    if has_any(text, [
        r"竞品|头部竞品|小竞品|竞品用户|竞品复制|低端|本地化|产品弱但分发强|差异化|定位|价值主张|品牌|真正卖的是什么",
    ]):
        return "competitor_mode"
    if query_type == "latest_news" or action_context == "market_watch" or has_any(text, [
        r"趋势|时机|窗口期|长期驱动力|热度|成本下降|基础设施|太早|刚好|太晚|玩家进入|竞争过热|单一平台政策|政策变化|技术变化|用户行为变化|进入、等待、观察|只收集证据",
    ]):
        return "timing_mode"
    if query_type in {"opportunity_research", "decision_research", "generic_research", "information_pile"}:
        return "opportunity_mode"
    return "general_mode"


def attach_report_mode(route: Dict[str, Any]) -> Dict[str, Any]:
    report_mode = clean_text(route.get("report_mode", "")) or infer_report_mode(
        str(route.get("user_query", "")),
        str(route.get("query_type", "")),
        str(route.get("action_context", "")),
        route.get("research_dimensions", []) if isinstance(route.get("research_dimensions"), list) else [],
    )
    route["report_mode"] = report_mode
    route["report_mode_label"] = report_mode_label(report_mode)
    return attach_search_strategy(route)


def attach_search_strategy(route: Dict[str, Any]) -> Dict[str, Any]:
    provided = clean_text(route.get("search_strategy", ""))
    if provided in SEARCH_STRATEGIES:
        route["search_strategy"] = provided
        route["strategy_source"] = clean_text(route.get("strategy_source", "")) or "external"
        route["strategy_reason"] = clean_text(route.get("strategy_reason", "")) or "外部语义路由提供 search_strategy，经枚举校验后采用。"
        return route
    inferred = infer_search_strategy(
        str(route.get("user_query", "")),
        str(route.get("query_type", "")),
        str(route.get("action_context", "")),
        str(route.get("topic", "")),
    )
    route.update(inferred)
    return route


def infer_action_context(value: str) -> str:
    text = clean_text(value)
    if has_any(text, [r"应该.*做.*还是", r"该.*做.*还是", r"做.*还是.*做", r"还是都做", r"选哪个", r"选择", r"对比.*方案", r"decision", r"choose"]):
        return "choice_decision"
    if has_any(text, [r"找.*新流量", r"获取.*流量", r"拿.*流量", r"流量入口", r"页面矩阵", r"做.*SEO", r"SEO.*机会", r"SEO.*流量", r"关键词.*机会", r"内容机会", r"早期用户|前\s*100\s*个用户|100\s*个早期用户|从哪里获得|哪里获得|哪里拿到|从哪.*用户|冷启动|获客渠道"]):
        return "seo_growth"
    if has_any(text, [r"借鉴|参考|对标|拆解|产品流程|产品逻辑|流程与逻辑|用户路径|产品路径|做法|创始人.*信号|产品团队.*信号"]):
        return "reference_teardown"
    if has_any(text, [
        r"(?:我有|已有|现有|我的|我们|当前).*(?:转化|续费|复购|会员|定价|体验|参考竞品|竞品)",
        r"已有",
        r"现有",
        r"我的产品",
        r"我们产品",
        r"当前产品",
        r"优化.*转化",
        r"注册.*转化",
        r"试用.*转化",
        r"付费转化",
        r"续费.*转化",
        r"trial",
        r"conversion",
    ]):
        return "existing_product_conversion"
    if has_any(text, [r"竞品观察", r"行业观察", r"市场观察", r"竞品/行业风险", r"行业风险", r"市场风险", r"只.*观察", r"只.*了解", r"不急", r"资讯速览", r"新闻汇总", r"market watch"]):
        return "market_watch"
    if has_any(text, [r"从\s*0", r"新产品", r"新工具", r"新网站", r"新品类", r"新品开发", r"创业机会", r"B2B\s*机会", r"工具站", r"MVP", r"可产品化", r"产品化.*机会", r"我想.*(?:做|开|开发|推出|上线|找.*机会)", r"要不要做", r"能不能做", r"值不值得", r"有没有.*机会", r"是否有.*机会", r"开发", r"上线", r"build"]):
        return "new_product_validation"
    if is_candidate_discovery_query(text) and has_candidate_action_purpose(text):
        return "new_product_validation"
    if has_any(text, [r"选哪个", r"选择", r"对比.*方案", r"decision", r"choose"]):
        return "choice_decision"
    if has_any(text, [r"复盘", r"要不要继续", r"停止", r"转向", r"继续投入"]):
        return "action_review"
    return ""


def has_explicit_action_purpose(value: str) -> bool:
    return has_any(value, [
        r"要不要|值不值得|能不能|该不该",
        r"我想.*(?:做|开发|上线|推出)|准备.*(?:做|开发|上线|推出)",
        r"可以做|能做|值得做|低成本验证|按.*能力",
        r"做.*SEO|SEO.*机会|关键词|搜索流量|页面机会",
        r"竞品|参考|对标|借鉴",
        r"商业化|付费|定价|转化|变现",
    ])


def broad_ai_tools_action_options(topic: str) -> List[Dict[str, str]]:
    return [
        {
            "id": "new_product_validation",
            "label": "按你的能力筛可做方向",
            "description": "适合独立开发、建站、SEO、轻开发，重点找能低成本验证的工具站/小产品。",
        },
        {
            "id": "domain_scan",
            "label": "按具体领域看工具",
            "description": "例如内容 SEO、营销销售、图片视频、办公文档、开发建站、教育学习、自动化工作流。",
        },
        {
            "id": "reference_teardown",
            "label": "按竞品/流程参考",
            "description": "找做得好的 AI 工具，拆首页、功能、定价、新用户流程和增长方式。",
        },
        {
            "id": "market_watch",
            "label": "按市场速览",
            "description": "只想知道现在 AI 工具有哪些类型、哪些比较火，不急着做产品判断。",
        },
    ]


def action_options_for(query_type: str, topic: str, dimensions: List[str] | None = None) -> List[Dict[str, str]]:
    dimensions = dimensions or []
    if is_generic_ai_tool_topic(topic):
        return broad_ai_tools_action_options(topic)
    if query_type == "reference_collection":
        return [
            {
                "id": "reference_teardown",
                "label": f"拆解 {topic} 的产品流程与做法",
                "description": "查真实产品、创始人/产品团队信号、用户路径、输出形态和可借鉴流程。",
            },
            {
                "id": "new_product_validation",
                "label": f"判断要不要从 0 做 {topic}",
                "description": "查市场空白、竞品密度、成本/API、MVP 切口和商业化空间。",
            },
            {
                "id": "existing_product_conversion",
                "label": "优化已有产品的注册、试用或付费转化",
                "description": "查首页、定价页、免费额度、升级触发点和转化路径。",
            },
            {
                "id": "seo_growth",
                "label": "找 SEO 新流量入口和页面机会",
                "description": "查关键词、页面类型、SERP 竞争、对比页/榜单页和内链结构。",
            },
            {
                "id": "market_watch",
                "label": "只做竞品/行业观察",
                "description": "查头部玩家、定位差异、商业模式和市场变化，不急着行动。",
            },
        ]
    if query_type == "latest_news":
        return [
            {
                "id": "new_product_validation",
                "label": "找可产品化的新机会",
                "description": "查新 API、新模型、新能力能否变成工具站、产品或小实验。",
            },
            {
                "id": "seo_growth",
                "label": "找 SEO/内容选题机会",
                "description": "查能否做教程、对比、替代品、榜单页或专题页。",
            },
            {
                "id": "market_watch",
                "label": "看竞品/行业风险和变化",
                "description": "查平台、竞品、融资、合作、政策或生态变化。",
            },
            {
                "id": "news_brief",
                "label": "只要资讯速览",
                "description": "只筛最近重要新闻，不做行动优先级判断。",
            },
        ]
    return [
        {
            "id": "new_product_validation",
            "label": "判断是否值得做产品或工具站",
            "description": "查能力、成本、竞品、用户痛点和变现入口。",
        },
        {
            "id": "seo_growth",
            "label": "判断是否有 SEO/内容机会",
            "description": "查关键词、页面类型、搜索意图和 SERP 竞争。",
        },
        {
            "id": "market_watch",
            "label": "判断竞品/行业变化是否影响方向",
            "description": "查竞品、市场、平台和生态变化。",
        },
        {
            "id": "news_brief",
            "label": "只做资料速览",
            "description": "只整理重要公开信息，不输出强行动建议。",
        },
    ]


def action_context_label(action_context: str) -> str:
    labels = {
        "new_product_validation": "新产品/工具站验证",
        "domain_scan": "具体领域工具扫描",
        "existing_product_conversion": "已有产品转化优化",
        "seo_growth": "SEO/新流量增长",
        "market_watch": "竞品/行业观察",
        "reference_teardown": "参考产品流程/逻辑拆解",
        "news_brief": "资讯速览",
        "choice_decision": "方案选择",
        "action_review": "行动复盘",
    }
    return labels.get(action_context, action_context or "未明确行动目的")


def confirmed_intent_type(query_type: str, action_context: str, dimensions: List[str]) -> str:
    dimension_set = set(dimensions)
    if query_type == "latest_news":
        if action_context == "new_product_validation":
            return "tool_or_product_opportunity"
        if action_context == "seo_growth":
            return "seo_or_content_opportunity"
        if action_context == "market_watch":
            return "competitor_or_market_signal"
        if action_context == "news_brief":
            return "news_brief"
    if query_type == "reference_collection":
        if action_context == "reference_teardown":
            return "reference_product_experience"
        if len(dimension_set) > 1:
            return "reference_multi_dimension"
        if "product_experience" in dimension_set:
            return "reference_product_experience"
        if "business_model" in dimension_set:
            return "reference_business_model"
        if "seo_content_structure" in dimension_set or action_context == "seo_growth":
            return "reference_seo_content_structure"
        if "feature_capability" in dimension_set:
            return "reference_model_function_capability"
        if action_context in {"new_product_validation", "existing_product_conversion", "market_watch"}:
            return "reference_multi_dimension"
    return "other"


def build_confirmation_question(route: Dict[str, Any]) -> str:
    topic = route.get("topic") or display_target(route.get("user_query", ""))
    if route.get("confirmation_variant") == "broad_ai_tools" or is_generic_ai_tool_topic(topic):
        return broad_ai_tools_confirmation_question()
    dimensions = dimension_labels(route.get("research_dimensions", []))
    dimension_text = f"，你已经提到的研究维度是：{' + '.join(dimensions)}" if dimensions else ""
    options = route.get("action_options") or action_options_for(route.get("query_type", "generic_research"), topic, route.get("research_dimensions", []))
    lines = [
        "INFO_ALCHEMIST=TRUE",
        "",
        f"我识别到你要查的是：{topic}{dimension_text}。",
        "但还需要确认这些信息要改变哪类行动，否则搜索计划会混在一起。",
        "",
        "你主要是为了哪类行动？",
        "",
    ]
    for index, option in enumerate(options, start=1):
        lines.extend([
            f"## {index}. {option['label']}",
            option.get("description", ""),
            "",
        ])
    lines.append("你也可以直接用一句话说明真实目的；如果还不清楚，我会最多继续追问 3 轮。")
    return "\n".join(lines).strip()


def broad_ai_tools_confirmation_question() -> str:
    return (
        "INFO_ALCHEMIST=TRUE\n\n"
        "“AI 工具”范围太大，我先帮你聚焦一下调研的方向，让报告结果更能帮到你。\n\n"
        "你这次更想看哪种方向？\n\n"
        "## 1. 按你的能力筛可做方向\n"
        "适合独立开发、建站、SEO、轻开发，重点找能低成本验证的工具站/小产品。你也可以补充自己的能力、资源或优势。\n\n"
        "## 2. 按具体领域看工具\n"
        "例如内容 SEO、营销销售、图片视频、办公文档、开发建站、教育学习、自动化工作流。你可以直接说一个领域。\n\n"
        "## 3. 按竞品/流程参考\n"
        "找做得好的 AI 工具，拆首页、功能、定价、新用户流程和增长方式。\n\n"
        "## 4. 按市场速览\n"
        "只想知道现在 AI 工具有哪些类型、哪些比较火，不急着做产品判断。\n\n"
        "你可以直接回复：1 + 你的能力/资源、2 + 领域、3 + 想拆的维度，或 4。\n"
        "如果还没想好，我会默认按「1：独立开发 + 建站/SEO/轻开发 + 低成本验证」来筛。"
    )


def normalize_external_route(data: Dict[str, Any], user_query: str) -> Dict[str, Any] | None:
    raw = data.get("semantic_intent") or data.get("semantic_route")
    if not isinstance(raw, dict) and isinstance(data.get("ai_intent"), dict) and data["ai_intent"].get("query_type"):
        raw = data.get("ai_intent")
    if not isinstance(raw, dict):
        return None
    query_type = str(raw.get("query_type", "")).strip()
    if query_type not in QUERY_TYPES:
        return None
    topic = strip_activation_markers(raw.get("topic") or extract_generic_topic(user_query))
    dimensions = [item for item in raw.get("research_dimensions", []) if isinstance(item, str)]
    action_context = clean_text(raw.get("action_context", ""))
    clarity = str(raw.get("decision_clarity", "")).strip()
    if clarity not in DECISION_CLARITIES:
        clarity = "clear" if action_context else ("partial" if dimensions else "unclear")
    route = {
        "route_source": "external_semantic",
        "user_query": user_query,
        "query_type": query_type,
        "topic": topic,
        "research_dimensions": unique(dimensions),
        "action_context": action_context,
        "decision_clarity": clarity,
        "needs_confirmation": bool(raw.get("needs_confirmation", clarity != "clear")),
        "confirmation_round": int(raw.get("confirmation_round", 0) or 0),
        "max_confirmation_rounds": MAX_CONFIRMATION_ROUNDS,
        "reason": clean_text(raw.get("reason", "")),
    }
    route["action_options"] = raw.get("action_options") if isinstance(raw.get("action_options"), list) else action_options_for(query_type, topic, route["research_dimensions"])
    route["confirmed_intent_type"] = raw.get("confirmed_intent_type") or confirmed_intent_type(query_type, action_context, route["research_dimensions"])
    route["confirmed_intent"] = raw.get("confirmed_intent") or compose_confirmed_intent(route)
    route["report_mode"] = raw.get("report_mode") or infer_report_mode(user_query, query_type, action_context, route["research_dimensions"])
    route["report_mode_label"] = raw.get("report_mode_label") or report_mode_label(route["report_mode"])
    if route["needs_confirmation"]:
        route["confirmation_question"] = raw.get("confirmation_question") or build_confirmation_question(route)
    return route


def compose_confirmed_intent(route: Dict[str, Any]) -> str:
    parts = []
    action = action_context_label(route.get("action_context", ""))
    if action:
        parts.append(action)
    labels = dimension_labels(route.get("research_dimensions", []))
    if labels:
        parts.append("研究维度：" + " + ".join(labels))
    return "；".join(parts)


DOMAIN_FOCUS_RULES = [
    ("内容 SEO", [r"内容\s*SEO|SEO|关键词|内容(?:生产|工作流|营销)?"]),
    ("营销销售", [r"营销|销售|外联|获客|广告|增长|CRM|邮件"]),
    ("图片视频", [r"图片|图像|生图|视频|剪辑|短视频|设计|素材"]),
    ("办公文档", [r"办公|文档|会议|纪要|表格|PPT|幻灯|知识库|PDF"]),
    ("开发建站", [r"开发|代码|编程|建站|网站|前端|后端|App|应用"]),
    ("教育学习", [r"教育|学习|课程|老师|学生|考试|培训"]),
    ("自动化工作流", [r"自动化|工作流|流程|SOP|agent|数字员工"]),
]


def extract_domain_focus(value: str) -> str:
    text = clean_text(value)
    explicit = re.search(r"(?:^|[，,。；;\s])2\s*[+＋]\s*(?P<focus>[^，,。；;]+)", text, re.I)
    if explicit:
        focus = clean_text(explicit.group("focus"))
        focus = re.sub(r"^(?:领域|方向|看|想看)\s*", "", focus).strip()
        if focus:
            return focus
    for label, patterns in DOMAIN_FOCUS_RULES:
        if has_any(text, patterns):
            return label
    return ""


def narrowed_ai_tool_topic(base_topic: str, reply: str) -> str:
    focus = extract_domain_focus(reply)
    if not focus:
        return base_topic
    compact = re.sub(r"\s+", "", focus).lower()
    if compact.endswith(("ai工具", "ai产品", "ai工具站")):
        return focus
    return f"{focus} AI 工具"


def route_query(user_query: str, data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = data or {}
    text = strip_activation_markers(user_query)
    external = normalize_external_route(data, text)
    if external:
        return external

    if not text:
        return attach_report_mode({
            "route_source": "fallback_semantic",
            "user_query": text,
            "query_type": "non_applicable",
            "topic": "",
            "research_dimensions": [],
            "action_context": "",
            "decision_clarity": "clear",
            "needs_confirmation": False,
            "trigger_level": "none",
            "reason": "输入为空。",
        })

    if is_evaluation_question(text):
        owned_topic = extract_owned_product_topic(text)
        topic = extract_context_topic(text) or (owned_topic if is_valid_context_topic(owned_topic) else "")
        action_context = infer_evaluation_action_context(text)
        if not topic and has_any(text, [r"值不值得做|要不要做|该不该做|能不能做|有没有.*机会|是否有.*机会"]):
            generic_topic = extract_generic_topic(text)
            if (
                generic_topic
                and not is_generic_opportunity_topic(generic_topic)
                and is_valid_context_topic(generic_topic)
                and not has_any(text, [r"^(哪些|哪个|哪类|当前市场|这个方向|这个机会|这个产品|我的产品|用户|竞品|作为\s*OPC)"])
            ):
                topic = generic_topic
        dimensions = extract_dimensions(text)
        query_type = "action_review" if action_context == "action_review" else "opportunity_research"
        needs_confirmation = not topic
        clarity = "unclear" if needs_confirmation else "clear"
        trigger_level = "clarify" if needs_confirmation else ("review" if action_context == "action_review" else "full")
        route = {
            "route_source": "fallback_semantic",
            "user_query": text,
            "query_type": query_type,
            "topic": topic or display_target(text),
            "research_dimensions": dimensions,
            "action_context": "" if needs_confirmation else action_context,
            "decision_clarity": clarity,
            "needs_confirmation": needs_confirmation,
            "trigger_level": trigger_level,
            "confirmation_round": int(data.get("confirmation_round", 0) or 0),
            "max_confirmation_rounds": MAX_CONFIRMATION_ROUNDS,
            "reason": "上下文依赖的机会判断问题需要先确认具体方向。" if needs_confirmation else "识别为机会/复盘判断问题，并提取具体方向后进入研究链路。",
        }
        route["action_options"] = action_options_for(query_type, route["topic"], dimensions)
        route["confirmed_intent_type"] = confirmed_intent_type(query_type, route["action_context"], dimensions)
        route["confirmed_intent"] = compose_confirmed_intent(route)
        attach_report_mode(route)
        if needs_confirmation:
            route["confirmation_question"] = build_confirmation_question(route)
        return route

    if has_any(text, [r"翻译", r"润色", r"改写", r"polish", r"translate", r"rewrite"]):
        query_type = "non_applicable"
        topic = display_target(text)
    elif has_any(text, [r"天气", r"汇率", r"几点", r"现在时间", r"今天日期", r"股价", r"weather", r"exchange rate"]):
        query_type = "direct_lookup"
        topic = display_target(text)
    elif has_any(text, [r"这周看到", r"信息.*都重要", r"不知道哪些该做", r"一堆", r"很多条", r"information pile"]):
        query_type = "information_pile"
        topic = display_target(text)
    elif is_reference_collection_query(text):
        query_type = "reference_collection"
        topic = extract_reference_topic(text) or display_target(text)
    elif is_popular_tool_collection_query(text):
        query_type = "reference_collection"
        topic = extract_popular_tool_topic(text)
    elif is_latest_news_query(text):
        query_type = "latest_news"
        topic = extract_news_topic(text)
    elif is_candidate_discovery_query(text):
        query_type = "opportunity_research"
        topic = extract_candidate_discovery_topic(text)
    elif has_any(text, [r"有没有.*机会", r"是否有.*机会", r"还有没有.*机会", r"机会", r"值不值得", r"要不要做", r"应该.*做", r"该不该.*做", r"做.*还是.*做", r"能不能做", r"商业化", r"我想.*(?:做|开|开发|推出|上线)", r"opportunit", r"worth", r"should I build"]):
        query_type = "opportunity_research"
        topic = extract_generic_topic(text)
    elif has_any(text, [r"决定", r"选哪个", r"是否", r"该不该", r"还是都做", r"decision", r"choose"]):
        query_type = "decision_research"
        topic = extract_generic_topic(text)
    elif has_any(text, [r"是什么", r"谁是", r"什么时候", r"多少钱", r"怎么用", r"what is", r"who is", r"when", r"how to"]):
        query_type = "factual_lookup"
        topic = display_target(text)
    elif has_any(text, [r"帮我查", r"查询", r"查一下", r"查查", r"研究一下", r"研究", r"了解一下", r"search", r"research"]):
        query_type = "curiosity"
        topic = display_target(text)
    else:
        query_type = "non_applicable"
        topic = display_target(text)

    if is_ai_media_site_choice_query(text):
        topic = "AI 视频站 vs AI 图片站"

    dimensions = extract_dimensions(text)
    action_context = infer_action_context(text)
    if query_type == "reference_collection" and is_popular_tool_collection_query(text) and not has_explicit_action_purpose(text):
        action_context = ""
    if query_type in {"non_applicable", "curiosity"} and action_context:
        query_type = "generic_research"
        topic = extract_owned_product_topic(text) or extract_generic_topic(text)
    if query_type == "non_applicable" and is_generic_ai_tool_topic(topic):
        query_type = "generic_research"
    broad_opportunity_needs_scope = should_confirm_broad_opportunity(text, topic, query_type)
    broad_ai_tools_needs_scope = should_confirm_broad_ai_tool_scope(text, topic, query_type, action_context)
    if broad_opportunity_needs_scope:
        action_context = ""
    if broad_ai_tools_needs_scope:
        action_context = ""

    if query_type in {"non_applicable", "direct_lookup", "factual_lookup"}:
        clarity = "clear"
        needs_confirmation = False
        trigger_level = "none" if query_type == "non_applicable" else ("direct" if query_type == "direct_lookup" else "light")
    elif query_type in {"opportunity_research", "decision_research", "information_pile", "action_review"}:
        if broad_opportunity_needs_scope or broad_ai_tools_needs_scope:
            clarity = "unclear"
            needs_confirmation = True
            trigger_level = "clarify"
        else:
            clarity = "clear" if action_context or query_type in {"opportunity_research", "decision_research", "information_pile", "action_review"} else "partial"
            needs_confirmation = False
            trigger_level = "full" if query_type != "action_review" else "review"
    elif query_type in {"reference_collection", "latest_news"}:
        clarity = "clear" if action_context else ("partial" if dimensions else "unclear")
        needs_confirmation = clarity != "clear"
        trigger_level = "clarify" if needs_confirmation else "full"
    else:
        clarity = "clear" if action_context else ("partial" if dimensions else "unclear")
        needs_confirmation = clarity != "clear"
        trigger_level = "clarify" if needs_confirmation else "full"

    route = {
        "route_source": "fallback_semantic",
        "user_query": text,
        "query_type": query_type,
        "topic": topic,
        "research_dimensions": dimensions,
        "action_context": action_context,
        "decision_clarity": clarity,
        "needs_confirmation": needs_confirmation,
        "trigger_level": trigger_level,
        "confirmation_round": int(data.get("confirmation_round", 0) or 0),
        "max_confirmation_rounds": MAX_CONFIRMATION_ROUNDS,
        "reason": "泛 AI 工具问题需要先确认用途和方向。" if broad_ai_tools_needs_scope else ("泛产品机会问题需要先确认行动范围。" if broad_opportunity_needs_scope else "本地语义兜底根据查询类型、研究维度和行动目的生成路由。"),
    }
    if broad_ai_tools_needs_scope:
        route["confirmation_variant"] = "broad_ai_tools"
    route["action_options"] = action_options_for(query_type, topic, dimensions)
    route["confirmed_intent_type"] = confirmed_intent_type(query_type, action_context, dimensions)
    route["confirmed_intent"] = compose_confirmed_intent(route)
    attach_report_mode(route)
    if needs_confirmation:
        route["confirmation_question"] = build_confirmation_question(route)
    return route


def selected_option_ids(reply: str, options: List[Dict[str, str]]) -> List[str]:
    text = clean_text(reply)
    selected = []
    for match in re.finditer(r"(?<!\d)(\d+)(?!\d)", text):
        index = int(match.group(1))
        if 1 <= index <= len(options):
            selected.append(options[index - 1]["id"])
    lowered = text.lower()
    natural_rules = [
        ("reference_teardown", [r"借鉴", r"参考", r"对标", r"拆解", r"流程", r"逻辑", r"产品路径", r"用户路径", r"产品设计", r"做法", r"创始人.*信号", r"产品团队.*信号"]),
        ("new_product_validation", [r"从\s*0", r"新产品", r"新工具", r"工具站", r"MVP", r"产品验证", r"要不要做", r"值不值得", r"开发", r"上线", r"build"]),
        ("domain_scan", [r"具体领域|领域|内容\s*SEO|营销销售|图片视频|办公文档|开发建站|教育学习|自动化工作流|图片|视频|文档|会议|代码|编程"]),
        ("existing_product_conversion", [r"已有", r"现有", r"我的产品", r"优化", r"注册", r"试用", r"付费转化", r"转化", r"conversion"]),
        ("seo_growth", [r"新流量", r"流量入口", r"页面机会", r"页面矩阵", r"做.*SEO", r"SEO.*机会", r"SEO.*流量", r"关键词.*机会", r"SERP.*机会"]),
        ("market_watch", [r"竞品", r"行业观察", r"市场观察", r"只.*观察", r"只.*了解", r"不急"]),
        ("news_brief", [r"资讯速览", r"新闻汇总", r"重要新闻", r"brief"]),
    ]
    allowed = {option["id"] for option in options}
    for action_id, patterns in natural_rules:
        if action_id in allowed and any(re.search(pattern, text, re.I) for pattern in patterns):
            selected.append(action_id)
    return unique(selected)


def resolve_reply(previous_query: str, reply: str, data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = data or {}
    base = route_query(previous_query, data)
    options = base.get("action_options") or action_options_for(base.get("query_type", "generic_research"), base.get("topic", ""), base.get("research_dimensions", []))
    selected = selected_option_ids(reply, options)
    reply_dimensions = extract_dimensions(reply)
    dimensions = unique([*(base.get("research_dimensions") or []), *reply_dimensions])
    if "seo_growth" in selected:
        dimensions = unique([*dimensions, "seo_content_structure"])
    if "existing_product_conversion" in selected:
        dimensions = unique([*dimensions, "product_experience", "business_model"])
    if "reference_teardown" in selected:
        dimensions = unique([*dimensions, "product_experience", "feature_capability"])
    action_context = selected[0] if selected else infer_action_context(reply)
    topic = base.get("topic", "")
    if action_context == "domain_scan" and is_generic_ai_tool_topic(topic):
        topic = narrowed_ai_tool_topic(topic, reply)
    round_index = int(data.get("confirmation_round", base.get("confirmation_round", 0)) or 0) + 1
    max_rounds = int(data.get("max_confirmation_rounds", MAX_CONFIRMATION_ROUNDS) or MAX_CONFIRMATION_ROUNDS)

    if not action_context and round_index >= max_rounds:
        action_context = "market_watch"
        forced = True
    else:
        forced = False

    missing_domain_focus = action_context == "domain_scan" and is_generic_ai_tool_topic(topic)
    clarity = "clear" if action_context and not missing_domain_focus else ("partial" if dimensions or action_context else "unclear")
    needs_confirmation = clarity != "clear"
    route = {
        **base,
        "route_source": "reply_semantic",
        "user_reply": reply,
        "selected_action_options": selected,
        "topic": topic,
        "research_dimensions": dimensions,
        "action_context": action_context,
        "decision_clarity": clarity,
        "needs_confirmation": needs_confirmation,
        "confirmation_round": round_index,
        "max_confirmation_rounds": max_rounds,
        "forced_after_max_confirmation": forced,
        "reason": "解析用户对意图确认问题的回复，合并原始查询主题、研究维度和行动目的。",
    }
    ctype = confirmed_intent_type(route.get("query_type", ""), action_context, dimensions)
    if route.get("query_type") == "reference_collection" and len(selected) > 1:
        ctype = "reference_multi_dimension"
    route["confirmed_intent_type"] = ctype
    route["confirmed_intent"] = compose_confirmed_intent(route)
    route["trigger_level"] = "full" if not needs_confirmation else "clarify"
    route.pop("report_mode", None)
    route.pop("report_mode_label", None)
    route.pop("search_strategy", None)
    route.pop("strategy_source", None)
    route.pop("strategy_reason", None)
    attach_report_mode(route)
    if needs_confirmation:
        route["confirmation_question"] = build_confirmation_question(route)
    else:
        route.pop("confirmation_question", None)
    return route


def read_input() -> Dict[str, Any]:
    raw = sys.stdin.read().strip()
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"user_query": raw}
        if isinstance(parsed, dict):
            return parsed
        return {"user_query": raw}
    if len(sys.argv) > 1:
        return {"user_query": " ".join(sys.argv[1:])}
    return {}


def main() -> int:
    data = read_input()
    if data.get("reply") or data.get("user_reply"):
        output = resolve_reply(
            str(data.get("previous_query") or data.get("original_query") or data.get("user_query", "")),
            str(data.get("reply") or data.get("user_reply") or ""),
            data,
        )
    else:
        output = route_query(str(data.get("user_query", "")), data)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
