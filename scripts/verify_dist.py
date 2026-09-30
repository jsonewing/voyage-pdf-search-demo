from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
DEFAULT_ARCHIVE = ROOT / "dist" / f"voyage-pdf-search-portable-v{VERSION}.zip"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a clean Voyage PDF Search package.")
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--port", type=int, default=18220)
    parser.add_argument("--timeout", type=int, default=420)
    return parser.parse_args()


def wait_json(url: str, process: subprocess.Popen, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Launcher exited before readiness with code {process.returncode}")
        try:
            with urlopen(url, timeout=1) as response:  # noqa: S310 - loopback only
                return json.loads(response.read())
        except Exception:  # noqa: BLE001
            time.sleep(0.4)
    raise TimeoutError(f"Timed out waiting for {url}")


def wait_http(url: str, process: subprocess.Popen, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Process exited before {url} became available")
        try:
            with urlopen(url, timeout=1) as response:  # noqa: S310 - loopback only
                return response.read()
        except Exception:  # noqa: BLE001
            time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for {url}")


def wait_port_closed(port: int, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as client:
            if client.connect_ex(("127.0.0.1", port)) != 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"Port {port} did not close")


def stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def launch(package_dir: Path, port: int, log_path: Path, env: dict[str, str]):
    log_file = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [str(package_dir / "run.sh")],
        cwd=package_dir,
        env={**env, "PORT": str(port), "NO_BROWSER": "1"},
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, log_file


def main() -> None:
    args = parse_args()
    archive = args.archive.resolve()
    if not archive.is_file():
        raise SystemExit(f"Archive not found: {archive}")

    clean_env = os.environ.copy()
    for key in ("ATLAS_URI", "VOYAGE_API_KEY", "OPENAI_API_KEY"):
        clean_env.pop(key, None)

    with tempfile.TemporaryDirectory(prefix="voyage-pdf-verify-") as directory:
        extract_root = Path(directory)
        subprocess.run(["unzip", "-q", str(archive), "-d", str(extract_root)], check=True)
        package_dirs = [path for path in extract_root.iterdir() if path.is_dir()]
        if len(package_dirs) != 1:
            raise RuntimeError("Expected one package directory after extraction")
        package_dir = package_dirs[0]
        if (package_dir / ".env").exists():
            raise RuntimeError("Portable package is not secret-free")
        if any((package_dir / "uploads").glob("*.pdf")):
            raise RuntimeError("Portable package contains an uploaded PDF")

        print("[1/5] Clean extraction is secret-free and contains no uploaded PDFs")
        first_log = extract_root / "first-run.log"
        first, first_handle = launch(package_dir, args.port, first_log, clean_env)
        try:
            page = wait_http(f"http://127.0.0.1:{args.port}/", first, args.timeout)
            if b"Voyage PDF Search" not in page:
                raise RuntimeError("Voyage PDF Search UI did not load")
            setup = wait_json(f"http://127.0.0.1:{args.port}/api/setup", first, 10)
            if setup.get("configured") or any(
                key in setup for key in ("atlas_uri", "voyage_api_key", "openai_api_key")
            ):
                raise RuntimeError(f"Setup endpoint exposed an invalid initial state: {setup}")
            runtime_python = package_dir / "vendor" / "python" / "install" / "bin" / "python3"
            if not runtime_python.is_file():
                raise RuntimeError("Pinned standalone Python was not installed")
            venv_python = package_dir / ".venv" / "bin" / "python"
            subprocess.run(
                [str(venv_python), "-c", "import fastapi, pdfplumber, pymongo, uvicorn, voyageai"],
                check=True,
                cwd=package_dir,
            )
            print("[2/5] First-run runtime and pinned dependencies installed")
            print("[3/5] UI, API, and secret-free first-run setup verified")

            warm_log = extract_root / "warm-restart.log"
            started = time.monotonic()
            warm, warm_handle = launch(package_dir, args.port, warm_log, clean_env)
            try:
                first.wait(timeout=35)
                page = wait_http(f"http://127.0.0.1:{args.port}/", warm, 45)
                elapsed = time.monotonic() - started
                if b"Voyage PDF Search" not in page or elapsed > 45:
                    raise RuntimeError(f"Warm restart was not ready in time: {elapsed:.1f}s")
                print(f"[4/5] Warm restart safely handed off the port in {elapsed:.1f}s")
            finally:
                stop(warm)
                warm_handle.close()
            wait_port_closed(args.port)
        finally:
            stop(first)
            first_handle.close()
        wait_port_closed(args.port)

        with (extract_root / "unrelated.log").open("w", encoding="utf-8") as handle:
            unrelated = subprocess.Popen(
                [str(package_dir / ".venv" / "bin" / "python"), "-m", "http.server", str(args.port), "--bind", "127.0.0.1"],
                cwd=package_dir,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                wait_http(f"http://127.0.0.1:{args.port}/", unrelated, 15)
                blocked = subprocess.run(
                    [str(package_dir / "run.sh")],
                    cwd=package_dir,
                    env={**clean_env, "PORT": str(args.port), "NO_BROWSER": "1"},
                    capture_output=True,
                    text=True,
                    timeout=45,
                )
                output = f"{blocked.stdout}\n{blocked.stderr}"
                if blocked.returncode == 0 or unrelated.poll() is not None:
                    raise RuntimeError("Launcher did not preserve the unrelated listener")
                if "belongs to another application" not in output:
                    raise RuntimeError("Launcher refusal did not explain the port conflict")
                print("[5/5] Unrelated listener was detected and left running")
            finally:
                stop(unrelated)

        print("Portable distribution verification passed.")


if __name__ == "__main__":
    main()
