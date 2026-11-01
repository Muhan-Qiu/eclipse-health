"""把 V1（MIT-BIH raw-window）PyTorch checkpoint 导出为 ONNX 并生成 models/index.json。

用法（项目根目录）::

    C:\\Users\\qiumuhan\\anaconda3\\python.exe modules\\official\\relay-ecg\\tools\\export_onnx.py

默认读取 ``C:\\Users\\qiumuhan\\Downloads\\relay LSTM\\V1`` 的 7 个 checkpoint，
写到 ``uploads/relay-ecg/models/``，索引写到 ``modules/official/relay-ecg/models/index.json``。
ONNX 不提交 git；脚本可重复执行，导出后用 onnxruntime 做 argmax 一致率校验（≥99%）。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from datetime import UTC, datetime
from importlib.machinery import SourceFileLoader
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_V1 = Path(os.environ.get("RELAY_V1_DIR", "V1"))
DEFAULT_OUT = REPO_ROOT / "uploads" / "relay-ecg" / "models"
DEFAULT_INDEX = REPO_ROOT / "modules" / "official" / "relay-ecg" / "models" / "index.json"

FS = 360
WIN_BEFORE = 90
WIN_AFTER = 144
WINDOW = WIN_BEFORE + WIN_AFTER
SEQ_LEN = 64
CLASSES = ["N", "SVEB", "VEB", "F", "Q"]
DT_MEDIAN = 275.0 / FS

# 任务给定的 4 类（N/SVEB/VEB/F）macro F1，来自 V1 特征标尺评测（见 index.scoreProtocol）。
SCORES = {
    "relay_k2": (0.5706, "ours"),
    "relay_k12": (0.5417, "ours"),
    "relay_k4": (0.5397, "ours"),
    "relay_k8": (0.5199, "ours"),
    "bilstm": (0.4186, "baseline"),
    "resnet1d": (0.4178, "baseline"),
    "tlstm": (0.3522, "baseline"),
}
CHECKPOINTS = {
    "relay_k2": "results/ckpt/relay_k2_s0.pt",
    "relay_k12": "results/ckpt/relay_k12_s0.pt",
    "relay_k4": "results/ckpt/relay_k4.pt",
    "relay_k8": "results/ckpt/relay_k8.pt",
    "bilstm": "results/ckpt/bilstm.pt",
    "resnet1d": "results/ckpt/resnet1d.pt",
    "tlstm": "results/ckpt/tlstm.pt",
}
NAMES = {
    "relay_k2": "Relay-LSTM K=2",
    "relay_k4": "Relay-LSTM K=4",
    "relay_k8": "Relay-LSTM K=8",
    "relay_k12": "Relay-LSTM K=12",
    "bilstm": "BiLSTM 基线",
    "resnet1d": "1D-ResNet18 基线",
    "tlstm": "T-LSTM 基线",
}


def load_relay_module(v1_root: Path) -> Any:
    path = v1_root / "relay LSTM V1.python"
    loader = SourceFileLoader("relay_lstm_v1_export", str(path))
    spec = importlib.util.spec_from_loader("relay_lstm_v1_export", loader)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class ExportFront(nn.Module):
    """``LocalGlobalSampler`` 的 ONNX 友好版本：用静态切片替代 ``unfold``。

    数值与上游完全一致（导出前做了 max |diff| == 0 校验）；参数名保持
    ``proj1/proj2``，因此可以直接 ``load_state_dict`` 上游权重。
    """

    def __init__(
        self, in_channels: int, n_local: int, n_global: int, window_size: int,
        out_dim: int, hidden_dim: int,
    ) -> None:
        super().__init__()
        self.in_channels = in_channels
        self.n_local = n_local
        self.n_global = n_global
        self.window_size = window_size
        self.proj1 = nn.Linear(in_channels * n_local * window_size + in_channels * n_global, hidden_dim)
        self.act = nn.ReLU()
        self.proj2 = nn.Linear(hidden_dim, out_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        length = x.shape[-1]
        step_local = length // self.n_local
        step_global = length // self.n_global
        local = torch.cat(
            [x[..., i * step_local:i * step_local + self.window_size] for i in range(self.n_local)],
            dim=-1,
        )
        global_blocks = x[..., ::step_global][..., : self.n_global]
        feat = torch.cat([local, global_blocks], dim=-1).flatten(start_dim=1)
        return self.proj2(self.act(self.proj1(feat)))


class RelayClassifier(nn.Module):
    def __init__(self, relay_mod: Any, n_rounds: int) -> None:
        super().__init__()
        self.front = ExportFront(2, 20, 8, 15, 128, 128)
        self.backbone = relay_mod.RelayLSTM(
            input_size=128, hidden_size=128, out_dim=len(CLASSES), n_rounds=n_rounds
        )

    def forward(self, x: torch.Tensor, dt: torch.Tensor) -> torch.Tensor:
        batch, steps, channels, width = x.shape
        z = self.front(x.reshape(batch * steps, channels, width)).reshape(batch, steps, -1)
        return self.backbone(z, dt)


class FlatLSTM(nn.Module):
    """复制自 V1 ``run_experiments.py`` 的基线（BiLSTM 用）。"""

    def __init__(self, in_ch: int, win: int, hidden: int, n_cls: int, bidir: bool = False) -> None:
        super().__init__()
        self.rnn = nn.LSTM(in_ch * win, hidden, batch_first=True, bidirectional=bidir)
        self.head = nn.Linear(hidden * (2 if bidir else 1), n_cls)

    def forward(self, x: torch.Tensor, dt: torch.Tensor | None = None) -> torch.Tensor:
        batch, steps = x.shape[0], x.shape[1]
        h, _ = self.rnn(x.reshape(batch, steps, -1))
        return self.head(h)


class TLSTMModel(nn.Module):
    """复制自 V1 ``run_experiments.py`` 的 T-LSTM 基线。"""

    def __init__(self, cell_cls: Any, in_ch: int, win: int, hidden: int, n_cls: int) -> None:
        super().__init__()
        self.hidden = hidden
        self.cell = cell_cls(in_ch * win, hidden, layer_norm=False, variable_decay=True)
        self.head = nn.Linear(hidden, n_cls)

    def forward(self, x: torch.Tensor, dt: torch.Tensor | None = None) -> torch.Tensor:
        batch, steps = x.shape[0], x.shape[1]
        h = x.new_zeros(batch, self.hidden)
        c = x.new_zeros(batch, self.hidden)
        outs = []
        for t in range(steps):
            dt_t = dt[:, t - 1:t] if (dt is not None and t > 0) else None
            h, c, _ = self.cell(x[:, t].reshape(batch, -1), h, c, dt_t)
            outs.append(h)
        return self.head(torch.stack(outs, dim=1))


class ResBlock1D(nn.Module):
    def __init__(self, cin: int, cout: int, stride: int = 1) -> None:
        super().__init__()
        self.conv1 = nn.Conv1d(cin, cout, 3, stride, 1, bias=False)
        self.bn1 = nn.BatchNorm1d(cout)
        self.conv2 = nn.Conv1d(cout, cout, 3, 1, 1, bias=False)
        self.bn2 = nn.BatchNorm1d(cout)
        self.act = nn.ReLU(inplace=True)
        if stride != 1 or cin != cout:
            self.skip: nn.Module = nn.Sequential(
                nn.Conv1d(cin, cout, 1, stride, bias=False), nn.BatchNorm1d(cout)
            )
        else:
            self.skip = nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.act(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        return self.act(out + self.skip(x))


class ResNet1D(nn.Module):
    """V1 早期 1D-ResNet（32/64/128，每阶段 2 个 block），按 checkpoint 形状还原。"""

    def __init__(self, in_ch: int, n_cls: int) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv1d(in_ch, 32, 7, 1, 3, bias=False),
            nn.BatchNorm1d(32),
            nn.ReLU(inplace=True),
        )
        self.layer1 = self._stage(32, 32, 2, 1)
        self.layer2 = self._stage(32, 64, 2, 2)
        self.layer3 = self._stage(64, 128, 2, 2)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.head = nn.Linear(128, n_cls)

    @staticmethod
    def _stage(cin: int, cout: int, blocks: int, stride: int) -> nn.Sequential:
        items = [ResBlock1D(cin, cout, stride)]
        items += [ResBlock1D(cout, cout, 1) for _ in range(blocks - 1)]
        return nn.Sequential(*items)

    def forward(self, x: torch.Tensor, dt: torch.Tensor | None = None) -> torch.Tensor:
        if x.dim() == 4:
            x = x.reshape(-1, x.shape[-2], x.shape[-1])
        z = self.stem(x)
        z = self.layer1(z)
        z = self.layer2(z)
        z = self.layer3(z)
        z = self.pool(z).flatten(start_dim=1)
        return self.head(z)


def build_model(name: str, relay_mod: Any) -> tuple[nn.Module, bool]:
    """返回 (model, uses_dt)。"""
    if name.startswith("relay_k"):
        return RelayClassifier(relay_mod, int(name.split("k")[1])), True
    if name == "bilstm":
        return FlatLSTM(2, WINDOW, 128, len(CLASSES), bidir=True), False
    if name == "tlstm":
        return TLSTMModel(relay_mod.RelayLSTMCell, 2, WINDOW, 128, len(CLASSES)), True
    if name == "resnet1d":
        return ResNet1D(2, len(CLASSES)), False
    raise ValueError(name)


def dummy_inputs(name: str, batch: int) -> tuple[torch.Tensor, ...]:
    if name == "resnet1d":
        return (torch.randn(batch, 2, WINDOW),)
    x = torch.randn(batch, SEQ_LEN, 2, WINDOW)
    if name in {"bilstm"}:
        return (x,)
    dt = torch.rand(batch, SEQ_LEN) * 1.0 + 0.5
    return (x, dt)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_one(
    name: str, v1_root: Path, out_dir: Path, relay_mod: Any
) -> dict[str, Any]:
    checkpoint = v1_root / CHECKPOINTS[name]
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    state = payload.get("state_dict", payload)
    model, uses_dt = build_model(name, relay_mod)
    model.load_state_dict(state, strict=True)
    model.eval()

    inputs = dummy_inputs(name, 4)
    input_names = ["x", "dt"] if uses_dt else ["x"]
    assert len(input_names) == len(inputs)
    target = out_dir / f"{name}.onnx"
    with torch.no_grad():
        torch.onnx.export(
            model,
            inputs,
            str(target),
            opset_version=17,
            input_names=input_names,
            output_names=["logits"],
            dynamic_axes={key: {0: "batch"} for key in [*input_names, "logits"]},
            do_constant_folding=True,
        )

    import onnxruntime as ort

    session = ort.InferenceSession(str(target), providers=["CPUExecutionProvider"])
    agreement = 1.0
    max_diff = 0.0
    for batch in (1, 4, 7):
        tensors = dummy_inputs(name, batch)
        feed = {key: value.numpy().astype(np.float32) for key, value in zip(input_names, tensors)}
        onnx_out = session.run(None, feed)[0]
        with torch.no_grad():
            torch_out = model(*tensors).numpy()
        match = float((onnx_out.argmax(-1) == torch_out.argmax(-1)).mean())
        diff = float(np.abs(onnx_out - torch_out).max())
        agreement = min(agreement, match)
        max_diff = max(max_diff, diff)
    if agreement < 0.99 or max_diff > 1e-4:
        raise RuntimeError(f"{name} ONNX 校验失败：agreement={agreement:.4f} diff={max_diff:.2e}")

    mode = "beat" if name == "resnet1d" else "sequence"
    x_shape = [1, 2, WINDOW] if mode == "beat" else [1, SEQ_LEN, 2, WINDOW]
    out_shape = [1, len(CLASSES)] if mode == "beat" else [1, SEQ_LEN, len(CLASSES)]
    tensors: dict[str, Any] = {"x": {"dtype": "float32", "shape": x_shape}}
    if uses_dt:
        tensors["dt"] = {"dtype": "float32", "shape": [1, SEQ_LEN]}
    score, group = SCORES[name]
    return {
        "id": name.replace("_", "-"),
        "name": NAMES[name],
        "source": "relay-v1",
        "class": group,
        "score": score,
        "metric": "macro_f1",
        "file": target.name,
        "sha256": sha256(target),
        "bytes": target.stat().st_size,
        "parameters": sum(p.numel() for p in model.parameters()),
        "classes": CLASSES,
        "checkpoint": CHECKPOINTS[name],
        "input": {
            "mode": mode,
            "fs": FS,
            "leads": 2,
            "windowSamples": WINDOW,
            "windowBefore": WIN_BEFORE,
            "windowAfter": WIN_AFTER,
            "beatsPerWindow": SEQ_LEN if mode == "sequence" else 1,
            "zscorePerLead": True,
            "dtMedianSeconds": round(DT_MEDIAN, 9),
            "tensors": tensors,
        },
        "output": {"tensor": "logits", "classes": CLASSES, "shape": out_shape},
        "preprocess": {
            "pipeline": "relay-v1-beat-window",
            "fs": FS,
            "windowBeforeSeconds": 0.25,
            "windowAfterSeconds": 0.40,
            "zscore": "per-lead",
            "dt": "rr_seconds / (275/360)",
        },
        "export": {
            "opset": 17,
            "torch": torch.__version__,
            "exportedAt": datetime.now(UTC).isoformat(timespec="seconds"),
            "argmaxAgreement": agreement,
            "maxAbsLogitDiff": max_diff,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1-root", type=Path, default=DEFAULT_V1)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    args = parser.parse_args()

    if not (args.v1_root / "relay LSTM V1.python").is_file():
        raise SystemExit(f"V1 源码不存在：{args.v1_root}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.index.parent.mkdir(parents=True, exist_ok=True)
    relay_mod = load_relay_module(args.v1_root)

    started = time.perf_counter()
    models = []
    for name in SCORES:
        entry = export_one(name, args.v1_root, args.out_dir, relay_mod)
        models.append(entry)
        print(
            f"{entry['id']:<10} {entry['class']:<8} score={entry['score']:.4f} "
            f"params={entry['parameters']:,} size={entry['bytes'] / 1e6:.2f}MB "
            f"agreement={entry['export']['argmaxAgreement']:.3f}"
        )

    models.sort(key=lambda item: (-item["score"], item["id"]))
    ours = [item["score"] for item in models if item["class"] == "ours"]
    baselines = [item["score"] for item in models if item["class"] == "baseline"]
    assert min(ours) > max(baselines), "ours 必须全部高于基线"
    index = {
        "schemaVersion": "1.0",
        "source": "relay-v1",
        "metric": "macro_f1",
        "classScope": "4-class AAMI (N/SVEB/VEB/F)",
        "scoreProtocol": {
            "protocol": "DS1 训 / DS2 测，AAMI 4 类 macro F1，5 种子均值",
            "source": "relay LSTM/10月19日WFDB基线测试/results_features/总表.md",
            "note": "精选子集，不是 V1 全量排行榜；V1 的 lstm 等基线在部分口径下高于 relay_k4/k8，本包按要求不收录。",
        },
        "classes": CLASSES,
        "dtMedianSeconds": round(DT_MEDIAN, 9),
        "window": {"before": WIN_BEFORE, "after": WIN_AFTER, "samples": WINDOW},
        "models": models,
        "ordering": {
            "oursMin": min(ours),
            "baselineMax": max(baselines),
            "satisfied": min(ours) > max(baselines),
        },
        "nonDiagnostic": "非医疗器械，不用于诊断",
    }
    args.index.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n导出 {len(models)} 个模型 -> {args.out_dir}")
    print(f"索引 -> {args.index}")
    print(f"用时 {time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
