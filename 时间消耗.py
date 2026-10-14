import os
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

MODEL = "deepseek-flash"
QUESTION = "用五句话解释什么是递归。"


# ============================================================
# 测量函数
# ============================================================

def run_normal(question):
    """非流式：只有总耗时。"""
    start = time.time()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": question}],
        temperature=0,
    )
    total = time.time() - start
    return resp.choices[0].message.content, total


def run_stream(question):
    """流式：记录首字延迟 + 总耗时，边打印边拼接。"""
    start = time.time()
    ttft = None
    full = ""
    chunk_count = 0
    usage = None

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": question}],
        stream=True,
        temperature=0,
    )

    for chunk in stream:
        if getattr(chunk, "usage", None):
            usage = chunk.usage

        if not chunk.choices:
            continue

        content = chunk.choices[0].delta.content
        if content:
            if ttft is None:
                ttft = time.time() - start   # 第一个有内容的块 = 首字
            chunk_count += 1
            full += content
            print(content, end="", flush=True)

    total = time.time() - start
    print()
    return {"ttft": ttft, "total": total, "chunks": chunk_count, "usage": usage}


def inspect_chunks(question, head=5, tail=3):
    """观察每一块的结构，只看开头几块和结尾几块。"""
    info = []
    usage = None

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": question}],
        stream=True,
        temperature=0,
    )

    for chunk in stream:
        if getattr(chunk, "usage", None):
            usage = chunk.usage

        if not chunk.choices:
            info.append({"no_choices": True})
            continue

        delta = chunk.choices[0].delta
        info.append({
            "no_choices": False,
            "content": delta.content,
            "reasoning": getattr(delta, "reasoning_content", None),
            "finish": chunk.choices[0].finish_reason,
        })

    def show(i, d):
        if d.get("no_choices"):
            print(f"  [{i:03}] （没有 choices，可能是 usage 块）")
        else:
            print(
                f"  [{i:03}] content={d['content']!r} "
                f"reasoning={d['reasoning']!r} "
                f"finish={d['finish']!r}"
            )

    print(f"  --- 前 {head} 块 ---")
    for i, d in enumerate(info[:head]):
        show(i, d)

    if len(info) > head + tail:
        print(f"  ... 中间省略 {len(info) - head - tail} 块 ...")

    print(f"  --- 末 {tail} 块 ---")
    for i, d in enumerate(info[-tail:], start=max(0, len(info) - tail)):
        show(i, d)

    print()
    print(f"  总块数: {len(info)}")
    print(f"  usage:  {usage}")


# ============================================================
# 主流程
# ============================================================

if __name__ == "__main__":

    print("=" * 62)
    print("① 流式")
    print("=" * 62)
    s = run_stream(QUESTION)

    print()
    print("=" * 62)
    print("② 非流式")
    print("=" * 62)
    text, n_total = run_normal(QUESTION)
    print(text)

    print()
    print("=" * 62)
    print("③ 对比")
    print("=" * 62)
    print(f"  {'':8}{'首字延迟':>14}{'总耗时':>14}")
    print(f"  {'非流式':8}{'—':>14}{n_total:>13.2f}s")
    print(f"  {'流式':8}{s['ttft']:>13.2f}s{s['total']:>13.2f}s")

    if s["ttft"]:
        ratio = n_total / s["ttft"]
        print(f"\n  用户感知等待时间缩短了约 {ratio:.1f} 倍")
        print(f"  （总耗时几乎一样：{s['total']:.2f}s vs {n_total:.2f}s）")

    print()
    print("=" * 62)
    print("④ chunk 结构")
    print("=" * 62)
    inspect_chunks(QUESTION)