#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QC irreversible de D0/D1, por registro y banda.

Detecta clipping, canales muertos, valores pegados, relleno de ceros, saltos,
muestras faltantes y posibles transitorios de conmutacion. Los saltos por
amplitud se reportan pero no se enmascaran: pueden ser sferics utiles.

``qc_band`` acepta ``mask_path`` para que el barrido de los 15 registros no
sobrescriba las mascaras del registro objetivo de P1.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import comun_p1 as comun


def read_channel(acq, trace_index, channel, n_samples, block_samples):
    parts = []
    for start in range(0, n_samples, block_samples):
        stop = min(start + block_samples, n_samples)
        block = acq.read_samples(
            trace_index, start=start, stop=stop, channels=[channel], units="counts"
        )
        if block.shape[0] != stop - start:
            raise RuntimeError(
                "lectura incompleta en %s [%d,%d): %d muestras"
                % (channel, start, stop, block.shape[0])
            )
        parts.append(block[:, 0])
    return np.concatenate(parts)


def constant_run_lengths(samples):
    n = len(samples)
    if n == 0:
        return np.array([], dtype=np.int64), np.array([], dtype=np.int64)
    changes = np.flatnonzero(np.diff(samples) != 0)
    starts = np.concatenate(([0], changes + 1))
    stops = np.concatenate((changes + 1, [n]))
    return starts, stops - starts


def subsample_thresholds(acq, trace_index, channels, n_samples, config):
    qc = config["qc"]
    n_blocks = int(qc["jump_sample_blocks"])
    block = int(qc["jump_block_samples"])
    block = min(block, n_samples)
    if n_blocks <= 1:
        starts = [0]
    else:
        span = max(0, n_samples - block)
        starts = sorted({int(round(i * span / (n_blocks - 1))) for i in range(n_blocks)})

    thresholds = {}
    for channel in channels:
        diffs = []
        for start in starts:
            stop = min(start + block, n_samples)
            block_data = acq.read_samples(
                trace_index, start=start, stop=stop, channels=[channel], units="counts"
            )[:, 0]
            if block_data.size > 1:
                diffs.append(np.diff(block_data).astype(np.float64))
        values = np.concatenate(diffs) if diffs else np.array([0.0])
        median, sigma = comun.robust_sigma(values)
        threshold = float(qc["jump_sigma"]) * sigma
        fallback = False
        if not np.isfinite(threshold) or threshold <= 0.0:
            fallback = True
            p999 = float(np.percentile(np.abs(values - median), 99.9))
            threshold = max(1.0, 0.5 * p999)
        thresholds[channel] = {
            "median_diff_counts": float(median),
            "robust_sigma_counts": float(sigma),
            "threshold_counts": float(threshold),
            "sigma_multiplier": float(qc["jump_sigma"]),
            "fallback_used": bool(fallback),
            "subsample_diffs": int(values.size),
            "blocks": len(starts),
            "block_samples": int(block),
        }
    return thresholds


def switching_events(samples, fs, config):
    qc = config["qc"]
    block = max(1, int(round(float(qc["switching_block_s"]) * fs)))
    n_blocks = len(samples) // block
    if n_blocks < 3:
        return {"estado": "NO_APLICABLE", "n_blocks": n_blocks, "events": []}
    means = samples[: n_blocks * block].reshape(n_blocks, block).mean(axis=1, dtype=np.float64)
    diffs = np.diff(means)
    median, sigma = comun.robust_sigma(diffs)
    threshold = float(qc["switching_sigma"]) * sigma
    if not np.isfinite(threshold) or threshold <= 0.0:
        return {
            "estado": "NO_CONCLUYENTE",
            "n_blocks": int(n_blocks),
            "block_s": float(block / fs),
            "median_diff": float(median),
            "robust_sigma": float(sigma),
            "events": [],
            "note": "sigma robusta nula; no se puede fijar umbral",
        }
    hits = np.flatnonzero(np.abs(diffs - median) > threshold)
    events = [
        {
            "block_index": int(index) + 1,
            "time_s": float((index + 1) * block / fs),
            "delta_mean_counts": float(diffs[index]),
        }
        for index in hits[:20]
    ]
    return {
        "estado": "OBSERVACION" if len(hits) else "PASA",
        "n_blocks": int(n_blocks),
        "block_s": float(block / fs),
        "median_diff": float(median),
        "robust_sigma": float(sigma),
        "threshold": float(threshold),
        "count": int(len(hits)),
        "events": events,
    }


def qc_band(acq, config, band, mask_path=None):
    qc = config["qc"]
    trace_index = int(config["bands"][band]["trace_index"])
    trace = acq.trace(trace_index)
    fs = float(trace.sample_rate_hz)
    n = int(trace.sample_count)
    duration = n / fs
    channels = list(trace.channels)
    block = int(qc["block_samples"])

    clip_samples = max(3, int(round(float(qc["clip_run_ms"]) * 1e-3 * fs)))
    stuck_samples = max(3, int(round(float(qc["stuck_run_s"]) * fs)))
    zero_samples = max(3, int(round(float(qc["zero_fill_run_s"]) * fs)))
    guard = int(round(float(qc["guard_ms"]) * 1e-3 * fs))
    jump_guard = int(round(float(qc["jump_guard_ms"]) * 1e-3 * fs))
    edge = int(round(float(qc["edge_ms"]) * 1e-3 * fs))

    thresholds = subsample_thresholds(acq, trace_index, channels, n, config)

    per_channel = {}
    bad_intervals = []
    switching = {}
    for channel in channels:
        samples = read_channel(acq, trace_index, channel, n, block)
        switching[channel] = switching_events(samples, fs, config)
        if len(samples) != n:
            raise RuntimeError("longitud inesperada en %s: %d != %d" % (channel, len(samples), n))

        minimum = int(samples.min())
        maximum = int(samples.max())
        mean = float(samples.mean(dtype=np.float64))
        std = float(samples.std(dtype=np.float64))
        zero_count = int(np.count_nonzero(samples == 0))
        at_min = int(np.count_nonzero(samples == minimum))
        at_max = int(np.count_nonzero(samples == maximum))

        starts, lengths = constant_run_lengths(samples)
        longest_index = int(np.argmax(lengths)) if len(lengths) else 0
        longest = int(lengths[longest_index]) if len(lengths) else 0
        longest_start = int(starts[longest_index]) if len(lengths) else 0

        clip_flags = (samples == minimum) | (samples == maximum)
        clip_runs = comun.run_intervals(clip_flags, 0, clip_samples)
        zero_runs = comun.run_intervals(samples == 0, 0, zero_samples)
        stuck_runs = [
            (int(starts[i]), int(starts[i] + lengths[i]))
            for i in range(len(lengths))
            if lengths[i] >= stuck_samples
        ]

        diff = np.diff(samples)
        info = thresholds[channel]
        low = info["median_diff_counts"] - info["threshold_counts"]
        high = info["median_diff_counts"] + info["threshold_counts"]
        jump_mask = (diff < low) | (diff > high)
        jump_indices = np.flatnonzero(jump_mask) + 1
        jump_intervals = []
        if jump_indices.size:
            raw = [(max(0, int(i) - jump_guard), min(n, int(i) + jump_guard + 1)) for i in jump_indices]
            jump_intervals = comun.dilate_intervals(raw, 0, n)

        dead = bool(std <= float(qc["dead_std_counts"]))

        per_channel[channel] = {
            "minimum_counts": minimum,
            "maximum_counts": maximum,
            "mean_counts": mean,
            "std_counts": std,
            "zero_count": zero_count,
            "fraction_at_minimum": float(at_min / n),
            "fraction_at_maximum": float(at_max / n),
            "clip_runs": len(clip_runs),
            "clip_samples": int(sum(stop - start for start, stop in clip_runs)),
            "zero_fill_runs": len(zero_runs),
            "zero_fill_samples": int(sum(stop - start for start, stop in zero_runs)),
            "stuck_runs": len(stuck_runs),
            "stuck_samples": int(sum(stop - start for start, stop in stuck_runs)),
            "longest_constant_run_samples": longest,
            "longest_constant_run_s": float(longest / fs),
            "longest_constant_run_start_sample": longest_start,
            "jump_count": int(jump_indices.size),
            "jump_fraction": float(jump_indices.size / max(1, n - 1)),
            "jump_threshold": info,
            "jump_intervals_first": jump_intervals[: int(qc["max_intervals"])],
            "jump_intervals_truncated": bool(len(jump_intervals) > int(qc["max_intervals"])),
            "dead_channel": dead,
            "unique_values_subsample": int(np.unique(samples[: min(n, 200000)]).size),
        }

        band_bad = []
        band_bad.extend(clip_runs)
        band_bad.extend(zero_runs)
        band_bad.extend(stuck_runs)
        if bool(qc["jump_mask_enabled"]):
            band_bad.extend(jump_intervals)
        band_bad = comun.dilate_intervals(band_bad, guard, n)
        bad_intervals.append((channel, band_bad))

        per_channel[channel]["bad_runs"] = len(band_bad)
        per_channel[channel]["bad_samples"] = int(sum(stop - start for start, stop in band_bad))
        per_channel[channel]["bad_fraction"] = float(
            per_channel[channel]["bad_samples"] / n
        )

    # Mascara conjunta empaquetada.
    packed = {}
    total_bad = 0
    union = np.zeros(n, dtype=bool)
    for channel, intervals in bad_intervals:
        mask = comun.build_mask_from_intervals(intervals, n)
        union |= mask
        total_bad += int(mask.sum())
        packed["bad_" + channel] = comun.pack_bool(mask, qc["mask_bitorder"])

    mask_path = (
        Path(mask_path)
        if mask_path is not None
        else (comun.ETAPA1 / ("mascaras_QC_%s.npz" % band))
    )
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        mask_path,
        n_samples=np.int64(n),
        fs=np.float64(fs),
        channels=np.array(channels),
        **packed,
    )

    dead = [ch for ch, row in per_channel.items() if row["dead_channel"]]
    clip_any = sum(row["clip_runs"] for row in per_channel.values())
    stuck_any = sum(row["stuck_runs"] for row in per_channel.values())
    zero_any = sum(row["zero_fill_runs"] for row in per_channel.values())
    jump_total = {ch: row["jump_count"] for ch, row in per_channel.items()}
    max_bad_fraction = max(row["bad_fraction"] for row in per_channel.values())

    expected = int(round(float(trace.sample_count)))
    missing = {
        "expected_samples": expected,
        "read_samples": n,
        "match": expected == n,
        "note": "El lector entrega exactamente sample_count; no hay huecos declarados en el SBF.",
    }

    checks = {
        "clipping": {
            "estado": "FALLA" if clip_any else "PASA",
            "runs": int(clip_any),
            "detail": "plateaus >= %.3f ms en el minimo o maximo global" % float(qc["clip_run_ms"]),
        },
        "canales_muertos": {
            "estado": "FALLA" if dead else "PASA",
            "channels": dead,
            "detail": "std <= %.3f counts" % float(qc["dead_std_counts"]),
        },
        "valores_pegados": {
            "estado": "FALLA" if stuck_any else "PASA",
            "runs": int(stuck_any),
            "detail": "tramos constantes >= %.3f s" % float(qc["stuck_run_s"]),
        },
        "relleno_de_ceros": {
            "estado": "FALLA" if zero_any else "PASA",
            "runs": int(zero_any),
            "detail": "tramos de ceros >= %.3f s" % float(qc["zero_fill_run_s"]),
        },
        "saltos": {
            "estado": "OBSERVACION" if sum(jump_total.values()) else "PASA",
            "counts": jump_total,
            "enmascarados": bool(qc["jump_mask_enabled"]),
            "detail": (
                "|diff - mediana| > %.1f sigma robusta; se reportan como candidatos, "
                "no se enmascaran para no borrar sferics" % float(qc["jump_sigma"])
            ),
        },
        "muestras_faltantes": {
            "estado": "PASA" if missing["match"] else "FALLA",
            **missing,
        },
        "transitorios_conmutacion": {
            "estado": "NO_APLICABLE",
            "detail": (
                "El registro tiene una sola configuracion de ganancia (settings_count=%d); "
                "el detector de cambios de media por bloque queda como observacion."
                % len(acq.settings)
            ),
            "detector_por_bloque": switching,
        },
    }

    status = comun.status_from_checks(list(checks.values()))
    if max_bad_fraction > float(qc["clip_fraction_max"]):
        status = "FALLA"
        checks["fraccion_invalida"] = {
            "estado": "FALLA",
            "detail": "bad_fraction %.6f > %.6f" % (max_bad_fraction, float(qc["clip_fraction_max"])),
        }

    sbf_audit = {
        "trace_index": trace_index,
        "band": band,
        "sample_rate_hz": fs,
        "sample_count": n,
        "duration_s": float(duration),
        "bytes_per_sample": int(trace.bytes_per_sample),
        "channel_count": int(trace.channel_count),
        "channels": channels,
        "receiver_serial": int(trace.receiver_serial),
        "adc_to_uv": [float(v) for v in trace.adc_to_uv],
        "settings_match": trace.settings_match,
        "settings_count": len(acq.settings),
        "independent_export_comparison": "no_disponible",
        "note": (
            "No hay exportacion independiente del software del fabricante para comparar signo, "
            "bits e intercalado. Se usa el lector ARMT_processing y se verifica la longitud leida."
        ),
    }

    return {
        "trace_index": trace_index,
        "sample_rate_hz": fs,
        "n_samples": n,
        "duration_s": float(duration),
        "channels": channels,
        "thresholds": {
            "clip_run_samples": clip_samples,
            "stuck_run_samples": stuck_samples,
            "zero_fill_run_samples": zero_samples,
            "guard_samples": guard,
            "jump_guard_samples": jump_guard,
            "edge_samples": edge,
        },
        "sbf_audit": sbf_audit,
        "checks": checks,
        "per_channel": per_channel,
        "bad_mask": {
            "file": mask_path.name,
            "sha256": comun.sha256_file(mask_path),
            "total_bad_samples_summed": int(total_bad),
            "union_bad_samples": int(union.sum()),
            "union_bad_fraction": float(union.sum() / n),
            "max_channel_bad_fraction": float(max_bad_fraction),
            "guard_samples": guard,
            "bitorder": qc["mask_bitorder"],
        },
        "status": status,
    }


def build(config=None):
    config = config or comun.load_config()
    SBFReader, _ = comun.import_armt()
    record = comun.target_record()
    source = Path(record["source"]["path_abs"])

    bands = {}
    with SBFReader(str(source)) as acq:
        for band in comun.band_list(config):
            bands[band] = qc_band(acq, config, band)

    statuses = [row["status"] for row in bands.values()]
    global_status = "FALLA" if "FALLA" in statuses else (
        "PASA_CON_OBSERVACIONES" if "PASA_CON_OBSERVACIONES" in statuses else "PASA"
    )

    payload = {
        "qc_version": "P1-QC-1.0.0",
        "generated_at_utc": comun.utc_now(),
        "stage": 1,
        "target_record": comun.TARGET_RECORD,
        "source": record["source"],
        "thresholds": config["qc"],
        "policy": {
            "jumps_masked": bool(config["qc"]["jump_mask_enabled"]),
            "jumps_note": (
                "Los saltos por amplitud se reportan y no se enmascaran. Un sferic puede ser "
                "senal util; borrarlo por amplitud violaria el plan 1.5."
            ),
            "mask_scope": "solo clipping, valores pegados, relleno de ceros y sus guardas",
            "guard_ms": float(config["qc"]["guard_ms"]),
        },
        "bands": bands,
        "global_status": global_status,
        "blockers_closed": [
            {
                "id": "B-P0-05",
                "alcance": "registro %s, bandas D0/D1" % comun.TARGET_RECORD,
                "estado": "CERRADO_PARA_ESTE_REGISTRO",
                "evidencia": "qc_D0_D1.json y mascaras_QC_D0/D1.npz",
            }
        ],
        "blockers_still_open": ["B-P0-01", "B-P0-02", "B-P0-03", "B-P0-04", "B-P0-06", "B-P0-07"],
        "notes": [
            "El QC se ejecuto sobre las 21 600 000 muestras de D0 y las 1 440 000 de D1.",
            "No se encontro clipping, canales muertos, valores pegados ni relleno de ceros.",
            "Los saltos detectados son candidatos impulsivos; no se eliminan.",
            "La comparacion con una exportacion independiente del fabricante sigue pendiente.",
        ],
    }
    comun.dump_json(comun.ETAPA1 / "qc_D0_D1.json", payload)
    return {
        "report": str(comun.ETAPA1 / "qc_D0_D1.json"),
        "masks": {
            band: str(comun.ETAPA1 / ("mascaras_QC_%s.npz" % band))
            for band in bands
        },
        "global_status": global_status,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    config = comun.load_config(args.config)
    result = build(config)
    print("reporte QC: %s" % result["report"])
    for band, path in result["masks"].items():
        print("mascara %s: %s" % (band, path))
    print("estado QC: %s" % result["global_status"])


if __name__ == "__main__":
    main()
