import json
import random

# ================= 全域設定 =================
MAX_POINTS = 10000  # 最大產生座標數
# ============================================

def main():
    ndjson_filename = "india_villages/place-village.ndjson"  # 請替換為實際的 ndjson 檔案名稱
    output_filename = globals().get('OUTPUT_FILENAME', 'waypoints.txt')
    
    city_data = []
    
    try:
        with open(ndjson_filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    
                    location = data.get("location")
                    
                    # 確保資料格式正確且國家符合條件
                    if location and len(location) >= 2:
                        # 根據範例，location 陣列為 [經度, 緯度]
                        lon = float(location[0])
                        lat = float(location[1])
                        city_data.append((lat, lon))
                except json.JSONDecodeError:
                    continue
                    
    except FileNotFoundError:
        print(f"找不到 {ndjson_filename} 檔案，請確認。")
        return

    # 若總數超過最大限制則隨機抽樣
    if len(city_data) > MAX_POINTS:
        selected_cities = random.sample(city_data, MAX_POINTS)
    else:
        selected_cities = city_data

    random.shuffle(selected_cities)
    
    # 寫入結果
    with open(output_filename, 'w', encoding='utf-8') as f:
        for lat, lon in selected_cities:
            # 保留小數點後 6 位以符合 GPS 精度要求
            f.write(f"{lat:.6f},{ lon + 0.001:.6f}\n")
            
    print(f"執行完畢，已將 {len(selected_cities)} 個城市座標存入 {output_filename}。")

if __name__ == "__main__":
    main()
