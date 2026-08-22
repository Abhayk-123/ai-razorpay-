"""Runtime configuration for RecoverPilot production-like mode."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# recoverpilot/core/config.py -> parents[2] = repository root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
PLAYBOOKS_DIR = PROJECT_ROOT / "recoverpilot" / "data" / "playbooks"
DB_PATH = DATA_DIR / "recoverpilot.db"
MODEL_PATH = ARTIFACTS_DIR / "recovery_model.joblib"
METRICS_PATH = ARTIFACTS_DIR / "metrics.json"
MODEL_VERSION_PATH = ARTIFACTS_DIR / "model_version.txt"
VECTOR_DIR = DATA_DIR / "chroma"
SYNTHETIC_CSV = DATA_DIR / "synthetic_failures.csv"
FEEDBACK_CSV = DATA_DIR / "feedback_failures.csv"
OUTBOX_DIR = DATA_DIR / "outbox"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_BASE_URL = os.getenv("API_BASE_URL", f"http://{API_HOST}:{API_PORT}")

RANDOM_SEED = 42
RETRY_COST_INR = float(os.getenv("RETRY_COST_INR", "2.5"))
TOP_K_QUEUE = 50

# Accelerate scheduled retries for local demos (36h / 60 => 36 minutes if scale=60)
DEMO_TIME_SCALE = float(os.getenv("DEMO_TIME_SCALE", "60"))
WORKER_POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "2"))

RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()
DEMO_MERCHANT_ID = os.getenv("DEMO_MERCHANT_ID", "mch_demo_001")
DEMO_MERCHANT_NAME = os.getenv("DEMO_MERCHANT_NAME", "Demo Merchant")
DEMO_API_KEY = os.getenv("DEMO_API_KEY", "rp_demo_key_change_me")
DEMO_WEBHOOK_SECRET = os.getenv("DEMO_WEBHOOK_SECRET", "whsec_demo_change_me")

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
