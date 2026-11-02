#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validador exhaustivo de la Etapa 3 — Puerta P3: Síntesis de subbanda limpia.

Ejecuta las comprobaciones formales de contrato, física electromagnética,
precisión numérica analítica, recuperación con el estimador P6, detección
de rango 1 (abstención), detección de saturación instrumental y aislamiento
respecto a los datos de campo de P0.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

ETAPA3_DIR = WORKSPACE_ROOT / "etapa3"
CONFIG_PATH = ETAPA3_DIR / "config_p3.json"
RESUMEN_PATH = ETAPA3_DIR / "resumen_p3.json"
REPORTE_PATH = ETAPA3_DIR / "reporte_p3.md"
DATOS_DIR = ETAPA3_DIR / "datos"

VALIDATION_FILE = ETAPA3_DIR / "validacion_etapa3.json"


def sha256_file(path: Path) -> str:
    """Calcula el hash SHA-256 de un archivo."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class Checker:
    def __init__(self):
        self.checks = []
        self.passed = 0
        self.failed = 0
        self.observations = 0

    def add(self, check_id: str, description: str, ok: bool, detail: str = "", is_observation: bool = False):
        if is_observation:
            estado = "OBSERVACION"
            self.observations += 1
        elif ok:
            estado = "PASA"
            self.passed += 1
        else:
            estado = "FALLA"
            self.failed += 1

        self.checks.append({
            "id": check_id,
            "descripcion": description,
            "resultado": estado,
            "detalle": detail,
        })
        return ok


def run_validation() -> Dict[str, Any]:
    c = Checker()
    print("[VALIDADOR P3] Iniciando validación formal de Etapa 3...")

    # 1. Existencia de artefactos clave
    c.add("FILE-CONFIG", "Existe config_p3.json", CONFIG_PATH.exists(), str(CONFIG_PATH))
    c.add("FILE-GEN", "Existe clean_generator.py", (ETAPA3_DIR / "clean_generator.py").exists(), str(ETAPA3_DIR / "clean_generator.py"))
    c.add("FILE-DRIVER", "Existe p3.py", (ETAPA3_DIR / "p3.py").exists(), str(ETAPA3_DIR / "p3.py"))
    c.add("FILE-RESUMEN", "Existe resumen_p3.json", RESUMEN_PATH.exists(), str(RESUMEN_PATH))
    c.add("FILE-REPORTE", "Existe reporte_p3.md", REPORTE_PATH.exists(), str(REPORTE_PATH))

    if not (CONFIG_PATH.exists() and RESUMEN_PATH.exists()):
        print("[VALIDADOR P3] Faltan archivos requeridos para continuar.")
        return finish_and_save(c)

    # 2. Cargar configuración y resumen
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    with open(RESUMEN_PATH, "r", encoding="utf-8") as f:
        resumen = json.load(f)

    # 3. Versiones declaradas
    c.add("VER-CONFIG", "config_p3.json declara P3-CONFIG-1.0.0", cfg.get("version") == "P3-CONFIG-1.0.0", cfg.get("version", ""))
    c.add("VER-RESUMEN", "resumen_p3.json declara P3-1.0.0", resumen.get("version") == "P3-1.0.0", resumen.get("version", ""))

    # 4. Escenarios y archivos de datos
    scenarios_cfg = cfg.get("scenarios", [])
    scenarios_res = resumen.get("scenarios", [])
    c.add("SCENARIOS-COUNT", "Configuración declara exactamente 6 escenarios", len(scenarios_cfg) == 6, f"{len(scenarios_cfg)} escenarios")
    c.add("SCENARIOS-MATCH", "Resumen cubre los 6 escenarios", len(scenarios_res) == 6, f"{len(scenarios_res)} en resumen")

    sc_by_id = {s["id"]: s for s in scenarios_res}

    for sc in scenarios_cfg:
        sc_id = sc["id"]
        npz_file = DATOS_DIR / f"{sc_id}.npz"
        c.add(f"DATA-FILE-{sc_id}", f"Existe archivo de datos {sc_id}.npz", npz_file.exists(), str(npz_file))

        if not npz_file.exists():
            continue

        # Cargar archivo npz y verificar canales
        data = np.load(npz_file)
        channels_ok = all(ch in data for ch in ["Ex", "Ey", "Hx", "Hy", "Hz", "time_s"])
        c.add(f"CHANNELS-{sc_id}", f"{sc_id}.npz contiene canales Ex, Ey, Hx, Hy, Hz y time_s", channels_ok, f"Keys: {list(data.keys())[:6]}")

        # Comprobar residuo de cierre algebraico del escenario
        res_info = sc_by_id.get(sc_id, {})
        closure = res_info.get("closure_metrics", {})
        e_res = closure.get("e_rel_residual", 1.0)
        pasa_cierre = closure.get("pasa_cierre", False)
        c.add(
            f"CLOSURE-{sc_id}",
            f"{sc_id} residuo espectral ||E - ZH|| / ||E|| < 1e-8",
            bool(pasa_cierre and e_res < 1e-8),
            f"Residuo relativo = {e_res:.3e}",
        )

        # Comprobar reconstrucción FFT
        fft_err = res_info.get("max_fft_reconstruction_error", 1.0)
        c.add(
            f"FFT-RECON-{sc_id}",
            f"{sc_id} error de reconstrucción FFT roundtrip < 1e-12",
            bool(fft_err < 1e-12),
            f"Error FFT = {fft_err:.3e}",
        )

    # 5. Comprobaciones específicas de física y estimación
    # 5.1 Semiespacio D0 (CTRL-01)
    s1 = sc_by_id.get("CTRL-01-HALFSPACE-D0", {})
    est1 = s1.get("estimation_metrics", {})
    bias1 = est1.get("median_bias_log10_rho", 1.0)
    phase_err1 = est1.get("median_phase_err_deg", 90.0)
    cond1 = est1.get("median_cond_shh", 999.0)
    c.add("EST-RECOVERY-CTRL-01", "CTRL-01 recuperación P6: bias rho_a <= 0.01 dec, fase <= 0.5 deg", bool(bias1 <= 0.01 and phase_err1 <= 0.5), f"Bias={bias1:.4f} dec, ErrFase={phase_err1:.3f} deg")
    c.add("COND-SHH-CTRL-01", "CTRL-01 cond(S_HH) <= 2.0 (excitación ortogonal rica de rango 2)", bool(cond1 <= 2.0), f"cond={cond1:.3f}")

    # 5.2 Semiespacio D1 (CTRL-02)
    s2 = sc_by_id.get("CTRL-02-HALFSPACE-D1", {})
    est2 = s2.get("estimation_metrics", {})
    bias2 = est2.get("median_bias_log10_rho", 1.0)
    phase_err2 = est2.get("median_phase_err_deg", 90.0)
    c.add("EST-RECOVERY-CTRL-02", "CTRL-02 recuperación P6: bias rho_a <= 0.01 dec, fase <= 0.5 deg", bool(bias2 <= 0.01 and phase_err2 <= 0.5), f"Bias={bias2:.4f} dec, ErrFase={phase_err2:.3f} deg")

    # 5.3 Capas estratificadas S1 en D0 (CTRL-03)
    s3 = sc_by_id.get("CTRL-03-STRATIFIED-S1-D0", {})
    est3 = s3.get("estimation_metrics", {})
    bias3 = est3.get("median_bias_log10_rho", 1.0)
    phase_err3 = est3.get("median_phase_err_deg", 90.0)
    c.add("EST-RECOVERY-CTRL-03", "CTRL-03 estratificado S1: bias rho_a <= 0.02 dec, fase <= 0.5 deg", bool(bias3 <= 0.02 and phase_err3 <= 0.5), f"Bias={bias3:.4f} dec, ErrFase={phase_err3:.3f} deg")

    # 5.4 Abstención de Rango 1 (CTRL-04)
    s4 = sc_by_id.get("CTRL-04-ABSTENTION-RANK1", {})
    est4 = s4.get("estimation_metrics", {})
    rank1_det = est4.get("rank1_detected", False)
    cond4 = est4.get("median_cond_shh", 0.0)
    abst_trig = est4.get("abstention_triggered", False)
    c.add("RANK1-ABSTENTION-CTRL-04", "CTRL-04 detecta rango 1 y activa abstención (cond > 1e4)", bool(rank1_det and abst_trig and cond4 > 1e4), f"cond={cond4:.2e}, abstention={abst_trig}")

    # 5.5 Tipper Hz y no estacionariedad (CTRL-05)
    s5 = sc_by_id.get("CTRL-05-NONSTATIONARY-SFERICS", {})
    cl5 = s5.get("closure_metrics", {})
    hz_res5 = cl5.get("hz_rel_residual", 1.0)
    c.add("TIPPER-CLOSURE-CTRL-05", "CTRL-05 residuo relativo de tipper ||Hz - TH|| / ||Hz|| < 1e-8", bool(hz_res5 < 1e-8), f"Residuo Hz = {hz_res5:.3e}")

    # 5.6 Detección de clipping instrumental (CTRL-06)
    s6 = sc_by_id.get("CTRL-06-INSTRUMENT-ADC-SAT", {})
    est6 = s6.get("estimation_metrics", {})
    clip_det = est6.get("clipping_detected", False)
    clip_frac = est6.get("clip_fraction", 0.0)
    c.add("INSTRUMENT-CLIPPING-CTRL-06", "CTRL-06 detecta saturación ADC (clip_fraction > 0.05)", bool(clip_det and clip_frac > 0.05), f"clip_fraction = {clip_frac*100:.2f}%")

    # 6. Comprobación de aislamiento y ausencia de fuga hacia P0
    p0_val_path = WORKSPACE_ROOT / "etapa0" / "validacion_etapa0.json"
    if p0_val_path.exists():
        with open(p0_val_path, "r", encoding="utf-8") as f:
            p0_val = json.load(f)
        real_manifest_hash = sha256_file(WORKSPACE_ROOT / "etapa0" / "manifest.json")
        real_splits_hash = sha256_file(WORKSPACE_ROOT / "etapa0" / "splits.csv")
        p0_hash_ok = bool(
            real_manifest_hash == p0_val["manifest_sha256"]
            and real_splits_hash == p0_val["splits_sha256"]
        )
        c.add("ISOLATION-P0", "Manifiesto y particiones de P0 intactos (sin fuga de datos)", p0_hash_ok, f"Manifest hash={real_manifest_hash[:10]}...")
    else:
        c.add("ISOLATION-P0", "No se encontró validacion_etapa0.json para comparar hashes", False, is_observation=True)

    # 7. Cuarentena sintética
    c.add("CUARENTENA-FLAG", "config_p3 declara synthetic: true y scientific_claim: false", bool(cfg.get("synthetic") is True and cfg.get("scientific_claim") is False), f"synthetic={cfg.get('synthetic')}")

    return finish_and_save(c)


def finish_and_save(c: Checker) -> Dict[str, Any]:
    status = "APROBADO" if c.failed == 0 else "RECHAZADO"
    if c.failed == 0 and c.observations > 0:
        status = "APROBADO_CON_OBSERVACIONES"

    out = {
        "artifact": "validacion_etapa3",
        "version": "P3-VAL-1.0.0",
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "stage": 3,
        "gate": "P3",
        "status": status,
        "counts": {
            "checks": len(c.checks),
            "passed": c.passed,
            "failed": c.failed,
            "observations": c.observations,
        },
        "checks": c.checks,
    }

    with open(VALIDATION_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"\n[VALIDADOR P3] Resultado: {status} ({c.passed} PASA, {c.failed} FALLA, {c.observations} OBSERVACIONES)")
    print(f"[VALIDADOR P3] Detalle guardado en {VALIDATION_FILE}")
    return out


if __name__ == "__main__":
    res = run_validation()
    sys.exit(0 if res["counts"]["failed"] == 0 else 1)
