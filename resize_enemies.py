from PIL import Image
import os

INPUT_DIR = "画像/敵一時保存"
OUTPUT_DIR = "static/enemies"

os.makedirs(OUTPUT_DIR, exist_ok=True)

def resize_to_128_centered(input_path, output_path):
    img = Image.open(input_path).convert("RGBA")

    # 比率維持で最大128に縮小
    img.thumbnail((128, 128), Image.NEAREST)

    # 透明キャンバス作成
    canvas = Image.new("RGBA", (128, 128), (0, 0, 0, 0))

    # 中央配置
    x = (128 - img.width) // 2
    y = (128 - img.height) // 2
    canvas.paste(img, (x, y), img)

    canvas.save(output_path, optimize=True)

for filename in os.listdir(INPUT_DIR):
    if filename.endswith(".png"):
        resize_to_128_centered(
            os.path.join(INPUT_DIR, filename),
            os.path.join(OUTPUT_DIR, filename)
        )

print("完了")
