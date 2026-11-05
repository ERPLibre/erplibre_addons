#!/usr/bin/env python3
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Synthesize the LinkUp sounds of static/src/audio.

Each sound is a sum of sine tones under an exponential decay, computed
here, with no recording or sample of any third party: the files are a
product of this script and share the licence of the module. They last
less than one second and peak at the same level (-3 dBFS), so that the
volumes of ``linkup_signals.js`` compare them fairly.

The script writes ``<name>.ogg`` (Vorbis) and ``<name>.mp3`` for each
sound, the two formats ``mail.sound_effects`` chooses between. It needs
``ffmpeg`` with ``libvorbis`` and ``libmp3lame``; metadata and encoder
tags are stripped, so that two runs give the same files.

Usage: python3 tools/generate_sounds.py [output directory]
"""

import math
import os
import struct
import subprocess
import sys
import tempfile
import wave

RATE = 44100
PEAK = 10 ** (-3 / 20)

# name: (duration in s, [(start s, frequency Hz, amplitude, decay s)])
SOUNDS = {
    # A short rising pair: the reflection leaves.
    "linkup_sent": (
        0.35,
        [(0.0, 880.0, 1.0, 0.08), (0.09, 1318.5, 0.9, 0.12)],
    ),
    # A soft falling pair: a reflection arrives.
    "linkup_received": (
        0.6,
        [(0.0, 1318.5, 0.8, 0.15), (0.14, 987.8, 1.0, 0.22)],
    ),
    # A rising arpeggio with a shimmer: a reflection is confirmed.
    "linkup_success": (
        0.8,
        [
            (0.0, 1046.5, 0.8, 0.12),
            (0.08, 1318.5, 0.8, 0.12),
            (0.16, 1568.0, 0.8, 0.14),
            (0.24, 2093.0, 1.0, 0.25),
            (0.24, 2637.0, 0.3, 0.2),
        ],
    ),
    # Three quick steps up: a reward.
    "linkup_yeah": (
        0.5,
        [
            (0.0, 784.0, 0.9, 0.06),
            (0.07, 987.8, 0.9, 0.06),
            (0.14, 1174.7, 1.0, 0.16),
        ],
    ),
    # A single bell with two partials: a highlight.
    "linkup_ting": (
        0.4,
        [(0.0, 1760.0, 1.0, 0.12), (0.0, 4400.0, 0.25, 0.05)],
    ),
}


def synthesize(duration, tones):
    """Return the samples of a sound, normalized to ``PEAK``.

    Each tone starts with a 5 ms attack, so that no click opens it, and
    the sound ends with a 20 ms fade out.
    """
    count = int(duration * RATE)
    samples = [0.0] * count
    for start, frequency, amplitude, decay in tones:
        first = int(start * RATE)
        for index in range(first, count):
            t = (index - first) / RATE
            attack = min(1.0, t / 0.005)
            samples[index] += (
                amplitude
                * attack
                * math.exp(-t / decay)
                * math.sin(2 * math.pi * frequency * t)
            )
    fade = int(0.02 * RATE)
    for index in range(fade):
        samples[count - 1 - index] *= index / fade
    peak = max(abs(sample) for sample in samples) or 1.0
    return [sample * PEAK / peak for sample in samples]


def write_wav(path, samples):
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(
            b"".join(
                struct.pack("<h", int(round(sample * 32767)))
                for sample in samples
            )
        )


def encode(wav, target, codec_args):
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-i",
            wav,
            "-map_metadata",
            "-1",
            "-fflags",
            "+bitexact",
            "-flags:a",
            "+bitexact",
            *codec_args,
            target,
        ],
        check=True,
    )


def main(directory):
    os.makedirs(directory, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, (duration, tones) in SOUNDS.items():
            wav = os.path.join(tmp, f"{name}.wav")
            write_wav(wav, synthesize(duration, tones))
            encode(
                wav,
                os.path.join(directory, f"{name}.ogg"),
                ["-c:a", "libvorbis", "-q:a", "4"],
            )
            encode(
                wav,
                os.path.join(directory, f"{name}.mp3"),
                ["-c:a", "libmp3lame", "-b:a", "96k", "-write_xing", "0"],
            )


if __name__ == "__main__":
    main(
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static",
            "src",
            "audio",
        )
    )
