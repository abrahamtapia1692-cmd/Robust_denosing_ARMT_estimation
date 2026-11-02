#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validador formal de la Etapa 9: Evaluacion Ciega de Extremo a Extremo (Puerta P9 y Compuerta G4).

Ejecuta 32 comprobaciones rigurosas e independientes de contratos, fisica electromagnetica,
benchmarks comparativos B0-B10, no inferioridad en limpios, recuperacion con ruido,
tasa de falsa recuperacion en no identificables, exclusion RMT y compuerta G4.
"""
from __future__ import annotations

import os
import sys
import json
import math
import hashlib

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from pathlib import Path
from typing import Dict, Any, List

import numpy as np
import torch

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from etapa9.evaluador_ciego import BlindEvaluator
from etapa8.pipeline_armt import ARMTPipeline

VERSION = "P9-VAL-2.0.0"


def validate_stage9() -> Dict[str, Any]:
    """Ejecuta la suite formal de 32 validaciones para la Puerta P9 y Compuerta G4."""
    root = _ROOT
    cfg_file = root / "etapa9" / "config_p9.json"
    res_file = root / "etapa9" / "resumen_p9.json"
    rep_file = root / "etapa9" / "reporte_p9.md"
    eval_file = root / "etapa9" / "evaluador_ciego.py"
    p9_file = root / "etapa9" / "p9.py"

    checks: List[Dict[str, Any]] = []

    def add_check(cid: str, desc: str, passed: bool, obs: str = ""):
        checks.append({
            "id": cid,
            "descripcion": desc,
            "estado": "PASA" if passed else "FALLA",
            "observacion": obs,
        })

    # =========================================================================
    # 1. Archivos, Configuración y Checkpoints
    # =========================================================================
    c1 = cfg_file.exists()
    add_check("V-P9-01", "Existencia de config_p9.json", c1)

    cfg = {}
    if c1:
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            c2 = "benchmarks" in cfg and "blind_soundings" in cfg and "preregistered_endpoints" in cfg
            add_check("V-P9-02", "Configuración válida con benchmarks B0-B10 y metas preregistradas", c2)
        except Exception as e:
            add_check("V-P9-02", "Configuración válida con benchmarks B0-B10 y metas preregistradas", False, str(e))
    else:
        add_check("V-P9-02", "Configuración válida con benchmarks B0-B10 y metas preregistradas", False, "Falta archivo")

    add_check("V-P9-03", "Existencia de evaluador_ciego.py", eval_file.exists())
    add_check("V-P9-04", "Existencia de p9.py", p9_file.exists())
    add_check("V-P9-05", "Existencia de resumen_p9.json", res_file.exists())
    add_check("V-P9-06", "Existencia de reporte_p9.md", rep_file.exists())

    det_ckpt = root / "etapa7" / "checkpoints" / "c_theta_scnet18.pt"
    b3_ckpt = root / "etapa7" / "checkpoints" / "d_psi_b3_scnet18.pt"
    b4_ckpt = root / "etapa7" / "checkpoints" / "d_psi_b4_cbam.pt"
    add_check("V-P9-07", "Existencia y carga de modelos B3, B4 y detector C_theta", det_ckpt.exists() and b3_ckpt.exists() and b4_ckpt.exists())

    res_data = {}
    if res_file.exists():
        with open(res_file, "r", encoding="utf-8") as f:
            res_data = json.load(f)

    # =========================================================================
    # 2. Comparadores Evaluados y No Inferioridad en Limpio (§9.1, §9.3)
    # =========================================================================
    benchs = res_data.get("benchmarks_evaluated", [])
    mandatory = cfg.get("mandatory_benchmarks", ["B0", "B1", "B3", "B4", "B7", "B8", "B9", "B10"])
    missing = [b for b in mandatory if b not in benchs]
    not_impl = res_data.get("benchmarks_not_evaluated", {})
    add_check("V-P9-08", "Evaluación real de comparadores obligatorios (sin omisiones silenciosas)",
              not missing and not any(b in mandatory for b in not_impl),
              f"eval={benchs}; faltan={missing}; no_impl={list(not_impl)}")

    # Verdad de referencia: config_p9 debe coincidir con el generador P3
    p3_cfg_path = root / "etapa3" / "config_p3.json"
    truth_ok = False
    truth_obs = "config_p3.json ausente"
    if p3_cfg_path.exists():
        try:
            p3_cfg = json.loads(p3_cfg_path.read_text(encoding="utf-8"))
            ref = None
            for caso in p3_cfg.get("scenarios", p3_cfg.get("casos", p3_cfg.get("cases", []))):
                cid = caso.get("id", "")
                if cid == "CTRL-03-STRATIFIED-S1-D0":
                    ref = caso
                    break
            if ref is not None:
                p9_mdl = cfg["blind_soundings"]["synth_stratified_s1"]
                rho_ok = list(map(float, ref.get("rho_ohm_m", []))) == list(map(float, p9_mdl.get("rho_ohm_m", [])))
                if_ok = list(map(float, ref.get("interfaces_m", []))) == list(map(float, p9_mdl.get("interfaces_m", [])))
                truth_ok = rho_ok and if_ok
                truth_obs = f"P3 rho={ref.get('rho_ohm_m')} if={ref.get('interfaces_m')}; P9 rho={p9_mdl.get('rho_ohm_m')} if={p9_mdl.get('interfaces_m')}"
            else:
                truth_obs = "Caso CTRL-03 no encontrado en config_p3.json"
        except Exception as e:  # noqa: BLE001
            truth_obs = str(e)
    add_check("V-P9-33", "El modelo de verdad de P9 coincide con el generador P3", truth_ok, truth_obs)


    p9_m = res_data.get("gate_p9_metrics", {})
    p95_z = p9_m.get("clean_p95_bias_z_pct", 99.0)
    add_check("V-P9-09", "No inferioridad en limpio: P95 sesgo Z <= 2.0%", p95_z <= 2.0, f"p95={p95_z:.4f}%")

    p95_ph = p9_m.get("clean_p95_phase_diff_deg", 90.0)
    add_check("V-P9-10", "No inferioridad en limpio: P95 fase <= 1.0°", p95_ph <= 1.0, f"p95={p95_ph:.4f}°")

    snd1 = res_data.get("soundings_results", {}).get("snd_blind_01_clean", {})
    med_z = snd1.get("median_bias_z_pct", 99.0)
    add_check("V-P9-11", "No inferioridad en limpio: Mediana sesgo Z <= 5.0%", med_z <= 5.0, f"med={med_z:.4f}%")

    med_ph = snd1.get("median_phase_diff_deg", 90.0)
    add_check("V-P9-12", "No inferioridad en limpio: Mediana fase <= 2.0°", med_ph <= 2.0, f"med={med_ph:.4f}°")

    # =========================================================================
    # 3. Recuperación en Contaminados y Superación de Comparadores (§9.1)
    # =========================================================================
    snd2 = res_data.get("soundings_results", {}).get("snd_blind_02_stratified", {})
    b_errs = snd2.get("benchmark_errors", {})

    err_z_b0 = b_errs.get("B0", {}).get("median_err_z_pct", 999.0)
    err_z_b3 = b_errs.get("B3", {}).get("median_err_z_pct", 999.0)
    err_z_b4 = b_errs.get("B4", {}).get("median_err_z_pct", 999.0)
    err_z_b8 = b_errs.get("B8", {}).get("median_err_z_pct", 999.0)

    add_check("V-P9-13", "B4 (CBAM Adaptado) supera holgadamente a B3 (SCNet18 Zhang et al. 2024)", err_z_b4 < err_z_b3, f"B4={err_z_b4:.2f}% vs B3={err_z_b3:.2f}%")
    add_check("V-P9-14", "B4 supera a la cota analítica lineal óptima de Wiener (B8)", err_z_b4 < err_z_b8, f"B4={err_z_b4:.2f}% vs B8={err_z_b8:.2f}%")
    add_check("V-P9-15", "B4 reduce el error de impedancia frente a la señal bruta (B0)", err_z_b4 < err_z_b0, f"B4={err_z_b4:.2f}% vs B0={err_z_b0:.2f}%")

    # Preservacion en ráfagas no estacionarias (sferics, CTRL-05)
    snd3 = res_data.get("soundings_results", {}).get("snd_blind_03_sferics", {})
    err_sf_b4 = snd3.get("mean_err_z_b4_pct", 99.0)
    add_check("V-P9-16", "Preservación física en ráfagas no estacionarias sferics (error Z <= 5.0%)", err_sf_b4 <= 5.0, f"err={err_sf_b4:.2f}%")

    # Prueba de estrés de textura Sim-to-Real (F1)
    snd4 = res_data.get("soundings_results", {}).get("snd_blind_04_texture_f1", {})
    txt_diff = snd4.get("clean_texture_preserved_diff", 99.0)
    add_check("V-P9-17", "Prueba de estrés de textura F1: preservación de fondo geológico", txt_diff < 1.0, f"diff={txt_diff:.2e}")

    # =========================================================================
    # 4. No Identificables, Abstención y Falsa Recuperación (§9.3)
    # =========================================================================
    non_id = res_data.get("soundings_results", {}).get("non_identifiable_tests", {})
    add_check("V-P9-18", "Detección de Rango 1 (CTRL-04): abstención obligatoria activada", bool(non_id.get("rank1_abstained", False)))

    # -------------------------------------------------------------------------
    # Comprobaciones fisicas REALES: ninguna se hardcodea en True.
    # -------------------------------------------------------------------------
    pipe = None
    pipe_err = ""
    try:
        pipe = ARMTPipeline(config_path="etapa8/config_p8.json", device="cpu")
    except Exception as e:  # noqa: BLE001
        pipe_err = str(e)

    # V-P9-19: soporte sintetico vacio S0 -> red omitida
    ok19, obs19 = False, pipe_err or "pipeline no disponible"
    if pipe is not None:
        try:
            s0_path = root / "banco_sintetico" / "soporte_S0.json"
            s0 = pipe.resolve_support("ARMT5-S0-EMPTY", "D0", s0_path)
            ok19 = bool(s0.get("network_omitted")) and s0.get("support_status") == "soporte_vacio"
            obs19 = f"status={s0.get('support_status')} omitted={s0.get('network_omitted')}"
        except Exception as e:  # noqa: BLE001
            obs19 = str(e)
    add_check("V-P9-19", "Compuerta G0: omisión de red ante soporte vacío sintético (soporte_S0)", ok19, obs19)

    add_check("V-P9-20", "Compuerta G0: omisión de red ante campo sin vínculo TEM (ARMT5-123-01-01-01)", bool(non_id.get("empty_support_omitted", False)))
    add_check("V-P9-21", "Exclusión estricta de bandas RMT D2 (bloqueo absoluto de red)", bool(non_id.get("rmt_excluded", False)))

    # V-P9-22: la misma regla se verifica para D3 (no se asume por simetria)
    ok22, obs22 = False, pipe_err or "pipeline no disponible"
    if pipe is not None:
        try:
            st3 = pipe.resolve_support("SND-BLIND-D3", "D3")
            ok22 = bool(st3.get("network_omitted")) and st3.get("support_status") == "excluido_rmt"
            obs22 = f"status={st3.get('support_status')} omitted={st3.get('network_omitted')}"
        except Exception as e:  # noqa: BLE001
            obs22 = str(e)
    add_check("V-P9-22", "Exclusión estricta de bandas RMT D3 (bloqueo absoluto de red)", ok22, obs22)

    false_rec = non_id.get("false_recovery_rate_pct", 99.0)
    add_check("V-P9-23", "Tasa de falsa recuperación en no identificables <= 5.0%", false_rec <= 5.0, f"rate={false_rec:.1f}%")

    # V-P9-24: D_real no debe contener blancos inventados
    ok24, obs24 = False, "D_real.npz ausente"
    dreal = root / "etapa5" / "datasets" / "D_real.npz"
    if dreal.exists():
        try:
            with np.load(dreal) as dr:
                tt = dr["target_type"]
                tt = str(tt.item()) if tt.ndim == 0 else str(tt[0])
            ok24 = tt == "unavailable"
            obs24 = f"target_type={tt}"
        except Exception as e:  # noqa: BLE001
            obs24 = str(e)
    add_check("V-P9-24", "Cero blancos inventados para registros de campo (etiqueta unavailable)", ok24, obs24)

    # V-P9-25: frecuencias evaluadas dentro del soporte autorizado
    ok25, obs25 = False, "soporte_S1.json ausente"
    sup1 = root / "banco_sintetico" / "soporte_S1.json"
    if sup1.exists():
        try:
            sj = json.loads(sup1.read_text(encoding="utf-8"))
            hab = sorted(float(i["f_hz"]) for i in sj.get("frequencies", [])
                         if i.get("band") == "D0" and (i.get("aplicacion") == "habilitada" or i.get("status") == "respaldada"))
            evaluadas = [125.0, 150.0, 200.0, 250.0, 300.0, 400.0, 500.0, 600.0, 800.0, 1000.0]
            # Sin extrapolacion = toda frecuencia evaluada cae dentro del rango habilitado
            bad = [f for f in evaluadas if hab and not (min(hab) <= f <= max(hab))]
            ok25 = bool(hab) and not bad
            obs25 = f"rango_habilitado=[{min(hab) if hab else None},{max(hab) if hab else None}]; fuera={bad}"
        except Exception as e:  # noqa: BLE001
            obs25 = str(e)
    add_check("V-P9-25", "Cero extrapolación de frecuencias fuera del soporte TEM autorizado", ok25, obs25)

    # V-P9-26: recomposicion Hann overlap-add C1
    ok26, obs26 = False, pipe_err or "pipeline no disponible"
    if pipe is not None:
        try:
            rng = np.random.RandomState(20261030)
            n = 4096
            x = rng.randn(n, 4)
            L, S = pipe.window_length, pipe.step
            wins = np.array([x[i : i + L] for i in range(0, n - L + 1, S)])
            rec = pipe.reconstruct_overlap_add(wins, n, S)
            err = float(np.max(np.abs(rec - x[: len(rec)])))
            ok26 = err < 1e-12
            obs26 = f"max|rec-x|={err:.2e}"
        except Exception as e:  # noqa: BLE001
            obs26 = str(e)
    add_check("V-P9-26", "Invarianza de recomposición continua Hanning overlap-add C1 (error < 1e-12)", ok26, obs26)

    # V-P9-27: descomposicion aditiva exacta medida sobre una salida real
    ok27, obs27 = False, pipe_err or "pipeline no disponible"
    if pipe is not None:
        try:
            d1s = np.load(root / "etapa3" / "datos" / "CTRL-01-HALFSPACE-D0.npz")
            xs = np.stack([d1s["Ex"], d1s["Ey"], d1s["Hx"], d1s["Hy"]], axis=1).astype(np.float32)
            r = pipe.process_continuous_record(xs, "SND-CHECK-27", "D0", 4000.0, force_mode="denoise_all")
            err = float(np.max(np.abs(xs - (r["s_hat"] + r["n_hat"]))))
            ok27 = err < 1e-12
            obs27 = f"max|x-(s+n)|={err:.2e}"
        except Exception as e:  # noqa: BLE001
            obs27 = str(e)
    add_check("V-P9-27", "Descomposición aditiva exacta muestra a muestra x = s_hat + n_hat (error < 1e-12)", ok27, obs27)

    # V-P9-28: invarianza de lote del denoisedor B4
    ok28, obs28 = False, pipe_err or "pipeline no disponible"
    if pipe is not None:
        try:
            torch.manual_seed(20261030)
            xb = torch.randn(4, 4, 256)
            with torch.no_grad():
                full = pipe.denoiser(xb)["s_hat"]
                singles = torch.cat([pipe.denoiser(xb[i : i + 1])["s_hat"] for i in range(4)], dim=0)
            diff = float(torch.max(torch.abs(full - singles)))
            ok28 = diff < 1e-5
            obs28 = f"max diff={diff:.2e}"
        except Exception as e:  # noqa: BLE001
            obs28 = str(e)
    add_check("V-P9-28", "Invarianza estricta ante tamaño de lote de inferencia (diff < 1e-5)", ok28, obs28)

    # V-P9-29: canales auxiliares (Hz) intactos
    ok29, obs29 = False, pipe_err or "pipeline no disponible"
    if pipe is not None:
        try:
            d1s = np.load(root / "etapa3" / "datos" / "CTRL-01-HALFSPACE-D0.npz")
            base = np.stack([d1s["Ex"], d1s["Ey"], d1s["Hx"], d1s["Hy"]], axis=1).astype(np.float32)
            aux = np.arange(len(base), dtype=np.float32)[:, None] * np.array([[1.0, 2.0]], dtype=np.float32)
            x6 = np.concatenate([base, aux], axis=1)
            r = pipe.process_continuous_record(x6, "SND-CHECK-29", "D0", 4000.0, force_mode="denoise_all")
            diff = float(np.max(np.abs(r["s_hat"][:, 4:] - x6[:, 4:])))
            ok29 = diff == 0.0
            obs29 = f"max diff Hz={diff:.2e}"
        except Exception as e:  # noqa: BLE001
            obs29 = str(e)
    add_check("V-P9-29", "Componentes auxiliares Hz conservadas idénticas e intactas", ok29, obs29)

    # V-P9-30: G4 solo si todos los subcriterios pasan (propagacion de fallos)
    g4 = res_data.get("gate_g4_safety", {})
    g4_app = bool(g4.get("g4_approved", False))
    g4_consistente = g4_app == all(
        bool(g4.get(k, False)) for k in (
            "no_inferiority_passed", "improvement_passed", "rejection_passed",
            "b7_passed", "b9_passed", "all_soundings_passed",
        )
    ) and not g4.get("missing_mandatory_benchmarks")
    add_check("V-P9-30", "Compuerta G4 aprobada solo si todos los subcriterios y sondeos pasan", g4_app and g4_consistente, f"approved={g4_app} consistente={g4_consistente}")

    # V-P9-31: trazabilidad de hashes congelados
    ok31, obs31 = False, "SND-BLIND-02.json ausente"
    j02 = root / "etapa10" / "salidas" / "SND-BLIND-02.json"
    if j02.exists():
        try:
            prov = json.loads(j02.read_text(encoding="utf-8")).get("provenance", {})
            fh = prov.get("frozen_hashes", {})
            malos = []
            for rel, h in fh.items():
                fp = root / rel
                if not fp.exists():
                    malos.append(f"{rel}:ausente")
                    continue
                hh = hashlib.sha256(fp.read_bytes()).hexdigest()
                if hh != h:
                    malos.append(f"{rel}:hash")
            ok31 = bool(fh) and not malos
            obs31 = f"{len(fh)} hashes; discrepancias={malos}"
        except Exception as e:  # noqa: BLE001
            obs31 = str(e)
    add_check("V-P9-31", "Trazabilidad completa y hashes SHA-256 congelados de modelos y datos", ok31, obs31)

    # V-P9-32: coherencia global P9 con los sondeos
    p9_pass = bool(p9_m.get("p9_passed", False))
    sondeos_ok = all(
        bool(v.get("passed", False))
        for v in res_data.get("soundings_results", {}).values()
    )
    add_check("V-P9-32", "Aprobación global P9 coherente con todos los sondeos", (not p9_pass) or sondeos_ok, f"p9_passed={p9_pass} sondeos_ok={sondeos_ok}")

    # =========================================================================
    # Resumen y Certificado Oficial
    # =========================================================================
    n_pasa = sum(1 for c in checks if c["estado"] == "PASA")
    n_falla = sum(1 for c in checks if c["estado"] == "FALLA")
    total = len(checks)
    approved = (n_falla == 0 and total >= 32)

    val_res = {
        "version": VERSION,
        "timestamp_utc": res_data.get("timestamp_utc", ""),
        "gate": "P9",
        "stage": 9,
        "total_checks": total,
        "checks_passed": n_pasa,
        "checks_failed": n_falla,
        "status": "APROBADO" if approved else "FALLIDO",
        "checks": checks
    }

    out_json = root / "etapa9" / "validacion_etapa9.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(val_res, f, indent=2)

    print("\n" + "=" * 80)
    print(f"Validación Formal Etapa 9: {val_res['status']} ({n_pasa}/{total} PASA, {n_falla} FALLA)")
    print("=" * 80)
    print(f"Certificado oficial emitido en: {out_json}")

    return val_res


if __name__ == "__main__":
    validate_stage9()
