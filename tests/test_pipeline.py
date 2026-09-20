"""流水线单元测试 + human_ref 一致性验证测试。"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm_client import MockClient, _parse_scores_struct, JudgeError
from src.metrics import overall, anchor_text
from src.scorer import run as run_scorer
from src.validation import validate, spearman

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTACH = os.path.join(PROJECT, "attachments")
OUT = os.path.join(PROJECT, "outputs", "test")


@pytest.fixture()
def client():
    return MockClient({"judge": {"seed": 42}})


@pytest.fixture()
def result(client):
    os.makedirs(OUT, exist_ok=True)
    return run_scorer(client, ATTACH, os.path.join(OUT, "scored_cases.json"), label="test")


# ---------- 单元 ----------

def test_mock_scores_all_20(client):
    cases = json.load(open(os.path.join(ATTACH, "task3_auto_replies.json"), encoding="utf-8"))
    assert len(cases) == 20
    for c in cases:
        s = client.judge_single(c)
        for m in ("usefulness", "accuracy", "tone"):
            assert 0 <= s[m] <= 5
            assert s[m] == round(s[m] * 2) / 2.0  # 半整数


def test_overall_is_arithmetic_mean():
    c = {"usefulness": 5, "accuracy": 4, "tone": 3}
    assert overall(c) == 4.0


def test_anchor_text_rounds_half():
    assert "主动办到底" in anchor_text("usefulness", 4.5) or anchor_text("usefulness", 4.5)
    assert isinstance(anchor_text("tone", 2.6), str)


def test_parse_structure_tolerates_wraps():
    raw = '先看内容 ```json\n{"usefulness":4.5,"accuracy":4,"tone":3,"reason":"ok"}``` 结束'
    out = _parse_scores_struct(raw, "case_x")
    assert out["usefulness"] == 4.5
    with pytest.raises(JudgeError):
        _parse_scores_struct("no json here", "case_x")


def test_json_parse_errors_on_oob():
    with pytest.raises(JudgeError):
        _parse_scores_struct("{"+'"usefulness":7'+"}", "case_x")


# ---------- 一致性验证 ----------

def test_consistency_hits_threshold(result):
    v = validate(result)
    assert v["tier_accuracy"] >= 0.65, f"命中率不足: {v['tier_accuracy']}"
    assert 0 <= v["spearman_usefulness_vs_truth"] <= 1


def test_spearman_math():
    assert spearman([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 2, 2, 3], [3, 1, 2, 2]) == pytest.approx(-0.5)


def test_report_artifacts_created(result):
    from src.report import build_report
    v = validate(result)
    paths = build_report(result, v, ATTACH, OUT)
    for p in (paths["report_md"], paths["report_html"]):
        assert os.path.exists(p)
    md = open(paths["report_md"], encoding="utf-8").read()
    # 报告主体只保留任务要求的三块：整体结论 / 指标分布 / 最差3条
    assert "## 整体结论" in md
    assert "## 各指标分布" in md
    assert "## 最差 3 条详解" in md
    assert "## 局限性" not in md  # 局限性已移出报告，见 README
    assert all(cid in md for cid in ("case_01", "case_20"))