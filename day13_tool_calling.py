import json
import time

from common import MODEL, client

# 先关掉思考模式：避免 reasoning_content 回传的复杂性，专注看协议
THINKING = "disabled"

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


def call_model(user_text, tools=None, label=""):
    """发一次请求，打印完整观察信息。"""
    kwargs = {
        "model": MODEL,
        "messages": [{"role": "user", "content": user_text}],
        "max_tokens": 2048,
        "extra_body": {"thinking": {"type": THINKING}},
    }
    if tools:
        kwargs["tools"] = tools

    print()
    print("=" * 78)
    print(f"{label}")
    print(f"  问题: {user_text}")
    print(f"  带 tools: {'是' if tools else '否'}")
    print("=" * 78)

    start = time.time()
    resp = client.chat.completions.create(**kwargs)
    elapsed = time.time() - start

    choice = resp.choices[0]
    msg = choice.message

    print(f"  finish_reason = {choice.finish_reason!r}")
    print(f"  content       = {msg.content!r}")
    print(f"  tool_calls    = ", end="")

    if not getattr(msg, "tool_calls", None):
        print("None")
    else:
        print(f"{len(msg.tool_calls)} 个")
        for i, tc in enumerate(msg.tool_calls):
            print(f"    [{i}] id        = {tc.id}")
            print(f"        type      = {tc.type}")
            print(f"        name      = {tc.function.name}")
            print(f"        arguments = {tc.function.arguments!r}")
            print(f"        arguments 类型 = {type(tc.function.arguments).__name__}")
            try:
                parsed = json.loads(tc.function.arguments)
                print(f"        json.loads 后   = {parsed}")
            except json.JSONDecodeError as e:
                print(f"        ⚠ JSON 解析失败: {e}")

    print(f"  usage: prompt={resp.usage.prompt_tokens} "
          f"completion={resp.usage.completion_tokens}  耗时={elapsed:.2f}s")
    print()

    return resp


if __name__ == "__main__":

    print("※ 今天不执行任何工具，只看模型返回了什么")


    # ---------- 实验 1：绝对需要外部信息 ----------
    call_model("北京现在天气怎么样？", tools=TOOLS,
               label="实验 1：需要外部信息")


    # ---------- 实验 2：完全不需要工具 ----------
    call_model("1 加 1 等于几？", tools=TOOLS,
               label="实验 2：不需要工具")


    # ---------- 实验 3：一次问两个城市 ----------
    call_model("北京和上海现在的天气分别怎么样？", tools=TOOLS,
               label="实验 3：可能需要多次调用")


    # ---------- 实验 4：需要隐式推理才发现要用工具 ----------
    call_model("我今天出门要不要带伞？", tools=TOOLS,
               label="实验 4：隐式需要工具")


    # ---------- 实验 5：同样的天气问题，但不给工具 ----------
    call_model("北京现在天气怎么样？", tools=None,
               label="实验 5：不给工具（对照组）")