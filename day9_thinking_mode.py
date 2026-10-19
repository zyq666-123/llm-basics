import json
import os
import time
from datetime import datetime

from common import MODEL, calc_cost, client

# ---------- 从 day8 复制 ----------
SYSTEM = """你是一个数学解题助手。
请解答用户给出的数学应用题，并以 json 格式输出结果。

json 格式：
{"answer": 一个数字}

只输出这个 json，不要有其他内容。"""

CASES = [
    # 把 day8 的 20 题整段粘贴到这里
]


def judge(raw_text, expected):
    """从 day8 复制"""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return False, None, f"非法 JSON: {e}"

    got = data.get("answer")
    if got is None:
        return False, None, "缺少 answer 字段"

    try:
        if abs(float(got) - float(expected)) < 1e-6:
            return True, got, None
    except (TypeError, ValueError):
        return False, got, f"不是数字: {got!r}"

    return False, got, f"答案不符（期望 {expected}）"


# ---------- 今天的配置 ----------
CONFIGS = [
    {"name": "non-thinking",  "thinking": "disabled", "effort": None},
    {"name": "thinking-low",  "thinking": "enabled",  "effort": "low"},
    {"name": "thinking-high", "thinking": "enabled",  "effort": "high"},
    {"name": "thinking-max",  "thinking": "enabled",  "effort": "max"},
]


def ask(question, cfg):
    kwargs = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 8192,            # max 档思考很长，给足
        "extra_body": {"thinking": {"type": cfg["thinking"]}},
    }
    if cfg["effort"]:                  # 关闭思考时不传档位
        kwargs["reasoning_effort"] = cfg["effort"]

    start = time.time()
    resp = client.chat.completions.create(**kwargs)
    return resp, time.time() - start


def run_config(cfg):
    print()
    print("=" * 76)
    print(f"配置: {cfg['name']}")
    print("=" * 76)

    results = []
    correct = 0
    cost_sum = 0.0
    time_sum = 0.0
    reasoning_sum = 0

    for i, (question, expected) in enumerate(CASES, 1):
        resp, elapsed = ask(question, cfg)
        raw = resp.choices[0].message.content
        ok, got, reason = judge(raw, expected)
        info = calc_cost(resp.usage)

        correct += int(ok)
        cost_sum += info["cost"]
        time_sum += elapsed
        reasoning_sum += info["reasoning"]

        results.append({
            "i": i, "question": question, "expected": expected,
            "got": got, "ok": ok, "reason": reason,
            "reasoning_tokens": info["reasoning"],
            "completion_tokens": info["completion"],
            "cost": info["cost"], "time_s": elapsed,
        })

        mark = "✓" if ok else "✗"
        print(f"{i:2}. {mark} 期望={expected:<6} 得到={got!r:<8} "
              f"思考{info['reasoning']:>5} 出{info['completion']:>5} "
              f"${info['cost']:.6f} {elapsed:>5.1f}s")

    n = len(CASES)
    return {
        "name": cfg["name"],
        "config": cfg,
        "accuracy": correct / n,
        "correct": correct,
        "total": n,
        "avg_cost": cost_sum / n,
        "avg_time": time_sum / n,
        "avg_reasoning_tokens": reasoning_sum / n,
        "details": results,
    }