def detect_audio_format(audio_bytes: bytes) -> tuple[str, str]:
    """Detects audio format from magic bytes and returns (extension, content_type)."""
    if audio_bytes.startswith(b'\x1a\x45\xdf\xa3'):
        return "webm", "audio/webm"
    elif audio_bytes.startswith(b'OggS'):
        return "ogg", "audio/ogg"
    # m4a / mp4 / aac
    elif len(audio_bytes) >= 8 and audio_bytes[4:8] == b'ftyp':
        return "m4a", "audio/m4a"
    elif audio_bytes.startswith(b'ID3') or audio_bytes.startswith(b'\xff\xfb'):
        return "mp3", "audio/mpeg"
    elif audio_bytes.startswith(b'RIFF') and len(audio_bytes) >= 12 and audio_bytes[8:12] == b'WAVE':
        return "wav", "audio/wav"
    else:
        # Default fallback
        return "webm", "audio/webm"
