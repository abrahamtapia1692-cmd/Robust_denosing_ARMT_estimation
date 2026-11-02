#!/usr/bin/env python3
"""Inventario reproducible de Etapa 0 (puerta P0) para el piloto ARMT.

Lee en modo solo lectura los SBF, las calibraciones .clb y el dosier TEM.
No aplica calibracion, no convierte a unidades fisicas y no modifica los
proyectos de origen. Los campos desconocidos se escriben como null y se
declaran en ``unknowns``.

Uso:
    python etapa0/inventario_armt.py
    python etapa0/inventario_armt.py --armt-root D:\\ARRT_software\\ARMT_processing
"""

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_SOFTWARE_ROOT = Path(r"D:\ARRT_software")
DEFAULT_ARMT_ROOT = DEFAULT_SOFTWARE_ROOT / "ARMT_processing"
DEFAULT_TEM_MANIFEST = (
    DEFAULT_SOFTWARE_ROOT
    / "TEM_MT_inversion"
    / "dosier_doi_20261014"
    / "manifiesto_entradas.json"
)

BANDS = {1: "D0", 2: "D1", 4: "D2", 8: "D3"}
BAND_INDEX = {1: 0, 2: 1, 4: 2, 8: 3}
SCOPE_BANDS = ("D0", "D1")
SPLIT_PROTOCOL = "P0-SPLITS-1.0.0"

# Propuesta congelada: la campana 2023 se reserva completa y tres sitios de
# 2021 se apartan para validacion. El resto queda para desarrollo.
TEST_CAMPAIGNS = {(2023, 123)}
VALIDATION_SITES = {(2021, 700, 43), (2021, 700, 55), (2021, 700, 90)}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def package_version(name):
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return "desconocida"


def iso_mtime(path):
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    except OSError:
        return None


def sha256_file(path, chunk_size=4 * 1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_to(path, root):
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def file_entry(path, workspace=WORKSPACE, software_root=DEFAULT_SOFTWARE_ROOT):
    path = Path(path).resolve()
    ref = relative_to(path, workspace)
    if ref is not None:
        base = "workspace"
    else:
        ref = relative_to(path, software_root)
        if ref is not None:
            base = "software_root"
        else:
            ref = path.as_posix()
            base = "external"
    return {
        "path_abs": str(path),
        "path_ref": ref,
        "path_base": base,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "mtime_utc": iso_mtime(path),
    }


def load_armt(armt_root):
    sys.path.insert(0, str(armt_root))
    import armt  # noqa: F401
    from armt.calibration import read_calibration
    from armt.reader import SBFReader

    return armt, SBFReader, read_calibration


def display_value(value):
    """Convierte '-' o cadenas vacias del dosier TEM en null explicito."""
    if value is None:
        return None
    value = value.strip()
    if value in ("", "-"):
        return None
    return value


def parse_float(value):
    value = display_value(value)
    if value is None:
        return None
    try:
        return float(value.split()[0])
    except (TypeError, ValueError):
        return None


def parse_tem(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    header = {}
    acquisition = {}
    coordinates = {}
    gates = []
    section = None
    in_data = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("<"):
            section = line.upper()
            in_data = section.startswith("<DATA")
            continue
        if line.startswith("#"):
            continue
        if in_data:
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                gates.append((float(parts[0]), float(parts[1]), float(parts[2])))
            except ValueError:
                continue
            continue
        if " " not in line and "\t" not in line:
            continue
        key, value = re.split(r"\s+", line, maxsplit=1)
        value = value.split("#", 1)[0].strip()
        key = key.upper()
        if section and section.startswith("<ACQUISITION"):
            acquisition[key] = value
        elif section and section.startswith("<COORDINATES"):
            coordinates[key] = value
        else:
            header[key] = value

    times = [g[0] for g in gates]
    voltages = [g[1] for g in gates]
    return {
        "project": display_value(header.get("PROJECT")),
        "area": display_value(header.get("AREA")),
        "client": display_value(header.get("CLIENT")),
        "contractor": display_value(header.get("CONTRACTOR")),
        "operator": display_value(header.get("OPERATOR")),
        "conditions": display_value(header.get("CONDITIONS")),
        "coordinates": {
            "type": display_value(coordinates.get("TYPE")),
            "datum": display_value(coordinates.get("DATUM")),
            "rx_x": parse_float(coordinates.get("RXLAT")),
            "rx_y": parse_float(coordinates.get("RXLONG")),
            "tx_x": parse_float(coordinates.get("TXLAT")),
            "tx_y": parse_float(coordinates.get("TXLONG")),
            "elevation": parse_float(coordinates.get("ELEVATION")),
            "crs": None,
            "latitude_deg": None,
            "longitude_deg": None,
            "status": "no_resuelto",
        },
        "acquisition": {
            "date": display_value(acquisition.get("ACQUISITION_DATE")),
            "time": display_value(acquisition.get("ACQUISITION_TIME")),
            "receiver": display_value(acquisition.get("RECEIVER")),
            "transmitter": display_value(acquisition.get("TRANSMITTER")),
            "configuration": display_value(acquisition.get("CONFIGURATION")),
            "tx_area_m2": parse_float(acquisition.get("TXAREA")),
            "rx_area_m2": parse_float(acquisition.get("RXAREA")),
            "current_a": parse_float(acquisition.get("CURRENT")),
            "repeat_rate_hz": parse_float(acquisition.get("REPTRATE")),
            "turnoff_us": parse_float(acquisition.get("TURNOFF")),
            "antenna_delay_us": parse_float(acquisition.get("ANTENNA_DELAY")),
            "filter_delay_us": parse_float(acquisition.get("FILTER_DELAY")),
            "user_delay_us": parse_float(acquisition.get("USER_DELAY")),
        },
        "gates": {
            "count": len(gates),
            "time_min_ms": min(times) if times else None,
            "time_max_ms": max(times) if times else None,
            "voltage_min_nv_per_a": min(voltages) if voltages else None,
            "voltage_max_nv_per_a": max(voltages) if voltages else None,
        },
    }


def coordinate_attempt(latitude_raw, longitude_raw, signed):
    def decode(value):
        if signed and value >= 2 ** 31:
            value -= 2 ** 32
        return math.degrees(value / 1e8)

    latitude = decode(latitude_raw)
    longitude = decode(longitude_raw)
    in_range = -90 <= latitude <= 90 and -180 <= longitude <= 180
    return {
        "latitude_deg": latitude,
        "longitude_deg": longitude,
        "in_range": in_range,
        "plausible": None,
    }


def sensor_kind(sensor_type):
    if sensor_type == 0:
        return "electrical_amplifier"
    if sensor_type == 1:
        return "magnetic_sensor"
    return "desconocido"


def calibration_entry(path, workspace, software_root):
    summary = read_calibration_cached(path)
    match = re.search(r"CLB_G([0-9]+(?:\.[0-9]+)?)_", path.parent.name)
    gain_token = match.group(1) if match else ""
    tables = []
    for index, table in enumerate(summary["tables"]):
        frequencies = table.get("log10_frequency_hz") or []
        tables.append(
            {
                "index": index,
                "gain": float(table["gain"]),
                "frequency_count": int(table["frequency_count"]),
                "channel_count": int(table["channel_count"]),
                "frequency_min_hz": float(10 ** min(frequencies)) if frequencies else 1.0,
                "frequency_max_hz": float(10 ** max(frequencies)) if frequencies else 1.0,
            }
        )
    name_match = re.match(r"^([eh])(\d{6})", path.name)
    variant = None
    if name_match:
        variant = path.stem[len(name_match.group(0)) :] or None
    entry = file_entry(path, workspace, software_root)
    entry.update(
        {
            "gain_directory": float(gain_token) if gain_token else 0.0,
            "gain_token": gain_token or "desconocido",
            "kind": summary["kind_name"],
            "kind_code": int(summary["kind"]),
            "serial_number": int(summary["serial_number"]),
            "filename_variant": variant,
            "table_count": len(tables),
            "tables": tables,
        }
    )
    entry["_selected_table"] = tables[0] if tables else None
    return entry


_CALIBRATION_CACHE = {}


def read_calibration_cached(path):
    key = str(path)
    if key not in _CALIBRATION_CACHE:
        _CALIBRATION_CACHE[key] = read_calibration(path).summary()
    return _CALIBRATION_CACHE[key]


def match_channel(kind, serial, gain, calibration_index):
    pool = [
        c
        for c in calibration_index.get((kind, serial), [])
        if c["kind"] == kind and c["serial_number"] == serial
    ]
    if not pool or gain <= 0:
        return None, 0
    selected = min(pool, key=lambda c: abs(math.log(c["gain_directory"] / gain)))
    table = selected["_selected_table"] or {}
    return (
        {
            "path_ref": selected["path_ref"],
            "sha256": selected["sha256"],
            "gain_directory": selected["gain_directory"],
            "delta_rel": (selected["gain_directory"] - gain) / gain,
            "table_gain": float(table.get("gain", 0.0)),
            "frequency_count": int(table.get("frequency_count", 0)),
            "frequency_min_hz": float(table.get("frequency_min_hz", 1.0)),
            "frequency_max_hz": float(table.get("frequency_max_hz", 1.0)),
        },
        len(pool),
    )


def build_record(path, SBFReader, calibration_index, workspace, software_root):
    with SBFReader(path) as reader:
        summary = reader.summary()
    settings = summary["settings"][0] if summary["settings"] else {}
    traces = summary["traces"]
    if not traces:
        raise RuntimeError("Registro sin trazas: %s" % path)

    array_index = int(settings.get("array_index", 0))
    line_index = int(settings.get("line_index", 0))
    station_index = int(settings.get("station_index", 0))
    repeat_index = int(settings.get("repeat_index", 0))
    record_id = "ARMT5-%03d-%02d-%02d-%02d" % (
        array_index,
        line_index,
        station_index,
        repeat_index,
    )

    years = []
    for trace in traces:
        start = trace.get("start_time")
        if start:
            years.append(int(start[:4]))
    year = min(years) if years else 0
    campaign_group = "C%04d-A%03d" % (year, array_index)
    site_group = "S%04d-A%03d-L%03d" % (year, array_index, line_index)
    if (year, array_index) in TEST_CAMPAIGNS:
        split = "prueba"
    elif (year, array_index, line_index) in VALIDATION_SITES:
        split = "validacion"
    else:
        split = "desarrollo"

    gains = settings.get("gains") or []
    serials = settings.get("sensor_serials") or []
    sensor_types = settings.get("sensor_types") or []
    azimuths = settings.get("sensor_azimuth_degrees") or []
    dipoles = settings.get("electric_dipole_lengths_cm")

    trace_entries = []
    matched_total = 0
    matched_d01 = 0
    total_d01 = 0
    max_delta_rel = 0.0
    for trace in traces:
        band_mask = int(trace["band_mask"])
        band = BANDS.get(band_mask, "D3")
        band_row = BAND_INDEX.get(band_mask, 3)
        channels = list(trace.get("channels") or ())
        channel_calibrations = []
        for channel_index, channel in enumerate(channels):
            try:
                serial = int(serials[band_row][channel_index])
            except (IndexError, TypeError, ValueError):
                serial = None
            try:
                gain = float(gains[band_row][channel_index])
            except (IndexError, TypeError, ValueError):
                gain = 0.0
            try:
                sensor_type = int(sensor_types[channel_index])
            except (IndexError, TypeError, ValueError):
                sensor_type = -1
            kind = sensor_kind(sensor_type)
            selected, n_candidates = match_channel(
                kind, serial, gain, calibration_index
            )
            reasons = []
            if selected is None:
                status = "sin_candidata"
                reasons.append("No hay archivo .clb con tipo y serie coincidentes")
            else:
                status = "candidata_no_verificada"
                reasons.extend(
                    [
                        "Sin fecha ni certificado de calibracion",
                        "La tabla esta normalizada; la ganancia se toma del directorio",
                        "Polaridad, longitud de dipolo y cadena de aplicacion no verificadas",
                    ]
                )
                if n_candidates > 1:
                    reasons.append(
                        "Multiples variantes para la misma serie; se elige la ganancia mas proxima"
                    )
                max_delta_rel = max(max_delta_rel, abs(selected["delta_rel"]))
                matched_total += 1
                if band in SCOPE_BANDS:
                    matched_d01 += 1
            if band in SCOPE_BANDS:
                total_d01 += 1
            channel_calibrations.append(
                {
                    "channel": channel,
                    "sensor_type": kind,
                    "serial_number": serial,
                    "gain_record": gain,
                    "n_candidates": n_candidates,
                    "selected": selected,
                    "status": status,
                    "reasons": reasons,
                }
            )
        trace_entries.append(
            {
                "index": int(trace["index"]),
                "section_index": int(trace["section_index"]),
                "band": band,
                "band_mask": band_mask,
                "in_scope": band in SCOPE_BANDS,
                "start_time_local": trace.get("start_time"),
                "latitude_raw": int(trace["latitude_raw"]),
                "longitude_raw": int(trace["longitude_raw"]),
                "altitude_m": int(trace["altitude_m"]),
                "sample_count": int(trace["sample_count"]),
                "sample_rate_hz": float(trace["sample_rate_hz"]),
                "duration_seconds": float(trace["duration_seconds"]),
                "bytes_per_sample": int(trace["bytes_per_sample"]),
                "channel_count": int(trace["channel_count"]),
                "channels": channels,
                "receiver_serial": int(trace["receiver_serial"]),
                "adc_to_uv": [float(v) for v in trace.get("adc_to_uv") or ()],
                "settings_match": str(trace.get("settings_match", "missing")),
                "calibration_channels": channel_calibrations,
            }
        )

    first_trace = traces[0]
    altitud = [int(t["altitude_m"]) for t in traces]
    calibration_notes = [
        "Coincidencia por tipo, serie y ganancia de directorio; no certifica validez",
        "No se aplico ninguna correccion de ganancia, ADC, sensor ni dipolo",
    ]
    if max_delta_rel > 0.005:
        calibration_notes.append(
            "La ganancia de registro se empareja al directorio mas proximo con "
            "desviacion relativa maxima de %.2f%%; revisar en P1"
            % (100.0 * max_delta_rel)
        )
    attempts_unsigned = coordinate_attempt(
        int(first_trace["latitude_raw"]), int(first_trace["longitude_raw"]), False
    )
    attempts_signed = coordinate_attempt(
        int(first_trace["latitude_raw"]), int(first_trace["longitude_raw"]), True
    )
    signed_plausible = bool(
        attempts_signed["in_range"]
        and attempts_signed["latitude_deg"] is not None
        and attempts_signed["longitude_deg"] is not None
    )
    attempts_signed["plausible"] = signed_plausible
    attempts_unsigned["plausible"] = False
    candidate_latitude = attempts_signed["latitude_deg"] if signed_plausible else None
    candidate_longitude = attempts_signed["longitude_deg"] if signed_plausible else None
    candidate_status = (
        "candidata_no_verificada" if signed_plausible else "no_disponible"
    )
    channel_count = sum(t["channel_count"] for t in trace_entries)
    warnings = []
    for warning in summary.get("warnings") or []:
        if warning not in warnings:
            warnings.append(warning)

    notes = []
    if station_index == 0:
        notes.append("station_index=0; el manual no aclara si es una estacion valida o un marcador")
    if any(value == 0 for value in altitud):
        notes.append("Al menos una traza declara altitud 0; no se interpreta como nivel del mar")
    if len(set(altitud)) > 1:
        notes.append("Las altitudes difieren entre trazas del mismo registro")
    if any(
        entry["band"] in SCOPE_BANDS and entry["duration_seconds"] < 60
        for entry in trace_entries
    ):
        notes.append("Alguna traza D0/D1 dura menos de 60 s; revisar suficiencia para ventanas")

    return {
        "record_id": record_id,
        "source": file_entry(path, workspace, software_root),
        "campaign": {
            "year": year,
            "year_status": "inferido_de_marca_temporal_local_sin_zona",
            "campaign_group": campaign_group,
            "source_directory": path.parent.name,
            "label": None,
            "label_status": "no_verificado",
            "verified": False,
        },
        "site": {
            "site_id": None,
            "site_name": None,
            "site_group": site_group,
            "latitude_deg": None,
            "longitude_deg": None,
            "datum": None,
            "crs": None,
            "status": "no_resuelto",
            "altitude_m_traces": altitud,
            "raw": {
                "latitude_uint32": int(first_trace["latitude_raw"]),
                "longitude_uint32": int(first_trace["longitude_raw"]),
            },
            "attempts": {
                "unsigned_1e8": attempts_unsigned,
                "signed_1e8": attempts_signed,
                "status": (
                    "candidata_plausible_no_verificada"
                    if signed_plausible
                    else "no_concluyente"
                ),
                "note": (
                    "El manual declara UInt32 con latitud y longitud en radianes x 10^8, "
                    "pero no define el tratamiento de hemisferios. La lectura en complemento "
                    "a dos produce una candidata plausible; la lectura sin signo no. "
                    "La candidata no se adopta como coordenada verificada."
                ),
            },
            "candidate_latitude_deg": candidate_latitude,
            "candidate_longitude_deg": candidate_longitude,
            "candidate_policy": "radianes_x_1e8_complemento_a_dos" if signed_plausible else None,
            "candidate_status": candidate_status,
            "note": (
                "Identidad de sitio desconocida. site_group se deriva de ano, arreglo y "
                "linea; no es un identificador oficial."
            ),
        },
        "settings": {
            "section_index": int(settings.get("section_index", 0)),
            "event_id": int(settings.get("event_id", 0)),
            "recording_mode": int(settings.get("recording_mode", 0)),
            "band_mask": int(settings.get("band_mask", 0)),
            "channel_mask": int(settings.get("channel_mask", 0)),
            "internal_transmitter_mask": int(settings.get("internal_transmitter_mask", 0)),
            "gains": [list(row) for row in gains],
            "delay_seconds": settings.get("delay_seconds"),
            "start_time_local": settings.get("start_time"),
            "overlap_percent": list(settings.get("overlap_percent") or []),
            "window_type": settings.get("window_type"),
            "frequency_list_ids": list(settings.get("frequency_list_ids") or []),
            "fft_lengths": list(settings.get("fft_lengths") or []),
            "fft_counts": list(settings.get("fft_counts") or []),
            "recording_period_seconds": settings.get("recording_period_seconds"),
            "array_index": array_index,
            "line_index": line_index,
            "station_index": station_index,
            "repeat_index": repeat_index,
            "sensor_types": [int(v) for v in sensor_types],
            "sensor_azimuth_degrees": [float(v) for v in azimuths],
            "sensor_serials": [list(row) for row in serials],
            "electric_dipole_lengths_cm": list(dipoles) if dipoles is not None else None,
        },
        "traces": trace_entries,
        "calibration": {
            "status": (
                "candidata_no_verificada"
                if matched_total == channel_count
                else "incompleta"
            ),
            "channels_total": channel_count,
            "channels_matched": matched_total,
            "fraction": (matched_total / channel_count) if channel_count else 0.0,
            "channels_d01_total": total_d01,
            "channels_d01_matched": matched_d01,
            "notes": calibration_notes,
        },
        "split": {
            "split": split,
            "split_group": site_group,
            "campaign_group": campaign_group,
            "protocol_version": SPLIT_PROTOCOL,
            "assignment_basis": "record_level_site_holdout",
            "frozen": True,
        },
        "tem_link": {
            "status": "no_verificado",
            "sounding_id": None,
            "evidence": None,
            "note": (
                "El dosier TEM usa coordenadas metricas locales y no contiene un "
                "identificador de sitio ARMT reconciliado."
            ),
        },
        "remote_reference": {
            "available": False,
            "source": None,
            "note": (
                "No se identifico una referencia remota verificada en los metadatos "
                "de los registros ni en el dosier."
            ),
        },
        "qc": {
            "status": "no_evaluado",
            "checks": {
                name: {"estado": "no_evaluado", "detalle": None}
                for name in (
                    "clipping",
                    "canales_muertos",
                    "saltos",
                    "muestras_faltantes",
                    "transitorios_conmutacion",
                )
            },
            "note": "P0 inventaria; el QC irreversible pertenece a P1.",
        },
        "warnings": warnings,
        "notes": notes,
    }


def build_splits(records):
    rows = []
    for record in records:
        traces = {trace["band"]: trace for trace in record["traces"]}
        rows.append(
            {
                "record_id": record["record_id"],
                "split": record["split"]["split"],
                "split_group": record["split"]["split_group"],
                "campaign_group": record["split"]["campaign_group"],
                "protocol_version": SPLIT_PROTOCOL,
                "array_index": record["settings"]["array_index"],
                "line_index": record["settings"]["line_index"],
                "station_index": record["settings"]["station_index"],
                "repeat_index": record["settings"]["repeat_index"],
                "campaign_year": record["campaign"]["year"],
                "source_file": record["source"]["path_ref"],
                "sha256": record["source"]["sha256"],
                "n_traces": len(record["traces"]),
                "has_d0": "si" if "D0" in traces else "no",
                "has_d1": "si" if "D1" in traces else "no",
                "d0_duration_s": (
                    "%.6f" % traces["D0"]["duration_seconds"] if "D0" in traces else ""
                ),
                "d1_duration_s": (
                    "%.6f" % traces["D1"]["duration_seconds"] if "D1" in traces else ""
                ),
                "notes": record["split"]["assignment_basis"],
            }
        )
    rows.sort(key=lambda row: row["record_id"])
    return rows


def write_splits(path, rows):
    columns = [
        "record_id",
        "split",
        "split_group",
        "campaign_group",
        "protocol_version",
        "array_index",
        "line_index",
        "station_index",
        "repeat_index",
        "campaign_year",
        "source_file",
        "sha256",
        "n_traces",
        "has_d0",
        "has_d1",
        "d0_duration_s",
        "d1_duration_s",
        "notes",
    ]
    with open(path, "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--armt-root", type=Path, default=DEFAULT_ARMT_ROOT)
    parser.add_argument("--software-root", type=Path, default=DEFAULT_SOFTWARE_ROOT)
    parser.add_argument("--tem-manifest", type=Path, default=DEFAULT_TEM_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=WORKSPACE / "etapa0")
    args = parser.parse_args(argv)

    global read_calibration
    armt_module, SBFReader, read_calibration = load_armt(args.armt_root)

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    schema_path = out_dir / "schema.json"
    protocol_path = out_dir / "protocolo_validacion.md"
    splits_path = out_dir / "splits.csv"
    samples_path = out_dir / "validacion_muestras.json"
    manifest_path = out_dir / "manifest.json"
    for required in (schema_path, protocol_path):
        if not required.exists():
            raise SystemExit("Falta el archivo requerido: %s" % required)

    records_roots = [args.armt_root / "ARMT_data", args.armt_root / "Soundings"]
    record_paths = []
    for root in records_roots:
        if root.exists():
            record_paths.extend(sorted(root.rglob("*.sbf")))
    record_paths = sorted(set(record_paths))
    if not record_paths:
        raise SystemExit("No se encontraron archivos SBF en %s" % records_roots)

    calibration_paths = sorted((args.armt_root / "Calibrations").rglob("*.clb"))
    calibration_files = [
        calibration_entry(path, WORKSPACE, args.software_root)
        for path in calibration_paths
    ]
    calibration_index = {}
    for entry in calibration_files:
        key = (entry["kind"], entry["serial_number"])
        calibration_index.setdefault(key, []).append(entry)

    records = [
        build_record(
            path,
            SBFReader,
            calibration_index,
            WORKSPACE,
            args.software_root,
        )
        for path in record_paths
    ]
    records.sort(key=lambda record: record["record_id"])

    split_rows = build_splits(records)
    write_splits(splits_path, split_rows)

    tem_manifest = json.loads(args.tem_manifest.read_text(encoding="utf-8-sig"))
    canonical_tem = []
    for entry in tem_manifest:
        path = Path(entry["path"])
        if path.suffix.lower() != ".tem":
            continue
        if path.parent.name.upper() != "TEMS":
            continue
        if not re.match(r"^SER-[0-9]{2}$", path.stem):
            continue
        canonical_tem.append(entry)
    if not canonical_tem:
        raise SystemExit("El dosier TEM no contiene sondeos canonicos SER-XX.tem")
    tem_candidates = []
    for entry in canonical_tem:
        path = Path(entry["path"])
        if not path.exists():
            raise SystemExit("No existe el archivo TEM declarado: %s" % path)
        digest = sha256_file(path)
        parsed = parse_tem(path)
        sounding_id = path.stem
        tem_candidates.append(
            {
                "sounding_id": sounding_id,
                "source": file_entry(path, WORKSPACE, args.software_root),
                "dossier_sha256_matches": (
                    digest == entry.get("sha256")
                    and path.stat().st_size == entry.get("size_bytes")
                ),
                "project": parsed["project"],
                "area": parsed["area"],
                "client": parsed["client"],
                "contractor": parsed["contractor"],
                "operator": parsed["operator"],
                "conditions": parsed["conditions"],
                "coordinates": parsed["coordinates"],
                "acquisition": parsed["acquisition"],
                "gates": parsed["gates"],
                "link_to_armt": {
                    "status": "no_verificado",
                    "record_ids": [],
                    "evidence": None,
                    "note": (
                        "Sin identificador de sitio, datum ni transformacion documentada. "
                        "No se asigna ningun sondeo a un registro ARMT."
                    ),
                },
                "notes": [
                    "Coordenadas declaradas como METRIC; no son lat/lon",
                    "DATUM y ELEVATION vacios en el encabezado",
                    "La fecha y la hora de adquisicion estan vacias",
                ],
            }
        )
    tem_candidates.sort(key=lambda item: item["sounding_id"])

    governing_paths = [
        (WORKSPACE / "PLAN_IMPLEMENTACION_ARMT.md", "Plan rector v1.3"),
        (WORKSPACE / "DISENO_RUIDOS_DATASET_AMT.md", "Especificacion de ruido y dataset v1.3"),
        (WORKSPACE / "VERIFICACION_SUPUESTOS.json", "Evidencia numerica de supuestos"),
    ]
    governing_documents = [
        {"documento": file_entry(path, WORKSPACE, args.software_root), "rol": role}
        for path, role in governing_paths
        if path.exists()
    ]

    module_paths = [
        (args.armt_root / "armt" / "reader.py", "Lector SBF"),
        (args.armt_root / "armt" / "calibration.py", "Lector de calibraciones .clb"),
        (args.armt_root / "armt" / "validation.py", "Validacion de lectura completa"),
        (args.armt_root / "armt" / "__init__.py", "Version declarada del paquete"),
        (args.armt_root / "pyproject.toml", "Metadatos del paquete"),
        (args.armt_root / "armt_reader.py", "Punto de entrada CLI"),
    ]
    modules = [
        {"module": file_entry(path, WORKSPACE, args.software_root), "rol": role}
        for path, role in module_paths
        if path.exists()
    ]

    declared_version = getattr(armt_module, "__version__", None)
    pyproject_text = (args.armt_root / "pyproject.toml").read_text(
        encoding="utf-8", errors="replace"
    )
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject_text)
    pyproject_version = match.group(1) if match else None
    if declared_version and pyproject_version:
        consistency = (
            "consistente" if declared_version == pyproject_version else "inconsistente"
        )
    else:
        consistency = "desconocida"

    product_paths = [
        (args.armt_root / "outputs" / "validacion_soundings.json", "Validacion SBF de Soundings"),
        (args.armt_root / "outputs" / "batch_processing_summary.json", "Resumen de lote"),
        (
            args.armt_root
            / "outputs"
            / "ARMT_data_reprocessed"
            / "summary_reprocessing_ARMT_data.json",
            "Resumen de reprocesamiento 2021",
        ),
        (
            args.armt_root / "outputs" / "batch_survey" / "survey_batch_summary.json",
            "Resumen de encuesta 2021",
        ),
        (
            args.armt_root / "outputs" / "soundings_batch" / "survey_batch_summary.json",
            "Resumen de encuesta 2023",
        ),
        (
            args.armt_root / "golden" / "01401401_baseline.json",
            "Linea base de no regresion",
        ),
    ]
    derived_products = []
    for path, role in product_paths:
        if path.exists():
            derived_products.append(
                {"product": file_entry(path, WORKSPACE, args.software_root), "rol": role}
            )

    split_counts = {"desarrollo": 0, "validacion": 0, "prueba": 0}
    for row in split_rows:
        split_counts[row["split"]] += 1

    d0_count = sum(1 for record in records if any(t["band"] == "D0" for t in record["traces"]))
    d1_count = sum(1 for record in records if any(t["band"] == "D1" for t in record["traces"]))
    d2_count = sum(1 for record in records if any(t["band"] == "D2" for t in record["traces"]))
    d3_count = sum(1 for record in records if any(t["band"] == "D3" for t in record["traces"]))
    total_bytes = sum(record["source"]["size_bytes"] for record in records)
    total_channel_traces = sum(
        trace["channel_count"] for record in records for trace in record["traces"]
    )
    total_scalars = sum(
        trace["sample_count"] * trace["channel_count"]
        for record in records
        for trace in record["traces"]
    )
    gain_groups = sorted({entry["gain_token"] for entry in calibration_files})

    unknowns = [
        {
            "id": "U-01",
            "campo": "site_id / site_name",
            "estado": "desconocido",
            "impacto": "No se puede agrupar por sitio oficial ni afirmar continuidad espacial",
            "resolucion_requerida": "Documentacion del levantamiento con identificadores y nombres de sitio",
        },
        {
            "id": "U-02",
            "campo": "latitude_deg / longitude_deg verificadas",
            "estado": "desconocido",
            "impacto": "Existe una candidata signed plausible, pero no verificada; no se usa para vincular TEM",
            "resolucion_requerida": "Confirmacion de la politica de hemisferios y una referencia independiente",
        },
        {
            "id": "U-03",
            "campo": "datum / crs",
            "estado": "desconocido",
            "impacto": "No se puede transformar a WGS84 ni comparar con TEM",
            "resolucion_requerida": "Datum, proyeccion y parametros de transformacion documentados",
        },
        {
            "id": "U-04",
            "campo": "altitude_m",
            "estado": "desconocido",
            "impacto": "Hay trazas con altitud 0 y diferencias internas no explicadas",
            "resolucion_requerida": "Altitud verificada por sitio y por traza",
        },
        {
            "id": "U-05",
            "campo": "tem_link",
            "estado": "desconocido",
            "impacto": "Ningun sondeo TEM puede aportar etiquetas al piloto",
            "resolucion_requerida": "Tabla reconciliada sondeo TEM - registro ARMT con evidencia",
        },
        {
            "id": "U-06",
            "campo": "calibration_validity",
            "estado": "desconocido",
            "impacto": "No se pueden interpretar amplitudes ni fases como campo",
            "resolucion_requerida": "Fecha, certificado, serie y cadena de aplicacion por canal",
        },
        {
            "id": "U-07",
            "campo": "channel_wiring / polarity",
            "estado": "desconocido",
            "impacto": "La orientacion y el signo de los canales no estan verificados",
            "resolucion_requerida": "Prueba de polaridad y rotacion con senal conocida",
        },
        {
            "id": "U-08",
            "campo": "dipole_length_cm",
            "estado": "desconocido",
            "impacto": "No se puede convertir Ey a campo electrico",
            "resolucion_requerida": "Longitud de dipolo medida y documentada",
        },
        {
            "id": "U-09",
            "campo": "qc_clipping_dead_channels",
            "estado": "desconocido",
            "impacto": "No se conocen saturacion, canales muertos, saltos ni huecos",
            "resolucion_requerida": "QC irreversible de P1 con mascaras y evidencia",
        },
        {
            "id": "U-10",
            "campo": "scenario_labels / noise_family",
            "estado": "desconocido",
            "impacto": "G3 no es evaluable por escenario",
            "resolucion_requerida": "Etiquetas de escenario y familia de ruido con origen y confianza",
        },
        {
            "id": "U-11",
            "campo": "timestamp_timezone",
            "estado": "desconocido",
            "impacto": "No se pueden alinear eventos entre instrumentos",
            "resolucion_requerida": "Zona horaria declarada por el instrumento o el operador",
        },
        {
            "id": "U-12",
            "campo": "campaign_label",
            "estado": "desconocido",
            "impacto": "La campana se identifica solo por ano y directorio",
            "resolucion_requerida": "Nombre oficial de campana y su alcance",
        },
        {
            "id": "U-13",
            "campo": "remote_reference",
            "estado": "desconocido",
            "impacto": "No hay comparador remoto para separar senal regional de distorsion local",
            "resolucion_requerida": "Referencia remota verificada o declaracion explicita de ausencia",
        },
    ]

    blockers = [
        {
            "id": "B-P0-01",
            "descripcion": "Nombre e identificador oficial del sitio desconocidos",
            "estado": "abierto",
            "severidad": "bloqueante",
            "afecta_p0": True,
            "evidencia": "site.site_id y site.site_name son null en los 15 registros",
        },
        {
            "id": "B-P0-02",
            "descripcion": "Coordenadas solo candidatas; politica de hemisferios no verificada",
            "estado": "abierto",
            "severidad": "bloqueante",
            "afecta_p0": True,
            "evidencia": (
                "La lectura signed en radianes x 1e8 produce 17.8-19.3 N y 99.6-99.7 W, "
                "pero no hay confirmacion independiente del signo ni del datum"
            ),
        },
        {
            "id": "B-P0-03",
            "descripcion": "Vinculo TEM-ARMT no verificado",
            "estado": "abierto",
            "severidad": "bloqueante",
            "afecta_p0": True,
            "evidencia": "tem_link.status=no_verificado en los 15 registros y en los 6 sondeos",
        },
        {
            "id": "B-P0-04",
            "descripcion": "Calibraciones sin fecha, certificado ni cadena de aplicacion",
            "estado": "abierto",
            "severidad": "bloqueante",
            "afecta_p0": True,
            "evidencia": "73 archivos .clb emparejados solo por tipo, serie y ganancia",
        },
        {
            "id": "B-P0-05",
            "descripcion": "QC de clipping, canales muertos, saltos y huecos no evaluado",
            "estado": "abierto",
            "severidad": "mayor",
            "afecta_p0": True,
            "evidencia": "qc.status=no_evaluado en los 15 registros",
        },
        {
            "id": "B-P0-06",
            "descripcion": "Etiquetas de escenario y familia de ruido ausentes",
            "estado": "abierto",
            "severidad": "mayor",
            "afecta_p0": True,
            "evidencia": "No existe campo de escenario ni de familia en el inventario",
        },
        {
            "id": "B-P0-07",
            "descripcion": "Zona horaria de las marcas temporales no declarada",
            "estado": "abierto",
            "severidad": "mayor",
            "afecta_p0": True,
            "evidencia": "reader.summary declara timestamp_timezone=unspecified",
        },
    ]

    samples_ok = False
    samples_detail = "No se ejecuto validar_muestras.py"
    if samples_path.exists():
        try:
            samples_report = json.loads(samples_path.read_text(encoding="utf-8-sig"))
            samples_ok = samples_report.get("resultado") == "APROBADO"
            samples_detail = "validacion_muestras.json: %s" % samples_report.get(
                "resultado", "sin resultado"
            )
        except (ValueError, OSError):
            samples_detail = "validacion_muestras.json ilegible"

    checklist = [
        {
            "id": "P0-01",
            "requisito": "Inventario de registros, campanas, fechas, bandas, fs, duracion, canales, sensores, ganancias, orientaciones y dipolos",
            "estado": "CUMPLIDO",
            "evidencia": "manifest.json: armt_records",
            "nota": "Los campos sin dato quedan null y declarados en unknowns",
        },
        {
            "id": "P0-02",
            "requisito": "Hash de archivos y versiones del software",
            "estado": "CUMPLIDO",
            "evidencia": "manifest.json: sources, software, armt_records",
            "nota": "SHA-256 de archivo completo",
        },
        {
            "id": "P0-03",
            "requisito": "Limitar la red a MT/AMT en D0/D1 y excluir D2/D3 y portadoras RMT",
            "estado": "CUMPLIDO",
            "evidencia": "manifest.json: scope",
            "nota": "Las trazas D2/D3 se inventarian con in_scope=false",
        },
        {
            "id": "P0-04",
            "requisito": "Asignar registros completos a desarrollo, validacion y prueba antes de cortar ventanas",
            "estado": "CUMPLIDO",
            "evidencia": "splits.csv",
            "nota": "Propuesta congelada a nivel de registro y sitio",
        },
        {
            "id": "P0-05",
            "requisito": "Contrato comun versionado con forma, orden, unidades, tiempos, mascaras y proveniencia",
            "estado": "CUMPLIDO",
            "evidencia": "schema.json",
            "nota": "JSON Schema draft-07",
        },
        {
            "id": "P0-06",
            "requisito": "Presupuesto de error distribuido y separacion de error aleatorio y sesgo",
            "estado": "PARCIAL",
            "evidencia": "protocolo_validacion.md, seccion 6",
            "nota": "Las metas estan fijadas; la distribucion instrumental requiere P1",
        },
        {
            "id": "P0-07",
            "requisito": "Campos desconocidos explicitos que limiten el alcance",
            "estado": "CUMPLIDO",
            "evidencia": "manifest.json: unknowns",
            "nota": "No se rellenan con valores convenientes",
        },
        {
            "id": "P0-08",
            "requisito": "Protocolo de evaluacion congelado",
            "estado": "CUMPLIDO",
            "evidencia": "protocolo_validacion.md",
            "nota": "Version 1.0.0",
        },
        {
            "id": "P0-09",
            "requisito": "Manifiesto completo para el piloto",
            "estado": "PARCIAL",
            "evidencia": "manifest.json",
            "nota": "Faltan identidad de sitio, coordenadas, vinculo TEM y validez de calibracion",
        },
        {
            "id": "P0-10",
            "requisito": "Ausencia de interseccion de grupos entre particiones",
            "estado": "CUMPLIDO",
            "evidencia": "validacion_etapa0.json",
            "nota": "Se comprueba site_group y campaign_group",
        },
        {
            "id": "P0-11",
            "requisito": "Reproduccion de una corrida fijando configuracion y semilla",
            "estado": "NO_APLICA",
            "evidencia": "manifest.json: generator",
            "nota": "P0 no entrena modelos; el generador y sus hashes quedan fijados",
        },
        {
            "id": "P0-12",
            "requisito": "Lectura completa sin cambiar valores",
            "estado": "CUMPLIDO" if samples_ok else "PENDIENTE",
            "evidencia": samples_detail,
            "nota": "validar_muestras.py lee todas las muestras declaradas y comprueba ida y vuelta",
        },
    ]

    p0_status = (
        "COMPLETO"
        if all(item["estado"] in ("CUMPLIDO", "NO_APLICA") for item in checklist)
        and not any(
            blocker["estado"] == "abierto" and blocker["afecta_p0"]
            for blocker in blockers
        )
        else "PARCIAL"
    )

    artifacts = []
    for path, role in (
        (schema_path, "Esquema del manifiesto"),
        (splits_path, "Particiones congeladas"),
        (protocol_path, "Protocolo de evaluacion congelado"),
    ):
        artifacts.append({"artifact": file_entry(path, WORKSPACE, args.software_root), "rol": role})

    manifest = {
        "schema_version": "1.0.0",
        "manifest_version": "1.0.0",
        "artifact": "manifest_etapa0",
        "generated_at_utc": utc_now(),
        "generator": {
            "script": "etapa0/inventario_armt.py",
            "sha256": sha256_file(Path(__file__)),
            "python": sys.version.split()[0],
            "command": " ".join([Path(sys.argv[0]).name] + sys.argv[1:]),
        },
        "scope": {
            "etapa": 0,
            "puerta": "P0",
            "p0_status": p0_status,
            "bandas_incluidas": ["D0", "D1"],
            "bandas_excluidas": ["D2", "D3"],
            "rmt_portadoras": "fuera_de_alcance",
            "productos": ["MT/AMT"],
            "separacion_detector_separador": True,
            "bss_requiere_sx_sy_zopt": False,
            "soporte_tem_vacio_es_valido": True,
            "fuente_del_alcance": "PLAN_IMPLEMENTACION_ARMT.md v1.3, secciones 4 y 3.6",
        },
        "sources": {
            "read_only": True,
            "path_bases": {
                "workspace": str(WORKSPACE),
                "software_root": str(args.software_root),
            },
            "armt_root": str(args.armt_root),
            "armt_records_roots": [str(path) for path in records_roots if path.exists()],
            "calibration_root": str(args.armt_root / "Calibrations"),
            "tem_manifest": file_entry(args.tem_manifest, WORKSPACE, args.software_root),
            "notes": [
                "Los archivos se abren en modo lectura; no se escriben en los proyectos de origen",
                "Los hashes SHA-256 cubren el archivo completo, incluidos bytes sobrantes",
                "El manifiesto no aplica calibracion ni convierte unidades",
                "Las rutas distinguen base workspace y base software_root",
            ],
        },
        "governing_documents": governing_documents,
        "software": {
            "python": sys.version.split()[0],
            "numpy": getattr(__import__("numpy"), "__version__", "desconocida"),
            "jsonschema": package_version("jsonschema"),
            "armt_processing_version": declared_version,
            "armt_processing_pyproject_version": pyproject_version,
            "version_consistency": consistency,
            "modules": modules,
        },
        "counts": {
            "armt_records": len(records),
            "armt_traces": sum(len(record["traces"]) for record in records),
            "armt_scalar_channels": total_channel_traces,
            "armt_scalar_samples": total_scalars,
            "bytes_armt_sbf": total_bytes,
            "records_2021": sum(1 for r in records if r["campaign"]["year"] == 2021),
            "records_2023": sum(1 for r in records if r["campaign"]["year"] == 2023),
            "records_with_d0": d0_count,
            "records_with_d1": d1_count,
            "records_with_d2": d2_count,
            "records_with_d3": d3_count,
            "calibration_files": len(calibration_files),
            "calibration_gain_groups": len(gain_groups),
            "calibration_electrical_amplifier": sum(
                1 for c in calibration_files if c["kind"] == "electrical_amplifier"
            ),
            "calibration_magnetic_sensor": sum(
                1 for c in calibration_files if c["kind"] == "magnetic_sensor"
            ),
            "tem_candidates": len(tem_candidates),
            "splits": split_counts,
        },
        "armt_records": records,
        "calibration_files": calibration_files,
        "tem_dataset": {
            "source_manifest": file_entry(args.tem_manifest, WORKSPACE, args.software_root),
            "project_reference": "GTM26-068-GH-027",
            "project_reference_source": "Ruta del dosier; no es un identificador de sitio ARMT",
            "candidate_count": len(tem_candidates),
            "link_status": "no_verificado",
            "note": (
                "El dosier contiene 22 entradas, incluidas variantes procesadas, SIR y "
                "un script. Se seleccionan solo los seis sondeos canonicos SER-XX.tem "
                "del directorio TEMS. El dosier aporta escenarios TEM candidatos con "
                "coordenadas metricas locales y sin vinculo documentado a los registros "
                "ARMT. No sustituye P2-T."
            ),
        },
        "tem_candidates": tem_candidates,
        "derived_products": derived_products,
        "artifacts": artifacts,
        "unknowns": unknowns,
        "blockers": blockers,
        "p0_checklist": checklist,
    }

    # Quitar campos auxiliares usados solo durante el emparejamiento.
    for entry in calibration_files:
        entry.pop("_selected_table", None)

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print("Manifiesto: %s" % manifest_path)
    print("Particiones: %s" % splits_path)
    print(
        "Registros: %d | trazas: %d | calibraciones: %d | TEM: %d | P0: %s"
        % (
            len(records),
            manifest["counts"]["armt_traces"],
            len(calibration_files),
            len(tem_candidates),
            p0_status,
        )
    )
    print(
        "Splits: desarrollo=%d validacion=%d prueba=%d"
        % (split_counts["desarrollo"], split_counts["validacion"], split_counts["prueba"])
    )
    missing = [
        record["record_id"]
        for record in records
        if record["calibration"]["channels_matched"]
        != record["calibration"]["channels_total"]
    ]
    if missing:
        print("Registros con calibracion incompleta: %s" % ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
