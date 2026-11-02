#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Barrido P1 de los 15 registros de P0 sobre D0/D1.

Extiende la Etapa 1 al conjunto completo de registros sin reexportar series
temporales: verifica el SHA-256 del SBF, ejecuta el mismo QC irreversible, cruza
la cobertura de calibracion por canal y resume la ganancia de cada registro.

No modifica P0 ni los proyectos de origen. Las unicas series temporales
exportadas a `.npy` siguen siendo las del registro objetivo de P1.
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import comun_p1 as comun
import qc_tiempo
from registro_calibracion import GAIN_MAP, clean_table

QC_FIELDS = [
    "record_id",
    "split",
    "band",
    "channel",
    "n_samples",
    "sample_rate_hz",
    "duration_s",
    "minimum_counts",
    "maximum_counts",
    "mean_counts",
    "std_counts",
    "zero_count",
    "clip_runs",
    "stuck_runs",
    "zero_fill_runs",
    "jump_count",
    "dead_channel",
    "bad_samples",
    "bad_fraction",
    "band_status",
]

CAL_FIELDS = [
    "record_id",
    "split",
    "band",
    "channel",
    "sensor_type",
    "serial_number",
    "clb_path_ref",
    "clb_sha256",
    "table_gain",
    "frequency_min_hz",
    "frequency_max_hz",
    "band_low_hz",
    "band_high_hz",
    "covered",
    "gain_record",
    "gain_directory",
    "delta_pct",
    "splice_detected",
    "phase_continuous",
    "phase_max_step_deg",
    "amplitude_max_step_db",
    "sha_verified",
    "status",
]

GAIN_FIELDS = [
    "record_id",
    "split",
    "campaign_group",
    "gain_unique",
    "gain_db",
    "nearest_directory",
    "nearest_label",
    "delta_pct",
    "adc_to_uv_d0",
    "adc_to_uv_d1",
    "dipole_ex_cm",
    "dipole_ey_cm",
    "azimuth_deg",
    "delay_s",
    "start_time_d0",
    "start_time_d1",
    "settings_sections",
    "bands_present",
]


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def gain_values(record):
    values = []
    for row in record["settings"].get("gains") or []:
        for value in row:
            values.append(float(value))
    return sorted({round(value, 9) for value in values})


def nearest_gain_label(gain):
    return min(GAIN_MAP, key=lambda item: abs(item[0] - gain) / gain)


def calibration_rows(record, config, band, cache, read_calibration):
    low, high = comun.band_range(config, band)
    trace_index = int(config["bands"][band]["trace_index"])
    trace = record["traces"][trace_index]
    rows = []
    for entry in trace["calibration_channels"]:
        channel = entry["channel"]
        selected = entry["selected"]
        path = Path(selected["path_ref"])
        if not path.is_absolute():
            path = comun.DEFAULT_SOFTWARE_ROOT / selected["path_ref"]
        if not path.is_file():
            raise FileNotFoundError("calibracion ausente: %s" % path)
        actual_sha = comun.sha256_file(path)

        key = str(path)
        if key not in cache:
            calibration = read_calibration(key)
            table = calibration.tables[0]
            clean = clean_table(
                table.frequencies_hz,
                table.log10_amplitude[:, 0],
                table.phase_degrees[:, 0],
                config,
            )
            cache[key] = {"table": table, "clean": clean}
        cached = cache[key]
        clean = cached["clean"]
        table = cached["table"]

        support_low = float(np.min(clean["freqs"]))
        support_high = float(np.max(clean["freqs"]))
        tol = 1e-6 * max(1.0, abs(low), abs(high))
        covered = bool(support_low <= low + tol and support_high >= high - tol)

        rows.append(
            {
                "record_id": record["record_id"],
                "split": record["split"]["split"],
                "band": band,
                "channel": channel,
                "sensor_type": entry["sensor_type"],
                "serial_number": int(entry["serial_number"]),
                "clb_path_ref": selected["path_ref"],
                "clb_sha256": selected["sha256"],
                "table_gain": float(selected["table_gain"]),
                "frequency_min_hz": support_low,
                "frequency_max_hz": support_high,
                "band_low_hz": float(low),
                "band_high_hz": float(high),
                "covered": covered,
                "gain_record": float(entry["gain_record"]),
                "gain_directory": float(selected["gain_directory"]),
                "delta_pct": float(100.0 * selected["delta_rel"]),
                "splice_detected": bool(clean["audit"]["splice_detected"]),
                "phase_continuous": bool(clean["audit"]["phase_continuous"]),
                "phase_max_step_deg": float(clean["audit"]["max_phase_step_deg"]),
                "amplitude_max_step_db": float(clean["audit"]["max_amplitude_step_db"]),
                "status": entry["status"],
                "sha_verified": bool(actual_sha == selected["sha256"]),
            }
        )
    return rows


def record_status(bands, consistency_ok):
    statuses = [row["status"] for row in bands.values()]
    if "FALLA" in statuses or not consistency_ok:
        return "FALLA"
    if "PASA_CON_OBSERVACIONES" in statuses:
        return "PASA_CON_OBSERVACIONES"
    return "PASA"


def sweep_record(SBFReader, read_calibration, record, config, cache):
    source = Path(record["source"]["path_abs"])
    source_sha = comun.sha256_file(source)
    source_ok = source_sha == record["source"]["sha256"]

    bands = {}
    consistency = {}
    calibration = {}

    with SBFReader(str(source)) as acq:
        for band in comun.band_list(config):
            trace_index = int(config["bands"][band]["trace_index"])
            manifest_trace = record["traces"][trace_index]
            live = acq.trace(trace_index)
            consistency[band] = {
                "sample_count_match": int(live.sample_count)
                == int(manifest_trace["sample_count"]),
                "sample_rate_match": abs(
                    float(live.sample_rate_hz) - float(manifest_trace["sample_rate_hz"])
                )
                <= 1e-9,
                "channels_match": list(live.channels) == list(manifest_trace["channels"]),
                "adc_to_uv_match": bool(
                    np.allclose(
                        np.asarray(live.adc_to_uv, dtype=float),
                        np.asarray(manifest_trace["adc_to_uv"], dtype=float),
                        rtol=0.0,
                        atol=1e-12,
                    )
                ),
                "receiver_serial_match": int(live.receiver_serial)
                == int(manifest_trace["receiver_serial"]),
            }
            mask_path = comun.BARRIDO / "mascaras" / (
                "%s_%s.npz" % (record["record_id"], band)
            )
            bands[band] = qc_tiempo.qc_band(acq, config, band, mask_path=mask_path)
            bands[band]["bad_mask"]["relative_path"] = "barrido/mascaras/%s" % (
                mask_path.name
            )
            bands[band]["manifest_trace"] = {
                "index": int(manifest_trace["index"]),
                "section_index": int(manifest_trace["section_index"]),
                "sample_count": int(manifest_trace["sample_count"]),
                "sample_rate_hz": float(manifest_trace["sample_rate_hz"]),
                "duration_seconds": float(manifest_trace["duration_seconds"]),
                "start_time_local": manifest_trace["start_time_local"],
                "adc_to_uv": [float(value) for value in manifest_trace["adc_to_uv"]],
            }

    for band in comun.band_list(config):
        calibration[band] = calibration_rows(
            record, config, band, cache, read_calibration
        )

    consistency_ok = all(
        all(row.values()) for row in consistency.values()
    )
    calibration_ok = all(
        row["covered"] and row["sha_verified"] and row["table_gain"] == 1.0
        for rows in calibration.values()
        for row in rows
    )
    status = record_status(bands, consistency_ok)

    gains = gain_values(record)
    if len(gains) == 1:
        nearest = nearest_gain_label(gains[0])
        nearest_payload = {
            "directory": nearest[1],
            "label": nearest[2],
            "delta_pct": float(100.0 * (nearest[0] - gains[0]) / gains[0]),
        }
    else:
        nearest_payload = {"directory": None, "label": None, "delta_pct": None}

    traits = record["settings"]
    payload = {
        "record_version": "P1-BARRIDO-1.0.0",
        "record_id": record["record_id"],
        "generated_at_utc": comun.utc_now(),
        "split": record["split"],
        "campaign": {
            "year": record["campaign"]["year"],
            "campaign_group": record["campaign"]["campaign_group"],
            "label": record["campaign"]["label"],
        },
        "site": {
            "site_id": record["site"]["site_id"],
            "site_name": record["site"]["site_name"],
            "status": record["site"]["status"],
            "note": "Identidad de sitio sin resolver (B-P0-01/B-P0-02).",
        },
        "source": record["source"],
        "source_sha256_recomputed": source_sha,
        "source_sha256_match": bool(source_ok),
        "consistency": {
            "bands": consistency,
            "all_match": bool(consistency_ok),
        },
        "settings_summary": {
            "gain_values_unique": gains,
            "gain_db": [float(20.0 * np.log10(value)) for value in gains],
            "nearest_gain_directory": nearest_payload,
            "adc_to_uv": [
                float(record["traces"][0]["adc_to_uv"][0]),
                float(record["traces"][1]["adc_to_uv"][0]),
            ],
            "electric_dipole_lengths_cm": [
                float(value) for value in traits["electric_dipole_lengths_cm"]
            ],
            "sensor_azimuth_degrees": [
                float(value) for value in traits["sensor_azimuth_degrees"]
            ],
            "delay_seconds": float(traits["delay_seconds"]),
            "settings_sections": len(traits.get("gains") or []),
        },
        "bands": bands,
        "calibration": calibration,
        "calibration_all_covered": bool(calibration_ok),
        "status": status,
        "blockers": {
            "B-P0-05": {
                "id": "B-P0-05",
                "alcance": "registro %s, bandas D0/D1" % record["record_id"],
                "estado": (
                    "CERRADO_PARA_ESTE_REGISTRO"
                    if status in ("PASA", "PASA_CON_OBSERVACIONES")
                    else "ABIERTO"
                ),
                "evidencia": "barrido/registros/%s.json y mascaras en barrido/mascaras/"
                % record["record_id"],
            }
        },
    }
    return payload


def aggregate(records, config):
    totals = {
        "records": len(records),
        "by_split": {},
        "samples": {"D0": 0, "D1": 0, "total": 0},
        "jumps": {channel: 0 for channel in comun.CHANNELS},
        "bad_samples_by_channel": 0,
        "bad_union_samples": 0,
        "dead_channels": 0,
        "clip_runs": 0,
        "stuck_runs": 0,
        "zero_fill_runs": 0,
        "records_falla": [],
        "records_con_observaciones": [],
        "calibration_uncovered": [],
        "source_hash_mismatch": [],
        "consistency_mismatch": [],
    }
    for payload in records:
        split = payload["split"]["split"]
        totals["by_split"][split] = totals["by_split"].get(split, 0) + 1
        if payload["status"] == "FALLA":
            totals["records_falla"].append(payload["record_id"])
        if payload["status"] == "PASA_CON_OBSERVACIONES":
            totals["records_con_observaciones"].append(payload["record_id"])
        if not payload["source_sha256_match"]:
            totals["source_hash_mismatch"].append(payload["record_id"])
        if not payload["consistency"]["all_match"]:
            totals["consistency_mismatch"].append(payload["record_id"])
        for band in comun.band_list(config):
            block = payload["bands"][band]
            totals["samples"][band] += int(block["n_samples"])
            totals["samples"]["total"] += int(block["n_samples"])
            for channel, row in block["per_channel"].items():
                totals["jumps"][channel] += int(row["jump_count"])
                totals["bad_samples_by_channel"] += int(row["bad_samples"])
                totals["dead_channels"] += int(bool(row["dead_channel"]))
                totals["clip_runs"] += int(row["clip_runs"])
                totals["stuck_runs"] += int(row["stuck_runs"])
                totals["zero_fill_runs"] += int(row["zero_fill_runs"])
            totals["bad_union_samples"] += int(
                block["bad_mask"]["union_bad_samples"]
            )
        for band, rows in payload["calibration"].items():
            for row in rows:
                if not (row["covered"] and row["sha_verified"] and row["table_gain"] == 1.0):
                    totals["calibration_uncovered"].append(
                        {
                            "record_id": payload["record_id"],
                            "band": band,
                            "channel": row["channel"],
                            "covered": row["covered"],
                            "sha_verified": row["sha_verified"],
                        }
                    )
    return totals


def report_markdown(records, totals, config):
    lines = [
        "# Barrido P1 de los 15 registros",
        "",
        "Generado por `etapa1/barrido_registros.py` con la configuracion "
        "`%s`." % config["version"],
        "",
        "El barrido **no reexporta series temporales** y **no modifica P0 ni los "
        "SBF de origen**. Extiende el QC y el cruce de calibracion del registro "
        "objetivo al conjunto completo de P0.",
        "",
        "## Resumen",
        "",
        "| Metrica | Valor |",
        "|---|---:|",
        "| Registros | %d |" % totals["records"],
        "| Desarrollo | %d |" % totals["by_split"].get("desarrollo", 0),
        "| Validacion | %d |" % totals["by_split"].get("validacion", 0),
        "| Prueba | %d |" % totals["by_split"].get("prueba", 0),
        "| Muestras D0 | %d |" % totals["samples"]["D0"],
        "| Muestras D1 | %d |" % totals["samples"]["D1"],
        "| Muestras totales | %d |" % totals["samples"]["total"],
        "| Muestras en mascara (union) | %d |" % totals["bad_union_samples"],
        "| Muestras en mascara (suma por canal) | %d |"
        % totals["bad_samples_by_channel"],
        "| Canales muertos | %d |" % totals["dead_channels"],
        "| Tramos de clipping | %d |" % totals["clip_runs"],
        "| Tramos pegados | %d |" % totals["stuck_runs"],
        "| Tramos de ceros | %d |" % totals["zero_fill_runs"],
        "| Registros en FALLA | %d |" % len(totals["records_falla"]),
        "| Registros con observaciones | %d |"
        % len(totals["records_con_observaciones"]),
        "| Cobertura de calibracion incompleta | %d |"
        % len(totals["calibration_uncovered"]),
        "| Hashes de origen distintos | %d |" % len(totals["source_hash_mismatch"]),
        "",
        "Saltos por canal (todos los registros, D0+D1): "
        + ", ".join(
            "%s = %d" % (channel, totals["jumps"][channel])
            for channel in comun.CHANNELS
        )
        + ".",
        "",
    ]

    groups = {}
    for payload in records:
        for gain in payload["settings_summary"]["gain_values_unique"]:
            groups.setdefault(gain, []).append(payload["record_id"])
    lines.extend(
        [
            "Grupos de ganancia de registro: "
            + "; ".join(
                "%.6g (%d registro%s: %s)"
                % (gain, len(ids), "" if len(ids) == 1 else "s", ", ".join(sorted(ids)))
                for gain, ids in sorted(groups.items())
            )
            + ". La calibracion cruzada usa el directorio mas proximo a cada ganancia.",
            "",
            "## Registros",
        ]
    )
    lines.extend(
        [
            "",
            "| Registro | Split | D0 (s) | D1 (s) | QC D0 | QC D1 | Saltos E | Saltos H "
            "| Mala (muestras) | Calibracion | Estado |",
            "|---|---|---:|---:|---|---|---:|---:|---:|---|---|",
        ]
    )
    for payload in records:
        d0 = payload["bands"]["D0"]
        d1 = payload["bands"]["D1"]
        jumps_e = sum(
            d0["per_channel"][channel]["jump_count"]
            + d1["per_channel"][channel]["jump_count"]
            for channel in ("Ex", "Ey")
        )
        jumps_h = sum(
            d0["per_channel"][channel]["jump_count"]
            + d1["per_channel"][channel]["jump_count"]
            for channel in ("Hx", "Hy", "Hz")
        )
        bad = int(d0["bad_mask"]["union_bad_samples"]) + int(
            d1["bad_mask"]["union_bad_samples"]
        )
        lines.append(
            "| %s | %s | %.0f | %.0f | %s | %s | %d | %d | %d | %s | %s |"
            % (
                payload["record_id"],
                payload["split"]["split"],
                d0["duration_s"],
                d1["duration_s"],
                d0["status"],
                d1["status"],
                jumps_e,
                jumps_h,
                bad,
                "cubierta" if payload["calibration_all_covered"] else "incompleta",
                payload["status"],
            )
        )
    lines.extend(
        [
            "",
            "## Limites",
            "",
            "- El QC es el mismo que P1: clipping, canales muertos, valores pegados, "
            "relleno de ceros, saltos y huecos. Los saltos se reportan y **no se "
            "enmascaran**.",
            "- La calibracion sigue siendo **candidata no verificada**: no hay fecha, "
            "certificado ni seccion de ganancia (B-P0-04).",
            "- La cobertura de calibracion solo indica soporte de frecuencia, no "
            "validez metrologica.",
            "- La identidad de sitio, las coordenadas, el vinculo TEM-ARMT y la zona "
            "horaria siguen sin resolver (B-P0-01, B-P0-02, B-P0-03, B-P0-07).",
            "- Este barrido no habilita P2-T ni la sintesis guiada por TEM.",
            "",
        ]
    )
    return "\n".join(lines)


def prepare(config):
    p0_hashes = comun.verify_p0_hashes()
    if not all(row["unchanged"] for row in p0_hashes):
        raise RuntimeError("P0 cambio; el barrido P1 exige el contrato congelado")

    manifest = comun.load_p0_manifest()
    records = comun.iter_records(manifest)
    if len(records) != 15:
        raise RuntimeError("se esperaban 15 registros en P0, hay %d" % len(records))

    for name in ("manifest.json", "splits.csv"):
        if "SYN-" in (comun.ETAPA0 / name).read_text(encoding="utf-8"):
            raise RuntimeError("hay identificadores SYN- en P0")
    return p0_hashes, records


def build(config=None):
    config = config or comun.load_config_barrido()
    started = time.time()
    p0_hashes, records = prepare(config)

    SBFReader, read_calibration = comun.import_armt()
    cache = {}

    per_record = []
    timings = []
    for record in records:
        step_start = time.time()
        payload = sweep_record(
            SBFReader, read_calibration, record, config, cache
        )
        path = comun.BARRIDO / "registros" / ("%s.json" % record["record_id"])
        comun.dump_json(path, payload)
        seconds = round(time.time() - step_start, 3)
        timings.append({"record_id": record["record_id"], "seconds": seconds})
        per_record.append(payload)
        print(
            "  %-22s %-11s %-24s %7.1f s"
            % (payload["record_id"], payload["split"]["split"], payload["status"], seconds)
        )

    return write_outputs(
        per_record, records, config, timings, started, p0_hashes, elapsed=None
    )


def write_outputs(
    per_record, records, config, timings, started, p0_hashes, elapsed=None, mode="completo"
):
    totals = aggregate(per_record, config)

    qc_rows = []
    cal_rows = []
    gain_rows = []
    by_id = {record["record_id"]: record for record in records}
    for payload in per_record:
        settings = payload["settings_summary"]
        gain_rows.append(
            {
                "record_id": payload["record_id"],
                "split": payload["split"]["split"],
                "campaign_group": payload["campaign"]["campaign_group"],
                "gain_unique": ";".join("%.9g" % value for value in settings["gain_values_unique"]),
                "gain_db": ";".join("%.6f" % value for value in settings["gain_db"]),
                "nearest_directory": settings["nearest_gain_directory"]["directory"] or "mixta",
                "nearest_label": settings["nearest_gain_directory"]["label"] or "n/a",
                "delta_pct": (
                    "%.6f" % settings["nearest_gain_directory"]["delta_pct"]
                    if settings["nearest_gain_directory"]["delta_pct"] is not None
                    else "n/a"
                ),
                "adc_to_uv_d0": "%.9g" % settings["adc_to_uv"][0],
                "adc_to_uv_d1": "%.9g" % settings["adc_to_uv"][1],
                "dipole_ex_cm": "%.1f" % settings["electric_dipole_lengths_cm"][0],
                "dipole_ey_cm": "%.1f" % settings["electric_dipole_lengths_cm"][1],
                "azimuth_deg": ";".join(
                    "%.1f" % value for value in settings["sensor_azimuth_degrees"]
                ),
                "delay_s": "%.6g" % settings["delay_seconds"],
                "start_time_d0": payload["bands"]["D0"]["manifest_trace"]["start_time_local"],
                "start_time_d1": payload["bands"]["D1"]["manifest_trace"]["start_time_local"],
                "settings_sections": settings["settings_sections"],
                "bands_present": ";".join(
                    sorted(
                        {
                            trace["band"]
                            for trace in by_id[payload["record_id"]]["traces"]
                            if trace["in_scope"]
                        }
                    )
                ),
            }
        )
        for band in comun.band_list(config):
            block = payload["bands"][band]
            for channel, row in block["per_channel"].items():
                qc_rows.append(
                    {
                        "record_id": payload["record_id"],
                        "split": payload["split"]["split"],
                        "band": band,
                        "channel": channel,
                        "n_samples": block["n_samples"],
                        "sample_rate_hz": "%.6f" % block["sample_rate_hz"],
                        "duration_s": "%.6f" % block["duration_s"],
                        "minimum_counts": row["minimum_counts"],
                        "maximum_counts": row["maximum_counts"],
                        "mean_counts": "%.9g" % row["mean_counts"],
                        "std_counts": "%.9g" % row["std_counts"],
                        "zero_count": row["zero_count"],
                        "clip_runs": row["clip_runs"],
                        "stuck_runs": row["stuck_runs"],
                        "zero_fill_runs": row["zero_fill_runs"],
                        "jump_count": row["jump_count"],
                        "dead_channel": "si" if row["dead_channel"] else "no",
                        "bad_samples": row["bad_samples"],
                        "bad_fraction": "%.10g" % row["bad_fraction"],
                        "band_status": block["status"],
                    }
                )
            for row in payload["calibration"][band]:
                cal_rows.append(
                    {
                        key: (
                            "si"
                            if value is True
                            else "no"
                            if value is False
                            else value
                        )
                        for key, value in row.items()
                    }
                )

    write_csv(comun.BARRIDO / "qc_registros.csv", QC_FIELDS, qc_rows)
    write_csv(comun.BARRIDO / "calibracion_cobertura.csv", CAL_FIELDS, cal_rows)
    write_csv(comun.BARRIDO / "ganancias_registros.csv", GAIN_FIELDS, gain_rows)

    summary = {
        "barrido_version": "P1-BARRIDO-1.0.0",
        "generated_at_utc": comun.utc_now(),
        "stage": 1,
        "build_mode": mode,
        "build_note": (
            "QC calculado en una pasada completa; CSV, resumen y reporte "
            "regenerados desde barrido/registros/*.json sin releer los SBF"
            if mode != "completo"
            else "QC calculado y entregables escritos en la misma pasada"
        ),
        "config_version": config["version"],
        "scope": config["scope"],
        "p0_hashes": p0_hashes,
        "totals": totals,
        "timings": timings,
        "total_seconds": round(
            (elapsed if elapsed is not None else time.time() - started), 3
        ),
        "outputs": {
            "registros": "barrido/registros/*.json",
            "mascaras": "barrido/mascaras/*.npz",
            "qc_csv": "barrido/qc_registros.csv",
            "calibracion_csv": "barrido/calibracion_cobertura.csv",
            "ganancias_csv": "barrido/ganancias_registros.csv",
            "reporte": "barrido/reporte_barrido.md",
        },
        "p1_status": "PARCIAL",
        "p1_status_reasons": [
            "La validez metrologica de las 73 .clb sigue sin resolver (B-P0-04)",
            "La ganancia no se aplica: no se puede decidir si la tabla ya la incluye",
            "La unidad magnetica V/(A/m) frente a mV/nT sigue sin resolver",
            "No hay exportacion independiente del fabricante",
            "El vinculo TEM-ARMT no esta verificado (B-P0-03); P2-T sigue bloqueado",
        ],
        "blockers_open": [
            "B-P0-01",
            "B-P0-02",
            "B-P0-03",
            "B-P0-04",
            "B-P0-06",
            "B-P0-07",
        ],
    }
    comun.dump_json(comun.BARRIDO / "resumen_global.json", summary)
    (comun.BARRIDO / "reporte_barrido.md").write_text(
        report_markdown(per_record, totals, config), encoding="utf-8"
    )

    return {
        "summary": str(comun.BARRIDO / "resumen_global.json"),
        "report": str(comun.BARRIDO / "reporte_barrido.md"),
        "records": len(per_record),
        "totals": totals,
        "seconds": summary["total_seconds"],
    }


def rebuild(config=None):
    """Regenera CSV, resumen y reporte desde los JSON por registro."""
    config = config or comun.load_config_barrido()
    p0_hashes, records = prepare(config)
    summary_path = comun.BARRIDO / "resumen_global.json"
    previous = comun.load_json(summary_path) if summary_path.is_file() else {}
    previous_seconds = {
        row["record_id"]: float(row.get("seconds", 0.0))
        for row in previous.get("timings", [])
    }
    per_record = []
    timings = []
    for record in records:
        path = comun.BARRIDO / "registros" / ("%s.json" % record["record_id"])
        if not path.is_file():
            raise FileNotFoundError("falta %s; ejecutar el barrido completo" % path)
        per_record.append(comun.load_json(path))
        timings.append(
            {
                "record_id": record["record_id"],
                "seconds": previous_seconds.get(record["record_id"], 0.0),
            }
        )
    return write_outputs(
        per_record,
        records,
        config,
        timings,
        time.time(),
        p0_hashes,
        elapsed=float(previous.get("total_seconds", 0.0)),
        mode="resumen_sin_relectura",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--resumir",
        action="store_true",
        help="regenera CSV, resumen y reporte desde barrido/registros/*.json",
    )
    args = parser.parse_args()
    config = comun.load_config_barrido(args.config)
    result = rebuild(config) if args.resumir else build(config)
    print("barrido P1: %d registros, %.1f s" % (result["records"], result["seconds"]))
    print("resumen: %s" % result["summary"])
    print("reporte: %s" % result["report"])


if __name__ == "__main__":
    main()
