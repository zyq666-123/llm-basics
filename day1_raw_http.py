import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()  # 把 .env 里的键值对读进环境变量

API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not API_KEY:
    raise SystemExit("没读到 DEEPSEEK_API_KEY，检查 .env 是否存在、变量名是否一致")

URL = "https://api.deepseek.com/chat/completions"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}

body = {
    "model": "deepseek-flash",
    "messages": [
        {"role": "system", "content": "你是一个简洁的助手，回答不超过两句话。"},
        {"role": "user", "content": "用一句话解释什么是 HTTP。"},
    ],
    "stream": False,
}

resp = httpx.post(URL, headers=headers, json=body, timeout=60)

print("状态码:", resp.status_code)
print("=" * 60)
print(json.dumps(resp.json(), ensure_ascii=False, indent=2))