#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-ejecucion independiente de la medicion P9 con la verdad del generador.

Motivo: etapa9/evaluador_ciego.py evalua el sondeo estratificado contra
rho=[100,10,500] / interfaces=[200,800], pero etapa3/config_p3.json genera
CTRL-03-STRATIFIED-S1-D0 con rho=[40,8,300] / interfaces=[30,120].
Este script repite exactamente la inyeccion del evaluador y mide el error
frente a la verdad realmente usada por el generador.

No modifica ningun artefacto oficial.
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

from etapa2.mt1d import z1d                      # noqa: E402
from etapa8.pipeline_armt import ARMTPipeline    # noqa: E402
from etapa9.evaluador_ciego import BlindEvaluator  # noqa: E402

MU0 = 4.0e-7 * math.pi
FS = 4000.0
FREQS = [125.0, 150.0, 200.0, 250.0, 300.0, 400.0, 500.0, 600.0, 800.0, 1000.0]

RHO_GEN = [40.0, 8.0, 300.0]
IFC_GEN = [30.0, 120.0]
RHO_EVAL = [100.0, 10.0, 500.0]
IFC_EVAL = [200.0, 800.0]


def truth(rho, ifc):
    z = z1d(FREQS, rho, ifc)
    out = {}
    for f, zz in zip(FREQS, z):
        w = 2.0 * math.pi * f
        out[f] = {
            "Zxy": complex(zz),
            "rho_a": float(abs(zz) ** 2 / (MU0 * w)),
            "phase_deg": float(math.degrees(math.atan2(zz.imag, zz.real))),
        }
    return out


def metrics(tf_list, ref):
    ez, er, ep = [], [], []
    for item in tf_list:
        f = item["f_hz"]
        if f in ref and item["Zxy"] is not None:
            zt = ref[f]["Zxy"]
            ez.append(abs(item["Zxy"] - zt) / abs(zt) * 100.0)
            if item.get("rho_a_xy"):
                er.append(abs(math.log10(item["rho_a_xy"]) - math.log10(ref[f]["rho_a"])))
            ep.append(abs(item["phase_xy_deg"] - ref[f]["phase_deg"]))
    pct = lambda v, q: float(np.percentile(v, q)) if v else None  # noqa: E731
    return {
        "median_err_z_pct": pct(ez, 50),
        "median_err_rho_dec": pct(er, 50),
        "median_err_phase_deg": pct(ep, 50),
        "p90_err_rho_dec": pct(er, 90),
        "p90_err_phase_deg": pct(ep, 90),
        "p95_err_z_pct": pct(ez, 95),
    }


def main() -> int:
    d2 = np.load(ROOT / "etapa3" / "datos" / "CTRL-03-STRATIFIED-S1-D0.npz")
    s_strat = np.stack([d2["Ex"], d2["Ey"], d2["Hx"], d2["Hy"]], axis=1).astype(np.float32)

    d_noise = np.load(ROOT / "etapa4" / "noise_bank" / "NOISE-D0-001.npz")
    n_raw = d_noise["noise"][:, :4].astype(np.float32)

    n_start = int(4.0 * FS)
    n_len = min(len(n_raw), len(s_strat) - n_start, int(8.0 * FS))
    p_s = np.mean(s_strat[n_start:n_start + n_len] ** 2)
    p_n = np.mean(n_raw[:n_len] ** 2) + 1e-12
    scale_n = math.sqrt((p_s / 1.0) / p_n)

    x_contam = s_strat.copy()
    x_contam[n_start:n_start + n_len] += n_raw[:n_len] * scale_n

    supp = ROOT / "banco_sintetico" / "soporte_S1.json"
    pipe = ARMTPipeline(config_path="etapa8/config_p8.json", device="cpu")
    ev = BlindEvaluator(config_path=str(ROOT / "etapa9" / "config_p9.json"), device="cpu")

    tf_b0 = pipe.estimate_transfer_functions(x_contam, FS, FREQS)
    res_b4 = pipe.process_continuous_record(x_contam, "VERIF-SND-02", "D0", FS, support_source=supp)
    tf_b4 = pipe.estimate_transfer_functions(res_b4["s_hat"], FS, FREQS)
    tf_b8 = ev.run_benchmark_b8_wiener(x_contam, FS, FREQS)
    tf_clean = pipe.estimate_transfer_functions(s_strat, FS, FREQS)

    ref_gen = truth(RHO_GEN, IFC_GEN)
    ref_eval = truth(RHO_EVAL, IFC_EVAL)

    report = {
        "motivo": "El evaluador P9 usa un modelo de verdad distinto al del generador",
        "modelo_generador": {"rho": RHO_GEN, "interfaces": IFC_GEN},
        "modelo_usado_por_evaluador": {"rho": RHO_EVAL, "interfaces": IFC_EVAL},
        "inyeccion_replicada": {
            "n_start": n_start,
            "n_len": n_len,
            "scale_n": float(scale_n),
            "snr_db": 0.0,
        },
        "senal_limpia_vs_verdad_generador": metrics(tf_clean, ref_gen),
        "benchmarks_vs_verdad_generador": {
            "B0": metrics(tf_b0, ref_gen),
            "B4": metrics(tf_b4, ref_gen),
            "B8": metrics(tf_b8, ref_gen),
        },
        "benchmarks_vs_verdad_del_evaluador": {
            "B0": metrics(tf_b0, ref_eval),
            "B4": metrics(tf_b4, ref_eval),
            "B8": metrics(tf_b8, ref_eval),
        },
        "ventanas_intervenidas_pct_b4": res_b4.get("intervened_pct"),
    }

    out = ROOT / "verificacion_rigor" / "reevaluacion_p9_verdad_correcta.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
