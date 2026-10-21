import json
import time

from common import MODEL, calc_cost, client
from tools import TOOLS, execute_tools

THINKING = "disabled"

DEFAULT_MAX_ROUNDS = 8
DEFAULT_MAX_SECONDS = 60.0
DEFAULT_MAX_COST = 0.05          # 美元
DEFAULT_REPEAT_THRESHOLD = 2

# 单次 HTTP 请求的超时（秒）
CALL_TIMEOUT = 30.0


# ============================================================
# 协议胶水（和 Day 17 一样）
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


def call(messages, timeout=CALL_TIMEOUT):
    return client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        max_tokens=2048,
        timeout=timeout,
        extra_body={"thinking": {"type": THINKING}},
    )


def has_tools(resp):
    return bool(getattr(resp.choices[0].message, "tool_calls", None))


def absorb(messages, resp, verbose=False):
    msg = resp.choices[0].message
    messages.append(assistant_msg_to_dict(msg))
    for cid, res in execute_tools(msg.tool_calls, verbose=verbose):
        messages.append({
            "role": "tool",
            "tool_call_id": cid,
            "content": json.dumps(res, ensure_ascii=False),
        })


def signature(tool_calls):
    """把一轮的工具调用压成一个可比较的签名。"""
    return tuple(
        (tc.function.name, tc.function.arguments)
        for tc in tool_calls
    )


# ============================================================
# 兜底：强制收尾
# ============================================================

REASON_HINT = {
    "max_rounds": "已达到最大工具调用步数",
    "budget_time": "已达到本次任务的耗时上限",
    "budget_cost": "已达到本次任务的成本上限",
    "repeat": "检测到重复的工具调用，继续下去不会有新信息",
    "error": "工具调用过程中出现异常",
}


def force_final_answer(messages, stop_reason):
    """去掉 tools，逼模型基于已有信息作答。"""
    hint = REASON_HINT.get(stop_reason, "流程被中止")
    msgs = messages + [{
        "role": "user",
        "content": (
            f"（系统提示：{hint}。）"
            "请不要再调用任何工具，直接根据目前已知的信息给出最终回答。"
            "如果信息不足，请明确说明还缺什么。"
        ),
    }]

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=msgs,
            max_tokens=1024,
            timeout=CALL_TIMEOUT,
            extra_body={"thinking": {"type": THINKING}},
            # ★ 故意不传 tools
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[无法生成回答：{type(e).__name__}: {e}]"


# ============================================================
# 主循环：四道预算 + 兜底
# ============================================================

def run(question,
        max_rounds=DEFAULT_MAX_ROUNDS,
        max_seconds=DEFAULT_MAX_SECONDS,
        max_cost=DEFAULT_MAX_COST,
        repeat_threshold=DEFAULT_REPEAT_THRESHOLD,
        verbose=True):

    messages = [{"role": "user", "content": question}]
    trace = {
        "question": question,
        "rounds": 0,
        "stop_reason": None,
        "answer": None,
        "degraded": False,
        "steps": [],
        "total_cost": 0.0,
        "elapsed": 0.0,
    }

    started = time.time()
    last_sig = None
    repeat_count = 0

    if verbose:
        print()
        print("=" * 78)
        print(f"问题: {question}")
        print("=" * 78)

    for round_no in range(1, max_rounds + 1):
        trace["rounds"] = round_no

        # ── 预算检查（进入新一轮之前）──
        elapsed = time.time() - started
        if elapsed > max_seconds:
            trace["stop_reason"] = "budget_time"
            break
        if trace["total_cost"] > max_cost:
            trace["stop_reason"] = "budget_cost"
            break

        # ── 调用 ──
        t0 = time.time()
        try:
            resp = call(messages)
        except Exception as e:
            trace["stop_reason"] = "error"
            trace["error"] = f"{type(e).__name__}: {e}"
            break

        dt = time.time() - t0
        info = calc_cost(resp.usage)
        trace["total_cost"] += info["cost"]

        msg = resp.choices[0].message

        if verbose:
            print(f"  ── 第 {round_no} 轮  {dt:.2f}s  "
                  f"${info['cost']:.6f}  finish={resp.choices[0].finish_reason!r}")

        # ── 正常终止 ──
        if not has_tools(resp):
            trace["stop_reason"] = "stop"
            trace["answer"] = msg.content
            trace["elapsed"] = time.time() - started
            if verbose:
                print(f"\n  【最终答案】{msg.content}")
                print(f"  {trace['elapsed']:.1f}s  ${trace['total_cost']:.6f}")
            return trace

        # ── 重复检测 ──
        sig = signature(msg.tool_calls)
        if sig == last_sig:
            repeat_count += 1
        else:
            repeat_count = 1
            last_sig = sig

        names = [tc.function.name for tc in msg.tool_calls]
        trace["steps"].append({
            "round": round_no,
            "tools": names,
            "cost": info["cost"],
            "elapsed": dt,
            "repeat": repeat_count,
        })

        if verbose:
            print(f"      工具: {names}  重复计数: {repeat_count}")

        if repeat_count >= repeat_threshold:
            trace["stop_reason"] = "repeat"
            break

        absorb(messages, resp, verbose=verbose)

    # ── 循环退出：可能是 break，也可能是走完了所有轮次 ──
    if trace["stop_reason"] is None:
        trace["stop_reason"] = "max_rounds"

    trace["elapsed"] = time.time() - started
    trace["degraded"] = True

    if verbose:
        print(f"\n  ⚠ 提前终止: {trace['stop_reason']}")
        print("  → 触发兜底，强制生成最终回答")

    trace["answer"] = force_final_answer(messages, trace["stop_reason"])

    if verbose:
        print(f"\n  【降级答案】{trace['answer']}")
        print(f"  {trace['elapsed']:.1f}s  ${trace['total_cost']:.6f}")

    return trace
if __name__ == "__main__":

    def report(label, tr):
        print()
        print("-" * 78)
        print(f"  测试: {label}")
        print(f"  终止原因 : {tr['stop_reason']}")
        print(f"  轮数     : {tr['rounds']}")
        print(f"  降级     : {tr['degraded']}")
        print(f"  成本     : ${tr['total_cost']:.6f}")
        print(f"  耗时     : {tr['elapsed']:.1f}s")
        ans = str(tr["answer"])
        print(f"  答案     : {ans[:120]}{'...' if len(ans) > 120 else ''}")
        print("-" * 78)


    NORMAL = "北京现在天气怎么样？"
    MULTI = ("读一下 notes.txt，查一下里面所有城市的温度，"
             "然后用计算器算出这三个城市温度的总和")

    # ---- 注入 1：正常路径 ----
    report("正常任务（应该 stop）", run(NORMAL))

    # ---- 注入 2：步数预算过小 ----
    report("max_rounds=1（应该 max_rounds）", run(MULTI, max_rounds=1))

    # ---- 注入 3：成本预算过小 ----
    report("max_cost=1e-9（应该 budget_cost）",
           run(MULTI, max_cost=1e-9))

    # ---- 注入 4：时间预算过小 ----
    report("max_seconds=0.001（应该 budget_time）",
           run(MULTI, max_seconds=0.001))

    # ---- 注入 5：诱导重复 ----
    report("诱导重复调用（应该 repeat）",
           run("请每隔一轮就查询一次北京天气，连续查 10 次再告诉我结果",
               max_rounds=10))