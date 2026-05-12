#!/usr/bin/env python3
"""
Project bootstrap script for lucid-ai-trader.

This script performs:
1) Python version validation (3.11+)
2) Virtual environment creation
3) Requirements installation
4) .env generation from .env.example with prompts
5) SQLite initialization
6) logs/ and reports/ directory creation
7) API smoke tests
8) Success summary and next steps
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple
from urllib import error, request

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / "venv"
DB_PATH_DEFAULT = ROOT / "data" / "lucid_trader.db"
ENV_EXAMPLE_PATH = ROOT / ".env.example"
ENV_PATH = ROOT / ".env"


def check_python_version() -> None:
    """
    Enforce Python 3.11+.
    """
    if sys.version_info < (3, 11):
        raise RuntimeError(
            f"Python 3.11+ is required. Detected: {sys.version.split()[0]}"
        )


def create_virtualenv() -> None:
    """
    Create local virtual environment in ./venv if missing.
    """
    if VENV_DIR.exists():
        print("✓ Virtual environment already exists at ./venv")
        return
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    print("✓ Created virtual environment at ./venv")


def venv_python() -> Path:
    """
    Return path to the virtualenv Python executable.
    """
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def install_requirements() -> None:
    """
    Upgrade pip and install dependencies if requirements.txt exists.
    """
    py = venv_python()
    subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip"], check=True)

    req = ROOT / "requirements.txt"
    if req.exists():
        subprocess.run([str(py), "-m", "pip", "install", "-r", str(req)], check=True)
        print("✓ Installed dependencies from requirements.txt")
    else:
        print("! requirements.txt not found; skipped dependency installation")


def parse_env_file(path: Path) -> Dict[str, str]:
    """
    Parse simple KEY=VALUE env files.
    """
    data: Dict[str, str] = {}
    if not path.exists():
        return data

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def create_env_file() -> None:
    """
    Create .env from .env.example, prompting for each key.
    Existing .env is preserved.
    """
    if ENV_PATH.exists():
        print("✓ .env already exists; keeping current file")
        return
    if not ENV_EXAMPLE_PATH.exists():
        raise FileNotFoundError(".env.example is missing. Create it before running setup.")

    template = parse_env_file(ENV_EXAMPLE_PATH)
    if not template:
        raise RuntimeError(".env.example has no key definitions.")

    print("\nEnter values for environment variables (press Enter to keep default):")
    output_lines = []
    for key, default in template.items():
        prompt = f"  {key}"
        if default:
            prompt += f" [{default}]"
        prompt += ": "
        try:
            user_value = input(prompt).strip()
        except EOFError:
            user_value = ""
        chosen = user_value if user_value else default
        output_lines.append(f"{key}={chosen}")

    ENV_PATH.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    print("✓ Created .env from .env.example")


def ensure_directories() -> None:
    """
    Ensure required runtime directories exist.
    """
    for rel in ("logs", "reports", "data"):
        (ROOT / rel).mkdir(parents=True, exist_ok=True)
    print("✓ Ensured logs/, reports/, and data/ directories exist")


def init_sqlite_db() -> Path:
    """
    Create SQLite database and baseline tables.
    """
    env = parse_env_file(ENV_PATH)
    db_path = Path(env.get("SQLITE_DB_PATH", str(DB_PATH_DEFAULT)))
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                price REAL NOT NULL,
                timeframe TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS setup_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO setup_runs (run_at, status) VALUES (datetime('now'), 'ok')
            """
        )
        conn.commit()
    finally:
        conn.close()

    print(f"✓ SQLite initialized at {db_path}")
    return db_path


def _http_get(url: str, headers: Dict[str, str] | None = None, timeout: int = 10) -> Tuple[bool, str]:
    req = request.Request(url, headers=headers or {}, method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return True, f"{resp.status}"
    except error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, str(exc)


def run_api_connection_tests() -> None:
    """
    Basic API smoke tests for configured integrations.
    Tests are non-destructive and skip missing credentials.
    """
    env = parse_env_file(ENV_PATH)
    print("\nConnection tests:")

    # TradingView webhook uses inbound secret (no outbound API test).
    if env.get("TRADINGVIEW_WEBHOOK_SECRET"):
        print("  ✓ TradingView webhook secret configured")
    else:
        print("  ✗ TradingView webhook secret missing")

    # Telegram bot check.
    telegram_token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    if telegram_token:
        ok, detail = _http_get(f"https://api.telegram.org/bot{telegram_token}/getMe")
        mark = "✓" if ok else "✗"
        print(f"  {mark} Telegram API: {detail}")
    else:
        print("  ! Telegram API skipped (TELEGRAM_BOT_TOKEN not set)")

    # Tradovate check (simple auth endpoint ping if credentials are present).
    tradovate_user = env.get("TRADOVATE_USERNAME", "").strip()
    tradovate_pass = env.get("TRADOVATE_PASSWORD", "").strip()
    tradovate_cid = env.get("TRADOVATE_CLIENT_ID", "").strip()
    tradovate_secret = env.get("TRADOVATE_CLIENT_SECRET", "").strip()
    tradovate_base = env.get("TRADOVATE_API_BASE_URL", "https://demo-api.tradovate.com").strip()
    if all([tradovate_user, tradovate_pass, tradovate_cid, tradovate_secret]):
        ok, detail = _http_get(f"{tradovate_base}/v1/health")
        mark = "✓" if ok else "✗"
        print(f"  {mark} Tradovate API: {detail}")
    else:
        print("  ! Tradovate API skipped (credentials incomplete)")

    # Anthropic check (models endpoint).
    anthropic_key = env.get("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key:
        ok, detail = _http_get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
            },
        )
        mark = "✓" if ok else "✗"
        print(f"  {mark} Anthropic API: {detail}")
    else:
        print("  ! Anthropic API skipped (ANTHROPIC_API_KEY not set)")


def print_next_steps() -> None:
    """
    Show concise instructions after successful setup.
    """
    py = venv_python()
    activate_cmd = "source venv/bin/activate"
    if os.name == "nt":
        activate_cmd = r"venv\Scripts\activate"

    print("\nSetup complete.\n")
    print("Next steps:")
    print(f"  1) Activate venv: {activate_cmd}")
    print(f"  2) Verify Python: {py} --version")
    print("  3) Start webhook receiver:")
    print("     python data/tradingview_client.py")
    print("  4) Configure TradingView alert webhook URL to:")
    print("     http://<your-host>:8080/tv-webhook")
    print("  5) Run your trading loop in paper mode before live trading.")


def main() -> None:
    try:
        print("Starting lucid-ai-trader setup...\n")
        check_python_version()
        print("✓ Python version is 3.11+")
        create_virtualenv()
        install_requirements()
        create_env_file()
        ensure_directories()
        init_sqlite_db()
        run_api_connection_tests()
        print_next_steps()
    except Exception as exc:
        print(f"\nSetup failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
