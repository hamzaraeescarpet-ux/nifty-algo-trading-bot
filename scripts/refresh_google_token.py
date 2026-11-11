import os
import json
import base64
import subprocess
import urllib.request
import ssl
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
import gspread
import nacl.encoding
import nacl.public

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

CLIENT_SECRET_PATH = r"C:\Users\hamza\Downloads\python development\amro store\client_secret_875992929801-3o9658vv47ih2lnegr8vcphbc494u0vm.apps.googleusercontent.com.json"
TOKEN_PATH = r"C:\Users\hamza\Downloads\python development\amro store\google_token.json"
REPO = "hamzaraeescarpet-ux/nifty-algo-trading-bot"

def get_github_token():
    p = subprocess.Popen(['git', 'credential', 'fill'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    creds = dict(line.split('=', 1) for line in out.splitlines() if '=' in line)
    return creds.get('password')

def upload_github_secret(secret_name: str, secret_value: str, gh_token: str):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # 1. Get public key
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
        headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json", "User-Agent": "Python"}
    )
    with urllib.request.urlopen(req, context=ctx) as resp:
        key_data = json.loads(resp.read().decode())
        public_key_b64 = key_data["key"]
        key_id = key_data["key_id"]

    # 2. Encrypt secret using PyNaCl
    public_key = nacl.public.PublicKey(public_key_b64.encode("utf-8"), nacl.encoding.Base64Encoder)
    sealed_box = nacl.public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")

    # 3. Put secret to GitHub
    put_data = json.dumps({
        "encrypted_value": encrypted_b64,
        "key_id": key_id
    }).encode("utf-8")

    put_req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/actions/secrets/{secret_name}",
        data=put_data,
        method="PUT",
        headers={"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json", "User-Agent": "Python", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(put_req, context=ctx) as resp:
        print(f"[GitHub] Secret '{secret_name}' successfully updated! HTTP Status: {resp.status}")

def run_login_flow():
    print("=" * 60)
    print("Starting Google OAuth Re-Authentication...")
    print("A browser tab will open automatically. Please sign in and approve access.")
    print("=" * 60)
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
    creds = flow.run_local_server(port=0)
    
    token_json = creds.to_json()
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(token_json)
    print(f"[Google Auth] Saved updated credentials to: {TOKEN_PATH}")

    # Test Google Sheet connection
    gc = gspread.authorize(creds)
    sheet = gc.open("Nifty50_Algo_Trading_Journal")
    print(f"[Google Sheets] Successfully verified connection to: '{sheet.title}'")

    # Update GitHub Secret
    gh_token = get_github_token()
    if gh_token:
        print("[GitHub] Updating secret GOOGLE_TOKEN_JSON on GitHub Actions...")
        upload_github_secret("GOOGLE_TOKEN_JSON", token_json, gh_token)
    else:
        print("[GitHub] Warning: GitHub personal access token not found via git credentials.")

    # Sync missing trades from paper_trades_journal.json to Google Sheet
    from data.google_sheets_sync import GoogleSheetsSync
    sync = GoogleSheetsSync(token_path=TOKEN_PATH, sheet_name="Nifty50_Algo_Trading_Journal")
    journal_path = Path("logs/paper_trades_journal.json")
    if journal_path.exists():
        with open(journal_path, "r", encoding="utf-8") as f:
            journal_data = json.load(f)
        trades = journal_data.get("history", [])
        print(f"[Sync] Syncing {len(trades)} trades to Google Sheets...")
        for t in trades:
            sync.log_trade(t)
        sync.update_daily_summary()
        sync.update_monthly_summary()
        sync.sync_all_ai_learnings()
        print("[Sync] Google Sheet is completely updated with all trades and AI learnings!")

if __name__ == "__main__":
    run_login_flow()
