import json
import time

from common import MODEL, client

THINKING = "disabled"

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
    }
]

TOOL_MAP = {"get_weather": get_weather}


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
    """执行一批工具调用，返回 [(tool_call_id, result), ...]"""
    out = []

    for tc in tool_calls:
        name = tc.function.name
        raw_args = tc.function.arguments

        print(f"    → 执行 {name}({raw_args})")

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
        except Exception as e:
            result = {"error": f"工具执行失败: {type(e).__name__}: {e}"}

        print(f"      ← {json.dumps(result, ensure_ascii=False)}")
        out.append((tc.id, result))

    return out


def run(user_text, max_rounds=1, verbose=True):
    """执行一次完整的工具调用闭环。"""
    messages = [{"role": "user", "content": user_text}]

    print()
    print("=" * 78)
    print(f"问题: {user_text}")
    print("=" * 78)

    for round_no in range(1, max_rounds + 1):
        print(f"\n  ── 第 {round_no} 轮调用 ──")

        t0 = time.time()
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            max_tokens=2048,
            extra_body={"thinking": {"type": THINKING}},
        )
        elapsed = time.time() - t0

        choice = resp.choices[0]
        msg = choice.message

        print(f"  finish_reason = {choice.finish_reason!r}")
        print(f"  content       = {msg.content!r}")

        # 没有工具调用 → 结束
        if not getattr(msg, "tool_calls", None):
            print(f"\n  【最终答案】{msg.content}")
            print(f"  耗时 {elapsed:.2f}s")
            return msg.content

        print(f"  tool_calls    = {len(msg.tool_calls)} 个")

        # 1. 回填 assistant 消息
        messages.append(assistant_msg_to_dict(msg))

        # 2. 执行工具
        results = execute_tools(msg.tool_calls)

        # 3. 回填 tool 消息
        for call_id, result in results:
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False),
            })

        if verbose:
            print(f"\n  当前消息数: {len(messages)}")
            for m in messages:
                role = m["role"]
                if role == "tool":
                    print(f"    [{role}] id={m['tool_call_id'][:12]}... "
                          f"content={m['content'][:40]}")
                elif role == "assistant":
                    print(f"    [{role}] tool_calls={len(m.get('tool_calls', []))} 个")
                else:
                    print(f"    [{role}] {str(m.get('content'))[:40]}")

    print("\n  ⚠ 达到最大轮数，未得到最终答案")
    return None


if __name__ == "__main__":

    # 实验 1：单城市，标准闭环
    run("北京现在天气怎么样？")

    # 实验 2：需要判断的城市（不在库里）
    run("拉萨现在天气怎么样？")

    # 实验 3：两个城市（看会不会一次返回 2 个 tool_calls）
    run("北京和上海现在的天气分别怎么样？")

    # 实验 4：隐式需要工具
    run("我今天去深圳出差，需要带伞吗？")

    # 实验 5：不需要工具
    run("你好，请介绍一下你自己。")