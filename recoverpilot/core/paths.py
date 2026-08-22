from recoverpilot.core.config import ARTIFACTS_DIR, DATA_DIR


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
