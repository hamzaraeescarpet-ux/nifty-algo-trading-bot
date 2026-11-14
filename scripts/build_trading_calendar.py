import calendar
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple
import json
import gspread
from google.oauth2 import service_account

BASE_DIR = Path(__file__).resolve().parent.parent
SA_FILE = BASE_DIR / "service_account.json"
JOURNAL_FILE = BASE_DIR / "logs" / "paper_trades_journal.json"

def get_color(r: float, g: float, b: float):
    return {"red": r, "green": g, "blue": b}

# Hex to RGB 0-1
COLOR_PROFIT_BG = get_color(212/255, 237/255, 218/255) # #D4EDDA Soft Green
COLOR_PROFIT_TXT = get_color(21/255, 87/255, 36/255)  # Dark Green

COLOR_LOSS_BG = get_color(248/255, 215/255, 218/255)   # #F8D7DA Soft Red
COLOR_LOSS_TXT = get_color(114/255, 28/255, 36/255)    # Dark Red

COLOR_BREAKEVEN_BG = get_color(209/255, 236/255, 241/255) # #D1ECF1 Soft Cyan/Blue
COLOR_BREAKEVEN_TXT = get_color(12/255, 84/255, 96/255)

COLOR_NOTRADE_BG = get_color(248/255, 249/255, 250/255)  # #F8F9FA Pale Neutral
COLOR_NOTRADE_TXT = get_color(108/255, 117/255, 125/255)

COLOR_HEADER_BG = get_color(200/255, 230/255, 201/255)   # Soft mint green header
COLOR_HEADER_TXT = get_color(27/255, 94/255, 32/255)

COLOR_TOTAL_BG = get_color(255/255, 243/255, 205/255)    # #FFF3CD Champagne
COLOR_TOTAL_TXT = get_color(133/255, 100/255, 4/255)

COLOR_TITLE_BG = get_color(44/255, 62/255, 80/255)       # Navy/Slate
COLOR_TITLE_TXT = get_color(1.0, 1.0, 1.0)

def aggregate_daily_pnl(trades: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Groups trades by 'YYYY-MM-DD'."""
    daily_stats = {}
    for t in trades:
        entry_time = t.get("entry_time", "")
        if not entry_time:
            continue
        try:
            # Parse 'DD-Mon-YYYY HH:MM:SS'
            dt = datetime.strptime(entry_time.split(" ")[0], "%d-%b-%Y")
            date_key = dt.strftime("%Y-%m-%d")
        except Exception:
            continue

        if date_key not in daily_stats:
            daily_stats[date_key] = {"trades": 0, "pnl": 0.0, "wins": 0, "losses": 0, "breakeven": 0}

        pnl = float(t.get("pnl", 0.0))
        daily_stats[date_key]["trades"] += 1
        daily_stats[date_key]["pnl"] += pnl
        if pnl > 0:
            daily_stats[date_key]["wins"] += 1
        elif pnl < 0:
            daily_stats[date_key]["losses"] += 1
        else:
            daily_stats[date_key]["breakeven"] += 1

    return daily_stats

def build_month_grid(year: int, month: int, daily_stats: Dict[str, Dict[str, Any]]) -> Tuple[List[List[str]], List[Dict[str, Any]]]:
    """Builds grid values and formatting requests for a month."""
    cal = calendar.Calendar(firstweekday=6) # 6 = Sunday
    weeks = cal.monthdayscalendar(year, month)
    month_name = calendar.month_name[month].upper()

    rows = []
    formats = [] # Cell format metadata

    for w_idx, week in enumerate(weeks):
        row_vals = []
        row_meta = []
        w_trades = 0
        w_pnl = 0.0

        for col_idx, day in enumerate(week):
            if day == 0:
                row_vals.append("")
                row_meta.append({"type": "EMPTY"})
            else:
                date_str = f"{year:04d}-{month:02d}-{day:02d}"
                stats = daily_stats.get(date_str, {"trades": 0, "pnl": 0.0})
                t_count = stats["trades"]
                pnl = stats["pnl"]
                w_trades += t_count
                w_pnl += pnl

                # Form cell text exactly like trader heatmap:
                # Line 1: Day
                # Line 2: X trades
                # Line 3: Rs. +/-P&L
                if pnl > 0:
                    pnl_str = f"+Rs. {pnl:,.2f}"
                    cell_type = "PROFIT"
                elif pnl < 0:
                    pnl_str = f"-Rs. {abs(pnl):,.2f}"
                    cell_type = "LOSS"
                elif t_count > 0:
                    pnl_str = "Rs. 0.00"
                    cell_type = "BREAKEVEN"
                else:
                    pnl_str = "Rs. 0.00"
                    cell_type = "NOTRADE"

                text = f"{day}\n{t_count} trades\n{pnl_str}"
                row_vals.append(text)
                row_meta.append({"type": cell_type, "pnl": pnl, "trades": t_count})

        # Week Total column (Column 8)
        if w_pnl > 0:
            w_pnl_str = f"+Rs. {w_pnl:,.2f}"
        elif w_pnl < 0:
            w_pnl_str = f"-Rs. {abs(w_pnl):,.2f}"
        else:
            w_pnl_str = "Rs. 0.00"

        w_total_text = f"Week {w_idx + 1}\n{w_trades} trades\n{w_pnl_str}"
        row_vals.append(w_total_text)
        row_meta.append({"type": "TOTAL", "pnl": w_pnl, "trades": w_trades})

        rows.append(row_vals)
        formats.append(row_meta)

    return rows, formats

def sync_calendar_tab():
    if not SA_FILE.exists():
        print(f"Error: {SA_FILE} not found.")
        return

    creds = service_account.Credentials.from_service_account_file(
        str(SA_FILE),
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    gc = gspread.authorize(creds)
    ss = gc.open("Nifty50_Algo_Trading_Journal")

    sheet_title = "Trading Calendar"
    try:
        ws = ss.worksheet(sheet_title)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=sheet_title, rows=100, cols=10)

    # Load trades
    with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
        journal_data = json.load(f)
    trades = journal_data.get("history", [])
    daily_stats = aggregate_daily_pnl(trades)

    # Let's build November 2026 and October 2026
    months_to_render = [(2026, 11), (2026, 10)]

    all_rows = []
    batch_requests = []
    current_row = 1 # 1-based index for GSheets

    for year, month in months_to_render:
        m_name = calendar.month_name[month].upper()
        # Calculate monthly totals
        m_trades = sum(s["trades"] for d, s in daily_stats.items() if d.startswith(f"{year:04d}-{month:02d}"))
        m_pnl = sum(s["pnl"] for d, s in daily_stats.items() if d.startswith(f"{year:04d}-{month:02d}"))
        m_pnl_str = f"+Rs. {m_pnl:,.2f}" if m_pnl > 0 else (f"-Rs. {abs(m_pnl):,.2f}" if m_pnl < 0 else "Rs. 0.00")

        # 1. Month Header Banner
        banner_text = f"📅 {m_name} {year} - TRADING PERFORMANCE CALENDAR | Total P&L: {m_pnl_str} | Total Trades: {m_trades}"
        all_rows.append([banner_text, "", "", "", "", "", "", ""])
        
        # Merge Row for Banner
        batch_requests.append({
            "mergeCells": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": current_row - 1,
                    "endRowIndex": current_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 8
                },
                "mergeType": "MERGE_ALL"
            }
        })
        # Style Banner
        batch_requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": current_row - 1,
                    "endRowIndex": current_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 8
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": COLOR_TITLE_BG,
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "textFormat": {"foregroundColor": COLOR_TITLE_TXT, "bold": True, "fontSize": 12}
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"
            }
        })
        current_row += 1

        # 2. Weekday Header Row
        headers = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT", "TOTAL"]
        all_rows.append(headers)
        batch_requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": current_row - 1,
                    "endRowIndex": current_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": 8
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": COLOR_HEADER_BG,
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "textFormat": {"foregroundColor": COLOR_HEADER_TXT, "bold": True, "fontSize": 11}
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"
            }
        })
        current_row += 1

        # 3. Calendar Grid Rows
        grid_rows, grid_meta = build_month_grid(year, month, daily_stats)
        grid_start_row = current_row

        for w_idx, (r_vals, r_meta) in enumerate(zip(grid_rows, grid_meta)):
            all_rows.append(r_vals)
            row_idx = current_row - 1

            for col_idx, meta in enumerate(r_meta):
                c_type = meta["type"]
                if c_type == "PROFIT":
                    bg = COLOR_PROFIT_BG
                    txt = COLOR_PROFIT_TXT
                    bold = True
                elif c_type == "LOSS":
                    bg = COLOR_LOSS_BG
                    txt = COLOR_LOSS_TXT
                    bold = True
                elif c_type == "BREAKEVEN":
                    bg = COLOR_BREAKEVEN_BG
                    txt = COLOR_BREAKEVEN_TXT
                    bold = True
                elif c_type == "TOTAL":
                    bg = COLOR_TOTAL_BG
                    txt = COLOR_TOTAL_TXT
                    bold = True
                elif c_type == "NOTRADE":
                    bg = COLOR_NOTRADE_BG
                    txt = COLOR_NOTRADE_TXT
                    bold = False
                else: # EMPTY
                    bg = get_color(1.0, 1.0, 1.0)
                    txt = get_color(0.5, 0.5, 0.5)
                    bold = False

                batch_requests.append({
                    "repeatCell": {
                        "range": {
                            "sheetId": ws.id,
                            "startRowIndex": row_idx,
                            "endRowIndex": row_idx + 1,
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": bg,
                                "horizontalAlignment": "CENTER",
                                "verticalAlignment": "MIDDLE",
                                "wrapStrategy": "WRAP",
                                "textFormat": {"foregroundColor": txt, "bold": bold, "fontSize": 10}
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat)"
                    }
                })

            current_row += 1

        # Add border around this month's grid
        batch_requests.append({
            "updateBorders": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": grid_start_row - 1,
                    "endRowIndex": current_row - 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 8
                },
                "top": {"style": "SOLID", "color": {"red": 0.4, "green": 0.4, "blue": 0.4}},
                "bottom": {"style": "SOLID", "color": {"red": 0.4, "green": 0.4, "blue": 0.4}},
                "left": {"style": "SOLID", "color": {"red": 0.4, "green": 0.4, "blue": 0.4}},
                "right": {"style": "SOLID", "color": {"red": 0.4, "green": 0.4, "blue": 0.4}},
                "innerHorizontal": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                "innerVertical": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}}
            }
        })

        # Empty spacer rows between months
        all_rows.append(["", "", "", "", "", "", "", ""])
        all_rows.append(["", "", "", "", "", "", "", ""])
        current_row += 2

    # Set column widths
    for col_i in range(8):
        batch_requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": ws.id,
                    "dimension": "COLUMNS",
                    "startIndex": col_i,
                    "endIndex": col_i + 1
                },
                "properties": {"pixelSize": 125},
                "fields": "pixelSize"
            }
        })

    # 1. Push cell values
    ws.update(range_name='A1', values=all_rows)
    print(f"[Calendar] Pushed {len(all_rows)} rows to '{sheet_title}' tab.")

    # 2. Execute Batch Formatting
    if batch_requests:
        ss.batch_update({"requests": batch_requests})
        print(f"[Calendar] Applied {len(batch_requests)} formatting rules (colors, borders, alignments)!")

    print(f"\n[SUCCESS] '{sheet_title}' is fully created and styled!")

if __name__ == "__main__":
    sync_calendar_tab()
