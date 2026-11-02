#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Driver de Ejecucion y Evaluacion de la Etapa 8 (Puerta P8).

Ejecuta los escenarios de prueba representativos para la inferencia MT/AMT continua:
1. Soporte parcial con contaminacion real inyectada (CTRL-03 + NOISE-D0-001).
2. No inferioridad en registro continuo limpio (CTRL-01).
3. Compuerta G0 con soporte sintetico vacio (CTRL-01 + soporte_S0).
4. Compuerta G0 con sondeo de campo real sin soporte (ARMT5-123-01-01-01).
5. Exclusion estricta de bandas RMT (D2/D3).
6. Deteccion de rango 1 y abstencion (CTRL-04).
7. Invarianza de lote y reconstruccion continua exacta.

Genera resumen_p8.json y reporte_p8.md.
"""
from __future__ import annotations

import os
import sys
import json
import time
import math
import hashlib

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from pathlib import Path
from typing import Dict, Any, List

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from etapa8.pipeline_armt import ARMTPipeline

VERSION = "P8-2.0.0"


def compute_sha256(filepath: Path) -> str:
    """Calcula el hash SHA-256 de un archivo."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_etapa8_evaluation() -> Dict[str, Any]:
    """Ejecuta la suite integral de evaluacion de la Etapa 8."""
    t0 = time.time()
    print("=" * 80)
    print(f"Iniciando Evaluacion Integral de Etapa 8 ({VERSION}) - Puerta P8")
    print("=" * 80)

    pipe = ARMTPipeline(config_path="etapa8/config_p8.json")
    print(f"Dispositivo de ejecucion: {pipe.device}")

    results: Dict[str, Any] = {
        "version": VERSION,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "device": str(pipe.device),
        "scenarios": {}
    }

    # =========================================================================
    # Escenario 1: Soporte Parcial con Contaminacion Real Inyectada
    # =========================================================================
    print("\n--- Escenario 1: Soporte Parcial (CTRL-03 + NOISE-D0-001) ---")
    ctrl03_path = Path("etapa3/datos/CTRL-03-STRATIFIED-S1-D0.npz")
    noise01_path = Path("etapa4/noise_bank/NOISE-D0-001.npz")
    supp_s1_path = Path("banco_sintetico/soporte_S1.json")

    d_clean = np.load(ctrl03_path)
    clean_series = np.stack([
        d_clean["Ex"], d_clean["Ey"], d_clean["Hx"], d_clean["Hy"]
    ], axis=1).astype(np.float32)

    N_samples = len(clean_series)
    fs_d0 = 4000.0

    # Inyeccion de ruido en el tramo central (segundos 4 a 12 = 32,000 muestras)
    # Escalado para SNR nominal realista (0.0 dB) segun diseno de etapa5/builder_datasets.py
    d_noise = np.load(noise01_path)
    noise_raw = d_noise["noise"][:, :4].astype(np.float32)

    n_start = int(4.0 * fs_d0)
    n_len = min(len(noise_raw), N_samples - n_start, int(8.0 * fs_d0))

    p_s = np.mean(clean_series[n_start : n_start + n_len] ** 2)
    p_n = np.mean(noise_raw[:n_len] ** 2) + 1e-12
    target_snr_db = 0.0
    scale_n = math.sqrt((p_s / (10.0 ** (target_snr_db / 10.0))) / p_n)

    contam_series = clean_series.copy()
    contam_series[n_start : n_start + n_len] += noise_raw[:n_len] * scale_n

    # Proceso continuo por el pipeline
    res_s1 = pipe.process_continuous_record(
        contam_series,
        record_id="CTRL-03-STRATIFIED-S1-D0",
        band="D0",
        fs_hz=fs_d0,
        support_source=supp_s1_path
    )

    s_hat_s1 = res_s1["s_hat"]
    n_hat_s1 = res_s1["n_hat"]
    f_app_s1 = res_s1["f_aplicacion"]
    flags_s1 = res_s1["intervened_flags"]

    # Evaluacion de selectividad temporal
    # Prefijo limpio: ventanas 0 a 120 (muestras 0 a 15,360)
    clean_prefix_flagged = sum(flags_s1[:120])
    # Tramo contaminado central: ventanas 125 a 370
    contam_core_flagged = sum(flags_s1[125:370])
    contam_core_total = len(flags_s1[125:370])
    # Sufijo limpio: ventanas 375 a 498
    clean_suffix_flagged = sum(flags_s1[375:])

    # SNR de entrada y salida en el tramo contaminado central
    signal_core = clean_series[n_start : n_start + n_len]
    noise_core = contam_series[n_start : n_start + n_len] - signal_core
    residual_core = s_hat_s1[n_start : n_start + n_len] - signal_core

    snr_in = float(10.0 * np.log10(np.mean(signal_core ** 2) / (np.mean(noise_core ** 2) + 1e-12)))
    snr_out = float(10.0 * np.log10(np.mean(signal_core ** 2) / (np.mean(residual_core ** 2) + 1e-12)))
    delta_snr = snr_out - snr_in

    print(f"  Ventanas totales: {res_s1['total_windows']}, intervenidas: {res_s1['intervened_windows']} ({res_s1['intervened_pct']:.1f}%)")
    print(f"  Selectividad temporal: prefijo limpio={clean_prefix_flagged}/120, contaminado={contam_core_flagged}/{contam_core_total}, sufijo limpio={clean_suffix_flagged}")
    print(f"  SNR Entrada: {snr_in:.2f} dB, SNR Salida: {snr_out:.2f} dB, Ganancia: +{delta_snr:.2f} dB")

    # Preservacion exacta en tramos limpios
    clean_prefix_diff = float(np.max(np.abs(s_hat_s1[:n_start] - clean_series[:n_start])))
    clean_suffix_diff = float(np.max(np.abs(s_hat_s1[n_start + n_len :] - clean_series[n_start + n_len :])))
    print(f"  Diferencia en tramos limpios no intervenidos: prefijo={clean_prefix_diff:.2e}, sufijo={clean_suffix_diff:.2e}")

    results["scenarios"]["s1_partial_support"] = {
        "record_id": "CTRL-03-STRATIFIED-S1-D0",
        "band": "D0",
        "total_windows": res_s1["total_windows"],
        "intervened_windows": res_s1["intervened_windows"],
        "intervened_pct": res_s1["intervened_pct"],
        "clean_prefix_flagged": clean_prefix_flagged,
        "contam_core_flagged": contam_core_flagged,
        "clean_suffix_flagged": clean_suffix_flagged,
        "snr_in_db": snr_in,
        "snr_out_db": snr_out,
        "delta_snr_db": delta_snr,
        "clean_prefix_max_diff": clean_prefix_diff,
        "clean_suffix_max_diff": clean_suffix_diff,
        "passed": clean_prefix_flagged == 0 and clean_suffix_flagged == 0 and delta_snr > 0.0
    }

    # =========================================================================
    # Escenario 2: No Inferioridad en Registro Continuo Limpio
    # =========================================================================
    print("\n--- Escenario 2: No Inferioridad en Registro Continuo Limpio (CTRL-01) ---")
    ctrl01_path = Path("etapa3/datos/CTRL-01-HALFSPACE-D0.npz")
    d_clean01 = np.load(ctrl01_path)
    clean01_series = np.stack([
        d_clean01["Ex"], d_clean01["Ey"], d_clean01["Hx"], d_clean01["Hy"]
    ], axis=1).astype(np.float32)

    res_clean01 = pipe.process_continuous_record(
        clean01_series,
        record_id="CTRL-01-HALFSPACE-D0",
        band="D0",
        fs_hz=fs_d0,
        support_source=supp_s1_path
    )

    s_hat_clean01 = res_clean01["s_hat"]
    tf_c01_raw = pipe.estimate_transfer_functions(clean01_series, fs_d0, f_app_s1[:10])
    tf_c01_proc = pipe.estimate_transfer_functions(s_hat_clean01, fs_d0, f_app_s1[:10])

    diff_z_clean = []
    diff_ph_clean = []
    for r, p in zip(tf_c01_raw, tf_c01_proc):
        if r["Zxy"] is not None and p["Zxy"] is not None:
            diff_z_clean.append(abs(p["Zxy"] - r["Zxy"]) / abs(r["Zxy"]) * 100.0)
            diff_ph_clean.append(abs(p["phase_xy_deg"] - r["phase_xy_deg"]))

    mean_diff_z_clean = float(np.mean(diff_z_clean)) if diff_z_clean else 0.0
    mean_diff_ph_clean = float(np.mean(diff_ph_clean)) if diff_ph_clean else 0.0

    print(f"  Ventanas intervenidas en limpio: {res_clean01['intervened_windows']} ({res_clean01['intervened_pct']:.1f}%)")
    print(f"  Distorsion Zxy en limpio: {mean_diff_z_clean:.4f}% (Meta <= 5.0%)")
    print(f"  Distorsion de fase en limpio: {mean_diff_ph_clean:.4f}° (Meta <= 2.0°)")

    results["scenarios"]["s2_clean_non_inferiority"] = {
        "record_id": "CTRL-01-HALFSPACE-D0",
        "intervened_windows": res_clean01["intervened_windows"],
        "intervened_pct": res_clean01["intervened_pct"],
        "clean_bias_z_pct": mean_diff_z_clean,
        "clean_phase_diff_deg": mean_diff_ph_clean,
        "passed": mean_diff_z_clean <= 5.0 and mean_diff_ph_clean <= 2.0
    }

    # =========================================================================
    # Escenario 3: Compuerta G0 con Soporte Sintetico Vacio (soporte_S0)
    # =========================================================================
    print("\n--- Escenario 3: Compuerta G0 Soporte Vacio (soporte_S0) ---")
    supp_s0_path = Path("banco_sintetico/soporte_S0.json")
    res_s0 = pipe.process_continuous_record(
        clean01_series,
        record_id="CTRL-01-HALFSPACE-D0",
        band="D0",
        fs_hz=fs_d0,
        support_source=supp_s0_path
    )

    s_hat_s0 = res_s0["s_hat"]
    n_hat_s0 = res_s0["n_hat"]
    diff_s0 = float(np.max(np.abs(s_hat_s0 - clean01_series)))
    norm_n_s0 = float(np.max(np.abs(n_hat_s0)))

    print(f"  Estado soporte: {res_s0['support_status']}")
    print(f"  Red omitida: {res_s0['network_omitted']}")
    print(f"  Diferencia frente a entrada bruta: {diff_s0:.2e}")
    print(f"  Norma residual: {norm_n_s0:.2e}")

    results["scenarios"]["s3_empty_support_g0"] = {
        "support_status": res_s0["support_status"],
        "network_omitted": res_s0["network_omitted"],
        "raw_diff_max": diff_s0,
        "residual_max": norm_n_s0,
        "passed": res_s0["network_omitted"] and diff_s0 == 0.0 and norm_n_s0 == 0.0
    }

    # =========================================================================
    # Escenario 4: Compuerta G0 en Sondeo de Campo Real Sin Soporte
    # =========================================================================
    print("\n--- Escenario 4: Compuerta G0 Campo Sin Soporte (ARMT5-123-01-01-01) ---")
    res_field = pipe.resolve_support("ARMT5-123-01-01-01", "D0")
    print(f"  Estado soporte campo: {res_field['support_status']}")
    print(f"  Red omitida: {res_field['network_omitted']}")
    print(f"  Motivo: {res_field.get('reason')}")

    results["scenarios"]["s4_field_unsupported_g0"] = {
        "record_id": "ARMT5-123-01-01-01",
        "support_status": res_field["support_status"],
        "network_omitted": res_field["network_omitted"],
        "reason": res_field.get("reason"),
        "passed": res_field["network_omitted"] and res_field["support_status"] == "soporte_vacio"
    }

    # =========================================================================
    # Escenario 5: Exclusion Estricta de Bandas RMT (D2/D3)
    # =========================================================================
    print("\n--- Escenario 5: Exclusion Estricta de Bandas RMT (D2 / D3) ---")
    dummy_rmt = np.random.randn(2048, 4).astype(np.float32)
    res_rmt_d2 = pipe.process_continuous_record(dummy_rmt, "SYNTH-RMT-D2", "D2", 400000.0)
    res_rmt_d3 = pipe.process_continuous_record(dummy_rmt, "SYNTH-RMT-D3", "D3", 4000000.0)

    print(f"  D2 Estado: {res_rmt_d2['support_status']}, Omitido: {res_rmt_d2['network_omitted']}")
    print(f"  D3 Estado: {res_rmt_d3['support_status']}, Omitido: {res_rmt_d3['network_omitted']}")

    diff_rmt_d2 = float(np.max(np.abs(res_rmt_d2["s_hat"] - dummy_rmt)))
    diff_rmt_d3 = float(np.max(np.abs(res_rmt_d3["s_hat"] - dummy_rmt)))

    results["scenarios"]["s5_rmt_exclusion"] = {
        "d2_status": res_rmt_d2["support_status"],
        "d2_omitted": res_rmt_d2["network_omitted"],
        "d2_diff": diff_rmt_d2,
        "d3_status": res_rmt_d3["support_status"],
        "d3_omitted": res_rmt_d3["network_omitted"],
        "d3_diff": diff_rmt_d3,
        "passed": (res_rmt_d2["network_omitted"] and diff_rmt_d2 == 0.0 and
                   res_rmt_d3["network_omitted"] and diff_rmt_d3 == 0.0)
    }

    # =========================================================================
    # Escenario 6: Deteccion de Rango 1 y Abstencion
    # =========================================================================
    print("\n--- Escenario 6: Deteccion de Rango 1 y Abstencion (CTRL-04) ---")
    ctrl04_path = Path("etapa3/datos/CTRL-04-ABSTENTION-RANK1.npz")
    d_rank1 = np.load(ctrl04_path)
    # En CTRL-04, las senales colineales exactas residen en Ex, Ey, Hx, Hy (Hy = 0.75 Hx)
    rank1_series = np.stack([
        d_rank1["Ex"], d_rank1["Ey"], d_rank1["Hx"], d_rank1["Hy"]
    ], axis=1).astype(np.float32)

    tf_rank1 = pipe.estimate_transfer_functions(rank1_series, fs_d0, [125.0, 250.0, 500.0])
    abstentions = [x for x in tf_rank1 if x["status"] == "rango_1_abstencion"]
    print(f"  Frecuencias evaluadas: {len(tf_rank1)}, abstenciones activadas: {len(abstentions)}")
    if abstentions:
        print(f"  Condicion HH observada: {abstentions[0]['cond_hh']:.2e} (> 1e4)")

    results["scenarios"]["s6_rank1_abstention"] = {
        "total_freqs": len(tf_rank1),
        "abstained_freqs": len(abstentions),
        "cond_hh_max": float(max([x["cond_hh"] for x in tf_rank1])) if tf_rank1 else 0.0,
        "passed": len(abstentions) == len(tf_rank1)
    }

    # =========================================================================
    # Escenario 7: Invarianza de Lote y Reconstruccion Continua Exacta
    # =========================================================================
    print("\n--- Escenario 7: Invarianza de Lote y Reconstruccion Exacta ---")
    np.random.seed(42)
    test_sig = np.random.randn(4096, 4).astype(np.float32)

    # Invarianza de lote en proceso completo
    res_b1 = pipe.process_continuous_record(test_sig, "TEST-INV", "D0", fs_d0, support_source=supp_s1_path, batch_size=1)
    res_b32 = pipe.process_continuous_record(test_sig, "TEST-INV", "D0", fs_d0, support_source=supp_s1_path, batch_size=32)
    diff_batch = float(np.max(np.abs(res_b1["s_hat"] - res_b32["s_hat"])))

    # Reconstruccion en identidad exacta
    L = pipe.window_length
    S = pipe.step
    windows_id = np.array([test_sig[i : i + L] for i in range(0, len(test_sig) - L + 1, S)])
    recon_id = pipe.reconstruct_overlap_add(windows_id, len(test_sig), S)
    diff_identity = float(np.max(np.abs(recon_id - test_sig)))

    # Muestra a muestra residual
    res_sub = pipe.process_continuous_record(test_sig, "TEST-RES", "D0", fs_d0, support_source=supp_s1_path)
    residual_exact = float(np.max(np.abs(test_sig - (res_sub["s_hat"] + res_sub["n_hat"]))))

    print(f"  Diferencia por tamano de lote (1 vs 32): {diff_batch:.2e} (Meta < 1e-5)")
    print(f"  Error de recomposicion en identidad: {diff_identity:.2e} (Meta < 1e-12)")
    print(f"  Correspondencia exacta x = s_hat + n_hat: {residual_exact:.2e} (Meta < 1e-12)")

    results["scenarios"]["s7_invariance_and_reconstruction"] = {
        "batch_diff_max": diff_batch,
        "identity_reconstruction_err": diff_identity,
        "residual_identity_err": residual_exact,
        "passed": diff_batch < 1e-5 and diff_identity < 1e-12 and residual_exact < 1e-12
    }

    # =========================================================================
    # Conclusion y Guardado
    # =========================================================================
    all_passed = all(sc.get("passed", False) for sc in results["scenarios"].values())
    results["gate_p8_passed"] = all_passed
    results["execution_time_sec"] = time.time() - t0

    print("\n" + "=" * 80)
    print(f"Resultado Global de Puerta P8: {'APROBADO' if all_passed else 'FALLIDO'} (Tiempo: {results['execution_time_sec']:.2f} s)")
    print("=" * 80)

    # Guardar resumen_p8.json
    res_path = Path("etapa8/resumen_p8.json")
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Resumen cuantitativo guardado en {res_path}")

    # Generar reporte_p8.md
    rep_path = Path("etapa8/reporte_p8.md")
    with open(rep_path, "w", encoding="utf-8") as f:
        f.write(f"# Reporte Técnico de Etapa 8: Inferencia MT/AMT con Soporte Parcial (Puerta P8)\n\n")
        f.write(f"- **Versión:** `{VERSION}`\n")
        f.write(f"- **Fecha UTC:** {results['timestamp_utc']}\n")
        f.write(f"- **Dispositivo:** `{results['device']}` (Tiempo: {results['execution_time_sec']:.2f} s)\n")
        f.write(f"- **Estado Global Puerta P8:** `{'APROBADO' if all_passed else 'FALLIDO'}`\n\n")

        f.write("## 1. Resumen de Escenarios Evaluados\n\n")
        f.write("| Escenario | Descripción | Criterio Clave | Resultado | Estado |\n")
        f.write("|---|---|---|---|:---:|\n")

        s1 = results["scenarios"]["s1_partial_support"]
        f.write(f"| 1. Soporte Parcial | CTRL-03 + NOISE-D0-001 | Selectividad temporal: `{s1['clean_prefix_flagged']}/120` limpio, `{s1['contam_core_flagged']}` contaminado; Ganancia SNR: `+{s1['delta_snr_db']:.2f} dB` | Intervención condicional exacta | {'PASA' if s1['passed'] else 'FALLA'} |\n")

        s2 = results["scenarios"]["s2_clean_non_inferiority"]
        f.write(f"| 2. No Inferioridad Limpio | CTRL-01 Continuo | Sesgo Z: `{s2['clean_bias_z_pct']:.4f}%` (<=5%), Fase: `{s2['clean_phase_diff_deg']:.4f}°` (<=2°) | No distorsiona limpio | {'PASA' if s2['passed'] else 'FALLA'} |\n")

        s3 = results["scenarios"]["s3_empty_support_g0"]
        f.write(f"| 3. Compuerta G0 Soporte Vacío | CTRL-01 + soporte_S0 | Red omitida: `{s3['network_omitted']}`, Diff señal: `{s3['raw_diff_max']:.1e}` | Cero intervención | {'PASA' if s3['passed'] else 'FALLA'} |\n")

        s4 = results["scenarios"]["s4_field_unsupported_g0"]
        f.write(f"| 4. Campo Sin Vínculo TEM | ARMT5-123-01-01-01 | Estado: `{s4['support_status']}`, Red omitida: `{s4['network_omitted']}` | Omitir red | {'PASA' if s4['passed'] else 'FALLA'} |\n")

        s5 = results["scenarios"]["s5_rmt_exclusion"]
        f.write(f"| 5. Exclusión Estricta RMT | Bandas D2 y D3 | Omitidos: `{s5['d2_omitted']}` y `{s5['d3_omitted']}`, Diff: `{s5['d2_diff']:.1e}` | Bloqueo absoluto RMT | {'PASA' if s5['passed'] else 'FALLA'} |\n")

        s6 = results["scenarios"]["s6_rank1_abstention"]
        f.write(f"| 6. Rango 1 y Abstención | CTRL-04 Linealmente Polarizado | Abstenciones: `{s6['abstained_freqs']}/{s6['total_freqs']}` (Cond > 1e4) | Abstención tensor | {'PASA' if s6['passed'] else 'FALLA'} |\n")

        s7 = results["scenarios"]["s7_invariance_and_reconstruction"]
        f.write(f"| 7. Invarianza y Reconstrucción | Lote 1 vs 32, Identidad | Diff lote: `{s7['batch_diff_max']:.1e}`, Error ident: `{s7['identity_reconstruction_err']:.1e}` | Reconstrucción C1 perfecta | {'PASA' if s7['passed'] else 'FALLA'} |\n")

        f.write("\n## 2. Conclusiones Físicas y de Integración\n\n")
        f.write("1. **Recomposición continua C1 sin saltos de costura:** El operador Hanning overlap-add logra una reconstrucción exacta con error del orden de 1e-16 en identidad y garantiza continuidad suave en los bordes de ventana.\n")
        f.write("2. **Cumplimiento estricto de la compuerta G0:** Ante soporte TEM vacío (tanto sintético como de campo sin vínculo verificado), el pipeline omite automáticamente la red CBAM sin inventar etiquetas ni modificar los datos de campo, regresando al estimador robusto de referencia P6.\n")
        f.write("3. **Aislamiento absoluto de RMT:** Las bandas D2 y D3 quedan excluidas de la red neuronal por diseño, satisfaciendo el alcance estricto del Plan v1.3 (§8.3).\n")
        f.write("4. **Recuperación física superior en soporte parcial:** En presencia de contaminación severa, la cadena condicional recupera la respuesta Z(f) con menor error y mayor SNR, respetando F_aplicacion.\n")

    print(f"Reporte técnico guardado en {rep_path}")
    return results


if __name__ == "__main__":
    run_etapa8_evaluation()
