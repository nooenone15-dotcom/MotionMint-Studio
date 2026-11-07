import asyncio
import os
import tempfile
import subprocess
import math
import streamlit as st
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
import edge_tts

st.set_page_config(page_title="MotionMint Studio", page_icon="🎬", layout="centered")
st.title("🎬 MotionMint Studio")
st.caption("Create a simple animated video from text or an image, with optional AI narration.")
st.info("This free starter creates animated graphics/image movement and narration. It does not generate new AI scenes from text.")

mode = st.radio("Choose video source", ["Text prompt", "Animate an image"], horizontal=True)
prompt = st.text_area("Describe your scene / video text", "A beautiful sunset over the mountains")
uploaded = None
if mode == "Animate an image":
    uploaded = st.file_uploader("Upload an image", type=["png", "jpg", "jpeg", "webp"])

duration = st.slider("Video duration (seconds)", 3, 10, 5)
voice_on = st.checkbox("Generate spoken narration from my text", value=True)
voice_text = st.text_area("Narration text", prompt if prompt else "Welcome to MotionMint Studio")
voice = st.selectbox("Narration voice", [
    "en-US-AriaNeural", "en-US-GuyNeural", "en-GB-SoniaNeural",
    "ur-PK-UzmaNeural", "ur-PK-AsadNeural", "hi-IN-SwaraNeural", "hi-IN-MadhurNeural"
])

def get_font(size):
    for candidate in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()

def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = (current + " " + word).strip()
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:5]

async def create_tts(text, voice_name, path):
    communicate = edge_tts.Communicate(text=text, voice=voice_name)
    await communicate.save(path)

def make_video():
    width, height, fps = 640, 360, 20
    frames_count = duration * fps
    tmp = tempfile.mkdtemp()
    mp4_path = os.path.join(tmp, "motionmint_video.mp4")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [ffmpeg, "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
               "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps),
               "-i", "-", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-preset", "ultrafast", mp4_path]
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    source_img = Image.open(uploaded).convert("RGB") if uploaded is not None else None
    font = get_font(30)
    small_font = get_font(18)
    for i in range(frames_count):
        t = i / fps
        if source_img is not None:
            zoom = 1.0 + 0.12 * (i / max(frames_count - 1, 1))
            sw, sh = int(source_img.width * zoom), int(source_img.height * zoom)
            img = source_img.resize((sw, sh), Image.Resampling.LANCZOS)
            left = max(0, (sw - width) // 2)
            top = max(0, (sh - height) // 2)
            img = img.crop((left, top, left + width, top + height))
            if img.size != (width, height):
                img = img.resize((width, height))
        else:
            arr = np.zeros((height, width, 3), dtype=np.uint8)
            phase = t / max(duration, 1)
            for y in range(height):
                blend = y / height
                arr[y, :, 0] = int(20 + 40 * blend + 20 * math.sin(phase * math.pi))
                arr[y, :, 1] = int(30 + 50 * blend)
                arr[y, :, 2] = int(80 + 100 * (1 - blend))
            img = Image.fromarray(arr)
        draw = ImageDraw.Draw(img)
        title = prompt.strip() or "MotionMint Studio"
        lines = wrap_text(title, font, width - 60, draw)
        text_height = len(lines) * 40
        y0 = (height - text_height) // 2
        # translucent dark panel behind text
        draw.rounded_rectangle((20, y0 - 20, width - 20, y0 + text_height + 20), radius=18, fill=(0, 0, 0, 150))
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            x = (width - (bbox[2] - bbox[0])) // 2
            draw.text((x, y0), line, font=font, fill="white", stroke_width=1, stroke_fill="black")
            y0 += 40
        draw.text((18, height - 30), "MotionMint Studio", font=small_font, fill="white")
        proc.stdin.write(np.asarray(img, dtype=np.uint8).tobytes())
    proc.stdin.close()
    stderr = proc.stderr.read().decode("utf-8", errors="ignore")
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError("Video encoder failed: " + stderr[-1200:])
    if voice_on and voice_text.strip():
        audio_path = os.path.join(tmp, "narration.mp3")
        asyncio.run(create_tts(voice_text.strip(), voice, audio_path))
        combined = os.path.join(tmp, "motionmint_with_voice.mp4")
        subprocess.run([ffmpeg, "-y", "-i", mp4_path, "-i", audio_path, "-c:v", "copy",
                        "-c:a", "aac", "-shortest", combined], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return combined
    return mp4_path

if st.button("✨ Generate video", type="primary", use_container_width=True):
    if mode == "Animate an image" and uploaded is None:
        st.warning("Please upload an image first.")
    elif not prompt.strip():
        st.warning("Please write a scene description.")
    else:
        try:
            with st.spinner("Creating your video… please wait."):
                result_path = make_video()
            with open(result_path, "rb") as video_file:
                video_bytes = video_file.read()
            st.success("Your video is ready!")
            st.video(video_bytes)
            st.download_button("⬇️ Download MP4", data=video_bytes, file_name="motionmint_video.mp4",
                               mime="video/mp4", use_container_width=True)
        except Exception as exc:
            st.error(f"Could not create video: {exc}")
