"""Run the PlexRAG API and frontend development server together."""

import argparse
from contextlib import ExitStack
import errno
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
HOST = "127.0.0.1"


def port_number(value):
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("Choose a port between 1 and 65535.")
    return port


def reserve_port(stack, name, preferred):
    probe = stack.enter_context(socket.socket())
    busy_errors = {errno.EADDRINUSE}
    if os.name == "nt":
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        busy_errors.update({errno.WSAEADDRINUSE, errno.WSAEACCES})
    try:
        probe.bind((HOST, preferred))
        return preferred
    except OSError as error:
        if error.errno not in busy_errors:
            raise
    probe.bind((HOST, 0))
    port = probe.getsockname()[1]
    print(f"{name} port {preferred} is unavailable. Using {port}.", flush=True)
    return port


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if process.poll() is None:
            process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-port", type=port_number, default=3000)
    parser.add_argument("--backend-port", type=port_number, default=7860)
    args = parser.parse_args()

    bun = shutil.which("bun")
    if not bun:
        parser.exit(1, "Install Bun and make sure it is on PATH.\n")
    if not (FRONTEND / "node_modules" / "next" / "package.json").is_file():
        parser.exit(1, "Install frontend dependencies with bun install --cwd frontend.\n")

    venv_python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python = str(venv_python) if venv_python.is_file() else sys.executable
    processes = {}
    process_group = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )

    try:
        with ExitStack() as reservations:
            backend_port = reserve_port(reservations, "API", args.backend_port)
            frontend_port = reserve_port(reservations, "Frontend", args.frontend_port)

        frontend_url = f"http://{HOST}:{frontend_port}"
        backend_url = f"http://{HOST}:{backend_port}"
        processes["API"] = subprocess.Popen(
            [python, "-u", "-m", "uvicorn", "backend.main:app", "--host", HOST,
             "--port", str(backend_port)],
            cwd=ROOT,
            **process_group,
        )
        processes["Frontend"] = subprocess.Popen(
            [bun, "run", "dev", "--hostname", HOST, "--port", str(frontend_port)],
            cwd=FRONTEND,
            env={**os.environ, "NEXT_PUBLIC_API_ORIGIN": backend_url},
            **process_group,
        )

        print(f"Starting PlexRAG at {frontend_url}/ and the API at {backend_url}.", flush=True)
        print("Press Ctrl+C to stop both servers.", flush=True)
        while True:
            for name, process in processes.items():
                code = process.poll()
                if code is not None:
                    print(f"{name} stopped with exit code {code}.", file=sys.stderr)
                    return code or 1
            time.sleep(0.25)
    except KeyboardInterrupt:
        return 0
    except OSError as error:
        print(f"Could not start PlexRAG: {error}", file=sys.stderr)
        return 1
    finally:
        for process in reversed(processes.values()):
            stop_process(process)


if __name__ == "__main__":
    sys.exit(main())
