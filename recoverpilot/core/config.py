"""Runtime configuration for RecoverPilot production-like mode."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value


# recoverpilot/core/config.py -> parents[2] = repository root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
PLAYBOOKS_DIR = PROJECT_ROOT / "recoverpilot" / "data" / "playbooks"

# On Vercel the deployment FS is read-only except /tmp
if os.getenv("VERCEL") or os.getenv("VERCEL_ENV"):
    DATA_DIR = Path("/tmp/recoverpilot/data")
else:
    DATA_DIR = PROJECT_ROOT / "data"
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass
DB_PATH = DATA_DIR / "recoverpilot.db"
MODEL_PATH = ARTIFACTS_DIR / "recovery_model.joblib"
METRICS_PATH = ARTIFACTS_DIR / "metrics.json"
MODEL_VERSION_PATH = ARTIFACTS_DIR / "model_version.txt"
VECTOR_DIR = DATA_DIR / "chroma"
SYNTHETIC_CSV = DATA_DIR / "synthetic_failures.csv"
FEEDBACK_CSV = DATA_DIR / "feedback_failures.csv"
OUTBOX_DIR = DATA_DIR / "outbox"

DATABASE_URL = _env("DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")

API_HOST = _env("API_HOST", "127.0.0.1")
API_PORT = int(_env("API_PORT", "8000"))
API_BASE_URL = _env("API_BASE_URL", f"http://{API_HOST}:{API_PORT}")
# Public URL for magic links (ngrok / deployed origin). Falls back to API_BASE_URL.
PUBLIC_BASE_URL = _env("PUBLIC_BASE_URL", API_BASE_URL).rstrip("/")

RANDOM_SEED = 42
RETRY_COST_INR = float(_env("RETRY_COST_INR", "2.5"))
TOP_K_QUEUE = 50

# Accelerate scheduled retries for local demos (36h / 60 => 36 minutes if scale=60)
DEMO_TIME_SCALE = float(_env("DEMO_TIME_SCALE", "60"))
WORKER_POLL_SECONDS = float(_env("WORKER_POLL_SECONDS", "2"))

RAZORPAY_WEBHOOK_SECRET = _env("RAZORPAY_WEBHOOK_SECRET", "").strip()
RAZORPAY_KEY_ID = _env("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = _env("RAZORPAY_KEY_SECRET", "").strip()
USE_RAZORPAY_PAYMENT_LINKS = _env("USE_RAZORPAY_PAYMENT_LINKS", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

DEMO_MERCHANT_ID = _env("DEMO_MERCHANT_ID", "mch_demo_001")
DEMO_MERCHANT_NAME = _env("DEMO_MERCHANT_NAME", "Demo Merchant")
DEMO_API_KEY = _env("DEMO_API_KEY", "rp_demo_key_change_me")
DEMO_WEBHOOK_SECRET = _env("DEMO_WEBHOOK_SECRET", "whsec_demo_change_me")

# Soft declines are potentially recoverable; hard declines must not be retried.
HARD_DECLINE_CODES = {
    "DO_NOT_HONOR_HARD",
    "STOLEN_CARD",
    "LOST_CARD",
    "PICKUP_CARD",
    "FRAUD_SUSPECTED",
    "INVALID_CARD",
    "CLOSED_ACCOUNT",
}

SOFT_DECLINE_CODES = {
    "INSUFFICIENT_FUNDS",
    "ISSUER_TIMEOUT",
    "NETWORK_ERROR",
    "BANK_DECLINE_SOFT",
    "AUTHENTICATION_REQUIRED",
    "EXCEEDS_FREQUENCY",
    "TEMPORARY_HOLD",
}
