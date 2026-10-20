import os, requests
from dotenv import load_dotenv
load_dotenv()

r = requests.get(os.environ["NEBIUS_BASE_URL"].rstrip("/") + "/models",
    headers={"Authorization": f"Bearer {os.environ['NEBIUS_API_KEY']}"})
print(r.status_code)
for m in r.json().get("data", []):
    if "nemotron" in m["id"].lower() or "nvidia" in m["id"].lower():
        print(m["id"])