# Python 相容性驗證

驗證日期：2026-09-15。平台：Windows x64。使用現有 `requirements.txt` 與 `requirements-lock.txt`，未更改套件版本。

| 版本 | 結果 |
| --- | --- |
| Python 3.11（現有 myenv） | 40 項測試通過；既有支援版本。 |
| Python 3.12.11 | 獨立環境安裝成功，pip check 通過，40 項測試與兩個離線 UI 檢查通過。 |
| Python 3.13.14（Microsoft Store 版） | 可建立虛擬環境並載入 Tkinter，但完整依賴安裝失敗，未進行完整執行測試。 |

3.13 安裝失敗原因為 `lzfse==0.4.2`：pip 選用原始碼套件並嘗試編譯，要求 Microsoft Visual C++ 14.0 以上的 Build Tools。目前測試機未具備所需編譯工具。相同套件有 Python 3.12 的 Windows x64 wheel，已下載並成功安裝。此結果表示目前安裝流程不能直接支援一般使用者的 3.13 環境，不代表安裝編譯工具後仍必然無法執行。

3.12 驗證命令：

```powershell
python -m pip install -r requirements.txt -c requirements-lock.txt
python -m pip check
python -m unittest discover -s tests -q
python -m tests.check_scan_ui
python -m tests.check_fly_ui
```

測試包括定位、還原定位、截圖與 tunneld 指令的 `--help` 載入檢查，以及模擬裝置的掃描與移動流程；沒有對手機執行定位或截圖，因此不代表完成 3.12 實機驗證。

測試環境位於已被 Git 忽略的 `.build/compat312`、`.build/compat313`，安裝紀錄為 `.build/compat312-install.log` 與 `.build/compat313-install.log`。現有 `myenv` 未變更。

目前 `Setup.bat` 呼叫的安裝腳本仍只接受 3.11；本次為相容性驗證，尚未放寬安裝腳本版本選擇。可以依這次結果將 3.12 納入後續安裝與 CI 支援。
