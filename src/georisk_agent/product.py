from __future__ import annotations

SPEC = {'id': 'georisk-agent',
 'name': '地缘政治风险监测预警智能体',
 'port': 8711,
 'accent': '#226752',
 'tagline': '研究国际问题，跟踪事件与不同立场，也关注与你相关的利益和风险。',
 'system': 'Write a geopolitical research brief for the supplied question. Use the provided public sources. '
           'Cite read evidence, state uncertainty and keep proposed actions separate from facts. Focus on '
           'what changed, the actors and explanations relevant to the research question, and what observable developments would '
           'change the assessment. Keep event severity, evidence strength and business relevance distinct.',
 'starter': {'question': '设备出口团队关注越南与印度尼西亚的交付安排。现有资料提到哪些物流或政策变化？哪些可能影响交付，下一步应核查什么？',
             'countries': ['Vietnam', 'Indonesia'],
             'topics': ['trade', 'investment', 'logistics'],
             'context': '虚构演示：设备出口团队正在收集公开资料。',
             'max_steps': 12,
             'deadline_seconds': 180},
 'demo_summary': '规则演示已整理导入的虚构资料，并保留来源与日期。',
 'demo_assessment': '这是虚构资料的规则演示。请检查来源及适用范围，补充资料后再形成实际业务判断。',
 'demo_actions': ['查看各项资料的来源与日期。', '补充与本次问题相关的资料。'],
 'demo_follow': ['下次运行时比较资料是否有更新。']}


SPEC['system'] += ' Read the relevant saved sources before deciding a conclusion; a failed or unavailable tool is not evidence. When public search queries are absent, use local evidence instead of trying to search. Compare changes with the previous assessment when available, and discuss exposure only when the user supplies it. Research and reporting tasks do not require business context.'


def demo_report(mission, evidence, previous):
    ids = [e["id"] for e in evidence]
    return {
        "title": SPEC["name"] + " · " + ("虚构情景演示" if evidence else "证据缺口说明"),
        "summary": SPEC["demo_summary"] if evidence else "任务范围内没有可用证据。请导入资料或注册信息源后再开展研究。",
        "findings": [{"claim": e["title"] + "：" + e["body"], "evidence_ids": [e["id"]]} for e in evidence],
        "assessment": SPEC["demo_assessment"] if evidence else "没有证据支持事实判断、选国排名或预警升级。",
        "priority": "watch" if evidence else "routine",
        "actions": SPEC["demo_actions"] if evidence else ["导入与任务国区、主题相符的证据包。"],
        "uncertainties": ["此运行由确定性规则生成，未调用大模型。", "资料是虚构演练数据，没有覆盖真实环境。"] if evidence else ["当前证据缺失。"],
        "follow_up": SPEC["demo_follow"] + (["已找到同一任务的历史报告；本轮保留独立版本。"] if previous else []),
        "evidence_ids": ids,
    }


SPEC["demo_report"] = demo_report

SPEC["system"] += " For an exposure with no supported connection to the event, recommend normal operating procedures unless separate evidence indicates a change. Missing information about an unrelated country or transport mode alone is not a reason to delay travel, halt work or impose additional emergency measures."
