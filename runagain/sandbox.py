import os, subprocess, tempfile, textwrap

def run_in_sandbox(workdir: str, dockerfile: str, command: str, tag: str) -> dict:
    """Build image from dockerfile, run command with CPU/mem/time limits. Returns exit code + log."""
    open(os.path.join(workdir, "Dockerfile.runagain"), "w").write(dockerfile)
    b = subprocess.run(["docker", "build", "-f", "Dockerfile.runagain", "-t", tag, "."],
                       cwd=workdir, capture_output=True, text=True, timeout=1200)
    if b.returncode != 0:
        return {"stage": "build", "exit_code": b.returncode, "log": (b.stdout + b.stderr)[-6000:]}
    try:
        r = subprocess.run(
            ["docker", "run", "--rm", "--cpus", os.getenv("SANDBOX_CPUS", "2"),
             "--memory", os.getenv("SANDBOX_MEMORY", "2g"), "--pids-limit", "256",
             tag, "sh", "-c", command],
            capture_output=True, text=True, timeout=int(os.getenv("SANDBOX_TIMEOUT_S", "600")))
        return {"stage": "run", "exit_code": r.returncode, "log": (r.stdout + r.stderr)[-6000:]}
    except subprocess.TimeoutExpired:
        return {"stage": "run", "exit_code": 124, "log": "timeout"}

def base_dockerfile(py: str, apt: list[str], pins: dict, req_file: str | None) -> str:
    apt_line = f"RUN apt-get update && apt-get install -y --no-install-recommends {' '.join(apt)} && rm -rf /var/lib/apt/lists/*" if apt else ""
    pin_line = "RUN pip install " + " ".join(f"'{k}=={v}'" for k, v in pins.items()) if pins else ""
    req_line = f"RUN pip install -r {req_file}" if req_file else ""
    return textwrap.dedent(f"""\
        FROM python:{py}-slim
        {apt_line}
        WORKDIR /app
        COPY . /app
        {req_line}
        {pin_line}
        """)
