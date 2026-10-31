"""
coachia/voice_coach.py
======================
Módulo de síntesis de voz offline (TTS) usando SAPI5 de Windows
y captura de audio por micrófono (Speech Recognition) para debatir con Claude.
"""

import threading
import sys
import re

try:
    import win32com.client
    import pythoncom
    HAS_SAPI = True
except ImportError:
    HAS_SAPI = False

try:
    import speech_recognition as sr
    HAS_SPEECH_REC = True
except ImportError:
    HAS_SPEECH_REC = False

_current_speech_thread = None
_is_speaking = False


def clean_tts_text(text: str) -> str:
    """
    Limpia el texto antes de enviarlo al motor TTS.
    """
    if not text:
        return ""

    text = re.sub(r'\b1\.\s*', 'Primera alternativa: ', text)
    text = re.sub(r'\b2\.\s*', 'Segunda alternativa: ', text)
    text = re.sub(r'\b3\.\s*', 'Tercera alternativa: ', text)

    text = re.sub(r'[🔴🟡🟢🤼⚽👑⏱️•▶▼▲⭐🛡️⚔️🔄⚡⛽👀🧠🎯🔍❌✅⚫]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def _find_spanish_voice(speaker):
    try:
        voices = speaker.GetVoices()
        spanish_voice = None
        
        for v in voices:
            desc = v.GetDescription().lower()
            if "sabina" in desc or "mexico" in desc:
                return v
            elif ("spanish" in desc or "helena" in desc or "spain" in desc) and not spanish_voice:
                spanish_voice = v
                
        return spanish_voice
    except Exception as e:
        print(f"[VoiceCoach] Error buscando voces: {e}")
        return None


def _speak_worker(text: str):
    global _is_speaking
    if not HAS_SAPI:
        print("[VoiceCoach] SAPI5 / pythoncom no disponible.")
        return

    clean_text = clean_tts_text(text)
    
    print("=" * 60)
    print("[VoiceCoach] TEXTO ENVIADO AL MOTOR DE VOZ (TTS EN ESPAÑOL):")
    print(clean_text)
    print("=" * 60)

    try:
        pythoncom.CoInitialize()
        _is_speaking = True
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        
        sp_voice = _find_spanish_voice(speaker)
        if sp_voice:
            speaker.Voice = sp_voice

        speaker.Rate = 1
        speaker.Volume = 100
        
        speaker.Speak(clean_text)
    except Exception as e:
        print(f"[VoiceCoach] Error en reproducción de voz: {e}")
    finally:
        _is_speaking = False
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def speak_async(text: str):
    global _current_speech_thread
    if not text:
        return

    if _is_speaking:
        stop_speech()

    _current_speech_thread = threading.Thread(target=_speak_worker, args=(text,), daemon=True)
    _current_speech_thread.start()


def stop_speech():
    pass


def listen_mic_to_text(language: str = "es-ES", timeout: float = 6.0, phrase_time_limit: float = 8.0) -> str:
    """
    Escucha el micrófono del usuario usando SpeechRecognition y transcribe la voz a texto.
    """
    if not HAS_SPEECH_REC:
        raise RuntimeError("La librería 'speech_recognition' no está disponible. Ejecuta 'pip install SpeechRecognition pyaudio'.")

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True

    try:
        with sr.Microphone() as source:
            print("[VoiceCoach] Escuchando audio por el micrófono del usuario...")
            recognizer.adjust_for_ambient_noise(source, duration=0.6)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)

        print("[VoiceCoach] Procesando audio capturado con reconocimiento de voz...")
        text = recognizer.recognize_google(audio, language=language)
        print(f"[VoiceCoach] Transcripción capturada: '{text}'")
        return text.strip()

    except sr.WaitTimeoutError:
        raise TimeoutError("No se detectó voz en el micrófono dentro del tiempo de espera.")
    except sr.UnknownValueError:
        raise ValueError("No se pudo entender el audio capturado por el micrófono.")
    except sr.RequestError as re:
        raise RuntimeError(f"Error en el servicio de reconocimiento de voz: {re}")
    except Exception as e:
        raise RuntimeError(f"Fallo en captura de micrófono: {e}")
