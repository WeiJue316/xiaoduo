"""judge 提示词构建：把 case 交给 LLM，让它按 rubrics 打分。"""

from .metrics import RUBRICS, METRICS


def build_messages(user_question: str, auto_reply: str):
    """构造发给 judge 的系统 + 用户消息。

    returns: (system_prompt, user_prompt)
    """
    system = (
        "你是一名严格的在线客服回复质量评审。你的任务是对一条【自动客服回复】"
        "针对【用户问题】的适配程度打分。\n\n"
        "你对三个维度分别打 0-5 分，分数允许半整数（0, 0.5, 1, ..., 5）。\n\n"
        "维度定义：\n"
        "1. usefulness 主动协助度：回复是否真的帮用户解决了问题，是否主动帮忙查证/代办，"
        "而不是把责任、判断或操作压力推回给用户。'正确但没用'的回复（用户问具体问题，"
        "回复却叫用户自己去查）在此维度应得低分。\n"
        "2. accuracy 准确性/不瞎编：事实是否正确，是否命中用户问题的核心，"
        "有没有臆造信息或答非所问。\n"
        "3. tone 语气/同理心：在用户流露情绪（焦急/生气/害怕/抱怨）时，"
        "回复是否有足够到位、诚恳的安抚与共情。\n\n"
        "各维度详细评分锚点：\n"
        f"{_format_rubrics()}\n\n"
        "判定要求：只针对你看到的那一条回复评分，不得臆造用户问题之外的信息。"
        "先在心里给出理由，再决定分数。"
    )

    user = (
        "【用户问题】\n{user}\n\n【自动客服回复】\n{reply}\n\n"
        '请严格输出一段合法 JSON（不要输出任何解释文字，不要用 markdown 代码块），格式为：\n'
        '{{"usefulness": <0-5半整数>, "accuracy": <0-5半整数>, '
        '"tone": <0-5半整数>, "reason": "<一句话点出主要扣分点>"}}'
    ).format(user=user_question, reply=auto_reply)

    return system, user


def _format_rubrics() -> str:
    lines = []
    for metric in ("usefulness", "accuracy", "tone"):
        name = METRICS[metric]
        lines.append(f"- {name}：")
        for score in (5, 4, 3, 2, 1, 0):
            desc = RUBRICS[metric][score]
            lines.append(f"    {score} 分：{desc}")
    return "\n".join(lines)