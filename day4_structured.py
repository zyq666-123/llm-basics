import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client =OpenAI(
    api_key =os.getenv("DEEPSEEK_API_KEY"),
    base_url ="https://api.deepseek.com",
)
MODEL ="deepseek-flash"
SYSTEM ="""你是一个简历信息抽取助手。
请从用户给出的文本中抽取信息，以json格式输出。

字段要求:
 - name:字符串，姓名
 - skills:字符串数组，技能列表
 - years:整数，工作年限
 json输出示例：
 {
    "name":"李四“,
    "skills":["Java","Mysql"],
    "years":3
    }
"""
def extract(text):
    resp = client.chat.completions.create(
        model =MODEL,
        messages =[
            {"role":"system","content":SYSTEM},
            {"role":"user","content":text},
        ],
        response_format ={"type":"json_object"},
        max_tokens =512
    )
    return resp.choices[0].message.content
raw =extract("今天天气不错。")
print("原始输出：")
print(repr(raw))
try:
    data =json.loads(raw)
    print("解析成功",data)
except json.JSONDecodeError as e:
    print("解析失败",e)
def validate(data):
    """返回错误列表，空列表表示通过。"""
    errors = []

    if not isinstance(data, dict):
        return ["顶层不是 JSON 对象"]

    if not isinstance(data.get("name"), str) or not data["name"]:
        errors.append("name 缺失或不是非空字符串")

    skills = data.get("skills")
    if not isinstance(skills, list) or not all(isinstance(s, str) for s in skills):
        errors.append("skills 缺失或不是字符串数组")

    years = data.get("years")
    if not isinstance(years, int) or isinstance(years, bool):
        errors.append("years 缺失或不是整数")

    return errors
CASES = [
    "张三，工作 5 年，会 Python、Go 和 Docker。",
    "李四，3 年经验，熟悉 Java 和 MySQL。",
    "王五，应届生，熟悉 Excel。",
    "赵六，十年经验，精通 Python。",
    "钱七，会 Java。",
    "孙八，工作 2 年，技能：React、TypeScript、Node.js。",
    "周九，8 年工作经验，擅长数据分析和 SQL。",
    "吴十，刚毕业，学过 C 语言。",
    "郑十一，有 15 年经验，主攻分布式系统。",
    "今天天气不错。",
]
ok = 0
for i, text in enumerate(CASES, 1):
    raw = extract(text)

    if not raw:                                  # ← 处理空返回
        print(f"{i:2}. [空返回] {text}")
        continue

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"{i:2}. [非法 JSON] {e}")
        continue

    errors = validate(data)
    if errors:
        print(f"{i:2}. [字段问题] {errors}  ->  {data}")
    else:
        ok += 1
        print(f"{i:2}. OK  {data}")

print(f"\n通过率: {ok}/{len(CASES)} = {ok / len(CASES):.0%}")

