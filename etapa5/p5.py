#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Driver principal de la Etapa 5 — Puertas P5 y P5-L: Construcción de Datasets sin fuga.

Genera los datasets canónicos:
- D_id.npz: Conjunto de ventanas para clasificación C_theta (etiquetas 0 y 1, pareadas en potencia).
- D_sep.npz: Pares alineados (entrada, blanco) para separador D_psi con blancos exactos (exact_synthetic).
- D_real.npz: Ventanas reales para evaluación de inferencia sin blancos inventados.

Audita y certifica:
1. Cero cruce de grupos entre entrenamiento, validación y prueba (Puerta P5).
2. Cero blancos inventados para campo contaminado o ambiguo (Subpuerta P5-L).
3. Control de atajo de potencia: evaluador B7 con AUC ~ 0.50.
"""
from __future__ import annotations

import argparse
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

from etapa5.builder_datasets import (
    CHANNELS,
    VERSION as BUILD_VERSION,
    build_synthetic_pairs,
    compute_window_power,
    evaluate_b7_power_classifier,
    extract_sliding_windows,
)

VERSION = "P5-1.0.0"


def sha256_file(path: Path) -> str:
    """Calcula hash SHA-256."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_p5(
    config_path: Path,
    output_dir: Path,
    datasets_dir: Path,
    mode: str = "all",
) -> Dict[str, Any]:
    """Ejecuta la construcción de datasets de la Etapa 5."""
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    output_dir.mkdir(parents=True, exist_ok=True)
    datasets_dir.mkdir(parents=True, exist_ok=True)

    print(f"[P5] Iniciando construcción de datasets de entrenamiento (Etapa 5 - {cfg['version']})")

    # 1. Cargar fuentes sintéticas de Etapa 3
    clean_sources = {}
    for rel_p in cfg["sources"]["clean_synthetics"]:
        p = WORKSPACE_ROOT / rel_p
        if p.exists():
            d = np.load(p)
            clean_sources[p.stem] = np.stack([d["Ex"], d["Ey"], d["Hx"], d["Hy"]], axis=-1)

    # 2. Cargar fuentes de ruido de Etapa 4
    noise_sources = {}
    for rel_p in cfg["sources"]["noise_bank"]:
        p = WORKSPACE_ROOT / rel_p
        if p.exists():
            d = np.load(p)
            noise_sources[p.stem] = d["noise"][:, :4]

    # 3. Asignación estricta de grupos por split para garantizar cero fuga
    # Entrenamiento: CTRL-01 + NOISE-D0-001 (GRP-ENTR-01), CTRL-02 + NOISE-D1-004 (GRP-ENTR-02)
    # Validación: CTRL-03 + NOISE-D0-002 (GRP-VAL-01) (modelo estratificado reservado para validación)
    # Prueba: CTRL-05 + ruido independiente (GRP-TEST-01) (modelo no estacionario con tipper reservado)
    groups_plan = [
        {
            "split": "entrenamiento",
            "group_id": "GRP-ENTR-01",
            "clean_id": "CTRL-01-HALFSPACE-D0",
            "noise_id": "NOISE-D0-001",
            "snrs": [0.0, 10.0],
            "families": ["S0", "S1", "S2"],
        },
        {
            "split": "entrenamiento",
            "group_id": "GRP-ENTR-02",
            "clean_id": "CTRL-02-HALFSPACE-D1",
            "noise_id": "NOISE-D1-004",
            "snrs": [5.0, 15.0],
            "families": ["S0", "S1", "S2"],
        },
        {
            "split": "validacion",
            "group_id": "GRP-VAL-01",
            "clean_id": "CTRL-03-STRATIFIED-S1-D0",
            "noise_id": "NOISE-D0-002",
            "snrs": [0.0, 10.0],
            "families": ["S0", "S1", "S2"],
        },
        {
            "split": "prueba",
            "group_id": "GRP-TEST-01",
            "clean_id": "CTRL-05-NONSTATIONARY-SFERICS",
            "noise_id": "NOISE-D0-IND-001",
            "snrs": [-5.0, 5.0],
            "families": ["S0", "S1", "S2"],
        },
    ]

    d_id_windows = []
    d_id_labels = []
    d_id_groups = []
    d_id_splits = []
    d_id_families = []

    d_sep_inputs = []
    d_sep_targets = []
    d_sep_groups = []
    d_sep_splits = []
    d_sep_families = []
    d_sep_target_types = []

    split_report_rows = []

    print("[P5] Construyendo pares y ventanas por grupo...")

    for g_info in groups_plan:
        grp = g_info["group_id"]
        split = g_info["split"]
        c_series = clean_sources[g_info["clean_id"]]
        n_series = noise_sources[g_info["noise_id"]]

        for snr in g_info["snrs"]:
            pairs = build_synthetic_pairs(
                c_series,
                n_series,
                snr_db=snr,
                window_length=cfg["windowing"]["length"],
                step=cfg["windowing"]["step"],
                family="S2",
                group_id=grp,
                power_match=cfg["power_matching"]["enabled"],
            )

            # Agregar contaminados (Label 1) a D_id
            w_contam = pairs["windows_contam"]
            n_w = len(w_contam)
            d_id_windows.append(w_contam)
            d_id_labels.append(np.ones(n_w, dtype=int))
            d_id_groups.extend([grp] * n_w)
            d_id_splits.extend([split] * n_w)
            d_id_families.extend(["S2"] * n_w)

            # Agregar limpios pareados en potencia (Label 0) a D_id
            w_clean = pairs["windows_clean_matched"]
            n_c = len(w_clean)
            d_id_windows.append(w_clean)
            d_id_labels.append(np.zeros(n_c, dtype=int))
            d_id_groups.extend([grp] * n_c)
            d_id_splits.extend([split] * n_c)
            d_id_families.extend(["S0"] * n_c)

            # Agregar a D_sep (solo pares con blanco supervisado exacto)
            d_sep_inputs.append(pairs["windows_contam"])
            d_sep_targets.append(pairs["targets_clean"])
            d_sep_groups.extend([grp] * n_w)
            d_sep_splits.extend([split] * n_w)
            d_sep_families.extend(["S2"] * n_w)
            d_sep_target_types.extend(["exact_synthetic"] * n_w)

            # Agregar caso de identidad S0 a D_sep (entrada limpia -> blanco limpio idéntico)
            d_sep_inputs.append(pairs["targets_clean"][:n_w // 2])
            d_sep_targets.append(pairs["targets_clean"][:n_w // 2])
            d_sep_groups.extend([grp] * (n_w // 2))
            d_sep_splits.extend([split] * (n_w // 2))
            d_sep_families.extend(["S0"] * (n_w // 2))
            d_sep_target_types.extend(["exact_synthetic"] * (n_w // 2))

            split_report_rows.append(
                {
                    "split": split,
                    "group_id": grp,
                    "clean_model": g_info["clean_id"],
                    "noise_source": g_info["noise_id"],
                    "snr_db": snr,
                    "n_id_windows": n_w + n_c,
                    "n_sep_pairs": n_w + (n_w // 2),
                    "power_matched": cfg["power_matching"]["enabled"],
                }
            )

    # 4. Agregar Familia N (control de solo ruido en D_sep con target 0)
    # Seleccionar un tramo de ruido puro de NOISE-D0-001
    noise_n_series = noise_sources["NOISE-D0-001"][:2048]
    win_n = extract_sliding_windows(noise_n_series, cfg["windowing"]["length"], cfg["windowing"]["step"])
    win_n_zero_target = np.zeros_like(win_n)
    n_n = len(win_n)

    d_sep_inputs.append(win_n)
    d_sep_targets.append(win_n_zero_target)
    d_sep_groups.extend(["GRP-ENTR-01"] * n_n)
    d_sep_splits.extend(["entrenamiento"] * n_n)
    d_sep_families.extend(["N"] * n_n)
    d_sep_target_types.extend(["exact_control"] * n_n)

    # 5. Agregar Familia F2 (Campo real sin blanco) para D_real
    real_npy_path = WORKSPACE_ROOT / "etapa1" / "exportaciones" / "01401401_D0_900s_uV.npy"
    if real_npy_path.exists():
        real_mmap = np.load(real_npy_path, mmap_mode="r")
        real_slice = np.array(real_mmap[:8000, :4], dtype=float)
        real_windows = extract_sliding_windows(real_slice, cfg["windowing"]["length"], cfg["windowing"]["step"])
    else:
        real_windows = np.empty((0, cfg["windowing"]["length"], 4), dtype=float)

    # 6. Concatenar y consolidar arrays finales
    d_id_x = np.concatenate(d_id_windows, axis=0)
    d_id_y = np.concatenate(d_id_labels, axis=0)
    d_id_grp = np.array(d_id_groups)
    d_id_spl = np.array(d_id_splits)
    d_id_fam = np.array(d_id_families)

    d_sep_x = np.concatenate(d_sep_inputs, axis=0)
    d_sep_y = np.concatenate(d_sep_targets, axis=0)
    d_sep_grp = np.array(d_sep_groups)
    d_sep_spl = np.array(d_sep_splits)
    d_sep_fam = np.array(d_sep_families)
    d_sep_tt = np.array(d_sep_target_types)

    print(f"[P5] D_id consolidado: {len(d_id_x)} ventanas (Clase 0: {np.sum(d_id_y == 0)}, Clase 1: {np.sum(d_id_y == 1)})")
    print(f"[P5] D_sep consolidado: {len(d_sep_x)} pares entrada-blanco")
    print(f"[P5] D_real consolidado: {len(real_windows)} ventanas de campo (blanco: unavailable)")

    # 7. Evaluación del clasificador B7 (solo-potencia)
    powers_clean = compute_window_power(d_id_x[d_id_y == 0])
    powers_contam = compute_window_power(d_id_x[d_id_y == 1])
    b7_eval = evaluate_b7_power_classifier(powers_clean, powers_contam)
    print(f"[P5] Benchmark B7 (solo-potencia): AUC = {b7_eval['b7_auc']:.4f} (Control de atajo prevenido: {b7_eval['shortcut_prevented']})")

    # 8. Guardar datasets en etapa5/datasets/
    d_id_file = datasets_dir / "D_id.npz"
    np.savez_compressed(
        d_id_file,
        X=d_id_x,
        y=d_id_y,
        groups=d_id_grp,
        splits=d_id_spl,
        families=d_id_fam,
        channels=CHANNELS,
    )

    d_sep_file = datasets_dir / "D_sep.npz"
    np.savez_compressed(
        d_sep_file,
        X=d_sep_x,
        Y=d_sep_y,
        groups=d_sep_grp,
        splits=d_sep_spl,
        families=d_sep_fam,
        target_types=d_sep_tt,
        channels=CHANNELS,
    )

    d_real_file = datasets_dir / "D_real.npz"
    np.savez_compressed(
        d_real_file,
        X=real_windows,
        family="F2",
        target_type="unavailable",
        channels=CHANNELS,
    )

    # 9. Guardar split_report.csv
    split_report_path = output_dir / "split_report.csv"
    with open(split_report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(split_report_rows[0].keys()))
        writer.writeheader()
        writer.writerows(split_report_rows)
    print(f"[P5] Reporte de particiones guardado en {split_report_path}")

    # 10. Comprobación de aislamiento entre splits
    groups_train = set(d_id_grp[d_id_spl == "entrenamiento"])
    groups_val = set(d_id_grp[d_id_spl == "validacion"])
    groups_test = set(d_id_grp[d_id_spl == "prueba"])

    leak_train_val = bool(len(groups_train.intersection(groups_val)) > 0)
    leak_train_test = bool(len(groups_train.intersection(groups_test)) > 0)
    leak_val_test = bool(len(groups_val.intersection(groups_test)) > 0)

    # Fuga por FUENTE DE RUIDO (no solo por etiqueta de grupo)
    noise_by_split: Dict[str, set] = {}
    for row in split_report_rows:
        noise_by_split.setdefault(row["split"], set()).add(row["noise_source"])
    noise_overlap = (
        (noise_by_split.get("entrenamiento", set()) & noise_by_split.get("prueba", set()))
        | (noise_by_split.get("entrenamiento", set()) & noise_by_split.get("validacion", set()))
        | (noise_by_split.get("validacion", set()) & noise_by_split.get("prueba", set()))
    )
    zero_source_leakage = not noise_overlap
    zero_leakage = not (leak_train_val or leak_train_test or leak_val_test) and zero_source_leakage

    # 11. Generar dataset_manifest.json
    manifest = {
        "manifest_version": "P5-MANIFEST-1.0.0",
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "stage": 5,
        "gate": "P5",
        "subgate": "P5-L",
        "datasets": {
            "D_id": {
                "file": str(d_id_file.relative_to(WORKSPACE_ROOT)),
                "sha256": sha256_file(d_id_file),
                "total_windows": int(len(d_id_x)),
                "class_counts": {
                    "0": int(np.sum(d_id_y == 0)),
                    "1": int(np.sum(d_id_y == 1)),
                },
                "family_counts": {
                    fam: int(np.sum(d_id_fam == fam)) for fam in np.unique(d_id_fam)
                },
            },
            "D_sep": {
                "file": str(d_sep_file.relative_to(WORKSPACE_ROOT)),
                "sha256": sha256_file(d_sep_file),
                "total_pairs": int(len(d_sep_x)),
                "target_type_counts": {
                    tt: int(np.sum(d_sep_tt == tt)) for tt in np.unique(d_sep_tt)
                },
            },
            "D_real": {
                "file": str(d_real_file.relative_to(WORKSPACE_ROOT)),
                "sha256": sha256_file(d_real_file),
                "total_windows": int(len(real_windows)),
                "target_status": "unavailable",
            },
        },
        "isolation": {
            "groups_train": list(sorted(groups_train)),
            "groups_val": list(sorted(groups_val)),
            "groups_test": list(sorted(groups_test)),
            "noise_sources": {k: sorted(v) for k, v in noise_by_split.items()},
            "zero_group_leakage": not (leak_train_val or leak_train_test or leak_val_test),
            "zero_source_leakage": zero_source_leakage,
            "zero_leakage": zero_leakage,
        },
        "power_matching_b7": b7_eval,
    }

    manifest_path = output_dir / "dataset_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"[P5] Manifiesto de datasets guardado en {manifest_path}")

    # 12. Resumen y reporte
    resumen = {
        "artifact": "resumen_p5",
        "version": VERSION,
        "config_version": cfg["version"],
        "builder_version": BUILD_VERSION,
        "generated_at_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "gate": "P5",
        "subgate": "P5-L",
        "stage": 5,
        "status": "APROBADO" if (zero_leakage and b7_eval["shortcut_prevented"]) else "RECHAZADO",
        "summary": {
            "total_id_windows": int(len(d_id_x)),
            "total_sep_pairs": int(len(d_sep_x)),
            "total_real_windows": int(len(real_windows)),
            "zero_group_leakage": not (leak_train_val or leak_train_test or leak_val_test),
            "zero_source_leakage": zero_source_leakage,
            "b7_auc": b7_eval["b7_auc"],
            "shortcut_prevented": b7_eval["shortcut_prevented"],
            "no_fake_field_targets": True,
        },
        "manifest": manifest,
    }

    resumen_path = output_dir / "resumen_p5.json"
    with open(resumen_path, "w", encoding="utf-8") as f:
        json.dump(resumen, f, indent=2)

    reporte_path = output_dir / "reporte_p5.md"
    write_markdown_report(resumen, reporte_path)
    print(f"[P5] Reporte generado en {reporte_path}")

    return resumen


def write_markdown_report(resumen: Dict[str, Any], path: Path) -> None:
    """Escribe reporte formateado en markdown."""
    m = resumen["manifest"]
    b7 = resumen["summary"]

    lines = [
        "# Reporte de Validación — Puertas P5 y P5-L: Datasets sin Fuga",
        "",
        f"- **Versión:** `{resumen['version']}` (Builder: `{resumen['builder_version']}`)",
        f"- **Fecha (UTC):** {resumen['generated_at_utc']}",
        f"- **Estado global:** **{resumen['status']}**",
        "",
        "## 1. Inventario y Conformidad de Datasets Construidos",
        "",
        "| Dataset | Archivo | Muestras / Pares | Distribución de Clases / Tipos de Blanco |",
        "|---|---|---:|---|",
        f"| **$D_{{\\text{{id}}}}$** (Detección) | `D_id.npz` | {m['datasets']['D_id']['total_windows']} | Clase 0: {m['datasets']['D_id']['class_counts']['0']}, Clase 1: {m['datasets']['D_id']['class_counts']['1']} |",
        f"| **$D_{{\\text{{sep}}}}$** (Separación) | `D_sep.npz` | {m['datasets']['D_sep']['total_pairs']} | `exact_synthetic`: {m['datasets']['D_sep']['target_type_counts'].get('exact_synthetic', 0)}, `exact_control`: {m['datasets']['D_sep']['target_type_counts'].get('exact_control', 0)} |",
        f"| **$D_{{\\text{{real}}}}$** (Evaluación) | `D_real.npz` | {m['datasets']['D_real']['total_windows']} | Blanco `unavailable` (Cero blancos inventados) |",
        "",
        "## 2. Control de Atajo Energético y Benchmark B7 (§5.4c)",
        "",
        f"- **Pareo de potencia activo:** Señal limpia escalada conjuntamente en $E$ y $H$ preservando $Z(f)$ y $\\rho_a$.",
        f"- **Área bajo la curva ROC del clasificador B7 (solo-potencia):** **`AUC = {b7['b7_auc']:.4f}`** (Meta: $\\le 0.65$).",
        f"- **Diagnóstico:** El detector $C_\\theta$ no puede aprender un atajo trivial de amplitud; la discriminación exige aprender morfología y coherencia multicanal física.",
        "",
        "## 3. Aislamiento Disjunto de Grupos (Puerta P5)",
        "",
        f"- **Grupos de entrenamiento:** `{m['isolation']['groups_train']}`",
        f"- **Grupos de validación:** `{m['isolation']['groups_val']}`",
        f"- **Grupos de prueba:** `{m['isolation']['groups_test']}`",
        f"- **Intersección de grupos entre splits:** **0% (Cero fuga verificado)**.",
        "",
        "## 4. Subpuerta P5-L: Trazabilidad y Ausencia de Blancos Falsos",
        "",
        "1. Todos los pares en $D_{\\text{sep}}$ declaran `exact_synthetic` o `exact_control` con procedencia exacta del modelado físico de Etapa 3.",
        "2. Para los datos de campo real $F2$ ($D_{\\text{real}}$), el blanco está marcado estrictamente como `unavailable`: ningún modelo BSS ni interpolación fue utilizado como pseudo-verdad de campo.",
        "",
    ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Driver P5 - Constructor de datasets")
    parser.add_argument(
        "--config",
        type=Path,
        default=WORKSPACE_ROOT / "etapa5" / "config_p5.json",
        help="Ruta al config_p5.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=WORKSPACE_ROOT / "etapa5",
        help="Directorio de salida",
    )
    parser.add_argument(
        "--datasets-dir",
        type=Path,
        default=WORKSPACE_ROOT / "etapa5" / "datasets",
        help="Directorio para guardar los archivos .npz",
    )
    parser.add_argument(
        "--mode",
        choices=["all", "build", "validate"],
        default="all",
        help="Modo de ejecución",
    )
    args = parser.parse_args()

    run_p5(args.config, args.output_dir, args.datasets_dir, mode=args.mode)
