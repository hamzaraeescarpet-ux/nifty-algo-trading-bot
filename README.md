# ⚡ Nifty 50 Options Algo Trading Bot (Paper & Live Ready)

Professional Algorithmic Trading Bot focused purely on **Nifty 50 Index Options (CE / PE Buying)** with **Real-time Google Sheets Journaling**, **Local Web Dashboard**, and **Windows Background Auto-Start**.

---

## 🌟 Key Features

1. **Nifty 50 Options Strategy (ATM CE / PE)**:
   - Tracks underlying **Nifty 50 Spot (`^NSEI`)**.
   - Bullish Confluence $\rightarrow$ Automatic **ATM CALL (CE)** Buying.
   - Bearish Confluence $\rightarrow$ Automatic **ATM PUT (PE)** Buying.
   - ATM Strike calculated dynamically rounded to 50 points.
   - Volatility ATR Stop-Loss & 1:2 Target scaled by Option Delta ($\Delta \approx 0.5$).
   - Trailing Stop-Loss protects profits as trades advance.

2. **Google Sheets Real-Time Sync**:
   - Every closed trade automatically uploads to your Google Spreadsheet:
   - **Spreadsheet Link:** [Nifty50_Algo_Trading_Journal](https://docs.google.com/spreadsheets/d/1o37uPLPB9WrR97q3quvk8qFJm_JY5S5mJGgF4a-hhgE)
   - Tabs:
     - `Trade Logs` : Full trade details, strike, PnL, exit reasons.
     - `Daily Summary` : Win rate, total trades, closing balance.
     - `Monthly Summary` : Monthly aggregated performance.

3. **Modern Local Web Dashboard (`http://127.0.0.1:5000`)**:
   - Live Equity growth curve.
   - Win/Loss doughnut breakdown.
   - Real-time active positions table.
   - One-click Google Sheet link.

4. **Silent Windows Auto-Start**:
   - Starts silently in the background whenever your laptop boots.
   - Sleeps automatically during off-market hours and activates at 9:15 AM IST.
   - Auto squares-off all positions at 3:15 PM IST.

---

## 🚀 Quick Commands & Batch Files

| File | Kaam (Purpose) |
|---|---|
| `start_bot.bat` | Bot ko open console window me start karein. |
| `start_bot_hidden.vbs` | Bot ko bina kisi black window ke background me chalayein. |
| `open_dashboard.bat` | Web Dashboard browser me kholein (`http://127.0.0.1:5000`). |
| `view_live_terminal.bat` | Background bot ki live activity terminal me dekhein. |
| `setup_autostart.bat` | Laptop boot hote hi automatic bot chalne ke liye setup karein. |
| `stop_bot.bat` | Background bot process ko band karein. |

---

## 🧪 Off-Market Testing (Abhi Test Karein)

Market band hone par test karne ke liye:
```bash
python run_bot.py --simulate
```
*Ye pichle real market candles replay karega, options trades lega, Google Sheet me sync karega aur dashboard update karega.*
