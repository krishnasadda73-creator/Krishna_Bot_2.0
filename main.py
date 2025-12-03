import os
import random
import shutil
import textwrap
import google.generativeai as genai
from moviepy.editor import *
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

# --- 2. VIDEO ENGINE (THE EDITOR) ---
def render_video(image_path, quote):
    print("🎬 Rendering Video...")
    
    bgm_files = [f for f in os.listdir(BGM_DIR) if f.endswith(".mp3")]
    if not bgm_files:
        print("❌ No BGM found!")
        return None
        
    selected_bgm = random.choice(bgm_files)
    print(f"🎵 Selected Music: {selected_bgm}")
    
    audio = AudioFileClip(os.path.join(BGM_DIR, selected_bgm))
    
    # Duration Logic (Max 58s)
    duration = min(audio.duration, 58.0)
    audio = audio.subclip(0, duration)
    
    # Image Logic (Crop 9:16)
    clip = ImageClip(image_path).resize(height=1920)
    clip = clip.crop(x1=clip.w/2 - 540, y1=0, width=1080, height=1920)
    clip = clip.set_duration(duration)
    
    # Text Logic
    wrapper = textwrap.TextWrapper(width=25)
    wrapped_txt = "\n".join(wrapper.wrap(quote))
    
    # Font Fallback System
    try:
        txt_clip = TextClip(wrapped_txt, fontsize=75, color='white', font=FONT_PATH, method='label', align='center')
    except Exception as e:
        print(f"⚠️ Custom font failed ({e}), using default Arial.")
        txt_clip = TextClip(wrapped_txt, fontsize=75, color='white', font='Arial', method='label', align='center')

    # Positioning (Bottom)
    txt_x = 'center'
    txt_y = 1920 - txt_clip.h - 200 
    txt_clip = txt_clip.set_position((txt_x, txt_y)).set_duration(duration)
    
    # Shadow Box
    shadow = ColorClip(size=(txt_clip.w + 60, txt_clip.h + 40), color=(0,0,0)).set_opacity(0.6)
    shadow = shadow.set_position(('center', txt_y - 20)).set_duration(duration)
    
    final = CompositeVideoClip([clip, shadow, txt_clip]).set_audio(audio)
    final.write_videofile(OUTPUT_FILE, fps=24, codec="libx264", audio_codec="aac")
    return OUTPUT_FILE

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
