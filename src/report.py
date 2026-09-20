"""报告生成：从 scored_cases.json 产出 report.md 与 report.html。

结构：
1. run meta + 整体均分 + 一句话结论
2. 三指标分布
3. 全 20 条分数表
4. 最差 3 条详解（对照 human_ref 的 annotator_notes）
5. 一致性验证（命中率 + Spearman）
6. 局限性 4 类
"""

import json
from .metrics import METRICS
from .ground_truth import GROUND_TRUTH

# 人工注释（供"最差3条"对照引述）
_HUMAN_NOTES = None


def _load_human_notes(attachments_dir):
    global _HUMAN_NOTES
    if _HUMAN_NOTES is not None:
        return _HUMAN_NOTES
    with open(f"{attachments_dir}/task3_human_ref.json", encoding="utf-8") as f:
        data = json.load(f)
    _HUMAN_NOTES = {d["id"]: d for d in data}
    return _HUMAN_NOTES


LIMITATIONS = [
    (
        "指标自身盲区",
        "「主动协助度」会把『确实只能给信息、不该代办』的回复误判为偏低（如用户仅问材质/规格，本就该答信息而非代办）；"
        "『正确但没帮上』与『差』的档位边界主观，人工标注之间的分歧本身就说明其模糊。",
        "case_08、case_13 这类『正确但没用』在有用性维度被我方判定更低，落入了『差』档，而人工标注归为『正确但没帮上』——两者结论一致说『不够好』，但档位分类不同。",
        "细化『主动』与『代办』的边界定义；对信息类问题单独设指标，避免与代办类混评。",
    ),
    (
        "judge 自身偏差",
        "LLM 评分存在系统性偏好：倾向打偏高分、往中间值收缩、用词重复；DeepSeek 对中文客服语境的稳定性需抽查。",
        "会把明显有缺陷的回复（如包含内部事项 case_05）分数偏高，或因措辞程式化而低估高共情回复。",
        "多模型交叉评分取中位；对低分与高分区抽样人工复核（kappa 一致性）；固定 temperature/seed 并记录版本。",
    ),
    (
        "样本与场景局限",
        "仅 20 条、单一在线客服场景、无多轮对话上下文、无法回测跨版本，覆盖的意图类别有限（多为售后/查询，缺投诉升级/多轮追问）。",
        "对『模糊追问类』case（case_16『那两款手机』）需要更多上下文才能准确判断主动度。",
        "扩样本到数百条并分意图分层；引入真实多轮会话；对每次自动回复改版重跑对比。",
    ),
    (
        "标注噪声",
        "human_ref 本身是单人主观、未给数值分数、且只有 20 条，无法真正校准；三档编码也依赖我方的解读。",
        "当人工注释者之间有分歧的 case 被当作『唯一真值』时，验证指标会失真。",
        "改为双注释者独立标注并计算一致率；将人工问题从『写一段话』升级为『三档+各指标打分』。",
    ),
]


def _fmt(v):
    return ("%.1f" % v).rstrip("0").rstrip(".")


def build_report(result, validation, attachments_dir, out_dir):
    meta = result["run_meta"]
    dist = result["distribution"]
    cases = result["cases"]

    overall_mean = round(sum(c["overall"] for c in cases) / len(cases), 2)

    # 一句话结论（按分档）
    if overall_mean >= 4:
        summary = f"整体质量较高（均分 {overall_mean}），主动协助到位，可考虑扩大覆盖范围。"
    elif overall_mean >= 3:
        weakest = min(METRICS, key=lambda m: dist[m]["mean"])
        summary = (
            f"整体处于中等水平（均分 {_fmt(overall_mean)}），核心短板是「{METRICS[weakest]}」"
            f"（均值 {_fmt(dist[weakest]['mean'])}），大量回复『正确但把操作抛回给用户』，暂不建议激进扩大覆盖。"
        )
    else:
        summary = f"整体质量偏低（均分 {_fmt(overall_mean)}），主动协助不足，当前不宜扩大自动回复覆盖。"
    # 最差3条 + 详解
    worst = cases[-3:][::-1]

    lines_md = []
    app_md = lines_md.append

    app_md("# 自动回复质量评估报告\n")
    app_md(f"- 生成时间：{meta['generated_at']}  ")
    app_md(f"- 评分引擎：{meta['client']}（model: `{meta.get('model') or 'mock/未指定'}`, seed: `{meta.get('seed')}`）  ")
    app_md(f"- 样本量：{meta['n_cases']} 条自动回复  ")
    app_md(f"- 运行标注：{meta.get('label') or 'mock 演示运行（非真实 LLM）'}\n")
    app_md("## 整体结论\n")
    app_md(f"- **整体均分：{_fmt(overall_mean)} / 5**（三指标等权算术平均）  ")
    app_md(f"- 结论：{summary}\n")

    app_md("## 各指标分布\n")
    app_md("| 指标 | 均值 | 中位 | 最低 | 最高 |")
    app_md("|---|---|---|---|---|")
    for m, name in METRICS.items():
        d = dist[m]
        app_md(f"| {name} | {_fmt(d['mean'])} | {_fmt(d['median'])} | {_fmt(d['min'])} | {_fmt(d['max'])} |")
    app_md("")

    app_md("## 全部 20 条得分\n")
    app_md("| Case | 整体均分 | 主动协助 | 准确 | 语气 | 主要扣分点 |")
    app_md("|---|---|---|---|---|---|")
    for c in cases:
        note = (c.get("reason") or "").replace("|", "\\|")
        app_md(
            f"| {c['id']} | {_fmt(c['overall'])} | {_fmt(c['usefulness'])} | "
            f"{_fmt(c['accuracy'])} | {_fmt(c['tone'])} | {note} |"
        )
    app_md("")

    app_md("## 最差 3 条详解\n")
    human = _load_human_notes(attachments_dir)
    for c in worst:
        app_md(f"### {c['id']} — 整体均分 {_fmt(c['overall'])}\n")
        app_md(f"- 用户问题：{c['user_question']}")
        app_md(f"- 自动回复：{c['auto_reply']}")
        app_md(
            f"- 我方判定：主动协助 {_fmt(c['usefulness'])} / 准确 {_fmt(c['accuracy'])} / "
            f"语气 {_fmt(c['tone'])} —— {c.get('reason') or ''}"
        )
        hn = human.get(c["id"], {})
        app_md(f"- 人工标注（对照）：{hn.get('annotator_notes', '')}")
        app_md(f"- 人工参考回复：{hn.get('human_reference', '')}\n")

    app_md("## 一致性验证（vs 人工三档 ground truth）\n")
    app_md(
        f"- 三档命中率：**{int(validation['tier_accuracy'] * 100)}%**（{validation['n']} 条）  "
    )
    app_md(f"- Spearman（usefulness vs 人工档位排序）：**{validation['spearman_usefulness_vs_truth']}**\n")
    app_md(f"  > 命中率显示我方评分与人工三档判断的整体一致程度；误判集中在『正确但没帮上』↔『差』的档位边界（如 case_08、case_13），详见局限性。\n")

    app_md("## 局限性\n")
    for i, (title, impact, case, improve) in enumerate(LIMITATIONS, 1):
        app_md(f"{i}. **{title}**——{impact}  ")
        app_md(f"   - 典型踩雷：{case}  ")
        app_md(f"   - 改进：{improve}\n")

    md_text = "\n".join(lines_md)
    with open(f"{out_dir}/report.md", "w", encoding="utf-8") as f:
        f.write(md_text)

    html_text = _render_html(md_text)
    with open(f"{out_dir}/report.html", "w", encoding="utf-8") as f:
        f.write(html_text)

    return {"report_md": f"{out_dir}/report.md", "report_html": f"{out_dir}/report.html"}


def _render_html(md_text):
    """极简 markdown 渲染（仅本项目报告用到的语法），输出可浏览器查看的 HTML。"""
    import html as _html

    esc = lambda s: _html.escape(s)
    out = []
    in_table = False
    for raw in md_text.splitlines():
        line = raw
        if line.startswith("# "):
            if in_table:
                out.append("</table>"); in_table = False
            out.append(f"<h1>{esc(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_table:
                out.append("</table>"); in_table = False
            out.append(f"<h2>{esc(line[3:])}</h2>")
        elif line.startswith("### "):
            if in_table:
                out.append("</table>"); in_table = False
            out.append(f"<h3>{esc(line[4:])}</h3>")
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not in_table and all(segs in ("-", "---", ":",) for segs in cells if set(segs) <= set("-: ")):
                continue
            if not in_table:
                out.append("<table><thead><tr>" + "".join(f"<th>{esc(c)}</th>" for c in cells) + "</tr></thead><tbody>")
                in_table = True
            else:
                out.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in cells) + "</tr>")
        elif line.startswith(">"):
            if in_table:
                out.append("</table>"); in_table = False
            out.append(f"<blockquote>{esc(line[1:].strip())}</blockquote>")
        elif line.startswith("- "):
            if in_table:
                out.append("</table>"); in_table = False
            out.append(f"<li>{esc(line[2:])}</li>")
        elif line.startswith(" " * 3 + "- "):
            if in_table:
                out.append("</table>"); in_table = False
            out.append(f"<li style='margin-left:24px'>{esc(line.strip()[2:])}</li>")
        elif line == "":
            out.append("")
        else:
            if in_table and line.strip() == "":
                out.append("</table>"); in_table = False
            else:
                out.append(f"<p>{esc(line)}</p>")
    if in_table:
        out.append("</table>")

    body = "\n".join(out)
    return (
        "<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>"
        "<title>自动回复质量评估报告</title>"
        "<style>body{font-family:-apple-system,'Microsoft YaHei',sans-serif;max-width:900px;"
        "margin:24px auto;padding:0 16px;line-height:1.6;color:#24292e}"
        "table{border-collapse:collapse;width:100%;margin:8px 0}"
        "th,td{border:1px solid #d0d7de;padding:6px 10px;font-size:14px}"
        "th{background:#f6f8fa}h1,h2,h3{color:#1f2328}blockquote{border-left:4px solid #d0d7de;"
        "margin-left:0;padding-left:12px;color:#57606a}</style></head><body>"
        + body
        + "</body></html>"
    )