import os
import random
import textwrap
import subprocess
import json
import traceback
import requests
import urllib.parse
import time  # for retry delays

import imageio_ffmpeg
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# =========================
# CONFIG & PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_DIR = os.path.join(BASE_DIR, "images")      # fallback folder
USED_DIR = os.path.join(BASE_DIR, "images_used")
BGM_DIR = os.path.join(BASE_DIR, "bgm")
FONT_PATH = os.path.join(BASE_DIR, "fonts", "font.ttf")
OUTPUT_FILE = os.path.join(BASE_DIR, "short.mp4")
GEN_IMAGE_FILE = os.path.join(BASE_DIR, "generated.png")

for folder in [IMAGE_DIR, USED_DIR, BGM_DIR, os.path.dirname(FONT_PATH)]:
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

# =========================
# 0. IMAGE – POLLINATIONS (WITH RETRY)
# =========================
def generate_krishna_image(prompt: str, out_path: str, retries: int = 3, delay: int = 5) -> bool:
    """
    Uses Pollinations to generate an image.
    Retries a few times if the server fails.
    """
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"

    for attempt in range(1, retries + 1):
        try:
            print(f"🎨 Pollinations attempt {attempt}/{retries}...")
            response = requests.get(url, stream=True, timeout=60)

            if response.status_code == 200:
                with open(out_path, "wb") as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                print(f"✅ Pollinations image saved to {out_path}")
                return True
            else:
                print(f"⚠️ Pollinations HTTP {response.status_code}")
        except Exception as e:
            print(f"⚠️ Pollinations error on attempt {attempt}: {e}")

        if attempt < retries:
            print(f"⏳ Waiting {delay} seconds before retry...")
            time.sleep(delay)

    print("❌ Pollinations failed after all retries.")
    return False

# =========================
# 1. GEMINI – SHORT, THEME-AWARE TEXT
# =========================
def get_ai_quote(scene_label: str):
    """
    Uses Gemini to generate a very short quote + title + description,
    tailored to the Krishna scene theme (e.g., Baby Krishna, Flute Krishna).
    """
    print(f"🧠 Generating SHORT quote via Gemini for scene: {scene_label}...")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("❌ GEMINI_API_KEY missing!")

    genai.configure(api_key=api_key)

    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]

    prompt = f"""
You are a Krishna Bhakti shorts script writer.
Current visual scene: "{scene_label}".

Generate STRICT JSON with ONLY these fields:
- "quote": Very SHORT Hindi line (5–7 words). Deep, emotional, devotional. NO emojis.
          It MUST match the scene: {scene_label}.
- "title": Catchy YouTube Shorts title (Hindi + English mix) with 1–2 emojis only.
           Also match the scene mood.
- "description": Short devotional caption + 5 relevant hashtags.

Rules:
- Quote must be very short and simple.
- No extra commentary.
- Output ONLY valid JSON. No markdown, no explanation.
"""

    for model_name in models_to_try:
        try:
            print(f"🤖 Trying Gemini model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            result = model.generate_content(prompt)

            raw = result.text.strip()

            # Remove ```json fences if present
            if raw.startswith("```"):
                raw = raw.replace("```json", "").replace("```", "")

            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end <= 0:
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

    raise RuntimeError("❌ All Gemini models failed")

# =========================
# 2. VIDEO ENGINE (IMAGE + BGM + MINIMAL BOTTOM TEXT)
# =========================
def render_video(image_path, quote):
    print("🎬 Rendering Video with BGM...")

    try:
        bgm_files = [f for f in os.listdir(BGM_DIR) if f.lower().endswith(".mp3")]
        if not bgm_files:
            print("❌ No BGM found in bgm/")
            return None

        bgm_path = os.path.join(BGM_DIR, random.choice(bgm_files))
        print(f"🎵 Using BGM: {os.path.basename(bgm_path)}")

        base_width = 1080
        base_height = 1920

        # ---- Background Image ----
        from PIL import Image  # (import here just in case)
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

        # ---- Bottom Minimal Text ----
        overlay = Image.new("RGBA", (base_width, base_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        font_size = 58
        try:
            font = ImageFont.truetype(FONT_PATH, font_size)
        except Exception:
            font = ImageFont.load_default()

        wrapper = textwrap.TextWrapper(width=22)
        lines = wrapper.wrap(quote)

        line_height = font_size + 8
        text_height = len(lines) * line_height
        max_width = 0

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            max_width = max(max_width, bbox[2] - bbox[0])

        padding_x = 50
        padding_y = 20
        box_width = max_width + 2 * padding_x
        box_height = text_height + 2 * padding_y

        box_x1 = (base_width - box_width) / 2
        box_y1 = base_height - box_height - 220
        box_x2 = box_x1 + box_width
        box_y2 = box_y1 + box_height

        draw.rounded_rectangle(
            (box_x1, box_y1, box_x2, box_y2),
            radius=36,
            fill=(0, 0, 0, 170),
        )

        current_y = box_y1 + padding_y
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            x = box_x1 + (box_width - w) / 2
            draw.text((x, current_y), line, font=font, fill="white")
            current_y += line_height

        overlay.save("temp_overlay.png")

        # ---- FFmpeg: Image + Overlay + BGM ----
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        command = [
            ffmpeg_exe, "-y",
            "-loop", "1", "-i", "temp_bg.png",
            "-i", "temp_overlay.png",
            "-i", bgm_path,
            "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
            "-map", "[v]", "-map", "2:a",
            "-t", "58",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-shortest",
            OUTPUT_FILE
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
                    "tags": ["Krishna", "Bhakti", "Shorts", "Hinduism"],
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
        print(f"✅ Upload Success: {response['id']}")
        return True

    except Exception:
        traceback.print_exc()
        return False

# =========================
# 4. MAIN
# =========================
if __name__ == "__main__":
    # 0) Define Krishna scene themes + image prompts
    krishna_scenes = [
        (
            "Baby Krishna eating Makhan",
            "cute baby Krishna eating butter, happy expression, indoor Vrindavan house, soft warm light, ultra realistic, 4k"
        ),
        (
            "Krishna playing flute in Vrindavan",
            "Lord Krishna playing flute in Vrindavan forest, cows and peacocks around, golden sunset light, ultra realistic, 4k"
        ),
        (
            "Radha Krishna divine love",
            "Radha and Krishna standing together, romantic devotional pose, flowers around, soft glowing divine light, ultra realistic, 4k"
        ),
        (
            "Krishna teaching Arjuna on battlefield",
            "Lord Krishna as charioteer guiding Arjuna on the battlefield of Kurukshetra, dramatic sky, epic scene, ultra realistic, 4k"
        ),
        (
            "Peaceful meditating Krishna",
            "Lord Krishna sitting peacefully near river Yamuna, moonlight, stars, calm night, ultra realistic, 4k"
        ),
        (
            "Temple aarti of Krishna",
            "Lord Krishna idol during temple aarti, many diyas and lamps, devotees, golden light, ultra realistic, 4k"
        ),
    ]

    scene_label, image_prompt = random.choice(krishna_scenes)
    print(f"🎭 Selected scene: {scene_label}")

    # 1) Text from Gemini (aware of scene)
    ai_content = get_ai_quote(scene_label)
    quote_text = ai_content.get("quote", "").strip()
    title_text = ai_content.get("title", "Krishna Shorts 🦚").strip()
    desc_text = ai_content.get("description", "Jai Shree Krishna #Krishna").strip()

    if not quote_text:
        print("❌ Empty quote from AI")
        exit(1)

    # 2) Image from Pollinations (with retries) or fallback to local image
    poll_ok = generate_krishna_image(image_prompt, GEN_IMAGE_FILE)

    if poll_ok:
        image_path = GEN_IMAGE_FILE
        print(f"🖼️ Using Pollinations image: {image_path}")
    else:
        print("⚠️ Using fallback local image from images/")
        images = [f for f in os.listdir(IMAGE_DIR) if f.lower().endswith((".jpg", ".png"))]
        if not images:
            print("❌ No fallback images available.")
            exit(1)
        fallback = random.choice(images)
        image_path = os.path.join(IMAGE_DIR, fallback)
        print(f"🖼️ Using local image: {image_path}")

    # 3) Render video
    video = render_video(image_path, quote_text)

    if video:
        success = upload_to_youtube(video, title_text, desc_text)
        if success:
            print("✅ Reel uploaded successfully")
        else:
            print("⚠️ Upload failed.")
    else:
        print("❌ Video render failed.")
