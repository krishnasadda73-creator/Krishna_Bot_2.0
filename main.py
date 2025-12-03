import os
import random
import shutil
import textwrap
import subprocess
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

# --- 1. VISION AI (THE DIAGNOSTIC WRITER) ---
def get_ai_quote(image_path):
    print(f"👁️ Vision AI Analyzing: {image_path}...")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ ERROR: GEMINI_API_KEY is missing from Secrets!")
        exit(1)

    # DIAGNOSTIC: Print first 4 chars to verify key update
    print(f"🔑 Using API Key starting with: {api_key[:4]}...")

    genai.configure(api_key=api_key)
    
    # DIAGNOSTIC: List available models for this specific key
    print("📋 Checking available models for this Project...")
    try:
        found_any = False
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"   - Found model: {m.name}")
                found_any = True
        if not found_any:
            print("   ⚠️ No text generation models found! (Generative Language API might be OFF)")
    except Exception as e:
        print(f"❌ Could not list models. Error: {e}")
        print("   (This usually means the API Key is invalid or the Project is deleted)")

    # 🛡️ SAFETY NET: Updated to match your available models (2.5 and 2.0)
    models_to_try = [
        "gemini-2.5-flash", 
        "gemini-2.0-flash", 
        "gemini-2.0-flash-exp",
        "gemini-1.5-flash",
        "gemini-pro"
    ]
    
    for model_name in models_to_try:
        try:
            print(f"🤖 Trying model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            myfile = genai.upload_file(image_path)
            
            prompt = """
            You are a spiritual creator. Look at this image of Lord Krishna.
            1. Identify the emotion (Peace, Love, Power, Wisdom).
            2. Write a powerful, short HINDI spiritual quote (max 15 words) matching that emotion.
            3. Output ONLY the Hindi text. No English, no hashtags.
            """
            
            result = model.generate_content([myfile, prompt])
            text = result.text.strip()
            print(f"✨ Generated Quote: {text}")
            return text
            
        except Exception as e:
            print(f"⚠️ Model {model_name} failed: {e}")
            continue # Try the next model
            
    print("❌ CRITICAL: All AI models failed. Please check the logs above to see which models are available.")
    exit(1)

# --- 2. VIDEO ENGINE (FFMPEG + PIL) ---
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

        # 2. Prepare Background Image (Resize & Crop using PIL)
        print("🖼️ Processing Background Image...")
        base_width = 1080
        base_height = 1920
        
        with Image.open(image_path) as img:
            # Resize Logic: Cover the area
            img_ratio = img.width / img.height
            target_ratio = base_width / base_height
            
            if img_ratio > target_ratio:
                # Too wide: fit height, crop width
                new_height = base_height
                new_width = int(new_height * img_ratio)
            else:
                # Too tall: fit width, crop height
                new_width = base_width
                new_height = int(new_width / img_ratio)
                
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Center Crop
            left = (new_width - base_width) / 2
            top = (new_height - base_height) / 2
            right = (new_width + base_width) / 2
            bottom = (new_height + base_height) / 2
            img = img.crop((left, top, right, bottom))
            
            # Save Background Temp
            img.save("temp_bg.png")

        # 3. Create Text Overlay (Transparent PNG)
        print("✍️ Creating Text Overlay...")
        overlay = Image.new('RGBA', (base_width, base_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Font Setup
        font_size = 75
        try:
            font = ImageFont.truetype(FONT_PATH, font_size)
        except:
            print("⚠️ Custom font failed, attempting default.")
            try:
                # Try to find a system font or generic path if FONT_PATH fails
                font = ImageFont.truetype("arial.ttf", font_size) 
            except:
                 font = ImageFont.load_default()

        # Wrap Text
        wrapper = textwrap.TextWrapper(width=25)
        lines = wrapper.wrap(quote)
        
        # Calculate Text Height block
        # We estimate height based on font size + padding
        line_height = font_size + 15
        total_text_height = len(lines) * line_height
        
        # Position: Bottom (with 200px margin)
        start_y = base_height - total_text_height - 250
        
        # Draw Shadow Box first
        padding = 40
        box_top = start_y - padding
        box_bottom = start_y + total_text_height + padding
        # We want the box to be centered and wide enough for the widest line
        max_line_width = 0
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            width = bbox[2] - bbox[0]
            if width > max_line_width:
                max_line_width = width
                
        box_left = (base_width - max_line_width) / 2 - padding
        box_right = (base_width + max_line_width) / 2 + padding
        
        draw.rectangle([box_left, box_top, box_right, box_bottom], fill=(0, 0, 0, 160))

        # Draw Text
        current_y = start_y
        for line in lines:
            # Center text horizontally
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            text_x = (base_width - text_w) / 2
            
            draw.text((text_x, current_y), line, font=font, fill="white")
            current_y += line_height
            
        overlay.save("temp_overlay.png")

        # 4. FFmpeg Command (The "Glue")
        print("💾 Encoding Final Video with FFmpeg...")
        
        # This command overlays the text on the bg, adds audio, and cuts to 58s max
        command = [
            'ffmpeg',
            '-y',                      # Overwrite output
            '-loop', '1',              # Loop image
            '-i', 'temp_bg.png',       # Input 0: Background
            '-i', 'temp_overlay.png',  # Input 1: Text Overlay
            '-i', bgm_path,            # Input 2: Audio
            '-filter_complex', '[0:v][1:v]overlay=0:0[v]', # Combine images
            '-map', '[v]',             # Use combined video
            '-map', '2:a',             # Use audio file
            '-t', '58',                # Max duration 58s
            '-c:v', 'libx264',         # H.264 Video Codec
            '-pix_fmt', 'yuv420p',     # Pixel format for compatibility
            '-shortest',               # Stop if audio is shorter than 58s
            OUTPUT_FILE
        ]
        
        subprocess.run(command, check=True)
        
        print("✅ Video Rendered Successfully!")
        return OUTPUT_FILE
        
    except Exception as e:
        print(f"❌ CRITICAL RENDER ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

# --- 3. YOUTUBE UPLOAD (THE COURIER) ---
def upload_to_youtube(video_file, quote):
    print("🚀 Uploading to YouTube...")
    try:
        creds = Credentials(
            None,
            refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["YOUTUBE_CLIENT_ID"],
            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"]
        )
        youtube = build('youtube', 'v3', credentials=creds)
        
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": f"{quote} #Krishna #Shorts",
                    "description": "Jai Shree Krishna. Daily Motivation. #Bhakti #Hinduism",
                    "tags": ["Krishna", "Bhakti", "Motivation", "Hinduism"],
                    "categoryId": "22"
                },
                "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
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
    
    # Run Flow
    quote = get_ai_quote(full_path)
    
    if quote:
        video = render_video(full_path, quote)
        if video:
            success = upload_to_youtube(video, quote)
            if success:
                shutil.move(full_path, os.path.join(USED_DIR, target_image))
                print(f"📦 Moved {target_image} to history folder.")
            else:
                print("⚠️ Upload failed. Image NOT moved.")
        else:
            print("❌ Render failed.")
