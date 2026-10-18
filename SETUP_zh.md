# 早上要做的事（約 25 分鐘）

全部做完後，作品集的準確率數字和截圖就都有了。

## 1. 解壓縮
把 `invoice-extractor.zip` 下載下來，解壓縮到「文件」資料夾：
```bash
cd ~/Documents && unzip -o ~/Downloads/invoice-extractor.zip && cd invoice-extractor
```

## 2. 申請 Gemini API Key（3 分鐘）
1. 打開 https://aistudio.google.com/apikey ，用 `jwu.ai.dev@gmail.com` 登入
2. 按 **Create API key**，然後複製
3. ⚠️ Key 不要貼到聊天裡，只貼在下面的終端機指令，以及 n8n 的憑證欄位

## 3. 跑準確率評估（約 3 分鐘）
在終端機執行（`你的KEY` 換成剛才複製的那串）：
```bash
export HTTPS_PROXY=http://127.0.0.1:7890
export GEMINI_API_KEY=你的KEY
python3 eval.py
python3 fill_readme.py
```
跑完畫面會顯示準確率。把**那段結果**（不含 Key）貼給我。
- 出現 `HTTP 429`：免費額度暫時用完，等一分鐘再跑同一行。已經跑過的發票會自動跳過。
- 出現 `HTTP 404 model not found`：改用 `python3 eval.py --model gemini-3.6-flash` 再跑。

## 4. n8n 設定 Gemini 憑證（2 分鐘）
「**Invoice Extractor**」流程我已經匯入你的 n8n 了，狀態是未啟用。
1. 打開它，雙擊 **Gemini extract** 節點
2. Credential 選 **Create new credential**（類型是 Header Auth）
   - Name：`x-goog-api-key`
   - Value：你的 Gemini Key
3. 存檔

## 5. 建立 Google Sheet（2 分鐘）
1. 把 `sheets_template.xlsx` 上傳到 Google Drive
2. 打開它 → 選單「檔案」→「**儲存為 Google 試算表**」
3. 複製這份新試算表的網址

## 6. 讓 n8n 可以寫入 Google Sheets（約 10 分鐘，只要做一次）
本機的 n8n 要先在 Google Cloud 建一組 OAuth 憑證：
1. 打開 https://console.cloud.google.com/ ，建立新專案，名稱填 `n8n`
2. 「API 和服務」→「程式庫」→ 搜尋並啟用 **Google Sheets API** 和 **Google Drive API**
3. 「OAuth 同意畫面」→ 選「外部」→ 名稱填 `n8n` → 在「測試使用者」加入你自己的 Gmail
4. 「憑證」→「建立憑證」→「OAuth 用戶端 ID」→ 類型選「網頁應用程式」
   - 已授權的重新導向 URI 填：`http://localhost:5678/rest/oauth2-credential/callback`
5. 複製「用戶端 ID」和「用戶端密鑰」
6. 回到 n8n，雙擊 **Sheets: Invoices** → Credential 選 **Create new credential**（Google Sheets OAuth2）→ 貼上 ID 和密鑰 → 按 **Sign in with Google** 並允許
7. **Document** 貼上第 5 步複製的試算表網址
8. **Sheets: Line Items** 選同一個憑證，貼上同一個網址
9. 存檔

> 測試模式下 Google 的授權每 7 天會過期。過期時回到憑證頁，重新按一次 Sign in 就好。

## 7. 實際測試（3 分鐘）
1. 雙擊 **Upload form** → 複製 **Test URL**，或直接按 **Execute workflow**
2. 在打開的表單裡，從 `testdata/invoices/` 選 3 到 5 張發票上傳，建議包含 `inv_14_bw.pdf`（這張的總額故意算錯）
3. 打開 Google Sheet，確認 Invoices 和 Line Items 兩個分頁都有資料，算錯的那張標示為 **Needs review**
4. 截三張圖給我：n8n 全綠的流程、Invoices 分頁、Summary 分頁

做完之後跟我說，我接著做封面圖、上傳 GitHub、填 Upwork Portfolio。
