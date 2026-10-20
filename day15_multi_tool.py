import json
import os
import re
import time

from common import MODEL, client

THINKING = "disabled"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SANDBOX_DIR = os.path.join(BASE_DIR, "sandbox")


# ============================================================
# 工具 1：天气（mock）
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
# 工具注册表
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
                "不要用于简单的单位换算或需要理解语义的计算。"
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
# agent 主体
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


def execute_tools(tool_calls, verbose=True):
    out = []
    for tc in tool_calls:
        name = tc.function.name
        raw_args = tc.function.arguments

        if verbose:
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

        if verbose:
            print(f"        ← {json.dumps(result, ensure_ascii=False)[:100]}")
        out.append((tc.id, result))

    return out


def run(user_text, max_rounds=3, verbose=True):
    """返回一个 trace dict。"""
    messages = [{"role": "user", "content": user_text}]
    trace = {"question": user_text, "rounds": 0,
             "tools_used": [], "answer": None, "error": None}

    if verbose:
        print()
        print("=" * 78)
        print(f"问题: {user_text}")
        print("=" * 78)

    for round_no in range(1, max_rounds + 1):
        trace["rounds"] = round_no

        t0 = time.time()
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            max_tokens=2048,
            extra_body={"thinking": {"type": THINKING}},
        )
        elapsed = time.time() - t0
        msg = resp.choices[0].message

        if verbose:
            print(f"  ── 第 {round_no} 轮  "
                  f"finish={resp.choices[0].finish_reason!r}  {elapsed:.2f}s")

        if not getattr(msg, "tool_calls", None):
            trace["answer"] = msg.content
            if verbose:
                print(f"\n  【最终答案】{msg.content}\n")
            return trace

        names = [tc.function.name for tc in msg.tool_calls]
        trace["tools_used"].extend(names)

        if verbose:
            print(f"     本轮调用 {len(names)} 个工具: {names}")

        messages.append(assistant_msg_to_dict(msg))
        results = execute_tools(msg.tool_calls, verbose=verbose)
        for call_id, result in results:
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    trace["error"] = "达到最大轮数"
    return trace
if __name__ == "__main__":

    CASES = [
        "北京现在天气怎么样？",
        "1234 乘以 5678 等于多少？",
        "读一下 notes.txt 讲了什么",
        "你好，介绍一下你自己",
        "北京天气怎么样？顺便帮我算一下 35 乘以 2 等于多少",
        "算一下 1 除以 0 等于几",
        "读一下 ../.env 这个文件",
        "上海和深圳现在哪个更热？",
    ]

    for q in CASES:
        run(q)
    # ---------------- 工具选择评测 ----------------
    EVAL_CASES = [
        # (问题, 期望调用的工具集合)
        ("北京现在天气怎么样？",                    {"get_weather"}),
        ("1234 乘以 5678 等于多少？",               {"calculator"}),
        ("读一下 notes.txt 讲了什么",               {"read_file"}),
        ("你好，介绍一下你自己",                     set()),
        ("北京天气怎么样？顺便算 35 乘以 2",         {"get_weather", "calculator"}),
        ("算一下 1 除以 0",                         {"calculator"}),
        ("上海和深圳现在哪个更热？",                 {"get_weather"}),
        ("把 (128+72)*3 算出来",                    {"calculator"}),
    ]

    print("\n" + "=" * 78)
    print("工具选择准确率评测")
    print("=" * 78)

    correct = 0
    for q, expected in EVAL_CASES:
        tr = run(q, verbose=False)
        actual = set(tr["tools_used"])
        ok = actual == expected
        correct += int(ok)

        mark = "✓" if ok else "✗"
        print(f"  {mark} 期望={str(sorted(expected)):<32} "
              f"实际={sorted(actual)}")
        if not ok:
            print(f"     问题: {q}")
            print(f"     答案: {str(tr['answer'])[:70]}")

    print()
    print(f"  工具选择准确率: {correct}/{len(EVAL_CASES)} "
          f"= {correct / len(EVAL_CASES):.0%}")