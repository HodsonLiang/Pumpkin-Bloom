import csv
import random
import math

# ================= 全域設定 =================
USE_OFFSET = False  # 開關：是否使用常態分佈機率偏移座標
TARGET_COUNTRIES = [ "Norway" , "France" ,  "Germany" , "Argentina", "Chile" ,"Peru" , "Colombia" , "Brazil"]  # 支援多個國家
MAX_POINTS = 10000  # 最大產生座標數
# ============================================

def estimate_sigma_km(population):
    """根據人口數量估計常態分佈的標準差（公里）"""
    try:
        pop = float(population)
    except (ValueError, TypeError):
        pop = 50000  # 若無人口資料，預設為 5 萬
    
    # 設定人口下限，避免偏移量趨近於零
    pop = max(pop, 10000)
    
    # 假設 100 萬人口城市的標準差為 15 公里
    return 0.015 * math.sqrt(pop)

def get_offset_coords(lat, lon, population):
    """套用常態分佈產生偏移後的座標"""
    sigma_km = estimate_sigma_km(population)
    
    # 緯度 1 度約為 111 公里
    sigma_lat = sigma_km / 111.0
    
    # 經度 1 度約為 111 * cos(緯度) 公里
    sigma_lon = sigma_km / (111.0 * math.cos(math.radians(lat)))
    
    # 使用常態分佈產生新座標 (mu, sigma)
    new_lat = random.gauss(lat, sigma_lat)
    new_lon = random.gauss(lon, sigma_lon)
    
    return new_lat, new_lon

def main():
    csv_filename = "worldcities.csv" 
    output_filename = globals().get('OUTPUT_FILENAME', 'waypoints.txt')
    
    city_data = []
    
    try:
        with open(csv_filename, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 檢查國家是否在全域設定的清單內
                if row.get('country') in TARGET_COUNTRIES:
                    lat = float(row['lat'])
                    lon = float(row['lng'])
                    population = row.get('population', 0)
                    city_data.append((lat, lon, population))
    except FileNotFoundError:
        print(f"找不到 {csv_filename} 檔案，請確認。")
        return

    if len(city_data) > MAX_POINTS:
        selected_cities = random.sample(city_data, MAX_POINTS)
    else:
        selected_cities = city_data

    random.shuffle(selected_cities)
    
    with open(output_filename, 'w', encoding='utf-8') as f:
        for lat, lon, pop in selected_cities:
            
            if USE_OFFSET:
                new_lat, new_lon = get_offset_coords(lat, lon, pop)
                print(f"原始: {lat:.4f}, {lon:.4f} (人口: {pop}) -> 偏移後: {new_lat:.6f}, {new_lon:.6f}")
            else:
                new_lat, new_lon = lat, lon
                print(f"原始: {lat:.4f}, {lon:.4f} (未開啟偏移) -> 寫入: {new_lat:.6f}, {new_lon:.6f}")
            
            # 保留小數點後 6 位以符合 GPS 精度要求
            f.write(f"{new_lat:.6f},{new_lon:.6f}\n")
            
    print(f"\n執行完畢，已將 {len(selected_cities)} 個城市座標存入 {output_filename}。")

if __name__ == "__main__":
    main()
