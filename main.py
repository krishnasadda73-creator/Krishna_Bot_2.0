import os
import random
import shutil
import textwrap
import subprocess
import json
import imageio_ffmpeg
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# --- CONFIGURATION ---
IMAGE_DIR = "images"
USED_DIR = "images_used"
BGM_DIR = "bgm"
FONT_PATH = "fonts/font.ttf" 
OUTPUT_FILE = "short.mp4"

# --- 1. VISION AI (THE POETIC WRITER) ---
def get_ai_quote(image_path):
    print(f"👁️ Vision AI Analyzing: {image_path}...")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ ERROR: GEMINI_API_KEY is missing from Secrets!")
        exit(1)

    genai.configure(api_key=api_key)
    
    # 🛡️ SAFETY NET: Models list
    models_to_try = [
        "gemini-2.5-flash", 
        "gemini-2.0-flash", 
        "gemini-1.5-flash", 
        "gemini-pro"
    ]
    
    for model_name in models_to_try:
        try:
            print(f"🤖 Trying model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            myfile = genai.upload_file(image_path)
            
            # --- PROMPT: Short, Deep, & Viral ---
            prompt = """
            You are a Bhakti poet and devotee of Lord Krishna. Look at this image.
            1. Feel the emotion (Vatsalya, Viraha, Prem, Shakti).
            2. Generate a valid JSON object with exactly these 3 fields:
               - "quote": A 2-line Hindi Shayari/Quote. Rhyming, deep, natural. Max 10-12 words. NO EMOJIS in this field.
               - "title": A viral, catchy YouTube Short title (Hindi + English mix). Use attractive cute emojis (🦚, 🌹, ✨, ❤️, 🌟, 🦢).
               - "description": A beautiful, heart-touching caption. Use natural flowery language and emojis (🦚, 🕉️, 🌼, ❤️). Add 5-6 relevant hashtags.
            
            Output strictly valid JSON only. Do not add markdown formatting.
            """
            
            result = model.generate_content([myfile, prompt])
            text = result.text.strip()
            
            # Clean up potential markdown formatting
            if text.startswith("```"):
                text = text.replace("```json", "").replace("```", "")
            
            data = json.loads(text)
            print(f"✨ AI Generated:\nQuote: {data.get('quote')}\nTitle: {data.get('title')}")
            return data
            
        except Exception as e:
            print(f"⚠️ Model {model_name} failed: {e}")
            continue 
            
    print("❌ CRITICAL: All AI models failed.")
    exit(1)

# --- 2. VIDEO ENGINE (FFMPEG + PIL + MINIMALIST TEXT) ---
def render_video(image_path, quote):
    print("🎬 Rendering Video with Direct FFmpeg...")
    
    try:
        # 1. Pick Music
        bgm_files = [f for f in os.listdir(BGM_DIR) if f.endswith(".mp3")]
        if not bgm_files:
            print("❌ No BGM found!")
            return None
            
        selected_bgm = random.choice(bgm_files)
        bgm_path = os.path.join(BGM_DIR, selected_bgm)
        print(f"🎵 Selected Music: {selected_bgm}")

        # 2. Prepare Background Image
        print("🖼️ Processing Background Image...")
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
            right = (new_width + base_width) / 2
            bottom = (new_height + base_height) / 2
            img = img.crop((left, top, right, bottom))
            img.save("temp_bg.png")

        # 3. Create Text Overlay (MINIMALIST STYLE)
        print("✍️ Creating Text Overlay...")
        overlay = Image.new('RGBA', (base_width, base_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        font_size = 85 # Slightly bigger for impact
        try:
            font = ImageFont.truetype(FONT_PATH, font_size)
        except:
            print("⚠️ Custom font failed, attempting default.")
            try:
                font = ImageFont.truetype("arial.ttf", font_size) 
            except:
                 font = ImageFont.load_default()

        # Tighter wrapping for compact look
        wrapper = textwrap.TextWrapper(width=20) 
        lines = wrapper.wrap(quote)
        
        line_height = font_size + 20
        total_text_height = len(lines) * line_height
        
        # Position: Bottom area (Moved down slightly to be less obtrusive)
        start_y = base_height - total_text_height - 350
        
        # --- NO BOX, JUST OUTLINE (MINIMALIST) ---
        current_y = start_y
        for line in lines:
            # Measure text
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            text_x = (base_width - text_w) / 2
            
            # Draw Text with THICK STROKE (Outline)
            # stroke_width=6 creates a nice black border around white text
            # This makes it readable on bright OR dark backgrounds without a box
            draw.text(
                (text_x, current_y), 
                line, 
                font=font, 
                fill="white", 
                stroke_width=6, 
                stroke_fill="black"
            )
            
            current_y += line_height
            
        overlay.save("temp_overlay.png")

        # 4. FFmpeg Command
        print("💾 Encoding Final Video with FFmpeg...")
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        
        command = [
            ffmpeg_exe, '-y',
            '-loop', '1', '-i', 'temp_bg.png',
            '-i', 'temp_overlay.png',
            '-i', bgm_path,
            '-filter_complex', '[0:v][1:v]overlay=0:0[v]',
            '-map', '[v]', '-map', '2:a',
            '-t', '58', '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p', '-shortest',
            OUTPUT_FILE
        ]
        
        subprocess.run(command, capture_output=True, check=True)
        print("✅ Video Rendered Successfully!")
        return OUTPUT_FILE
        
    except Exception as e:
        print(f"❌ RENDER ERROR: {e}")
        return None

# --- 3. YOUTUBE UPLOAD (PUBLIC) ---
def upload_to_youtube(video_file, title, description):
    print("🚀 Uploading to YouTube...")
    try:
        creds = Credentials(
            None,
            refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
            token_uri="[https://oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)",
            client_id=os.environ["YOUTUBE_CLIENT_ID"],
            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"]
        )
        youtube = build('youtube', 'v3', credentials=creds)
        
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": ["Krishna", "Bhakti", "Motivation", "Hinduism", "RadhaKrishna", "Shorts"],
                    "categoryId": "22"
                },
                "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
            },
            media_body=MediaFileUpload(video_file)
        )
        response = request.execute()
        print(f"✅ Upload Success! Video ID: {response['id']}")
        return True
    except Exception as e:
        print(f"❌ Upload Failed: {e}")
        return False

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    images = [f for f in os.listdir(IMAGE_DIR) if f.endswith(('.jpg', '.png'))]
    
    if not images:
        print("❌ CRITICAL: No images left! Add more to 'images/' folder.")
        exit()
        
    target_image = images[0]
    full_path = os.path.join(IMAGE_DIR, target_image)
    print(f"🖼️ Processing: {target_image}")
    
    # Get all AI Data (Quote, Title, Desc)
    ai_content = get_ai_quote(full_path)
    
    if ai_content:
        # Extract the parts
        quote_text = ai_content.get("quote", "")
        title_text = ai_content.get("title", "Krishna Shorts 🦚")
        desc_text = ai_content.get("description", "Jai Shree Krishna #Krishna")

        # Fallback if AI fails to give a quote
        if not quote_text:
            print("❌ AI returned empty quote.")
            exit(1)

        video = render_video(full_path, quote_text)
        if video:
            success = upload_to_youtube(video, title_text, desc_text)
            if success:
                shutil.move(full_path, os.path.join(USED_DIR, target_image))
                print(f"📦 Moved {target_image} to history folder.")
            else:
                print("⚠️ Upload failed. Image NOT moved.")
        else:
            print("❌ Render failed.")
