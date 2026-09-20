"""评分编排：对 20 条逐条评分，聚合成整体分，落盘可追溯。"""

import datetime as _dt
import json
from .metrics import overall


def _load_cases(attachments_dir):
    with open(f"{attachments_dir}/task3_auto_replies.json", encoding="utf-8") as f:
        return json.load(f)


def run(client, attachments_dir: str, out_path: str, label: str = "") -> dict:
    """对全部 case 评分并写 scored_cases.json，返回 run 结果 dict。"""
    cases = _load_cases(attachments_dir)
    item_list = []
    for case in cases:
        try:
            scores = client.judge_single(case)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"{case['id']} 评分失败: {e}") from e
        scores["overall"] = overall(scores)
        item_list.append(
            {
                "id": case["id"],
                "user_question": case["user_question"],
                "auto_reply": case["auto_reply"],
                **scores,
            }
        )

    # 按整体分降序排序，最差的自然落在末尾
    item_list.sort(key=lambda r: r["overall"], reverse=True)

    run_meta = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "client": getattr(client, "__class__", type(client)).__name__,
        "seed": getattr(client, "seed", None),
        "model": getattr(client, "model", None),
        "label": label,
        "n_cases": len(item_list),
    }

    # compute metrics distribution
    distribution = {}
    for m in ("usefulness", "accuracy", "tone"):
        vals = [r[m] for r in item_list]
        distribution[m] = {
            "min": min(vals),
            "max": max(vals),
            "mean": round(sum(vals) / len(vals), 2),
            "median": round(sorted(vals)[len(vals) // 2], 2),
        }

    result = {"run_meta": run_meta, "distribution": distribution, "cases": item_list}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result