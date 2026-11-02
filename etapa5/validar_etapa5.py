#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validador exhaustivo de la Etapa 5 — Puertas P5 y P5-L: Datasets sin fuga de información.

Verifica:
1. Existencia, esquema y versiones de D_id, D_sep y D_real.
2. Cero cruce de grupos entre particiones de entrenamiento, validación y prueba (Puerta P5).
3. Cero blancos inventados para datos de campo o ambiguos (Subpuerta P5-L).
4. Alineación dimensional exacta entre entrada y blanco en D_sep.
5. Control de atajo de potencia: AUC del clasificador B7 <= 0.65.
6. Aislamiento e integridad estricta del piloto P0.
"""
from __future__ import annotations

import csv
import datetime
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict

import numpy as np

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

ETAPA5_DIR = WORKSPACE_ROOT / "etapa5"
CONFIG_PATH = ETAPA5_DIR / "config_p5.json"
MANIFEST_PATH = ETAPA5_DIR / "dataset_manifest.json"
SPLIT_REPORT_PATH = ETAPA5_DIR / "split_report.csv"
RESUMEN_PATH = ETAPA5_DIR / "resumen_p5.json"
REPORTE_PATH = ETAPA5_DIR / "reporte_p5.md"
DATASETS_DIR = ETAPA5_DIR / "datasets"

D_ID_PATH = DATASETS_DIR / "D_id.npz"
D_SEP_PATH = DATASETS_DIR / "D_sep.npz"
D_REAL_PATH = DATASETS_DIR / "D_real.npz"

VALIDATION_FILE = ETAPA5_DIR / "validacion_etapa5.json"


def sha256_file(path: Path) -> str:
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
    print("[VALIDADOR P5] Iniciando validación formal de Etapa 5 (Puertas P5 y P5-L)...")

    # 1. Existencia de artefactos
    c.add("FILE-CONFIG", "Existe config_p5.json", CONFIG_PATH.exists(), str(CONFIG_PATH))
    c.add("FILE-BUILDER", "Existe builder_datasets.py", (ETAPA5_DIR / "builder_datasets.py").exists(), str(ETAPA5_DIR / "builder_datasets.py"))
    c.add("FILE-DRIVER", "Existe p5.py", (ETAPA5_DIR / "p5.py").exists(), str(ETAPA5_DIR / "p5.py"))
    c.add("FILE-MANIFEST", "Existe dataset_manifest.json", MANIFEST_PATH.exists(), str(MANIFEST_PATH))
    c.add("FILE-SPLIT-REPORT", "Existe split_report.csv", SPLIT_REPORT_PATH.exists(), str(SPLIT_REPORT_PATH))
    c.add("FILE-RESUMEN", "Existe resumen_p5.json", RESUMEN_PATH.exists(), str(RESUMEN_PATH))
    c.add("FILE-REPORTE", "Existe reporte_p5.md", REPORTE_PATH.exists(), str(REPORTE_PATH))
    c.add("FILE-D-ID", "Existe D_id.npz", D_ID_PATH.exists(), str(D_ID_PATH))
    c.add("FILE-D-SEP", "Existe D_sep.npz", D_SEP_PATH.exists(), str(D_SEP_PATH))
    c.add("FILE-D-REAL", "Existe D_real.npz", D_REAL_PATH.exists(), str(D_REAL_PATH))

    if not (CONFIG_PATH.exists() and MANIFEST_PATH.exists() and D_ID_PATH.exists() and D_SEP_PATH.exists()):
        print("[VALIDADOR P5] Faltan archivos requeridos para continuar.")
        return finish_and_save(c)

    # 2. Cargar manifiesto y resumen
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(RESUMEN_PATH, "r", encoding="utf-8") as f:
        resumen = json.load(f)

    # 3. Versiones
    c.add("VER-CONFIG", "config_p5.json declara P5-CONFIG-1.0.0", cfg.get("version") == "P5-CONFIG-1.0.0", cfg.get("version", ""))
    c.add("VER-MANIFEST", "dataset_manifest.json declara P5-MANIFEST-1.0.0", manifest.get("manifest_version") == "P5-MANIFEST-1.0.0", manifest.get("manifest_version", ""))
    c.add("VER-RESUMEN", "resumen_p5.json declara P5-1.0.0", resumen.get("version") == "P5-1.0.0", resumen.get("version", ""))

    # 4. Validar D_id
    d_id = np.load(D_ID_PATH)
    x_id = d_id["X"]
    y_id = d_id["y"]
    grp_id = d_id["groups"]
    spl_id = d_id["splits"]

    c.add("D-ID-SHAPE", "D_id tiene forma (N, 256, 4)", x_id.ndim == 3 and x_id.shape[1] == 256 and x_id.shape[2] == 4, str(x_id.shape))
    c.add("D-ID-LABELS-MATCH", "D_id X y labels y tienen la misma longitud", len(x_id) == len(y_id), f"{len(x_id)} vs {len(y_id)}")

    count_0 = int(np.sum(y_id == 0))
    count_1 = int(np.sum(y_id == 1))
    balance_ratio = min(count_0, count_1) / max(count_0, count_1)
    c.add("D-ID-BALANCED", "D_id clases 0 y 1 equilibradas (ratio >= 0.90)", bool(balance_ratio >= 0.90), f"Clase 0: {count_0}, Clase 1: {count_1} (ratio={balance_ratio:.3f})")

    # 5. Validar D_sep
    d_sep = np.load(D_SEP_PATH)
    x_sep = d_sep["X"]
    y_sep = d_sep["Y"]
    tt_sep = d_sep["target_types"]

    c.add("D-SEP-ALIGNMENT", "D_sep entrada X y blanco Y tienen forma idéntica", x_sep.shape == y_sep.shape, f"X={x_sep.shape}, Y={y_sep.shape}")
    c.add("D-SEP-CHANNELS", "D_sep tiene 4 canales Ex, Ey, Hx, Hy", x_sep.shape[2] == 4, str(x_sep.shape))

    # 6. Subpuerta P5-L: Cero blancos inventados
    allowed_target_types = {"exact_synthetic", "exact_control"}
    all_target_types = set(np.unique(tt_sep))
    no_fake_targets = all_target_types.issubset(allowed_target_types)
    c.add("NO-INVENTED-TARGETS", "D_sep solo contiene blancos declarados exact_synthetic o exact_control", no_fake_targets, f"Tipos presentes: {all_target_types}")

    # Verificar D_real
    d_real = np.load(D_REAL_PATH)
    real_target_type = str(d_real.get("target_type", ""))
    c.add("D-REAL-NO-FAKE-TARGET", "D_real declara target_type='unavailable' (sin blanco inventado)", real_target_type == "unavailable", f"target_type={real_target_type}")

    # 7. Puerta P5: Cero cruce de grupos entre particiones
    groups_train = set(grp_id[spl_id == "entrenamiento"])
    groups_val = set(grp_id[spl_id == "validacion"])
    groups_test = set(grp_id[spl_id == "prueba"])

    c.add("DISJOINT-TRAIN-VAL", "Grupos disjuntos entre entrenamiento y validación", len(groups_train.intersection(groups_val)) == 0, f"train={groups_train}, val={groups_val}")
    c.add("DISJOINT-TRAIN-TEST", "Grupos disjuntos entre entrenamiento y prueba", len(groups_train.intersection(groups_test)) == 0, f"train={groups_train}, test={groups_test}")
    c.add("DISJOINT-VAL-TEST", "Grupos disjuntos entre validación y prueba", len(groups_val.intersection(groups_test)) == 0, f"val={groups_val}, test={groups_test}")

    # 8. Control de atajo de potencia (B7)
    b7_auc = float(manifest.get("power_matching_b7", {}).get("b7_auc", 1.0))
    shortcut_prevented = bool(manifest.get("power_matching_b7", {}).get("shortcut_prevented", False))
    c.add("POWER-MATCHING-B7", "Clasificador B7 (solo-potencia) AUC <= 0.65 (atajo prevenido)", bool(shortcut_prevented and b7_auc <= 0.65), f"B7 AUC={b7_auc:.4f}")

    # 9. Aislamiento e integridad de P0
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

    return finish_and_save(c)


def finish_and_save(c: Checker) -> Dict[str, Any]:
    status = "APROBADO" if c.failed == 0 else "RECHAZADO"
    if c.failed == 0 and c.observations > 0:
        status = "APROBADO_CON_OBSERVACIONES"

    out = {
        "artifact": "validacion_etapa5",
        "version": "P5-VAL-1.0.0",
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "stage": 5,
        "gate": "P5",
        "subgate": "P5-L",
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

    print(f"\n[VALIDADOR P5] Resultado: {status} ({c.passed} PASA, {c.failed} FALLA, {c.observations} OBSERVACIONES)")
    print(f"[VALIDADOR P5] Detalle guardado en {VALIDATION_FILE}")
    return out


if __name__ == "__main__":
    res = run_validation()
    sys.exit(0 if res["counts"]["failed"] == 0 else 1)
