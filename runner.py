import os
import posixpath
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import PurePosixPath


def _decode_timeout_stream(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def _safe_relpath(name: str) -> str:
    """Accept only relative workspace paths for generated files."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("empty file path")
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe file path: {name!r}")
    return str(path)


def _write_codes(workdir: str, codes: dict) -> None:
    for raw_name, code in codes.items():
        name = _safe_relpath(raw_name)
        fpath = os.path.join(workdir, *name.split("/"))
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w", encoding="utf-8", newline="\n") as f:
            f.write(code)


def _write_requirements(workdir: str, requirements: list | None) -> None:
    reqs = requirements or []
    with open(os.path.join(workdir, "requirements.txt"), "w", encoding="utf-8", newline="\n") as f:
        for req in reqs:
            req = str(req).strip()
            if req:
                f.write(req + "\n")


def _find_docker() -> str | None:
    docker = shutil.which("docker")
    if docker:
        return docker
    default_path = r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    if os.path.exists(default_path):
        return default_path
    return None


def _docker_env(docker: str) -> dict:
    env = os.environ.copy()
    docker_dir = os.path.dirname(docker)
    env["PATH"] = docker_dir + os.pathsep + env.get("PATH", "")
    return env


def run_in_subprocess(codes: dict, entry_point: str, *, timeout: int = 20,
                      stdin_input: str = None) -> dict:
    """Run generated files in a temporary directory on the host.

    This preserves the old runner contract. It is useful when Docker is not
    installed, but it is not an isolation boundary.
    """
    workdir = tempfile.mkdtemp(prefix="aaa_run_")
    try:
        entry = _safe_relpath(entry_point)
        _write_codes(workdir, codes)
        try:
            proc = subprocess.run(
                [sys.executable, entry],
                cwd=workdir,
                stdin=(subprocess.DEVNULL if stdin_input is None else None),
                input=stdin_input,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "timed_out": False,
                "stage": "run",
            }
        except subprocess.TimeoutExpired as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": _decode_timeout_stream(e.stdout),
                "stderr": _decode_timeout_stream(e.stderr) + f"\n[runner] TimeoutExpired after {timeout}s",
                "timed_out": True,
                "stage": "run",
            }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_in_docker(codes: dict, requirements: list | None, entry_point: str, *,
                  timeout: int = 60, stdin_input: str = None,
                  image: str = "python:3.11-slim",
                  network: str = "none",
                  memory: str = "256m",
                  cpus: str = "1") -> dict:
    """Run generated files inside a fresh Docker container and return measurements.

    Contract:
      input: codes, requirements, entry_point, timeout, optional stdin
      output: {success, exit_code, stdout, stderr, timed_out, stage}

    The container is removed after each run. By default it has no network; pass
    network="bridge" only when installing external requirements is part of the
    measurement.
    """
    docker = _find_docker()
    if not docker:
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "[runner] Docker executable not found",
            "timed_out": False,
            "stage": "build",
        }

    workdir = tempfile.mkdtemp(prefix="aaa_docker_")
    try:
        entry = _safe_relpath(entry_point)
        _write_codes(workdir, codes)
        _write_requirements(workdir, requirements)

        container_entry = posixpath.join("/workspace", entry)
        stage_marker = "__AAA_STAGE_RUN__"
        inner = (
            "if [ -s requirements.txt ]; then "
            "python -m pip install --no-cache-dir -r requirements.txt || exit $?; "
            "fi; "
            f"printf '\\n{stage_marker}\\n' >&2; "
            f"exec python {shlex.quote(container_entry)}"
        )

        cmd = [
            docker, "run", "--rm", "-i",
            "--network", network,
            "--memory", memory,
            "--cpus", cpus,
            "-v", f"{workdir}:/workspace",
            "-w", "/workspace",
            image,
            "sh", "-c", inner,
        ]

        try:
            proc = subprocess.run(
                cmd,
                input=stdin_input,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=_docker_env(docker),
            )
            stderr = proc.stderr or ""
            reached_run = stage_marker in stderr
            stderr = stderr.replace(f"\n{stage_marker}\n", "\n").replace(stage_marker, "")
            stage = "run" if reached_run else "build"
            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": stderr,
                "timed_out": False,
                "stage": stage,
            }
        except subprocess.TimeoutExpired as e:
            stderr = _decode_timeout_stream(e.stderr)
            reached_run = stage_marker in stderr
            stderr = stderr.replace(f"\n{stage_marker}\n", "\n").replace(stage_marker, "")
            return {
                "success": False,
                "exit_code": -1,
                "stdout": _decode_timeout_stream(e.stdout),
                "stderr": stderr + f"\n[runner] Docker TimeoutExpired after {timeout}s",
                "timed_out": True,
                "stage": "run" if reached_run else "build",
            }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def looks_alive(run_result: dict, expected: str = None) -> bool:
    if not run_result.get("success"):
        return False
    if expected:
        return expected in run_result.get("stdout", "")
    return True


if __name__ == "__main__":
    print("=== runner.py self-test ===")

    codes_ok = {
        "a.py": "def greet():\n    return 'hello from a'\n",
        "main.py": "from a import greet\nprint(greet())\n",
    }
    r = run_in_subprocess(codes_ok, "main.py")
    assert r["success"] is True, r
    assert "hello from a" in r["stdout"], r
    assert looks_alive(r, expected="hello from a") is True
    print("[1] subprocess import/run ok")

    codes_bad = {
        "a.py": "def greet():\n    return 'hi'\n",
        "main.py": "from a import nonexistent\nprint(nonexistent())\n",
    }
    r = run_in_subprocess(codes_bad, "main.py")
    assert r["success"] is False, r
    assert "ImportError" in r["stderr"] or "cannot import" in r["stderr"], r
    print("[2] subprocess import failure observed")

    codes_loop = {"main.py": "while True:\n    pass\n"}
    r = run_in_subprocess(codes_loop, "main.py", timeout=1)
    assert r["timed_out"] is True, r
    print("[3] subprocess timeout observed")

    codes_input = {"main.py": "x = input('enter: ')\nprint('got', x)\n"}
    r = run_in_subprocess(codes_input, "main.py", timeout=2)
    assert r["timed_out"] is False, r
    assert "EOFError" in r["stderr"], r
    print("[4] subprocess stdin EOF observed")

    r = run_in_docker(codes_ok, [], "main.py", timeout=10)
    if r["stderr"] == "[runner] Docker executable not found":
        print("[5] docker skipped: executable not found")
    else:
        assert r["success"] is True, r
        assert "hello from a" in r["stdout"], r
        assert r["stage"] == "run", r
        print("[5] docker import/run ok")

    print("=== ok ===")
