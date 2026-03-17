# 🏨 Tokyo Inn 空房監控

GitHub Actions 自動監控東橫 Inn 空房，有空房時發送 Telegram / Discord / LINE 通知。

## 使用方法

### 1. Fork 或建立此 Repo（設為 Public 可無限免費運行）

### 2. 加入 Secrets

進入 repo 的 **Settings → Secrets and variables → Actions → New repository secret**

| Secret 名稱 | 說明 | 範例 |
|------------|------|------|
| `SCRAPE_URLS` | 監控網址，多個用逗號分隔 | `https://www.toyoko-inn.com/...` |
| `TG_BOT_TOKEN` | Telegram Bot Token，多個用逗號 | `123456:ABC...` |
| `TG_CHAT_ID` | Telegram Chat ID，多個用逗號 | `987654321` |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL（選填） | `https://discord.com/api/webhooks/...` |
| `LINE_NOTIFY_TOKEN` | LINE Notify Token（選填） | `xxxxxx` |
| `EMAIL_USERNAME` | 寄件 Email（選填） | `your@gmail.com` |
| `EMAIL_PASSWORD` | Email 密碼或應用程式密碼（選填） | `xxxx xxxx xxxx` |
| `EMAIL_TARGET_ADDRESS` | 收件 Email（選填） | `target@gmail.com` |

### 3. 設定檢查頻率

編輯 `.github/workflows/monitor.yml` 的 cron 表達式：

```yaml
- cron: "*/10 * * * *"   # 每 10 分鐘
- cron: "*/5 * * * *"    # 每 5 分鐘（最小間隔）
- cron: "*/30 * * * *"   # 每 30 分鐘
```

### 4. 手動觸發

進入 repo 的 **Actions → Tokyo Inn 空房監控 → Run workflow**

## 注意事項

- Public repo 的 GitHub Actions 是**完全免費無限制**的
- Private repo 每月有 2,000 分鐘免費額度
- 多個 URL / Token 用**逗號**分隔，不要有空格
