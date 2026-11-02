#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exportacion calibrada reversible de D0/D1.

Solo aplica ``counts * adc_to_uv``. No aplica ganancia, respuesta .clb,
longitud de dipolo, polaridad ni orientacion. Las muestras invalidas no se
borran: se entregan las mascaras de QC por separado.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import comun_p1 as comun


def window_for_band(config, band, n_samples, fs):
    export = config["export"]
    if band == "D0":
        start = int(round(float(export["d0_start_s"]) * fs))
        duration = float(export["d0_duration_s"])
        stop = min(n_samples, start + int(round(duration * fs)))
    else:
        start = 0
        stop = n_samples
    return start, stop


def export_band(acq, config, band, output_dir):
    SBFReader, _ = comun.import_armt()
    trace_index = int(config["bands"][band]["trace_index"])
    trace = acq.trace(trace_index)
    fs = float(trace.sample_rate_hz)
    n_total = int(trace.sample_count)
    channels = list(trace.channels)
    adc = np.asarray(trace.adc_to_uv, dtype=np.float64)
    start, stop = window_for_band(config, band, n_total, fs)
    n = stop - start
    block = int(config["qc"]["block_samples"])

    dtype = np.dtype("<f4")
    filename = "01401401_%s_%s_uV.npy" % (
        band,
        ("%ds" % int(round(n / fs))) if band == "D0" else ("%ds" % int(round(n / fs))),
    )
    path = output_dir / filename
    memmap = np.lib.format.open_memmap(path, mode="w+", dtype=dtype, shape=(n, len(channels)))

    minimum = np.full(len(channels), np.inf)
    maximum = np.full(len(channels), -np.inf)
    total = np.zeros(len(channels), dtype=np.float64)
    total_sq = np.zeros(len(channels), dtype=np.float64)
    nonfinite = np.zeros(len(channels), dtype=np.int64)

    for block_start in range(start, stop, block):
        block_stop = min(block_start + block, stop)
        counts = acq.read_samples(
            trace_index,
            start=block_start,
            stop=block_stop,
            channels=channels,
            units="counts",
        )
        microvolts = (counts.astype(np.float64) * adc).astype(dtype)
        memmap[block_start - start : block_stop - start, :] = microvolts
        minimum = np.minimum(minimum, microvolts.min(axis=0))
        maximum = np.maximum(maximum, microvolts.max(axis=0))
        total += microvolts.sum(axis=0, dtype=np.float64)
        total_sq += np.square(microvolts, dtype=np.float64).sum(axis=0)
        nonfinite += (~np.isfinite(microvolts)).sum(axis=0)
    memmap.flush()
    del memmap

    mean = total / n
    variance = np.maximum(total_sq / n - mean * mean, 0.0)
    stats = {
        channel: {
            "min_uV": float(minimum[i]),
            "max_uV": float(maximum[i]),
            "mean_uV": float(mean[i]),
            "std_uV": float(np.sqrt(variance[i])),
            "nonfinite": int(nonfinite[i]),
        }
        for i, channel in enumerate(channels)
    }

    mask_path = comun.ETAPA1 / ("mascaras_QC_%s.npz" % band)
    payload = {
        "file": str(Path("exportaciones") / filename),
        "abs_path": str(path),
        "sha256": comun.sha256_file(path),
        "shape": [int(n), len(channels)],
        "dtype": str(dtype),
        "units": "uV",
        "channels": channels,
        "trace_index": trace_index,
        "sample_rate_hz": fs,
        "start_sample": int(start),
        "stop_sample": int(stop),
        "n_samples_total": n_total,
        "duration_s": float(n / fs),
        "start_time_local": trace.start_time,
        "adc_to_uv": [float(v) for v in adc],
        "formula": "uV = counts * adc_to_uv",
        "mask_file": mask_path.name,
        "stats": stats,
    }
    return payload, path


def write_verification(acq, config, bands, output_dir):
    rows = []
    for band, payload in bands.items():
        trace_index = int(config["bands"][band]["trace_index"])
        fs = float(config["bands"][band]["sample_rate_hz"])
        adc = np.asarray(payload["adc_to_uv"], dtype=np.float64)
        data = np.load(output_dir / Path(payload["file"]).name, mmap_mode="r")
        n = data.shape[0]
        points = sorted({0, 1, 2, n // 2, n // 2 + 1, n - 2, n - 1})
        for sample in points:
            if sample < 0 or sample >= n:
                continue
            counts = acq.read_samples(
                trace_index,
                start=payload["start_sample"] + sample,
                stop=payload["start_sample"] + sample + 1,
                channels=payload["channels"],
                units="counts",
            )[0]
            expected = counts.astype(np.float64) * adc
            exported = data[sample]
            for index, channel in enumerate(payload["channels"]):
                rows.append(
                    {
                        "band": band,
                        "sample_index_in_export": int(sample),
                        "sample_index_in_sbf": int(payload["start_sample"] + sample),
                        "channel": channel,
                        "counts": int(counts[index]),
                        "adc_to_uv": float(adc[index]),
                        "expected_uV": float(expected[index]),
                        "exported_uV": float(exported[index]),
                        "abs_diff_uV": float(abs(expected[index] - exported[index])),
                    }
                )
        del data

    path = output_dir / "muestras_verificacion.csv"
    with open(path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "band",
                "sample_index_in_export",
                "sample_index_in_sbf",
                "channel",
                "counts",
                "adc_to_uv",
                "expected_uV",
                "exported_uV",
                "abs_diff_uV",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def build(config=None):
    config = config or comun.load_config()
    SBFReader, _ = comun.import_armt()
    record = comun.target_record()
    output_dir = comun.ETAPA1 / "exportaciones"
    output_dir.mkdir(parents=True, exist_ok=True)

    bands = {}
    with SBFReader(record["source"]["path_abs"]) as acq:
        for band in comun.band_list(config):
            payload, _ = export_band(acq, config, band, output_dir)
            bands[band] = payload
        verification = write_verification(acq, config, bands, output_dir)

    payload = {
        "export_version": "P1-EXPORT-1.0.0",
        "generated_at_utc": comun.utc_now(),
        "stage": 1,
        "target_record": comun.TARGET_RECORD,
        "source": record["source"],
        "formula": "uV = counts * adc_to_uv",
        "applied": ["adc_to_uv"],
        "not_applied": [
            "ganancia de registro",
            "respuesta .clb (amplitud y fase)",
            "longitud de dipolo",
            "polaridad",
            "orientacion",
        ],
        "bands": bands,
        "verification_csv": str(Path("exportaciones") / verification.name),
        "notes": [
            "Las muestras no se borran ni se corrigen por QC; las mascaras son archivos aparte.",
            "D0 se exporta como ventana de 900 s desde el inicio del registro.",
            "D1 se exporta completo (45 s).",
            "El campo fisico en V/m o nT no se obtiene con esta exportacion.",
        ],
    }
    comun.dump_json(output_dir / "exportaciones.json", payload)
    return {"report": str(output_dir / "exportaciones.json"), "bands": bands}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    config = comun.load_config(args.config)
    result = build(config)
    print("reporte de exportacion: %s" % result["report"])
    for band, payload in result["bands"].items():
        print(
            "%s: %s %s %s"
            % (band, payload["file"], payload["shape"], payload["units"])
        )


if __name__ == "__main__":
    main()
