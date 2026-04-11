import os
import random
import shutil
import textwrap
import subprocess
import json
import traceback
import time

import imageio_ffmpeg
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# =========================
# CONFIG
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_DIR = os.path.join(BASE_DIR, "images")
USED_DIR = os.path.join(BASE_DIR, "images_used")
BGM_DIR = os.path.join(BASE_DIR, "bgm")
FONT_PATH = os.path.join(BASE_DIR, "fonts", "font.ttf")
OUTPUT_FILE = os.path.join(BASE_DIR, "output", "reel.mp4")

os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(USED_DIR, exist_ok=True)
os.makedirs(BGM_DIR, exist_ok=True)
os.makedirs(os.path.dirname(FONT_PATH), exist_ok=True)
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

# =========================
# 1. AI QUOTE
# =========================
def get_ai_quote(image_path):
    print(f"👁️ Vision AI: {image_path}")

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-2.5-flash")

    file = genai.upload_file(image_path)

    prompt = """
Generate JSON:
{
"quote": "2-line Hindi quote",
"title": "viral title with emojis",
"description": "caption + hashtags"
}
"""

    res = model.generate_content([file, prompt])
    raw = res.text.strip()

    raw = raw.replace("```json", "").replace("```", "")
    data = json.loads(raw)

    return data

# =========================
# 2. VIDEO
# =========================
def render_video(image_path, quote):
    print("🎬 Rendering...")

    bgm = random.choice(os.listdir(BGM_DIR))
    bgm_path = os.path.join(BGM_DIR, bgm)

    img = Image.open(image_path).resize((1080, 1920))
    img.save("bg.png")

    overlay = Image.new("RGBA", (1080, 1920))
    draw = ImageDraw.Draw(overlay)

    font = ImageFont.truetype(FONT_PATH, 60)
    lines = textwrap.wrap(quote, width=25)

    y = 1500
    for line in lines:
        draw.text((100, y), line, font=font, fill="white")
        y += 70

    overlay.save("overlay.png")

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    subprocess.run([
        ffmpeg, "-y",
        "-loop", "1", "-i", "bg.png",
        "-i", "overlay.png",
        "-i", bgm_path,
        "-filter_complex", "[0][1]overlay",
        "-t", "58",
        "-pix_fmt", "yuv420p",
        OUTPUT_FILE
    ])

    return OUTPUT_FILE

# =========================
# 3. YOUTUBE
# =========================
def upload_to_youtube(video, title, desc):
    creds = Credentials(
        None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )

    youtube = build("youtube", "v3", credentials=creds)

    req = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": desc},
            "status": {"privacyStatus": "public"}
        },
        media_body=MediaFileUpload(video)
    )

    req.execute()
    print("✅ YouTube Uploaded")

# =========================
# 4. INSTAGRAM
# =========================
def upload_instagram(video, caption):
    from instagrapi import Client

    print("📸 Instagram Upload...")

    cl = Client()
    cl.load_settings("session.json")
    cl.login("vira_lhubbb", "Uday@9799084603")

    time.sleep(random.randint(20, 60))

    cl.clip_upload(video, caption=caption)

    print("✅ Instagram Uploaded")

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    images = os.listdir(IMAGE_DIR)
    img = random.choice(images)

    path = os.path.join(IMAGE_DIR, img)

    ai = get_ai_quote(path)

    video = render_video(path, ai["quote"])

    upload_to_youtube(video, ai["title"], ai["description"])
    upload_instagram(video, ai["description"])

    shutil.move(path, os.path.join(USED_DIR, img))

    print("🔥 ALL DONE")
