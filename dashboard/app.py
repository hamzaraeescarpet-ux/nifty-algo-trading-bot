import json
import os
from pathlib import Path
from flask import Flask, render_template, jsonify
from config import settings

app = Flask(__name__, template_folder="templates")
BASE_DIR = Path(__file__).resolve().parent.parent
JOURNAL_FILE = BASE_DIR / "logs" / "paper_trades_journal.json"

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

    # Equity curve calculation
    equity_curve = [initial_cap]
    running_balance = initial_cap
    for t in history:
        running_balance += t.get("pnl", 0)
        equity_curve.append(round(running_balance, 2))

    return jsonify({
        "initial_capital": initial_cap,
        "balance": round(balance, 2),
        "total_pnl": round(total_pnl, 2),
        "total_trades": len(history),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "open_positions": journal.get("open_positions", []),
        "history": history,
        "equity_curve": equity_curve,
        "google_sheet_url": settings.GOOGLE_SHEET_URL
    })

def run_dashboard():
    print(f"\n[Dashboard] Web Dashboard starting at http://{settings.DASHBOARD_HOST}:{settings.DASHBOARD_PORT}")
    app.run(host=settings.DASHBOARD_HOST, port=settings.DASHBOARD_PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    run_dashboard()
