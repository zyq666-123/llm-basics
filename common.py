import os
from dotenv import load_dotenv
from openai import OpenAI, base_url

load_dotenv()
MODEL = "deepseek-flash"
client =OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url ="https://api.deepseek.com",
)