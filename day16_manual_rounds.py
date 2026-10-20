import json
import os
import re

from common import MODEL, client

THINKING = "disabled"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SANDBOX_DIR = os.path.join(BASE_DIR, "sandbox")

MAX_ROUNDS = 5          # 硬编码的上限——今天就是为了让你看见它的局限


# ============================================================
# 工具 1：天气
# ============================================================

WEATHER_DB = {
    "北京": {"condition": "晴", "temp_c": 18, "humidity": 35},
    "上海": {"condition": "多云", "temp_c": 22, "humidity": 60},
    "深圳": {"condition": "雷阵雨", "temp_c": 28, "humidity": 85},
    "成都": {"condition": "阴", "temp_c": 20, "humidity": 70},
}


def get_weather(city: str, unit: str = "celsius"):
    data = WEATHER_DB.get(city)
    if data is None:
        return {
            "error": f"不支持的城市: {city}",
            "supported_cities": list(WEATHER_DB.keys()),
        }

    temp = data["temp_c"]
    if unit == "fahrenheit":
        temp = round(temp * 9 / 5 + 32)

    return {
        "city": city,
        "condition": data["condition"],
        "temperature": temp,
        "unit": unit,
        "humidity": data["humidity"],
    }


# ============================================================
# 工具 2：计算器（安全版）
# ============================================================

ALLOWED_EXPR = re.compile(r"^[0-9+\-*/(). ]+$")


def calculator(expression: str):
    expr = str(expression).strip()

    if not expr:
        return {"error": "表达式为空"}

    if not ALLOWED_EXPR.fullmatch(expr):
        return {"error": "只支持数字和 + - * / ( )，不接受字母或其他符号"}

    try:
        value = eval(expr, {"__builtins__": {}}, {})
    except ZeroDivisionError:
        return {"error": "除以零"}
    except Exception as e:
        return {"error": f"计算失败: {type(e).__name__}: {e}"}

    return {"expression": expr, "result": value}


# ============================================================
# 工具 3：读文件（沙箱内）
# ============================================================

def read_file(path: str):
    full = os.path.abspath(os.path.join(SANDBOX_DIR, str(path)))

    if not full.startswith(SANDBOX_DIR + os.sep):
        return {"error": "拒绝访问：路径超出允许范围"}

    if not os.path.isfile(full):
        try:
            available = os.listdir(SANDBOX_DIR)
        except OSError:
            available = []
        return {"error": f"文件不存在: {path}", "available_files": available}

    try:
        with open(full, encoding="utf-8") as f:
            text = f.read(4000)
    except Exception as e:
        return {"error": f"读取失败: {type(e).__name__}: {e}"}

    return {
        "path": path,
        "content": text,
        "truncated": len(text) >= 4000,
    }


# ============================================================
# 注册表
# ============================================================

TOOL_MAP = {
    "get_weather": get_weather,
    "calculator": calculator,
    "read_file": read_file,
}


# ============================================================
# 三份 schema
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": (
                "查询指定城市的实时天气情况。"
                "当用户询问某地天气、气温、是否下雨、是否需要带伞时使用。"
                "不要用于查询历史天气或未来多日预报。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，中文，例如：北京、上海、深圳",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "温度单位，默认摄氏度",
                    },
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": (
                "执行四则运算并返回精确结果。"
                "当需要精确计算（尤其是较大数字的乘除、多个数连续运算）时使用。"
                "只支持数字和 + - * / ( )，不支持函数、变量或单位换算。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "要计算的数学表达式，例如：1234*5678 或 (35+12)/2",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "读取沙箱目录下的文本文件内容。"
                "当用户提到某个文件名、要求查看或总结本地文档时使用。"
                "只支持文本文件，且只能读取沙箱目录内的文件。"
                "不要用于写入、删除或列出目录。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "沙箱内的相对路径，例如：notes.txt",
                    },
                },
                "required": ["path"],
            },
        },
    },
]


# ============================================================
# 消息与工具执行
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


def execute_tools(tool_calls):
    out = []

    for tc in tool_calls:
        name = tc.function.name
        raw_args = tc.function.arguments

        print(f"      → {name}({raw_args})")

        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError as e:
            out.append((tc.id, {"error": f"参数不是合法 JSON: {e}"}))
            continue

        func = TOOL_MAP.get(name)
        if func is None:
            out.append((tc.id, {"error": f"未知工具: {name}"}))
            continue

        try:
            result = func(**args)
        except TypeError as e:
            result = {"error": f"参数不匹配: {e}"}
        except Exception as e:
            result = {"error": f"工具执行失败: {type(e).__name__}: {e}"}

        print(f"        ← {json.dumps(result, ensure_ascii=False)[:110]}")
        out.append((tc.id, result))

    return out


# ============================================================
# 一次调用 + 一次吸收
# ============================================================

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


def log(resp):
    ch = resp.choices[0]
    msg = ch.message
    print(f"  finish_reason = {ch.finish_reason!r}")
    if getattr(msg, "tool_calls", None):
        for tc in msg.tool_calls:
            print(f"  tool_call: {tc.function.name}({tc.function.arguments})")
    else:
        print(f"  content = {msg.content!r}")


def absorb(messages, resp):
    """把 assistant 消息和所有 tool 消息追加进历史。"""
    msg = resp.choices[0].message
    messages.append(assistant_msg_to_dict(msg))
    for cid, res in execute_tools(msg.tool_calls):
        messages.append({
            "role": "tool",
            "tool_call_id": cid,
            "content": json.dumps(res, ensure_ascii=False),
        })


# ============================================================
# ★★★ 今天的主角：五段一模一样的代码 ★★★
# 唯一的区别是「第几轮」这个数字。
# 这就是 Day 17 要消灭的东西。
# ============================================================

def run_manual(question):
    messages = [{"role": "user", "content": question}]

    print()
    print("=" * 78)
    print(f"问题: {question}")
    print("=" * 78)

    # ────────────── 第 1 轮 ──────────────
    print("\n── 第 1 轮 ──")
    resp = call(messages)
    log(resp)
    if not has_tools(resp):
        answer = resp.choices[0].message.content
        print(f"\n【最终答案】{answer}")
        return {"rounds": 1, "messages": messages, "answer": answer}
    absorb(messages, resp)

    # ────────────── 第 2 轮 ──────────────
    print("\n── 第 2 轮 ──")
    resp = call(messages)
    log(resp)
    if not has_tools(resp):
        answer = resp.choices[0].message.content
        print(f"\n【最终答案】{answer}")
        return {"rounds": 2, "messages": messages, "answer": answer}
    absorb(messages, resp)

    # ────────────── 第 3 轮 ──────────────
    print("\n── 第 3 轮 ──")
    resp = call(messages)
    log(resp)
    if not has_tools(resp):
        answer = resp.choices[0].message.content
        print(f"\n【最终答案】{answer}")
        return {"rounds": 3, "messages": messages, "answer": answer}
    absorb(messages, resp)

    # ────────────── 第 4 轮 ──────────────
    print("\n── 第 4 轮 ──")
    resp = call(messages)
    log(resp)
    if not has_tools(resp):
        answer = resp.choices[0].message.content
        print(f"\n【最终答案】{answer}")
        return {"rounds": 4, "messages": messages, "answer": answer}
    absorb(messages, resp)

    # ────────────── 第 5 轮 ──────────────
    print("\n── 第 5 轮 ──")
    resp = call(messages)
    log(resp)
    if not has_tools(resp):
        answer = resp.choices[0].message.content
        print(f"\n【最终答案】{answer}")
        return {"rounds": 5, "messages": messages, "answer": answer}
    absorb(messages, resp)

    # 5 轮还没结束
    print(f"\n⚠ 已经 {MAX_ROUNDS} 轮了，任务还没结束")
    print("   如果它需要第 6 轮，我只能再复制一段——这就是今天的问题")
    return {"rounds": MAX_ROUNDS, "messages": messages, "answer": None,
            "exhausted": True}


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":

    TASKS = [
        "北京现在天气怎么样？",
        "notes.txt 里提到了哪几个城市？它们的天气分别怎么样？",
        "读一下 notes.txt，查一下里面所有城市的温度，"
        "然后用计算器算出这三个城市温度的总和",
    ]

    results = []

    for q in TASKS:
        r = run_manual(q)
        results.append((q, r))
        print(f"\n  >>> 用了 {r['rounds']} 轮，"
              f"最终消息数 {len(r['messages'])} 条")

    # ---------------- 汇总表 ----------------
    print()
    print("=" * 78)
    print("汇总：同一个程序，轮数却不一样")
    print("=" * 78)
    print(f"  {'轮数':>4}  {'消息数':>6}  {'状态':<8}  问题")
    print("  " + "-" * 70)

    for q, r in results:
        status = "未结束" if r.get("exhausted") else "完成"
        print(f"  {r['rounds']:>4}  {len(r['messages']):>6}  {status:<8}  "
              f"{q[:38]}")

    print()
    rounds = [r["rounds"] for _, r in results]
    print(f"  轮数范围: {min(rounds)} ~ {max(rounds)}")
    print(f"  如果上限写死成 {min(rounds)}，任务 3 会失败")
    print(f"  如果上限写死成 {max(rounds)}，那明天换个更难的任务就又要改代码")
    print()
    print("  → 轮数不是常量，所以必须用循环")