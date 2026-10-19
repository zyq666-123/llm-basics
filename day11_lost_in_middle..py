import json
import os
import random
import time
from datetime import datetime

from common import MODEL, calc_cost, client


# ============================================================
# 配置
# ============================================================

N_FILLER = 300          # 填充段落数，约 12000+ token，看实际输出的 prompt_tokens 再调
POSITIONS = [0.0, 0.25, 0.5, 0.75, 1.0]
SEED = 42

CFG = {"thinking": "disabled", "temperature": 0}


# ============================================================
# 填充文本生成（内容无关，但每段要不一样）
# ============================================================

CITIES = ["北京", "上海", "广州", "深圳", "成都", "武汉",
          "西安", "杭州", "南京", "重庆", "天津", "苏州"]

FILLER_TEMPLATES = [
    "第 {i} 号仓库本月入库 {a} 箱，出库 {b} 箱，库存结余 {c} 箱，设备运转正常。",
    "巡检记录 {i}：{m} 月 {d} 日，温度 {t} 摄氏度，湿度 {h}%，未发现异常。",
    "运输单据 {i}：由 {city} 发往 {city2}，共计 {a} 箱，预计 {d2} 小时送达。",
    "培训记录 {i}：{m} 月组织安全培训，参加人数 {p} 人，考核通过率 {r}%。",
    "供应商 {i}：合同编号 HT-{a}，供货周期 {d} 天，账期 {k} 天。",
    "值班表 {i}：{m} 月 {d} 日由第 {p} 组值班，交接班时间 {t} 时整。",
    "质量抽检 {i}：抽样 {a} 件，合格 {b} 件，合格率 {r}%，无重大缺陷。",
    "能耗记录 {i}：本月用电 {a} 度，用水 {k} 吨，同比下降 {r}%。",
]


def make_filler(n, seed=SEED):
    """生成 n 段互不相同的填充文本。"""
    rng = random.Random(seed)
    paras = []
    for i in range(1, n + 1):
        tpl = rng.choice(FILLER_TEMPLATES)
        paras.append(tpl.format(
            i=i,
            m=rng.randint(1, 12),
            d=rng.randint(1, 28),
            d2=rng.randint(4, 72),
            a=rng.randint(10, 999),
            b=rng.randint(10, 999),
            c=rng.randint(10, 999),
            t=rng.randint(15, 28),
            h=rng.randint(40, 80),
            p=rng.randint(5, 50),
            r=rng.randint(80, 100),
            k=rng.randint(15, 90),
            city=rng.choice(CITIES),
            city2=rng.choice(CITIES),
        ))
    return paras


# ============================================================
# 针（关键信息）
# ============================================================

NEEDLES = [
    ("深蓝项目的验证码", "K7X-2048"),
    ("赤松项目的验证码", "M3P-7719"),
    ("白鹭项目的验证码", "Z8Q-3362"),
]


def make_needle_para(label, code):
    return f"【重要通知】{label}为 {code}，请相关人员立即记录并妥善保管。"


def insert_needle(paras, needle_para, pos):
    """把针插入到 pos 指定的相对位置。"""
    idx = round(pos * len(paras))
    idx = max(0, min(len(paras), idx))
    return paras[:idx] + [needle_para] + paras[idx:]


# ============================================================
# 调用与判定
# ============================================================

SYSTEM = """你是一个文档问答助手。
请仅根据用户提供的文档内容回答问题，并以 json 格式输出结果：

{"answer": "从文档中找到的答案原文；如果文档中没有相关信息，填「未找到」"}

只输出这个 json，不要有其他内容。"""


def ask_with_context(context_text, question):
    user_content = f"""以下是文档内容：

{context_text}

---

问题：{question}"""

    kwargs = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 512,
        "extra_body": {"thinking": {"type": CFG["thinking"]}},
    }
    if CFG.get("temperature") is not None:
        kwargs["temperature"] = CFG["temperature"]

    start = time.time()
    resp = client.chat.completions.create(**kwargs)
    return resp, time.time() - start


def extract_answer(raw_text):
    if not raw_text:
        return None
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    ans = data.get("answer")
    return str(ans) if ans is not None else None


def hit(answer, code):
    """答案里是否包含验证码（忽略大小写和空格）。"""
    if not answer:
        return False
    norm = answer.upper().replace(" ", "").replace("-", "")
    return code.upper().replace("-", "") in norm


# ============================================================
# ① sanity check
# ============================================================

def run_sanity():
    print("=" * 78)
    print("① Sanity check：只放针，不放废话")
    print("=" * 78)

    ok_count = 0
    for label, code in NEEDLES:
        needle = make_needle_para(label, code)
        question = f"{label}是什么？"
        resp, _ = ask_with_context(needle, question)
        ans = extract_answer(resp.choices[0].message.content)
        passed = hit(ans, code)
        ok_count += int(passed)
        print(f"  {label:<14} 期望={code:<10} 得到={ans!r:<14} "
              f"{'✓' if passed else '✗'}")

    print(f"\n  {ok_count}/{len(NEEDLES)} 通过")
    if ok_count < len(NEEDLES):
        print("  ⚠ sanity check 没全过，后面的位置实验意义不大，先查 prompt / 判定")
    return ok_count == len(NEEDLES)


# ============================================================
# ② 位置实验
# ============================================================

def run_position_experiment():
    print()
    print("=" * 78)
    print("② 位置实验")
    print("=" * 78)

    filler = make_filler(N_FILLER)
    print(f"  填充段落数: {len(filler)}")

    records = []
    total_cost = 0.0

    for label, code in NEEDLES:
        needle = make_needle_para(label, code)
        question = f"{label}是什么？"

        for pos in POSITIONS:
            paras = insert_needle(filler, needle, pos)
            context_text = "\n".join(paras)

            resp, elapsed = ask_with_context(context_text, question)
            info = calc_cost(resp.usage)
            total_cost += info["cost"]

            ans = extract_answer(resp.choices[0].message.content)
            ok = hit(ans, code)

            records.append({
                "label": label,
                "code": code,
                "pos": pos,
                "answer": ans,
                "ok": ok,
                "prompt_tokens": info["prompt"],
                "cost": info["cost"],
                "time_s": elapsed,
            })

            print(f"  {label:<14} pos={pos:<5} 输入={info['prompt']:>6}tok  "
                  f"答案={str(ans)[:24]:<26} {'✓' if ok else '✗'}  {elapsed:>5.1f}s")

    return records, total_cost


# ============================================================
# ③ 汇总与可视化
# ============================================================

def summarize(records):
    print()
    print("=" * 78)
    print("③ 按位置汇总")
    print("=" * 78)

    by_pos = {}
    for r in records:
        by_pos.setdefault(r["pos"], []).append(r)

    print(f"  {'位置':<8}{'准确率':>10}   {'命中/总数':>10}   柱状图")
    print("  " + "-" * 62)

    summary = {}
    for pos in POSITIONS:
        rs = by_pos[pos]
        ok = sum(1 for r in rs if r["ok"])
        acc = ok / len(rs)
        bars = "█" * round(acc * 20)
        empty = "░" * (20 - len(bars))
        print(f"  {pos:<8.2f}{acc:>9.0%}   {ok:>4}/{len(rs):<6}   {bars}{empty}")
        summary[pos] = {"accuracy": acc, "ok": ok, "total": len(rs)}

    # 位置效应强度
    accs = [summary[p]["accuracy"] for p in POSITIONS]
    mid = summary[0.5]["accuracy"]
    edges = max(summary[0.0]["accuracy"], summary[1.0]["accuracy"])
    print()
    print(f"  开头/结尾最好值: {edges:.0%}")
    print(f"  中间值:          {mid:.0%}")
    print(f"  位置效应（边缘 - 中间）: {edges - mid:+.0%}")

    if abs(edges - mid) < 0.001:
        print("  → 没有观察到位置效应。可能原因见分析部分")
    elif mid < edges:
        print("  → 观察到 U 形趋势：中间最差，符合 Lost in the Middle")
    else:
        print("  → 反常结果：中间反而更好，值得再看看样本")

    # 输入规模
    prompts = [r["prompt_tokens"] for r in records]
    print()
    print(f"  实际输入规模: 平均 {sum(prompts) / len(prompts):.0f} tokens  "
          f"（范围 {min(prompts)} - {max(prompts)}）")

    return summary


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    started = time.time()

    sanity_ok = run_sanity()

    records, total_cost = run_position_experiment()
    summary = summarize(records)

    os.makedirs("results", exist_ok=True)
    path = "results/day11_lost_in_middle.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "name": "day11_lost_in_middle",
            "created_at": datetime.now().isoformat(),
            "config": {
                "n_filler": N_FILLER,
                "positions": POSITIONS,
                "seed": SEED,
                "thinking": CFG["thinking"],
                "temperature": CFG.get("temperature"),
                "model": MODEL,
            },
            "sanity_ok": sanity_ok,
            "summary": {str(k): v for k, v in summary.items()},
            "total_cost": total_cost,
            "records": records,
        }, f, ensure_ascii=False, indent=2)

    print()
    print(f"  总成本: ${total_cost:.6f}  ≈ ¥{total_cost * 7.2:.4f}")
    print(f"  结果已保存到 {path}")
    print(f"  总耗时 {time.time() - started:.1f}s")