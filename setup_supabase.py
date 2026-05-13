#!/usr/bin/env python3
"""
setup_supabase.py
=================
Prints the SQL you need to paste into the Supabase Dashboard SQL Editor,
then opens the browser to the right page.

Usage:
    python setup_supabase.py
"""
from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_REF = "xnskpnrqqdeapwkvniid"
SQL_FILE    = Path(__file__).parent / "data" / "migrations" / "001_initial.sql"
DASHBOARD_URL = f"https://supabase.com/dashboard/project/{PROJECT_REF}/sql/new"

sql = SQL_FILE.read_text(encoding="utf-8")

print("=" * 70)
print("  Lucid AI Trader - Supabase Database Setup")
print("=" * 70)
print()
print("  Your SQL schema is in:")
print(f"  {SQL_FILE}")
print()
print("  Steps to create all tables:")
print(f"  1. The Supabase SQL Editor should open in your browser.")
print(f"     URL: {DASHBOARD_URL}")
print(f"  2. Paste the contents of:")
print(f"     data/migrations/001_initial.sql")
print(f"  3. Click 'Run'")
print()
print("  Opening browser...")
webbrowser.open(DASHBOARD_URL)
print()
print("-" * 70)
print("  SQL CONTENT (copy everything between the dashes):")
print("-" * 70)
print(sql)
print("-" * 70)
print()
print("  After running the SQL, restart the server:")
print("  python dashboard/server.py")
print()
