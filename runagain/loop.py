"""Bounded repair loop. Sandbox result is the source of truth: revived iff exit code == 0."""
import copy, json, os, re, subprocess, tempfile, time
from . import llm, research, sandbox

PKG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
VER_RE = re.compile(r"^[A-Za-z0-9_.!+*\-]+$")
APT_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]*$")
PY_RE = re.compile(r"^3\.\d{1,2}$")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def write_requirements(work: str, pins: dict) -> str | None:
    """Rewrite requirements with the agent's pins applied. Returns file name or None."""
    src = os.path.join(work, "requirements.txt")
    orig = open(src, encoding="utf-8", errors="ignore").read().splitlines() if os.path.exists(src) else []
    want = {_norm(k): (k, v) for k, v in pins.items()}
    out, seen = [], set()
    for line in orig:
        m = re.match(r"\s*([A-Za-z0-9_.\-]+)", line)
        n = _norm(m.group(1)) if m and not line.lstrip().startswith(("#", "-")) else None
        if n in want:
            out.append(f"{want[n][0]}=={want[n][1]}")
            seen.add(n)
        else:
            out.append(line)
    out += [f"{k}=={v}" for n, (k, v) in want.items() if n not in seen]
    if not out:
        return None
    name = "requirements.runagain.txt"
    open(os.path.join(work, name), "w", encoding="utf-8").write("\n".join(out) + "\n")
    return name


def failing_rank(res: dict) -> int:
    """Where in the Dockerfile the failure happened: apt=1, pip=2, run=3 (later = more progress)."""
    if res["stage"] == "run":
        return 3
    m = re.search(r'process "([^"]+)" did not complete', res["log"])
    cmd = m.group(1) if m else ""
    return 1 if "apt-get" in cmd else 2


def make_query(log: str, py: str) -> str:
    pkgs = re.findall(r"Collecting\s+(\S+)", log)
    if pkgs:
        return f"{pkgs[-1]} python {py} pip install build fails, compatible version with wheel"[:300]
    for line in reversed(log.strip().splitlines()):
        if re.search(r"(?i)error|exception|not found|no module", line) and "failed to solve" not in line \
                and "View build details" not in line:
            return f"python {py} {line.strip()}"[:300]
    return f"python {py} " + (log.strip().splitlines()[-1] if log.strip() else "error")[:200]


def apply_patch(work: str, patch: str) -> str:
    if len(patch) > 2000:
        return "rejected: patch too large"
    if not patch.lstrip().startswith(("diff ", "--- ")):
        return "rejected: patch must be a unified diff of repository source files (not a Dockerfile)"
    p = os.path.join(work, "revive_tmp.patch")
    open(p, "w", encoding="utf-8", newline="\n").write(patch if patch.endswith("\n") else patch + "\n")
    kw = dict(cwd=work, capture_output=True, encoding="utf-8", errors="replace")
    chk = subprocess.run(["git", "apply", "--check", p], **kw)
    if chk.returncode != 0:
        return "rejected: git apply --check failed: " + chk.stderr[:200]
    subprocess.run(["git", "apply", p], **kw)
    return "applied"


def reset_patches(work: str, patches: list) -> None:
    subprocess.run(["git", "checkout", "--", "."], cwd=work, capture_output=True)
    for p in patches:
        apply_patch(work, p)


def revive(repo_url: str, commit: str, verification_command: str, max_attempts: int | None = None) -> dict:
    max_attempts = max_attempts or int(os.getenv("MAX_ATTEMPTS", "5"))
    work = tempfile.mkdtemp(prefix="runagain_")
    subprocess.run(["git", "clone", "--quiet", repo_url, work], check=True, timeout=300)
    if commit:
        subprocess.run(["git", "checkout", "--quiet", commit], cwd=work, check=True)
    state = {"py": "3.11", "apt": [], "pins": {}, "patches": []}
    attempts, rejected = [], []
    prev_rank, last_good, last_state, last_decision, patch_note = None, None, None, None, None
    df = ""
    for i in range(1, max_attempts + 1):
        req = write_requirements(work, state["pins"])
        df = sandbox.base_dockerfile(state["py"], state["apt"], req)
        print(f"[attempt {i}] building and running (py={state['py']} apt={state['apt']} pins={state['pins']}) ...", flush=True)
        res = sandbox.run_in_sandbox(work, df, verification_command, f"runagain-{int(time.time())}-{i}")
        print(f"[attempt {i}] stage={res['stage']} exit={res['exit_code']}", flush=True)
        rec = {"attempt": i, "state": copy.deepcopy(state), "result": res}
        attempts.append(rec)
        if res["exit_code"] == 0:
            return {"revived": True, "attempts": attempts, "dockerfile": df, "patches": state["patches"]}

        rank = failing_rank(res)
        if last_decision is not None and prev_rank is not None and rank < prev_rank:
            why = "build now fails EARLIER than before: " + res["log"].strip()[-300:]
            rejected.append({"strategy": last_decision["strategy"], "change": last_decision["change"], "why": why})
            state = copy.deepcopy(last_state)
            reset_patches(work, state["patches"])
            rec["reverted_last_change"] = True
            print(f"[attempt {i}] last change made things worse -> reverted", flush=True)
        else:
            last_good, prev_rank = res, rank
        ctx = last_good or res

        evidence = research.search(make_query(ctx["log"], state["py"]))
        decision = llm.decide({
            "traceback": ctx["log"][-6000:], "stage": ctx["stage"],
            "current_state": state, "rejected_changes": rejected, "last_patch_result": patch_note,
            "prior_attempts": [{"attempt": a["attempt"], "state": a["state"], "exit": a["result"]["exit_code"],
                                "tail": a["result"]["log"][-300:]} for a in attempts[:-1]],
            "research": evidence, "verification_command": verification_command})
        rec.update({"research": evidence, "decision": decision})
        print(f"[attempt {i}] decision: {decision['strategy']} {json.dumps(decision['change'])}", flush=True)
        os.makedirs("benchmark/results", exist_ok=True)
        open("benchmark/results/partial.json", "w", encoding="utf-8").write(json.dumps(attempts, indent=2))
        if decision["strategy"] == "give_up":
            break

        last_state, last_decision, patch_note = copy.deepcopy(state), decision, None
        ch = decision["change"]
        for k, v in (ch.get("pip_pins") or {}).items():
            if PKG_RE.match(str(k)) and VER_RE.match(str(v)):
                state["pins"][k] = v
        for a in ch.get("apt_packages") or []:
            if APT_RE.match(str(a)) and a not in state["apt"]:
                state["apt"].append(a)
        pv = (ch.get("python_version") or "").strip()
        if PY_RE.match(pv):
            state["py"] = pv
        if ch.get("patch"):
            patch_note = apply_patch(work, ch["patch"])
            if patch_note == "applied":
                state["patches"].append(ch["patch"])
    return {"revived": False, "attempts": attempts, "dockerfile": df, "patches": state["patches"]}


def summarize(result: dict) -> str:
    lines = [f"REVIVED: {result['revived']}  (attempts: {len(result['attempts'])})"]
    for a in result["attempts"]:
        r = a["result"]
        tail = " | ".join(x.strip() for x in r["log"].strip().splitlines()[-3:])[:300]
        lines.append(f"\n--- attempt {a['attempt']}  stage={r['stage']}  exit={r['exit_code']}"
                     + ("  [REVERTED last change]" if a.get("reverted_last_change") else ""))
        lines.append(f"state: py={a['state']['py']} apt={a['state']['apt']} pins={a['state']['pins']}")
        lines.append(f"log tail: {tail}")
        if "decision" in a:
            d = a["decision"]
            lines.append(f"decision: {d['failure_class']} -> {d['strategy']} {json.dumps(d['change'])}")
            lines.append(f"root cause: {d['root_cause']}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    result = revive(sys.argv[1], sys.argv[2], sys.argv[3])
    os.makedirs("benchmark/results", exist_ok=True)
    out = f"benchmark/results/run_{int(time.time())}.json"
    open(out, "w", encoding="utf-8").write(json.dumps(result, indent=2))
    print(summarize(result))
    print(f"\nFull result saved to {out}")