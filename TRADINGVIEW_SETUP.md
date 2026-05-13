# TradingView Setup Guide — Lucid AI Trader
## Takes 10 minutes. Works on TradingView web and desktop app.

### Step 1: Open TradingView
Go to tradingview.com or open the TradingView desktop app.
Open chart for CME_MINI:MES1! (S&P 500 Micro) or CME_MINI:MNQ1! (Nasdaq Micro).

### Step 2: Add the Pine Script
Click "Pine Editor" (bottom of chart) → New Script → Delete all existing code.
Open `lucid-ai-trader/pine_scripts/signal_overlay.pine` in any text editor.
Copy ALL content → Paste into Pine Editor → Click "Add to Chart".

### Step 3: Configure the indicator
Click the gear icon on the "Lucid AI Trader" indicator → Settings.
All settings are pre-configured. No changes needed unless customizing.

### Step 4: Create the webhook alert
Click the bell icon or right-click the chart → "Add Alert".
- Condition: Select "Lucid AI Trader" → "Lucid AI Signal"
- Alert Actions: Check "Webhook URL"
- Webhook URL: `http://YOUR_SERVER_IP:8080/api/tv/webhook`
  (If running locally: start ngrok → copy the https URL → use that URL)
- Message field: leave as-is (default)
- Click "Create".

### Step 5: Get your public URL (if running locally)
```
ngrok http 8080
```
Copy the `https://abc123.ngrok.io` URL.
Use `https://abc123.ngrok.io/api/tv/webhook` as your webhook URL.

The bot logs the correct webhook URL at startup:
```
TradingView webhook URL: https://abc123.ngrok.io/api/tv/webhook
```

### Step 6: Verify connection
```bash
python main.py --mode paper --test-tv
```
This runs a self-contained integration test — no live broker connection needed.

Once running normally:
```bash
python main.py --mode paper
```

In your dashboard, the "AI Draws" tab polls for drawings every 5 seconds.
Wait for the first ORB to be established (9:30–9:45 AM ET).
You should see the ORB high/low lines appear on your TradingView chart.

### Dashboard keyboard shortcut
`Ctrl+T` toggles between Embedded Chart mode and AI Draws mode.

### That's it. The bot now controls your TradingView chart.
