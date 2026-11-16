# 開發、測試與打包

## 支援環境與依賴

目前支援 Windows 10/11 x64、Python 3.11。`myenv/` 是本機執行環境，不納入 Git 或發布包。其他 Python 版本尚未以目前依賴重新驗證。

`requirements.txt` 固定直接依賴，`requirements-lock.txt` 固定完整相依版本。pymobiledevice3 11.15.5 包含 iOS／iPadOS 27.2 的 RSD 主機識別碼修正，搭配 construct-typing 0.8.1。不要單獨降回舊版套件。

第一次安裝或更新均使用根目錄的 `Setup.bat`；更新前請先結束控制台、搜尋、移動視窗及舊 tunneld。Setup 重用既有環境，不刪除座標或結果，也不會操作手機定位。

## 離線驗證

從專案根目錄執行：

```powershell
.\myenv\Scripts\python.exe -m pip check
.\myenv\Scripts\python.exe -m unittest discover -s tests -v
.\myenv\Scripts\python.exe -m tests.check_fly_ui
.\myenv\Scripts\python.exe -m tests.check_scan_ui
.\myenv\Scripts\python.exe -m tests.check_launcher_ui
```

單元測試使用模擬裝置。`test_device_cli` 會實際載入裝置指令的 `--help`，不會連接手機；Setup 也透過 `pikmin.preflight` 執行相同相容性檢查。介面檢查會暫時建立本機視窗，需要有桌面的 Windows 工作階段。GitHub Actions 的 `.github/workflows/tests.yml` 使用同一組檢查。

| 測試模組 | 負責內容 |
| --- | --- |
| `test_device_backend`、`test_device_session`、`test_device_pairing`、`test_device_cli` | 裝置準備、已掛載映像、進度事件、配對與指令相容性 |
| `test_launcher` | 子視窗啟動、取消及收尾 |
| `test_fly`、`test_scan`、`test_scan_state` | 移動、搜尋、續搜、手動定位與換裝置狀態 |
| `test_library`、`test_target_history` | 資料格式、座標產生及歷史結果 |
| `test_map_tiles`、`test_vision` | 地圖快取與圖片辨識 |
| `check_*_ui` | 三個視窗的離線操作與版面 |

`python -m tests.benchmark_vision` 是選用的合成圖片效能比較，不屬於日常回歸測試，也不能代表實機辨識準確率。

## 實機驗收

離線測試不能證明實際裝置定位成功。更新裝置依賴後，應在解鎖且信任電腦的裝置上，檢查連線準備、單獨傳送、少量點數搜尋、截圖、停止／還原定位與斷線提示。

2026-11-08 已在 iPad15,3／iPadOS 27.2 驗證單獨截圖、連續三次截圖，以及保持 DVT 連線時截圖。兩個截圖程序同時啟動仍曾有一次失敗；完整搜尋另由使用者回報恢復可用，尚未完成所有實機驗收項目。

已掛載的開發者映像會跳過自動下載／掛載；未掛載時準備最多等待 90 秒，通道最多等待 30 秒。HTTP 通道清單可用不代表裝置內的服務必定可連線。

## 更新依賴

在 `.build/` 下建立乾淨 Python 3.11 環境，以更新後的 `requirements.txt` 安裝，完成 `pip check`、單元測試與介面檢查，再以該環境的 `pip freeze` 更新鎖定檔。最後更新 `myenv` 並進行實機驗收。不要將試驗環境或裝置截圖提交至 Git。

## 原始碼發布包

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/package.ps1
```

輸出為 `dist/Pikmin-mushroom-source-<時間>.zip`。打包採白名單，只包含程式、安裝入口、文件、測試、示範座標及辨識範本，不包含 `.git`、執行環境、快取或個人資料。

## 本機檔案與 Git

- `.build/`：可重建的測試環境、下載與驗證暫存；完成驗證並關閉相關程序後可刪除。
- `dist/`：可重新打包的原始碼 ZIP。
- `__pycache__/`：Python 自動產生的快取，可刪除。
- `local_archive/`：個人舊資料或診斷封存；先確認內容再刪除。
- `data/`、`found_targets/`、`scan_sessions/`、設定與書籤：使用者資料，不能當作程式暫存整批清除。

上述本機內容由 `.gitignore` 排除。`.gitattributes` 統一 Python／Markdown／YAML 的 LF 與 Windows 啟動腳本的 CRLF。提交前檢查 `git status` 及 `git diff --check`，不要提交個人座標、畫面或環境。
