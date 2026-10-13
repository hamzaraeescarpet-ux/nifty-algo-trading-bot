import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings
JOURNAL_FILE = BASE_DIR / "logs" / "paper_trades_journal.json"
TEMPLATE_FILE = BASE_DIR / "dashboard" / "templates" / "index.html"
OUTPUT_FILE = BASE_DIR / "dashboard" / "report.html"

def generate_static_report():
    if not JOURNAL_FILE.exists() or not TEMPLATE_FILE.exists():
        print("[Report] Journal or template not found.")
        return

    with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
        journal = json.load(f)

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        html = f.read()

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

    equity_curve = [initial_cap]
    equity_labels = ["Initial"]
    trade_pnls = []
    trade_labels = []
    running_balance = initial_cap

    for i, t in enumerate(history):
        pnl = t.get("pnl", 0)
        running_balance += pnl
        equity_curve.append(round(running_balance, 2))
        t_label = t.get("exit_time") or t.get("entry_time") or f"Trade {i+1}"
        equity_labels.append(t_label.split(" ")[0] if " " in t_label else t_label)
        trade_pnls.append(round(pnl, 2))
        trade_labels.append(t.get("symbol", f"T{i+1}"))

    stats_data = {
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
        "open_positions": journal.get("open_positions", []),
        "history": history,
        "google_sheet_url": settings.GOOGLE_SHEET_URL
    }

    # Embed static data
    stats_json_str = json.dumps(stats_data)
    preload_block = (
        "<script>\n"
        "    const STATIC_DATA = " + stats_json_str + ";\n"
        "    const origFetch = window.fetch;\n"
        "    window.fetch = async function(url, opts) {\n"
        "        if (typeof url === 'string' && url.includes('/api/stats')) {\n"
        "            return { ok: true, json: async () => STATIC_DATA };\n"
        "        }\n"
        "        return origFetch(url, opts);\n"
        "    };\n"
        "</script>\n"
    )

    html_mod = html.replace("<script>", preload_block + "<script>", 1)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_mod)

    print(f"[Report] Generated standalone dashboard report: {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_static_report()
