import os, random, textwrap, datetime, json
from pathlib import Path
from gtts import gTTS
from moviepy.editor import TextClip, CompositeVideoClip, AudioFileClip, ColorClip
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from telegram import Bot

# ---------- KONFIGURASI ----------
PROMPTS_DIR = Path("prompts")
OUTPUT_DIR = Path("output")
ASSET_MUSIC = Path("assets/music.mp3")  # opsional
VIDEO_SIZE = (1080, 1920)               # 9:16
FONT_SIZE = 70
FONT_COLOR = 'white'
BG_COLOR = (0, 0, 0)
VIDEOS_PER_RUN = 2
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID", None)
GDRIVE_FOLDER_NAME = "AutoVideos"       # akan dibuat jika folder_id kosong / tidak ada

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

OUTPUT_DIR.mkdir(exist_ok=True)
# ---------------------------------

def kirim_laporan(pesan: str):
    """Kirim laporan ke Telegram jika token dan chat ID tersedia."""
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            bot = Bot(token=TELEGRAM_TOKEN)
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=pesan)
        except Exception as e:
            print(f"Gagal kirim laporan Telegram: {e}")

def load_prompts():
    return sorted(PROMPTS_DIR.glob("*.txt"))

def create_tts(text, lang='id', out_file="temp_audio.mp3"):
    tts = gTTS(text=text, lang=lang)
    tts.save(out_file)
    return out_file

def create_video_from_text(text, audio_file, output_path):
    wrapped = textwrap.fill(text, width=40)
    audio_clip = AudioFileClip(audio_file)
    duration = audio_clip.duration

    # Background
    bg = ColorClip(size=VIDEO_SIZE, color=BG_COLOR, duration=duration)

    # Teks overlay
    txt_clip = TextClip(
        wrapped,
        fontsize=FONT_SIZE,
        color=FONT_COLOR,
        size=(VIDEO_SIZE[0] - 100, None),
        method='caption',
        align='center',
        font='DejaVu-Sans'
    ).set_position('center').set_duration(duration)

    video = CompositeVideoClip([bg, txt_clip]).set_audio(audio_clip)

    # Musik opsional
    if ASSET_MUSIC.exists():
        music = AudioFileClip(str(ASSET_MUSIC)).volumex(0.2).set_duration(duration)
        video = video.set_audio(audio_clip.volumex(1.0))  # gunakan voice utama saja

    video.write_videofile(
        str(output_path),
        fps=30,
        codec="libx264",
        audio_codec="aac"
    )

def get_drive_service():
    creds_json = os.environ.get("GDRIVE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GDRIVE_CREDENTIALS env tidak ditemukan.")
    creds_data = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        creds_data,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=creds)
    return service

def ensure_drive_folder(service, folder_id=None, folder_name="AutoVideos"):
    """Pastikan folder ada, jika tidak ada, buat baru."""
    if folder_id:
        # cek apakah folder ada
        try:
            service.files().get(fileId=folder_id, supportsAllDrives=True).execute()
            return folder_id
        except Exception:
            print("Folder ID tidak ditemukan, akan dibuat baru.")
    
    # buat folder baru di Drive/Shared Drive
    file_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    folder = service.files().create(
        body=file_metadata,
        fields="id",
        supportsAllDrives=True
    ).execute()
    print(f"Folder baru dibuat: {folder_name} (ID: {folder['id']})")
    return folder["id"]

def upload_to_drive(file_path, folder_id=None):
    service = get_drive_service()
    folder_id = ensure_drive_folder(service, folder_id, folder_name=GDRIVE_FOLDER_NAME)
    file_metadata = {"name": os.path.basename(file_path), "parents": [folder_id]}
    media = MediaFileUpload(file_path, resumable=True)
    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
        supportsAllDrives=True
    ).execute()
    file_id = uploaded.get("id")
    drive_url = f"https://drive.google.com/file/d/{file_id}"
    print(f"Uploaded to Drive: {drive_url}")
    return drive_url

def main():
    prompts = load_prompts()
    if not prompts:
        print("Tidak ada file prompt di folder prompts/")
        kirim_laporan("❌ Tidak ada file prompt ditemukan.")
        return

    selected = prompts[:VIDEOS_PER_RUN]
    for prompt_file in selected:
        with open(prompt_file, "r", encoding="utf-8") as f:
            text = f.read().strip()
        if not text:
            continue

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_file = OUTPUT_DIR / f"voice_{timestamp}.mp3"
        video_file = OUTPUT_DIR / f"lifehack_{timestamp}.mp4"

        print(f"▶ Membuat audio: {prompt_file.name}")
        create_tts(text, out_file=str(audio_file))

        print(f"▶ Membuat video: {video_file.name}")
        create_video_from_text(text, str(audio_file), video_file)

        print("▶ Upload ke Google Drive")
        drive_url = upload_to_drive(str(video_file), folder_id=GDRIVE_FOLDER_ID)

        # Laporan Telegram
        kirim_laporan(f"✅ Video berhasil dibuat dan diupload!\n\nNama: {video_file.name}\nDrive: {drive_url}")

        done_dir = PROMPTS_DIR / "done"
        done_dir.mkdir(exist_ok=True)
        prompt_file.rename(done_dir / prompt_file.name)

    print("✅ Semua video selesai diproses.")
    kirim_laporan("🎉 Semua video selesai diproses.")

if __name__ == "__main__":
    main()
