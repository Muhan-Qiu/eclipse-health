"""把 Sleep-EDF Relay / 基线权重导出为 ONNX，并写入 verify.json 与 models/index.json。

用法（项目根目录，使用带 torch 2.5.1 的 base Python）：
    C:\\Users\\qiumuhan\\anaconda3\\python.exe modules\\official\\relay-sleep\\tools\\export_models.py

依赖用户机器上的原始实验目录：
  - Relay 模型工厂与 checkpoint：<data-root>/trackb/models.py、results_trackb/_pilot/_ckpt
  - 基线 checkpoint：<data-root>/results/full/_ckpt
  - 基线架构源码：<braindecode-src>/braindecode（braindecode 1.8.1，未安装，直接按源码导入）

Relay 统一导出 ``features [B,10,272]`` + ``dt [B,10,1]`` -> ``logits [B,10,5]``。
Chambon2018 / AttnSleep 是 30s 原始 EEG 的端到端模型（3 个窗口 -> 序列标签），
checkpoint 的 head 输入是 272/2400 维特征 × 3，无法从 272 维冻结特征推理；
因此按真实架构导出 ``windows [B,3,C,3000]`` -> ``logits [B,5]``，并在元数据中标注。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_ROOT = Path(r"<sleep-data-root>")
DEFAULT_BRAINDECODE = Path(
    r"<braindecode-src>"
)
DEFAULT_MODULE_MODELS = REPO_ROOT / "modules" / "official" / "relay-sleep" / "models"
DEFAULT_WEIGHTS_DIR = REPO_ROOT / "uploads" / "relay-sleep" / "models"

CLASSES = ["W", "N1", "N2", "N3", "R"]
SEQ_LEN = 10
FEAT_DIM = 272
N_CLASSES = 5
SAMPLES_PER_WINDOW = 3000
WINDOWS_PER_SEQUENCE = 3
OPSET = 17

RELAY_WEIGHTS = [
    {
        "id": "paper-highway-h-k2-c256",
        "name": "Relay paper-highway K=2 (C256)",
        "name_zh": "Relay paper-highway K=2 · C256",
        "config": "paper_highway_h_k2",
        "ckpt": "_pilot/_ckpt/pilot_paper_highway_h_k2_S10_C256_lr2e-3_seed0/state.pt",
        "file": "relay_paper_highway_h_k2_c256.onnx",
    },
    {
        "id": "paper-highway-h-k2-b256",
        "name": "Relay paper-highway K=2 (B256)",
        "name_zh": "Relay paper-highway K=2 · B256",
        "config": "paper_highway_h_k2",
        "ckpt": "_pilot/_ckpt/pilot_paper_highway_h_k2_S10_B256_lr1e-3_seed0/state.pt",
        "file": "relay_paper_highway_h_k2_b256.onnx",
    },
    {
        "id": "bilstm-l4-b256",
        "name": "BiLSTM 4-layer (B256)",
        "name_zh": "BiLSTM 4 层 · B256",
        "config": "bilstm_L4",
        "ckpt": "_pilot/_ckpt/pilot_bilstm_L4_S10_B256_lr1e-3_seed0/state.pt",
        "file": "relay_bilstm_l4_b256.onnx",
    },
]

BASELINE_WEIGHTS = [
    {
        "id": "chambon2018-seed4",
        "name": "Chambon2018 (2ch)",
        "name_zh": "Chambon2018 · 2 通道基线",
        "ckpt": "results/full/_ckpt/chambon2018_seed4/params.pt",
        "history": "results/full/_ckpt/chambon2018_seed4/history.json",
        "file": "chambon2018_seed4.onnx",
        "channels": 2,
    },
    {
        "id": "attnsleep-seed1",
        "name": "AttnSleep (1ch)",
        "name_zh": "AttnSleep · 单通道基线",
        "ckpt": "results/full/_ckpt/attnsleep_seed1/params.pt",
        "history": "results/full/_ckpt/attnsleep_seed1/history.json",
        "file": "attnsleep_seed1.onnx",
        "channels": 1,
    },
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_source_module(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ Relay
def load_relay_factory(data_root: Path) -> types.ModuleType:
    return load_source_module("relay_trackb_models", data_root / "trackb" / "models.py")


def build_relay(factory: types.ModuleType, item: dict[str, Any], path: Path) -> tuple[nn.Module, float]:
    state = torch.load(path, map_location="cpu", weights_only=False)
    model = factory.build_model(item["config"])
    weights = state.get("best_state") or state.get("model")
    if not isinstance(weights, dict):
        raise TypeError(f"checkpoint has no state dict: {path}")
    model.load_state_dict(weights, strict=True)
    model.eval()
    score = float(state.get("best_ba") or 0.0)
    return model, score


# --------------------------------------------------------------- Baselines
def load_baseline_classes(src: Path) -> tuple[type, type]:
    """按 braindecode 1.8.1 源码加载两个模型，不安装包、不触发 models/__init__。"""
    package = types.ModuleType("braindecode")
    package.__path__ = [str(src / "braindecode")]
    sys.modules["braindecode"] = package

    models_pkg = types.ModuleType("braindecode.models")
    models_pkg.__path__ = [str(src / "braindecode" / "models")]
    sys.modules["braindecode.models"] = models_pkg

    functional = types.ModuleType("braindecode.functional")
    functional.__path__ = [str(src / "braindecode" / "functional")]
    sys.modules["braindecode.functional"] = functional

    modules_pkg = types.ModuleType("braindecode.modules")
    modules_pkg.__path__ = [str(src / "braindecode" / "modules")]
    sys.modules["braindecode.modules"] = modules_pkg

    attention = load_source_module(
        "braindecode.functional.attention",
        src / "braindecode" / "functional" / "attention.py",
    )
    functional.scaled_dot_product_attention = attention.scaled_dot_product_attention

    stub_util = types.ModuleType("braindecode.util")
    stub_util.np_to_th = lambda *args, **kwargs: None
    sys.modules["braindecode.util"] = stub_util

    load_source_module(
        "braindecode.modules.parametrization",
        src / "braindecode" / "modules" / "parametrization.py",
    )
    convolution = load_source_module(
        "braindecode.modules.convolution",
        src / "braindecode" / "modules" / "convolution.py",
    )
    modules_pkg.CausalConv1d = convolution.CausalConv1d

    class EEGModuleMixin(nn.Module):
        """只保留信号属性推断；源码基类还带 Hub/通道映射，导出用不到。"""

        def __init__(
            self,
            n_outputs=None,
            n_chans=None,
            chs_info=None,
            n_times=None,
            input_window_seconds=None,
            sfreq=None,
            channel_strategy="native",
            channel_strategy_kwargs=None,
        ) -> None:
            super().__init__()
            self._n_outputs = n_outputs
            self._n_chans = n_chans
            self._chs_info = chs_info
            self._n_times = n_times
            self._input_window_seconds = input_window_seconds
            self._sfreq = sfreq
            self._n_chans_for_jit = n_chans

        @property
        def n_outputs(self):
            return self._n_outputs

        @property
        def n_chans(self):
            return self._n_chans

        @property
        def n_times(self):
            if self._n_times is None and self._input_window_seconds and self._sfreq:
                return round(self._input_window_seconds * self._sfreq)
            return self._n_times

        @property
        def sfreq(self):
            if self._sfreq is None and self._input_window_seconds and self._n_times:
                return self._n_times / self._input_window_seconds
            return self._sfreq

        @property
        def input_window_seconds(self):
            if self._input_window_seconds is None and self._n_times and self._sfreq:
                return self._n_times / self._sfreq
            return self._input_window_seconds

    base = types.ModuleType("braindecode.models.base")
    base.EEGModuleMixin = EEGModuleMixin
    sys.modules["braindecode.models.base"] = base

    attn = load_source_module(
        "braindecode.models.attn_sleep",
        src / "braindecode" / "models" / "attn_sleep.py",
    )
    chambon = load_source_module(
        "braindecode.models.sleep_stager_chambon_2018",
        src / "braindecode" / "models" / "sleep_stager_chambon_2018.py",
    )
    return chambon.SleepStagerChambon2018, attn.AttnSleep


class TimeDistributed(nn.Module):
    """与 braindecode.modules.TimeDistributed 等价的最小实现（只为参数名对齐）。"""

    def __init__(self, module: nn.Module) -> None:
        super().__init__()
        self.module = module

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch, windows, channels, times = x.shape
        out = self.module(x.reshape(batch * windows, channels, times))
        return out.reshape(batch, windows, -1)


def build_baseline(
    chambon_cls: type, attn_cls: type, item: dict[str, Any], path: Path
) -> tuple[nn.Module, int]:
    if item["channels"] == 2:
        features = chambon_cls(2, 100, n_outputs=N_CLASSES, n_times=SAMPLES_PER_WINDOW, return_feats=True)
    else:
        features = attn_cls(
            sfreq=100, n_outputs=N_CLASSES, n_times=SAMPLES_PER_WINDOW, drop_prob=0.3, return_feats=True
        )
    head = nn.Sequential(
        nn.Flatten(start_dim=1),
        nn.Dropout(0.5),
        nn.Linear(features.len_last_layer * WINDOWS_PER_SEQUENCE, N_CLASSES),
    )
    model = nn.Sequential(TimeDistributed(features), head)
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=False), strict=True)
    model.eval()
    return model, int(item["channels"])


def best_history_score(path: Path) -> float:
    if not path.is_file():
        return 0.0
    rows = json.loads(path.read_text(encoding="utf-8"))
    values = [
        float(row["valid_bal_acc"])
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("valid_bal_acc"), (int, float))
    ]
    return max(values) if values else 0.0


# ----------------------------------------------------------------- Export
def export_onnx(
    model: nn.Module,
    inputs: tuple[torch.Tensor, ...],
    input_names: list[str],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dynamic = {name: {0: "batch"} for name in [*input_names, "logits"]}
    torch.onnx.export(
        model,
        inputs,
        output_path.as_posix(),
        input_names=input_names,
        output_names=["logits"],
        opset_version=OPSET,
        dynamic_axes=dynamic,
        do_constant_folding=True,
        dynamo=False,
    )


def argmax_agreement(model: nn.Module, onnx_path: Path, inputs: tuple[torch.Tensor, ...]) -> dict[str, float]:
    import onnxruntime as ort

    with torch.no_grad():
        reference = model(*inputs).numpy()
    session = ort.InferenceSession(onnx_path.as_posix(), providers=["CPUExecutionProvider"])
    feeds = {name: value.numpy() for name, value in zip([i.name for i in session.get_inputs()], inputs)}
    output = session.run(None, feeds)[0]
    ref_argmax = reference.reshape(-1, N_CLASSES).argmax(axis=1)
    ort_argmax = np.asarray(output).reshape(-1, N_CLASSES).argmax(axis=1)
    return {
        "agreement": float((ref_argmax == ort_argmax).mean()),
        "maxAbsDiff": float(np.abs(reference - output).max()),
        "batch": int(inputs[0].shape[0]),
    }


class RelayExportWrapper(nn.Module):
    """训练代码的 dt 是 [B,T]；模块契约固定为 [B,T,1]，导出时在这里降维。"""

    def __init__(self, model: nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, features: torch.Tensor, dt: torch.Tensor) -> torch.Tensor:
        return self.model(features, dt.squeeze(-1))


def export_relay(
    factory: types.ModuleType, data_root: Path, item: dict[str, Any], weights_dir: Path
) -> dict[str, Any]:
    model, score = build_relay(factory, item, data_root / "results_trackb" / item["ckpt"])
    cache = data_root / "trackb" / "seq_cache" / "S10.npz"
    features = np.load(cache)["test_X"][:256].astype(np.float32)
    x = torch.from_numpy(features)
    dt = torch.ones(1, SEQ_LEN, 1).expand(x.shape[0], -1, -1).contiguous()
    export_model = RelayExportWrapper(model).eval()
    output = weights_dir / item["file"]
    export_onnx(export_model, (x, dt), ["features", "dt"], output)
    check = argmax_agreement(export_model, output, (x, dt))
    return {
        "id": item["id"],
        "name": item["name"],
        "class": "ours",
        "score": round(score, 4),
        "metric": "balanced_accuracy",
        "file": item["file"],
        "sha256": sha256_file(output),
        "seqLen": SEQ_LEN,
        "classes": CLASSES,
        "parameters": int(sum(p.numel() for p in model.parameters())),
        "inputShape": [SEQ_LEN, FEAT_DIM],
        "inputKind": "features-dt",
        "verification": check,
        "opset": OPSET,
    }


def export_baseline(
    chambon_cls: type,
    attn_cls: type,
    data_root: Path,
    item: dict[str, Any],
    weights_dir: Path,
) -> dict[str, Any]:
    model, channels = build_baseline(chambon_cls, attn_cls, item, data_root / item["ckpt"])
    generator = torch.Generator().manual_seed(0)
    x = torch.randn(8, WINDOWS_PER_SEQUENCE, channels, SAMPLES_PER_WINDOW, generator=generator)
    output = weights_dir / item["file"]
    export_onnx(model, (x,), ["windows"], output)
    check = argmax_agreement(model, output, (x,))
    score = best_history_score(data_root / item["history"])
    return {
        "id": item["id"],
        "name": item["name"],
        "class": "baseline",
        "score": round(score, 4),
        "metric": "balanced_accuracy",
        "file": item["file"],
        "sha256": sha256_file(output),
        "seqLen": WINDOWS_PER_SEQUENCE,
        "classes": CLASSES,
        "parameters": int(sum(p.numel() for p in model.parameters())),
        "inputShape": [WINDOWS_PER_SEQUENCE, channels, SAMPLES_PER_WINDOW],
        "inputKind": "raw-windows",
        "channels": channels,
        "verification": check,
        "opset": OPSET,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--braindecode-src", type=Path, default=DEFAULT_BRAINDECODE)
    parser.add_argument("--module-models", type=Path, default=DEFAULT_MODULE_MODELS)
    parser.add_argument("--weights-dir", type=Path, default=DEFAULT_WEIGHTS_DIR)
    args = parser.parse_args()

    torch.manual_seed(0)
    factory = load_relay_factory(args.data_root)
    chambon_cls, attn_cls = load_baseline_classes(args.braindecode_src)

    records = []
    for item in RELAY_WEIGHTS:
        records.append(export_relay(factory, args.data_root, item, args.weights_dir))
        print("relay", item["id"], "ok")
    for item in BASELINE_WEIGHTS:
        records.append(export_baseline(chambon_cls, attn_cls, args.data_root, item, args.weights_dir))
        print("baseline", item["id"], "ok")

    index = []
    verify = {"opset": OPSET, "classes": CLASSES, "models": records}
    for record in records:
        index.append(
            {
                "id": record["id"],
                "name": record["name"],
                "source": "relay",
                "class": record["class"],
                "score": record["score"],
                "metric": record["metric"],
                "file": record["file"],
                "sha256": record["sha256"],
                "seqLen": record["seqLen"],
                "classes": record["classes"],
                "parameters": record["parameters"],
                "inputKind": record["inputKind"],
                "inputShape": record["inputShape"],
                **({"channels": record["channels"]} if "channels" in record else {}),
            }
        )
    write_json(args.module_models / "index.json", index)
    write_json(args.module_models / "verify.json", verify)
    print(f"wrote {len(records)} models -> {args.weights_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
