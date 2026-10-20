import os, subprocess, tempfile, textwrap

def run_in_sandbox(workdir: str, dockerfile: str, command: str, tag: str) -> dict:
    """Build image from dockerfile, run command with CPU/mem/time limits. Returns exit code + log."""
    open(os.path.join(workdir, "Dockerfile.runagain"), "w").write(dockerfile)
    try:
        b = subprocess.run(["docker", "build", "-f", "Dockerfile.runagain", "-t", tag, "."],
                           cwd=workdir, capture_output=True, encoding="utf-8", errors="replace",
                           timeout=int(os.getenv("SANDBOX_BUILD_TIMEOUT_S", "600")))
    except subprocess.TimeoutExpired:
        return {"stage": "build", "exit_code": 124,
                "log": "BUILD TIMEOUT: docker build exceeded the time limit (often pip compiling an old package from source)"}
    if b.returncode != 0:
        return {"stage": "build", "exit_code": b.returncode, "log": ((b.stdout or "") + (b.stderr or ""))[-6000:]}
    try:
        r = subprocess.run(
            ["docker", "run", "--rm", "--cpus", os.getenv("SANDBOX_CPUS", "2"),
             "--memory", os.getenv("SANDBOX_MEMORY", "2g"), "--pids-limit", "256",
             tag, "sh", "-c", command],
            capture_output=True, encoding="utf-8", errors="replace", timeout=int(os.getenv("SANDBOX_TIMEOUT_S", "600")))
        return {"stage": "run", "exit_code": r.returncode, "log": ((r.stdout or "") + (r.stderr or ""))[-6000:]}
    except subprocess.TimeoutExpired:
        return {"stage": "run", "exit_code": 124, "log": "timeout"}

def base_dockerfile(py: str, apt: list[str], req_file: str | None) -> str:
    lines = [f"FROM python:{py}-slim"]
    if apt:
        lines.append("RUN apt-get update && apt-get install -y --no-install-recommends "
                     + " ".join(apt) + " && rm -rf /var/lib/apt/lists/*")
    lines += ["WORKDIR /app", "COPY . /app"]
    if req_file:
        lines.append(f"RUN pip install --no-cache-dir --prefer-binary -r {req_file}")
    return "\n".join(lines) + "\n"