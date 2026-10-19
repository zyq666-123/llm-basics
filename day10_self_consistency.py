import json
import os
import time
from collections import Counter
from datetime import datetime

from common import MODEL, calc_cost, client


# ============================================================
# 题库与 prompt（和 day8 / day9 完全一致，保证可比）
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
# 基础工具
# ============================================================

def extract_answer(raw_text):
    """从模型返回的 JSON 里抽出数字答案，失败返回 None。"""
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


def judge_num(got, expected):
    """带容差的相等判断。"""
    if got is None:
        return False
    return abs(got - float(expected)) < 1e-6


def ask(question, cfg):
    """发一次请求。cfg 可含 thinking / effort / temperature / top_p。"""
    kwargs = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 8192,
        "extra_body": {"thinking": {"type": cfg["thinking"]}},
    }
    if cfg.get("effort"):
        kwargs["reasoning_effort"] = cfg["effort"]
    if cfg.get("temperature") is not None:
        kwargs["temperature"] = cfg["temperature"]
    if cfg.get("top_p") is not None:
        kwargs["top_p"] = cfg["top_p"]

    start = time.time()
    resp = client.chat.completions.create(**kwargs)
    return resp, time.time() - start


def vote(answers):
    """众数投票。返回 (胜出答案, 票数, 是否并列)。"""
    answers = [a for a in answers if a is not None]     # 剔除无效样本
    if not answers:
        return None, 0, False

    canon = [f"{a:g}" for a in answers]                 # 6.0 -> "6"，统一格式
    counter = Counter(canon)
    top = counter.most_common()

    best_count = top[0][1]
    winners = [a for a, c in top if c == best_count]

    if len(winners) > 1:
        return float(winners[0]), best_count, True      # 并列，取最先出现的
    return float(top[0][0]), best_count, False


# ============================================================
# ① 随机性探测
# ============================================================

PROBE_QUESTION = "小明有 5 个苹果，妈妈又给了他 3 个，他一共吃了 2 个，还剩几个？"

PROBE_CONFIGS = [
    {"name": "思考-默认",      "thinking": "enabled",  "effort": "high"},
    {"name": "非思考 t=0",     "thinking": "disabled", "temperature": 0},
    {"name": "非思考 t=1.0",   "thinking": "disabled", "temperature": 1.0},
    {"name": "思考+top_p=1.0", "thinking": "enabled",  "effort": "high", "top_p": 1.0},
]


def run_probe(times=5):
    print("=" * 78)
    print("① 随机性探测")
    print("=" * 78)
    print(f"问题: {PROBE_QUESTION}\n")

    for cfg in PROBE_CONFIGS:
        answers = []
        for _ in range(times):
            resp, _ = ask(PROBE_QUESTION, cfg)
            answers.append(extract_answer(resp.choices[0].message.content))

        uniq = len(set(a for a in answers if a is not None))
        flag = "有随机性" if uniq > 1 else "完全确定"
        print(f"{cfg['name']:<16} 结果={answers}")
        print(f"{'':16} 不同答案数={uniq}   {flag}\n")


# ============================================================
# ② 主实验
# ============================================================

CFG_MAIN = {"thinking": "disabled", "temperature": 1.0}
N_SAMPLES = 5


def run_experiment():
    rows = []
    total_cost = 0.0

    print("=" * 78)
    print(f"② 主实验：每题采样 {N_SAMPLES} 次")
    print("=" * 78)

    for i, (question, expected) in enumerate(CASES, 1):
        samples = []

        for _ in range(N_SAMPLES):
            resp, _ = ask(question, CFG_MAIN)
            samples.append(extract_answer(resp.choices[0].message.content))
            total_cost += calc_cost(resp.usage)["cost"]

        voted, votes, tie = vote(samples)

        row = {
            "i": i,
            "question": question,
            "expected": expected,
            "samples": samples,
            "voted": voted,
            "votes": votes,
            "tie": tie,
            "first_ok": judge_num(samples[0], expected),
            "voted_ok": judge_num(voted, expected),
            "oracle_ok": any(judge_num(s, expected) for s in samples),
        }
        rows.append(row)

        print(f"{i:2}. 期望={expected:<5} 采样={samples} "
              f"票={voted}({votes}){'并列' if tie else ''}  "
              f"单次{'✓' if row['first_ok'] else '✗'} "
              f"投票{'✓' if row['voted_ok'] else '✗'} "
              f"oracle{'✓' if row['oracle_ok'] else '✗'}")

    return rows, total_cost


def summarize(rows, total_cost):
    n = len(rows)

    acc_first = sum(r["first_ok"] for r in rows) / n
    acc_voted = sum(r["voted_ok"] for r in rows) / n
    acc_oracle = sum(r["oracle_ok"] for r in rows) / n

    per_sample = []
    for k in range(N_SAMPLES):
        ok = sum(1 for r in rows if judge_num(r["samples"][k], r["expected"]))
        per_sample.append(ok / n)

    ties = sum(1 for r in rows if r["tie"])
    single_cost = total_cost / N_SAMPLES

    print()
    print("=" * 78)
    print("结果")
    print("=" * 78)
    print(f"  第 1 次采样准确率    : {acc_first:>6.0%}")
    print(f"  各次采样准确率       : {[f'{x:.0%}' for x in per_sample]}")
    print(f"  {N_SAMPLES} 次投票后准确率     : {acc_voted:>6.0%}")
    print(f"  oracle@{N_SAMPLES}（有一次对）: {acc_oracle:>6.0%}")
    print(f"  出现并列的题数       : {ties}/{n}")
    print()
    print(f"  单次方案成本（1 次/题）: ${single_cost:.6f}")
    print(f"  投票方案成本（{N_SAMPLES} 次/题）: ${total_cost:.6f}")

    gain = acc_voted - acc_first
    print()
    if gain > 0:
        extra = total_cost - single_cost
        print(f"  准确率提升 {gain:+.0%}，多花 ${extra:.6f}")
        print(f"  → 每 +1 个百分点准确率成本 ${extra / (gain * 100):.6f}")
    elif gain < 0:
        print(f"  ⚠ 准确率下降 {gain:+.0%}，成本却翻了 {N_SAMPLES} 倍")
    else:
        print(f"  准确率无变化，成本翻了 {N_SAMPLES} 倍")

    # 哪些题被救回来 / 被拖下水
    rescued = [r for r in rows if not r["first_ok"] and r["voted_ok"]]
    broken = [r for r in rows if r["first_ok"] and not r["voted_ok"]]

    print()
    print(f"  投票救回来的题: {[r['i'] for r in rescued] or '无'}")
    print(f"  投票弄错的题:   {[r['i'] for r in broken] or '无'}")

    if rescued:
        print("\n  救回来的详情:")
        for r in rescued:
            print(f"    第{r['i']:2}题 期望={r['expected']:<5} "
                  f"采样={r['samples']} → 票={r['voted']}")

    if broken:
        print("\n  弄错的详情:")
        for r in broken:
            print(f"    第{r['i']:2}题 期望={r['expected']:<5} "
                  f"采样={r['samples']} → 票={r['voted']}")

    print()
    print(f"  oracle@{N_SAMPLES} 与投票准确率的差距: {acc_oracle - acc_voted:+.0%}")
    print("  （这个差就是投票机制没兑现的潜力）")

    return {
        "accuracy_first": acc_first,
        "accuracy_voted": acc_voted,
        "accuracy_oracle": acc_oracle,
        "per_sample_accuracy": per_sample,
        "ties": ties,
        "single_cost": single_cost,
        "total_cost": total_cost,
        "rescued": [r["i"] for r in rescued],
        "broken": [r["i"] for r in broken],
    }


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    started = time.time()

    run_probe(times=5)

    rows, total_cost = run_experiment()
    summary = summarize(rows, total_cost)

    os.makedirs("results", exist_ok=True)
    path = "results/day10_voting.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "name": "day10_self_consistency",
            "created_at": datetime.now().isoformat(),
            "config": {**CFG_MAIN, "n_samples": N_SAMPLES},
            "summary": summary,
            "rows": rows,
        }, f, ensure_ascii=False, indent=2)

    print()
    print(f"结果已保存到 {path}")
    print(f"总耗时 {time.time() - started:.1f}s")