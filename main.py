import os
import random
import shutil
import textwrap
import datetime
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

# --- 1. VISION AI (THE WRITER) ---
def get_ai_quote(image_path):
    print(f"👁️ Vision AI Analyzing: {image_path}...")
    
    # Configure Gemini
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    myfile = genai.upload_file(image_path)
    
    # The Prompt
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

# --- 2. VIDEO ENGINE (THE EDITOR) ---
def render_video(image_path, quote):
    print("🎬 Rendering Video...")
    
    # 1. Pick Music
    bgm_files = [f for f in os.listdir(BGM_DIR) if f.endswith(".mp3")]
    selected_bgm = random.choice(bgm_files)
    print(f"🎵 Selected Music: {selected_bgm}")
    
    audio = AudioFileClip(os.path.join(BGM_DIR, selected_bgm))
    
    # 2. Set Duration (Max 58s for Shorts)
    duration = min(audio.duration, 58.0)
    audio = audio.subclip(0, duration)
    
    # 3. Process Image (Crop 9:16)
    clip = ImageClip(image_path).resize(height=1920)
    # Center crop logic
    clip = clip.crop(x1=clip.w/2 - 540, y1=0, width=1080, height=1920)
    clip = clip.set_duration(duration)
    
    # 4. Create Text (Bottom Position)
    wrapper = textwrap.TextWrapper(width=25) # Break line every 25 chars
    wrapped_txt = "\n".join(wrapper.wrap(quote))
    
    # Generate Text Clip
    txt_clip = TextClip(wrapped_txt, fontsize=75, color='white', font=FONT_PATH, method='label', align='center')
    
    # Position: Center X, Bottom Y (150px margin)
    txt_x = 'center'
    txt_y = 1920 - txt_clip.h - 200 
    
    txt_clip = txt_clip.set_position((txt_x, txt_y)).set_duration(duration)
    
    # 5. Add Black Shadow Box (For readability)
    shadow = ColorClip(size=(txt_clip.w + 60, txt_clip.h + 40), color=(0,0,0)).set_opacity(0.6)
    shadow = shadow.set_position(('center', txt_y - 20)).set_duration(duration)
    
    # 6. Combine
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
                    "description": "Jai Shree Krishna. Daily Motivation.",
                    "tags": ["Krishna", "Bhakti", "Motivation", "Hinduism"],
                    "categoryId": "22"
                },
                "status": {
                    "privacyStatus": "private", # KEEP PRIVATE FOR TESTING
                    "selfDeclaredMadeForKids": False
                }
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
    # 1. Find an unused image
    images = [f for f in os.listdir(IMAGE_DIR) if f.endswith(('.jpg', '.png'))]
    
    if not images:
        print("❌ CRITICAL: No images left! Add more to 'images/' folder.")
        exit()
        
    # Pick the first one (we will move it later, so order doesn't matter)
    target_image = images[0]
    full_path = os.path.join(IMAGE_DIR, target_image)
    print(f"🖼️ Processing: {target_image}")
    
    # 2. Run the Machine
    quote = get_ai_quote(full_path)
    
    if quote:
        render_video(full_path, quote)
        
        # 3. Upload (Only if render worked)
        success = upload_to_youtube(OUTPUT_FILE, quote)
        
        # 4. Move to Used (Only if upload worked)
        if success:
            shutil.move(full_path, os.path.join(USED_DIR, target_image))
            print(f"📦 Moved {target_image} to history folder.")
        else:
            print("⚠️ Upload failed, keeping image for next time.")
