import cv2
import os
import glob

def check_image_has_target(image_path, templates_folder, threshold=0.15):
    """
    使用 TM_SQDIFF_NORMED 配合去背遮罩。
    數值越小代表越吻合 (0.0 為完美重疊)。
    """
    if not os.path.exists(image_path) or not os.path.exists(templates_folder):
        print("找不到截圖或範本資料夾。")
        return False, None

    # 直接讀取彩色原圖，不轉灰階、不取邊緣
    img = cv2.imread(image_path)
    if img is None:
        return False, None

    # img = cv2.copyMakeBorder(img, 400, 400, 400, 400, cv2.BORDER_CONSTANT, value=[0, 0, 0])

    template_files = glob.glob(os.path.join(templates_folder, "*.png"))
    if not template_files:
        print(f"資料夾 {templates_folder} 內沒有找到 .png 檔案。")
        return False, None

    for t_path in template_files:
        template = cv2.imread(t_path, cv2.IMREAD_UNCHANGED)
        if template is None:
            continue

        # 確認圖片包含透明通道
        if len(template.shape) == 3 and template.shape[2] == 4:
            # 提取透明通道作為遮罩
            alpha_channel = template[:, :, 3]
            _, mask = cv2.threshold(alpha_channel, 1, 255, cv2.THRESH_BINARY)
            
            # 提取 RGB 顏色部分
            template_color = template[:, :, :3]
            
            # 使用平方差標準化演算法 (支援 mask)
            result = cv2.matchTemplate(img, template_color, cv2.TM_SQDIFF_NORMED, mask=mask)
            
            # 取得最小值與最大值
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            # SQDIFF_NORMED 演算法中，min_val 越接近 0 越吻合
            if min_val <= threshold:
                target_name = os.path.basename(t_path)
                print(f"找到目標: {target_name}，差異度: {min_val:.3f}")
                return True, target_name
        else:
            print(f"{os.path.basename(t_path)} 沒有透明通道。")

    return False, None