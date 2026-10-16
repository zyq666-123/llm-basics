import os
from dotenv import load_dotenv
from openai import OpenAI
from common import MODEL,client

load_dotenv()

MODEL ="deepseek-flash"
messages=[
    {"role":"system","content":"你是一个简洁的助手，回答不超过两句话。"}

]

while True:
    user_input =input("\n你:").strip()
    if user_input.lower() in ("exit","quit"):
        print("结束")
        break
    if user_input=="/clear":
        messages =messages[:1]
        print("[历史已清空]")
        continue
    if not user_input:
        continue
    messages.append({"role":"user","content":user_input})
    resp =client.chat.completions.create(model =MODEL,messages =messages)
    answer = resp.choices[0].message.content
    print(f"\nAI:{answer}")
    messages.append({"role":"assistant","content":answer})
    print(f"[消息数{len(messages)} |prompt_tokens{resp.usage.prompt_tokens}]")
print(f"   [本轮实际发出 {len(messages)} 条消息]")

