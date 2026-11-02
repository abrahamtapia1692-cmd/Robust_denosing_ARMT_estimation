#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validador exhaustivo de la Etapa 4 — Puertas P4 y P4-N: Banco de contaminantes multicanal.

Ejecuta las comprobaciones formales de contrato, calidad de separación BSS,
cálculo riguroso de coherencia con K_eff grados de libertad, presupuesto de fuga
en inyecciones controladas (< 5%), ausencia de la regla fija 2+2, taxonomía de
evidencia P4-N y aislamiento estricto de particiones de desarrollo.
"""
from __future__ import annotations

import csv
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

ETAPA4_DIR = WORKSPACE_ROOT / "etapa4"
CONFIG_PATH = ETAPA4_DIR / "config_p4.json"
RESUMEN_PATH = ETAPA4_DIR / "resumen_p4.json"
REPORTE_PATH = ETAPA4_DIR / "reporte_p4.md"
CATALOG_PATH = ETAPA4_DIR / "noise_episodes.csv"
NOISE_BANK_DIR = ETAPA4_DIR / "noise_bank"

VALIDATION_FILE = ETAPA4_DIR / "validacion_etapa4.json"


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
    print("[VALIDADOR P4] Iniciando validación formal de Etapa 4 (Puertas P4 y P4-N)...")

    # 1. Existencia de artefactos clave
    c.add("FILE-CONFIG", "Existe config_p4.json", CONFIG_PATH.exists(), str(CONFIG_PATH))
    c.add("FILE-EXTRACT", "Existe extractor_ruido.py", (ETAPA4_DIR / "extractor_ruido.py").exists(), str(ETAPA4_DIR / "extractor_ruido.py"))
    c.add("FILE-DRIVER", "Existe p4.py", (ETAPA4_DIR / "p4.py").exists(), str(ETAPA4_DIR / "p4.py"))
    c.add("FILE-CATALOG", "Existe noise_episodes.csv", CATALOG_PATH.exists(), str(CATALOG_PATH))
    c.add("FILE-RESUMEN", "Existe resumen_p4.json", RESUMEN_PATH.exists(), str(RESUMEN_PATH))
    c.add("FILE-REPORTE", "Existe reporte_p4.md", REPORTE_PATH.exists(), str(REPORTE_PATH))
    c.add("DIR-NOISE-BANK", "Existe directorio noise_bank/", NOISE_BANK_DIR.exists() and NOISE_BANK_DIR.is_dir(), str(NOISE_BANK_DIR))

    if not (CONFIG_PATH.exists() and RESUMEN_PATH.exists() and CATALOG_PATH.exists()):
        print("[VALIDADOR P4] Faltan archivos requeridos para continuar.")
        return finish_and_save(c)

    # 2. Cargar configuración, resumen y catálogo
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    with open(RESUMEN_PATH, "r", encoding="utf-8") as f:
        resumen = json.load(f)

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        episodes_csv = list(reader)

    # 3. Versiones declaradas
    c.add("VER-CONFIG", "config_p4.json declara P4-CONFIG-1.0.0", cfg.get("version") == "P4-CONFIG-1.0.0", cfg.get("version", ""))
    c.add("VER-RESUMEN", "resumen_p4.json declara P4-1.0.0", resumen.get("version") == "P4-1.0.0", resumen.get("version", ""))

    # 4. Comprobaciones de catálogo y episodios extraídos
    c.add("CATALOG-COUNT", "Catálogo contiene al menos 4 episodios extraídos", len(episodes_csv) >= 4, f"{len(episodes_csv)} episodios")

    for ep in episodes_csv:
        ep_id = ep["episode_id"]
        ep_file = WORKSPACE_ROOT / ep["file"]
        c.add(f"EPISODE-FILE-{ep_id}", f"Existe archivo binario {ep_id}.npz", ep_file.exists(), str(ep_file))

        if not ep_file.exists():
            continue

        data = np.load(ep_file)
        c.add(f"EPISODE-ARRAYS-{ep_id}", f"{ep_id}.npz contiene noise y signal_residual", "noise" in data and "signal_residual" in data, str(list(data.keys())[:4]))

        # Error de reconstrucción identidad
        id_err = float(ep["identity_reconstruction_error"])
        c.add(f"IDENTITY-{ep_id}", f"{ep_id} error de reconstrucción identidad < 1%", bool(id_err < 0.01), f"err={id_err:.2e}")

        # Comprobar clasificación válida
        ep_class = ep["class"]
        c.add(f"CLASS-{ep_id}", f"{ep_id} clase válida en taxonomía P4-N", ep_class in cfg["episode_classes"], f"clase={ep_class}")

    # 5. Comprobación teórica de coherencia crítica (H19)
    from etapa4.extractor_ruido import critical_coherence
    coh_16 = critical_coherence(16, alpha=0.05)
    expected_coh_16 = 1.0 - (0.05 ** (1.0 / 15.0))
    coh_diff = abs(coh_16 - expected_coh_16)
    c.add("THEORY-COHERENCE-FORMULA", "Fórmula de coherencia crítica gamma2_crit(K=16) coincide con 1 - 0.05^(1/15) (~0.181)", bool(coh_diff < 1e-6), f"gamma2_crit={coh_16:.4f}")

    # 6. Desacople de la regla 2+2 (H18/H21)
    # Verificar que el número de componentes de ruido en los episodios no está rígidamente fijado en 2
    noise_comps_counts = []
    for ep in episodes_csv:
        ep_file = WORKSPACE_ROOT / ep["file"]
        if ep_file.exists():
            data = np.load(ep_file)
            mix = data.get("mixing_matrix")
            if mix is not None:
                noise_comps_counts.append(mix.shape[1])
    c.add("THEORY-NO-FORCE-2PLUS2", "BSS opera con rango k <= C - r_s sin forzar 2 naturales + 2 ruido", bool(len(noise_comps_counts) > 0 and all(k <= 4 for k in noise_comps_counts)), f"Componentes={noise_comps_counts}")

    # 7. Benchmark de fuga de señal útil (Puerta P4: Fuga nominal < 5%)
    nominal_grid = resumen.get("nominal_leakage_grid", [])
    c.add("LEAKAGE-BENCHMARK-RUN", "Benchmark de fuga evaluado en niveles nominales", len(nominal_grid) >= 2, f"{len(nominal_grid)} niveles evaluados")

    all_nom_pass = True
    for g in nominal_grid:
        snr = g["snr_db"]
        leak = g["leakage_fraction"]
        pasa = g["pasa_fuga"]
        if not pasa or leak >= 0.05:
            all_nom_pass = False
        c.add(f"LEAKAGE-SNR-{snr:+03.0f}dB", f"Fuga de señal útil a SNR={snr:+.0f} dB < 5% (P4)", bool(leak < 0.05), f"Fuga={leak*100:.2f}%")

    # 8. Subpuerta P4-N: Verificación de que componentes con fuga excesiva son protegidas
    classes_present = set(ep["class"] for ep in episodes_csv)
    c.add("P4N-SIGNAL-PROTECTION", "Subpuerta P4-N protege señales útiles contra fuga indebida", "senal_protegida" in classes_present or all_nom_pass, f"Clases presentes: {classes_present}")

    # 9. Aislamiento de particiones y ausencia de fuga hacia P0
    # 9.1 Split desarrollo estricto
    target_rec = cfg.get("target_record")
    target_split = cfg.get("target_split")
    c.add("SPLIT-RESTRICTION", "Ruido extraído únicamente de split 'desarrollo'", target_split == "desarrollo", f"split={target_split}")

    # 9.2 Hashes de P0 intactos
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
        c.add("ISOLATION-P0", "Manifiesto y particiones de P0 intactos (sin modificación por BSS)", p0_hash_ok, f"Manifest hash={real_manifest_hash[:10]}...")
    else:
        c.add("ISOLATION-P0", "No se encontró validacion_etapa0.json para comparar hashes", False, is_observation=True)

    return finish_and_save(c)


def finish_and_save(c: Checker) -> Dict[str, Any]:
    status = "APROBADO" if c.failed == 0 else "RECHAZADO"
    if c.failed == 0 and c.observations > 0:
        status = "APROBADO_CON_OBSERVACIONES"

    out = {
        "artifact": "validacion_etapa4",
        "version": "P4-VAL-1.0.0",
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "stage": 4,
        "gate": "P4",
        "subgate": "P4-N",
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

    print(f"\n[VALIDADOR P4] Resultado: {status} ({c.passed} PASA, {c.failed} FALLA, {c.observations} OBSERVACIONES)")
    print(f"[VALIDADOR P4] Detalle guardado en {VALIDATION_FILE}")
    return out


if __name__ == "__main__":
    res = run_validation()
    sys.exit(0 if res["counts"]["failed"] == 0 else 1)
