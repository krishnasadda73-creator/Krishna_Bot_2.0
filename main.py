import os
import random
import shutil
import textwrap
import subprocess
import json
import traceback
import asyncio
import requests
import urllib.parse

import imageio_ffmpeg
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import edge_tts

# =========================
# CONFIG & PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_DIR = os.path.join(BASE_DIR, "images")        # fallback folder
USED_DIR = os.path.join(BASE_DIR, "images_used")
FONT_PATH = os.path.join(BASE_DIR, "fonts", "font.ttf")
OUTPUT_FILE = os.path.join(BASE_DIR, "short.mp4")
VOICE_FILE = os.path.join(BASE_DIR, "voice.mp3")
GEN_IMAGE_FILE = os.path.join(BASE_DIR, "generated.png")

# Ensure folders exist
for folder in [IMAGE_DIR, USED_DIR, os.path.dirname(FONT_PATH)]:
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)


# =========================
# 0. IMAGE GENERATION (POLLINATIONS)
# =========================
def generate_krishna_image(prompt: str, out_path: str) -> bool:
    """
    Uses Pollinations.AI to generate an image based on a text prompt.
    No API key required. 100% free.
    """
    try:
        print("🎨 Generating image from Pollinations...")
        # Example endpoint: https://image.pollinations.ai/prompt/{prompt}
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"

        response = requests.get(url, stream=True, timeout=60)
        if response.status_code != 200:
            print(f"❌ Pollinations error: HTTP {response.status_code}")
            return False

        with open(out_path, "wb") as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)

        print(f"✅ Image saved to {out_path}")
        return True
    except Exception as e:
        print(f"❌ Pollinations request failed: {e}")
        return False


# =========================
# 1. VISION / TEXT – GEMINI
# =========================
def get_ai_quote():
    """
    Uses Gemini to generate quote + title + description for a Krishna Reel.
    Image is NOT passed to Gemini now (since we generate via Pollinations).
    """
    print("🧠 Calling Gemini for quote/title/description...")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("❌ GEMINI_API_KEY is missing!")

    genai.configure(api_key=api_key)

    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]

    base_prompt = """
You are a Bhakti poet and devotee of Lord Krishna.
Generate a valid JSON object with exactly these 3 fields:
- "quote": A 2-line Hindi Shayari/Quote. Rhyming, deep, natural. Max 10-12 words. NO EMOJIS.
- "title": A viral, catchy YouTube Short title (Hindi + English mix) with cute emojis.
- "description": A beautiful, heart-touching caption with emojis + 5-6 relevant hashtags.
Output strictly valid JSON only. No markdown.
"""

    for model_name in models_to_try:
        try:
            print(f"🤖 Trying Gemini model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            result = model.generate_content(base_prompt)

            raw = result.text.strip()

            if raw.startswith("```"):
                raw = raw.replace("```json", "").replace("```", "")

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
            print(f"⚠️ Gemini model {model_name} failed: {e}")
            continue

    raise RuntimeError("❌ All Gemini models failed in get_ai_quote")


# =========================
# 2. VOICE – EDGE TTS (Hindi)
# =========================
async def generate_voice_async(text: str, out_path: str):
    """
    Uses edge-tts to generate Hindi voiceover with hi-IN-MadhurNeural.
    """
    print("🎙️ Generating voiceover with Edge-TTS (hi-IN-MadhurNeural)...")
    communicate = edge_tts.Communicate(text, "hi-IN-MadhurNeural")
    await communicate.save(out_path)
    print(f"✅ Voice saved to {out_path}")


def generate_voice(text: str, out_path: str) -> bool:
    try:
        asyncio.run(generate_voice_async(text, out_path))
        return True
    except Exception as e:
        print(f"❌ Voice generation failed: {e}")
        return False


# =========================
# 3. VIDEO ENGINE – IMAGE + BOTTOM TEXT + VOICE
# =========================
def render_video(image_path: str, quote: str, voice_path: str):
    print("🎬 Rendering Video...")

    try:
        if not os.path.exists(image_path):
            print(f"❌ Image not found: {image_path}")
            return None

        if not os.path.exists(voice_path):
            print(f"❌ Voice file not found: {voice_path}")
            return None

        base_width = 1080
        base_height = 1920

        # --- 3.1 Prepare background image ---
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

        # --- 3.2 Minimal bottom bar text (like your baby Krishna style) ---
        overlay = Image.new("RGBA", (base_width, base_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        font_size = 64
        try:
            font = ImageFont.truetype(FONT_PATH, font_size)
        except Exception:
            font = ImageFont.load_default()

        wrapper = textwrap.TextWrapper(width=25)
        lines = wrapper.wrap(quote.strip())
        if not lines:
            print("⚠️ Empty quote for overlay")
            return None

        line_height = font_size + 8
        text_height = len(lines) * line_height
        max_text_width = 0

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            if w > max_text_width:
                max_text_width = w

        padding_x = 60
        padding_y = 25
        box_width = max_text_width + 2 * padding_x
        box_height = text_height + 2 * padding_y

        box_x1 = (base_width - box_width) / 2
        box_y1 = base_height - box_height - 220  # little above bottom for UI
        box_x2 = box_x1 + box_width
        box_y2 = box_y1 + box_height

        draw.rounded_rectangle(
            (box_x1, box_y1, box_x2, box_y2),
            radius=40,
            fill=(0, 0, 0, 170),
        )

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

        # --- 3.3 FFmpeg – Image loop + overlay + voice audio ---
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        command = [
            ffmpeg_exe,
            "-y",
            "-loop",
            "1",
            "-i",
            "temp_bg.png",      # 0:v
            "-i",
            "temp_overlay.png", # 1:v
            "-i",
            voice_path,         # 2:a
            "-filter_complex",
            "[0:v][1:v]overlay=0:0[v]",
            "-map",
            "[v]",
            "-map",
            "2:a",
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
# 4. YOUTUBE UPLOAD
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
# 5. MAIN EXECUTION
# =========================
if __name__ == "__main__":
    # 1) Get quote/title/description from Gemini
    ai_content = get_ai_quote()
    quote_text = ai_content.get("quote", "").strip()
    title_text = ai_content.get("title", "Krishna Shorts 🦚").strip()
    desc_text = ai_content.get("description", "Jai Shree Krishna #Krishna").strip()

    if not quote_text:
        print("❌ Empty quote from AI")
        exit(1)

    # 2) Generate image via Pollinations
    # You can make this prompt richer if you want more detailed art
    image_prompt = "beautiful devotional illustration of baby Krishna, soft lighting, divine, high quality, 4k, digital art"
    poll_ok = generate_krishna_image(image_prompt, GEN_IMAGE_FILE)

    image_path_to_use = GEN_IMAGE_FILE

    # Fallback: if Pollinations fails, use local image folder
    if not poll_ok:
        print("⚠️ Pollinations failed, falling back to local images/")
        images = [f for f in os.listdir(IMAGE_DIR) if f.lower().endswith((".jpg", ".png"))]
        if not images:
            print("❌ No images available in images/ folder as fallback.")
            exit(1)
        target_image = random.choice(images)
        image_path_to_use = os.path.join(IMAGE_DIR, target_image)
    else:
        target_image = None  # we used generated image, not from folder

    print(f"🖼️ Using image: {image_path_to_use}")

    # 3) Generate voiceover from quote (Hindi)
    voice_ok = generate_voice(quote_text, VOICE_FILE)
    if not voice_ok:
        print("❌ Could not generate voice. Aborting.")
        exit(1)

    # 4) Render video
    video = render_video(image_path_to_use, quote_text, VOICE_FILE)

    if video:
        success = upload_to_youtube(video, title_text, desc_text)

        # Only move local image if we used one from images/
        if success and target_image:
            shutil.move(image_path_to_use, os.path.join(USED_DIR, target_image))
            print("📦 Image moved to images_used/")
        elif success:
            print("📦 Used Pollinations image (no local image to move)")
        else:
            print("⚠️ Upload failed. Image NOT moved.")
    else:
        print("❌ Video render failed.")
