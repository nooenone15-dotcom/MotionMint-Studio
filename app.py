import os
import math
import tempfile
import subprocess
from pathlib import Path

import gradio as gr
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

OUT = Path("outputs")
OUT.mkdir(exist_ok=True)

VOICES = {
    "English - Jenny (Female)": "en-US-JennyNeural",
    "English - Aria (Female)": "en-US-AriaNeural",
    "English - Guy (Male)": "en-US-GuyNeural",
    "English - Davis (Male)": "en-US-DavisNeural",
    "Urdu - Uzma (Female)": "ur-PK-UzmaNeural",
    "Urdu - Asad (Male)": "ur-PK-AsadNeural",
    "Hindi - Swara (Female)": "hi-IN-SwaraNeural",
    "Hindi - Madhur (Male)": "hi-IN-MadhurNeural",
}

def get_font(size):
    for candidate in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()

def wrap_text(draw, text, font, max_width):
    words = (text or "Your video starts here").split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines[:6]

def make_video(prompt, image_file, narration, voice_label, ratio, duration, effect):
    try:
        import numpy as np
    except Exception as e:
        raise gr.Error(f"Missing numpy: {e}")

    width, height = (1280, 720) if ratio == "16:9 Landscape" else ((720, 1280) if ratio == "9:16 Portrait" else (1080, 1080))
    fps = 24
    seconds = int(duration)
    total = fps * seconds
    title = (prompt or "").strip() or "MotionMint Studio"
    output = OUT / f"motionmint_{os.getpid()}.mp4"

    source = None
    if image_file:
        try:
            source = Image.open(image_file).convert("RGB")
        except Exception as e:
            raise gr.Error(f"Could not open image: {e}")
        source = source.resize((width, height), Image.Resampling.LANCZOS)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{width}x{height}", "-pix_fmt", "rgb24", "-r", str(fps),
        "-i", "-", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(output)
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    font = get_font(max(28, int(width * 0.055)))
    small = get_font(max(18, int(width * 0.022)))
    try:
        for i in range(total):
            t = i / max(1, total - 1)
            if source:
                scale = 1.0 + (0.10 * t if effect in ["Slow zoom in", "Pulse"] else 0.05 * math.sin(t * math.pi))
                sw, sh = int(width * scale), int(height * scale)
                frame = source.resize((sw, sh), Image.Resampling.LANCZOS)
                if effect == "Move left":
                    x = int((sw - width) * t)
                elif effect == "Move right":
                    x = int((sw - width) * (1 - t))
                else:
                    x = (sw - width) // 2
                y = (sh - height) // 2
                frame = frame.crop((x, y, x + width, y + height))
                overlay = Image.new("RGBA", (width, height), (0, 0, 0, 75))
                frame = Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")
            else:
                # Procedural animated gradient background; not an AI-generated scene.
                arr = np.zeros((height, width, 3), dtype=np.uint8)
                yy, xx = np.mgrid[0:height, 0:width]
                phase = t * 2 * math.pi
                v = (np.sin(xx / width * 5 + phase) + np.cos(yy / height * 4 - phase)) / 2
                arr[:, :, 0] = np.clip(30 + 55 * (v + 1), 0, 255)
                arr[:, :, 1] = np.clip(20 + 45 * (1 - v), 0, 255)
                arr[:, :, 2] = np.clip(75 + 100 * (v + 1) / 2, 0, 255)
                frame = Image.fromarray(arr, "RGB")

            draw = ImageDraw.Draw(frame)
            lines = wrap_text(draw, title, font, int(width * 0.82))
            line_h = int(font.size * 1.35)
            block_h = len(lines) * line_h
            y0 = (height - block_h) // 2
            for j, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font, stroke_width=2)
                x = (width - (bbox[2] - bbox[0])) // 2
                draw.text((x, y0 + j * line_h), line, font=font, fill="white",
                          stroke_width=2, stroke_fill=(0, 0, 0))
            footer = "MOTIONMINT STUDIO"
            draw.text((width * 0.04, height * 0.93), footer, font=small, fill=(235, 235, 245))
            if effect == "Fade in" and t < 0.2:
                frame = Image.blend(Image.new("RGB", (width, height), "black"), frame, t / 0.2)
            proc.stdin.write(np.asarray(frame, dtype=np.uint8).tobytes())
        proc.stdin.close()
        stderr = proc.stderr.read().decode("utf-8", "ignore")
        code = proc.wait()
        if code != 0:
            raise RuntimeError(stderr[-1800:])
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        raise

    audio_path = None
    if narration and narration.strip():
        try:
            import asyncio
            import edge_tts
            audio_path = OUT / f"voice_{os.getpid()}.mp3"
            async def save_voice():
                communicate = edge_tts.Communicate(narration.strip(), VOICES[voice_label])
                await communicate.save(str(audio_path))
            asyncio.run(save_voice())
            final = OUT / f"motionmint_final_{os.getpid()}.mp4"
            mux = subprocess.run(
                [ffmpeg, "-y", "-i", str(output), "-i", str(audio_path),
                 "-c:v", "copy", "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(final)],
                capture_output=True, text=True
            )
            if mux.returncode == 0:
                output = final
        except Exception as e:
            raise gr.Error(f"Video was created, but voice generation failed: {e}")
    return str(output)

with gr.Blocks(theme=gr.themes.Soft(), title="MotionMint Studio") as demo:
    gr.Markdown("# 🎬 MotionMint Studio\nCreate animated videos from text or an image, with optional AI narration.")
    gr.Markdown("**Free starter version:** creates motion-graphic videos and animates uploaded pictures. It does not generate brand-new AI scenes like a dedicated text-to-video model.")
    with gr.Row():
        with gr.Column():
            prompt = gr.Textbox(label="Video prompt / on-screen text", lines=3, placeholder="A cinematic announcement about a night party...")
            image = gr.Image(label="Optional image (image-to-motion)", type="filepath")
            narration = gr.Textbox(label="Narration script (optional)", lines=3, placeholder="Type what you want the voice to say...")
            voice = gr.Dropdown(list(VOICES.keys()), value="English - Jenny (Female)", label="AI voice")
        with gr.Column():
            ratio = gr.Radio(["16:9 Landscape", "9:16 Portrait", "1:1 Square"], value="16:9 Landscape", label="Video format")
            duration = gr.Slider(5, 20, value=8, step=1, label="Duration (seconds)")
            effect = gr.Dropdown(["Slow zoom in", "Move left", "Move right", "Pulse", "Fade in"], value="Slow zoom in", label="Animation effect")
            create = gr.Button("✨ Create video", variant="primary")
            result = gr.Video(label="Your MotionMint video")
    create.click(make_video, inputs=[prompt, image, narration, voice, ratio, duration, effect], outputs=result)
    gr.Markdown("### Notes\n- No microphone is used; narration is generated from typed text.\n- Voice generation needs an internet connection and may be subject to service limits.\n- Free hosting may sleep when idle; video rendering is limited by available CPU and memory.")

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")))
