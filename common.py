# common.py
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = "deepseek-flash"

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

PRICE = {
    "peak":     {"cache_hit": 0.006, "cache_miss": 0.30, "output": 1.20},
    "off_peak": {"cache_hit": 0.003, "cache_miss": 0.15, "output": 0.60},
}


def calc_cost(usage, price=None):
    """根据 usage 算这次请求花了多少美元。"""
    price = price or PRICE["peak"]

    cached = getattr(usage, "prompt_cache_hit_tokens", None)
    if cached is None:
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) if details else 0
    cached = cached or 0

    details = getattr(usage, "completion_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", 0) if details else 0
    reasoning = reasoning or 0

    cost = (
        (usage.prompt_tokens - cached) / 1_000_000 * price["cache_miss"]
        + cached / 1_000_000 * price["cache_hit"]
        + usage.completion_tokens / 1_000_000 * price["output"]
    )

    return {
        "prompt": usage.prompt_tokens,
        "cached": cached,
        "completion": usage.completion_tokens,
        "reasoning": reasoning,
        "cost": cost,
    }