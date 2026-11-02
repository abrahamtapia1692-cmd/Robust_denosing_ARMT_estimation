#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Driver de Ejecucion de la Etapa 9: Evaluacion Ciega de Extremo a Extremo (Puerta P9).

Ejecuta el evaluador ciego, recolecta las metricas de todos los benchmarks B0-B10,
sondeos de prueba independientes, evalua la compuerta de seguridad G4 y genera
los reportes auditables resumen_p9.json y reporte_p9.md.
"""
from __future__ import annotations

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from etapa9.evaluador_ciego import BlindEvaluator

VERSION = "P9-2.0.0"


def run_etapa9() -> Dict[str, Any]:
    """Ejecuta el pipeline completo de la Etapa 9."""
    t0 = time.time()
    evaluator = BlindEvaluator(config_path="etapa9/config_p9.json")
    results = evaluator.evaluate_all()
    results["execution_time_sec"] = time.time() - t0
    results["timestamp_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Guardar resumen_p9.json
    res_path = _ROOT / "etapa9" / "resumen_p9.json"
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nResumen cuantitativo oficial guardado en: {res_path}")

    # Generar reporte_p9.md — estados calculados, nunca hardcodeados
    rep_path = _ROOT / "etapa9" / "reporte_p9.md"
    g4 = results["gate_g4_safety"]
    p9_m = results["gate_p9_metrics"]
    s2_res = results["soundings_results"].get("snd_blind_02_stratified", {})
    b_errs = s2_res.get("benchmark_errors", {})
    ep = evaluator.cfg["preregistered_endpoints"]

    clean_ep = ep["clean_non_inferiority"]
    rec_ep = ep["contaminated_recovery"]
    rej_ep = ep["non_identifiable_rejection"]

    def estado(valor, limite, modo="max"):
        if valor is None:
            return "NO_EVALUADO"
        ok = valor <= limite if modo == "max" else valor >= limite
        return "PASA" if ok else "FALLA"

    filas = [
        (
            f"No inferioridad en limpio (P95 sesgo Z)",
            f"$\\le {clean_ep['p95_bias_z_pct_max']:.1f}\\%$",
            f"{p9_m.get('clean_p95_bias_z_pct', 0):.4f}%",
            estado(p9_m.get("clean_p95_bias_z_pct"), clean_ep["p95_bias_z_pct_max"]),
        ),
        (
            "No inferioridad en limpio (P95 fase)",
            f"$\\le {clean_ep['p95_phase_diff_deg_max']:.1f}^\\circ$",
            f"{p9_m.get('clean_p95_phase_diff_deg', 0):.4f}°",
            estado(p9_m.get("clean_p95_phase_diff_deg"), clean_ep["p95_phase_diff_deg_max"]),
        ),
        (
            "Recuperación con ruido (mediana $\\rho_a$)",
            f"$\\le {rec_ep['median_bias_log10_rho_max']:.2f}\\text{{ dec}}$",
            f"{p9_m.get('stratified_median_err_rho_dec', 0):.4f} dec",
            estado(p9_m.get("stratified_median_err_rho_dec"), rec_ep["median_bias_log10_rho_max"]),
        ),
        (
            "Recuperación con ruido (mediana fase)",
            f"$\\le {rec_ep['median_phase_diff_deg_max']:.1f}^\\circ$",
            f"{p9_m.get('stratified_median_err_phase_deg', 0):.2f}°",
            estado(p9_m.get("stratified_median_err_phase_deg"), rec_ep["median_phase_diff_deg_max"]),
        ),
        (
            "Mejora de impedancia vs B0",
            f"$\\ge {rec_ep['min_impedance_improvement_pct']:.1f}\\%$",
            f"{p9_m.get('improvement_vs_b0_pct', 0):.2f}%",
            estado(p9_m.get("improvement_vs_b0_pct"), rec_ep["min_impedance_improvement_pct"], "min"),
        ),
        (
            "Control de atajo B7 (AUC solo-potencia)",
            "$\\le 0.65$",
            f"{p9_m.get('b7_power_auc', 0):.4f}",
            estado(p9_m.get("b7_power_auc"), 0.65),
        ),
        (
            "Tasa de falsa recuperación",
            f"$\\le {rej_ep['max_false_recovery_rate_pct']:.1f}\\%$",
            f"{p9_m.get('false_recovery_rate_pct', 0):.1f}%",
            estado(p9_m.get("false_recovery_rate_pct"), rej_ep["max_false_recovery_rate_pct"]),
        ),
    ]

    sondeos = results["soundings_results"]
    for clave, nombre in [
        ("snd_blind_01_clean", "SND-BLIND-01 limpio"),
        ("snd_blind_02_stratified", "SND-BLIND-02 estratificado"),
        ("snd_blind_03_sferics", "SND-BLIND-03 sferics"),
        ("snd_blind_04_texture_f1", "SND-BLIND-04 textura F1"),
        ("non_identifiable_tests", "Sondeos no identificables"),
    ]:
        ok = bool(sondeos.get(clave, {}).get("passed", False))
        filas.append((f"Sondeo {nombre}", "Todos los criterios", "—", "PASA" if ok else "FALLA"))

    faltantes = g4.get("missing_mandatory_benchmarks", [])

    with open(rep_path, "w", encoding="utf-8") as f:
        f.write("# Reporte Técnico de Etapa 9: Evaluación Ciega de Extremo a Extremo (Puerta P9)\n\n")
        f.write(f"- **Versión:** `{VERSION}`\n")
        f.write(f"- **Fecha UTC:** {results['timestamp_utc']}\n")
        f.write(f"- **Naturaleza de los datos:** **sintético** (`synthetic: true`, `scientific_claim: false`)\n")
        f.write(f"- **Modelo de verdad:** `{results.get('truth_model_source')}` → "
                f"$\\rho={s2_res.get('truth_model', {}).get('rho_ohm_m')}$, "
                f"interfaces={s2_res.get('truth_model', {}).get('interfaces_m')}$\n")
        f.write(f"- **Semilla:** `{results.get('seed')}`\n")
        f.write(f"- **Compuerta de Seguridad G4:** `{'APROBADO' if g4.get('g4_approved') else 'BLOQUEADO'}`\n")
        f.write(f"- **Estado Puerta P9:** `{'APROBADO' if p9_m.get('p9_passed') else 'BLOQUEADO'}`\n\n")

        f.write("## 1. Tabla Comparativa de Benchmarks (SND-BLIND-02 Estratificado)\n\n")
        f.write("| Benchmark | Tipo | Mediana Err Z (%) | Mediana Err ρa (dec) | Mediana Err Fase (°) | P90 Err ρa (dec) | P90 Err Fase (°) |\n")
        f.write("|---|---|---:|---:|---:|---:|---:|\n")

        for b_id, m in b_errs.items():
            b_desc = next((x["name"] for x in evaluator.cfg["benchmarks"] if x["id"] == b_id), b_id)
            f.write(f"| **{b_id}** | {b_desc} | {m['median_err_z_pct']:.2f}% | {m['median_err_rho_dec']:.4f} | {m['median_err_phase_deg']:.2f}° | {m['p90_err_rho_dec']:.4f} | {m['p90_err_phase_deg']:.2f}° |\n")

        forced = s2_res.get("b4_forced_error", {})
        if forced:
            f.write(f"\n- **B4 forzado sobre todas las ventanas (`denoise_all`):** Z={forced.get('median_err_z_pct', 0):.2f}%, "
                    f"ρa={forced.get('median_err_rho_dec', 0):.4f} dec, fase={forced.get('median_err_phase_deg', 0):.2f}°\n")
        f.write(f"- **B7 (AUC solo-potencia):** {s2_res.get('b7_power_auc', 0):.4f} (meta ≤ 0.65)\n")
        f.write(f"- **Ventanas intervenidas por B4 (auto):** {s2_res.get('b4_intervened_pct', 0):.1f}%\n")

        f.write("\n## 2. Métricas frente a Metas Preregistradas\n\n")
        f.write("| Criterio Físico / Numérico | Meta Preregistrada (P9) | Valor Observado | Estado |\n")
        f.write("|---|---|---|:---:|\n")
        for criterio, meta, valor, est in filas:
            f.write(f"| {criterio} | {meta} | **{valor}** | **{est}** |\n")

        f.write("\n## 3. Comparadores\n\n")
        f.write(f"- **Evaluados:** `{results.get('benchmarks_evaluated')}`\n")
        if faltantes:
            f.write(f"- **Obligatorios no implementados:** `{faltantes}` — la puerta no puede aprobarse.\n")
        for b_id, motivo in results.get("benchmarks_not_evaluated", {}).items():
            f.write(f"  - `{b_id}`: {motivo}\n")
        b9 = s2_res.get("b9_independent_noise", {})
        if b9:
            f.write(f"- **B9 (ruido independiente NOISE-D0-003):** B0={b9.get('B0', {}).get('median_err_z_pct', float('nan')):.2f}%, "
                    f"B4={b9.get('B4', {}).get('median_err_z_pct', float('nan')):.2f}%\n")

        f.write("\n## 4. Conclusiones\n\n")
        if p9_m.get("p9_passed"):
            f.write("1. La puerta P9 se aprueba con todos los endpoints preregistrados cumplidos.\n")
            f.write("2. El resultado es válido únicamente para el escenario sintético declarado.\n")
        else:
            f.write("1. **La puerta P9 NO se aprueba.** Uno o más endpoints preregistrados no se cumplen.\n")
            f.write("2. El pipeline **no debe liberarse** ni declararse recuperación de datos.\n")
            f.write("3. Los productos de Etapa 10 quedan en cuarentena sintética.\n")

    print(f"Reporte técnico oficial guardado en: {rep_path}")
    return results


if __name__ == "__main__":
    run_etapa9()
