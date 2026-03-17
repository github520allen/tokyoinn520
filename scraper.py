"""
Tokyo Inn 空房監控 - GitHub Actions 版本
設定方式：在 GitHub repo 的 Settings > Secrets and variables > Actions 加入 Secrets
"""
import os
import datetime
import logging
import urllib.parse
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from playwright.sync_api import sync_playwright

# ==========================================
# 從環境變數讀取設定
# ==========================================
def get_list(env_key: str) -> list:
    val = os.environ.get(env_key, "")
    return [v.strip() for v in val.split(",") if v.strip()]

URLS               = get_list("SCRAPE_URLS")
TG_TOKENS          = get_list("TG_BOT_TOKEN")
TG_CHAT_IDS        = get_list("TG_CHAT_ID")
DISCORD_WEBHOOK    = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
LINE_TOKEN         = os.environ.get("LINE_NOTIFY_TOKEN", "").strip()
EMAIL_SMTP_SERVER  = os.environ.get("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT    = os.environ.get("EMAIL_SMTP_PORT", "587")
EMAIL_USERNAME     = os.environ.get("EMAIL_USERNAME", "").strip()
EMAIL_PASSWORD     = os.environ.get("EMAIL_PASSWORD", "").strip()
EMAIL_TARGET       = os.environ.get("EMAIL_TARGET_ADDRESS", "").strip()

# ==========================================
# 日誌
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)

# ==========================================
# 通知函式
# ==========================================
def send_telegram(message: str, photo_bytes: bytes = None) -> None:
    pairs = list(zip(TG_TOKENS, TG_CHAT_IDS))
    if not pairs:
        log.warning("Telegram 未設定，跳過。")
        return
    for idx, (token, chat_id) in enumerate(pairs, 1):
        try:
            if photo_bytes:
                resp = requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": message, "parse_mode": "HTML"},
                    files={"photo": ("screenshot.jpg", photo_bytes, "image/jpeg")},
                    timeout=30,
                )
            else:
                resp = requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                    timeout=10,
                )
            resp.raise_for_status()
            log.info(f"✅ Telegram Bot {idx} 通知成功")
        except Exception as e:
            log.error(f"❌ Telegram Bot {idx} 通知失敗: {e}")


def send_discord(message: str, hotel: str = "", price: str = "", url: str = "", schedule: str = "") -> None:
    if not DISCORD_WEBHOOK:
        return
    fields = []
    if schedule:
        fields.append({"name": "📅 日程", "value": schedule, "inline": False})
    if hotel:
        fields.append({"name": "🏨 飯店", "value": hotel, "inline": False})
    if price:
        fields.append({"name": "💰 價格", "value": price, "inline": False})
    if url:
        fields.append({"name": "🔗 連結", "value": f"[點此前往]({url})", "inline": False})
    payload = {
        "content": "🛎 **東橫 Inn 空房通知** 🛎",
        "embeds": [{"title": "找到空房！", "color": 0x00FF00, "fields": fields}],
    }
    try:
        resp = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        resp.raise_for_status()
        log.info("✅ Discord 通知成功")
    except Exception as e:
        log.error(f"❌ Discord 通知失敗: {e}")


def send_line(message: str) -> None:
    if not LINE_TOKEN:
        return
    try:
        resp = requests.post(
            "https://notify-api.line.me/api/notify",
            headers={"Authorization": f"Bearer {LINE_TOKEN}"},
            data={"message": f"\n{message}"},
            timeout=10,
        )
        resp.raise_for_status()
        log.info("✅ LINE 通知成功")
    except Exception as e:
        log.error(f"❌ LINE 通知失敗: {e}")


def send_email(subject: str, body: str) -> None:
    if not all([EMAIL_SMTP_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_TARGET]):
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_USERNAME
        msg["To"] = EMAIL_TARGET
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))
        server = smtplib.SMTP(EMAIL_SMTP_SERVER, int(EMAIL_SMTP_PORT), timeout=15)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        log.info("✅ Email 通知成功")
    except Exception as e:
        log.error(f"❌ Email 通知失敗: {e}")


# ==========================================
# 主要爬蟲邏輯
# ==========================================
def run() -> None:
    if not URLS:
        log.error("❌ 未設定 SCRAPE_URLS，請在 GitHub Secrets 加入此變數。")
        return

    log.info(f"🚀 開始檢查 {len(URLS)} 個東橫 Inn 網址...")
    found_any = False

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        for idx, url in enumerate(URLS, 1):
            log.info(f"[{idx}/{len(URLS)}] 前往: {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(2000)

                # 解析日期
                params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                start  = params.get("start", [""])[0].replace("-", "/")
                end    = params.get("end",   [""])[0].replace("-", "/")
                schedule = f"{start} ~ {end}" if start and end else start or ""

                # 截圖
                screenshot = page.screenshot(type="jpeg", quality=60)

                # 飯店名稱
                hotel = "未知飯店"
                try:
                    # 先試搜尋結果頁的特定 class
                    hotel_selectors = [
                        "[class*='CardResults_title']",
                        "[class*='hotelName']",
                        "[class*='hotel-name']",
                        "[class*='HotelName']",
                        "[class*='htlName']",
                        "[class*='CardResults_name']",
                        "[class*='card-name']",
                        "[class*='result-name']",
                        "[class*='property-name']",
                    ]
                    for selector in hotel_selectors:
                        els = page.locator(selector).all_inner_texts()
                        if els:
                            hotel = els[0].strip()
                            break

                    # 若還是未知，從 h1~h4 找含關鍵字的
                    if hotel == "未知飯店":
                        hints = page.locator("h1,h2,h3,h4").all_inner_texts()
                        for h in hints:
                            if any(k in h for k in ["東橫", "Toyoko", "Tokyo", "Inn", "inn"]):
                                hotel = h.strip()
                                break

                    # 最後嘗試從頁面標題抓
                    if hotel == "未知飯店":
                        title = page.title()
                        if title and len(title) > 2:
                            hotel = title.split("|")[0].strip()
                except Exception:
                    pass

                # 價格
                price = ""
                try:
                    price_hints = page.locator(
                        ".CardResults_description__szF_r,.CardResults_-sub__axTfm"
                    ).all_inner_texts()
                    for ph in price_hints:
                        if "¥" in ph or "￥" in ph:
                            price = ph.strip()
                            break
                    if not price:
                        fallback = page.locator(
                            "p:has-text('¥'),p:has-text('￥'),p:has-text('日元')"
                        ).all_inner_texts()
                        if fallback:
                            price = fallback[0].strip()
                except Exception:
                    pass

                # 判斷是否有空房
                body_text = ""
                try:
                    body_text = page.inner_text("body")
                except Exception:
                    pass

                # 無空房關鍵字（繁體、簡體、英文、日文）
                no_room_keywords = [
                    "沒有找到符合的搜尋結果",
                    "没有找到符合的搜索结果",
                    "No matching results",
                    "沒有空房", "没有空房",
                    "満室", "空室なし",
                    "ご希望の条件に合う客室はございません",
                    "该条件下暂无可用客房",
                    "no rooms available",
                ]
                no_room_flag = any(k.lower() in body_text.lower() for k in no_room_keywords)

                # 正向判斷：頁面上有沒有房間卡片
                room_card_count = 0
                try:
                    room_card_count = page.locator(
                        ".CardResults, .card-result, .hotel-card, "
                        "[class*='CardResults'], [class*='hotelCard'], "
                        "[class*='roomCard'], [class*='result-item']"
                    ).count()
                except Exception:
                    pass

                log.info(f"[{idx}] 無空房關鍵字: {no_room_flag} | 房間卡片數: {room_card_count}")

                # 有無空房關鍵字 OR 完全沒有房間卡片 → 判定無空房
                no_room = no_room_flag or room_card_count == 0

                if no_room:
                    log.info(f"[{idx}] 無空房，跳過通知")
                else:
                    found_any = True
                    info = price or hotel
                    msg = (
                        f"🛎 Tokyo Inn 可能有空房 🛎\n\n"
                        f"📅 日程: {schedule}\n"
                        f"🏨 飯店: {hotel}\n"
                        f"💡 資訊: {info}\n"
                        f"🔗 連結: {url}"
                    )
                    log.info(f"✅ 偵測到空房！{hotel} {schedule}")
                    send_telegram(msg, screenshot)
                    send_discord(msg, hotel, price, url, schedule)
                    send_line(msg)
                    send_email("🛎 Tokyo Inn 空房通知", msg.replace("\n", "<br>"))

            except Exception as e:
                log.error(f"[{idx}] 檢查失敗: {e}")

        browser.close()

    if not found_any:
        log.info("本次檢查完畢，未發現空房。")
    else:
        log.info("本次檢查完畢，已發送空房通知！")


if __name__ == "__main__":
    run()
