import json

from common import MODEL, client
from tools import TOOLS, execute_tools

THINKING = "disabled"


# ============================================================
# 协议胶水（留在 agent 层，不属于工具）
# ============================================================

def assistant_msg_to_dict(msg):
    d = {"role": "assistant", "content": msg.content or ""}
    if getattr(msg, "reasoning_content", None):
        d["reasoning_content"] = msg.reasoning_content
    if getattr(msg, "tool_calls", None):
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return d


def call(messages):
    return client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        max_tokens=2048,
        extra_body={"thinking": {"type": THINKING}},
    )


def has_tools(resp):
    return bool(getattr(resp.choices[0].message, "tool_calls", None))


def absorb(messages, resp, verbose=False):
    """回填 assistant + 全部 tool 消息。"""
    msg = resp.choices[0].message
    messages.append(assistant_msg_to_dict(msg))
    for cid, res in execute_tools(msg.tool_calls, verbose=verbose):
        messages.append({
            "role": "tool",
            "tool_call_id": cid,
            "content": json.dumps(res, ensure_ascii=False),
        })
def run_v1(question, max_rounds=8, verbose=False):
    """while True + break"""
    messages = [{"role": "user", "content": question}]
    round_no = 0

    while True:
        round_no += 1
        if round_no > max_rounds:        # ← 靠这句保命
            return {"stop_reason": "max_rounds", "rounds": round_no - 1,
                    "answer": None}

        resp = call(messages)
        if not has_tools(resp):
            return {"stop_reason": "stop", "rounds": round_no,
                    "answer": resp.choices[0].message.content}

        if verbose:
            print(f"  第 {round_no} 轮: "
                  f"{[tc.function.name for tc in resp.choices[0].message.tool_calls]}")
        absorb(messages, resp, verbose=verbose)
def run_v2(question, max_rounds=8, verbose=False):
    """while 计数器"""
    messages = [{"role": "user", "content": question}]
    round_no = 0

    while round_no < max_rounds:
        round_no += 1
        resp = call(messages)
        if not has_tools(resp):
            return {"stop_reason": "stop", "rounds": round_no,
                    "answer": resp.choices[0].message.content}
        if verbose:
            print(f"  第 {round_no} 轮: "
                  f"{[tc.function.name for tc in resp.choices[0].message.tool_calls]}")
        absorb(messages, resp, verbose=verbose)

    return {"stop_reason": "max_rounds", "rounds": round_no, "answer": None}
def run(question, max_rounds=8, verbose=False):
    """for + range —— 最终版本"""
    messages = [{"role": "user", "content": question}]
    trace = {"question": question, "rounds": 0, "stop_reason": None,
             "answer": None, "steps": []}

    for round_no in range(1, max_rounds + 1):
        trace["rounds"] = round_no

        try:
            resp = call(messages)
        except Exception as e:
            trace["stop_reason"] = f"error:{type(e).__name__}"
            trace["error"] = str(e)
            return trace

        msg = resp.choices[0].message

        if not has_tools(resp):
            trace["stop_reason"] = "stop"
            trace["answer"] = msg.content
            return trace

        names = [tc.function.name for tc in msg.tool_calls]
        trace["steps"].append({"round": round_no, "tools": names})

        if verbose:
            print(f"  第 {round_no} 轮: {names}")

        absorb(messages, resp, verbose=verbose)

    trace["stop_reason"] = "max_rounds"
    return trace
if __name__ == "__main__":

    QUESTION = ("读一下 notes.txt，查一下里面所有城市的温度，"
                "然后用计算器算出这三个城市温度的总和")

    print("=" * 78)
    print("版本 1：while True")
    print("=" * 78)
    r1 = run_v1(QUESTION, verbose=True)
    print(f"  → {r1['stop_reason']}，{r1['rounds']} 轮")

    print()
    print("=" * 78)
    print("版本 2：while 计数器")
    print("=" * 78)
    r2 = run_v2(QUESTION, verbose=True)
    print(f"  → {r2['stop_reason']}，{r2['rounds']} 轮")

    print()
    print("=" * 78)
    print("版本 3：for range")
    print("=" * 78)
    r3 = run(QUESTION, verbose=True)
    print(f"  → {r3['stop_reason']}，{r3['rounds']} 轮")
    print(f"    steps: {r3['steps']}")
    print(f"\n【最终答案】{r3['answer']}")

    print()
    print("=" * 78)
    print("对比")
    print("=" * 78)
    print(f"  v1: {r1['rounds']} 轮, {r1['stop_reason']}")
    print(f"  v2: {r2['rounds']} 轮, {r2['stop_reason']}")
    print(f"  v3: {r3['rounds']} 轮, {r3['stop_reason']}")
    r = run("北京现在天气怎么样？", verbose=True)
    # 期望：stop_reason='stop'，1 轮
    r = run("北京现在天气怎么样？", verbose=True)
    # 期望：stop_reason='stop'，1 轮