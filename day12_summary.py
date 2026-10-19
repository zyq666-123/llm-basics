import json
import os

PATHS = {
    "day8":  "results/day8_baseline.json",
    "day9":  "results/day9_thinking.json",
    "day10": "results/day10_voting.json",
    "day11": "results/day11_lost_in_middle.json",
}


def load(key):
    path = PATHS[key]
    if not os.path.exists(path):
        print(f"  [缺失] {path}")
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def bar(value, width=24, scale=1.0):
    n = round(value / scale * width)
    n = max(0, min(width, n))
    return "█" * n + "░" * (width - n)


def main():
    d8, d9, d10, d11 = (load(k) for k in ("day8", "day9", "day10", "day11"))

    # ---------------- 总表 ----------------
    rows = []

    if d8:
        n = d8["total"]
        rows.append((
            "Day8 baseline（thinking-high ×1）",
            d8["accuracy"],
            d8["total_cost_usd"] / n,
            d8["total_time_s"] / n,
        ))

    if d9:
        for s in d9["summaries"]:
            rows.append((
                f"Day9 {s['name']}",
                s["accuracy"],
                s["avg_cost"],
                s["avg_time"],
            ))

    if d10:
        sm = d10["summary"]
        rows.append(("Day10 单次采样", sm["accuracy_first"],
                     sm["single_cost"] / len(d10["rows"]), None))
        rows.append(("Day10 5 次投票", sm["accuracy_voted"],
                     sm["total_cost"] / len(d10["rows"]), None))

    print("=" * 88)
    print("Week 2 全部方案横向对比")
    print("=" * 88)
    print(f"{'方案':<36}{'准确率':>8}{'每题成本$':>13}{'每题耗时':>11}")
    print("-" * 88)

    for name, acc, cost, t in rows:
        t_str = f"{t:.1f}s" if t is not None else "—"
        print(f"{name:<36}{acc:>7.0%}{cost:>13.6f}{t_str:>11}")

    # ---------------- Day9 明细 ----------------
    if d9:
        print()
        print("=" * 88)
        print("Day9 思考模式：准确率 vs 成本")
        print("=" * 88)
        for s in d9["summaries"]:
            print(f"  {s['name']:<16} {s['accuracy']:>4.0%}  "
                  f"{bar(s['accuracy'], 20)}  "
                  f"成本 ${s['avg_cost']:.6f}  {s['avg_time']:>5.1f}s")

    # ---------------- Day10 明细 ----------------
    if d10:
        sm = d10["summary"]
        print()
        print("=" * 88)
        print("Day10 投票：采样多样性与命中上限")
        print("=" * 88)
        print(f"  各次采样准确率 : {[f'{x:.0%}' for x in sm['per_sample_accuracy']]}")
        print(f"  第 1 次        : {sm['accuracy_first']:.0%}")
        print(f"  投票后         : {sm['accuracy_voted']:.0%}")
        print(f"  oracle         : {sm['accuracy_oracle']:.0%}")
        print(f"  未兑现的潜力   : {sm['accuracy_oracle'] - sm['accuracy_voted']:+.0%}")
        print(f"  并列题数       : {sm['ties']}")
        print(f"  救回来的题     : {sm['rescued'] or '无'}")
        print(f"  弄错的题       : {sm['broken'] or '无'}")

    # ---------------- Day11 明细 ----------------
    if d11:
        print()
        print("=" * 88)
        print("Day11 位置效应")
        print("=" * 88)
        for k in sorted(d11["summary"], key=float):
            v = d11["summary"][k]
            print(f"  位置 {float(k):<5.2f} {v['accuracy']:>4.0%}  "
                  f"{bar(v['accuracy'], 20)}  ({v['ok']}/{v['total']})")

        recs = d11["records"]
        p = [r["prompt_tokens"] for r in recs]
        print(f"\n  上下文规模: 平均 {sum(p) / len(p):.0f} tokens")
        print(f"  sanity check: {'通过' if d11['sanity_ok'] else '失败'}")

    print()
    print("=" * 88)


if __name__ == "__main__":
    main()