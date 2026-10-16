import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

MODEL = "deepseek-flash"
USD_TO_CNY = 7.2

# 美元 / 1M tokens，以官方价格页为准
PRICE = {
    "peak":     {"cache_hit": 0.006, "cache_miss": 0.30, "output": 1.20},
    "off_peak": {"cache_hit": 0.003, "cache_miss": 0.15, "output": 0.60},
}


# ============================================================
# 成本计算（② 写的）
# ============================================================

def calc_cost(usage, price=None):
    price = price or PRICE["peak"]

    prompt_tokens = usage.prompt_tokens
    completion_tokens = usage.completion_tokens

    cached = getattr(usage, "prompt_cache_hit_tokens", None)
    if cached is None:
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) if details else 0
    cached = cached or 0
    cache_miss = prompt_tokens - cached

    details = getattr(usage, "completion_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", 0) if details else 0
    reasoning = reasoning or 0

    cost = (
        cache_miss          / 1_000_000 * price["cache_miss"]
        + cached            / 1_000_000 * price["cache_hit"]
        + completion_tokens / 1_000_000 * price["output"]
    )

    return {
        "prompt": prompt_tokens,
        "cached": cached,
        "miss": cache_miss,
        "completion": completion_tokens,
        "reasoning": reasoning,
        "content": completion_tokens - reasoning,
        "cost": cost,
    }
def cost_without_cache(info, price=None):
    """假设完全没有缓存命中，这次要花多少。"""
    price = price or PRICE["peak"]
    return (
        info["prompt"] / 1_000_000 * price["cache_miss"]
        + info["completion"] / 1_000_000 * price["output"]
    )

def split_cost(info, price=None):
    """把成本拆成输入部分和输出部分。"""
    price = price or PRICE["peak"]
    in_cost = (
        info["miss"] / 1_000_000 * price["cache_miss"]
        + info["cached"] / 1_000_000 * price["cache_hit"]
    )
    out_cost = info["completion"] / 1_000_000 * price["output"]
    return in_cost, out_cost


def show_cost(label, info):
    in_cost, out_cost = split_cost(info)
    total = in_cost + out_cost
    print(f"\n--- {label} ---")
    print(f"  输入 {info['prompt']:>6} tokens  "
          f"(缓存命中 {info['cached']}, 未命中 {info['miss']})")
    print(f"  输出 {info['completion']:>6} tokens  "
          f"(其中思考 {info['reasoning']}, 正文 {info['content']})")
    print(f"  输入成本 ${in_cost:.6f} ({in_cost / total * 100:>4.0f}%)   "
          f"输出成本 ${out_cost:.6f} ({out_cost / total * 100:>4.0f}%)")
    print(f"  合计 ${total:.6f}  ≈ ¥{total * USD_TO_CNY:.4f}")


# ============================================================
# 场景 A
# ============================================================

SHORT_SYSTEM = "你是一个简洁的助手，回答不超过两句话。"

# A3 专用：这里不能再说"不超过两句话"，否则和"500 字"打架
PLAIN_SYSTEM = "你是一个乐于解释的技术助手。"

# A2 用的超长背景（靠重复堆出来，方便你改长度）
REPEAT = 40
LONG_SYSTEM = "你是一个客服助手。以下是公司背景资料，请记住：\n" + (
    "本公司成立于 2015 年，主营跨境电子商务，覆盖北美、欧洲与东南亚市场。"
    "仓储中心分布在深圳、洛杉矶与法兰克福，合作物流商共 12 家。"
    "退换货政策为签收后 30 天内无理由退货，质量问题由公司承担运费。"
    "客服工作时间为北京时间 9:00 至 21:00，节假日照常。"
) * REPEAT


def run_once(label, system, question):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": question})

    resp = client.chat.completions.create(model=MODEL, messages=messages)

    info = calc_cost(resp.usage)
    show_cost(label, info)
    return info


if __name__ == "__main__":

    TURNS = 10

    messages = [
        {"role": "system", "content": "你是一个简洁的助手，回答不超过两句话。"}
    ]

    rows = []
    total = 0.0
    total_no_cache = 0.0

    print("开始多轮对话，共", TURNS, "轮……\n")

    for turn in range(1, TURNS + 1):

        messages.append({
            "role": "user",
            "content": f"请用一句话说明数字 {turn} 的一个特点。",
        })

        resp = client.chat.completions.create(model=MODEL, messages=messages)

        messages.append({
            "role": "assistant",
            "content": resp.choices[0].message.content,
        })

        info = calc_cost(resp.usage)
        no_cache = cost_without_cache(info)

        total += info["cost"]
        total_no_cache += no_cache

        rows.append({
            "turn": turn,
            "prompt": info["prompt"],
            "cached": info["cached"],
            "completion": info["completion"],
            "cost": info["cost"],
            "no_cache": no_cache,
            "cum": total,
        })

    # ---------------- 明细表 ----------------
    print("=" * 84)
    print("多轮对话成本明细")
    print("=" * 84)
    print(f"{'轮次':>4}{'输入tok':>10}{'命中缓存':>10}{'输出tok':>10}"
          f"{'本轮$':>12}{'累计$':>12}{'无缓存本轮$':>14}")
    print("-" * 84)

    for r in rows:
        print(f"{r['turn']:>4}{r['prompt']:>10}{r['cached']:>10}{r['completion']:>10}"
              f"{r['cost']:>12.6f}{r['cum']:>12.6f}{r['no_cache']:>14.6f}")

    # ---------------- 输入增长 ----------------
    first, last = rows[0], rows[-1]

    print()
    print("=" * 84)
    print("① 输入是怎么长的")
    print("=" * 84)
    print(f"  第 1 轮输入:   {first['prompt']:>7} tokens")
    print(f"  第 {TURNS} 轮输入:  {last['prompt']:>7} tokens"
          f"   （涨了 {last['prompt'] / first['prompt']:.1f} 倍）")
    print(f"  第 1 轮单轮成本:   ${first['cost']:.6f}")
    print(f"  第 {TURNS} 轮单轮成本:  ${last['cost']:.6f}"
          f"   （涨了 {last['cost'] / first['cost']:.1f} 倍）")

    # ---------------- 缓存命中率 ----------------
    total_input = sum(r["prompt"] for r in rows)
    total_cached = sum(r["cached"] for r in rows)

    print()
    print("=" * 84)
    print("② 缓存起了多大作用")
    print("=" * 84)
    print(f"  累计发出输入:  {total_input:>8} tokens")
    print(f"  其中命中缓存:  {total_cached:>8} tokens"
          f"   （命中率 {total_cached / total_input * 100:.1f}%）")
    print(f"  实际累计成本:      ${total:.6f}")
    print(f"  假如没有缓存:      ${total_no_cache:.6f}")
    print(f"  缓存省了:          {(1 - total / total_no_cache) * 100:.1f}%")

    # ---------------- 平方增长 ----------------
    print()
    print("=" * 84)
    print("③ 累计成本的形状")
    print("=" * 84)
    ideal = first["cost"] * TURNS
    print(f"  实际累计:            ${total:.6f}")
    print(f"  若每轮成本都等于第1轮: ${ideal:.6f}")
    print(f"  → 是理想值的 {total / ideal:.1f} 倍")
    print()
    print("  看点：单轮成本是【线性】涨的，")
    print(f"  所以 {TURNS} 轮的累计成本是【平方级】的——")
    print(f"  平均每一轮的成本 ${total / TURNS:.6f} 比第 1 轮 ${first['cost']:.6f} "
          f"高了 {total / TURNS / first['cost']:.1f} 倍。")