import os, requests
from dotenv import load_dotenv
load_dotenv()

base = os.environ["NEBIUS_BASE_URL"].rstrip("/")
r = requests.post(base + "/chat/completions",
   headers={"Authorization": f"Bearer {os.environ['NEBIUS_API_KEY']}"},
   json={"model": os.environ["NEBIUS_MODEL"],
         "messages": [{"role": "user", "content": "Say OK"}]})
print("Nemotron:", r.status_code, r.text[:200])

from runagain.research import search
print("Tavily:", search("python 3.11 ModuleNotFoundError distutils")[:1])