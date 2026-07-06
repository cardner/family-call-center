"""Minimal valid WAV bytes for audio-stream tests (44-byte silent header)."""


def _wav_bytes():
    return (
        b"RIFF"
        + (36).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")  # PCM
        + (1).to_bytes(2, "little")  # mono
        + (8000).to_bytes(4, "little")  # sample rate
        + (8000).to_bytes(4, "little")  # byte rate
        + (1).to_bytes(2, "little")  # block align
        + (8).to_bytes(2, "little")  # bits per sample
        + b"data"
        + (0).to_bytes(4, "little")  # no samples
    )


WAV_BYTES = _wav_bytes()
