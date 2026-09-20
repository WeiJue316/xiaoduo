"""人工标注的三档 ground truth —— 仅用于事后验证，不参与评分。

将 human_ref.json 的 annotator_notes 编码成三个业务档位，作为一致性验证的基准。
评分器（judge / mock）**不 import 本模块**，保证验证不泄露到推理过程。

档位定义：
- 主动解决：回复主动帮忙办，或给出了充分且可直接行动的路径（用户基本不需要新操作）。
- 正确但没帮上：给了规则/信息，但把查证或操作责任交回用户（"正确但没用"）。
- 差：答非所问 / 把判断推回用户且无实质协助 / 忽略了用户核心诉求。
"""

# 档位到数值（用于排序相关）
TIER_RANK = {"主动解决": 3, "正确但没帮上": 2, "差": 1}

# 20 条编码结果（依据 annotator_notes 的人工解读）
GROUND_TRUTH = {
    "case_01": "正确但没帮上",
    "case_02": "正确但没帮上",
    "case_03": "正确但没帮上",
    "case_04": "正确但没帮上",
    "case_05": "差",
    "case_06": "正确但没帮上",
    "case_07": "正确但没帮上",
    "case_08": "正确但没帮上",
    "case_09": "正确但没帮上",
    "case_10": "主动解决",
    "case_11": "正确但没帮上",
    "case_12": "正确但没帮上",
    "case_13": "正确但没帮上",
    "case_14": "主动解决",
    "case_15": "主动解决",
    "case_16": "正确但没帮上",
    "case_17": "正确但没帮上",
    "case_18": "主动解决",
    "case_19": "正确但没帮上",
    "case_20": "差",
}

# usefulness 分 -> 三档 的映射阈值（核心指标驱动，固定值）
# 主动解决 >= USE_SOLVE ；正确但没帮上 >= USE_PASSABLE-；差 <前者
USE_SOLVE = 4.0
USE_TIERS = [(4.0, "主动解决"), (2.5, "正确但没帮上"), (0.0, "差")]


def tier_from_usefulness(usefulness: float) -> str:
    """按 usefulness 档位阈值映射（核心指标驱动）。"""
    for threshold, tier in USE_TIERS:
        if usefulness >= threshold:
            return tier
    return "差"