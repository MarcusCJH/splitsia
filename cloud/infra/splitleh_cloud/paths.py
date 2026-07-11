import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INFRA_ROOT = REPO_ROOT / "cloud" / "infra"
API_ROOT = REPO_ROOT / "cloud" / "api"
BUNDLE_SCRIPT = INFRA_ROOT / "scripts" / "bundle_lambda.py"
LAMBDA_LAYER = API_ROOT / "dist" / "lambda_layer"
LAMBDA_CODE = API_ROOT / "dist" / "lambda_code"

# Copied into lambda_layer/python/ alongside pip deps.
LAYER_PACKAGES: tuple[str, ...] = ("shared", "splitleh")

# Bundling / Lambda runtime (keep in sync with BaseLambda + Runtime constructs).
LAMBDA_PYTHON = "3.12"
LAMBDA_PLATFORM = "aarch64-manylinux2014"
LAYER_VERSION_NAME = "lambda_layer"
HANDLER_MODULE = "lambda_function"


def lambda_code_dir(slug: str) -> Path:
    return LAMBDA_CODE / slug


def lambda_handler() -> str:
    """Handler at zip root - asset folder is flat (no package subfolder)."""
    return f"{HANDLER_MODULE}.handler"


def lambda_services() -> list[str]:
    """Service folders with a handler entrypoint (splitleh_*/lambda_function.py)."""
    return sorted(
        path.name
        for path in API_ROOT.iterdir()
        if path.is_dir()
        and path.name.startswith("splitleh_")
        and (path / f"{HANDLER_MODULE}.py").is_file()
    )


def setup_import_paths() -> None:
    """Ensure infra + api roots are importable (app.py, bundle script)."""
    for root in (INFRA_ROOT, API_ROOT):
        root_str = str(root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
