# Pikmin Mushroom 控制台

Windows 桌面工具，透過 pymobiledevice3 操作 iPhone／iPad 模擬定位，提供路徑移動、目標搜尋與座標產生。

## 安裝與更新

支援 **Windows 10/11 x64、Python 3.11**。

1. 下載 GitHub 原始碼 ZIP 並完整解壓縮，或使用 Git clone。
2. 雙擊 **Setup.bat** 安裝或更新環境，需要網路。它會尋找 Python 3.11 64 位元；沒有時透過 WinGet 安裝，接著建立或重用 `myenv`，安裝依賴並驗證指令。
3. 連接並解鎖 iPhone／iPad，信任電腦並開啟開發者模式。電腦需安裝 Apple Devices 或 iTunes 提供的 USB 驅動。
4. 雙擊 **Start.bat**，接受 Windows 管理員授權。選擇模式並啟動，再於地圖／搜尋視窗按開始。

更新前先關閉舊的控制台、搜尋、移動視窗及 tunneld；更新後重新啟動。Setup 不會刪除座標、結果或設定，也不會操作手機定位。不需要手動啟用 Python 環境或自行啟動 tunneld。

沒有 WinGet 時，可安裝 [Python 3.11.9 Windows 64-bit](https://www.python.org/downloads/release/python-3119/)（保留 Tcl/Tk），再執行 Setup。裝置與驅動要求參考 [pymobiledevice3 官方說明](https://github.com/doronz88/pymobiledevice3)。目前不支援 macOS／Linux。

## 功能與操作說明

- **路徑移動**：地圖標點、速度與間隔、循環、暫停、匯入／匯出路線。[操作說明](docs/movement.md)
- **目標搜尋**：依座標清單定位、截圖辨識、預覽命中圖片、書籤、歷史結果及停止後續掃。[操作說明](docs/scanning.md)
- **座標產生**：選擇國家與聚落種類，下載 Geoapify 資料並快取，之後可離線生成座標。[資料說明](docs/data.md)

三個視窗可在未連接裝置時開啟；開始搜尋、傳送或移動時才準備裝置連線。地圖圖磚、首次下載國家資料與未掛載的開發者映像仍可能需要網路。

搜尋預設先傳送下一點再截圖，也可改成逐點等待後截圖。定位與圖片內容受裝置及遊戲載入時間影響，地圖標記不是手機 GPS 回讀。

## 資料放在哪裡

| 路徑 | 內容 |
| --- | --- |
| `data/waypoints/*.pikscan` | 搜尋座標；安裝時僅在空座標庫建立台北附近三點示範 |
| `data/routes/*.pikroute` | 移動路線 |
| `data/cache/` | 國家資料與地圖快取 |
| `mushroom_pics/` | 搜尋辨識用的透明 PNG 範本 |
| `found_targets/` | 命中截圖，`.trash/` 為專案回收區 |
| `scan_sessions/` | 搜尋設定、結果及最後截圖 |
| `launcher_settings.json`、`target_bookmarks.json` | 本機設定與書籤 |

搜尋器的「匯入…」可將每行 `緯度,經度` 的舊 TXT 複製轉換為新格式，原檔保留。新加入辨識範本後，重新開啟搜尋器更新種類清單。個人資料與快取不納入 Git 或發布 ZIP。

## 連線問題

- **找不到裝置**：確認已解鎖、信任電腦，資料線可傳輸資料，Apple USB 驅動可辨識裝置。
- **停在準備連線**：介面會顯示映像檢查、準備或等待通道等步驟；查看「執行紀錄」取得錯誤。已掛載的開發者映像會略過下載；未掛載時準備最多等待 90 秒，通道最多等待 30 秒。
- **iOS／iPadOS 27.2 截圖或服務拒絕連線**：本專案固定使用含相容性修正的 pymobiledevice3 11.15.5。執行 Setup 更新後，須重新啟動舊程式與 tunneld。
- **斷線後**：搜尋會停止收尾，移動會暫停；重新接上不會自行恢復。

Setup 只處理電腦端環境，無法代替裝置上的信任與開發者模式設定。

## 專案維護

程式在 `pikmin/`，三個入口是 `launcher.py`、`main.py`、`fly.py`；安裝、啟動與打包腳本集中於 `scripts/`。`tests/` 保留離線回歸、介面檢查及選用效能測試。

測試指令、依賴更新、實機驗收、Git 規則、打包及可清理檔案，統一見 [開發與維護說明](docs/development.md)。
