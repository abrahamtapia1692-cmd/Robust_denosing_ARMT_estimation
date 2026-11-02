#!/usr/bin/env python3
"""Genera el banco sintetico de contrato S0/S1.

No lee muestras del SBF objetivo: solo toma del manifiesto P0 el identificador,
la particion y las trazas D0/D1. Los archivos ``.tem`` generados son fixtures
de formato y soporte, no mediciones del sitio.
"""

import argparse
from pathlib import Path

import numpy as np

from comun import (
    DEFAULT_MODEL,
    DEFAULT_OUT_DIR,
    WORKSPACE,
    file_entry,
    load_real_context,
    python_version,
    read_json,
    sha256_file,
    utc_now,
    write_json,
)
from modelo_surrogate import (
    _reference_rhos,
    apparent_resistivity,
    forward,
    gate_times_ms,
)


def scenario_kernels(scenario, model):
    if scenario.get("kernels") is not None:
        return scenario["kernels"]
    return model["surrogate"]["kernels"]


def scenario_anchors(scenario, model):
    if scenario.get("amplitude_anchors_ms_nv_per_a") is not None:
        return scenario["amplitude_anchors_ms_nv_per_a"]
    return model["surrogate"]["amplitude_anchors_ms_nv_per_a"]


def write_tem(path, scenario, model, gates, voltage, resistivity, target):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "<HEADER INFO>",
        "TEM_ID        %s" % scenario["tem_id"],
        "PROJECT       SYNTHETIC_CONTRACT_BENCH",
        "AREA          -",
        "CLIENT        -",
        "CONTRACTOR    -",
        "OPERATOR      -",
        "CONDITIONS    synthetic_contract_fixture_not_maxwell",
        "",
        "<COORDINATES>",
        "TYPE          NONE",
        "DATUM",
        "RXLAT         -",
        "RXLONG        -",
        "TXLAT         -",
        "TXLONG        -",
        "ELEVATION     -",
        "",
        "<BLOCK>",
        "<ACQUISITION PARAMETERS>",
        "ACQUISITION_DATE            -",
        "ACQUISITION_TIME            -",
        "RECEIVER      SYNTHETIC",
        "TRANSMITTER   SYNTHETIC",
        "CONFIGURATION SINGLE",
        "TXAREA        10000.0",
        "RXAREA        10000.0",
        "CURRENT       1.0",
        "REPTRATE      1.0",
        "TIMESERIES    -",
        "TURNOFF       10.0",
        "ANTENNA_DELAY 0.0",
        "FILTER_DELAY  0.0",
        "USER_DELAY    0.0",
        "",
        "<PROCESSING PARAMETERS>",
        "FILEDATE      SYNTHETIC",
        "PROGRAM       banco_sintetico/generar_tem_sintetico.py",
        "FILEVERSION   SYNTHETIC CONTRACT 1.0.0",
        "",
        "<INPUT FILE INFO>",
        "INFILE        -",
        "RUNS          1",
        "# RunNum, GroupNum, Gain",
        "-",
        "",
        "<DATA>",
        "# Fixture sintetico de contrato. No es una medicion TEM del sitio.",
        "# target_record %s" % target["record_id"],
        "# target_split %s" % target["split"],
        "# scenario %s" % scenario["id"],
        "# synthetic true",
        "# scientific_claim false",
        "# t(i) = USER_DELAY + t0(i)",
        "# Time [ms], Voltage [nV/A], Resistivity [Ohmm]",
    ]
    for t, v, r in zip(gates, voltage, resistivity):
        lines.append("%.6e  %.6e  %.6e" % (float(t), float(v), float(r)))
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")


def build(model, real_context, out_dir, model_path=DEFAULT_MODEL):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model_sha = sha256_file(model_path)
    generator_sha = sha256_file(Path(__file__).resolve())
    seed = int(model["noise"]["seed"])
    sigma = float(model["noise"]["multiplicative_sigma"])
    additive_sigma = float(model["noise"]["additive_nv_per_a"])
    base_rhos = _reference_rhos(model)

    scenarios = []
    for index, scenario in enumerate(model["scenarios"]):
        gates = gate_times_ms(model)
        kernels = scenario_kernels(scenario, model)
        anchors = scenario_anchors(scenario, model)
        clean = forward(gates, model, base_rhos, kernels, anchors)

        rng = np.random.default_rng(seed + index)
        multiplicative = rng.lognormal(mean=0.0, sigma=sigma, size=gates.size)
        additive = rng.normal(0.0, additive_sigma, size=gates.size)
        observed = np.clip(clean * multiplicative + additive, 1.0, None)

        if scenario["mode"] == "constante_sin_decaimiento":
            resistivity = np.zeros_like(gates)
            interpretable = False
            data_quality = "sin_decaimiento_util"
        else:
            resistivity = apparent_resistivity(gates, model)
            interpretable = True
            data_quality = "surrogate_capas"

        tem_path = out_dir / scenario["file"]
        write_tem(
            tem_path,
            scenario,
            model,
            gates,
            observed,
            resistivity,
            real_context,
        )

        truth = {
            "truth_version": "SYN-TRUTH-1.0.0",
            "scenario": scenario["id"],
            "tem_id": scenario["tem_id"],
            "synthetic": True,
            "scientific_claim": False,
            "target_record": real_context["record_id"],
            "target_split": real_context["split"],
            "target_traces": real_context["traces"],
            "model_version": model["version"],
            "model_sha256": model_sha,
            "generator_sha256": generator_sha,
            "seed": seed + index,
            "gates_ms": [float(value) for value in gates],
            "voltage_clean_nv_per_a": [float(value) for value in clean],
            "voltage_nv_per_a": [float(value) for value in observed],
            "resistivity_ohm_m": [float(value) for value in resistivity],
            "resistivity_interpretable": interpretable,
            "layers": model["layers"],
            "kernels": kernels,
            "amplitude_anchors_ms_nv_per_a": anchors,
            "noise": {
                "seed": seed + index,
                "multiplicative_sigma": sigma,
                "additive_nv_per_a": additive_sigma,
            },
            "data_quality": data_quality,
            "tem_file_sha256": sha256_file(tem_path),
            "tem_file_size_bytes": tem_path.stat().st_size,
            "notes": [
                "La verdad sintetica es declarada y no representa el subsuelo del sitio.",
                "El modelo directo es un surrogate de contrato, no una solucion de Maxwell.",
                "Los voltajes no se calibraron contra ningun instrumento real.",
            ],
        }
        truth_path = out_dir / ("verdad_%s.json" % scenario["id"])
        write_json(truth_path, truth)

        scenarios.append(
            {
                "id": scenario["id"],
                "tem_id": scenario["tem_id"],
                "purpose": scenario["purpose"],
                "mode": scenario["mode"],
                "expected": scenario["expected"],
                "tem_file": file_entry(tem_path),
                "truth_file": file_entry(truth_path),
                "support_file": None,
            }
        )

    manifest = {
        "manifest_version": "1.0.0",
        "artifact": "banco_sintetico_contrato",
        "generated_at_utc": utc_now(),
        "synthetic": True,
        "scientific_claim": False,
        "purpose": model["purpose"],
        "target_record": {
            "record_id": real_context["record_id"],
            "split": real_context["split"],
            "campaign_group": real_context["campaign_group"],
            "site_group": real_context["site_group"],
            "source_path_ref": real_context["source_path_ref"],
            "source_sha256": real_context["source_sha256"],
            "traces": real_context["traces"],
        },
        "real_inputs": {
            "manifest": file_entry(WORKSPACE / "etapa0" / "manifest.json"),
            "splits": file_entry(WORKSPACE / "etapa0" / "splits.csv"),
            "p0_validation": file_entry(WORKSPACE / "etapa0" / "validacion_etapa0.json"),
            "manifest_sha256_p0": real_context["p0_manifest_sha256"],
            "splits_sha256_p0": real_context["p0_splits_sha256"],
        },
        "model": file_entry(model_path),
        "generator": {
            "script": "banco_sintetico/generar_tem_sintetico.py",
            "sha256": generator_sha,
            "python": python_version(),
        },
        "quarantine": {
            "directory": "banco_sintetico",
            "id_prefix": "SYN-TEM-",
            "real_manifest_modified": False,
            "real_splits_modified": False,
            "allowed_target_splits": ["desarrollo"],
            "p2t_evidence": False,
            "training_labels": False,
            "note": (
                "El banco no se registra en etapa0/manifest.json ni en splits.csv. "
                "No cierra B-P0-03, no cierra P2-T y no habilita etiquetas de "
                "entrenamiento."
            ),
        },
        "scenarios": scenarios,
        "support": {
            "status": "pendiente",
            "version": None,
            "generated_at_utc": None,
            "files": [],
        },
        "notes": [
            "Fixture de contrato; el modelo directo es un surrogate fenomenologico, no Maxwell.",
            "No usa muestras del SBF objetivo; solo su identificador, particion y trazas D0/D1.",
            "S0 representa ausencia de informacion; S1 representa soporte parcial declarado.",
            "Los rangos de soporte prueban la logica de clasificacion, no el subsuelo del sitio.",
        ],
    }
    write_json(out_dir / "manifiesto_sintetico.json", manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    model = read_json(args.model)
    real_context = load_real_context(model)
    manifest = build(model, real_context, args.out_dir, args.model)

    print("Banco sintetico: %s" % Path(args.out_dir).resolve())
    print("Registro objetivo: %s (%s)" % (manifest["target_record"]["record_id"], manifest["target_record"]["split"]))
    for scenario in manifest["scenarios"]:
        print(
            "  %s %s -> %s"
            % (scenario["id"], scenario["tem_id"], scenario["tem_file"]["path_ref"])
        )
    print("Manifiesto: %s" % (Path(args.out_dir) / "manifiesto_sintetico.json").resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
