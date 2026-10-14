import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
URL = "https://api.deepseek.com/chat/completions"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}

body = {
    "model": "deepseek-flash",
    "messages": [{"role": "user", "content": "用两句话解释递归。"}],
    "stream": True,
}


# ============================================================
# 第一部分：看响应头 —— 确认这真的是 SSE
# ============================================================
print("=" * 60)
print("第一部分：响应头")
print("=" * 60)

with httpx.stream("POST", URL, headers=headers, json=body, timeout=60) as resp:
    print("状态码:", resp.status_code)
    print("Content-Type:", resp.headers.get("content-type"))
    # 把响应读完再退出，否则连接会悬着
    for _ in resp.iter_lines():
        pass


# ============================================================
# 第二部分：逐行打印原始 SSE —— 看清协议长什么样
# ============================================================
print()
print("=" * 60)
print("第二部分：原始 SSE（前 12 行）")
print("=" * 60)

with httpx.stream("POST", URL, headers=headers, json=body, timeout=60) as resp:
    for i, line in enumerate(resp.iter_lines()):
        print(f"{i:02} {repr(line)}")
        if i >= 11:
            break


# ============================================================
# 第三部分：手工解析 —— 不用 SDK，自己拼出完整回答
# ============================================================
print()
print("=" * 60)
print("第三部分：手工解析")
print("=" * 60)

with httpx.stream("POST", URL, headers=headers, json=body, timeout=60) as resp:
    full = ""
    chunk_count = 0

    for line in resp.iter_lines():

        if not line:
            continue                              # 空行是事件分隔符

        if not line.startswith("data: "):
            continue                              # 非数据行，跳过

        payload = line[len("data: "):]            # 剥掉 "data: " 前缀

        if payload == "[DONE]":                   # 结束标记
            break

        chunk = json.loads(payload)

        # usage 块可能没有 choices
        if chunk.get("usage"):
            print(f"\n\n[usage] {chunk['usage']}")

        choices = chunk.get("choices")
        if not choices:
            continue

        content = choices[0]["delta"].get("content")
        if content:
            chunk_count += 1
            full += content
            print(content, end="", flush=True)

    print()
    print("-" * 60)
    print(f"共收到 {chunk_count} 个增量块")
    print(f"拼出 {len(full)} 个字")
    print(f"完整文本：{full}")
