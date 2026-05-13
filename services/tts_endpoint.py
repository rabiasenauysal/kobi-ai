# ── Google Cloud TTS Endpoint ─────────────────────────────────────────
import os, json, base64
from google.cloud import texttospeech

def _setup_google_credentials():
    """
    Google credentials'ı hazırla.
    Öncelik sırası:
    1. GOOGLE_APPLICATION_CREDENTIALS env var zaten set → direkt kullan
    2. GOOGLE_CREDENTIALS_JSON env var içinde JSON string → dosyaya yaz
    3. Fallback: eski Windows path (local dev için)
    """
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return  # Zaten set, bir şey yapma

    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds_path = "/app/google_credentials.json"
        try:
            with open(creds_path, "w") as f:
                f.write(creds_json)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
            return
        except Exception as e:
            print(f"[TTS] Credentials yazma hatası: {e}")

    # Local dev fallback
    local_path = r"C:\Users\uysal\Documents\GitHub\promexi-rnd-tyfai1\gen-lang-client-0370570152-7ed922ca8b8e.json"
    if os.path.exists(local_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_path


@app.post("/api/tts")
async def text_to_speech(request: Request):
    try:
        body = await request.json()
        text = body.get("text", "").strip()
        if not text:
            return JSONResponse({"error": "Metin boş"}, status_code=400)
        if len(text) > 1000:
            text = text[:1000]

        _setup_google_credentials()

        client = texttospeech.TextToSpeechClient()

        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="tr-TR",
            name="tr-TR-Wavenet-A",
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=0.95,
        )

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )

        audio_b64 = base64.b64encode(response.audio_content).decode("utf-8")
        return JSONResponse({"audio_b64": audio_b64})

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)