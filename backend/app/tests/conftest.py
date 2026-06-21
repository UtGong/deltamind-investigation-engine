import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ["GEMINI_API_KEY"] = "test_key"
os.environ["GEMINI_MODEL"] = "gemini-test-model"

# Product default: LLM planner.
# In tests this uses MockLLMProvider, so no external API call occurs.
os.environ["SEARCH_PLANNER_PROVIDER"] = "llm"

os.environ["FREE_SEARCH_PROVIDER"] = "mock"
os.environ["PAID_SEARCH_PROVIDER"] = "tavily"
os.environ["ALLOW_PAID_SEARCH"] = "false"
os.environ["MAX_PAID_SEARCH_CALLS_PER_CASE"] = "0"

os.environ["TAVILY_API_KEY"] = "test_key"
os.environ["TAVILY_MAX_RESULTS"] = "5"
os.environ["TAVILY_SEARCH_DEPTH"] = "basic"
