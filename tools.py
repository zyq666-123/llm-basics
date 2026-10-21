"""工具层：所有工具的定义、schema、注册表和执行器。"""

import json
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SANDBOX_DIR = os.path.join(BASE_DIR, "sandbox")


# ============================================================
# 工具实现
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


ALLOWED_EXPR = re.compile(r"^[0-9+\-*/(). ]+$")


def calculator(expression: str):
    expr = str(expression).strip()
    if not expr:
        return {"error": "表达式为空"}
    if not ALLOWED_EXPR.fullmatch(expr):
        return {"error": "只支持数字和 + - * / ( )"}
    try:
        value = eval(expr, {"__builtins__": {}}, {})
    except ZeroDivisionError:
        return {"error": "除以零"}
    except Exception as e:
        return {"error": f"计算失败: {type(e).__name__}: {e}"}
    return {"expression": expr, "result": value}


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
    return {"path": path, "content": text, "truncated": len(text) >= 4000}


# ============================================================
# 注册表
# ============================================================

TOOL_MAP = {
    "get_weather": get_weather,
    "calculator": calculator,
    "read_file": read_file,
}


# ============================================================
# schema
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
                        "description": "要计算的数学表达式，例如：1234*5678",
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
# 执行器
# ============================================================

def execute_tools(tool_calls, verbose=False):
    """执行一批工具调用，返回 [(tool_call_id, result), ...]"""
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