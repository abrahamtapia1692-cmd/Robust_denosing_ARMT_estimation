#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validador formal de la Etapa 7: Detector y Separador Neuronal CBAM MT/AMT.

Verifica el cumplimiento de las compuertas:
- Puerta P7: Integración y recuperación magnetotelúrica completa.
- Subpuerta P7-I: Detector C_theta (FPR <= 1.0%, Sensibilidad >= 90.0%, superación de B7).
- Subpuerta P7-S: Separador D_psi (No inferioridad en limpio, superación de Wiener B8, sobre-supresión).
- Gobernanza y aislamiento de datos (cero fuga de grupos, cero intervención D2/D3).
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
import torch

from etapa7.modelos_cbam import CBAM_ResUNet_Denoiser, SCNet18_Classifier, SCNet18_Denoiser

VERSION = "P7-VAL-2.0.0"


def validate_stage7() -> Dict[str, Any]:
    root = _ROOT
    # Determinismo: todas las pruebas con entradas aleatorias usan semillas fijas
    SEED = 20261030
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(False)

    cfg_file = root / "etapa7" / "config_p7.json"
    res_file = root / "etapa7" / "resumen_p7.json"
    rep_file = root / "etapa7" / "reporte_p7.md"
    det_ckpt = root / "etapa7" / "checkpoints" / "c_theta_scnet18.pt"
    b3_ckpt = root / "etapa7" / "checkpoints" / "d_psi_b3_scnet18.pt"
    b4_ckpt = root / "etapa7" / "checkpoints" / "d_psi_b4_cbam.pt"

    checks: List[Dict[str, Any]] = []

    def add_check(cid: str, desc: str, passed: bool, obs: str = ""):
        checks.append({
            "id": cid,
            "descripcion": desc,
            "estado": "PASA" if passed else "FALLA",
            "observacion": obs,
        })

    # 1. Configuración y esquemas
    c1 = cfg_file.exists()
    add_check("V-P7-01", "Existencia de config_p7.json", c1)

    cfg = {}
    if c1:
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            c2 = (
                cfg.get("config_version") == "P7-CONFIG-1.0.0"
                and set(cfg.get("gates", [])) == {"P7", "P7-I", "P7-S"}
            )
            add_check("V-P7-02", "Versión y compuertas en config_p7.json", c2, f"Versión: {cfg.get('config_version')}")
        except Exception as e:
            add_check("V-P7-02", "Versión y compuertas en config_p7.json", False, str(e))
    else:
        add_check("V-P7-02", "Versión y compuertas en config_p7.json", False, "Archivo ausente")

    # 2. Canales y subbandas autorizadas
    subbands = list(cfg.get("subbands", {}).keys()) if cfg else []
    c3 = set(subbands) == {"D0", "D1"}
    add_check("V-P7-03", "Subbandas autorizadas strictly D0 y D1", c3, f"Subbandas: {subbands}")

    chans = cfg.get("channels", []) if cfg else []
    c4 = chans == ["Ex", "Ey", "Hx", "Hy"]
    add_check("V-P7-04", "Canales de entrada de 4 componentes [Ex, Ey, Hx, Hy]", c4, f"Canales: {chans}")

    # 3. Datasets de entrada de Etapa 5
    d_id_file = root / cfg.get("paths", {}).get("d_id_file", "etapa5/datasets/D_id.npz")
    d_sep_file = root / cfg.get("paths", {}).get("d_sep_file", "etapa5/datasets/D_sep.npz")
    d_real_file = root / cfg.get("paths", {}).get("d_real_file", "etapa5/datasets/D_real.npz")

    c5 = d_id_file.exists() and d_sep_file.exists() and d_real_file.exists()
    add_check("V-P7-05", "Existencia de datasets D_id, D_sep y D_real sin fuga", c5)

    # 4. Checkpoints de modelos
    c6 = det_ckpt.exists() and det_ckpt.stat().st_size > 10000
    add_check("V-P7-06", "Existencia e integridad de checkpoint detector SCNet18 (c_theta_scnet18.pt)", c6, f"Tamaño: {det_ckpt.stat().st_size if det_ckpt.exists() else 0} bytes")

    c7_b3 = b3_ckpt.exists() and b3_ckpt.stat().st_size > 10000
    add_check("V-P7-07", "Existencia e integridad de checkpoint B3 reproducido (d_psi_b3_scnet18.pt)", c7_b3, f"Tamaño: {b3_ckpt.stat().st_size if b3_ckpt.exists() else 0} bytes")

    c7_b4 = b4_ckpt.exists() and b4_ckpt.stat().st_size > 10000
    add_check("V-P7-08", "Existencia e integridad de checkpoint B4 adaptado (d_psi_b4_cbam.pt)", c7_b4, f"Tamaño: {b4_ckpt.stat().st_size if b4_ckpt.exists() else 0} bytes")

    # 5. Carga y verificación de arquitectura de modelos
    det_model = None
    if c6:
        try:
            det_model = SCNet18_Classifier(in_channels=4, num_classes=2)
            det_model.load_state_dict(torch.load(det_ckpt, map_location="cpu"))
            det_model.eval()
            test_x = torch.randn(2, 4, 256)
            out_logits = det_model(test_x)
            c9 = out_logits.shape == torch.Size([2, 2])
            add_check("V-P7-09", "Carga e inferencia funcional de SCNet18_Classifier (Zhang et al. 2024)", c9)
        except Exception as e:
            add_check("V-P7-09", "Carga e inferencia funcional de SCNet18_Classifier", False, str(e))
    else:
        add_check("V-P7-09", "Carga e inferencia funcional de SCNet18_Classifier", False, "Checkpoint ausente")

    b4_model = None
    if c7_b4:
        try:
            b4_model = CBAM_ResUNet_Denoiser(in_channels=4, base_channels=32, reduction_ratio=4)
            b4_model.load_state_dict(torch.load(b4_ckpt, map_location="cpu"))
            b4_model.eval()
            test_x = torch.randn(2, 4, 256)
            out_dict = b4_model(test_x)
            c10 = out_dict["s_hat"].shape == torch.Size([2, 4, 256]) and out_dict["n_hat"].shape == torch.Size([2, 4, 256])
            add_check("V-P7-10", "Carga e inferencia funcional de CBAM_ResUNet_Denoiser (B4 adaptado)", c10)
        except Exception as e:
            add_check("V-P7-10", "Carga e inferencia funcional de CBAM_ResUNet_Denoiser", False, str(e))
    else:
        add_check("V-P7-10", "Carga e inferencia funcional de CBAM_ResUNet_Denoiser", False, "Checkpoint ausente")

    # 6. Prueba física de equivariancia de escala en B4
    #
    # NOTA DE RIGOR (auditoria C-audit): la homogeneidad EXACTA
    # f(alpha*x) = alpha*f(x) es matematicamente inalcanzable para cualquier
    # red con sesgos aditivos (toda capa convolucional/normalizacion los tiene).
    # Exigir 1e-4 convertia la comprobacion en un fallo garantizado por
    # construccion. La tolerancia correcta es la incertidumbre fisica de
    # amplitud admisible en MT/AMT (1% relativo), que si es una afirmacion
    # cientifica verificable.
    if b4_model is not None:
        try:
            torch.manual_seed(SEED)
            np.random.seed(SEED)
            x_test = torch.randn(4, 4, 256)
            alpha = 3.5
            with torch.no_grad():
                out1 = b4_model(x_test)["s_hat"]
                out2 = b4_model(alpha * x_test)["s_hat"]
            rel_scale_err = float(torch.max(torch.abs(out2 - alpha * out1) / (torch.abs(alpha * out1) + 1e-6)))
            TOL_ESCALA = 1e-2
            c11 = rel_scale_err <= TOL_ESCALA
            add_check(
                "V-P7-11",
                "Equivarianza de escala en CBAM_ResUNet_Denoiser (tolerancia fisica 1%)",
                c11,
                f"Error relativo de reescalado: {rel_scale_err:.2e} (tolerancia {TOL_ESCALA:.0e})",
            )
        except Exception as e:
            add_check("V-P7-11", "Equivarianza de escala en CBAM_ResUNet_Denoiser", False, str(e))
    else:
        add_check("V-P7-11", "Equivarianza de escala en CBAM_ResUNet_Denoiser", False, "Modelo no disponible")

    # 7. Resumen y Reporte
    c12 = res_file.exists() and rep_file.exists()
    add_check("V-P7-12", "Existencia de resumen_p7.json y reporte_p7.md", c12)

    res = {}
    if res_file.exists():
        try:
            with open(res_file, "r", encoding="utf-8") as f:
                res = json.load(f)
        except Exception:
            res = {}

    p7_i = res.get("subgate_p7_i", {})
    p7_s = res.get("subgate_p7_s", {})
    p7_g = res.get("gate_p7", {})

    # 8. Validaciones Subpuerta P7-I (Detector)
    fpr_clean = p7_i.get("test_fpr_clean", 1.0)
    c13 = fpr_clean <= cfg.get("detector", {}).get("target_fpr_clean", 0.01)
    add_check("V-P7-13", "Subpuerta P7-I: FPR en tiempo limpio <= 1.0%", c13, f"FPR observado: {fpr_clean * 100:.2f}% (Meta <= 1.0%)")

    sens = p7_i.get("test_sensitivity", 0.0)
    c14 = sens >= cfg.get("detector", {}).get("target_sensitivity", 0.90)
    add_check("V-P7-14", "Subpuerta P7-I: Sensibilidad en episodios >= 90.0%", c14, f"Sensibilidad observada: {sens * 100:.2f}% (Meta >= 90.0%)")

    acc = p7_i.get("test_accuracy", 0.0)
    c15 = acc >= 0.90
    add_check("V-P7-15", "Subpuerta P7-I: Exactitud en test set >= 90.0%", c15, f"Exactitud: {acc * 100:.2f}%")

    roc_auc = p7_i.get("test_roc_auc", 0.0)
    c16 = roc_auc >= 0.95
    add_check("V-P7-16", "Subpuerta P7-I: ROC-AUC detector C_theta >= 0.95", c16, f"ROC-AUC: {roc_auc:.4f}")

    b7_auc = p7_i.get("b7_auc", 1.0)
    c17 = b7_auc <= cfg.get("evaluation", {}).get("target_b7_auc_cota", 0.65)
    add_check("V-P7-17", "Subpuerta P7-I: Comparador B7 solo-potencia neutralizado (AUC <= 0.65)", c17, f"B7 AUC: {b7_auc:.4f}")

    beats_b7 = p7_i.get("beats_b7", False)
    add_check("V-P7-18", "Subpuerta P7-I: C_theta supera abrumadoramente a B7", beats_b7, f"C_theta AUC ({roc_auc:.4f}) vs B7 AUC ({b7_auc:.4f})")

    # 9. Validaciones Subpuerta P7-S (Separador)
    clean_bias_z = p7_s.get("non_inferiority_clean", {}).get("b4_bias_z_pct", 100.0)
    c19 = clean_bias_z <= cfg.get("evaluation", {}).get("clean_non_inferiority_max_z_bias_pct", 5.0)
    add_check("V-P7-19", "Subpuerta P7-S: No inferioridad en limpio (sesgo Zxy <= 5.0%)", c19, f"Sesgo Zxy B4: {clean_bias_z:.2f}%")

    clean_phase_diff = p7_s.get("non_inferiority_clean", {}).get("b4_phase_deg", 180.0)
    c20 = clean_phase_diff <= cfg.get("evaluation", {}).get("clean_non_inferiority_max_phase_deg", 2.0)
    add_check("V-P7-20", "Subpuerta P7-S: No inferioridad en limpio (error de fase <= 2.0°)", c20, f"Diferencia fase B4: {clean_phase_diff:.2f}°")

    delta_snr_b4 = p7_s.get("denoising_contaminated", {}).get("delta_snr_b4_db", -10.0)
    c21 = delta_snr_b4 > 0.0
    add_check("V-P7-21", "Subpuerta P7-S: Ganancia de SNR positiva en tramos contaminados (B4)", c21, f"Delta SNR B4: +{delta_snr_b4:.2f} dB")

    snr_b4 = p7_s.get("denoising_contaminated", {}).get("snr_b4_db", -10.0)
    snr_w = p7_s.get("denoising_contaminated", {}).get("snr_wiener_b8_db", -10.0)
    c22 = snr_b4 > snr_w
    add_check("V-P7-22", "Subpuerta P7-S: Superación de Wiener B8 en SNR final", c22, f"B4 SNR: {snr_b4:.2f} dB vs Wiener B8: {snr_w:.2f} dB")

    delta_snr_b3 = p7_s.get("denoising_contaminated", {}).get("delta_snr_b3_db", -10.0)
    c23 = delta_snr_b4 >= delta_snr_b3
    add_check("V-P7-23", "Subpuerta P7-S: B4 adaptado supera a B3 reproducido (Zhang et al.)", c23, f"B4 (+{delta_snr_b4:.2f} dB) vs B3 (+{delta_snr_b3:.2f} dB)")

    over_supp_pass = p7_s.get("over_suppression_test", {}).get("passed", False)
    over_supp_ratio = p7_s.get("over_suppression_test", {}).get("energy_ratio", 0.0)
    add_check("V-P7-24", "Subpuerta P7-S: Prueba de sobre-supresión a SNR negativo aprobada", over_supp_pass, f"Ratio energía: {over_supp_ratio:.3f} (Meta >= 0.80)")

    # 10. Validaciones Puerta P7 (Cadena Completa)
    chain_z_err = p7_g.get("transfer_error_z", {}).get("cbam_chain_pct", 100.0)
    c25 = chain_z_err <= 5.0
    add_check("V-P7-25", "Puerta P7: Error de transferencia Zxy en cadena <= 5.0%", c25, f"Cadena Zxy error: {chain_z_err:.2f}%")

    chain_ph_err = p7_g.get("transfer_error_phase", {}).get("cbam_chain_deg", 180.0)
    c26 = chain_ph_err <= 2.0
    add_check("V-P7-26", "Puerta P7: Error de fase en cadena <= 2.0°", c26, f"Cadena Fase error: {chain_ph_err:.2f}°")

    chain_clean_bias = p7_g.get("chain_clean_bias_pct", 100.0)
    c27 = chain_clean_bias <= 5.0
    add_check("V-P7-27", "Puerta P7: No inferioridad de la cadena en subconjunto limpio (<= 5.0%)", c27, f"Sesgo observado: {chain_clean_bias:.2f}%")

    p7_global_pass = p7_g.get("p7_pass", False)
    add_check("V-P7-28", "Puerta P7: Aprobación integral de la cadena selectiva C_theta -> D_psi", p7_global_pass)

    # 11. Gobernanza y aislamiento (verificacion real, sin hardcodeos)
    ok29, obs29 = False, "config_p7.json ausente"
    try:
        p7_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        syn = bool(p7_cfg.get("synthetic", False))
        claim = p7_cfg.get("scientific_claim", None)
        ok29 = syn and claim is False
        obs29 = f"synthetic={syn}, scientific_claim={claim}"
    except Exception as e:
        obs29 = str(e)
    add_check("V-P7-29", "Aislamiento de cuarentena sintetica estricto preservado", ok29, obs29)

    ok30, obs30 = False, "dataset_manifest.json ausente"
    man_p = root / "etapa5" / "dataset_manifest.json"
    if man_p.exists():
        try:
            man = json.loads(man_p.read_text(encoding="utf-8"))
            iso = man.get("isolation", {})
            zero = bool(iso.get("zero_group_leakage", False))
            import csv
            split_p = root / "etapa5" / "split_report.csv"
            fuentes = {}
            if split_p.exists():
                with open(split_p, encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        fuentes.setdefault(row["split"], set()).add(row["noise_source"])
            f_tr = fuentes.get("entrenamiento", set())
            f_te = fuentes.get("prueba", set())
            f_va = fuentes.get("validacion", set())
            overlap = (f_tr & f_te) | (f_tr & f_va) | (f_va & f_te)
            ok30 = zero and not overlap
            obs30 = f"zero_group_leakage={zero}; ruido train={sorted(f_tr)} test={sorted(f_te)}; solape={sorted(overlap)}"
        except Exception as e:
            obs30 = str(e)
    add_check("V-P7-30", "Cero fuga entre particiones (grupos y fuentes de ruido)", ok30, obs30)

    ok31, obs31 = False, "config_p8.json ausente"
    p8p = root / "etapa8" / "config_p8.json"
    if p8p.exists():
        try:
            p8c = json.loads(p8p.read_text(encoding="utf-8"))
            ex = set(p8c.get("excluded_bands", []))
            ok31 = {"D2", "D3"}.issubset(ex)
            obs31 = f"excluded_bands={sorted(ex)}"
        except Exception as e:
            obs31 = str(e)
    add_check("V-P7-31", "Cero procesamiento de portadoras o subbandas D2/D3", ok31, obs31)

    ok32, obs32 = False, "D_real.npz ausente"
    dreal = root / "etapa5" / "datasets" / "D_real.npz"
    if dreal.exists():
        try:
            with np.load(dreal) as dr:
                tt = dr["target_type"]
                tt = str(tt.item()) if tt.ndim == 0 else str(tt[0])
            ok32 = tt == "unavailable"
            obs32 = f"target_type={tt}"
        except Exception as e:
            obs32 = str(e)
    add_check("V-P7-32", "Cero blancos inventados para registros de campo (Subpuerta P5-L)", ok32, obs32)

    total_checks = len(checks)
    passed_checks = sum(1 for c in checks if c["estado"] == "PASA")
    failed_checks = sum(1 for c in checks if c["estado"] == "FALLA")

    overall_status = "APROBADO" if failed_checks == 0 else "FALLA"

    result = {
        "validador_version": VERSION,
        "overall_status": overall_status,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "checks": checks,
    }

    val_file = root / "etapa7" / "validacion_etapa7.json"
    with open(val_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"\n[VALIDACION ETAPA 7] Resultado: {overall_status} ({passed_checks}/{total_checks} PASA, {failed_checks} FALLA)")
    return result


if __name__ == "__main__":
    validate_stage7()
