#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera una familia de ruido independiente del motor BSS de Etapa 4.

Motivo (hallazgo de auditoria C6): entrenamiento y prueba compartian
NOISE-D0-001, por lo que la metrica de prueba estaba contaminada por fuga de
fuente. Este generador produce un mecanismo distinto (AR(1) coloreado +
armonicos de red), determinista, para usarse EXCLUSIVAMENTE en el split de
prueba. No se deriva de ninguna grabacion de campo ni del banco BSS.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "fuentes" / "NOISE-D0-IND-001.npz"
SEED = 20261030
N = 48000
FS = 4000.0


def main() -> int:
    rng = np.random.RandomState(SEED)
    t = np.arange(N) / FS

    # Ruido AR(1) correlacionado entre canales (mecanismo distinto del BSS)
    phi = 0.85
    common = np.zeros(N)
    common[0] = rng.randn()
    for i in range(1, N):
        common[i] = phi * common[i - 1] + math.sqrt(1.0 - phi ** 2) * rng.randn()

    mixing = np.array(
        [
            [1.0, 0.30, -0.20, 0.10],
            [0.25, 1.0, 0.15, -0.10],
            [-0.15, 0.20, 1.0, 0.25],
            [0.10, -0.10, 0.30, 1.0],
        ],
        dtype=float,
    )
    indep = rng.randn(N, 4)
    base = indep + common[:, None] * np.array([0.6, -0.4, 0.5, -0.3])
    noise4 = base @ mixing.T

    # Armonicos de red (50/60 Hz y sus multiplos)
    for f0 in (50.0, 60.0):
        for h in range(1, 5):
            f = f0 * h
            if f >= FS / 2:
                break
            amp = 0.15 / h
            ph = rng.uniform(0, 2 * math.pi, size=4)
            noise4 += amp * np.sin(2 * math.pi * f * t[:, None] + ph[None, :])

    # Normalizar a RMS unitaria por canal
    noise4 /= np.sqrt(np.mean(noise4 ** 2, axis=0, keepdims=True))

    aux = np.zeros((N, 1), dtype=float)
    noise = np.concatenate([noise4, aux], axis=1).astype(np.float32)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT,
        noise=noise,
        signal_residual=np.zeros_like(noise),
        channels=np.array(["Ex", "Ey", "Hx", "Hy", "Hz"]),
        fs=FS,
        start_s=0.0,
        stop_s=N / FS,
        duration_s=N / FS,
        mixing_matrix=mixing,
        kurtosis=np.zeros(4),
        coherence_max=np.zeros(4),
        gamma2_crit=np.zeros(4),
        leakage_fraction=np.zeros(4),
        episode_class=np.array(["independiente_arma"]),
        generator="P5-IND-NOISE-1.0.0",
        seed=SEED,
        independent_of_bss=True,
    )

    meta = {
        "file": str(OUT.relative_to(ROOT)).replace("\\", "/"),
        "generator": "P5-IND-NOISE-1.0.0",
        "seed": SEED,
        "n_samples": N,
        "fs_hz": FS,
        "independent_of_bss": True,
        "purpose": "Split de prueba P5 (elimina fuga NOISE-D0-001)",
    }
    (HERE / "fuentes" / "NOISE-D0-IND-001.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
