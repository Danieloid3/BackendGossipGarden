import asyncio
import base64
from app.services.chat_service import chat_with_plant
import logging

logging.basicConfig(level=logging.INFO)

async def test_audio():
    plant_id = "30971c28-37e0-4c43-b083-2636d2c60153"
    user_id = "f9c11ced-2085-4acf-996f-7c2320703132"
    audio_path = "/home/lotus/Downloads/WhatsApp Ptt 2026-06-26 at 7.30.49 AM.ogg"
    transcription = "Hola plantita de la suerte eh te quería preguntar si había sentido mucho sol ayer porque te dejé justo como al lado de la ventana y no me di cuenta y no sé si te quemaste o como te sientes"
    
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    
    audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
    
    print("Enviando audio al chat...")
    try:
        response = await chat_with_plant(
            plant_id=plant_id,
            user_id=user_id,
            message=transcription,
            language="es",
            response_format="audio",
            user_audio_base64=audio_b64
        )
        print("====== RESPUESTA DEL LLM ======")
        print(response.reply)
        print("====== AUDIO DE LA PLANTA ======")
        print(response.audio_url)
        print("====== AUDIO GUARDADO DEL USUARIO ======")
        print(response.user_audio_url)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_audio())
