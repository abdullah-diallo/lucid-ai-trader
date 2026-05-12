# Lucid AI Trader
Lucid AI Trader is an automated futures-trading assistant. In plain English, it listens for market signals, checks whether conditions are safe to trade, and helps you execute and monitor trades with clear logs and reports.

## What this system does
- Watches for TradingView alerts (webhooks).
- Interprets alerts as buy/sell/close signals.
- Applies session and timing safety checks (market hours, high-volume windows, news windows).
- Stores key signal data in SQLite for traceability.
- Produces logs and daily report artifacts you can review.

## Prerequisites
Before you start, make sure you have:
- Python 3.11 or newer
- TradingView account (for alerts)
- Tradovate account (demo/paper first)
- Telegram account + bot token (optional but recommended for alerts)
- Internet access for API checks

## Installation (step-by-step)
1. Clone or open the project.
2. From the project root, run:
   - `python3 setup.py`
3. The setup script will:
   - verify Python version
   - create `venv/`
   - install dependencies
   - create `.env` from `.env.example`
   - initialize SQLite
   - create `logs/` and `reports/`
   - run API smoke tests

4. Activate the virtual environment:
   - macOS/Linux: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate`

5. Start the TradingView webhook receiver:
   - `python data/tradingview_client.py`

## API keys and account setup

### TradingView
- Site: https://www.tradingview.com/
- You do not need a traditional API key for this flow.
- You need:
  - A TradingView alert using webhook delivery
  - A shared secret value matching `TRADINGVIEW_WEBHOOK_SECRET` in `.env`

### Tradovate
- Site: https://www.tradovate.com/
- Developer/API docs: https://api.tradovate.com/
- Configure in `.env`:
  - `TRADOVATE_API_BASE_URL` (use demo URL first)
  - `TRADOVATE_USERNAME`
  - `TRADOVATE_PASSWORD`
  - `TRADOVATE_CLIENT_ID`
  - `TRADOVATE_CLIENT_SECRET`

### Telegram (optional alerts)
- Bot creation: https://core.telegram.org/bots#how-do-i-create-a-bot
- API reference: https://core.telegram.org/bots/api
- Configure:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`

### Anthropic (optional AI workflows)
- Console: https://console.anthropic.com/
- API docs: https://docs.anthropic.com/
- Configure:
  - `ANTHROPIC_API_KEY`

## Lucid/Tradovate configuration guidance
1. Always begin in Tradovate demo/paper environment.
2. Keep `TRADOVATE_API_BASE_URL` pointed to the demo endpoint until stable.
3. Set conservative position sizing and strict stop rules first.
4. Verify every signal appears correctly in logs before enabling live execution.

## Paper mode first (recommended)
1. Set `PAPER_MODE=true` in `.env`.
2. Start webhook receiver.
3. Trigger test alerts from TradingView.
4. Confirm:
   - webhook accepted
   - signal emitted
   - database receives entries
   - no live order routes are hit

Do not switch to live mode until you have several days of stable paper behavior.

## TradingView webhook format
Your alert JSON message should look like:

```json
{
  "symbol": "MES1!",
  "action": "BUY",
  "price": 5386.25,
  "timeframe": "15m",
  "reason": "ORB breakout confirmed on TradingView",
  "secret": "your_webhook_secret_key"
}
```

The `secret` must exactly match `TRADINGVIEW_WEBHOOK_SECRET`.

## Telegram bot commands (suggested command set)
If your bot module supports command handlers, use these practical commands:
- `/start` - show bot status and available commands
- `/status` - show session status and whether trading is currently allowed
- `/lastsignal` - show most recent signal details
- `/today` - show current-day performance summary
- `/pause` - pause automated execution
- `/resume` - resume automated execution
- `/paper` - force paper mode
- `/help` - show command help

If your current bot code uses different command names, keep your local command list as the source of truth.

## Reading the daily report
A useful daily report should answer:
- How many signals were generated?
- How many were filtered out by session/news rules?
- What were win/loss outcomes in paper mode?
- Which hours were strongest/weakest?
- Were there repeated failures (latency, missing fields, API errors)?

Review these before changing thresholds or going live.

## FAQ / common problems

### 1) “Webhook returns 403 Invalid secret”
- Cause: TradingView alert secret and `.env` secret do not match.
- Fix: Update one side so values are identical (no extra spaces).

### 2) “Webhook returns 400 Invalid JSON payload”
- Cause: Alert message is not valid JSON.
- Fix: Validate JSON syntax in TradingView alert message before saving.

### 3) “No alerts arrive at server”
- Cause: Wrong webhook URL, local network exposure issue, or service not running.
- Fix: Confirm receiver process is running and URL is publicly reachable.

### 4) “Tradovate test failed”
- Cause: demo URL mismatch or incomplete credentials.
- Fix: verify `TRADOVATE_API_BASE_URL` and credential fields.

### 5) “No trading during expected hours”
- Cause: session/news filters blocked execution.
- Fix: check `SessionManager` outputs (`get_current_session`, `is_news_window`, `is_high_volume_time`).

## Important financial risk disclaimer
This software is for educational and tooling purposes only. It is not financial advice. Futures trading carries substantial risk and can result in losses larger than your initial capital. Always test in paper mode first, use strict risk controls, and consult a licensed financial professional if needed.
