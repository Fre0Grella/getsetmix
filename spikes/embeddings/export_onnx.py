"""Spike #22: export a LAION CLAP audio tower to ONNX, once, with PyTorch.

Run in a throwaway environment of its own; the environment that computes
embeddings never has torch in it:
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    pip install transformers onnx onnxruntime numpy
    set HF_HOME=<somewhere outside the repo>
    python export_onnx.py <out-dir> [--model laion/larger_clap_music]
    (the spike also exported --model laion/clap-htsat-unfused)

Writes <out-dir>/<name>_audio.onnx (input "input_features" (n, 1, 1001, 64),
output "audio_embeds" (n, 512)) and export_check.json, which records:
- how far the numpy front end in bench.py is from transformers'
  ClapFeatureExtractor on the same audio;
- how far ONNX Runtime's output is from PyTorch's on the same input.
"""
import argparse, json, sys, time
from pathlib import Path

import numpy as np
import torch
from transformers import ClapAudioModelWithProjection, ClapFeatureExtractor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench import log_mel, Embedder, WIN, inside_repo  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out_dir")
ap.add_argument("--model", default="laion/larger_clap_music")
a = ap.parse_args()
out = Path(a.out_dir).resolve()
assert not inside_repo(out), "write the output outside the repository"
out.mkdir(parents=True, exist_ok=True)
name = a.model.split("/")[-1]
onnx_path = out / f"{name}_audio.onnx"

model = ClapAudioModelWithProjection.from_pretrained(a.model).eval()
fe = ClapFeatureExtractor.from_pretrained(a.model)


class Tower(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, input_features):
        return self.m(input_features=input_features).audio_embeds


tower = Tower(model).eval()
rng = np.random.default_rng(0)
# A test signal with some structure: noise plus two tones, 10 s at 48 kHz.
t = np.arange(WIN) / 48000
wave = (0.05 * rng.standard_normal(WIN) + 0.3 * np.sin(2 * np.pi * 220 * t)
        + 0.2 * np.sin(2 * np.pi * 3520 * t)).astype(np.float32)

ref = fe(wave, sampling_rate=48000, return_tensors="np")["input_features"][0, 0]   # (1001, 64)
mine = log_mel(wave)
fe_diff = float(np.abs(ref - mine).max())

x = torch.from_numpy(np.stack([mine, log_mel(wave[::-1].copy())])[:, None])
with torch.no_grad():
    want = tower(x).numpy()
t0 = time.perf_counter()
torch.onnx.export(tower, (x,), str(onnx_path), input_names=["input_features"],
                  output_names=["audio_embeds"], dynamic_axes={"input_features": {0: "n"}, "audio_embeds": {0: "n"}},
                  opset_version=17, dynamo=False)
export_s = time.perf_counter() - t0
got = Embedder(onnx_path)(x.numpy()[:, 0])
cos = (want * got).sum(1) / np.linalg.norm(want, axis=1) / np.linalg.norm(got, axis=1)
res = {"model": a.model, "onnx": onnx_path.name, "onnx_mb": round(onnx_path.stat().st_size / 1e6, 1),
       "torch": torch.__version__, "export_s": round(export_s, 1),
       "frontend_max_abs_diff_db": fe_diff, "frontend_ref_range_db": [float(ref.min()), float(ref.max())],
       "onnx_vs_torch_max_abs": float(np.abs(want - got).max()), "onnx_vs_torch_cosine_min": float(cos.min())}
(out / f"{name}_export_check.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
