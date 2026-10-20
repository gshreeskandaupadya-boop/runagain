"""Bounded repair loop. Sandbox result is the source of truth: revived iff exit code == 0."""
import json, os, subprocess, tempfile, time
from . import llm, research, sandbox

def revive(repo_url: str, commit: str, verification_command: str, max_attempts: int | None = None) -> dict:
    max_attempts = max_attempts or int(os.getenv("MAX_ATTEMPTS", "5"))
    work = tempfile.mkdtemp(prefix="runagain_")
    subprocess.run(["git", "clone", "--quiet", repo_url, work], check=True, timeout=300)
    if commit:
        subprocess.run(["git", "checkout", "--quiet", commit], cwd=work, check=True)
    req = "requirements.txt" if os.path.exists(os.path.join(work, "requirements.txt")) else None
    state = {"py": "3.11", "apt": [], "pins": {}}
    attempts = []
    for i in range(1, max_attempts + 1):
        df = sandbox.base_dockerfile(state["py"], state["apt"], state["pins"], req)
        res = sandbox.run_in_sandbox(work, df, verification_command, f"runagain-{int(time.time())}-{i}")
        rec = {"attempt": i, "state": dict(state), "result": res}
        attempts.append(rec)
        if res["exit_code"] == 0:
            return {"revived": True, "attempts": attempts, "dockerfile": df}
        last_line = res["log"].strip().splitlines()[-1] if res["log"].strip() else "no output"
        evidence = research.search(f"python {state['py']} {last_line}")
        decision = llm.decide({"traceback": res["log"], "stage": res["stage"], "state": state,
                               "prior_attempts": [{"state": a["state"], "tail": a["result"]["log"][-500:]} for a in attempts[:-1]],
                               "research": evidence, "verification_command": verification_command})
        rec.update({"research": evidence, "decision": decision})
        if decision["strategy"] == "give_up":
            break
        ch = decision["change"]
        state["pins"].update(ch.get("pip_pins", {}))
        state["apt"] = sorted(set(state["apt"]) | set(ch.get("apt_packages", [])))
        state["py"] = ch.get("python_version", state["py"])
        # compat_patch application intentionally TODO: apply via `git apply` after size check
    return {"revived": False, "attempts": attempts, "dockerfile": df}

if __name__ == "__main__":
    import sys
    print(json.dumps(revive(sys.argv[1], sys.argv[2], sys.argv[3]), indent=2)[:4000])
