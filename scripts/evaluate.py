#!/usr/bin/env python3
"""CLI 入口：评估自动回复质量流水线。

用法：
  python scripts/evaluate.py --mock --out outputs/           # mock 全链路演示
  python scripts/evaluate.py --real --config config/config.json --out outputs/
                                                             # 真实 DeepSeek（需填配置）

参数：
  --real / --mock     指定评分引擎（默认 mock）
  --config PATH       真实模式下的配置文件
  --out PATH          输出目录（默认 outputs/）
  --label TEXT        附加运行标注，写入报告
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="自动回复质量评估流水线")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--real", action="store_true", help="使用真实 LLM(DeepSeek via Agentplan)")
    g.add_argument("--mock", action="store_true", help="使用 mock 引擎")
    ap.add_argument("--config", default="config/config.json", help="真实模式配置文件")
    ap.add_argument("--out", default="outputs", help="输出目录")
    ap.add_argument("--label", default="", help="运行标注（写入报告）")
    args = ap.parse_args()

    from src.llm_client import build_client
    from src.scorer import run as run_scorer
    from src.validation import validate
    from src.report import build_report

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    attachments = os.path.join(project_root, "attachments")
    out_dir = args.out if os.path.isabs(args.out) else os.path.join(project_root, args.out)
    os.makedirs(out_dir, exist_ok=True)

    kind = "real" if args.real else "mock"
    config = {}
    if kind == "real":
        config = _load_config(args.config)

    client = build_client(kind, config)

    print(f"[evaluate] 引擎={kind} label='{args.label}'")
    result = run_scorer(client, attachments, os.path.join(out_dir, "scored_cases.json"), label=args.label or kind)
    print(f"[evaluate] 已评分 {result['run_meta']['n_cases']} 条")

    validation = validate(result)
    with open(os.path.join(out_dir, "validation.json"), "w", encoding="utf-8") as f:
        json.dump(validation, f, ensure_ascii=False, indent=2)

    paths = build_report(result, validation, attachments, out_dir)
    print(f"[evaluate] 一致性命中率={validation['tier_accuracy']}")
    print(f"[evaluate] 报告已生成:\n  md  {paths['report_md']}\n  html {paths['report_html']}")


if __name__ == "__main__":
    main()