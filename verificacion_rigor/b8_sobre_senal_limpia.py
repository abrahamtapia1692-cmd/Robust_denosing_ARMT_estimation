#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comprueba el filtro B8 (Wiener) sobre senal LIMPIA, sin ruido inyectado.

Si la 'cota lineal optima' degrada una senal limpia, el comparador B8 no es
una cota valida y la conclusion 'B4 supera a Wiener' carece de base.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from etapa2.mt1d import z1d                    # noqa: E402
from etapa9.evaluador_ciego import BlindEvaluator  # noqa: E402

FREQS = [125.0, 150.0, 200.0, 250.0, 300.0, 400.0, 500.0, 600.0, 800.0, 1000.0]


def main() -> int:
    d = np.load(ROOT / "etapa3" / "datos" / "CTRL-03-STRATIFIED-S1-D0.npz")
    s = np.stack([d["Ex"], d["Ey"], d["Hx"], d["Hy"]], axis=1).astype(np.float32)
    truth = z1d(FREQS, [40.0, 8.0, 300.0], [30.0, 120.0])
    ev = BlindEvaluator(config_path=str(ROOT / "etapa9" / "config_p9.json"), device="cpu")
    tf = ev.run_benchmark_b8_wiener(s, 4000.0, FREQS)
    rows = []
    for item, f, z in zip(tf, FREQS, truth):
        rows.append({
            "f_hz": f,
            "err_z_pct": abs(item["Zxy"] - z) / abs(z) * 100.0,
            "phase_est": item["phase_xy_deg"],
            "phase_true": math.degrees(math.atan2(z.imag, z.real)),
        })
    out = {
        "descripcion": "B8/Wiener aplicado a la senal limpia (sin ruido)",
        "median_err_z_pct": float(np.median([r["err_z_pct"] for r in rows])),
        "rows": rows,
    }
    p = ROOT / "verificacion_rigor" / "b8_sobre_senal_limpia.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
