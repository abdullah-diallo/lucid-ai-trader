"""
Groq AI client — fast LLaMA inference for trade analysis and signal commentary.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

_client: Optional[Groq] = None
DEFAULT_MODEL = "llama-3.3-70b-versatile"


def get_groq() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY must be set in .env")
        _client = Groq(api_key=api_key)
    return _client


def analyze_signal(signal: Dict[str, Any]) -> str:
    """Generate a brief AI commentary on a trading signal."""
    client = get_groq()
    prompt = (
        f"You are a professional futures trader analyzing a signal.\n"
        f"Symbol: {signal.get('symbol', 'N/A')}\n"
        f"Action: {signal.get('action', 'N/A')}\n"
        f"Price: {signal.get('price', 'N/A')}\n"
        f"Timeframe: {signal.get('timeframe', 'N/A')}\n"
        f"Reason: {signal.get('reason', 'N/A')}\n\n"
        f"Give a concise 2-3 sentence analysis of this trade signal including risk considerations. "
        f"Be direct and professional."
    )
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"AI analysis unavailable: {exc}"


def analyze_pnl(pnl_data: Dict[str, Any]) -> str:
    """Generate a brief AI commentary on P&L performance."""
    client = get_groq()
    prompt = (
        f"You are a trading performance analyst.\n"
        f"Net P&L: {pnl_data.get('net_pnl', 0)}\n"
        f"Win Rate: {pnl_data.get('win_rate', 0)}%\n"
        f"Total Trades: {pnl_data.get('total_trades', 0)}\n"
        f"Gross Profit: {pnl_data.get('gross_profit', 0)}\n"
        f"Gross Loss: {pnl_data.get('gross_loss', 0)}\n\n"
        f"Give a concise 2-sentence assessment of this trading performance and one actionable suggestion."
    )
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"AI analysis unavailable: {exc}"


def chat(messages: List[Dict[str, str]], system: str = "") -> str:
    """General-purpose chat endpoint."""
    client = get_groq()
    full_messages: List[Dict[str, str]] = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=full_messages,
            max_tokens=512,
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"Error: {exc}"
