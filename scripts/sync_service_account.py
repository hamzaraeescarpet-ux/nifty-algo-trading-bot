import os
import sys
import json
import base64
import subprocess
import urllib.request
import ssl
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from google.oauth2 import service_account
import gspread
import nacl.encoding
import nacl.public

REPO = "hamzaraeescarpet-ux/nifty-algo-trading-bot"
SA_PATH = Path("service_account.json")

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

def run_sync():
    with open(SA_PATH, "r", encoding="utf-8") as f:
        sa_content = f.read()
    
    # 1. Upload to GitHub Secrets
    gh_token = get_github_token()
    if gh_token:
        print("[1/3] Uploading Service Account key to GitHub Secrets...")
        upload_github_secret("GOOGLE_TOKEN_JSON", sa_content, gh_token)
        upload_github_secret("GOOGLE_SERVICE_ACCOUNT_JSON", sa_content, gh_token)
    else:
        print("[GitHub] Warning: GitHub personal access token not found.")

    # 2. Connect to Google Sheets & Sync Everything
    print("[2/3] Connecting to Google Sheet and syncing all trade data...")
    from data.google_sheets_sync import GoogleSheetsSync
    sync = GoogleSheetsSync(sheet_name="Nifty50_Algo_Trading_Journal")
    
    # Load paper trades
    journal_path = Path("logs/paper_trades_journal.json")
    if journal_path.exists():
        with open(journal_path, "r", encoding="utf-8") as f:
            j_data = json.load(f)
        trades = j_data.get("history", [])
        balance = j_data.get("balance", 100000.0)
        initial_capital = j_data.get("initial_capital", 100000.0)
        print(f"Syncing full history ({len(trades)} trades) to Google Sheets...")
        sync.sync_all_history_to_sheets(trades, balance, initial_capital)

    # 3. Sync AI Learning History
    print("[3/3] Syncing AI Self-Learning Engine history to 'AI Brain & Learnings' tab...")
    sync.sync_all_ai_learnings()
    print("\n[ALL DONE] Everything successfully synced to Google Sheets and GitHub Secrets!")

if __name__ == "__main__":
    run_sync()
