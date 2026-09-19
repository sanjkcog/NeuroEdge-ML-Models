# -*- coding: utf-8 -*-
"""1D-CNN for cnc_drift_1dcnn-timeseries — architecture exactly as specified in
`model_proposed.md` §Architecture (~11.4k parameters, dilated conv stack, GAP, scalar head).

Normalisation lives INSIDE the model (`TSModel`), so the exported ONNX graph starts with
Sub/Div and takes raw sensor values exactly as the device sends them. The terminal Sigmoid is
added only by `ScoreModel`, used for export and for computing scores at eval time — training uses
`BCEWithLogitsLoss` directly on `TSModel`'s raw logit for numerical stability
(model_proposed.md §Architecture, last row).
"""
from __future__ import annotations

import torch
from torch import nn


class Conv1DCore(nn.Module):
    """The conv trunk + head from model_proposed.md's architecture table. Input/output shapes are
    annotated per `pytorch-patterns.md`'s "explicit shape management" guidance."""

    def __init__(self, n_features: int = 3, dropout: float = 0.3) -> None:
        super().__init__()
        self.block1 = nn.Sequential(
            nn.Conv1d(n_features, 16, kernel_size=5, dilation=1, padding=2),
            nn.BatchNorm1d(16),
            nn.ReLU(inplace=True),
        )
        self.block2 = nn.Sequential(
            nn.Conv1d(16, 32, kernel_size=5, dilation=2, padding=4),
            nn.BatchNorm1d(32),
            nn.ReLU(inplace=True),
        )
        self.block3 = nn.Sequential(
            nn.Conv1d(32, 64, kernel_size=3, dilation=4, padding=4),
            nn.BatchNorm1d(64),
            nn.ReLU(inplace=True),
        )
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.head = nn.Sequential(
            nn.Linear(64, 32),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(32, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, 3, 64) — already normalised
        x = self.block1(x)  # -> (batch, 16, 64)
        x = self.block2(x)  # -> (batch, 32, 64)
        x = self.block3(x)  # -> (batch, 64, 64)
        x = self.pool(x)  # -> (batch, 64, 1)
        x = x.squeeze(-1)  # -> (batch, 64)
        return self.head(x)  # -> (batch, 1) raw logit


class TSModel(nn.Module):
    """Wraps `Conv1DCore` with train-fold normalisation baked in as buffers, so a raw sensor
    window in physical units is what both training and the exported ONNX graph consume
    (`use_case.lock.json: scaling: in_graph`, `model_proposed.md` §Export)."""

    def __init__(self, core: Conv1DCore, mean, std) -> None:
        super().__init__()
        self.core = core
        self.register_buffer("mean", torch.as_tensor(mean, dtype=torch.float32).view(1, -1, 1))
        self.register_buffer("std", torch.as_tensor(std, dtype=torch.float32).view(1, -1, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # x: (batch, features, window), raw units
        return self.core((x - self.mean) / self.std)


# The logit is clamped before Sigmoid so the exported float32 score stays strictly inside (0, 1)
# even for inputs far outside the training range.
LOGIT_CLAMP = 15.0


class ScoreModel(nn.Module):
    """Export / scoring wrapper: appends the terminal Sigmoid so the graph's output is bounded in
    (0, 1) (`model-codegen` invariant 8, `ml-model-package`'s "in the graph, not in a note")."""

    def __init__(self, model: TSModel) -> None:
        super().__init__()
        self.model = model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.sigmoid(self.model(x).clamp(-LOGIT_CLAMP, LOGIT_CLAMP))


def build_model(mean, std, n_features: int = 3, dropout: float = 0.3) -> TSModel:
    return TSModel(Conv1DCore(n_features=n_features, dropout=dropout), mean, std)


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())


if __name__ == "__main__":
    # Smoke check: shapes + parameter count, no data or GPU needed.
    import numpy as np

    m = build_model(mean=np.zeros(3), std=np.ones(3))
    x = torch.randn(8, 3, 64)
    out = m(x)
    assert out.shape == (8, 1), out.shape
    n_params = count_parameters(m)
    print(f"Conv1DCore+TSModel forward OK, output shape {tuple(out.shape)}, {n_params} parameters")
    scored = ScoreModel(m)(x)
    assert ((scored > 0) & (scored < 1)).all()
    print("ScoreModel (sigmoid) output strictly inside (0, 1): OK")
