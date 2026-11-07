# MotionMint Studio

A small Gradio web app that creates animated motion-graphic videos from text or adds camera movement to an uploaded image. Optional typed narration is converted to speech using Edge TTS.

## Important limitation
This starter does **not** create new photorealistic AI scenes from text or images. It creates procedural animated graphics and image-motion videos. Genuine generative text-to-video/image-to-video generally requires a separate model/API and substantial compute.

## Run locally
```bash
pip install -r requirements.txt
python app.py
```

## Deploy to Render
1. Push all files in this folder to a GitHub repository.
2. In Render choose **New +** → **Web Service**.
3. Connect GitHub and select `MotionMint-Studio`.
4. Runtime: Python.
5. Build command: `pip install -r requirements.txt`
6. Start command: `python app.py`
7. Choose Free instance and deploy.

Free Render services can sleep when idle and have limited CPU/RAM. Long videos may fail or take a while. Generated files are temporary on free instances.
