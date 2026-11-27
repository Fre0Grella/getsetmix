"""Spike #22: CLAP audio embeddings on the CPU, without PyTorch. Also the server benchmark.

This file is self-contained on purpose: copy it alone to another machine to
measure the cost there. It needs Python 3.10+, ffmpeg on PATH and:
    pip install onnxruntime numpy psutil

Benchmark (prints a JSON summary and writes bench.json to <out-dir>):
    python bench.py <out-dir> <audio files or folders...> [--model model.onnx] [--tracks 20]
                    [--windows 6] [--threads 0] [--seek]

It embeds a fixed random pick of --tracks files (all of them if fewer).

Without --model it downloads Xenova/larger_clap_music_and_speech
onnx/audio_model.onnx (281 MB) into <out-dir>. That export has the same
architecture and size as the laion/larger_clap_music export used in the
spike, so it costs the same per window. Audio files are only read, never
written.

The rest of the spike imports decode(), log_mel() and Embedder from here.
"""
import argparse, json, os, platform, subprocess, sys, time, urllib.request
from pathlib import Path

import numpy as np

SR = 48000            # CLAP's sample rate
WIN = 10 * SR         # one model input: 10 s, 480,000 samples
N_FFT, HOP, N_MELS, FMIN, FMAX = 1024, 480, 64, 50.0, 14000.0
AUDIO_EXT = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a", ".ogg"}
DEFAULT_MODEL = ("https://huggingface.co/Xenova/larger_clap_music_and_speech/"
                 "resolve/main/onnx/audio_model.onnx")


# ---- decode ---------------------------------------------------------------

def decode(path, start=None, duration=None):
    """Decode a file to 48 kHz mono float32 with ffmpeg (read only)."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32)


def decode_windows(path, starts, chunk=1 << 20):
    """Decode the whole file in one ffmpeg run, streaming, and keep only the
    10 s windows that begin at the given sample offsets. Memory stays at a few
    windows even for a two-hour mix."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
           "-ar", str(SR), "-f", "f32le", "-"]
    wins = [np.zeros(WIN, np.float32) for _ in starts]
    got = [0] * len(starts)
    pos, rest = 0, b""
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as p:
        while True:
            buf = p.stdout.read(chunk)
            if not buf:
                break
            buf = rest + buf
            usable = len(buf) // 4 * 4
            rest = buf[usable:]
            x = np.frombuffer(buf[:usable], dtype=np.float32)
            for i, s in enumerate(starts):
                lo, hi = max(s, pos), min(s + WIN, pos + len(x))
                if lo < hi:
                    wins[i][lo - s:hi - s] = x[lo - pos:hi - pos]
                    got[i] = max(got[i], hi - s)
            pos += len(x)
            if all(s + WIN <= pos for s in starts):
                p.kill()                     # past the last window: stop decoding
                break
    return [w[:g] for w, g in zip(wins, got)]


# ---- CLAP front end (port of transformers' ClapFeatureExtractor, rand_trunc path) ----

def _hz_to_mel(f):   # slaney scale, as librosa and transformers use it
    f = np.asarray(f, dtype=np.float64)
    m = 3.0 * f / 200.0
    log = f >= 1000.0
    return np.where(log, 15.0 + np.log(np.maximum(f, 1e-10) / 1000.0) * (27.0 / np.log(6.4)), m)


def _mel_to_hz(m):
    m = np.asarray(m, dtype=np.float64)
    f = 200.0 * m / 3.0
    log = m >= 15.0
    return np.where(log, 1000.0 * np.exp(np.log(6.4) / 27.0 * (m - 15.0)), f)


def _mel_filters():
    fft_freqs = np.linspace(0, SR // 2, N_FFT // 2 + 1)
    filt = _mel_to_hz(np.linspace(_hz_to_mel(FMIN), _hz_to_mel(FMAX), N_MELS + 2))
    diff = np.diff(filt)
    slopes = filt[None, :] - fft_freqs[:, None]
    down = -slopes[:, :-2] / diff[:-1]
    up = slopes[:, 2:] / diff[1:]
    bank = np.maximum(0.0, np.minimum(down, up))
    return bank * (2.0 / (filt[2:N_MELS + 2] - filt[:N_MELS]))[None, :]   # slaney norm, (513, 64)


MEL = _mel_filters()
HANN = np.hanning(N_FFT + 1)[:-1]   # periodic Hann


def log_mel(x):
    """10 s of 48 kHz mono -> (1001, 64) log-mel in dB, as CLAP expects.

    Shorter input is repeated then zero-padded ("repeatpad"); longer input
    is cut to its first 10 s (callers pass exact windows).
    """
    x = np.asarray(x, dtype=np.float32)
    if len(x) < WIN:
        if len(x) == 0:
            x = np.zeros(1, np.float32)
        x = np.tile(x, WIN // len(x))
        x = np.pad(x, (0, WIN - len(x)))
    x = x[:WIN].astype(np.float64)
    x = np.pad(x, N_FFT // 2, mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(x, N_FFT)[::HOP]
    spec = np.abs(np.fft.rfft(frames * HANN, axis=1)) ** 2          # (1001, 513)
    mel = np.maximum(spec @ MEL, 1e-10)
    return (10.0 * np.log10(mel)).astype(np.float32)               # (1001, 64)


# ---- model ----------------------------------------------------------------

class Embedder:
    def __init__(self, model_path, threads=0):
        import onnxruntime as ort
        so = ort.SessionOptions()
        if threads:
            so.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(str(model_path), so, providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name
        names = [o.name for o in self.sess.get_outputs()]
        self.out = "audio_embeds" if "audio_embeds" in names else names[0]

    def __call__(self, mels):
        """(n, 1001, 64) log-mels -> (n, 512) projected embeddings (not normalised)."""
        feats = np.asarray(mels, np.float32)[:, None]               # (n, 1, 1001, 64)
        return self.sess.run([self.out], {self.inp: feats})[0]


def window_starts(length_s, n):
    """n evenly spaced 10 s windows between 10% and 90% of the track."""
    if length_s <= 10:
        return [0.0]
    lo, hi = 0.1 * length_s, max(0.1 * length_s, 0.9 * length_s - 10)
    starts = np.linspace(lo, hi, n) if n > 1 else [(lo + hi) / 2]
    return sorted({round(float(s), 1) for s in starts})       # short tracks: fewer windows


def embed_track(path, emb, n_windows, timer, seek=False):
    """Return (n, 512) embeddings of n_windows sampled 10 s windows.

    Default: decode the whole file once and cut the windows out (measured
    faster). seek=True runs ffprobe and one seeking ffmpeg call per window.
    """
    t = time.perf_counter()
    length = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True).stdout.strip())
    starts = window_starts(length, n_windows)
    if seek:
        wins = [decode(path, s, 10.0) for s in starts]
    else:
        wins = decode_windows(path, [int(s * SR) for s in starts])
    if not any(len(w) for w in wins):
        raise ValueError("no audio decoded")
    timer["decode"] += time.perf_counter() - t
    t = time.perf_counter()
    mels = np.stack([log_mel(w) for w in wins])
    timer["features"] += time.perf_counter() - t
    t = time.perf_counter()
    out = emb(mels)
    timer["inference"] += time.perf_counter() - t
    return out


def inside_repo(path):
    """True if path is inside the git checkout this script lives in (if any)."""
    here = Path(__file__).resolve().parent
    root = next((p for p in [here, *here.parents] if (p / ".git").exists()), None)
    return root is not None and (path == root or root in path.parents)


def machine():
    import psutil
    cpu = platform.processor()
    if sys.platform.startswith("linux"):
        try:
            cpu = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo")
                       if l.startswith("model name"))
        except (OSError, StopIteration):
            pass
    import onnxruntime as ort
    return {"cpu": cpu, "machine": platform.machine(), "os": platform.platform(),
            "logical_cpus": os.cpu_count(), "physical_cores": psutil.cpu_count(logical=False),
            "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
            "python": platform.python_version(), "onnxruntime": ort.__version__}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir")
    ap.add_argument("audio", nargs="+", help="audio files and/or folders searched recursively")
    ap.add_argument("--model")
    ap.add_argument("--tracks", type=int, default=20)
    ap.add_argument("--windows", type=int, default=6)
    ap.add_argument("--threads", type=int, default=0, help="0 = ONNX Runtime's default")
    ap.add_argument("--seek", action="store_true", help="decode each window with its own seek")
    a = ap.parse_args()
    import psutil
    out = Path(a.out_dir).resolve()
    assert not inside_repo(out), "write the output outside the repository"
    out.mkdir(parents=True, exist_ok=True)
    model = Path(a.model) if a.model else out / "larger_clap_music_and_speech_audio_model.onnx"
    if not model.exists():
        print("downloading", DEFAULT_MODEL, file=sys.stderr)
        urllib.request.urlretrieve(DEFAULT_MODEL, model)
    files = []
    for src in map(Path, a.audio):
        files += [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.suffix.lower() in AUDIO_EXT)
    if len(files) > a.tracks:
        import random
        files = random.Random(0).sample(files, a.tracks)       # a fixed random pick, not the first N
    proc = psutil.Process()
    t = time.perf_counter(); emb = Embedder(model, a.threads); load_s = time.perf_counter() - t
    emb(np.zeros((1, 1001, 64), np.float32))                      # warm-up, not timed
    timer = {"decode": 0.0, "features": 0.0, "inference": 0.0}
    peak, done = proc.memory_info().rss, 0
    for f in files:
        try:
            embed_track(f, emb, a.windows, timer, a.seek)
            done += 1
        except Exception as e:  # noqa: BLE001 - a benchmark keeps going
            print("failed:", type(e).__name__, file=sys.stderr)
        peak = max(peak, proc.memory_info().rss)
    mi = proc.memory_info()
    peak = max(peak, getattr(mi, "peak_wset", 0) or 0)          # Windows keeps a true peak
    if sys.platform != "win32":
        import resource
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak = max(peak, r * (1 if sys.platform == "darwin" else 1024))
    res = {"machine": machine(), "model": str(model.name), "model_mb": round(model.stat().st_size / 1e6, 1),
           "threads": a.threads or "default", "windows_per_track": a.windows, "seek": a.seek, "tracks": done,
           "model_load_s": round(load_s, 2), "peak_rss_mb": round(peak / 2**20),
           "s_per_track": {k: round(v / max(done, 1), 3) for k, v in timer.items()}}
    res["s_per_track"]["total"] = round(sum(res["s_per_track"].values()), 3)
    (out / "bench.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
