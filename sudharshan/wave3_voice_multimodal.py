import math
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class HardenedWakeWordEngine:
    def __init__(self, sample_rate: int = 16000, vad_rms_threshold: float = 0.025, max_zcr: float = 0.35) -> None:
        self.sample_rate = sample_rate
        self.vad_rms_threshold = vad_rms_threshold
        self.max_zcr = max_zcr
        self.target_freqs = (300.0, 600.0, 1000.0, 1500.0, 2200.0, 3000.0, 4000.0, 5200.0)

    def vad_is_speech(self, samples: List[float]) -> bool:
        if not samples:
            return False
        rms = math.sqrt(sum(s * s for s in samples) / len(samples))
        if rms < self.vad_rms_threshold:
            return False
        crossings = sum(1 for i in range(1, len(samples)) if (samples[i - 1] >= 0) != (samples[i] >= 0))
        zcr = crossings / max(1, len(samples) - 1)
        return zcr <= self.max_zcr

    def goertzel_spectrum(self, samples: List[float]) -> List[float]:
        n = len(samples)
        if n == 0:
            return [0.0] * len(self.target_freqs)
        powers: List[float] = []
        for freq in self.target_freqs:
            k = int(0.5 + (n * freq) / self.sample_rate)
            omega = (2.0 * math.pi * k) / n
            coeff = 2.0 * math.cos(omega)
            q1 = q2 = 0.0
            for s in samples:
                q0 = coeff * q1 - q2 + s
                q2 = q1
                q1 = q0
            powers.append(round(q1 * q1 + q2 * q2 - q1 * q2 * coeff, 4))
        return powers

    def evaluate_frame(self, samples: List[float]) -> Dict[str, Any]:
        speech = self.vad_is_speech(samples)
        return {
            "vad_speech": speech,
            "spectrum": self.goertzel_spectrum(samples) if speech else [0.0] * len(self.target_freqs),
        }


class LocalWhisperSTT:
    def __init__(self, binary: str = "whisper-cli", model_path: str = "ggml-base.q5_1.bin") -> None:
        self.binary = binary
        self.model_path = model_path

    def build_command(self, audio_path: Path, language: str = "auto") -> List[str]:
        return [self.binary, "-m", self.model_path, "-l", language, "-f", str(audio_path), "--no-timestamps"]

    def transcribe(self, audio_path: Path, language: str = "auto") -> Dict[str, Any]:
        exe = shutil.which(self.binary)
        if not exe:
            return {"available": False, "text": "", "language": language, "detail": f"{self.binary} not installed"}
        cmd = [exe, "-m", self.model_path, "-l", language, "-f", str(audio_path), "--no-timestamps"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
        return {
            "available": True,
            "ok": proc.returncode == 0,
            "text": proc.stdout.strip(),
            "language": language,
        }


class LocalPiperTTS:
    VOICES = ("en_US-lessac-medium", "en_GB-alba-medium", "en_IN-kusal-medium")

    def __init__(self, voice: str = "en_US-lessac-medium") -> None:
        self.voice = voice if voice in self.VOICES else self.VOICES[0]
        self._interrupt_event = threading.Event()
        self.is_speaking = False

    def select_voice(self, voice: str) -> None:
        if voice not in self.VOICES:
            raise ValueError(f"Unsupported Piper voice: {voice}")
        self.voice = voice

    def barge_in_interrupt(self) -> None:
        self._interrupt_event.set()
        self.is_speaking = False

    def speak_chunks(self, text: str, sink: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        self._interrupt_event.clear()
        self.is_speaking = True
        spoken = []
        for sentence in re.split(r"(?<=[.!?])\s+", (text or "").strip()):
            if not sentence:
                continue
            if self._interrupt_event.is_set():
                return {"interrupted": True, "voice": self.voice, "spoken_chunks": spoken}
            if sink:
                sink(sentence)
            spoken.append(sentence)
        self.is_speaking = False
        return {"interrupted": False, "voice": self.voice, "spoken_chunks": spoken}


class VoiceConversationController:
    def __init__(self, ptt_hotkey: str = "Ctrl+Space") -> None:
        self.ptt_hotkey = ptt_hotkey
        self.mode = "push_to_talk"
        self.active = False

    def set_mode(self, mode: str) -> None:
        if mode not in ("push_to_talk", "hands_free"):
            raise ValueError("Mode must be 'push_to_talk' or 'hands_free'")
        self.mode = mode

    def trigger_ptt(self, pressed: bool) -> Dict[str, Any]:
        self.active = bool(pressed)
        return {"mode": self.mode, "hotkey": self.ptt_hotkey, "listening": self.active}


class ScreenshotPerceptionPipeline:
    @staticmethod
    def build_capture_command(platform_name: str, output_path: Path, region: Optional[str] = None) -> List[str]:
        p = platform_name.lower()
        if "linux" in p:
            cmd = ["grim"]
            if region:
                cmd.extend(["-g", region])
            cmd.append(str(output_path))
            return cmd
        if "darwin" in p:
            return ["screencapture", "-x", str(output_path)]
        return ["powershell", "-NoProfile", "-Command", f"Add-Type -AssemblyName System.Windows.Forms; '{output_path}'"]

    @staticmethod
    def route_perception_model(task: str = "vision") -> str:
        return "glm-ocr" if task.lower() == "ocr" else "qwen3.5:4b"


class LocalMeetingTranscriber:
    def __init__(self) -> None:
        self.segments: List[Dict[str, Any]] = []

    def add_segment(self, speaker: str, text: str, timestamp_sec: float = 0.0) -> None:
        self.segments.append({"speaker": speaker, "text": text.strip(), "ts": timestamp_sec})

    def summarize_action_items(self) -> Dict[str, Any]:
        action_items = []
        decisions = []
        for seg in self.segments:
            txt = seg["text"]
            low = txt.lower()
            if any(k in low for k in ("action:", "todo", "will ", "need to ", "follow up")):
                action_items.append(f"[{seg['speaker']}] {txt}")
            elif any(k in low for k in ("decided", "approved", "agreed", "ship ")):
                decisions.append(f"[{seg['speaker']}] {txt}")
        return {
            "segment_count": len(self.segments),
            "action_items": action_items,
            "decisions": decisions,
        }


class AudioWaveformVisualizer:
    @staticmethod
    def compute_bars(samples: List[float], num_bars: int = 16) -> List[float]:
        if not samples or num_bars <= 0:
            return [0.0] * max(0, num_bars)
        step = max(1, len(samples) // num_bars)
        bars = []
        for i in range(num_bars):
            chunk = samples[i * step:(i + 1) * step]
            if not chunk:
                bars.append(0.0)
            else:
                rms = math.sqrt(sum(s * s for s in chunk) / len(chunk))
                bars.append(round(min(1.0, rms * 2.5), 3))
        return bars


class OCRToClipboardPipeline:
    @staticmethod
    def clean_ocr_output(raw_text: str) -> str:
        lines = [ln.rstrip() for ln in (raw_text or "").splitlines()]
        return "\n".join(ln for ln in lines if ln.strip())

    def process(self, raw_text: str, clipboard_writer: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        cleaned = self.clean_ocr_output(raw_text)
        if clipboard_writer:
            clipboard_writer(cleaned)
        return {"chars": len(cleaned), "text": cleaned, "copied": clipboard_writer is not None}


class SpokenConfirmationGate:
    AFFIRMATIVE = {"confirm", "yes confirm", "approve", "proceed", "execute"}

    @classmethod
    def verify_spoken_response(cls, command_desc: str, spoken_reply: str) -> Dict[str, Any]:
        norm = re.sub(r"[^a-z ]", "", (spoken_reply or "").lower()).strip()
        approved = norm in cls.AFFIRMATIVE
        return {"command": command_desc, "spoken_reply": spoken_reply, "approved": approved}


class VoiceCommandMacroRegistry:
    def __init__(self) -> None:
        self._macros: Dict[str, List[Dict[str, Any]]] = {}

    def bind(self, phrase: str, steps: List[Dict[str, Any]]) -> None:
        key = (phrase or "").strip().lower()
        if not key or not steps:
            raise ValueError("Macro requires non-empty phrase and steps")
        self._macros[key] = list(steps)

    def resolve(self, transcript: str) -> Optional[List[Dict[str, Any]]]:
        key = (transcript or "").strip().lower()
        return self._macros.get(key)
