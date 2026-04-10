import os
import random
import shutil
import textwrap
import subprocess
import json
import traceback

import imageio_ffmpeg
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# =========================
# CONFIG & FOLDERS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_DIR = os.path.join(BASE_DIR, "images")
USED_DIR = os.path.join(BASE_DIR, "images_used")
BGM_DIR = os.path.join(BASE_DIR, "bgm")
FONT_PATH = os.path.join(BASE_DIR, "fonts", "font.ttf")
OUTPUT_FILE = os.path.join(BASE_DIR, "short.mp4")

# Ensure folders exist
for folder in [IMAGE_DIR, USED_DIR, BGM_DIR, os.path.dirname(FONT_PATH)]:
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)


# =========================
# 1. VISION AI
# =========================
def get_ai_quote(image_path):
    print(f"👁️ Vision AI Analyzing: {image_path}...")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("❌ GEMINI_API_KEY is missing!")

    genai.configure(api_key=api_key)

    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]

    for model_name in models_to_try:
        try:
            print(f"🤖 Trying model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            myfile = genai.upload_file(image_path)

            prompt = """
You are a Bhakti poet and devotee of Lord Krishna. Look at this image.
Generate a valid JSON object with exactly these 3 fields:
- "quote": A 2-line Hindi Shayari/Quote. Rhyming, deep, natural. Max 10-12 words. NO EMOJIS.
- "title": A viral, catchy YouTube Short title (Hindi + English mix) with cute emojis.
- "description": A beautiful, heart-touching caption with emojis + 5-6 relevant hashtags.
Output strictly valid JSON only. No markdown.
"""

            result = model.generate_content([myfile, prompt])
            raw = result.text.strip()

            # Remove possible ```json fences
            if raw.startswith("```"):
                raw = raw.replace("```json", "").replace("```", "")

            # Extract JSON between first { and last }
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON object found in model output")

            json_text = raw[start:end]
            data = json.loads(json_text)

            print("✨ AI Generated:")
            print("Quote:", data.get("quote"))
            print("Title:", data.get("title"))

            return data

        except Exception as e:
            print(f"⚠️ Model {model_name} failed: {e}")
            continue

    raise RuntimeError("❌ All Gemini models failed in get_ai_quote")


# =========================
# 2. VIDEO ENGINE (BABY-KRISHNA STYLE BOTTOM TEXT)
# =========================
def render_video(image_path, quote):
    print("🎬 Rendering Video...")

    try:
        # --- 1. Pick BGM ---
        bgm_files = [f for f in os.listdir(BGM_DIR) if f.lower().endswith(".mp3")]
        if not bgm_files:
            print("❌ No BGM found in bgm/ folder!")
            return None

        bgm_path = os.path.join(BGM_DIR, random.choice(bgm_files))
        print(f"🎵 Selected Music: {os.path.basename(bgm_path)}")

        # --- 2. Prepare 1080x1920 Background ---
        base_width = 1080
        base_height = 1920

        with Image.open(image_path) as img:
            img_ratio = img.width / img.height
            target_ratio = base_width / base_height

            if img_ratio > target_ratio:
                new_height = base_height
                new_width = int(new_height * img_ratio)
            else:
                new_width = base_width
                new_height = int(new_width / img_ratio)

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            left = (new_width - base_width) / 2
            top = (new_height - base_height) / 2
            right = left + base_width
            bottom = top + base_height

            img = img.crop((left, top, right, bottom))
            img.save("temp_bg.png")

        # --- 3. Minimal Bottom Text Style ---
        overlay = Image.new("RGBA", (base_width, base_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Smaller, softer font
        font_size = 64
        try:
            font = ImageFont.truetype(FONT_PATH, font_size)
        except Exception:
            font = ImageFont.load_default()

        # Compact text: we expect 1–2 short lines
        wrapper = textwrap.TextWrapper(width=25)
        lines = wrapper.wrap(quote.strip())

        if not lines:
            print("⚠️ Empty quote for overlay")
            return None

        # Measure text block
        line_height = font_size + 8
        text_height = len(lines) * line_height
        max_text_width = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            if w > max_text_width:
                max_text_width = w

        # Bottom rounded bar (like your baby Krishna short)
        padding_x = 60
        padding_y = 25
        box_width = max_text_width + 2 * padding_x
        box_height = text_height + 2 * padding_y

        box_x1 = (base_width - box_width) / 2
        # Lift a bit above absolute bottom so YT UI doesn’t cover it
        box_y1 = base_height - box_height - 220
        box_x2 = box_x1 + box_width
        box_y2 = box_y1 + box_height

        # Semi-transparent black rounded rectangle
        draw.rounded_rectangle(
            (box_x1, box_y1, box_x2, box_y2),
            radius=40,
            fill=(0, 0, 0, 170),  # 170/255 opacity
        )

        # Centered white text inside the bar
        current_y = box_y1 + padding_y
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            text_x = box_x1 + (box_width - text_w) / 2

            draw.text(
                (text_x, current_y),
                line,
                font=font,
                fill="white",
            )
            current_y += line_height

        overlay.save("temp_overlay.png")

        # --- 4. Encode Final Video with FFmpeg ---
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        command = [
            ffmpeg_exe,
            "-y",
            "-loop",
            "1",
            "-i",
            "temp_bg.png",
            "-i",
            "temp_overlay.png",
            "-i",
            bgm_path,
            "-filter_complex",
            "[0:v][1:v]overlay=0:0[v]",
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-t",
            "58",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            OUTPUT_FILE,
        ]

        subprocess.run(command, capture_output=True, check=True)
        print("✅ Video Rendered Successfully!")
        return OUTPUT_FILE

    except Exception as e:
        print("❌ RENDER ERROR:", e)
        return None

    finally:
        for f in ["temp_bg.png", "temp_overlay.png"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass


# =========================
# 3. YOUTUBE UPLOAD
# =========================
def upload_to_youtube(video_file, title, description):
    print("🚀 Uploading to YouTube...")

    required_env = [
        "YOUTUBE_REFRESH_TOKEN",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
    ]
    for key in required_env:
        if not os.environ.get(key):
            print(f"❌ Missing env var: {key}")
            return False

    try:
        creds = Credentials(
            token=None,
            refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["YOUTUBE_CLIENT_ID"],
            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
            scopes=["https://www.googleapis.com/auth/youtube.upload"],
        )

        youtube = build("youtube", "v3", credentials=creds)

        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": ["Krishna", "Bhakti", "Motivation", "Hinduism", "RadhaKrishna", "Shorts"],
                    "categoryId": "22",
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                },
            },
            media_body=MediaFileUpload(video_file),
        )

        response = request.execute()
        print(f"✅ Upload Success! Video ID: {response['id']}")
        return True

    except Exception:
        print("❌ Upload Failed:")
        traceback.print_exc()
        return False


# =========================
# 4. MAIN EXECUTION
# =========================
if __name__ == "__main__":
    images = [f for f in os.listdir(IMAGE_DIR) if f.lower().endswith((".jpg", ".png"))]

    if not images:
        print("❌ No images in images/ folder.")
        exit(1)

    target_image = random.choice(images)
    full_path = os.path.join(IMAGE_DIR, target_image)

    print(f"🖼️ Processing: {target_image}")

    ai_content = get_ai_quote(full_path)

    quote_text = ai_content.get("quote", "")
    title_text = ai_content.get("title", "Krishna Shorts 🦚")
    desc_text = ai_content.get("description", "Jai Shree Krishna #Krishna")

    if not quote_text:
        print("❌ Empty quote from AI")
        exit(1)

    video = render_video(full_path, quote_text)

    if video:
        success = upload_to_youtube(video, title_text, desc_text)
        if success:
            shutil.move(full_path, os.path.join(USED_DIR, target_image))
            print("📦 Image moved to images_used/")
        else:
            print("⚠️ Upload failed. Image NOT moved.")
    else:
        print("❌ Video render failed.")
