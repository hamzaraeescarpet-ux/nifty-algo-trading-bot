import json
import os
from pathlib import Path
from flask import Flask, render_template, jsonify
from config import settings

app = Flask(__name__, template_folder="templates")
BASE_DIR = Path(__file__).resolve().parent.parent
JOURNAL_FILE = BASE_DIR / "logs" / "paper_trades_journal.json"

ADAPTIVE_FILE = BASE_DIR / "config" / "adaptive_weights.json"

def load_adaptive_weights():
    if ADAPTIVE_FILE.exists():
        try:
            with open(ADAPTIVE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def load_journal():
    if JOURNAL_FILE.exists():
        try:
            with open(JOURNAL_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "initial_capital": settings.INITIAL_CAPITAL,
        "balance": settings.INITIAL_CAPITAL,
        "total_trades": 0,
        "history": [],
        "open_positions": []
    }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/stats")
def get_stats():
    journal = load_journal()
    history = journal.get("history", [])
    initial_cap = journal.get("initial_capital", settings.INITIAL_CAPITAL)
    balance = journal.get("balance", initial_cap)
    
    wins = [t for t in history if t.get("pnl", 0) > 0]
    losses = [t for t in history if t.get("pnl", 0) <= 0]
    total_pnl = sum(t.get("pnl", 0) for t in history)
    win_rate = round((len(wins) / len(history)) * 100, 2) if history else 0.0

    total_win_amt = sum(t.get("pnl", 0) for t in wins)
    total_loss_amt = abs(sum(t.get("pnl", 0) for t in losses))
    profit_factor = round(total_win_amt / total_loss_amt, 2) if total_loss_amt > 0 else (round(total_win_amt, 2) if total_win_amt > 0 else 0.0)

    ce_count = sum(1 for t in history if "CE" in t.get("symbol", "") or t.get("option_type") == "CE")
    pe_count = sum(1 for t in history if "PE" in t.get("symbol", "") or t.get("option_type") == "PE")

    # Equity curve calculation
    equity_curve = [initial_cap]
    equity_labels = ["Initial"]
    trade_pnls = []
    trade_labels = []

    running_balance = initial_cap
    daily_pnl_map = {}

    for i, t in enumerate(history):
        pnl = t.get("pnl", 0)
        running_balance += pnl
        equity_curve.append(round(running_balance, 2))
        t_label = t.get("exit_time") or t.get("entry_time") or f"Trade {i+1}"
        equity_labels.append(t_label.split(" ")[0] if " " in t_label else t_label)
        trade_pnls.append(round(pnl, 2))
        trade_labels.append(t.get("symbol", f"T{i+1}"))

        # Daily grouping
        date_key = t_label.split(" ")[0] if " " in t_label else "Unknown"
        daily_pnl_map[date_key] = round(daily_pnl_map.get(date_key, 0.0) + pnl, 2)

    adaptive_weights = load_adaptive_weights()

    return jsonify({
        "initial_capital": initial_cap,
        "balance": round(balance, 2),
        "total_pnl": round(total_pnl, 2),
        "total_trades": len(history),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "ce_count": ce_count,
        "pe_count": pe_count,
        "trade_pnls": trade_pnls,
        "trade_labels": trade_labels,
        "equity_curve": equity_curve,
        "equity_labels": equity_labels,
        "daily_pnl": daily_pnl_map,
        "open_positions": journal.get("open_positions", []),
        "history": history,
        "adaptive_weights": adaptive_weights,
        "google_sheet_url": settings.GOOGLE_SHEET_URL
    })

def run_dashboard():
    print(f"\n[Dashboard] Web Dashboard starting at http://{settings.DASHBOARD_HOST}:{settings.DASHBOARD_PORT}")
    app.run(host=settings.DASHBOARD_HOST, port=settings.DASHBOARD_PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    run_dashboard()
