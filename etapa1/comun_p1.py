#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utilidades comunes de la Etapa 1 (P1).

No escribe en los proyectos de origen. Todo camino absoluto que aparece en los
entregables de P1 se resuelve a traves de ``path_ref`` y ``path_base`` del
manifiesto de P0, para que los reportes sean portables dentro de este equipo.
"""

import hashlib
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

WORKSPACE = Path(__file__).resolve().parents[1]
ETAPA0 = WORKSPACE / "etapa0"
ETAPA1 = WORKSPACE / "etapa1"
BARRIDO = ETAPA1 / "barrido"
DEFAULT_SOFTWARE_ROOT = Path(r"D:\ARRT_software")
ARMT_ROOT = DEFAULT_SOFTWARE_ROOT / "ARMT_processing"

P0_ARTIFACTS = [
    "etapa0/manifest.json",
    "etapa0/schema.json",
    "etapa0/splits.csv",
    "etapa0/protocolo_validacion.md",
]

TARGET_RECORD = "ARMT5-700-14-14-01"
CHANNELS = ("Ex", "Ey", "Hx", "Hy", "Hz")


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError("tipo no serializable: %r" % (type(value),))


def dump_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=json_default)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def resolve_entry(entry):
    """Resuelve una entrada con path_abs/path_ref/path_base del manifiesto P0."""
    absolute = Path(entry["path_abs"])
    if absolute.exists():
        return absolute
    base = entry.get("path_base")
    if base == "workspace":
        return WORKSPACE / entry["path_ref"]
    if base == "software_root":
        return DEFAULT_SOFTWARE_ROOT / entry["path_ref"]
    return Path(entry["path_ref"])


def path_ref_for(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(DEFAULT_SOFTWARE_ROOT).as_posix(), "software_root"
    except ValueError:
        return path.relative_to(WORKSPACE).as_posix(), "workspace"


def load_config(path=None):
    return load_json(path or (ETAPA1 / "config_p1.json"))


def load_config_barrido(path=None):
    return load_json(path or (ETAPA1 / "config_barrido.json"))


def load_p0_manifest():
    return load_json(ETAPA0 / "manifest.json")


def load_p0_validation():
    return load_json(ETAPA0 / "validacion_etapa0.json")


def target_record(manifest=None):
    manifest = manifest or load_p0_manifest()
    for record in manifest["armt_records"]:
        if record["record_id"] == TARGET_RECORD:
            return record
    raise KeyError("registro objetivo %s ausente del manifiesto P0" % TARGET_RECORD)


def iter_records(manifest=None):
    """Devuelve los 15 registros de P0 en el orden del manifiesto."""
    manifest = manifest or load_p0_manifest()
    return list(manifest["armt_records"])


def record_by_id(record_id, manifest=None):
    manifest = manifest or load_p0_manifest()
    for record in manifest["armt_records"]:
        if record["record_id"] == record_id:
            return record
    raise KeyError("registro %s ausente del manifiesto P0" % record_id)


def verify_p0_hashes():
    """Devuelve el estado de los cuatro artefactos congelados de P0."""
    expected = load_p0_validation()
    mapping = {
        "etapa0/manifest.json": expected["manifest_sha256"],
        "etapa0/schema.json": expected["schema_sha256"],
        "etapa0/splits.csv": expected["splits_sha256"],
        "etapa0/protocolo_validacion.md": expected["protocolo_sha256"],
    }
    results = []
    for rel, digest in mapping.items():
        path = WORKSPACE / rel
        actual = sha256_file(path) if path.exists() else None
        results.append(
            {
                "artifact": rel,
                "expected_sha256": digest,
                "actual_sha256": actual,
                "unchanged": actual == digest,
            }
        )
    return results


def import_armt():
    """Importa el lector ARMT sin instalar nada y sin tocar el proyecto origen."""
    root = str(ARMT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from armt import SBFReader, read_calibration  # noqa: F401

    return SBFReader, read_calibration


def band_list(config):
    return list(config["bands"].keys())


def band_range(config, band):
    return tuple(float(v) for v in config["bands"][band]["review_range_hz"])


def interp_count(f_min, f_max, per_decade, minimum):
    if f_min <= 0 or f_max <= f_min:
        raise ValueError("rango de interpolacion invalido: %r" % ((f_min, f_max),))
    span = math.log10(f_max / f_min)
    return max(int(minimum), int(math.ceil(span * per_decade)) + 1)


def branch_correct(phase_deg, keep_mask=None):
    """Desenrolla la fase con el salto minimo entre puntos consecutivos.

    ``keep_mask`` permite excluir puntos ya marcados como atipicos. Devuelve la
    fase corregida y el numero de correcciones de 360 grados aplicadas.
    """
    phase = np.asarray(phase_deg, dtype=float)
    if keep_mask is None:
        keep_mask = np.ones(phase.shape, dtype=bool)
    keep = np.flatnonzero(keep_mask)
    out = np.full(phase.shape, np.nan, dtype=float)
    corrections = 0
    if len(keep) == 0:
        return out, corrections
    out[keep[0]] = phase[keep[0]]
    for previous, current in zip(keep[:-1], keep[1:]):
        step = phase[current] - phase[previous]
        turns = int(round(step / 360.0))
        if turns != 0:
            corrections += abs(turns)
        out[current] = out[previous] + (step - 360.0 * turns)
    return out, corrections


def mark_phase_outliers(phase_deg, threshold_deg):
    """Marca puntos cuyo salto minimo respecto al ultimo punto valido excede el umbral.

    Se recorre en orden de frecuencia. Un punto atipico no actualiza la
    referencia, de modo que el siguiente punto se compara con el ultimo valido.
    """
    phase = np.asarray(phase_deg, dtype=float)
    keep = np.zeros(phase.shape, dtype=bool)
    if len(phase) == 0:
        return keep
    keep[0] = True
    previous = 0
    for index in range(1, len(phase)):
        step = phase[index] - phase[previous]
        step = (step + 180.0) % 360.0 - 180.0
        if abs(step) <= threshold_deg:
            keep[index] = True
            previous = index
    return keep


def near_duplicate_groups(freqs, rel_tol):
    """Agrupa frecuencias contiguas cuya separacion relativa es <= rel_tol."""
    freqs = np.asarray(freqs, dtype=float)
    groups = []
    if len(freqs) <= 1:
        return groups
    start = 0
    for index in range(1, len(freqs)):
        rel = (freqs[index] - freqs[index - 1]) / freqs[index - 1]
        if rel > rel_tol:
            if index - start > 1:
                groups.append((start, index))
            start = index
    if len(freqs) - start > 1:
        groups.append((start, len(freqs)))
    return groups


def run_intervals(flag, offset, min_length):
    """Intervalos [inicio, fin) de True con longitud >= min_length."""
    flag = np.asarray(flag, dtype=bool)
    if flag.size == 0:
        return []
    padded = np.concatenate(([False], flag, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    starts = edges[0::2]
    stops = edges[1::2]
    lengths = stops - starts
    return [
        (int(offset + a), int(offset + b))
        for a, b, n in zip(starts, stops, lengths)
        if n >= min_length
    ]


def dilate_intervals(intervals, pad, limit):
    merged = []
    for start, stop in sorted(intervals):
        start = max(0, start - pad)
        stop = min(limit, stop + pad)
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
        else:
            merged.append((start, stop))
    return merged


def pack_bool(mask, bitorder="little"):
    return np.packbits(np.asarray(mask, dtype=np.uint8), bitorder=bitorder)


def unpack_bool(packed, n_samples, bitorder="little"):
    bits = np.unpackbits(np.asarray(packed, dtype=np.uint8), bitorder=bitorder)
    return bits[:n_samples].astype(bool)


def build_mask_from_intervals(intervals, n_samples):
    mask = np.zeros(n_samples, dtype=bool)
    for start, stop in intervals:
        mask[start:stop] = True
    return mask


def capped(intervals, limit):
    if len(intervals) <= limit:
        return {"count": len(intervals), "truncated": False, "intervals": intervals}
    return {"count": len(intervals), "truncated": True, "intervals": intervals[:limit]}


def rel_to_abs(entry):
    return "%s/%s" % (entry["path_base"], entry["path_ref"])


def fmt_float(value, digits=6):
    return float(("%." + str(digits) + "f") % float(value))


def robust_sigma(values):
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return 0.0, 0.0
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return median, 1.4826 * mad


def status_from_checks(checks):
    states = [c["estado"] for c in checks]
    if any(s == "FALLA" for s in states):
        return "FALLA"
    if any(s in ("OBSERVACION", "NO_APLICABLE") for s in states):
        return "PASA_CON_OBSERVACIONES"
    return "PASA"
