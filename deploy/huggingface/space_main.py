"""Hugging Face Space entry point (Gradio SDK runtime, no Gradio UI).

Free Spaces run `python <app_file>` and route port 7860. This starts the AgentShelf
API there, after migrating, seeding the sandbox demo store and launching a
supervised job worker. The browser app is served by Vercel, which forwards /api,
/mcp, /.well-known, /checkout and /webhooks here.
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "backend"
WORKER_RESTART_SECONDS = 5
PORT = 7860


def run_worker_forever():
    while True:
        subprocess.run([sys.executable, "worker.py"], cwd=BACKEND, check=False)
        print(f"worker exited; restarting in {WORKER_RESTART_SECONDS} seconds", flush=True)
        time.sleep(WORKER_RESTART_SECONDS)


def report_zero_gpu_startup():
    """Satisfy ZeroGPU hardware, which stops a Space with no @spaces.GPU function.

    AgentShelf needs no GPU. On ZeroGPU the platform requires at least one decorated
    function and a startup report, which `spaces` normally sends from Gradio's
    launch(); this app never calls launch(), so send it here. Elsewhere it is a no-op.
    """
    try:
        import spaces
    except ImportError:
        return

    @spaces.GPU
    def no_gpu_work():
        return None

    startup = getattr(getattr(spaces, "zero", None), "startup", None)
    if startup is not None:
        startup()
        print("ZeroGPU startup reported (no GPU work is scheduled)", flush=True)


def main():
    report_zero_gpu_startup()
    os.environ.setdefault("SERVE_FRONTEND", "false")
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    if subprocess.run([sys.executable, "seed.py"], check=False).returncode != 0:
        print("demo seed skipped", flush=True)
    threading.Thread(target=run_worker_forever, daemon=True).start()

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=PORT,
        workers=int(os.environ.get("WEB_CONCURRENCY", "2")),
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        timeout_keep_alive=5,
    )


if __name__ == "__main__":
    main()
