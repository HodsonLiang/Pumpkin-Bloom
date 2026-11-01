# Pikmin Mushroom 控制台

Windows 桌面工具，透過 pymobiledevice3 操作 iPhone 模擬定位，提供路徑移動與截圖辨識兩種模式。

- **路徑移動**：地圖標點、速度與傳送間隔設定、剩餘時間、循環路線、暫停與路線匯入／匯出。
- **目標搜尋**：依座標清單傳送與截圖，地圖顯示搜尋點及命中點，預覽截圖、匯出結果、停止後續掃。
- **座標產生**：從 Geoapify 下載各國城市、城鎮、村莊及聚落，快取後可離線產生座標。

## 第一次使用

1. 從 GitHub 的 **Code → Download ZIP** 下載並完整解壓縮，或使用 Git clone。不要直接在 ZIP 中啟動。
2. 雙擊 **`Setup.bat`**。它會尋找 Python 3.11 64-bit；沒有 Python 時，透過 Windows 的 WinGet 安裝，再建立 `myenv`、安裝依賴與驗證環境。需要網路。
3. 連接並解鎖 iPhone，信任這台電腦，確認開發者模式已開啟。
4. 雙擊 **`Start.bat`**，接受 Windows 管理員授權。選擇模式並啟動；在開啟的地圖／搜尋視窗按開始。

不用自行開兩個終端機，也不用手動啟用虛擬環境。管理員授權仍由 Windows 顯示。

支援目標為 **Windows 10/11 x64 + Python 3.11**。本專案的啟動、安裝與停止流程使用 Windows 工具，尚未支援 macOS/Linux。裝置連線需有可用的 Apple USB 驅動程式；若電腦無法辨識 iPhone，請先安裝／修復 Apple Devices 或 iTunes 並完成信任配對。pymobiledevice3 的裝置限制與驅動說明以[官方文件](https://github.com/doronz88/pymobiledevice3)為準。

若沒有 WinGet，安裝 [Python 3.11.9 Windows 64-bit](https://www.python.org/downloads/release/python-3119/)（保留 Tcl/Tk 選項），再執行 `Setup.bat`。WinGet 安裝參數見 [Microsoft 文件](https://learn.microsoft.com/en-us/windows/package-manager/winget/install)。安裝程式只建立本專案環境，不會自動刪除既有環境。

## 座標與圖片

首次安裝會建立 `data/waypoints/waypoints.pikscan` 示範座標（台北附近三點）。搜尋介面以此資料夾的下拉選單選檔；「匯入…」可將舊版每行 `緯度,經度` 的 TXT 複製轉換為新格式，原檔不會被覆寫。

- `data/waypoints/*.pikscan`：搜尋座標。
- `data/routes/*.pikroute`：移動路線的所有標點。
- `data/cache/geoapify/<country>.zip`：國家資料快取。

辨識範本放在 `mushroom_pics/`；程式開啟時讀取 PNG 種類，可在「搜尋種類…」勾選。個人座標、截圖及快取都排除 Git 與公開 ZIP。詳細格式見[資料說明](docs/data.md)。

## 使用說明

- [路徑移動](docs/movement.md)
- [目標搜尋、截圖與結果存檔](docs/scanning.md)
- [資料格式與選用資料集](docs/data.md)

掃描預設保留原本「提前傳送下一點再截圖」的時序，也能選「逐點等待後截圖」。定位和圖片內容仍受手機／遊戲載入速度影響，地圖標記不是手機 GPS 回讀。

## 專案結構

```text
Setup.bat / Start.bat    建立環境／開啟控制台
launcher.py             控制台與子程式管理
fly.py / main.py        移動／搜尋入口
pikmin/                 介面、裝置流程、辨識及座標產生
tests/                  不連接手機的回歸與介面測試
scripts/                安裝與乾淨原始碼打包
docs/                   操作文件
examples/               可匯入的示範文字座標
data/                   本機座標、路線與國家快取（不公開）
mushroom_pics/           實際使用的辨識範本
```

## 開發與驗證

`pymobiledevice3 9.32.0` 的定位／截圖指令使用舊版 `csfield` API，因此固定搭配 `construct-typing 0.7.0`。`0.8.x` 雖然可能通過 `pip check`，載入 developer 指令仍會出現 `DataclassFieldError`。安裝程式現在會實際載入連線、設定定位、清除定位與截圖指令的 `--help`，不會操作手機。

既有環境遇到此錯誤可重新執行 `Setup.bat`，或執行：

```powershell
.\myenv\Scripts\python.exe -m pip install -r requirements.txt -c requirements-lock.txt
.\myenv\Scripts\python.exe -m pikmin.preflight
```

從專案根目錄執行：

```powershell
.\myenv\Scripts\python.exe -m unittest discover -s tests -v
.\myenv\Scripts\python.exe -m tests.check_fly_ui
.\myenv\Scripts\python.exe -m tests.check_scan_ui
.\myenv\Scripts\python.exe -m tests.check_launcher_ui
```

測試使用模擬裝置，不會操作手機。GitHub Actions 也會執行上述測試。`requirements.txt` 列出直接依賴；`requirements-lock.txt` 固定已在全新 Windows x64 / Python 3.11 環境驗證的完整依賴版本，安裝程式與 CI 會一起使用。更新依賴時請在乾淨環境重新解析、驗證並更新鎖定檔。

手動安裝（已安裝 Python 3.11）：

```powershell
py -3.11 -m venv myenv
.\myenv\Scripts\python.exe -m pip install -r requirements.txt -c requirements-lock.txt
.\myenv\Scripts\python.exe -m pikmin.storage
```

### 裝置連線狀態

啟動器、搜尋器及移動器都可在沒有 iOS 裝置時開啟。裝置連接或斷開時彈出提醒；開始搜尋、傳送或移動時才檢查裝置、準備開發者映像及 tunneld，沒有裝置時顯示提示。搜尋中斷線會停止收尾，移動中斷線會暫停；重新接上不會自動恢復操作。

開發者映像首次準備可能需要網路（包括 Apple 簽署服務）；最多等待 90 秒，通道最多等待 30 秒。離線開啟指不需要連接手機；新地圖圖磚及首次下載國家資料仍需要網路。

Setup 只安裝電腦端 Python 依賴，無法代替裝置上的「信任此電腦」、開發者模式及 Apple USB 驅動安裝。新電腦無法偵測裝置時，請確認資料線可傳輸資料、裝置已解鎖，並安裝／修復 Apple Devices 或 iTunes 的驅動。成功的 HTTP 健康查詢不再顯示於執行紀錄；真正的錯誤仍會保留。
