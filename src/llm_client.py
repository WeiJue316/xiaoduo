"""LLM 客户端：统一 judge_single 接口，提供真实(RealClient)与 mock(MockClient)实现。

RealClient 通过一个可适配层（_adapt）对接火山 Agentplan。由于 Agentplan 的具体
endpoint/鉴权/返回结构由 LYY 提供后才确定，这里预留 OpenAI 兼容的 chat 适配作为
起点；真实接口信息一到，只需改写 _adapt 一个方法即可跑真。

MockClient 是一份确定性的参考实现，用于在无 API key 时把整条流水线跑通、可复现，
并作为"rubrics 是否贴合人工判断"的自检基准。分数基于对每条 case 内容的业务判断，
**不与 human_ref.json 发生引用关系**。
"""

import json
import os
import urllib.request


class JudgeError(Exception):
    pass


def _parse_scores_struct(raw: str, case_id: str) -> dict:
    """宽容解析 judge 返回的 JSON，容忍前后缀 / 代码块包裹，可取半整数。"""
    text = raw.strip()
    if text.startswith("```"):
        # 去掉围栏
        text = text.lstrip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
        if text.endswith("```"):
            text = text[: -3].strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise JudgeError(f"{case_id}: 返回中未找到 JSON 对象")
    obj = json.loads(text[start : end + 1])
    if not isinstance(obj, dict):
        raise JudgeError(f"{case_id}: 解析结果非对象")
    out = {}
    for m in ("usefulness", "accuracy", "tone"):
        v = obj.get(m)
        f = float(v)
        if f < 0 or f > 5:
            raise JudgeError(f"{case_id}: {m} 越界 {f}")
        out[m] = round(f * 2) / 2.0  # 归一为半整数
    out["reason"] = str(obj.get("reason", "")).strip()
    return out


class RealClient:
    """通过火山 Agentplan 的真实评分客户端。

    config 预期结构：
    {
      "agentplan": {"endpoint": "...", "api_key": "...", "model": "..."},
      "judge": {"seed": 42}
    }
    """

    def __init__(self, config: dict):
        agent = config.get("agentplan", {})
        self.endpoint = agent.get("endpoint")
        self.api_key = agent.get("api_key")
        self.model = agent.get("model", "deepseek-v4-flash")
        self.seed = config.get("judge", {}).get("seed", 42)
        if not self.endpoint or not self.api_key:
            raise JudgeError("RealClient 需 config 提供 agentplan.endpoint 与 api_key")

    def judge_single(self, case: dict) -> dict:
        from .judge import build_messages

        system, user = build_messages(case["user_question"], case["auto_reply"])
        raw = self._adapt(system, user)
        return _parse_scores_struct(raw, case["id"])

    def _adapt(self, system: str, user: str) -> str:
        """OpenAI 兼容 chat 适配。Agentplan 真实接口信息一到，改写此方法即可。"""
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "seed": self.seed,
            "max_tokens": 300,
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            raise JudgeError(f"Agentplan 调用失败: {e}") from e
        # 兼容常见返回形状
        content = None
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            # 某些服务返回非 OpenAI 形状，从残留字段兜底
            content = payload.get("result") or payload.get("output")
        if not content:
            raise JudgeError(f"Agentplan 未返回文本: {str(payload)[:200]}")
        return content


class MockClient:
    """确定性参考实现。judge 返回结构必须与 RealClient 对齐。"""

    # 每条 case 的判定：基于个案内容的业务判断（0-5 半整数）。reason 用一句中文点出主扣分点。
    _VERDICTS = {
        "case_01": {"usefulness": 2.5, "accuracy": 4.0, "tone": 4.0, "reason": "给了路径但把'联系/去取'的活交回用户，未主动代办"},
        "case_02": {"usefulness": 2.5, "accuracy": 4.0, "tone": 3.0, "reason": "只讲通用规定，未查具体商品，让用户自己确认容量"},
        "case_03": {"usefulness": 3.0, "accuracy": 4.0, "tone": 3.0, "reason": "规则准确但让用户自查进度，未主动查单"},
        "case_04": {"usefulness": 3.0, "accuracy": 4.0, "tone": 4.0, "reason": "先堆排查步骤增加负担，但给了质保方案且语气诚恳"},
        "case_05": {"usefulness": 2.0, "accuracy": 3.0, "tone": 4.0, "reason": "道歉但未触及原始问题，'加强培训'是用户不关心的内部事项"},
        "case_06": {"usefulness": 2.5, "accuracy": 4.0, "tone": 3.0, "reason": "罗列原因让用户自查，未帮确认优惠券状态"},
        "case_07": {"usefulness": 3.0, "accuracy": 4.0, "tone": 3.0, "reason": "防诈提醒好但把'是否真登录'的判断推给用户，惧感安抚不足"},
        "case_08": {"usefulness": 2.0, "accuracy": 3.0, "tone": 3.0, "reason": "用户问具体商品却叫其看详情页，典型'正确但没用'"},
        "case_09": {"usefulness": 3.5, "accuracy": 4.0, "tone": 3.0, "reason": "规则正确但未追问具体情况给针对性答复"},
        "case_10": {"usefulness": 4.0, "accuracy": 4.0, "tone": 3.0, "reason": "给出明确操作路径与退款时限，尚可"},
        "case_11": {"usefulness": 3.0, "accuracy": 4.0, "tone": 3.0, "reason": "给了通用换货流程但未追问两件商品的具体信息来代办"},
        "case_12": {"usefulness": 2.5, "accuracy": 4.0, "tone": 3.0, "reason": "列原因让用户等，未主动查物流"},
        "case_13": {"usefulness": 2.0, "accuracy": 3.0, "tone": 3.0, "reason": "敏感肌用户的需求被打回'自己看详情页'，缺个性化"},
        "case_14": {"usefulness": 4.0, "accuracy": 4.0, "tone": 4.0, "reason": "建议类反馈处理良好，感谢并承诺转达"},
        "case_15": {"usefulness": 4.0, "accuracy": 4.0, "tone": 5.0, "reason": "连续踩雷场景道歉与补偿都到位，共情充分"},
        "case_16": {"usefulness": 3.5, "accuracy": 4.0, "tone": 3.0, "reason": "追问场景预算合理，但'看评价'又把用户推开"},
        "case_17": {"usefulness": 2.5, "accuracy": 3.0, "tone": 3.0, "reason": "两个问题都让用户自己查，未主动代办"},
        "case_18": {"usefulness": 4.0, "accuracy": 4.0, "tone": 4.0, "reason": "质保方案清晰、语气诚恳，质量尚可"},
        "case_19": {"usefulness": 3.0, "accuracy": 4.0, "tone": 3.0, "reason": "未查具体商品补货，给通用建议"},
        "case_20": {"usefulness": 2.0, "accuracy": 3.0, "tone": 3.5, "reason": "用户已说搞不懂，回复又重复流程，近乎答非所问"},
    }

    def __init__(self, config: dict):
        self.seed = config.get("judge", {}).get("seed", 42)
        # mock 是确定性的；seed 仅用于对齐界面
        self._verdicts = dict(self._VERDICTS)

    def judge_single(self, case: dict) -> dict:
        v = self._verdicts.get(case["id"])
        if v is None:
            raise JudgeError(f"MockClient 无 case {case['id']} 的预置判定")
        return dict(v)


def build_client(kind: str, config: dict):
    """kind: 'real' | 'mock'，返回对应客户端实例。"""
    if kind == "real":
        return RealClient(config)
    if kind == "mock":
        return MockClient(config)
    raise JudgeError(f"未知客户端类型: {kind}")