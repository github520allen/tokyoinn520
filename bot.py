"""
Tokyo Inn 監控 Telegram Bot
部署於 Render.com，透過 Webhook 接收 Telegram 指令
"""
import os
import logging
import requests
from flask import Flask, request

# ==========================================
# 設定
# ==========================================
BOT_TOKEN      = os.environ.get("TG_BOT_TOKEN", "").strip()
ALLOWED_CHATS  = set(os.environ.get("TG_CHAT_ID", "").replace(" ", "").split(","))
GH_TOKEN       = os.environ.get("GH_TOKEN", "").strip()       # GitHub Personal Access Token
GH_OWNER       = os.environ.get("GH_OWNER", "").strip()       # GitHub 帳號
GH_REPO        = os.environ.get("GH_REPO", "").strip()        # GitHub Repo 名稱
GH_WORKFLOW    = os.environ.get("GH_WORKFLOW", "monitor.yml") # Workflow 檔名
RENDER_URL     = os.environ.get("RENDER_URL", "").strip()     # Render 的外部網址

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

# ==========================================
# Telegram API 工具
# ==========================================
def tg_send(chat_id: str, text: str) -> None:
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log.error(f"發送訊息失敗: {e}")


def tg_set_webhook() -> None:
    if not RENDER_URL:
        log.warning("未設定 RENDER_URL，無法設定 Webhook")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    resp = requests.post(url, json={"url": f"{RENDER_URL}/webhook"}, timeout=10)
    log.info(f"Webhook 設定結果: {resp.json()}")


# ==========================================
# GitHub Actions API
# ==========================================
def gh_headers() -> dict:
    return {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def gh_base() -> str:
    return f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/actions/workflows/{GH_WORKFLOW}"


def get_workflow_state() -> str:
    """回傳 active / disabled_manually / unknown"""
    try:
        resp = requests.get(gh_base(), headers=gh_headers(), timeout=10)
        data = resp.json()
        return data.get("state", "unknown")
    except Exception:
        return "unknown"


def enable_workflow() -> bool:
    try:
        resp = requests.put(f"{gh_base()}/enable", headers=gh_headers(), timeout=10)
        return resp.status_code == 204
    except Exception:
        return False


def disable_workflow() -> bool:
    try:
        resp = requests.put(f"{gh_base()}/disable", headers=gh_headers(), timeout=10)
        return resp.status_code == 204
    except Exception:
        return False


def trigger_workflow() -> bool:
    """立即手動觸發一次"""
    try:
        resp = requests.post(
            f"{gh_base()}/dispatches",
            headers=gh_headers(),
            json={"ref": "main"},
            timeout=10,
        )
        # 也試試 master
        if resp.status_code == 422:
            resp = requests.post(
                f"{gh_base()}/dispatches",
                headers=gh_headers(),
                json={"ref": "master"},
                timeout=10,
            )
        return resp.status_code == 204
    except Exception:
        return False


def get_recent_runs(limit: int = 5) -> list:
    """取得最近幾次執行紀錄"""
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/actions/workflows/{GH_WORKFLOW}/runs?per_page={limit}",
            headers=gh_headers(),
            timeout=10,
        )
        runs = resp.json().get("workflow_runs", [])
        return runs
    except Exception:
        return []


# ==========================================
# 指令處理
# ==========================================
HELP_TEXT = """🏨 <b>Tokyo Inn 空房監控 Bot</b>

可用指令：
/start   — 開啟自動監控（啟用排程）
/stop    — 關閉自動監控（停用排程）
/run     — 立即檢查一次
/status  — 查看目前監控狀態
/history — 最近 5 次執行紀錄
/help    — 顯示此說明"""


def handle_command(chat_id: str, text: str) -> None:
    cmd = text.strip().split()[0].lower().split("@")[0]

    if cmd == "/start":
        ok = enable_workflow()
        if ok:
            tg_send(chat_id, "✅ 監控已<b>開啟</b>！\n每 5 分鐘自動檢查一次，有空房會通知你。")
        else:
            tg_send(chat_id, "❌ 開啟失敗，請確認 GH_TOKEN 是否設定正確。")

    elif cmd == "/stop":
        ok = disable_workflow()
        if ok:
            tg_send(chat_id, "🛑 監控已<b>關閉</b>。\n傳 /start 可以重新開啟。")
        else:
            tg_send(chat_id, "❌ 關閉失敗，請確認 GH_TOKEN 是否設定正確。")

    elif cmd == "/run":
        tg_send(chat_id, "🔍 正在觸發立即檢查...")
        ok = trigger_workflow()
        if ok:
            tg_send(chat_id, "✅ 已觸發！約 1 分鐘後出結果，有空房會通知你。")
        else:
            tg_send(chat_id, "❌ 觸發失敗，請確認 GH_TOKEN 和 repo 設定是否正確。")

    elif cmd == "/status":
        state = get_workflow_state()
        if state == "active":
            status_text = "🟢 <b>監控中</b>（每 5 分鐘自動檢查）"
        elif state == "disabled_manually":
            status_text = "🔴 <b>已停止</b>（傳 /start 重新開啟）"
        else:
            status_text = f"⚠️ 狀態未知：{state}"
        tg_send(chat_id, f"目前狀態：{status_text}")

    elif cmd == "/history":
        runs = get_recent_runs(5)
        if not runs:
            tg_send(chat_id, "⚠️ 無法取得執行紀錄")
            return
        lines = ["📋 <b>最近 5 次執行紀錄：</b>\n"]
        for r in runs:
            icon = "✅" if r.get("conclusion") == "success" else (
                   "❌" if r.get("conclusion") == "failure" else "🔄")
            trigger = "排程" if r.get("event") == "schedule" else "手動"
            created = r.get("created_at", "")[:16].replace("T", " ")
            lines.append(f"{icon} {created} [{trigger}]")
        tg_send(chat_id, "\n".join(lines))

    elif cmd == "/help":
        tg_send(chat_id, HELP_TEXT)

    else:
        tg_send(chat_id, f"❓ 不認識的指令：{cmd}\n\n{HELP_TEXT}")


# ==========================================
# Flask Webhook
# ==========================================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)
    if not data:
        return "ok"

    message = data.get("message") or data.get("edited_message")
    if not message:
        return "ok"

    chat_id = str(message.get("chat", {}).get("id", ""))
    text    = message.get("text", "")

    # 只回應已授權的 chat
    if ALLOWED_CHATS and chat_id not in ALLOWED_CHATS:
        log.warning(f"未授權的 chat_id: {chat_id}")
        tg_send(chat_id, "⛔ 你沒有權限使用此 Bot。")
        return "ok"

    if text.startswith("/"):
        handle_command(chat_id, text)
    else:
        tg_send(chat_id, "📌 請使用指令操作，傳 /help 查看所有指令。")

    return "ok"


@app.route("/", methods=["GET"])
def index():
    return "Tokyo Inn Bot is running 🏨"


@app.route("/setup", methods=["GET"])
def setup():
    """手動觸發 Webhook 設定"""
    tg_set_webhook()
    return "Webhook set!"


# ==========================================
# 啟動
# ==========================================
if __name__ == "__main__":
    tg_set_webhook()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
