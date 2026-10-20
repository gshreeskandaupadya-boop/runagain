import json, os, re, requests
from .schema import DECISION_SCHEMA, validate

SYSTEM = ("You repair environment drift in legacy Python repos. Given a failed run, "
          "choose exactly ONE bounded fix. Reply with JSON only matching the schema. "
          "Never rewrite program logic. Patches must be small compatibility changes.")

def decide(context: dict) -> dict:
    """context: traceback, dep files, prior attempts, tavily results. Returns validated decision."""
    r = requests.post(
        os.environ["NEBIUS_BASE_URL"].rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['NEBIUS_API_KEY']}"},
        json={"model": os.environ["NEBIUS_MODEL"], "temperature": 0.1,
              "messages": [{"role": "system", "content": SYSTEM + "\nSchema: " + json.dumps(DECISION_SCHEMA)},
                           {"role": "user", "content": json.dumps(context)[:24000]}]},
        timeout=120)
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    decision = json.loads(m.group(0))
    validate(decision)
    return decision
