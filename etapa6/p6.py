#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Etapa 6 (P6) en la rama AMT sin TEM.

Genera:

- ``respuestas/<registro>_<banda>.npz``: Z compleja, covarianza y diagnosticos;
- ``respuestas_resumen.csv``: una fila por registro, banda y frecuencia;
- ``benchmark_control.csv``: recuperacion y cobertura sobre controles 1D;
- ``resumen_p6.json`` y ``reporte_p6.md``.

No lee TEM, no sintetiza para entrenamiento, no etiqueta y no entrena. La
respuesta de campo se calcula sin calibracion aplicada: es relativa y no se
convierte a resistividad aparente fisica.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_SOFTWARE_ROOT = Path(r"D:\ARRT_software")
sys.path.insert(0, str(ROOT / "etapa2"))
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import estimador as est  # noqa: E402
import mt1d  # noqa: E402

VERSION = "P6-1.0.0"
RESPONSE_VERSION = "P6-RESPONSE-1.0.0"
BENCH_VERSION = "P6-BENCH-1.0.0"
CSV_NEWLINE = "\n"
CSV_ENCODING = "utf-8"

RESPONSE_FIELDS = [
    "record_id", "split", "band", "frequency_hz", "estado", "motivo",
    "band_lo_hz", "band_hi_hz", "n_bins", "n_windows", "n_blocks", "k_eff",
    "gamma2_crit", "cond_hh", "eig_ratio", "coherence_xy", "coherence_yx",
    "zxx_re", "zxx_im", "zxy_re", "zxy_im", "zyx_re", "zyx_im",
    "zyy_re", "zyy_im", "abs_zxy", "phase_zxy_deg",
    "sigma_log10_abs_zxy", "sigma_phase_zxy_deg",
    "sigma_cal_log10_abs_zxy", "sigma_cal_phase_zxy_deg",
    "abs_zxx_over_zxy", "abs_zyy_over_zxy",
    "calibrado", "soporte_tem", "rama", "version",
]

BENCH_FIELDS = [
    "escenario", "modelo", "banda", "frequency_hz", "n_realizaciones",
    "n_calibracion", "n_evaluacion",
    "bias_log10", "rmse_log10", "bias_phase_deg", "rmse_phase_deg",
    "coverage_log10", "coverage_phase_deg",
    "coverage_log10_cal", "coverage_phase_deg_cal",
    "coverage_log10_grupo", "coverage_phase_deg_grupo",
    "bias_log10_ls", "rmse_log10_ls",
    "r_cal_log10", "r_cal_phase_deg",
    "flag_rate_no_identificable", "median_cond", "median_sigma_log10",
    "median_sigma_phase_deg", "criterio_grupo", "detalle", "version",
]


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def dump_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=1, ensure_ascii=False, default=_json_default)
    path.write_text(text + "\n", encoding="utf-8")


def _json_default(value):
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
    raise TypeError("tipo no serializable: %r" % (type(value),))


def write_csv(path, fields, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding=CSV_ENCODING) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator=CSV_NEWLINE,
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def g(value, sig=12):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(number):
        return "nan"
    return format(number, ".%dg" % sig)


def load_grids(cfg):
    grids = {}
    for band in ("D0", "D1"):
        rows = read_csv(ROOT / cfg["inputs"]["grid_%s" % band])
        grids[band] = np.array([float(r["frequency_hz"]) for r in rows], dtype=float)
    return grids


def band_config(cfg, band):
    local = copy.deepcopy(cfg)
    local["_band_range"] = list(cfg["bands"][band]["band_range_hz"])
    return local


def split_map():
    rows = read_csv(ROOT / "etapa0" / "splits.csv")
    key = "record_id"
    return {r[key]: r["split"] for r in rows}


def base_row(record_id, split, band, frequency_hz, spec, n_windows, n_blocks):
    return dict(
        record_id=record_id, split=split, band=band,
        frequency_hz=g(frequency_hz), estado="no_evaluado",
        motivo="resolucion_L256_fmin_%g" % float(spec["f_min_hz"]),
        band_lo_hz="", band_hi_hz="", n_bins="",
        n_windows=str(n_windows), n_blocks=str(n_blocks), k_eff="",
        gamma2_crit="", cond_hh="", eig_ratio="",
        coherence_xy="", coherence_yx="",
        zxx_re="nan", zxx_im="nan", zxy_re="nan", zxy_im="nan",
        zyx_re="nan", zyx_im="nan", zyy_re="nan", zyy_im="nan",
        abs_zxy="nan", phase_zxy_deg="nan",
        sigma_log10_abs_zxy="nan", sigma_phase_zxy_deg="nan",
        sigma_cal_log10_abs_zxy="nan", sigma_cal_phase_zxy_deg="nan",
        abs_zxx_over_zxy="nan", abs_zyy_over_zxy="nan",
        calibrado="no", soporte_tem="no_aplica", rama="AMT_sin_TEM",
        version=RESPONSE_VERSION,
    )


def response_row(record_id, split, band, row, factors=None):
    z = row["z"]
    zxy = z[0, 1]
    denom = abs(zxy) if abs(zxy) > 0 else float("nan")
    fac = (factors or {}).get(band, {})
    r_log = float(fac.get("r_log10", float("nan")))
    r_ph = float(fac.get("r_phase_deg", float("nan")))
    out = base_row(record_id, split, band, row["frequency_hz"],
                   {"f_min_hz": float("-inf")}, row["n_windows"], row["n_blocks"])
    out.update(dict(
        estado=row["estado"], motivo=row["motivo"],
        band_lo_hz=g(row["band_lo_hz"]), band_hi_hz=g(row["band_hi_hz"]),
        n_bins=str(row["n_bins"]), k_eff=str(row["k_eff"]),
        gamma2_crit=g(row["gamma2_crit"]), cond_hh=g(row["cond_hh"]),
        eig_ratio=g(row["eig_ratio"]),
        coherence_xy=g(row["coherence_xy"]), coherence_yx=g(row["coherence_yx"]),
    ))
    if row["estado"] != "estimado":
        return out
    out.update(dict(
        zxx_re=g(z[0, 0].real), zxx_im=g(z[0, 0].imag),
        zxy_re=g(z[0, 1].real), zxy_im=g(z[0, 1].imag),
        zyx_re=g(z[1, 0].real), zyx_im=g(z[1, 0].imag),
        zyy_re=g(z[1, 1].real), zyy_im=g(z[1, 1].imag),
        abs_zxy=g(abs(zxy)), phase_zxy_deg=g(np.degrees(np.angle(zxy))),
        sigma_log10_abs_zxy=g(row["sigma_log10_abs_zxy"]),
        sigma_phase_zxy_deg=g(row["sigma_phase_zxy_deg"]),
        sigma_cal_log10_abs_zxy=g(r_log * row["sigma_log10_abs_zxy"]),
        sigma_cal_phase_zxy_deg=g(r_ph * row["sigma_phase_zxy_deg"]),
        abs_zxx_over_zxy=g(abs(z[0, 0]) / denom),
        abs_zyy_over_zxy=g(abs(z[1, 1]) / denom),
    ))
    return out


def npz_payload(grid, spec, rows, record, band, fs, n_samples, seed, factors=None):
    n = grid.size
    z = np.full((n, 2, 2), np.nan + 0j, dtype=complex)
    cov = np.full((n, 8, 8), np.nan, dtype=float)
    estado = np.array(["no_evaluado"] * n, dtype=object)
    motivo = np.array(["resolucion_L256_fmin_%g" % float(spec["f_min_hz"])] * n,
                      dtype=object)
    arrays = {name: np.full(n, np.nan, dtype=float) for name in (
        "band_lo_hz", "band_hi_hz", "n_bins", "n_windows", "n_blocks", "k_eff",
        "gamma2_crit", "cond_hh", "eig_ratio", "coherence_xy", "coherence_yx",
        "sigma_log10_abs_zxy", "sigma_phase_zxy_deg",
        "sigma_cal_log10_abs_zxy", "sigma_cal_phase_zxy_deg")}
    fac = (factors or {}).get(band, {})
    r_log = float(fac.get("r_log10", 1.0))
    r_ph = float(fac.get("r_phase_deg", 1.0))
    index = {float(f): i for i, f in enumerate(grid)}
    for row in rows:
        i = index[float(row["frequency_hz"])]
        estado[i] = row["estado"]
        motivo[i] = row["motivo"]
        for name in arrays:
            if name.startswith("sigma_cal_") or name.startswith("sigma_"):
                continue
            arrays[name][i] = float(row[name])
        if row["estado"] != "estimado":
            continue
        z[i] = row["z"]
        cov[i] = row["cov"]
        arrays["sigma_log10_abs_zxy"][i] = float(row["sigma_log10_abs_zxy"])
        arrays["sigma_phase_zxy_deg"][i] = float(row["sigma_phase_zxy_deg"])
        arrays["sigma_cal_log10_abs_zxy"][i] = r_log * float(row["sigma_log10_abs_zxy"])
        arrays["sigma_cal_phase_zxy_deg"][i] = r_ph * float(row["sigma_phase_zxy_deg"])
    meta = dict(
        respuesta_version=RESPONSE_VERSION, estimador_version=est.VERSION,
        config_version=CONFIG_VERSION, record_id=record["record_id"],
        split=(record["split"].get("split") if isinstance(record["split"], dict)
               else record["split"]), band=band, sample_rate_hz=fs,
        n_samples=int(n_samples), calibrado=False, soporte_tem="no_aplica",
        rama="AMT_sin_TEM", seed_bootstrap=int(seed),
        r_cal_log10=r_log, r_cal_phase_deg=r_ph,
        convencion="exp(+i*omega*t); Z_hat = S_EH S_HH^-1",
        nota=("Respuesta relativa sin calibracion: no es rho_a fisica. "
              "El cociente E/H usa uV del ADC en ambos canales. "
              "sigma_cal aplica el factor r calibrado en controles; no cubre "
              "error de calibracion ni de modelo."),
    )
    payload = dict(frequency_hz=grid, z=z, cov=cov, estado=estado,
                   motivo=motivo, meta=np.array(json.dumps(meta, ensure_ascii=False)))
    payload.update(arrays)
    return payload, meta


def estimate_record(acq, record, band, grid, cfg, seed, factors=None):
    spec = cfg["bands"][band]
    split = record["split"]
    if isinstance(split, dict):
        split = split.get("split")
    trace_index = int(spec["trace_index"])
    trace = acq.trace(trace_index)
    n_samples = int(trace.sample_count)
    fs = float(trace.sample_rate_hz)
    fmin = float(spec["f_min_hz"])
    fmax = float(spec["f_max_hz"])
    local = band_config(cfg, band)
    n_window = int(local["estimator"]["window_samples"])
    step = max(1, int(round(n_window * (1.0 - float(local["estimator"]["overlap_fraction"])))))
    n_windows = n_samples // step
    n_blocks = int(math.ceil(n_samples / float(step) /
                            max(1, int(round(float(local["bootstrap"]["block_seconds"]) * fs / step)))))

    estimable = (grid >= fmin) & (grid <= fmax)
    freqs = grid[estimable]
    bins = [est.band_bins(f, fs, n_window,
                          float(local["estimator"]["band_half_width_rel"]),
                          local["_band_range"]) for f in freqs]

    def read(start, stop):
        return acq.read_samples(trace_index, start=int(start),
                                stop=int(min(stop, n_samples)),
                                channels=list(est.CHANNELS), units="uV")

    started = time.time()
    result = est.estimate(read, n_samples, fs, freqs, local, bins=bins, seed=seed)
    rows = []
    by_freq = {float(r["frequency_hz"]): r for r in result["rows"]}
    for f in grid:
        if fmin <= float(f) <= fmax:
            rows.append(response_row(record["record_id"], split, band,
                                     by_freq[float(f)], factors))
        else:
            rows.append(base_row(record["record_id"], split, band, float(f),
                                 spec, n_windows, n_blocks))
    payload, meta = npz_payload(grid, spec, result["rows"], record, band, fs,
                                n_samples, seed, factors)
    meta["elapsed_s"] = float(time.time() - started)
    return rows, payload, meta


def real_responses(cfg, grids, only=None, factors=None):
    sys.path.insert(0, str(DEFAULT_SOFTWARE_ROOT / "ARMT_processing"))
    from armt import SBFReader

    manifest = load_json(ROOT / cfg["inputs"]["manifest"])
    records = manifest["armt_records"]
    if only:
        records = [r for r in records if r["record_id"] in set(only)]
    responses_dir = HERE / cfg["outputs"]["responses_dir"]
    responses_dir.mkdir(parents=True, exist_ok=True)
    all_rows = []
    metas = []
    for index, record in enumerate(records):
        source = Path(record["source"]["path_abs"])
        with SBFReader(str(source)) as acq:
            for band in ("D0", "D1"):
                seed = int(cfg["bootstrap"]["seed"]) + 100000 * index + (0 if band == "D0" else 1)
                rows, payload, meta = estimate_record(acq, record, band, grids[band],
                                                      cfg, seed, factors)
                np.savez_compressed(responses_dir / ("%s_%s.npz" % (record["record_id"], band)),
                                    **payload)
                all_rows.extend(rows)
                metas.append(meta)
                print("[P6] %s %s: %d filas, %.1f s" % (record["record_id"], band,
                                                        len(rows), meta["elapsed_s"]),
                      flush=True)
    write_csv(HERE / cfg["outputs"]["responses_csv"], RESPONSE_FIELDS, all_rows)
    return all_rows, metas


def _design(cfg):
    scenarios = list(cfg["controls"]["scenarios"])
    models = list(cfg["controls"]["models"])
    design = [(name, "semiespacio_100") for name in scenarios]
    for model in models:
        if model != "semiespacio_100":
            design.append(("limpio", model))
    return design


def _offset(text):
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little")


def _run_group(cfg, scenario, model, band, realizations, freqs, rho, interfaces):
    """Corre un grupo (escenario, modelo, banda) y devuelve arreglos por realización."""
    controls = cfg["controls"]
    params = controls["scenarios"][scenario]
    fs = float(cfg["bands"][band]["sample_rate_hz"])
    n_samples = int(round(fs * float(controls["duration_%s_s" % band])))
    local = band_config(cfg, band)
    band_range = controls["band_%s_hz" % band]
    nf = freqs.size
    err = np.full((realizations, nf), np.nan)
    sig = np.full((realizations, nf), np.nan)
    pherr = np.full((realizations, nf), np.nan)
    phsig = np.full((realizations, nf), np.nan)
    err_ls = np.full((realizations, nf), np.nan)
    flag = np.full((realizations, nf), np.nan)
    cond = np.full((realizations, nf), np.nan)
    for rep in range(realizations):
        seed = (int(controls["seed"]) + 1000003 * rep
                + _offset(scenario + "|" + model + "|" + band))
        syn = est.synthesize(fs, n_samples, rho, interfaces,
                             tuple(band_range), seed,
                             snr_db=params["snr_db"],
                             noise_target=params["noise_target"],
                             coherent_rel=float(params["coherente_rel"]),
                             outliers=float(params["outliers"]),
                             rango_uno=bool(params["rango_uno"]))
        series = np.column_stack([syn["e"], syn["h"],
                                  np.zeros(n_samples, dtype=float)])

        def read(start, stop, series=series):
            return series[int(start):int(stop)]

        result = est.estimate(read, n_samples, fs, freqs, local, seed=seed)
        for index, row in enumerate(result["rows"]):
            f_bins = (np.asarray(row["bins"], dtype=float) * fs
                      / float(local["estimator"]["window_samples"]))
            z_ref = complex(np.mean(mt1d.z1d(f_bins, rho, interfaces)))
            z = row["z"][0, 1]
            z_ls = row["z_ls"][0, 1]
            err[rep, index] = float(np.log10(abs(z) / abs(z_ref)))
            err_ls[rep, index] = float(np.log10(abs(z_ls) / abs(z_ref)))
            pherr[rep, index] = float(np.degrees(np.angle(z / z_ref)))
            sig[rep, index] = float(row["sigma_log10_abs_zxy"])
            phsig[rep, index] = float(row["sigma_phase_zxy_deg"])
            flag[rep, index] = float(row["estado"] != "estimado")
            cond[rep, index] = float(row["cond_hh"])
    print("[P6] control %-16s %-14s %s listo" % (scenario, model, band), flush=True)
    return dict(err=err, err_ls=err_ls, pherr=pherr, sig=sig, phsig=phsig,
                flag=flag, cond=cond, freqs=freqs)


def _calibration_factors(store, bands, n_cal):
    """Factor de calibración r = RMS(error) / RMS(sigma bootstrap).

    Se estima en la mitad de calibración del control limpio (semiespacio) y no
    interviene en la mitad de evaluación, que es la que decide la cobertura.
    """
    factors = {}
    for band in bands:
        item = store[("limpio", "semiespacio_100", band)]
        cal = slice(0, n_cal)
        r_log = float(np.sqrt(np.mean(item["err"][cal] ** 2))
                      / np.sqrt(np.mean(item["sig"][cal] ** 2)))
        r_ph = float(np.sqrt(np.mean(item["pherr"][cal] ** 2))
                     / np.sqrt(np.mean(item["phsig"][cal] ** 2)))
        factors[band] = dict(r_log10=r_log, r_phase_deg=r_ph)
    return factors


def benchmark(cfg, grids):
    controls = cfg["controls"]
    realizations = int(controls["realizations"])
    n_cal = max(2, min(int(controls.get("calibration_realizations", realizations // 2)),
                       realizations // 2))
    design = _design(cfg)
    bands = ("D0", "D1")
    store = {}
    for scenario, model in design:
        model_spec = controls["models"][model]
        rho = [float(v) for v in model_spec["rho"]]
        interfaces = [float(v) for v in model_spec["interfaces_m"]]
        for band in bands:
            freqs = np.array(controls["frequencies_%s_hz" % band], dtype=float)
            store[(scenario, model, band)] = _run_group(
                cfg, scenario, model, band, realizations, freqs, rho, interfaces)

    factors = _calibration_factors(store, bands, n_cal)
    rows = []
    for (scenario, model, band), item in store.items():
        freqs = item["freqs"]
        cal = slice(0, n_cal)
        ev = slice(n_cal, realizations)
        r_log = factors[band]["r_log10"]
        r_ph = factors[band]["r_phase_deg"]
        group_log = float(np.mean(np.abs(item["err"][ev]) <= r_log * item["sig"][ev]))
        group_ph = float(np.mean(np.abs(item["pherr"][ev]) <= r_ph * item["phsig"][ev]))
        for index, f in enumerate(freqs):
            err = item["err"][:, index]
            err_ls = item["err_ls"][:, index]
            phase = item["pherr"][:, index]
            sig = item["sig"][:, index]
            phsig = item["phsig"][:, index]
            cover = float(np.mean(np.abs(err[ev]) <= sig[ev]))
            cover_ph = float(np.mean(np.abs(phase[ev]) <= phsig[ev]))
            cover_cal = float(np.mean(np.abs(err[ev]) <= r_log * sig[ev]))
            cover_ph_cal = float(np.mean(np.abs(phase[ev]) <= r_ph * phsig[ev]))
            rows.append(dict(
                escenario=scenario, modelo=model, banda=band,
                frequency_hz=g(f, 10), n_realizaciones=str(realizations),
                n_calibracion=str(n_cal), n_evaluacion=str(realizations - n_cal),
                bias_log10=g(np.median(err)), rmse_log10=g(np.sqrt(np.mean(err ** 2))),
                bias_phase_deg=g(np.median(phase)),
                rmse_phase_deg=g(np.sqrt(np.mean(phase ** 2))),
                coverage_log10=g(cover), coverage_phase_deg=g(cover_ph),
                coverage_log10_cal=g(cover_cal), coverage_phase_deg_cal=g(cover_ph_cal),
                coverage_log10_grupo=g(group_log), coverage_phase_deg_grupo=g(group_ph),
                bias_log10_ls=g(np.median(err_ls)),
                rmse_log10_ls=g(np.sqrt(np.mean(err_ls ** 2))),
                r_cal_log10=g(r_log), r_cal_phase_deg=g(r_ph),
                flag_rate_no_identificable=g(np.mean(item["flag"][:, index])),
                median_cond=g(np.median(item["cond"][:, index])),
                median_sigma_log10=g(np.median(sig)),
                median_sigma_phase_deg=g(np.median(phsig)),
                criterio_grupo="", detalle="", version=BENCH_VERSION,
            ))
    _apply_criteria(rows, cfg)
    write_csv(HERE / cfg["outputs"]["benchmark_csv"], BENCH_FIELDS, rows)
    calibration = dict(
        artifact="calibracion_p6", version=VERSION,
        metodo="r = RMS(error) / RMS(sigma bootstrap) en la mitad de calibracion",
        controles="limpio/semiespacio_100",
        n_calibracion=n_cal, n_evaluacion=realizations - n_cal,
        factors=factors,
        nota=("El factor corrige la subcobertura del bootstrap temporal, que no "
              "captura el error sistematico de ventana y ancho de banda. No cubre "
              "error de calibracion ni de modelo."),
    )
    dump_json(HERE / cfg["outputs"]["calibration"], calibration)
    return rows, factors


def _apply_criteria(rows, cfg):
    """Criterio por escenario: la cobertura se agrega, no se toma el mínimo."""
    tol = cfg["tolerances"]
    groups = {}
    for row in rows:
        groups.setdefault((row["escenario"], row["modelo"]), []).append(row)
    for (scenario, model), items in groups.items():
        bias = max(abs(float(r["bias_log10"])) for r in items)
        bias_ph = max(abs(float(r["bias_phase_deg"])) for r in items)
        cover = float(items[0]["coverage_log10_grupo"])
        cover_ph = float(items[0]["coverage_phase_deg_grupo"])
        flag = max(float(r["flag_rate_no_identificable"]) for r in items)
        rmse = max(float(r["rmse_log10"]) for r in items)
        rmse_ls = max(float(r["rmse_log10_ls"]) for r in items)
        inside = (tol["coverage_min"] <= cover <= tol["coverage_max"]
                  and tol["coverage_min"] <= cover_ph <= tol["coverage_max"])
        if scenario == "limpio" and model == "semiespacio_100":
            ok = (bias <= tol["limpio_bias_log10"]
                  and bias_ph <= tol["limpio_bias_phase_deg"] and inside)
            detail = ("bias=%.4f dec, fase=%.3f deg, cobertura calibrada="
                      "%.2f/%.2f (evaluacion independiente)" % (bias, bias_ph, cover, cover_ph))
        elif scenario == "ruido_E":
            ok = (bias <= tol["ruido_bias_log10"]
                  and bias_ph <= tol["ruido_bias_phase_deg"] and inside)
            detail = ("bias=%.4f dec, fase=%.3f deg, cobertura calibrada="
                      "%.2f/%.2f" % (bias, bias_ph, cover, cover_ph))
        elif scenario == "outliers":
            ok = (bias <= tol["outliers_bias_log10"] and rmse <= 1.05 * rmse_ls)
            detail = "bias=%.4f dec, rmse robusto=%.4f vs LS=%.4f" % (bias, rmse, rmse_ls)
        elif scenario == "rango_uno":
            ok = flag >= tol["rango_uno_flag_min"]
            detail = "fraccion marcada no_identificable=%.2f" % flag
        elif scenario == "ruido_H":
            ok = None
            detail = ("sin referencia remota: el ruido en H sesga Z; "
                      "bias=%.4f dec, cobertura=%.2f" % (bias, cover))
        elif scenario == "ruido_coherente":
            ok = None
            detail = ("coherencia no es identidad; bias=%.4f dec, fase=%.3f deg" % (
                bias, bias_ph))
        else:
            ok = None
            detail = "modelo estratificado: bias de banda=%.4f dec" % bias
        label = "PASA" if ok is True else ("FALLA" if ok is False else "OBSERVACION")
        for row in items:
            row["criterio_grupo"] = label
            row["detalle"] = detail


def summarize(cfg, grids, real_rows, metas, bench_rows, factors=None):
    states = {}
    for row in real_rows:
        states[row["estado"]] = states.get(row["estado"], 0) + 1
    per_band = {}
    for band in ("D0", "D1"):
        items = [r for r in real_rows if r["band"] == band]
        per_band[band] = dict(
            filas=len(items),
            estimado=sum(1 for r in items if r["estado"] == "estimado"),
            no_evaluado=sum(1 for r in items if r["estado"] == "no_evaluado"),
            no_identificable=sum(1 for r in items if r["estado"] == "no_identificable"),
            senal_insuficiente=sum(1 for r in items if r["estado"] == "senal_insuficiente"),
            frecuencia_min_estimada_hz=min(
                [float(r["frequency_hz"]) for r in items if r["estado"] == "estimado"] or [None]),
            frecuencia_max_estimada_hz=max(
                [float(r["frequency_hz"]) for r in items if r["estado"] == "estimado"] or [None]),
        )
    crit = {}
    for row in bench_rows:
        key = "%s/%s" % (row["escenario"], row["modelo"])
        crit[key] = row["criterio_grupo"]
    sig = [float(r["sigma_log10_abs_zxy"]) for r in real_rows
           if r["estado"] == "estimado" and np.isfinite(float(r["sigma_log10_abs_zxy"]))]
    coh = [float(r["coherence_xy"]) for r in real_rows
           if r["estado"] == "estimado" and np.isfinite(float(r["coherence_xy"]))]

    def pooled(scenario, model):
        items = [r for r in bench_rows
                 if r["escenario"] == scenario and r["modelo"] == model]
        if not items:
            return None
        return dict(log10=float(items[0]["coverage_log10_grupo"]),
                    phase_deg=float(items[0]["coverage_phase_deg_grupo"]),
                    bootstrap_log10=float(np.mean(
                        [float(r["coverage_log10"]) for r in items])))

    summary = dict(
        artifact="resumen_p6", version=VERSION, gate="P6",
        estado_puerta="PARCIAL",
        rama="AMT_sin_TEM",
        generated_at_utc=utc_now(),
        scope=cfg["scope"],
        records=len({r["record_id"] for r in real_rows}),
        responses=len(real_rows),
        states=states,
        per_band=per_band,
        benchmark=crit,
        calibration=dict(
            factors=factors or {},
            source="calibracion_p6.json",
            n_calibracion=int(next((r["n_calibracion"] for r in bench_rows), 0)),
            coverage_limpio=pooled("limpio", "semiespacio_100"),
            nota=("r corrige la subcobertura del bootstrap temporal. La cobertura se "
                  "mide en la mitad de evaluacion, independiente de la calibracion."),
        ),
        real_diagnostics=dict(
            sigma_log10_median=float(np.median(sig)) if sig else None,
            sigma_log10_max=float(np.max(sig)) if sig else None,
            sigma_cal_log10_median=float(np.median(
                [float(r["sigma_cal_log10_abs_zxy"]) for r in real_rows
                 if r["estado"] == "estimado"
                 and r.get("sigma_cal_log10_abs_zxy")
                 and np.isfinite(float(r["sigma_cal_log10_abs_zxy"]))] or [np.nan]))
            if sig else None,
            coherence_xy_median=float(np.median(coh)) if coh else None,
            coherence_xy_min=float(np.min(coh)) if coh else None,
        ),
        limits=[
            "Sin calibracion aplicada: Z es relativa y no se convierte a rho_a.",
            "Sin referencia remota: el ruido en H no es corregible.",
            "D0 por debajo de 125 Hz queda no_evaluado con L=256 (N_c=8).",
            "La compuerta de coherencia descarta las frecuencias sin correlacion Ex-Hy: una respuesta bajo el critico no se publica.",
            "La cobertura de frecuencias es instrumental; F_red_validada por familia de ruido sigue pendiente (B-P0-06).",
            "El factor r de incertidumbre se calibra en controles 1D: no cubre error de calibracion ni de modelo en campo.",
            "P3-P5 y P7 siguen cerradas: no hay sintesis guiada por TEM, etiquetas ni entrenamiento.",
        ],
        conclusion=("P6 se cierra como PARCIAL en la rama AMT sin TEM: el estimador recupera "
                    "la verdad en controles identificables, rechaza el rango uno y produce "
                    "respuestas relativas con covarianza; no habilita la rama neuronal."),
        metas={
            "p6_estimador_control": "ver benchmark_control.csv",
            "p6_respuesta_covarianza": "respuestas/*.npz y respuestas_resumen.csv",
        },
    )
    dump_json(HERE / cfg["outputs"]["summary"], summary)
    return summary


def report(cfg, summary, metas, bench_rows, real_rows):
    lines = []
    lines.append("# P6 — Estimador de referencia e incertidumbre (rama AMT sin TEM)")
    lines.append("")
    lines.append("Versión `%s`; generado %s." % (VERSION, utc_now()))
    lines.append("")
    lines.append("## Alcance")
    lines.append("")
    lines.append("La rama sin TEM mantiene cerradas P3–P5 y P7: no hay síntesis guiada "
                 "por TEM, ni etiquetas, ni entrenamiento. Esta etapa implementa el "
                 "estimador de referencia que el plan §10 permite ejecutar en paralelo "
                 "desde P1, incluso fuera del soporte TEM.")
    lines.append("")
    lines.append("## Respuestas reales")
    lines.append("")
    lines.append("| Banda | Filas | Estimadas | No evaluadas | No identificables | Sin señal | Rango estimado |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    for band, item in summary["per_band"].items():
        span = "%s–%s Hz" % (g(item["frecuencia_min_estimada_hz"], 6),
                             g(item["frecuencia_max_estimada_hz"], 6))
        lines.append("| %s | %d | %d | %d | %d | %d | %s |" % (
            band, item["filas"], item["estimado"], item["no_evaluado"],
            item["no_identificable"], item["senal_insuficiente"], span))
    lines.append("")
    diag = summary["real_diagnostics"]
    lines.append("Mediana de σ(log10|Zxy|) de las filas estimadas = %s; mediana de "
                 "coherencia γ²(Ex–Hy) de las filas estimadas = %s." % (
                     g(diag["sigma_log10_median"], 4), g(diag["coherence_xy_median"], 4)))
    lines.append("")
    lines.append("**Compuerta de coherencia.** Una frecuencia solo se publica como "
                 "`estimado` si γ²(Ex–Hy) supera el valor crítico de ruido "
                 "γ²_crit = 1 − α^(1/(k_eff−1)) con α = 0,05. Bajo ese umbral la "
                 "estimación está dominada por ruido incoherente y se marca "
                 "`senal_insuficiente`. La coherencia se mide sobre el espectro "
                 "apilado y es invariante a un desfase constante, de modo que un "
                 "retardo fijo no la reduce: un valor bajo implica ruido "
                 "independiente o desfase variable, no un simple desalineamiento.")
    lines.append("")
    lines.append("Las respuestas se guardan sin calibración aplicada. El cociente E/H usa "
                 "µV del ADC en ambos canales: es una respuesta relativa y **no** una "
                 "resistividad aparente física.")
    lines.append("")
    lines.append("## Controles 1D")
    lines.append("")
    lines.append("| Escenario | Modelo | Criterio | Detalle |")
    lines.append("|---|---|---|---|")
    seen = set()
    for row in bench_rows:
        key = (row["escenario"], row["modelo"])
        if key in seen:
            continue
        seen.add(key)
        lines.append("| %s | %s | %s | %s |" % (row["escenario"], row["modelo"],
                                                row["criterio_grupo"], row["detalle"]))
    lines.append("")
    lines.append("## Incertidumbre")
    lines.append("")
    cal = summary.get("calibration") or {}
    factors = cal.get("factors") or {}
    lines.append("El bootstrap por bloques mide la variabilidad temporal del estimador, "
                 "pero no el error sistemático de ventana y ancho de banda. Sobre el "
                 "control limpio, la cobertura del bootstrap solo es ≈0,6. Se calibra "
                 "un factor `r = RMS(error) / RMS(σ_bootstrap)` en la mitad de "
                 "calibración y la cobertura se mide en la mitad de evaluación, "
                 "independiente.")
    lines.append("")
    lines.append("| Banda | r(σ log10) | r(σ fase) |")
    lines.append("|---|---:|---:|")
    for band, item in factors.items():
        lines.append("| %s | %s | %s |" % (band, g(item.get("r_log10"), 4),
                                          g(item.get("r_phase_deg"), 4)))
    lines.append("")
    cover = cal.get("coverage_limpio") or {}
    if cover:
        lines.append("Cobertura del control limpio en evaluación: log10 %s, fase %s "
                     "(bootstrap solo: %s)." % (
                         g(cover.get("log10"), 3), g(cover.get("phase_deg"), 3),
                         g(cover.get("bootstrap_log10"), 3)))
        lines.append("")
    lines.append("En las respuestas de campo, `sigma_log10_abs_zxy` es la incertidumbre "
                 "estadística condicional del bootstrap y `sigma_cal_log10_abs_zxy` la "
                 "incertidumbre con el factor calibrado. Ninguna de las dos cubre el "
                 "error de calibración (B-P0-04) ni el de modelo.")
    lines.append("")
    lines.append("## Límites")
    lines.append("")
    for item in summary["limits"]:
        lines.append("- " + item)
    lines.append("")
    lines.append("## Conclusión")
    lines.append("")
    lines.append(summary["conclusion"])
    lines.append("")
    lines.append("P6 queda **PARCIAL**: el estimador y la covarianza están implementados y "
                 "validados en controles, pero la calibración (B-P0-04), la familia de ruido "
                 "(B-P0-06) y la referencia remota siguen abiertas. No se habilita síntesis, "
                 "etiquetado ni entrenamiento.")
    lines.append("")
    (HERE / cfg["outputs"]["report"]).write_text("\n".join(lines), encoding="utf-8")


CONFIG_VERSION = ""


def main(argv=None):
    global CONFIG_VERSION
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("all", "real", "controls"), default="all")
    parser.add_argument("--records", nargs="*", default=None,
                        help="subconjunto de record_id para pruebas")
    parser.add_argument("--realizations", type=int, default=None,
                        help="sobreescribe controls.realizations para pruebas")
    args = parser.parse_args(argv)

    cfg = load_json(HERE / "config_p6.json")
    if args.realizations:
        cfg["controls"]["realizations"] = int(args.realizations)
    CONFIG_VERSION = cfg["version"]
    grids = load_grids(cfg)

    real_rows, metas, bench_rows, factors = [], [], [], {}
    if args.mode in ("all", "controls"):
        started = time.time()
        bench_rows, factors = benchmark(cfg, grids)
        print("[P6] controles en %.1f s" % (time.time() - started), flush=True)
    else:
        path = HERE / cfg["outputs"]["benchmark_csv"]
        bench_rows = read_csv(path) if path.exists() else []
        cal_path = HERE / cfg["outputs"]["calibration"]
        if cal_path.exists():
            factors = load_json(cal_path)["factors"]

    if args.mode in ("all", "real"):
        started = time.time()
        real_rows, metas = real_responses(cfg, grids, only=args.records,
                                          factors=factors)
        print("[P6] respuestas reales en %.1f s" % (time.time() - started), flush=True)
    else:
        path = HERE / cfg["outputs"]["responses_csv"]
        real_rows = read_csv(path) if path.exists() else []

    if args.mode == "all" or (real_rows and bench_rows):
        summary = summarize(cfg, grids, real_rows, metas, bench_rows, factors)
        report(cfg, summary, metas, bench_rows, real_rows)
        summary["software"] = {
            "p6": {"path": "etapa6/p6.py", "sha256": sha256_file(Path(__file__))},
            "estimador": {"path": "etapa6/estimador.py",
                          "version": est.VERSION,
                          "sha256": sha256_file(HERE / "estimador.py")},
            "mt1d": {"path": "etapa2/mt1d.py", "version": mt1d.VERSION,
                     "sha256": sha256_file(ROOT / "etapa2" / "mt1d.py")},
        }
        summary["files"] = sorted(
            p.name for p in HERE.glob("*") if p.is_file() and p.suffix in (".csv", ".json", ".md")
        ) + sorted(p.name for p in (HERE / cfg["outputs"]["responses_dir"]).glob("*.npz"))
        dump_json(HERE / cfg["outputs"]["summary"], summary)
        print(json.dumps(dict(estado=summary["estado_puerta"], states=summary["states"],
                              benchmark=summary["benchmark"]), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
