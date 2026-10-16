#llm-basics
用Deepseek API学习LLM应用开发的基础练习：从裸HTTP请求。
到多轮对话。结构化输出，流式传输和成本核算。
##环境要求
-Pyrhon 3.10+
- 依赖：'httpx','openai','pyrhon-dotenv'
##安装
...bash
python -m venv.venv
- .venv\Scripts\activate
python -m pip install httpx openai pyrhon-dotenv
##配置
在项目根目录创建’.env':
DEEPSEEK_API_KEY =你的key
>'.enb'已在'.gitignore'中，不会被提交。
##文件说明
|文件|内容|
|---|---|
| `day1_raw_http.py` | 不用 SDK，裸 HTTP 调用。看清请求体结构和响应 JSON 的每一层 |
| `day2_sdk_chat.py` | 用 OpenAI SDK 重写，并实现多轮对话；验证"模型无状态" |
| `day3_system_prompt.py` | system prompt 实验：角色、格式约束、以及约束的边界 |
| `day4_structured.py` | JSON 模式 + 一个最小评测脚本（10 条用例的通过率） |
| `day5_stream.py` | 流式输出：delta 累加、TTFT 测量 |
| `day5_sse_raw.py` | 裸 HTTP 手工解析 SSE，不依赖 SDK |
| `day6_cost.py` | token 成本核算；多轮对话成本曲线与缓存命中率 |
##运行
~~~bash
python .....