#!/usr/bin/env python3
"""Lectura completa de los SBF de Etapa 0 y prueba de ida y vuelta.

Lee todas las muestras declaradas con ``armt.validation.validate_file`` y
comprueba que una copia NPY conserva forma, tipo y valores. No aplica
calibracion ni escribe en los proyectos de origen.

Uso:
    python etapa0/validar_muestras.py
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_SOFTWARE_ROOT = Path(r"D:\ARRT_software")
DEFAULT_ARMT_ROOT = DEFAULT_SOFTWARE_ROOT / "ARMT_processing"
DEFAULT_MANIFEST = WORKSPACE / "etapa0" / "manifest.json"
DEFAULT_OUT = WORKSPACE / "etapa0" / "validacion_muestras.json"
TMP_ROOT = Path(
    os.environ.get(
        "ARMT_TMP", r"C:\Users\Geotem_User\AppData\Local\Temp\opencode"
    )
)


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_armt(armt_root):
    sys.path.insert(0, str(armt_root))
    from armt.reader import SBFReader
    from armt.validation import validate_file

    return SBFReader, validate_file


def record_paths(manifest_path, armt_root):
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        return [
            (record["record_id"], Path(record["source"]["path_abs"]))
            for record in manifest["armt_records"]
        ]
    paths = []
    for root in (armt_root / "ARMT_data", armt_root / "Soundings"):
        if root.exists():
            for path in sorted(root.rglob("*.sbf")):
                paths.append((path.stem, path))
    return paths


def roundtrip_check(SBFReader, path, tmp_root):
    import numpy as np

    with SBFReader(path) as reader:
        trace_index = None
        for trace in reader.traces:
            if trace.band_mask == 1:
                trace_index = trace.index
                break
        if trace_index is None:
            trace_index = 0
        stop = min(4096, reader.traces[trace_index].sample_count)
        first = reader.read_samples(trace_index, 0, stop, units="counts")
        second = reader.read_samples(trace_index, 0, stop, units="counts")
    tmp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="armt_rt_", dir=str(tmp_root)) as tmp:
        target = Path(tmp) / "slice.npy"
        np.save(target, first)
        restored = np.load(target, allow_pickle=False)
    equal_copy = bool(np.array_equal(first, second))
    equal_disk = bool(np.array_equal(first, restored))
    return {
        "trace_index": trace_index,
        "samples": int(first.shape[0]),
        "channels": int(first.shape[1]),
        "dtype": str(first.dtype),
        "repeatable_read": equal_copy,
        "npy_roundtrip": equal_disk,
        "ok": equal_copy and equal_disk,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--armt-root", type=Path, default=DEFAULT_ARMT_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    SBFReader, validate_file = load_armt(args.armt_root)
    records = record_paths(args.manifest, args.armt_root)
    if args.limit:
        records = records[: args.limit]
    if not records:
        raise SystemExit("No hay registros SBF para validar")

    results = []
    total = len(records)
    for index, (record_id, path) in enumerate(records, start=1):
        print("[%d/%d] %s" % (index, total, path.name), flush=True)
        report = validate_file(path)
        checks_ok = all(
            check.get("raw_decode_matches")
            for trace in report["traces"]
            for check in trace.get("spot_checks", [])
        )
        roundtrip = roundtrip_check(SBFReader, path, TMP_ROOT)
        results.append(
            {
                "record_id": record_id,
                "source": str(path.resolve()),
                "sha256_before": report["sha256"],
                "status": report["status"],
                "source_unchanged": bool(report.get("source_unchanged")),
                "total_scalar_samples": int(report.get("total_scalar_samples", 0)),
                "spot_checks_ok": checks_ok,
                "roundtrip": roundtrip,
                "traces": [
                    {
                        "trace_index": trace["trace_index"],
                        "band_mask": report["inventory"]["traces"][trace["trace_index"]][
                            "band_mask"
                        ],
                        "sample_rate_hz": trace["sample_rate_hz"],
                        "sample_count_per_channel": trace["sample_count_per_channel"],
                        "channel_count": trace["channel_count"],
                        "duration_seconds": trace["duration_seconds"],
                        "bytes_per_sample": trace["bytes_per_sample"],
                        "channel_statistics": trace["channel_statistics"],
                    }
                    for trace in report["traces"]
                ],
            }
        )

    result = "APROBADO"
    for item in results:
        if not (
            item["status"] in ("readable", "readable_with_notes")
            and item["source_unchanged"]
            and item["spot_checks_ok"]
            and item["roundtrip"]["ok"]
        ):
            result = "FALLA"
            break

    output = {
        "validacion_version": "1.0.0",
        "generated_at_utc": utc_now(),
        "scope": (
            "Lectura de todas las muestras declaradas, comprobaciones puntuales "
            "independientes y roundtrip NPY. No aplica calibracion ni convierte unidades."
        ),
        "resultado": result,
        "summary": {
            "records": len(results),
            "records_ok": sum(
                1
                for item in results
                if item["status"] in ("readable", "readable_with_notes")
                and item["source_unchanged"]
                and item["spot_checks_ok"]
                and item["roundtrip"]["ok"]
            ),
            "total_scalar_samples": sum(item["total_scalar_samples"] for item in results),
        },
        "records": results,
        "notes": [
            "Un resultado legible no certifica unidades, cableado, polaridad ni calibracion",
            "Los bytes sobrantes se excluyen de las muestras y se registran en el lector",
            "La prueba NPY usa una copia temporal y no modifica el SBF",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Resultado: %s" % result)
    print("Reporte: %s" % args.out.resolve())
    return 0 if result == "APROBADO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
