import json, os, re, requests
from .schema import DECISION_SCHEMA, validate

SYSTEM = (
    "You repair environment drift in legacy Python repos, one bounded fix per turn. "
    "Reply with JSON only, matching the schema. Rules: "
    "(1) The image is python:<version>-slim (Debian); the build runs `pip install -r requirements` after optional apt packages. "
    "(2) When an old pinned package fails to build because no wheel exists for this Python, PREFER pip_pins to a newer version of that package that ships a wheel, "
    "or python_version to an older Python that the old package supports. Do not apt-install build tools or distutils for this. "
    "(3) Use apt_packages only for real Debian package names needed for a missing shared library; never guess names. "
    "(4) `patch` is ONLY a unified diff of repository source files (starts with 'diff ' or '---'); never put a Dockerfile in it. Leave it empty otherwise. "
    "(5) Look at rejected_changes and last_patch_result: never repeat a rejected change. "
    "(6) Omit unused fields from `change`; do not return empty strings. Never rewrite program logic. If no safe fix exists, strategy=give_up.")

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
