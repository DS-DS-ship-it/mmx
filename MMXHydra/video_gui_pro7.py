#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
video_gui_pro7.py — MMX HYDRA Player (Pro)

What’s improved vs prior versions:
- Stable cursor logic (no QScreen.cursor()) for autohide controls.
- Speed slider 0.25×–4.00× + presets that DO NOT reset timeline.
- Debounced timeline seeking (smooth scrub; no jump-back-to-start).
- Filter panel (Gamma, Sharpen, Contrast, Saturation, Brightness, Temperature, Hue, Invert).
- Save Video (video-only MP4) with filters applied.
- PYAV-first playback with OpenCV fallback; speed-aware pacing in both.
- Optional HYDRA encode/decode integration (auto-detect & safe-off if missing).
"""

from __future__ import annotations
import os, sys, math, time, subprocess, tempfile, shutil, threading, hashlib, struct, random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import cv2

# ---------- Optional backends ----------
try:
    import av
    HAVE_PYAV = True
except Exception:
    HAVE_PYAV = False

try:
    import sounddevice as sd
    HAVE_SD = True
except Exception:
    HAVE_SD = False

from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QEvent, QPointF, QRectF, QSize
)
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QPen, QBrush, QFont, QAction, QPolygonF, QCursor
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QFileDialog, QSlider, QPushButton,
    QMenuBar, QHBoxLayout, QVBoxLayout, QDockWidget
)

# ========================= HYDRA binary resolver =========================
def resolve_hydra_bin() -> Optional[str]:
    p = os.environ.get("HYDRA_BIN")
    if p and Path(p).exists():
        return str(Path(p).resolve())
    p = shutil.which("mmx-audio")
    if p:
        return p
    # common local build locations
    here = Path(__file__).resolve()
    candidates = [
        here.parent / "MMXHydra" / "target" / "release" / "mmx-audio",
        here.parent / ".." / "MMXHydra" / "target" / "release" / "mmx-audio",
        here.parent / "target" / "release" / "mmx-audio",
    ]
    for c in candidates:
        if c.exists():
            return str(c.resolve())
    return None

HYDRA_BIN = resolve_hydra_bin()
HYDRA_ENABLE = True
HYDRA_QUALITY = 0.98
HYDRA_FRAME   = "ms10"
HYDRA_KBPS    = 192
HYDRA_USE_MS  = False
HYDRA_USE_TR  = False
HYDRA_AUTO_SWAP_SNR_DB = 26.0

PREF_WAV_RATE = 48000
PREF_WAV_CH   = 2

SD_DEVICE = None
STREAM_BLOCKSIZE = 1024
STREAM_LATENCY = "high"

# ========================= Utils / probes =========================
def _have_hydra() -> bool:
    try:
        return HYDRA_ENABLE and HYDRA_BIN is not None and os.access(HYDRA_BIN, os.X_OK)
    except Exception:
        return False

def _safe_rm(p: Path):
    try: p.unlink(missing_ok=True)
    except Exception: pass

def _sha1(path: Path) -> str:
    try:
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1<<20), b""):
                h.update(chunk)
        return h.hexdigest()[:12]
    except Exception:
        return "?"

def _rms_db(x: np.ndarray, eps=1e-12) -> float:
    return 20.0 * math.log10(float(np.sqrt(np.mean(np.square(x), axis=0)).max()) + eps)

def _snr_db(ref: np.ndarray, test: np.ndarray, eps: float = 1e-9) -> float:
    n = min(ref.shape[0], test.shape[0])
    if n <= 0: return -120.0
    ref = ref[:n]; test = test[:n]
    err = ref - test
    p_sig = float(np.mean(ref**2) + eps)
    p_err = float(np.mean(err**2) + eps)
    return 10.0 * math.log10(p_sig / p_err)

def wav_has_audio(path: Path) -> bool:
    try:
        arr, _ = _read_wav_any(path)
        return arr.size > 0 and float(np.max(np.abs(arr))) > 0.0
    except Exception:
        return False

# ========================= High-quality resampler (fallback) =========================
def _design_sinc(taps: int, cutoff: float) -> np.ndarray:
    n = np.arange(taps) - (taps - 1) / 2.0
    sinc = np.sinc(2 * cutoff * n)
    win = np.blackman(taps)
    h = sinc * win
    h /= np.sum(h)
    return h.astype(np.float32)

def _resample_poly_sinc(x: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or x.size == 0:
        return x.astype(np.float32, copy=False)
    from math import gcd
    g = gcd(src_rate, dst_rate)
    L = dst_rate // g
    M = src_rate // g
    cutoff = 0.9 / max(L, M)
    taps = 64 * max(1, int(max(L, M)))
    h = _design_sinc(taps, cutoff)

    def upfirdn_1d(sig):
        up = np.zeros((sig.shape[0] * L,), dtype=np.float32)
        up[::L] = sig
        y = np.convolve(up, h, mode="full")
        delay = (taps - 1) // 2
        y = y[delay:delay + sig.shape[0]*L]
        y = y[::M]
        return y

    if x.ndim == 1:
        y = upfirdn_1d(x.astype(np.float32, copy=False))
        return y[:, None]
    else:
        cols = [upfirdn_1d(x[:, c].astype(np.float32, copy=False)) for c in range(x.shape[1])]
        n = min(map(len, cols))
        return np.stack([c[:n] for c in cols], axis=1)

# ========================= WAV reader (handles WAVE_FORMAT_EXTENSIBLE) =========================
KSDATAFORMAT_SUBTYPE_PCM   = (0x00000001, 0x0000, 0x0010, b'\x80\x00\x00\xaa\x00\x38\x9b\x71')
KSDATAFORMAT_SUBTYPE_IEEEF = (0x00000003, 0x0000, 0x0010, b'\x80\x00\x00\xaa\x00\x38\x9b\x71')

def _parse_guid(b: bytes):
    d1, d2, d3 = struct.unpack("<IHH", b[:8])
    d4 = b[8:]
    return (d1, d2, d3, d4)

def _read_wav_any(path: Path) -> Tuple[np.ndarray, int]:
    with open(path, "rb") as f:
        data = f.read()

    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Not a RIFF/WAVE file")

    pos = 12
    fmt = None
    data_off = None
    data_size = None

    while pos + 8 <= len(data):
        cid = data[pos:pos+4]
        size = struct.unpack("<I", data[pos+4:pos+8])[0]
        cpos = pos + 8
        if cid == b"fmt ":
            if size < 16: raise ValueError("bad fmt chunk")
            wFormatTag, nChannels, nSamplesPerSec, nAvgBytesPerSec, nBlockAlign, wBitsPerSample = struct.unpack("<HHIIHH", data[cpos:cpos+16])
            ext = {
                "wFormatTag": wFormatTag,
                "nChannels": nChannels,
                "nSamplesPerSec": nSamplesPerSec,
                "nAvgBytesPerSec": nAvgBytesPerSec,
                "nBlockAlign": nBlockAlign,
                "wBitsPerSample": wBitsPerSample,
                "validBitsPerSample": wBitsPerSample,
                "subformat": None
            }
            if size >= 18:
                cbSize = struct.unpack("<H", data[cpos+16:cpos+18])[0]
                if wFormatTag == 0xFFFE and size >= 40:  # WAVE_FORMAT_EXTENSIBLE
                    validBitsPerSample, channelMask = struct.unpack("<HI", data[cpos+18:cpos+24])
                    subformat = _parse_guid(data[cpos+24:cpos+40])
                    ext["validBitsPerSample"] = validBitsPerSample
                    ext["subformat"] = subformat
            fmt = ext
        elif cid == b"data":
            data_off = cpos
            data_size = size
        pos = cpos + ((size + 1) & ~1)  # word align

    if fmt is None or data_off is None or data_size is None:
        raise ValueError("missing fmt or data chunk")

    ch = fmt["nChannels"]
    rate = fmt["nSamplesPerSec"]
    bps = fmt["validBitsPerSample"]
    tag = fmt["wFormatTag"]
    sub = fmt["subformat"]

    print(f"[WAVEXT] tag=0x{tag:04x} ch={ch} rate={rate} bits={bps} sub={sub[0] if sub else None}")

    raw = memoryview(data)[data_off:data_off+data_size]
    if tag in (0x0001, 0xFFFE) and (sub is None or sub == KSDATAFORMAT_SUBTYPE_PCM):
        if bps == 16:
            arr = np.frombuffer(raw, dtype="<i2").reshape(-1, ch).astype(np.float32) / 32768.0
        elif bps == 24:
            b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, ch*3)
            out = np.empty((b.shape[0], ch), dtype=np.int32)
            for c in range(ch):
                s = b[:, 3*c:3*c+3]
                val = s[:,0].astype(np.int32) | (s[:,1].astype(np.int32) << 8) | (s[:,2].astype(np.int32) << 16)
                sign = (s[:,2] & 0x80) != 0
                val = val | (-(sign.astype(np.int32)) << 24)
                out[:, c] = val
            arr = (out.astype(np.float32) / (1<<23))
        elif bps == 32:
            arr_i = np.frombuffer(raw, dtype="<i4").reshape(-1, ch)
            arr = (arr_i.astype(np.float32) / (2**31))
        else:
            raise ValueError(f"unsupported PCM bits: {bps}")
    elif tag in (0x0003, 0xFFFE) and sub == KSDATAFORMAT_SUBTYPE_IEEEF:
        arr = np.frombuffer(raw, dtype="<f4").reshape(-1, ch)
    else:
        raise ValueError(f"unsupported WAV format tag 0x{tag:04x}")

    if not np.isfinite(arr).all():
        print("[WARN] NaN/Inf detected in WAV -> zeroing")
        arr[~np.isfinite(arr)] = 0.0
    print(f"[PROBE] WAV data: shape={arr.shape} min={arr.min():.3f} max={arr.max():.3f} rms={_rms_db(arr):.1f} dBFS")
    return np.ascontiguousarray(arr, dtype=np.float32), int(rate)

# ========================= Extraction =========================
def _afconvert_extract(src_video: str, dst_wav: Path, sr: int, ch: int) -> bool:
    try:
        cmd = ["afconvert", "-f", "WAVE", "-d", f"LEI16@{sr}", "-c", str(ch), src_video, str(dst_wav)]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if r.returncode == 0 and dst_wav.exists() and dst_wav.stat().st_size > 44:
            print("[EXTRACT] afconvert OK")
            return True
        print("[EXTRACT] afconvert failed:", r.stderr.strip() or r.stdout.strip())
        return False
    except FileNotFoundError:
        print("[EXTRACT] afconvert not found; will try PyAV.")
        return False
    except Exception as e:
        print("[EXTRACT] afconvert error:", e)
        return False

def _pyav_extract(src_video: str, dst_wav: Path, sr: int, ch: int) -> bool:
    if not HAVE_PYAV: return False
    try:
        ic = av.open(src_video)
        astream = next((s for s in ic.streams if s.type == "audio"), None)
        if astream is None:
            ic.close(); return False
        astream.thread_type = "AUTO"
        from av.audio.resampler import AudioResampler
        layout = "stereo" if ch == 2 else "mono"
        resampler = AudioResampler(format="s16", layout=layout, rate=sr)

        import wave, contextlib
        with contextlib.closing(wave.open(str(dst_wav), "wb")) as wf:
            wf.setnchannels(ch); wf.setsampwidth(2); wf.setframerate(sr)
            for pkt in ic.demux(astream):
                for frm in pkt.decode():
                    res = resampler.resample(frm)
                    frames = res if isinstance(res, (list, tuple)) else [res]
                    for r in frames:
                        if r is None: continue
                        try:
                            if hasattr(r, "format") and hasattr(r.format, "is_planar") and not r.format.is_planar:
                                wf.writeframes(bytes(r.planes[0])); continue
                        except Exception:
                            pass
                        try:
                            planes = [np.frombuffer(p, dtype=np.int16) for p in r.planes]
                            if len(planes) == 1:
                                wf.writeframes(planes[0].tobytes())
                            else:
                                n = min(map(len, planes))
                                if ch == 2 and len(planes) >= 2:
                                    inter = np.empty(n*2, dtype=np.int16)
                                    inter[0::2] = planes[0][:n]
                                    inter[1::2] = planes[1][:n]
                                    wf.writeframes(inter.tobytes())
                                else:
                                    mix = np.mean(np.stack([a[:n] for a in planes], axis=1), axis=1).astype(np.int16)
                                    wf.writeframes(mix.tobytes())
                        except Exception:
                            try: wf.writeframes(bytes(r.planes[0]))
                            except Exception: pass
        ic.close()
        print("[EXTRACT] PyAV OK")
        return True
    except Exception as e:
        print("[EXTRACT] PyAV error:", e)
        return False

def extract_audio_wav(src_video: str, dst_wav: Path, sr: int = PREF_WAV_RATE, ch: int = PREF_WAV_CH) -> bool:
    if _afconvert_extract(src_video, dst_wav, sr, ch):
        return True
    return _pyav_extract(src_video, dst_wav, sr, ch)

# ========================= HYDRA wrap =========================
def hydra_process_wav(in_wav: Path, out_wav: Path,
                      kbps: int = HYDRA_KBPS,
                      frame: str = HYDRA_FRAME,
                      quality: float = HYDRA_QUALITY,
                      use_ms: bool = HYDRA_USE_MS,
                      use_transient: bool = HYDRA_USE_TR) -> bool:
    if not _have_hydra(): return False
    mmxh = Path(tempfile.gettempdir()) / f"mmx_{int(time.time()*1000)}.mmxh"
    try:
        env = os.environ.copy()
        if not use_ms: env["HYDRA_NO_MS"] = "1"
        if not use_transient: env["HYDRA_NO_TRANSIENT"] = "1"

        cmd_enc = [
            HYDRA_BIN, "encode", str(in_wav), str(mmxh),
            "--mode","mdct-banded",
            "--sample-rate", str(PREF_WAV_RATE),
            "--channels", str(PREF_WAV_CH),
            "--frame", frame,
            "--quality", f"{quality:.3f}",
            "--kbps", str(kbps)
        ]
        subprocess.run(cmd_enc, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        print("[HYDRA] encode OK")

        cmd_dec = [HYDRA_BIN, "decode", str(mmxh), str(out_wav)]
        subprocess.run(cmd_dec, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print("[HYDRA] decode OK")

        ok = wav_has_audio(out_wav)
        print(f"[HYDRA] out exists={out_wav.exists()} has_audio={ok} sha1={_sha1(out_wav)}")
        return ok
    except subprocess.CalledProcessError as e:
        print("[HYDRA] fail:", e.stderr or e.stdout)
        return False
    except Exception as e:
        print("[HYDRA] err:", e)
        return False
    finally:
        _safe_rm(mmxh)

# ========================= Filters =========================
@dataclass
class FX:
    gamma: float = 1.0
    sharpen: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    brightness: int = 0
    temperature: int = 0
    hue: int = 0
    invert: bool = False

def _apply_filters_bgr(frame_bgr: np.ndarray, fx: FX) -> np.ndarray:
    f = frame_bgr
    # contrast + brightness
    if abs(fx.contrast - 1.0) > 1e-6 or fx.brightness != 0:
        f = cv2.convertScaleAbs(f, alpha=float(fx.contrast), beta=int(fx.brightness))
    # HSV (sat + hue)
    if abs(fx.saturation - 1.0) > 1e-6 or fx.hue != 0:
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV).astype(np.float32)
        if fx.hue != 0:
            hsv[..., 0] = (hsv[..., 0] + fx.hue/2.0) % 180.0
        if abs(fx.saturation - 1.0) > 1e-6:
            hsv[..., 1] *= float(fx.saturation)
        hsv = np.clip(hsv, [0,0,0], [180,255,255])
        f = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    # temperature
    if fx.temperature != 0:
        b,g,r = cv2.split(f)
        t = abs(int(fx.temperature))
        if fx.temperature > 0:
            r = cv2.add(r, t); b = cv2.subtract(b, t)
        else:
            b = cv2.add(b, t); r = cv2.subtract(r, t)
        f = cv2.merge([b,g,r])
    # gamma
    if abs(fx.gamma - 1.0) > 1e-3:
        invG = 1.0/float(fx.gamma)
        lut = (np.clip(((np.arange(256)/255.0)**invG)*255.0+0.5, 0, 255)).astype(np.uint8)
        f = cv2.LUT(f, lut)
    # sharpen
    if fx.sharpen > 1e-3:
        blur = cv2.GaussianBlur(f, (0,0), 1.0)
        f = cv2.addWeighted(f, 1.0+fx.sharpen, blur, -fx.sharpen, 0)
    # invert
    if fx.invert:
        f = cv2.bitwise_not(f)
    return f

# ----------------------------- Filter Panel (dock) ---------------------------
class HexBackground(QWidget):
    """Morphing hex-grid background. Call .pulse() on interaction."""
    def __init__(self, parent=None, grid=42):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.grid = grid
        self.r = grid * 0.58
        self.phase = 0.0
        self.intensity = 0.0
        self.particles = []
        self._seed_particles()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)  # ~30fps

    def _seed_particles(self):
        self.particles.clear()
        for _ in range(120):
            self.particles.append({
                "pos": QPointF(random.random(), random.random()),
                "vel": QPointF((random.random()-0.5)*0.002, (random.random()-0.5)*0.002),
                "life": random.randint(90, 260),
            })

    def pulse(self, amount=0.35):
        self.intensity = min(1.0, self.intensity + amount)

    def sizeHint(self):
        return QSize(1280, 720)

    def _tick(self):
        self.phase += 0.015
        self.intensity *= 0.96
        for p in self.particles:
            p["pos"] += p["vel"]
            if p["pos"].x() < 0 or p["pos"].x() > 1: p["vel"].setX(-p["vel"].x())
            if p["pos"].y() < 0 or p["pos"].y() > 1: p["vel"].setY(-p["vel"].y())
            p["life"] -= 1
            if p["life"] <= 0:
                p["pos"] = QPointF(random.random(), random.random())
                p["vel"] = QPointF((random.random()-0.5)*0.002, (random.random()-0.5)*0.002)
                p["life"] = random.randint(90, 260)
        self.update()

    def _hex_points(self, cx, cy, r):
        pts = []
        for i in range(6):
            ang = math.radians(60*i + 30)  # flat-top hex
            pts.append(QPointF(cx + r*math.cos(ang), cy + r*math.sin(ang)))
        return QPolygonF(pts)

    def paintEvent(self, ev):
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        p.fillRect(self.rect(), QColor(12, 12, 12))
        p.fillRect(self.rect(), QBrush(QColor(255, 255, 255, 14)))

        glow = np.zeros((max(1, h//3), max(1, w//3)), dtype=np.float32)
        for pp in self.particles:
            px = int(pp["pos"].x() * (glow.shape[1]-1))
            py = int(pp["pos"].y() * (glow.shape[0]-1))
            if 0 <= px < glow.shape[1] and 0 <= py < glow.shape[0]:
                glow[py, px] += 1.0
        if glow.size:
            glow = cv2.GaussianBlur(glow, (0,0), 4.0)
            glow = glow / (glow.max() + 1e-5)

        spacing = self.grid
        r = self.r
        row_h = r * math.sin(math.radians(60)) * 2
        col_w = r * 1.5

        base_alpha = 40
        wiggle = 0.6 + 0.4*math.sin(self.phase*1.4)
        pulse = self.intensity

        y = r
        row = 0
        while y < h + r:
            xoff = (0 if row % 2 == 0 else col_w)
            x = r + xoff
            while x < w + r:
                gx = int(min(glow.shape[1]-1, max(0, int(x / w * (glow.shape[1]-1)))))
                gy = int(min(glow.shape[0]-1, max(0, int(y / h * (glow.shape[0]-1)))))
                g = float(glow[gy, gx]) if glow.size else 0.0

                scale = 1.0 + 0.07*math.sin(self.phase + x*0.01 + y*0.012) + 0.15*pulse + 0.22*g*wiggle
                rr = r * scale

                poly = self._hex_points(x, y, rr)

                p.setBrush(QColor(255,255,255, int(10 + 70*(g*pulse))))
                alp = int(base_alpha + 120*g + 60*pulse)
                pen = QPen(QColor(255,255,255, max(20, min(200, alp))))
                pen.setWidthF(1.0)
                p.setPen(pen)

                p.drawPolygon(poly)
                x += spacing + col_w
            y += row_h
            row += 1

        # soft edge vignette
        p.setBrush(QColor(0, 0, 0, 150))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(0, 0, w, h), 8, 8)

class FilterPanel(QDockWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("🎛 Filters", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)

        self.bg = HexBackground(grid=30)
        self.bg.setMinimumWidth(280)

        panel = QWidget()
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setStyleSheet("background: rgba(10,10,10,160);")

        grid = QVBoxLayout(panel)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setSpacing(10)
        self.sliders = {}

        def add_slider(title, mn, mx, val, step=1, suffix=""):
            lab = QLabel(f"{title}: {val}{suffix}")
            lab.setStyleSheet("color:#ddd;")
            s = QSlider(Qt.Orientation.Horizontal)
            s.setMinimum(mn); s.setMaximum(mx); s.setValue(val); s.setSingleStep(step)
            s.valueChanged.connect(lambda v, L=lab, T=title: L.setText(f"{T}: {v}{suffix}"))
            s.valueChanged.connect(lambda _: self.changed.emit())
            grid.addWidget(lab); grid.addWidget(s)
            self.sliders[title] = s

        add_slider("Gamma",       50, 250, 100, suffix="%")   # 0.50..2.50
        add_slider("Sharpen",       0, 300,   0)              # 0..3.0
        add_slider("Contrast",     50, 300, 100, suffix="%")  # 0.5..3.0
        add_slider("Saturation",    0, 300, 100, suffix="%")  # 0..3.0
        add_slider("Brightness", -100, 100,   0)              # beta
        add_slider("Temperature",-100, 100,   0)
        add_slider("Hue",        -180, 180,   0, step=2)
        add_slider("Invert",        0,   1,   0)

        btn_reset = QPushButton("Reset FX")
        btn_reset.clicked.connect(self.reset)
        grid.addWidget(btn_reset)

        host = QWidget()
        stack = QVBoxLayout(host)
        stack.setContentsMargins(0,0,0,0)
        stack.addWidget(self.bg)
        stack.addWidget(panel, 0, Qt.AlignmentFlag.AlignTop)
        self.setWidget(host)

    def value_dict(self):
        S = self.sliders
        return {
            "gamma":       max(0.5, min(2.5, S["Gamma"].value()/100.0)),
            "sharpen":     S["Sharpen"].value()/100.0*3.0,
            "contrast":    S["Contrast"].value()/100.0,
            "saturation":  S["Saturation"].value()/100.0,
            "brightness":  S["Brightness"].value(),
            "temperature": S["Temperature"].value(),
            "hue":         S["Hue"].value(),
            "invert":      bool(S["Invert"].value()),
        }

    def reset(self):
        defaults = {
            "Gamma":100, "Sharpen":0, "Contrast":100, "Saturation":100,
            "Brightness":0, "Temperature":0, "Hue":0, "Invert":0
        }
        for k, s in self.sliders.items():
            s.blockSignals(True); s.setValue(defaults[k]); s.blockSignals(False)
        self.changed.emit()
        self.bg.pulse(0.6)

# ========================= Audio Streamer (speed-aware) =========================
class StreamPlayer:
    """
    Writes audio chunks to sounddevice at a fixed samplerate,
    and advances through the source at a fractional step = speed.
    Speed changes do NOT restart playback (no position reset).
    """
    def __init__(self, tag: str):
        self.tag = tag
        self.arr: Optional[np.ndarray] = None      # float32, shape (N, C)
        self.rate: Optional[int] = None            # source rate
        self.stream = None
        self.thread: Optional[threading.Thread] = None
        self.stop_flag = False

        self.lock = threading.Lock()
        self.out_rate: Optional[int] = None        # device rate
        self.vpos = 0.0                            # fractional frame index
        self.speed = 1.0                           # 0.25 .. 4.0

    def set_speed(self, s: float):
        s = max(0.25, min(4.0, float(s)))
        with self.lock:
            self.speed = s

    def load(self, wav_path: Path):
        arr, rate = _read_wav_any(wav_path)
        if arr.ndim == 1:
            arr = arr[:, None]
        peak = float(np.max(np.abs(arr))) if arr.size else 0.0
        if peak > 1.5:
            arr = np.clip(arr, -1.0, 1.0)
        self.arr = np.ascontiguousarray(arr, dtype=np.float32)
        self.rate = int(rate)
        self.vpos = 0.0
        print(f"[{self.tag}] load ok: shape={self.arr.shape} rate={self.rate} peak={float(np.abs(self.arr).max()):.3f} rms={_rms_db(self.arr):.1f} dBFS")

    def _open_stream(self, samplerate: int) -> bool:
        if not HAVE_SD:
            print(f"[{self.tag}] sounddevice missing — audio disabled")
            return False
        try:
            sd.check_output_settings(device=SD_DEVICE, samplerate=samplerate, channels=self.arr.shape[1], dtype='float32')
        except Exception as e:
            print(f"[{self.tag}] check_output_settings({samplerate}) ->", e)
            return False
        try:
            self.stream = sd.OutputStream(
                device=SD_DEVICE,
                samplerate=samplerate,
                channels=self.arr.shape[1],
                dtype='float32',
                latency=STREAM_LATENCY,
                blocksize=STREAM_BLOCKSIZE,
            )
            self.stream.start()
            self.out_rate = samplerate
            print(f"[{self.tag}] stream started @ {samplerate} Hz ch={self.arr.shape[1]}")
            return True
        except Exception as e:
            print(f"[{self.tag}] OutputStream({samplerate}) error:", e)
            return False

    def _interp_chunk(self, nframes: int) -> np.ndarray:
        N = self.arr.shape[0]
        C = self.arr.shape[1]
        with self.lock:
            step = float(self.speed)
            start = float(self.vpos)
            idx = start + step * np.arange(nframes, dtype=np.float32)
            i0 = np.clip(np.floor(idx).astype(np.int64), 0, max(0, N-2))
            frac = (idx - i0).astype(np.float32)
            i1 = i0 + 1
            a0 = self.arr[i0]
            a1 = self.arr[i1]
            chunk = (a0 * (1.0 - frac)[:, None]) + (a1 * frac[:, None])
            self.vpos = float(idx[-1] + step)
        end_idx = int(min(N, math.ceil(self.vpos)))
        if end_idx >= N - 1 and chunk.shape[0] > (N - int(start)):
            need = chunk.shape[0]
            have = max(0, N - int(start))
            if need > have:
                pad = np.zeros((need - have, C), dtype=np.float32)
                chunk = np.vstack([chunk[:have], pad])
        return chunk.astype(np.float32, copy=False)

    def _feeder(self):
        try:
            bs = STREAM_BLOCKSIZE
            while not self.stop_flag:
                if self.arr is None:
                    time.sleep(0.01); continue
                if self.vpos >= (self.arr.shape[0] - 1):
                    break
                chunk = self._interp_chunk(bs)
                if self.stream:
                    self.stream.write(chunk)
                else:
                    time.sleep(bs / float(self.out_rate or 48000))
            try:
                if self.stream:
                    self.stream.stop(); self.stream.close()
            except Exception:
                pass
            self.stream = None
        except Exception as e:
            print(f"[{self.tag}] feeder error:", e)
            try:
                if self.stream:
                    self.stream.abort(); self.stream.close()
            except Exception:
                pass
            self.stream = None

    def play_from_ms(self, ms: int = 0):
        if self.arr is None:
            print(f"[{self.tag}] no audio loaded")
            return
        self.stop()
        # prefer native rate
        ok_stream = self._open_stream(self.rate)
        if not ok_stream:
            # resample once to device default
            dev_rate = 44100
            if HAVE_SD:
                try:
                    dev = sd.query_devices(SD_DEVICE, 'output') if SD_DEVICE is not None else sd.query_devices(None, 'output')
                    dev_rate = int(dev['default_samplerate']) if dev.get('default_samplerate') else 44100
                except Exception:
                    pass
            if self.rate != dev_rate:
                print(f"[{self.tag}] resampling (polyphase) {self.rate} -> {dev_rate}")
                y = _resample_poly_sinc(self.arr, self.rate, dev_rate)
                self.arr = np.ascontiguousarray(y, dtype=np.float32)
                self.rate = dev_rate
            self.out_rate = self.rate

        with self.lock:
            self.out_rate = self.rate
            self.vpos = float(self.out_rate * (ms/1000.0))
            self.vpos = max(0.0, min(float(self.arr.shape[0]-1), self.vpos))
        self.stop_flag = False
        self.thread = threading.Thread(target=self._feeder, daemon=True)
        self.thread.start()
        print(f"[{self.tag}] play @ {ms} ms  out_rate={self.out_rate}  vpos={self.vpos:.1f}  speed={self.speed:.2f}×")

    def seek_ms(self, ms: int):
        if self.arr is None:
            return
        with self.lock:
            self.vpos = float(self.out_rate * (ms/1000.0))
            self.vpos = max(0.0, min(float(self.arr.shape[0]-1), self.vpos))
        print(f"[{self.tag}] seek -> {ms} ms (vpos {self.vpos:.1f})")

    def stop(self):
        self.stop_flag = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.5)
        self.thread = None
        if self.stream:
            try: self.stream.abort(); self.stream.close()
            except Exception: pass
            self.stream = None

# ========================= Video worker (speed-aware, no seek on speed change) =========================
class VideoWorker(QThread):
    frameReady = pyqtSignal(QImage, int)
    metaReady  = pyqtSignal(int, int, float, int)
    ended      = pyqtSignal()

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.loop = False
        self.speed = 1.0
        self.fx = FX()
        self._running = True
        self._seek_to_frame: Optional[int] = None
        self._resync = False

    def stop(self): self._running = False
    def set_loop(self, v: bool): self.loop = v
    def set_speed(self, s: float):
        self.speed = max(0.25, min(4.0, float(s)))
        self._resync = True  # re-time without seeking
    def set_fx(self, fx: FX): self.fx = fx
    def seek(self, frame_index: int): self._seek_to_frame = max(0, int(frame_index))

    def _emit_frame(self, frame_bgr, pos_frame):
        h,w,_ = frame_bgr.shape
        qimg = QImage(frame_bgr.data, w, h, w*3, QImage.Format.Format_BGR888).copy()
        self.frameReady.emit(qimg, int(pos_frame))

    def run(self):
        if HAVE_PYAV:
            try: self._run_pyav(); return
            except Exception: pass
        self._run_opencv()

    def _run_pyav(self):
        container = av.open(self.path)
        vstream = next((s for s in container.streams if s.type == 'video'), None)
        if vstream is None:
            container.close(); self._run_opencv(); return
        vstream.thread_type = "AUTO"
        if vstream.average_rate: fps = float(vstream.average_rate)
        elif getattr(vstream, "base_rate", None): fps = float(vstream.base_rate)
        else: fps = 30.0
        if getattr(vstream, "frames", 0): total_frames = int(vstream.frames)
        elif getattr(container, "duration", None) and fps>0 and vstream.time_base:
            dur_s = float(container.duration) / 1e6
            total_frames = max(1, int(round(dur_s * fps)))
        else: total_frames = 0
        w = vstream.codec_context.width; h = vstream.codec_context.height
        self.metaReady.emit(w, h, fps, max(1, total_frames))
        tb = vstream.time_base; clock_start = None; start_pts = None
        max_lag = 1.0 / max(10.0, fps); target_after_seek = None

        def do_seek_frame(fidx: int):
            nonlocal start_pts, clock_start, target_after_seek
            sec = fidx / max(1e-9, fps); ts = int(sec / float(tb))
            container.seek(ts, stream=vstream, any_frame=False, backward=True)
            target_after_seek = int(fidx); start_pts = None; clock_start = None

        for packet in container.demux(vstream):
            if not self._running: break
            if self._seek_to_frame is not None:
                do_seek_frame(self._seek_to_frame); self._seek_to_frame = None; continue
            for frame in packet.decode():
                if not self._running: break
                if start_pts is None:
                    start_pts = frame.pts or 0; clock_start = time.perf_counter()
                pts_s = ((frame.pts or start_pts) - start_pts) * tb
                pos_frame = int(round(float(pts_s) * fps))
                if target_after_seek is not None and pos_frame < target_after_seek: continue
                target_after_seek = None
                if self._resync:
                    clock_start = time.perf_counter() - (pts_s / max(0.25, self.speed))
                    self._resync = False
                target = clock_start + (pts_s / max(0.25, self.speed))
                now = time.perf_counter()
                if now - target > max_lag:
                    continue
                sleep = target - now
                if sleep > 0: time.sleep(min(0.012, sleep))
                img = frame.to_ndarray(format="bgr24")
                img = _apply_filters_bgr(img, self.fx)
                self._emit_frame(img, pos_frame)

        if self.loop and self._running:
            container.close(); self._run_pyav(); return
        container.close(); self.ended.emit()

    def _run_opencv(self):
        cap = cv2.VideoCapture(self.path)
        if not cap.isOpened(): self.ended.emit(); return
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        self.metaReady.emit(w, h, fps, max(1, total_frames))
        base_dt = 1.0 / fps; start = time.perf_counter(); frames_out = 0; max_lag = base_dt

        def do_seek_frame(fidx: int):
            nonlocal start, frames_out
            cap.set(cv2.CAP_PROP_POS_FRAMES, float(max(0, fidx))); start = time.perf_counter(); frames_out = 0

        while True and self._running:
            if self._seek_to_frame is not None:
                do_seek_frame(self._seek_to_frame); self._seek_to_frame = None
            ok, frame = cap.read()
            if not ok:
                if self.loop: do_seek_frame(0); continue
                break
            if self._resync:
                start = time.perf_counter() - (frames_out * base_dt) / max(0.25, self.speed)
                self._resync = False
            pos_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
            if pos_frame <= 0: pos_frame = frames_out
            frame = _apply_filters_bgr(frame, self.fx)
            self._emit_frame(frame, pos_frame); frames_out += 1
            target = start + (frames_out * base_dt) / max(0.25, self.speed)
            now = time.perf_counter(); dt = target - now
            if dt > 0: time.sleep(min(0.012, dt))
            elif -dt > max_lag: cap.grab()
        cap.release(); self.ended.emit()

# ========================= UI bits =========================
class JumpSlider(QSlider):
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.orientation() == Qt.Orientation.Horizontal:
            x = ev.position().x(); w = max(1.0, self.width()-1.0)
            vmin, vmax = self.minimum(), self.maximum()
            val = int(round(vmin + (vmax - vmin) * (x / w)))
            self.setValue(max(vmin, min(vmax, val)))
            self.sliderMoved.emit(self.value())
            self.sliderPressed.emit()
            ev.accept()
            return
        super().mousePressEvent(ev)

# ========================= Main Player =========================
class VideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MMX HYDRA Player — Pro")
        self.resize(1280, 840)
        self.setMouseTracking(True)

        self.bg = HexBackground(grid=46)
        self.setCentralWidget(self.bg)

        self.video_label = QLabel(self.bg)
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background: black;")

        self.brand = QLabel("Aurora • Quasar", self.bg)
        self.brand.setStyleSheet("color: rgba(255,255,255,220); background: rgba(0,0,0,90); padding: 6px 12px; border-radius: 10px;")
        f = QFont("Snell Roundhand", 22)
        if not f.exactMatch(): f = QFont("Brush Script MT", 22)
        self.brand.setFont(f)

        # Timeline (blue fill)
        self.timeline = JumpSlider(Qt.Orientation.Horizontal, self)
        self.timeline.setRange(0, 1); self.timeline.setEnabled(False)
        self.timeline.setCursor(Qt.CursorShape.PointingHandCursor)
        self.timeline.setStyleSheet("""
            QSlider::groove:horizontal { height:8px; background: transparent; border-radius:4px; }
            QSlider::sub-page:horizontal { background: #1e88ff; border-radius:4px; }
            QSlider::add-page:horizontal { background: rgba(255,255,255,0.22); border-radius:4px; }
            QSlider::handle:horizontal { width:16px; height:16px; margin:-6px 0; border-radius:8px; background: #ffffff; }
        """)

        # Controls
        self.controls = QWidget(self.bg)
        self.controls.setStyleSheet("""
            QWidget { background: rgba(0,0,0,160); border-radius: 10px; color: #eee; }
            QLabel  { color: #eee; }
            QPushButton { color:#fff; background: rgba(255,255,255,0.18); padding:6px 10px; border-radius:6px; border:none; }
            QPushButton:checked { background: rgba(255,255,255,0.75); color:#111; }
            QSlider::groove:horizontal { height:6px; background: rgba(255,255,255,0.35); border-radius:3px; }
            QSlider::handle:horizontal { width:14px; background: #fff; margin:-5px 0; border-radius:7px; }
        """)
        vbox = QVBoxLayout(self.controls); vbox.setContentsMargins(10,10,10,10); vbox.setSpacing(8)

        # Row 1: transport
        row1 = QHBoxLayout(); row1.setSpacing(8)
        self.btn_open = QPushButton("Open"); row1.addWidget(self.btn_open)
        self.btn_play = QPushButton("Play"); row1.addWidget(self.btn_play)
        self.btn_loop = QPushButton("Loop OFF"); self.btn_loop.setCheckable(True); row1.addWidget(self.btn_loop)
        self.btn_save = QPushButton("Save Video"); row1.addWidget(self.btn_save)
        self.lbl_mode = QLabel("Audio: RAW"); row1.addWidget(self.lbl_mode, 1)
        vbox.addLayout(row1)

        # Row 2: Speed presets + slider
        row2 = QHBoxLayout(); row2.setSpacing(6)
        self.speed_label = QLabel("Speed: 1.00×"); row2.addWidget(self.speed_label)
        for s in (0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0):
            b = QPushButton(f"{s}×")
            b.clicked.connect(lambda _, v=s: self._set_speed(v, update_slider=True))
            row2.addWidget(b)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(25); self.speed_slider.setMaximum(400)
        self.speed_slider.setSingleStep(5); self.speed_slider.setPageStep(25)
        self.speed_slider.setValue(100)
        self.speed_slider.valueChanged.connect(lambda v: self._set_speed(v/100.0, update_slider=False))
        row2.addWidget(self.speed_slider, 1)
        vbox.addLayout(row2)

        # Menu + Dock (Filters)
        menubar = QMenuBar(self); self.setMenuBar(menubar)
        m_fx = menubar.addMenu("Filters")
        act_show = QAction("Show Filter Panel", self); m_fx.addAction(act_show)
        act_hide = QAction("Hide Filter Panel", self); m_fx.addAction(act_hide)
        m_view = menubar.addMenu("View")
        act_full = QAction("Toggle Fullscreen", self); m_view.addAction(act_full)
        act_show.triggered.connect(self._show_filters)
        act_hide.triggered.connect(self._hide_filters)
        act_full.triggered.connect(self._toggle_fullscreen)

        self.filters_dock = FilterPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.filters_dock)
        self.filters_dock.hide()
        self.filters_dock.changed.connect(self._on_filters_changed)

        # State
        self.vworker: Optional[VideoWorker] = None
        self.path: Optional[str] = None
        self._fps = 30.0
        self._total_frames = 1
        self._last_input_time = time.time()
        self._seeking = False
        self._fill_expand = False
        self.speed = 1.0

        # Tmp audio files
        self.tmpdir = Path(tempfile.mkdtemp(prefix="mmx_player_hydra_"))
        self.src_wav = self.tmpdir / "in.wav"
        self.hyd_wav = self.tmpdir / "out_hydra.wav"

        self.raw = StreamPlayer("RAW")
        self.hyd = StreamPlayer("HYD")
        self.mode = "raw"

        # Wire signals
        self.btn_open.clicked.connect(self._open)
        self.btn_play.clicked.connect(self._play_pause)
        self.btn_loop.toggled.connect(self._loop_toggled)
        self.btn_save.clicked.connect(self._save_video)

        # Debounced timeline seeking
        self.timeline.sliderPressed.connect(self._seek_pressed)
        self.timeline.sliderMoved.connect(self._queue_seek)       # debounced
        self.timeline.sliderReleased.connect(self._seek_release)

        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.timeout.connect(self._do_seek)
        self._pending_seek: Optional[int] = None

        self.short_raw = QAction(self); self.short_raw.setShortcut("R"); self.short_raw.triggered.connect(self._force_raw)
        self.short_hyd = QAction(self); self.short_hyd.setShortcut("H"); self.short_hyd.triggered.connect(self._force_hydra)
        self.addAction(self.short_raw); self.addAction(self.short_hyd)

        # Speed shortcuts
        self.short_slow = QAction(self); self.short_slow.setShortcut("["); self.short_slow.triggered.connect(lambda: self._step_speed(1/1.25))
        self.short_fast = QAction(self); self.short_fast.setShortcut("]"); self.short_fast.triggered.connect(lambda: self._step_speed(1.25))
        self.addAction(self.short_slow); self.addAction(self.short_fast)

        self._layout_t = QTimer(self); self._layout_t.timeout.connect(self._layout); self._layout_t.start(33)
        self._autohide_t = QTimer(self); self._autohide_t.timeout.connect(self._maybe_hide_controls); self._autohide_t.start(150)

        self.video_label.raise_(); self.controls.raise_(); self.brand.raise_(); self.timeline.raise_()
        QApplication.instance().installEventFilter(self)

        print("MMX HYDRA Player — Pro")
        if HAVE_SD:
            try:
                info = sd.query_devices(SD_DEVICE, 'output') if SD_DEVICE is not None else sd.query_devices(None, 'output')
                print(f"[AUDIO] Output device: {info['name']} @ {info.get('default_samplerate','?')} Hz")
            except Exception as e:
                print("[AUDIO] Device query error:", e)

    # ---------- layout / events ----------
    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel, QEvent.Type.KeyPress):
            self._bump_activity(); self.controls.show()
        return super().eventFilter(obj, ev)

    def _layout(self):
        w, h = self.width(), self.height()
        top = self.menuBar().height() if not self.isFullScreen() else 0
        margin = 12 if not self.isFullScreen() else 0
        self.brand.setVisible(not self.isFullScreen())
        if self.brand.isVisible():
            self.brand.adjustSize()
            self.brand.move((w-self.brand.width())//2, top + margin)
        vy = top + (margin*2 + (self.brand.height() if self.brand.isVisible() else 0))
        self.video_label.setGeometry(margin, vy, w - margin*2, h - vy - margin - 28)
        self.timeline.setGeometry(8, h - 20, w - 16, 12)
        cw, ch = min(880, w-40), 118
        self.controls.setGeometry((w-cw)//2, h - ch - 36, cw, ch)
        self.video_label.raise_(); self.controls.raise_(); self.brand.raise_(); self.timeline.raise_()

    def _maybe_hide_controls(self):
        try:
            y = self.mapFromGlobal(QCursor.pos()).y()
        except Exception:
            y = self.height()
        bottom_zone = self.height() - 200
        recently_active = (time.time() - self._last_input_time) < 8.0
        keep_visible = self._seeking or not self.path or recently_active or (y >= bottom_zone)
        self.controls.setVisible(keep_visible)

    def _bump_activity(self): self._last_input_time = time.time()
    def mouseMoveEvent(self, ev): self._bump_activity()
    def keyPressEvent(self, ev):
        self._bump_activity()
        if ev.key() == Qt.Key.Key_Space: self._play_pause()
        elif ev.key() == Qt.Key.Key_F: self._toggle_fullscreen()

    # ---------- speed control ----------
    def _apply_speed(self):
        self.speed_label.setText(f"Speed: {self.speed:.2f}×")
        if self.vworker: self.vworker.set_speed(self.speed)  # re-time clock, no seek
        self.raw.set_speed(self.speed)
        self.hyd.set_speed(self.speed)

    def _set_speed(self, s: float, update_slider: bool):
        self.speed = max(0.25, min(4.0, float(s)))
        if update_slider:
            self.speed_slider.blockSignals(True)
            self.speed_slider.setValue(int(round(self.speed * 100)))
            self.speed_slider.blockSignals(False)
        self._apply_speed()
        self.bg.pulse(0.12)

    def _step_speed(self, factor: float):
        self._set_speed(self.speed * factor, update_slider=True)

    # ---------- filters ----------
    def _on_filters_changed(self):
        vd = self.filters_dock.value_dict()
        fx = FX(
            gamma=vd["gamma"], sharpen=vd["sharpen"], contrast=vd["contrast"],
            saturation=vd["saturation"], brightness=vd["brightness"],
            temperature=vd["temperature"], hue=vd["hue"], invert=vd["invert"]
        )
        if self.vworker:
            self.vworker.set_fx(fx)
        self.bg.pulse(0.2)

    # ---------- file / playback ----------
    def _open(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open Video")
        if not f: return
        self.path = f
        print("[OPEN] Video:", self.path)

        _safe_rm(self.src_wav); _safe_rm(self.hyd_wav)

        ok1 = extract_audio_wav(self.path, self.src_wav, sr=PREF_WAV_RATE, ch=PREF_WAV_CH)
        print(f"[OPEN] WAV extracted -> {self.src_wav} ok={ok1} sha1={_sha1(self.src_wav)} size={self.src_wav.stat().st_size if self.src_wav.exists() else 0}")

        if ok1:
            self.raw.load(self.src_wav)
        else:
            print("[OPEN] No audio track found. Silent playback.")

        self._start_video()

        if ok1:
            self.mode = "raw"; self.lbl_mode.setText("Audio: RAW")
            self.raw.set_speed(self.speed)
            self.raw.play_from_ms(0)

        def _hydra_task():
            if not ok1 or not _have_hydra(): return
            print("[HYDRA] background encode/decode…")
            ok = hydra_process_wav(self.src_wav, self.hyd_wav,
                                   kbps=HYDRA_KBPS, frame=HYDRA_FRAME, quality=HYDRA_QUALITY,
                                   use_ms=HYDRA_USE_MS, use_transient=HYDRA_USE_TR)
            if not ok: return
            try:
                self.hyd.load(self.hyd_wav)
                ref, _ = _read_wav_any(self.src_wav)
                tst, _ = _read_wav_any(self.hyd_wav)
                snr = _snr_db(ref[:min(8*PREF_WAV_RATE, ref.shape[0])], tst[:min(8*PREF_WAV_RATE, tst.shape[0])])
                print(f"[HYDRA] SNR ≈ {snr:.2f} dB (>= {HYDRA_AUTO_SWAP_SNR_DB} dB -> auto-swap)")
                if snr >= HYDRA_AUTO_SWAP_SNR_DB:
                    ms = 0
                    if self._fps > 0 and self.timeline.maximum() > 0:
                        ms = int((self.timeline.value() / self._fps) * 1000.0)
                    self._force_hydra(ms_override=ms)
            except Exception as e:
                print("[HYDRA] SNR check err:", e)

        if _have_hydra():
            threading.Thread(target=_hydra_task, daemon=True).start()

        self.bg.pulse(0.7)

    def _start_video(self):
        self._stop_video()
        self.vworker = VideoWorker(self.path)
        vd = self.filters_dock.value_dict()
        self.vworker.set_fx(FX(
            gamma=vd["gamma"], sharpen=vd["sharpen"], contrast=vd["contrast"],
            saturation=vd["saturation"], brightness=vd["brightness"],
            temperature=vd["temperature"], hue=vd["hue"], invert=vd["invert"]
        ))
        self.vworker.frameReady.connect(self._on_frame)
        self.vworker.metaReady.connect(self._meta)
        self.vworker.set_loop(self.btn_loop.isChecked())
        self.vworker.set_speed(self.speed)  # keep in sync
        self.vworker.start()
        self.btn_play.setText("Pause")

    def _stop_video(self):
        if self.vworker:
            self.vworker.stop(); self.vworker.wait()
            self.vworker = None

    # ---------- frame & meta ----------
    def _on_frame(self, qimg: QImage, pos_frame: int):
        size = self.video_label.size()
        pm = QPixmap.fromImage(qimg).scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.FastTransformation)
        self.video_label.setPixmap(pm)
        if not self._seeking:
            self.timeline.blockSignals(True)
            vmax = max(0, self._total_frames - 1)
            self.timeline.setValue(min(max(0, pos_frame), vmax))
            self.timeline.blockSignals(False)

    def _meta(self, w, h, fps, total_frames):
        self._fps = fps if fps > 0 else 30.0
        self._total_frames = max(1, int(total_frames))
        self.timeline.setMaximum(max(1, self._total_frames - 1))
        try: self.timeline.setTickInterval(max(1, int(self._total_frames / 24)))
        except Exception: pass
        self.timeline.setEnabled(True)
        print(f"[VIDEO] {w}x{h}  fps={self._fps:.3f}  frames={self._total_frames}")

    # ---------- debounced seek ----------
    def _seek_pressed(self):
        self._seeking = True
        self.controls.show()
        self._bump_activity()

    def _queue_seek(self, v: int):
        vmax = max(0, self._total_frames - 1)
        self._pending_seek = int(max(0, min(v, vmax)))
        # restart debounce timer (120ms)
        self._seek_timer.start(120)

    def _do_seek(self):
        if self._pending_seek is None: return
        fidx = int(self._pending_seek)
        self._pending_seek = None
        if self.vworker:
            self.vworker.seek(fidx)
        if self._fps > 0:
            ms = int((fidx / self._fps) * 1000.0)
            if self.mode == "hyd" and wav_has_audio(self.hyd_wav):
                self.hyd.seek_ms(ms)
            elif wav_has_audio(self.src_wav):
                self.raw.seek_ms(ms)

    def _seek_release(self):
        # flush last seek immediately
        if self._pending_seek is not None:
            self._do_seek()
        self._seeking = False
        self.bg.pulse(0.15)

    # ---------- controls ----------
    def _play_pause(self):
        if not self.path:
            self._open(); return
        if self.vworker and self.vworker.isRunning():
            self._stop_video(); self.btn_play.setText("Play")
            self.raw.stop(); self.hyd.stop()
        else:
            self._start_video()
            pos_ms = 0
            if self._fps > 0 and self.timeline.maximum() > 0:
                pos_ms = int((self.timeline.value() / self._fps) * 1000.0)
            if self.mode == "hyd" and wav_has_audio(self.hyd_wav):
                self.hyd.set_speed(self.speed)
                self.hyd.play_from_ms(pos_ms)
            elif wav_has_audio(self.src_wav):
                self.raw.set_speed(self.speed)
                self.raw.play_from_ms(pos_ms)

    def _loop_toggled(self, s):
        self.btn_loop.setText("Loop ON" if s else "Loop OFF")
        if self.vworker: self.vworker.set_loop(s)

    # ---------- audio mode toggles ----------
    def _force_raw(self, ms_override: Optional[int] = None):
        if not wav_has_audio(self.src_wav): return
        self.mode = "raw"; self.lbl_mode.setText("Audio: RAW")
        pos_ms = ms_override if ms_override is not None else int((self.timeline.value()/self._fps)*1000.0) if self._fps>0 else 0
        self.hyd.stop()
        self.raw.set_speed(self.speed)
        self.raw.play_from_ms(pos_ms)

    def _force_hydra(self, ms_override: Optional[int] = None):
        if not wav_has_audio(self.hyd_wav): return
        self.mode = "hyd"; self.lbl_mode.setText("Audio: HYDRA")
        pos_ms = ms_override if ms_override is not None else int((self.timeline.value()/self._fps)*1000.0) if self._fps>0 else 0
        self.raw.stop()
        self.hyd.set_speed(self.speed)
        self.hyd.play_from_ms(pos_ms)

    # ---------- saving (video-only) ----------
    def _save_video(self):
        if not self.path: return
        out_path, _ = QFileDialog.getSaveFileName(self, "Save Video", "", "MP4 Files (*.mp4)")
        if not out_path: return

        cap = cv2.VideoCapture(self.path)
        if not cap.isOpened(): return
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        w  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(out_path, fourcc, fps, (w, h))

        # freeze current FX at export start
        vd = self.filters_dock.value_dict()
        fx = FX(
            gamma=vd["gamma"], sharpen=vd["sharpen"], contrast=vd["contrast"],
            saturation=vd["saturation"], brightness=vd["brightness"],
            temperature=vd["temperature"], hue=vd["hue"], invert=vd["invert"]
        )

        self.setWindowTitle("Saving… 0% (video-only)")
        n = 0
        while True:
            ok, frame = cap.read()
            if not ok: break
            out.write(_apply_filters_bgr(frame, fx))
            n += 1
            if n % 10 == 0:
                pct = int(100*n/total)
                self.setWindowTitle(f"Saving… {pct}% (video-only)")
                QApplication.processEvents()

        out.release(); cap.release()
        self.setWindowTitle("MMX HYDRA Player — Saved ✓ (video-only)")

    # ---------- window ----------
    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.menuBar().show(); self.showNormal(); self._fill_expand = False; self.bg.setVisible(True)
        else:
            self.menuBar().hide(); self._fill_expand = True; self.bg.setVisible(True); self.showFullScreen()

    def _show_filters(self): self.filters_dock.show(); self.bg.pulse(0.4)
    def _hide_filters(self): self.filters_dock.hide()

    def changeEvent(self, ev):
        if ev.type() == QEvent.Type.WindowStateChange:
            # hook if you want to pause timers on minimize
            pass
        super().changeEvent(ev)

    def closeEvent(self, ev):
        self._stop_video()
        self.raw.stop(); self.hyd.stop()
        try: shutil.rmtree(self.tmpdir, ignore_errors=True)
        except Exception: pass
        ev.accept()

# ========================= Main =========================
if __name__ == "__main__":
    os.environ.setdefault("QT_ENABLE_HIGDPI_SCALING", "1")
    app = QApplication(sys.argv)
    win = VideoPlayer()
    win.show()
    sys.exit(app.exec())
