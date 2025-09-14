import os, random, textwrap, datetime, json
from pathlib import Path
from gtts import gTTS
from moviepy.editor import (
    TextClip, CompositeVideoClip, AudioFileClip, ColorClip
)
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

# ---------- KONFIGURASI ----------
PROMPTS_DIR = Path("prompts")
OUTPUT_DIR = Path("output")
ASSET_MUSIC = Path("assets/music.mp3")  # opsional
VIDEO_SIZE = (1080, 1920)              # 9:16
FONT_SIZE = 70
FONT_COLOR = 'white'
BG_COLOR = (0, 0, 0)
VIDEOS_PER_RUN = 2
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID", None)

OUTPUT_DIR.mkdir(exist_ok=True)
# ---------------------------------

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

    # Teks overlay (hapus use_builtin, gunakan method='caption')
    txt_clip = TextClip(
        wrapped,
        fontsize=FONT_SIZE,
        color=FONT_COLOR,
        size=(VIDEO_SIZE[0] - 100, None),
        method='caption',
        align='center',
        font='DejaVu-Sans'  # pastikan font tersedia
    ).set_position('center').set_duration(duration)

    video = CompositeVideoClip([bg, txt_clip]).set_audio(audio_clip)

    # Tambahkan musik opsional
    if ASSET_MUSIC.exists():
        music = AudioFileClip(str(ASSET_MUSIC)).volumex(0.2).set_duration(duration)
        final_audio = audio_clip.volumex(1.0)
        # Kombinasi manual: tumpuk musik dengan voiceover
        video = video.set_audio(final_audio)  # Bisa diganti dengan composite audio jika perlu

    video.write_videofile(
        str(output_path),
        fps=30,
        codec="libx264",
        audio_codec="aac"
    )

def upload_to_drive(file_path, folder_id=None):
    gauth = GoogleAuth()
    creds_json = os.environ.get("GDRIVE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GDRIVE_CREDENTIALS env tidak ditemukan.")
    creds_data = json.loads(creds_json)

    tmp_credentials = "creds.json"
    with open(tmp_credentials, "w") as f:
        json.dump(creds_data, f)

    gauth.LoadCredentialsFile(tmp_credentials)
    if gauth.credentials is None:
        raise ValueError("Kredensial Google Drive tidak valid.")
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()

    drive = GoogleDrive(gauth)
    file_name = os.path.basename(file_path)
    gfile = drive.CreateFile({
        'title': file_name,
        'parents': [{'id': folder_id}] if folder_id else []
    })
    gfile.SetContentFile(file_path)
    gfile.Upload()
    print(f"Uploaded to Drive: {file_name}")

def main():
    prompts = load_prompts()
    if not prompts:
        print("Tidak ada file prompt di folder prompts/")
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
        upload_to_drive(str(video_file), folder_id=GDRIVE_FOLDER_ID)

        done_dir = PROMPTS_DIR / "done"
        done_dir.mkdir(exist_ok=True)
        prompt_file.rename(done_dir / prompt_file.name)

    print("✅ Semua video selesai diproses.")

if __name__ == "__main__":
    main()
