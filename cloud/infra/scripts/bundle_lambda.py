"""Bundle lambda_layer (deps + shared libs) and flat per-function code."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

_INFRA = Path(__file__).resolve().parents[1]
if str(_INFRA) not in sys.path:
    sys.path.insert(0, str(_INFRA))

from splitleh_cloud.paths import (
    API_ROOT,
    HANDLER_MODULE,
    LAMBDA_LAYER,
    LAMBDA_PLATFORM,
    LAMBDA_PYTHON,
    LAYER_PACKAGES,
    REPO_ROOT,
    lambda_code_dir,
    lambda_services,
    setup_import_paths,
)

setup_import_paths()

LAYER_PYTHON = LAMBDA_LAYER / "python"
REQUIREMENTS_HASH = LAMBDA_LAYER / ".requirements.sha256"

_SKIP_NAMES = frozenset({"cdk", "__pycache__"})
# Flat zip root is on sys.path - never shadow stdlib module names (e.g. select.py breaks boto3).
_FORBIDDEN_ROOT_MODULES = frozenset(
    {"select", "socket", "json", "typing", "email", "http", "test", "random", "os", "sys"}
)
_COPY_IGNORE = shutil.ignore_patterns("cdk", "__pycache__", "*.pyc")


def _requirements_digest() -> str:
    parts = [(API_ROOT / "requirements.txt").read_bytes()]
    for name in LAYER_PACKAGES:
        root = API_ROOT / name
        for path in sorted(root.rglob("*.py")):
            parts.append(str(path.relative_to(root)).encode())
            parts.append(path.read_bytes())
    for service in lambda_services():
        root = API_ROOT / service
        for path in sorted(root.rglob("*.py")):
            if "cdk" in path.parts:
                continue
            parts.append(str(path.relative_to(root)).encode())
            parts.append(path.read_bytes())
    return hashlib.sha256(b"".join(parts)).hexdigest()


def _install_pip_deps() -> None:
    if LAYER_PYTHON.exists():
        shutil.rmtree(LAYER_PYTHON)
    LAYER_PYTHON.mkdir(parents=True)

    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "-r",
            str(API_ROOT / "requirements.txt"),
            "--target",
            str(LAYER_PYTHON),
            "--python-version",
            LAMBDA_PYTHON,
            "--python-platform",
            LAMBDA_PLATFORM,
            "--no-cache",
        ],
        check=True,
        cwd=REPO_ROOT,
    )


def _copy_layer_libs() -> None:
    for name in LAYER_PACKAGES:
        src = API_ROOT / name
        dest = LAYER_PYTHON / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest, ignore=_COPY_IGNORE)


def _ensure_layer() -> None:
    digest = _requirements_digest()
    cached = (
        REQUIREMENTS_HASH.read_text(encoding="utf-8").strip()
        if REQUIREMENTS_HASH.exists()
        else ""
    )
    if cached == digest and LAYER_PYTHON.is_dir() and any(LAYER_PYTHON.iterdir()):
        print(f"Reusing lambda_layer at {LAMBDA_LAYER}")
        return
    _install_pip_deps()
    _copy_layer_libs()
    REQUIREMENTS_HASH.write_text(digest, encoding="utf-8")
    print(f"Bundled lambda_layer to {LAMBDA_LAYER}")


def _copy_service_code(service: str) -> None:
    """Copy handler modules flat - zip root is lambda_function.py, not service/service/."""
    src = API_ROOT / service
    dest = lambda_code_dir(service)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    for path in src.iterdir():
        if path.name in _SKIP_NAMES:
            continue
        if path.is_file() and path.suffix == ".py":
            stem = path.stem
            if stem in _FORBIDDEN_ROOT_MODULES:
                raise SystemExit(
                    f"{service}/{path.name} shadows Python stdlib - rename before bundling"
                )
            shutil.copy2(path, dest / path.name)

    if not (dest / f"{HANDLER_MODULE}.py").is_file():
        raise SystemExit(f"Missing {HANDLER_MODULE}.py for {service}")

    print(f"Bundled {service} handler to {dest}")


def main() -> None:
    for stale in (API_ROOT / "dist" / "code", API_ROOT / "dist" / "layer"):
        if stale.exists():
            shutil.rmtree(stale)
    LAMBDA_LAYER.mkdir(parents=True, exist_ok=True)
    _ensure_layer()
    for service in lambda_services():
        _copy_service_code(service)


if __name__ == "__main__":
    main()
