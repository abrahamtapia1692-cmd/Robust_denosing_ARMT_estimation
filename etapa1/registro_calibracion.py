#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registro de calibracion y auditoria de ganancias de P1.

Lee las tablas ``.clb`` ya inventariadas en P0, verifica su SHA-256, limpia el
empalme de 10 kHz, desenrolla la fase y construye una tabla de respuesta
compleja interpolada. No aplica ninguna correccion a las series temporales.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import comun_p1 as comun


GAIN_MAP = [
    (1.0, "CLB_G1_Ex_shifted", "1"),
    (1.77828, "CLB_G1.8_Ex_shifted", "1.8"),
    (3.16228, "CLB_G3.2_Ex_shifted", "3.2"),
    (5.62341, "CLB_G5.6_Ex_shifted", "5.6"),
    (10.0, "CLB_G10_Ex_shifted", "10"),
    (17.7828, "CLB_G18_Ex_shifted", "18"),
    (31.6228, "CLB_G32_Ex_shifted", "32"),
    (56.2341, "CLB_G56_Ex_shifted", "56"),
    (100.0, "CLB_G100_Ex_shifted", "100"),
]

NT_PER_A_PER_M = 4.0 * np.pi * 1e-4  # 1 A/m = 4*pi*1e-4 nT
V_PER_A_PER_M_TO_V_PER_NT = 1.0 / NT_PER_A_PER_M


def nearest_index(freqs, target):
    return int(np.argmin(np.abs(np.asarray(freqs) - target)))


def clean_table(freqs, log_amp, phase, config):
    """Devuelve la tabla limpia y el detalle de la auditoria de fase."""
    cal = config["calibration"]
    rel_tol = float(cal["near_duplicate_rel"])
    outlier_deg = float(cal["phase_outlier_deg"])

    freqs = np.asarray(freqs, dtype=float)
    log_amp = np.asarray(log_amp, dtype=float)
    phase = np.asarray(phase, dtype=float)

    raw_groups = comun.near_duplicate_groups(freqs, rel_tol)
    keep = comun.mark_phase_outliers(phase, outlier_deg)
    phase_clean, corrections = comun.branch_correct(phase, keep)

    removed = []
    previous = None
    for index in range(len(freqs)):
        if keep[index]:
            previous = index
            continue
        if previous is None:
            step = None
        else:
            step = phase[index] - phase[previous]
            step = (step + 180.0) % 360.0 - 180.0
        removed.append(
            {
                "index": int(index),
                "frequency_hz": float(freqs[index]),
                "phase_deg": float(phase[index]),
                "log10_amplitude": float(log_amp[index]),
                "step_vs_previous_kept_deg": None if step is None else float(step),
            }
        )

    kept_freqs = freqs[keep]
    kept_phase = phase_clean[keep]
    kept_log_amp = log_amp[keep]
    groups_kept = comun.near_duplicate_groups(kept_freqs, rel_tol)

    phase_steps = np.abs(np.diff(kept_phase)) if len(kept_phase) > 1 else np.array([0.0])
    amp_steps_db = (
        20.0 * np.abs(np.diff(kept_log_amp)) if len(kept_log_amp) > 1 else np.array([0.0])
    )
    max_phase_step = float(phase_steps.max())
    max_amp_step_db = float(amp_steps_db.max())
    at_phase = int(np.argmax(phase_steps)) + 1 if len(phase_steps) else 0
    at_amp = int(np.argmax(amp_steps_db)) + 1 if len(amp_steps_db) else 0

    splice = bool(
        [row for row in removed if abs(row["frequency_hz"] - 10000.0) / 10000.0 < 0.01]
    ) or any(
        np.any(np.abs(freqs[start:stop] - 10000.0) / 10000.0 < 0.01)
        for start, stop in raw_groups
    )
    splice_groups = []
    if splice:
        center = 10000.0
        near = np.flatnonzero(np.abs(freqs - center) / center < 1e-5)
        if near.size == 0:
            near = np.flatnonzero(np.abs(freqs - center) / center < 1e-3)
        splice_groups.append(
            {
                "center_hz": center,
                "frequencies_hz": [float(freqs[i]) for i in near],
                "kept_frequencies_hz": [float(freqs[i]) for i in near if keep[i]],
                "removed_indices": [int(i) for i in near if not keep[i]],
            }
        )

    audit = {
        "raw_frequency_count": int(len(freqs)),
        "used_frequency_count": int(keep.sum()),
        "near_duplicate_groups": [
            {
                "start_index": int(start),
                "stop_index": int(stop),
                "frequencies_hz": [float(v) for v in freqs[start:stop]],
            }
            for start, stop in raw_groups
        ],
        "near_duplicate_groups_after_cleaning": [
            {
                "start_index": int(start),
                "stop_index": int(stop),
                "frequencies_hz": [float(v) for v in kept_freqs[start:stop]],
            }
            for start, stop in groups_kept
        ],
        "outliers_removed": removed,
        "branch_corrections_360": int(corrections),
        "phase_unwrapped_min_deg": float(kept_phase.min()),
        "phase_unwrapped_max_deg": float(kept_phase.max()),
        "max_phase_step_deg": max_phase_step,
        "max_phase_step_at_hz": float(kept_freqs[at_phase]) if len(kept_freqs) else None,
        "max_amplitude_step_db": max_amp_step_db,
        "max_amplitude_step_at_hz": float(kept_freqs[at_amp]) if len(kept_freqs) else None,
        "splice_detected": splice,
        "splice_groups": splice_groups,
        "splice_phase_jump_deg": float(max_phase_step) if splice else 0.0,
        "splice_amplitude_jump_db": float(max_amp_step_db) if splice else 0.0,
        "splice_width_hz": (
            float(np.max(splice_groups[0]["frequencies_hz"]) - np.min(splice_groups[0]["frequencies_hz"]))
            if splice_groups
            else 0.0
        ),
        "phase_continuous": bool(max_phase_step <= float(cal["phase_continuity_deg"])),
        "amplitude_continuous": bool(max_amp_step_db <= float(cal["amplitude_continuity_db"])),
        "amplitude_units": "log10(amplitud) en el archivo; se exporta amplitud lineal",
    }
    return {
        "freqs": kept_freqs,
        "log_amp": kept_log_amp,
        "phase_deg": kept_phase,
        "audit": audit,
        "keep_mask": keep,
    }


def interpolate(clean, f_min, f_max, config):
    cal = config["calibration"]
    log_f = np.log10(clean["freqs"])
    log_a = clean["log_amp"]
    phase = clean["phase_deg"]
    # No se extrapola fuera del soporte de la tabla.
    f_min = max(f_min, float(clean["freqs"][0]))
    f_max = min(f_max, float(clean["freqs"][-1]))
    count = comun.interp_count(
        f_min, f_max, float(cal["interp_grid_per_decade"]), int(cal["interp_min_points"])
    )
    grid = np.geomspace(f_min, f_max, count)
    log_grid = np.log10(grid)
    amp = np.power(10.0, np.interp(log_grid, log_f, log_a))
    phase_grid = np.interp(log_grid, log_f, phase)
    return {
        "frequency_hz": grid,
        "amplitude": amp,
        "phase_deg": phase_grid,
        "phase_rad": np.deg2rad(phase_grid),
    }


def audit_gain_directories(config):
    """Compara el mismo numero de serie en los nueve directorios de ganancia."""
    SBFReader, read_calibration = comun.import_armt()  # noqa: F841
    root = Path(comun.load_p0_manifest()["sources"]["calibration_root"])
    record = comun.target_record()
    record_gain = float(record["settings"]["gains"][0][0])

    directory_rows = []
    for nominal, folder, label in GAIN_MAP:
        delta = (nominal - record_gain) / record_gain
        directory_rows.append(
            {
                "folder": folder,
                "label": label,
                "label_value": float(label),
                "nominal_gain": float(nominal),
                "nominal_gain_db": float(20.0 * np.log10(nominal)),
                "delta_rel_to_record": float(delta),
                "delta_pct_to_record": float(100.0 * delta),
                "selected": folder == "CLB_G1.8_Ex_shifted",
            }
        )

    probes = []
    for channel, prefix, serial in (
        ("Ex", "e", 100),
        ("Ey", "e", 101),
        ("Hx", "h", 200),
        ("Hy", "h", 201),
        ("Hz", "h", 202),
    ):
        filename = "%s%06d.clb" % (prefix, serial)
        by_directory = []
        for nominal, folder, label in GAIN_MAP:
            path = root / folder / filename
            if not path.is_file():
                continue
            calibration = read_calibration(str(path))
            table = calibration.tables[0]
            freqs = table.frequencies_hz
            amp = np.power(10.0, table.log10_amplitude[:, 0])
            phase = table.phase_degrees[:, 0]
            row = {"folder": folder, "label": label, "nominal_gain": float(nominal)}
            for target in (100.0, 10000.0):
                index = nearest_index(freqs, target)
                row["amplitude_%g_hz" % target] = float(amp[index])
                row["phase_%g_hz" % target] = float(phase[index])
                row["frequency_%g_hz" % target] = float(freqs[index])
            by_directory.append(row)

        summary = {"channel": channel, "serial_number": serial, "filename": filename}
        for target in (100.0, 10000.0):
            key = "amplitude_%g_hz" % target
            values = [row[key] for row in by_directory]
            selected = [row[key] for row in by_directory if row["folder"] == "CLB_G1.8_Ex_shifted"]
            summary["amplitude_%g_hz" % target] = {
                "min": float(np.min(values)),
                "max": float(np.max(values)),
                "median": float(np.median(values)),
                "spread_pct": float(100.0 * (np.max(values) - np.min(values)) / np.median(values)),
                "selected": float(selected[0]) if selected else None,
                "selected_vs_median_pct": (
                    float(100.0 * (selected[0] - np.median(values)) / np.median(values))
                    if selected
                    else None
                ),
            }
        summary["by_directory"] = by_directory
        probes.append(summary)

    manifest = comun.load_p0_manifest()
    table_counts = [entry["table_count"] for entry in manifest["calibration_files"]]
    table_gains = sorted(
        {float(table["gain"]) for entry in manifest["calibration_files"] for table in entry["tables"]}
    )
    files_with_gain_sections = sum(1 for entry in manifest["calibration_files"] if entry["table_count"] > 1)

    selected_label = 1.8
    rounding_ratio = record_gain / selected_label
    payload = {
        "audit_version": "P1-GAIN-AUDIT-1.0.0",
        "generated_at_utc": comun.utc_now(),
        "target_record": comun.TARGET_RECORD,
        "record_gain": float(record_gain),
        "record_gain_db": float(20.0 * np.log10(record_gain)),
        "record_gain_source": "SBF settings.gains[0][0] (una sola configuracion en el registro)",
        "selected_directory": "CLB_G1.8_Ex_shifted",
        "selected_label": selected_label,
        "selected_label_delta_rel": float((selected_label - record_gain) / record_gain),
        "selected_label_delta_pct": float(100.0 * (selected_label - record_gain) / record_gain),
        "divide_by_label_result_ratio": float(rounding_ratio),
        "divide_by_label_result_pct": float(100.0 * (rounding_ratio - 1.0)),
        "directory_map": directory_rows,
        "table_structure": {
            "files_total": len(manifest["calibration_files"]),
            "table_count_distribution": {
                str(value): int(table_counts.count(value)) for value in sorted(set(table_counts))
            },
            "unique_table_gain_values": table_gains,
            "files_with_gain_sections": int(files_with_gain_sections),
            "implication": (
                "Ningun .clb declara la ganancia aplicada. El manual (App. 7) preve secciones "
                "con gain para otras ganancias, pero los 73 archivos solo tienen la tabla por "
                "defecto con gain=1.0. La ganancia solo se conoce por el nombre del directorio."
            ),
        },
        "amplitude_probe": probes,
        "spread_conclusion": (
            "La amplitud de la tabla electrica no escala con la ganancia del directorio y "
            "difiere hasta ~25-32 % entre directorios para el mismo numero de serie. "
            "La tabla magnetica varia ~5 %. Elegir el directorio mas proximo no es una "
            "operacion neutra y no se puede certificar sin metadatos de calibracion."
        ),
        "double_compensation_risk": {
            "electric_amplitude_at_100_hz": 1.8706,
            "record_gain": float(record_gain),
            "ratio_table_over_gain": float(1.8706 / record_gain),
            "ratio_db": float(20.0 * np.log10(1.8706 / record_gain)),
            "note": (
                "La amplitud electrica de la tabla (V/V) esta cerca de la ganancia de registro "
                "(1.77828). Si la tabla ya incluye la ganancia del amplificador, dividir otra vez "
                "por 1.77828 introduciria una doble correccion de 5.00 dB. Si no la incluye, no "
                "aplicarla deja ese mismo sesgo. Los archivos no permiten decidirlo."
            ),
        },
        "unit_interpretation": {
            "manual_reference": "ARMT-5 user manual, Appendix 7, p. 70",
            "electric": "V/V para sensores electricos y grabador",
            "magnetic_literal": "V/(A/m) para sensores magneticos",
            "conversion_nT_per_A_per_m": float(NT_PER_A_PER_M),
            "V_per_A_per_m_to_V_per_nT": float(V_PER_A_PER_M_TO_V_PER_NT),
            "existing_code_factor": 1000.0,
            "existing_code_ratio_to_literal": float(1000.0 / V_PER_A_PER_M_TO_V_PER_NT),
            "field_ratio_code_over_literal": float(V_PER_A_PER_M_TO_V_PER_NT / 1000.0),
            "note": (
                "instrument_calibration.py multiplica la tabla H por 1000 como si estuviera en "
                "mV/nT. Si el manual se lee literalmente (V/(A/m)), el cociente de sensibilidades "
                "es 1.2566 y el campo calculado por ese codigo seria 0.7958 veces el literal "
                "(-20.4 %). La unidad real no esta verificada; P1 no aplica la tabla."
            ),
        },
        "conclusion": (
            "La cadena de ganancia no se puede cerrar con los archivos disponibles. P1 no aplica "
            "ganancia ni respuesta .clb; solo caracteriza y deja la decision registrada."
        ),
    }
    return payload


def build(config=None):
    config = config or comun.load_config()
    manifest = comun.load_p0_manifest()
    record = comun.target_record(manifest)
    SBFReader, read_calibration = comun.import_armt()  # noqa: F841

    # Las cinco respuestas se calculan una vez por canal y se reutilizan en D0/D1.
    channel_cache = {}
    bands_payload = {}
    csv_payload = {}

    for band in comun.band_list(config):
        f_min, f_max = comun.band_range(config, band)
        trace = record["traces"][int(config["bands"][band]["trace_index"])]
        channels_payload = []
        responses = {}

        for entry in trace["calibration_channels"]:
            channel = entry["channel"]
            selected = entry["selected"]
            path = Path(selected["path_ref"])
            if not path.is_absolute():
                path = comun.DEFAULT_SOFTWARE_ROOT / selected["path_ref"]
            actual_sha = comun.sha256_file(path)
            if actual_sha != selected["sha256"]:
                raise RuntimeError("SHA-256 distinto para %s" % path)

            key = (channel, selected["path_ref"])
            if key not in channel_cache:
                calibration = read_calibration(str(path))
                table = calibration.tables[0]
                freqs = table.frequencies_hz
                log_amp = table.log10_amplitude[:, 0]
                phase = table.phase_degrees[:, 0]
                clean = clean_table(freqs, log_amp, phase, config)
                channel_cache[key] = {
                    "calibration": calibration,
                    "table": table,
                    "clean": clean,
                }
            cached = channel_cache[key]
            clean = cached["clean"]
            table = cached["table"]

            support_low = float(np.min(clean["freqs"]))
            support_high = float(np.max(clean["freqs"]))
            tol = 1e-6 * max(1.0, abs(f_min), abs(f_max))
            covered = (support_low <= f_min + tol) and (support_high >= f_max - tol)
            if not covered:
                raise RuntimeError(
                    "%s: la calibracion no cubre %s (%.6g-%.6g Hz)"
                    % (channel, band, support_low, support_high)
                )

            response = interpolate(clean, f_min, f_max, config)
            responses[channel] = response

            gain_delta = float(selected["delta_rel"])
            channel_payload = {
                "channel": channel,
                "band": band,
                "sensor_type": entry["sensor_type"],
                "serial_number": int(entry["serial_number"]),
                "record_gain": float(entry["gain_record"]),
                "record_gain_db": float(20.0 * np.log10(entry["gain_record"])),
                "gain_directory": float(selected["gain_directory"]),
                "gain_delta_rel": gain_delta,
                "gain_delta_pct": float(100.0 * gain_delta),
                "table_index": 0,
                "table_gain": float(selected["table_gain"]),
                "clb": {
                    "path_ref": selected["path_ref"],
                    "sha256": selected["sha256"],
                    "size_bytes": int(path.stat().st_size),
                },
                "frequency_count_raw": int(len(table.frequencies_hz)),
                "frequency_count_used": int(len(clean["freqs"])),
                "frequency_min_hz": support_low,
                "frequency_max_hz": support_high,
                "band_review_hz": [f_min, f_max],
                "support_covered": bool(covered),
                "response_units": (
                    "V/V (manual App.7)"
                    if entry["sensor_type"] == "electrical_amplifier"
                    else "V/(A/m) (manual App.7); interpretacion no verificada"
                ),
                "audit": clean["audit"],
                "interpolated_response": {
                    "file": "respuesta_interpolada_%s.csv" % band,
                    "points": int(len(response["frequency_hz"])),
                    "f_min_hz": float(response["frequency_hz"][0]),
                    "f_max_hz": float(response["frequency_hz"][-1]),
                    "phase_continuous": clean["audit"]["phase_continuous"],
                    "usable_range_hz": (
                        [float(response["frequency_hz"][0]), min(float(response["frequency_hz"][-1]), 9900.0)]
                        if clean["audit"]["splice_detected"]
                        and float(response["frequency_hz"][-1]) > 9900.0
                        else [float(response["frequency_hz"][0]), float(response["frequency_hz"][-1])]
                    ),
                    "splice_note": (
                        "El extremo superior coincide con el empalme de 10 kHz; usar hasta 9.9 kHz "
                        "o tratar 10 kHz como escenario separado."
                        if clean["audit"]["splice_detected"]
                        and float(response["frequency_hz"][-1]) > 9900.0
                        else "sin empalme dentro de la banda revisada"
                    ),
                },
                "status": "candidata_no_verificada",
                "notes": [
                    "SHA-256 verificado contra el manifiesto P0",
                    "No se aplico ganancia, amplitud ni fase a las series temporales",
                    "Fecha, certificado y cadena de aplicacion siguen ausentes (B-P0-04)",
                    "La tabla electrica contiene un empalme anomalo cerca de 10 kHz; "
                    "el punto atipico se excluye solo para interpolar",
                ],
            }
            channels_payload.append(channel_payload)

        grid = next(iter(responses.values()))["frequency_hz"]
        bands_payload[band] = {
            "trace_index": int(config["bands"][band]["trace_index"]),
            "sample_rate_hz": float(trace["sample_rate_hz"]),
            "review_range_hz": [f_min, f_max],
            "effective_range_hz": [float(grid[0]), float(grid[-1])],
            "interp_points": int(len(grid)),
            "channels": channels_payload,
            "complete_channel_set": sorted(responses) == sorted(comun.CHANNELS),
        }
        csv_payload[band] = responses

    registry = {
        "registry_version": "P1-CALREG-1.0.0",
        "generated_at_utc": comun.utc_now(),
        "stage": 1,
        "target_record": comun.TARGET_RECORD,
        "source": record["source"],
        "p0_manifest_sha256": comun.sha256_file(comun.ETAPA0 / "manifest.json"),
        "manual_reference": "ARMT-5 user manual 1.0 ENG, Appendix 7, p. 70",
        "phase_convention": (
            "respuesta compleja = amplitud * exp(+i*phi), convencion de armt.calibration; "
            "el signo no se verifico contra un patron"
        ),
        "gain_chain": {
            "record_gain": float(record["settings"]["gains"][0][0]),
            "directory_label": 1.8,
            "table_gain": 1.0,
            "applied_in_export": False,
            "audit_file": "auditoria_ganancias.json",
        },
        "bands": bands_payload,
        "corrections_applied_to_export": {
            "adc_to_uv": True,
            "gain": False,
            "clb_amplitude": False,
            "clb_phase": False,
            "dipole_length": False,
            "polarity": False,
            "orientation": False,
        },
        "status": "PARCIAL",
        "status_reasons": [
            "Las calibraciones no tienen fecha, certificado ni cadena de aplicacion (B-P0-04)",
            "La amplitud electrica no es reproducible entre directorios de ganancia",
            "La unidad magnetica del manual (V/(A/m)) no coincide con el factor 1000 del codigo existente",
            "No hay calibracion de entradas del receptor (archivos r*.clb)",
            "No se aplico ninguna correccion de amplitud o fase a las series temporales",
        ],
        "blockers": ["B-P0-04", "B-P0-03", "B-P0-01", "B-P0-02"],
    }

    comun.dump_json(comun.ETAPA1 / "calibration_registry.json", registry)
    comun.dump_json(comun.ETAPA1 / "auditoria_ganancias.json", audit_gain_directories(config))

    for band, responses in csv_payload.items():
        path = comun.ETAPA1 / ("respuesta_interpolada_%s.csv" % band)
        header = ["frequency_hz"]
        for channel in comun.CHANNELS:
            header.extend([channel + "_amplitude", channel + "_phase_deg"])
        with open(path, "w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            grid = responses[comun.CHANNELS[0]]["frequency_hz"]
            for index, frequency in enumerate(grid):
                row = ["%.10g" % frequency]
                for channel in comun.CHANNELS:
                    row.append("%.9g" % responses[channel]["amplitude"][index])
                    row.append("%.6f" % responses[channel]["phase_deg"][index])
                writer.writerow(row)

    return {
        "registry": str(comun.ETAPA1 / "calibration_registry.json"),
        "gain_audit": str(comun.ETAPA1 / "auditoria_ganancias.json"),
        "responses": {
            band: str(comun.ETAPA1 / ("respuesta_interpolada_%s.csv" % band))
            for band in csv_payload
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    config = comun.load_config(args.config)
    result = build(config)
    print("registro de calibracion: %s" % result["registry"])
    print("auditoria de ganancias: %s" % result["gain_audit"])
    for band, path in result["responses"].items():
        print("respuesta %s: %s" % (band, path))


if __name__ == "__main__":
    main()
