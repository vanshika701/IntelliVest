"""The LSTM half of the LSTM + LightGBM ensemble (model 4.0.0).

The LSTM reads the last SEQ_LEN trading days of a stock as a sequence of
daily, scale-free channels and outputs, for every horizon in HORIZON_GRID,
a 10th/50th/90th percentile of the volatility-scaled excess return and a
chance of beating the Nifty. Used unchanged by ml/train_hybrid_lstm_lightgbm.py
(training) and the prediction service (serving), so both see the same inputs.

torch is imported lazily: the app runs without it when only the
LightGBM model is used.
"""

import numpy as np
import pandas as pd

from app.services.prediction.horizon import HORIZON_GRID

SEQ_LEN = 64
CHANNELS = 7
H = len(HORIZON_GRID)
OFFSETS = np.arange(-SEQ_LEN + 1, 1)


def sequence_inputs(f: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Daily channels, one row per row of `f` (compute_features output,
    sorted by ticker and date), and whether the row has SEQ_LEN rows of
    history in the same series. Returns are in units of recent volatility,
    so one network fits stocks of every size."""
    keys = [f["ticker"], f["segment"]]
    g = f.groupby(keys, sort=False)
    r = np.log(f["close"]) - np.log(g["close"].shift(1))
    m = np.log(f["nifty_close"]) - np.log(g["nifty_close"].shift(1))
    vol, mvol = f["vol_63"], f["mkt_vol_21"].replace(0, np.nan)
    volume = f["volume"].replace(0, np.nan)
    vol_mean = volume.groupby(keys).transform(lambda s: s.rolling(63, min_periods=20).mean())
    with np.errstate(divide="ignore", invalid="ignore"):
        channels = [
            (r / vol).clip(-8, 8),
            (m / mvol).clip(-8, 8),
            ((r - m) / vol).clip(-8, 8),
            np.log(volume / vol_mean).clip(-4, 4),
            (np.log(f["vix"].clip(lower=0.05)) - np.log(0.18)) / 0.3,
            f["dist_high252"] / 0.3,
            f["dist_ma50"] / 0.1,
        ]
    x = np.stack([np.asarray(c, dtype=np.float64) for c in channels], axis=1)
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
    valid = (g.cumcount() >= SEQ_LEN - 1).to_numpy()
    return x, valid


def windows(x: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """(len(idx), SEQ_LEN, CHANNELS): the SEQ_LEN rows ending at each idx."""
    return x[idx[:, None] + OFFSETS]


def build_net(hidden: int = 48, dropout: float = 0.2):
    import torch
    from torch import nn

    class SequenceNet(nn.Module):
        """LSTM -> per horizon: low/mid/high (ordered by construction) and a beat logit."""

        def __init__(self) -> None:
            super().__init__()
            self.lstm = nn.LSTM(CHANNELS, hidden, batch_first=True)
            self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, 64), nn.ReLU(), nn.Linear(64, H * 4))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            _, (h, _) = self.lstm(x)
            raw = self.head(h[-1]).view(-1, H, 4)
            mid = raw[..., 0]
            low = mid - nn.functional.softplus(raw[..., 1])
            high = mid + nn.functional.softplus(raw[..., 2])
            return torch.stack([low, mid, high, raw[..., 3]], dim=-1)

    return SequenceNet()


def predict(net, x: np.ndarray, idx: np.ndarray, batch: int = 8192) -> np.ndarray:
    """(len(idx), H, 4): low, mid, high (scaled units) and chance of beating."""
    import torch

    net.eval()
    out = np.empty((len(idx), H, 4), dtype=np.float32)
    with torch.no_grad():
        for s in range(0, len(idx), batch):
            o = net(torch.from_numpy(windows(x, idx[s : s + batch])))
            o[..., 3] = torch.sigmoid(o[..., 3])
            out[s : s + batch] = o.numpy()
    return out
