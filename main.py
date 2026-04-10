# 🔥 FINAL 10/10 KRISHNA REEL AUTOMATION (PRODUCTION READY)

import os
import random
import shutil
import subprocess
import json
import traceback
import pickle
from datetime import datetime

import imageio_ffmpeg
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont, ImageOps
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_DIR = os.path.join(BASE_DIR, "images")
USED_DIR = os.path.join(BASE_DIR, "images_used")
BGM_DIR = os.path.join(BASE_DIR, "bgm")
FONT_PATH = os.path.join(BASE_DIR, "fonts", "NotoSansDevanagari-Regular.ttf")
OUTPUT_FILE = os.path.join(BASE_DIR, "short.mp4")
HISTORY_FILE = os.path.join(BASE_DIR, "history.txt")
TOKEN_FILE = os.path.join(BASE_DIR, "token.pickle")

for folder in [IMAGE_DIR, USED_DIR, BGM_DIR, os.path.dirname(FONT_PATH)]:
    os.makedirs(folder, exist_ok=True)

# =========================
# AI QUOTE GENERATION (RETRY + SAFE JSON)
# =========================
def get_ai_quote(image_path, retries=3):
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-2.0-flash")

    uploaded = genai.upload_file(image_path)

    prompt = """
Return ONLY valid JSON:
{
 "quote": "2 line Hindi quote (max 12 words)",
 "title": "viral short title",
 "description": "caption + hashtags"
}
"""

    for attempt in range(retries):
        try:
            response = model.generate_content([uploaded, prompt])
            text = response.text.strip()

            start = text.find("{")
            end = text.rfind("}") + 1
            data = json.loads(text[start:end])

            if len(data.get("quote", "")) < 10:
                raise ValueError("Weak quote")

            return data

        except Exception as e:
            print(f"Retry {attempt+1} failed:", e)

    genai.delete_file(uploaded.name)
    raise RuntimeError("AI failed after retries")

# =========================
# SMART TEXT WRAP
# =========================
def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = current + " " + word if current else word
        w = draw.textbbox((0,0), test, font=font)[2]
        if w <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines

# =========================
# VIDEO RENDER (PREMIUM LOOK)
# =========================
def render_video(image_path, quote):
    bgm = os.path.join(BGM_DIR, random.choice(os.listdir(BGM_DIR)))

    W, H = 1080, 1920

    with Image.open(image_path) as img:
        img = ImageOps.fit(img, (W, H), Image.Resampling.LANCZOS)
        img.save("bg.png")

    overlay = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(overlay)

    font = ImageFont.truetype(FONT_PATH, 64)
    lines = wrap_text(draw, quote, font, 850)

    # dynamic box
    padding = 40
    line_h = 70
    text_h = len(lines) * line_h

    max_w = max([draw.textbbox((0,0), l, font=font)[2] for l in lines])

    box_w = max_w + padding*2
    box_h = text_h + padding*2

    x1 = (W - box_w)//2
    y1 = H - box_h - 200

    draw.rounded_rectangle((x1,y1,x1+box_w,y1+box_h), radius=40, fill=(0,0,0,160))

    y = y1 + padding
    for line in lines:
        w = draw.textbbox((0,0), line, font=font)[2]
        x = (W - w)//2
        draw.text((x,y), line, font=font, fill="white")
        y += line_h

    overlay.save("overlay.png")

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg, "-y",
        "-loop", "1", "-i", "bg.png",
        "-i", "overlay.png",
        "-stream_loop", "-1", "-i", bgm,
        "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
        "-map", "[v]", "-map", "2:a",
        "-t", "30",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        OUTPUT_FILE
    ]

    result = subprocess.run(cmd, capture_output=True)

    if result.returncode != 0:
        print(result.stderr.decode())
        raise RuntimeError("FFmpeg failed")

    # cleanup temp
    for f in ["bg.png", "overlay.png"]:
        if os.path.exists(f): os.remove(f)

    return OUTPUT_FILE

# =========================
# YOUTUBE UPLOAD (RETRY)
# =========================
def upload(video, title, desc):
    with open(TOKEN_FILE, 'rb') as token:
        creds = pickle.load(token)

    yt = build("youtube", "v3", credentials=creds)

    for i in range(3):
        try:
            req = yt.videos().insert(
                part="snippet,status",
                body={
                    "snippet": {"title": title, "description": desc},
                    "status": {"privacyStatus": "public"}
                },
                media_body=MediaFileUpload(video)
            )

            res = req.execute()
            print("Uploaded:", res["id"])
            return
        except Exception as e:
            print("Upload retry", i+1, e)

    raise RuntimeError("Upload failed after retries")

# =========================
# HISTORY
# =========================
def load_history():
    if os.path.exists(HISTORY_FILE):
        return set(open(HISTORY_FILE).read().splitlines())
    return set()

def update_history(img):
    with open(HISTORY_FILE, "a") as f:
        f.write(img + "\n")

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    imgs = [f for f in os.listdir(IMAGE_DIR) if f.endswith((".jpg",".png"))]
    used = load_history()

    imgs = [i for i in imgs if i not in used]
    if not imgs:
        raise RuntimeError("No fresh images")

    img = random.choice(imgs)
    path = os.path.join(IMAGE_DIR, img)

    print("Processing:", img)

    ai = get_ai_quote(path)
    video = render_video(path, ai["quote"])
    upload(video, ai["title"], ai["description"])

    update_history(img)
    new_name = datetime.now().strftime("%Y%m%d_%H%M%S_") + img
    shutil.move(path, os.path.join(USED_DIR, new_name))

    print("✅ DONE - FULL AUTO PIPELINE")
