"""Ensure Lambda assets exist before CDK synth/deploy."""

from __future__ import annotations

import subprocess

from splitleh_cloud.paths import BUNDLE_SCRIPT, REPO_ROOT


def ensure_bundled() -> None:
    subprocess.run(
        ["uv", "run", "python", str(BUNDLE_SCRIPT)],
        check=True,
        cwd=REPO_ROOT,
    )
