"""Utilidades comunes del banco sintetico de contrato.

El banco vive fuera de ``etapa0`` y nunca escribe en el manifiesto ni en las
particiones del piloto. Todas las rutas y hashes se calculan desde aqui para
que los generadores compartan la misma nocion de proveniencia.
"""

import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent
DEFAULT_MODEL = HERE / "modelo_control.json"
DEFAULT_OUT_DIR = HERE
REAL_MANIFEST = WORKSPACE / "etapa0" / "manifest.json"
REAL_SPLITS = WORKSPACE / "etapa0" / "splits.csv"
REAL_VALIDATION = WORKSPACE / "etapa0" / "validacion_etapa0.json"


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    with open(path, encoding="utf-8-sig") as stream:
        return json.load(stream)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def file_entry(path):
    path = Path(path).resolve()
    try:
        ref = path.relative_to(WORKSPACE).as_posix()
        base = "workspace"
    except ValueError:
        ref = path.as_posix()
        base = "external"
    return {
        "path_abs": str(path),
        "path_ref": ref,
        "path_base": base,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "mtime_utc": datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc
        ).isoformat().replace("+00:00", "Z"),
    }


def find_record(manifest, record_id):
    for record in manifest.get("armt_records", []):
        if record.get("record_id") == record_id:
            return record
    raise SystemExit("No existe el registro objetivo %s en el manifiesto P0" % record_id)


def load_real_context(model):
    """Lee el manifiesto P0 y comprueba que no cambio desde su validacion."""
    if not REAL_MANIFEST.exists():
        raise SystemExit("Falta el manifiesto P0: %s" % REAL_MANIFEST)
    if not REAL_VALIDATION.exists():
        raise SystemExit("Falta la validacion P0: %s" % REAL_VALIDATION)

    manifest = read_json(REAL_MANIFEST)
    validation = read_json(REAL_VALIDATION)
    manifest_sha = sha256_file(REAL_MANIFEST)
    splits_sha = sha256_file(REAL_SPLITS)

    if manifest_sha != validation.get("manifest_sha256"):
        raise SystemExit(
            "El manifiesto P0 cambio desde su validacion. Regenere Etapa 0 antes "
            "de construir el banco sintetico."
        )
    if splits_sha != validation.get("splits_sha256"):
        raise SystemExit(
            "splits.csv cambio desde la validacion P0. Regenere Etapa 0 antes "
            "de construir el banco sintetico."
        )

    record = find_record(manifest, model["target_record"])
    split = record["split"]["split"]
    if split != model["target_split"]:
        raise SystemExit(
            "El registro objetivo %s esta en %s y el banco exige %s"
            % (record["record_id"], split, model["target_split"])
        )

    traces = []
    for trace in record.get("traces", []):
        if trace.get("band") not in ("D0", "D1"):
            continue
        traces.append(
            {
                "band": trace["band"],
                "sample_rate_hz": trace["sample_rate_hz"],
                "sample_count": trace["sample_count"],
                "duration_seconds": trace["duration_seconds"],
                "channels": list(trace.get("channels") or []),
            }
        )

    return {
        "record_id": record["record_id"],
        "split": split,
        "campaign_group": record["campaign"]["campaign_group"],
        "site_group": record["site"]["site_group"],
        "campaign_year": record["campaign"]["year"],
        "source_path_ref": record["source"]["path_ref"],
        "source_sha256": record["source"]["sha256"],
        "traces": traces,
        "manifest_sha256": manifest_sha,
        "splits_sha256": splits_sha,
        "validation_sha256": sha256_file(REAL_VALIDATION),
        "p0_manifest_sha256": validation["manifest_sha256"],
        "p0_splits_sha256": validation["splits_sha256"],
    }


def load_parse_tem():
    """Carga el parser real de Etapa 0 sin ejecutar su main."""
    path = WORKSPACE / "etapa0" / "inventario_armt.py"
    if not path.exists():
        raise SystemExit("Falta el parser de Etapa 0: %s" % path)
    spec = importlib.util.spec_from_file_location("inventario_armt_etapa0", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_tem


def read_header_value(path, key):
    wanted = key.upper()
    with open(path, encoding="utf-8", errors="replace") as stream:
        for raw_line in stream:
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("<"):
                continue
            parts = line.split(None, 1)
            if parts and parts[0].upper() == wanted:
                return parts[1].strip() if len(parts) > 1 else ""
    return None


def python_version():
    return sys.version.split()[0]
