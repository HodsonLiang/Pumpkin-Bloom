# 選用資料與輸出

## 座標檔

UTF-8 文字檔，每行 `緯度,經度`。根目錄 `waypoints.txt`、`waypoints_new.txt` 等個人座標已排除 Git。公開示範位於 `examples/waypoints.txt`。

## 世界城市（選用）

在根目錄放置 `worldcities.csv`，標頭至少包含 `country,lat,lng,population`。`country` 必須符合控制台輸入的英文國名；`population` 可留空。不隨專案打包，請自行取得可使用的資料。

```csv
country,lat,lng,population
Taiwan,25.033964,121.564468,100000
```

以上只是格式示例，不是人口統計資料。

## 印度村莊（選用）

放置於根目錄的 `india_villages/place-village.ndjson`。每行一個 JSON，至少包含 `location`，順序為 `[經度, 緯度]`：

```json
{"location": [77.209, 28.6139]}
```

生成器沿用原設定，輸出經度增加 `0.001`。其餘城市、鄉鎮及 hamlet 資料不會被此生成器讀取。

## 辨識範本

`mushroom_pics/` 內的透明 PNG 會全部參與比對；透明通道作為遮罩。圖片應與手機截圖中的目標大小相符。其他原圖或未啟用範本不用放進此資料夾。

## 本機輸出

- `found_targets/`：找到目標的截圖。
- `scan_sessions/`：每次搜尋設定、逐張辨識結果與最後截圖。
- `temp_screenshots/`：舊版掃描可能留下的截圖。
- `launcher_settings.json`：本機控制台設定。

上述資料都排除 Git，不會隨原始碼 ZIP 分享；安裝時也不會覆蓋你既有的資料。
