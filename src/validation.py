"""一致性验证：我方评分 vs 人工标注三档 ground truth。

输出命中率 + Spearman 排序相关，写 validation.json，供报告如实引用偏差。
"""

import json
from .ground_truth import GROUND_TRUTH, TIER_RANK, tier_from_usefulness


def _avg_ranks(values):
    """对列表计算秩（含并列，用平均秩）。values 原序。"""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # 平均秩（1-based）
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x, y):
    """手写 Spearman 秩相关（含 tie 平均秩）。"""
    n = len(x)
    if n < 2:
        return 0.0
    rx, ry = _avg_ranks(x), _avg_ranks(y)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def validate(result: dict) -> dict:
    """result 为 scorer.run 的输出。返回验证指标 dict。"""
    rows = []
    for r in result["cases"]:
        uid = r["id"]
        predicted = tier_from_usefulness(r["usefulness"])
        truth = GROUND_TRUTH[uid]
        rows.append(
            {
                "id": uid,
                "predicted_tier": predicted,
                "truth_tier": truth,
                "hit": predicted == truth,
                "truth_rank": TIER_RANK[truth],
                "usefulness": r["usefulness"],
            }
        )

    hits = [r["hit"] for r in rows]
    accuracy = sum(hits) / len(hits)

    # 一致性矩阵
    matrix = {}
    for tier in sorted(set(TIER_RANK), key=TIER_RANK.get, reverse=True):
        matrix[tier] = {}
        for t2 in sorted(set(TIER_RANK), key=TIER_RANK.get, reverse=True):
            matrix[tier][t2] = sum(
                1 for r in rows if r["predicted_tier"] == tier and r["truth_tier"] == t2
            )

    rho = spearman([r["usefulness"] for r in rows], [r["truth_rank"] for r in rows])

    validation = {
        "n": len(rows),
        "tier_accuracy": round(accuracy, 3),
        "spearman_usefulness_vs_truth": round(rho, 3),
        "matrix": matrix,
        "rows": rows,
    }
    return validation