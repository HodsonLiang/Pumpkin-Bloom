# 資料格式與本機資料

## 搜尋座標及移動路線

- `data/waypoints/*.pikscan`：搜尋器與啟動器下拉選單列出的座標。
- `data/routes/*.pikroute`：移動器「路線 → 匯出路線」保存的所有標點，包含已走過的點；載入會替換路線並暫停，維持目前位置。
- 檔案為 UTF-8 JSON：`format` 分別是 `pikmin.scan` / `pikmin.route`，`version` 為 `1`，`points` 為依序排列的 `[緯度, 經度]` 陣列。使用對應副檔名，不要只修改檔名轉換格式。
- 「匯入…」支援舊 TXT：每行 `緯度,經度`，複製轉成 `.pikscan`，不改動原檔；重複匯入相同檔名與內容不產生副本。
- 初次安裝只有在座標庫為空時，才將 `examples/waypoints.txt` 轉為示範檔。

## Geoapify

在啟動器「產生座標」按「勾選國家…」，以中文、英文名稱或代碼搜尋並勾選國家／地區，再勾選 Cities、Towns、Villages、Hamlets 中的一種或多種。程式下載 `https://www.geoapify.com/data-share/localities/<country_code>.zip`，原始 ZIP 放在 `data/cache/geoapify`，之後直接讀本地快取。選取的類型没有地點或國家不存在時，顯示錯誤，不覆蓋既有輸出。

採用原始地點座標，無舊版印度經度 +0.001 偏移；去除重複座標後，依點數上限隨機抽樣並打亂順序。ZIP 逐行讀取，不需要解壓到專案目錄。要更新國家資料，可關閉生成器後刪除該國 ZIP，再重新產生。

資料來源：[Geoapify OSM Locality Extracts](https://www.geoapify.com/data-share/localities/readme.html)。© OpenStreetMap contributors，依 ODbL 提供；輸出檔保留來源與署名。公開再散布資料時請遵循來源授權。

## 辨識範本

`mushroom_pics/` 的透明 PNG 會在搜尋器啟動時列成可選種類及圖示。透明通道作為辨識遮罩，图片應與手機截圖中的目標大小相符。新加／移除範本後，重新開啟搜尋器更新種類選單。

## 其他本機資料

- `found_targets/`：命中截圖；`.trash/` 為可還原的刪除區。
- `scan_sessions/`：搜尋設定、逐張辨識結果、最後截圖及辨識失敗圖片。
- `target_bookmarks.json`：依截圖檔名記錄的星號書籤。
- `launcher_settings.json`：啟動器設定。
- `data/runtime/`：啟動器通知子視窗正常關閉的暫存信號。
- `local_archive/legacy-data-20261008/`：本次整理保留的舊城市 CSV、印度資料及原始 TXT；有內容的 TXT 已另外轉入座標庫。

本機資料排除 Git，原始碼打包使用白名單，不包含快取、封存資料或個人座標與圖片。原本的 `worldcities.csv` 及 `india_villages` 不再參與生成流程。

## 國家名稱清單

國家選擇提供中文及英文全名，搜尋篩選不會清除其他已勾選項目。「勾選搜尋結果／取消搜尋結果」只影響目前篩選出的國家；按「套用」才保存。內部仍使用兩碼代碼相容舊設定。

清單依 2026-10-31 Geoapify 官方下載目錄的 217 個國家／地區建立；中文名稱參考使用者提供的《OBU月季報4種代碼表》，補上現行名稱。PDF 中過時的國家代碼、銀行及統計代碼不作為下載選項。英文名稱及補充譯名使用 Unicode CLDR（透過 Intl.DisplayNames）；來源與授權連結記於 `pikmin/countries.py`。

## 地圖圖磚

地圖使用標準 HTTPS OSM 圖磚位址及固定的 Pumpkin-Bloom 應用識別，只載入可見視窗需要的圖磚，不再預抓畫面外區域。瀏覽快取位於 `data/cache/maps/osm.sqlite3`，至少保留七天，過期以條件請求更新；不是地圖離線下載功能。

403／429 會停止網路請求、顯示錯誤提示，而不把伺服器的錯誤 PNG 當作地圖。可稍後按「重試地圖」；持續被封鎖時不會自動改換身分或服務規避限制。地圖下方顯示 OpenStreetMap 署名。

參考：[OpenStreetMap 圖磚使用政策](https://operations.osmfoundation.org/policies/tiles/)。
