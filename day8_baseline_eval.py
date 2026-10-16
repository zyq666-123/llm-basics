import json
import os
import time
from datetime import datetime
from common import MODEL, client, calc_cost
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
SYSTEM = """你是一个数学解题助手。
请解答用户给出的数学应用题，并以 json 格式输出结果。

json 格式：
{"answer": 一个数字}

只输出这个 json，不要有其他内容。"""


def ask(question):
    start = time.time()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ],
        response_format={"type": "json_object"},
        max_tokens=4096,          # 思考模式会吃不少输出 token，给足
    )
    return resp, time.time() - start
def judge(raw_text, expected):
    """返回 (是否正确, 抽出的答案, 失败原因)"""
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
results = []
correct = 0
total_cost = 0.0
total_time = 0.0

for i, (question, expected) in enumerate(CASES, 1):
    resp, elapsed = ask(question)
    raw = resp.choices[0].message.content
    ok, got, reason = judge(raw, expected)
    info = calc_cost(resp.usage)

    correct += int(ok)
    total_cost += info["cost"]
    total_time += elapsed

    mark = "✓" if ok else "✗"
    print(f"{i:2}. {mark}  期望={expected:<6} 得到={got!r:<8} "
          f"思考{info['reasoning']:>5}tok  ${info['cost']:.6f}  {elapsed:.1f}s")
    if not ok:
        print(f"      ↳ {reason}")

print()
print("=" * 62)
print(f"准确率:  {correct}/{len(CASES)} = {correct / len(CASES):.0%}")
print(f"总成本:  ${total_cost:.6f}  ≈ ¥{total_cost * 7.2:.4f}")
print(f"总耗时:  {total_time:.1f}s   平均 {total_time / len(CASES):.1f}s/题")
print(f"平均每题: ${total_cost / len(CASES):.6f}")
os.makedirs("results", exist_ok=True)

out = {
    "name": "day8_baseline",
    "created_at": datetime.now().isoformat(),
    "config": {
        "model": MODEL,
        "thinking": "default (enabled, effort=high)",
        "response_format": "json_object",
    },
    "total": len(CASES),
    "correct": correct,
    "accuracy": correct / len(CASES),
    "total_cost_usd": total_cost,
    "total_time_s": total_time,
    "details": results,
}

with open("results/day8_baseline.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("\n结果已保存到 results/day8_baseline.json")