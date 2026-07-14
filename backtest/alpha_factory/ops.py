"""Composable operators on wide frames (index=UTC days, columns=coins). Pure pandas."""
import numpy as np
import pandas as pd


def ts_mean(df, w): return df.rolling(w).mean()
def ts_std(df, w):  return df.rolling(w).std()
def ts_sum(df, w):  return df.rolling(w).sum()
def delta(df, w):   return df - df.shift(w)
def ewma(df, span): return df.ewm(span=span, adjust=False).mean()
def rolling_skew(df, w): return df.rolling(w).skew()
def rolling_kurt(df, w): return df.rolling(w).kurt()


def ts_rank(df, w):
    """Percentile (0..1) of today's value within the trailing w-window."""
    return df.rolling(w).rank(pct=True)


def decay(df, w):
    """Linear-decay weighted mean over w bars, newest heaviest (weights 1..w normalized)."""
    wts = np.arange(1, w + 1, dtype=float)
    wts /= wts.sum()
    return df.rolling(w).apply(lambda x: float(np.dot(x, wts)), raw=True)


def ts_corr(a, b, w):
    return a.rolling(w).corr(b)


def cs_rank(df):
    """Cross-sectional rank per day scaled to 0..1 (bottom=0, top=1)."""
    n = df.count(axis=1)
    return (df.rank(axis=1) - 1).div(n - 1, axis=0)


def cs_z(df):
    return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1).replace(0, np.nan), axis=0)


def rsi(df, n):
    d = df.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + up / dn.replace(0, np.nan))).fillna(50)
