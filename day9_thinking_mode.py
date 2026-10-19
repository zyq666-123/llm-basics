import json
import os
import time
from datetime import datetime

from common import MODEL, calc_cost, client


# ============================================================
# prompt 与题库（和 day8 完全一致，保证可比）
# ============================================================

SYSTEM = """你是一个数学解题助手。
请解答用户给出的数学应用题，并以 json 格式输出结果。

json 格式：
{"answer": 一个数字}

只输出这个 json，不要有其他内容。"""

CASES = [
    # ---- 简单（5 题）----
    ("小明有 5 个苹果，妈妈又给了他 3 个，他一共吃了 2 个，还剩几个？", 6),
    ("一箱牛奶 12 盒，买了 3 箱，喝了 7 盒，还剩几盒？", 29),
    ("甲有 45 元，乙比甲多 15 元，两人一共多少钱？", 105),
    ("一个长方形长 12 厘米宽 8 厘米，周长是多少厘米？", 40),
    ("班里有 40 人，男生占 3/5，女生有多少人？", 16),

    # ---- 中等（10 题）----
    ("图书馆有 240 本书，借出 1/4，又新买 30 本，现在有多少本？", 210),
    ("汽车每小时行 60 公里，行驶 2.5 小时，能走多远？", 150),
    ("一件衣服原价 200 元，打八折后再减 20 元，实付多少元？", 140),
    ("水池有 500 升水，每小时流出 45 升，3 小时后还剩多少升？", 365),
    ("苹果 6 元一斤，买了 2.5 斤，付 20 元，找零多少元？", 5),
    ("三本书共 156 页，第一本 48 页，第二本比第一本多 12 页，第三本多少页？", 48),
    ("每盒铅笔 12 支，45 支能装满几盒，还剩几支？（填剩余支数）", 9),
    ("一个数加上 27 后乘 3 等于 108，这个数是多少？", 9),
    ("小明跑步速度 200 米/分，跑 3 公里需要多少分钟？", 15),
    ("商店进货 80 件，卖出 3/5 后又进货 25 件，现在多少件？", 57),

    # ---- 较难（5 题）----
    ("一根绳子长 8 米，剪成每段 2/5 米，能剪几段？", 20),
    ("一列火车 8:15 出发，行驶 3 小时 40 分，几点到？（填分钟数，如 11:55 填 55）", 55),
    ("一块地 3/4 公顷种白菜，剩下的 1/2 种萝卜，萝卜种了多少公顷？（填分子，即 1/8 填 1）", 1),
    ("用 24 厘米长的铁丝围成一个正方形，面积是多少平方厘米？", 36),
    ("5 个人 3 天完成一项工作，如果 3 个人做同样效率，需要几天？", 5),
]


# ============================================================
# 判定
# ============================================================

def extract_answer(raw_text):
    """从返回的 JSON 里抽出数字答案，失败返回 None。"""
    if not raw_text:
        return None
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return None

    got = data.get("answer")
    if got is None:
        return None

    try:
        return float(got)
    except (TypeError, ValueError):
        return None


def judge(raw_text, expected):
    """返回 (是否正确, 抽出的答案, 失败原因)。"""
    got = extract_answer(raw_text)
    if got is None:
        return False, None, "无法解析出数字"

    if abs(got - float(expected)) < 1e-6:
        return True, got, None

    return False, got, f"答案不符（期望 {expected}）"


# ============================================================
# 四组配置
# ============================================================

CONFIGS = [
    {"name": "non-thinking",  "thinking": "disabled", "effort": None},
    {"name": "thinking-low",  "thinking": "enabled",  "effort": "low"},
    {"name": "thinking-high", "thinking": "enabled",  "effort": "high"},
    {"name": "thinking-max",  "thinking": "enabled",  "effort": "max"},
]


def ask(question, cfg):
    """按配置发一次请求。"""
    kwargs = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 8192,                  # max 档思考很长，给足
        "extra_body": {"thinking": {"type": cfg["thinking"]}},
    }
    if cfg["effort"]:                        # 关闭思考时不传档位
        kwargs["reasoning_effort"] = cfg["effort"]

    start = time.time()
    resp = client.chat.completions.create(**kwargs)
    return resp, time.time() - start


# ============================================================
# 跑一组配置
# ============================================================

def run_config(cfg):
    print()
    print("=" * 78)
    print(f"配置: {cfg['name']}   (thinking={cfg['thinking']}, "
          f"effort={cfg['effort'] or '—'})")
    print("=" * 78)

    results = []
    correct = 0
    cost_sum = 0.0
    time_sum = 0.0
    reasoning_sum = 0
    completion_sum = 0

    for i, (question, expected) in enumerate(CASES, 1):
        resp, elapsed = ask(question, cfg)
        raw = resp.choices[0].message.content
        ok, got, reason = judge(raw, expected)
        info = calc_cost(resp.usage)

        correct += int(ok)
        cost_sum += info["cost"]
        time_sum += elapsed
        reasoning_sum += info["reasoning"]
        completion_sum += info["completion"]

        results.append({
            "i": i,
            "question": question,
            "expected": expected,
            "got": got,
            "ok": ok,
            "reason": reason,
            "reasoning_tokens": info["reasoning"],
            "completion_tokens": info["completion"],
            "prompt_tokens": info["prompt"],
            "cost": info["cost"],
            "time_s": elapsed,
        })

        mark = "✓" if ok else "✗"
        print(f"{i:2}. {mark} 期望={expected:<6} 得到={str(got):<8} "
              f"思考{info['reasoning']:>5} 出{info['completion']:>5} "
              f"${info['cost']:.6f} {elapsed:>5.1f}s")

    n = len(CASES)
    return {
        "name": cfg["name"],
        "config": cfg,
        "correct": correct,
        "total": n,
        "accuracy": correct / n,
        "total_cost": cost_sum,
        "avg_cost": cost_sum / n,
        "total_time": time_sum,
        "avg_time": time_sum / n,
        "avg_reasoning_tokens": reasoning_sum / n,
        "avg_completion_tokens": completion_sum / n,
        "details": results,
    }


# ============================================================
# 汇总输出
# ============================================================

def print_comparison(summaries):
    print()
    print("=" * 88)
    print("对比：准确率 / 成本 / 延迟 / 思考量")
    print("=" * 88)
    print(f"{'配置':<16}{'准确率':>9}{'平均成本$':>14}{'平均耗时':>11}"
          f"{'平均思考tok':>14}")
    print("-" * 88)

    for s in summaries:
        print(f"{s['name']:<16}{s['accuracy']:>8.0%}"
              f"{s['avg_cost']:>14.6f}{s['avg_time']:>10.1f}s"
              f"{s['avg_reasoning_tokens']:>14.0f}")

    print()
    print("=" * 88)
    print(f"边际效益（相对 {summaries[0]['name']}）")
    print("=" * 88)

    base = summaries[0]
    for s in summaries[1:]:
        d_acc = s["accuracy"] - base["accuracy"]
        d_cost = s["avg_cost"] - base["avg_cost"]
        d_time = s["avg_time"] - base["avg_time"]
        d_reason = s["avg_reasoning_tokens"] - base["avg_reasoning_tokens"]

        line = (f"  {s['name']:<16} 准确率 {d_acc:+.0%}   "
                f"成本 {d_cost:+.6f}   耗时 {d_time:+.1f}s   "
                f"思考 {d_reason:+.0f}tok")

        if d_acc > 0 and d_cost > 0:
            line += f"\n{'':19}→ 每 +1 个百分点多花 ${d_cost / (d_acc * 100):.6f}"
        elif d_acc > 0:
            line += "\n" + " " * 19 + "→ 又准又便宜"
        elif d_cost > 0:
            line += "\n" + " " * 19 + "→ 没变准，还更贵"

        print(line)

    # 逐题对照
    print()
    print("=" * 88)
    print("逐题对照")
    print("=" * 88)

    width = 15
    header = f"{'题':>3}  " + "".join(f"{s['name'][:13]:>{width}}" for s in summaries)
    print(header)
    print("-" * len(header))

    for i in range(len(CASES)):
        row = f"{i + 1:>3}  "
        for s in summaries:
            row += f"{('✓' if s['details'][i]['ok'] else '✗'):>{width}}"
        print(row)

    # 反常题：开了思考反而错
    print()
    print("=" * 88)
    print("开了思考反而答错的题")
    print("=" * 88)

    found = False
    for i in range(len(CASES)):
        base_ok = summaries[0]["details"][i]["ok"]
        worse = [s["name"] for s in summaries[1:]
                 if base_ok and not s["details"][i]["ok"]]
        if worse:
            found = True
            print(f"  第 {i + 1:2} 题（期望 {CASES[i][1]}）："
                  f"non-thinking ✓，但 {', '.join(worse)} ✗")

    if not found:
        print("  无")


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    started = time.time()

    summaries = []
    for cfg in CONFIGS:
        summaries.append(run_config(cfg))

    print_comparison(summaries)

    os.makedirs("results", exist_ok=True)
    path = "results/day9_thinking.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "name": "day9_thinking_mode",
            "created_at": datetime.now().isoformat(),
            "model": MODEL,
            "n_cases": len(CASES),
            "summaries": summaries,
        }, f, ensure_ascii=False, indent=2)

    print()
    print(f"结果已保存到 {path}")
    print(f"总耗时 {time.time() - started:.1f}s")



























