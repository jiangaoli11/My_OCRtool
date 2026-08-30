from pathlib import Path

from PIL import Image, ImageDraw


def make_icon() -> None:
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((8, 8, 248, 248), radius=52, fill="#0f172a")
    draw.rounded_rectangle((19, 19, 237, 237), radius=42, outline="#1e293b", width=4)

    green = "#22c55e"
    white = "#f8fafc"
    # 四角框选标记
    for points in (
        ((57, 97), (57, 61), (93, 61)),
        ((163, 61), (199, 61), (199, 97)),
        ((57, 159), (57, 195), (93, 195)),
        ((163, 195), (199, 195), (199, 159)),
    ):
        draw.line(points, fill=green, width=13, joint="curve")

    # 文本行与扫描线
    draw.rounded_rectangle((82, 98, 174, 109), radius=5, fill=white)
    draw.rounded_rectangle((82, 123, 158, 134), radius=5, fill=white)
    draw.rounded_rectangle((82, 148, 181, 159), radius=5, fill=white)
    draw.rounded_rectangle((42, 116, 214, 124), radius=4, fill="#4ade80")

    output = Path(__file__).resolve().parents[1] / "assets" / "app.ico"
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Icon written to {output}")


if __name__ == "__main__":
    make_icon()
