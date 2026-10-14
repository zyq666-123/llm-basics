import os
import json

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

MODEL = "deepseek-flash"
QUESTION = "用三句话解释什么是递归。"

def ask_normal(question):
    resp =client.chat.completions.create(
        model =MODEL,
        messages =[{"role":"user","content":question}],
        temperature =0,
    )
    return resp.choices[0].message.content
def ask_stream(question):
    stream =client.chat.completions.create(
        model =MODEL,
        messages =[{"role":"user","content":question}],
        stream =True,
        temperature =0,
    )
    full =""
    for chunk in stream:
        content =chunk.choices[0].delta.content
        if content:
            full+=content
            print(content,end="",flush =True)
    print()
    return full
if __name__ =="__main__":
    print("="*50)
    print("【流式】")
    print("="*50)
    streamed =ask_stream(QUESTION)
    print()
    print("="*50)
    print("【非流式】")
    normal =ask_normal(QUESTION)
    print(normal)
    print()
    print("="*50)
    print("【对比】")
    print("="*50)
    print("流式拼出来的长度:",len(streamed))
    print("非流式拼出来的长度:",len(normal))
    print("两者一致吗？:",streamed==normal)
