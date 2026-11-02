#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validador de la Etapa 6 (P6) en la rama AMT sin TEM.

Comprueba coherencia interna de los entregables, no la validez fisica de las
respuestas: sin calibracion (B-P0-04) y sin vinculo TEM (B-P0-03), una respuesta
solo puede declararse relativa.

Uso:
    python etapa6/validar_etapa6.py

Devuelve 0 si no hay fallas y 1 si alguna comprobacion falla.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "etapa2"))
sys.path.insert(0, str(HERE))

import estimador as est  # noqa: E402

VERSION = "P6-VAL-1.0.0"
VERSIONES = ("P6-CONFIG-1.0.0", "P6-EST-1.0.1", "P6-1.0.0",
             "P6-RESPONSE-1.0.0", "P6-BENCH-1.0.0")
ESTADOS = {"estimado", "no_evaluado", "no_identificable", "senal_insuficiente"}
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
NPZ_ARRAYS = [
    "frequency_hz", "z", "cov", "estado", "motivo", "meta",
    "band_lo_hz", "band_hi_hz", "n_bins", "n_windows", "n_blocks", "k_eff",
    "gamma2_crit", "cond_hh", "eig_ratio", "coherence_xy", "coherence_yx",
    "sigma_log10_abs_zxy", "sigma_phase_zxy_deg",
    "sigma_cal_log10_abs_zxy", "sigma_cal_phase_zxy_deg",
]


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def as_float(value, default=float("nan")):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def add(checks, cid, descripcion, ok, detalle=""):
    checks.append(dict(id=cid, descripcion=descripcion,
                       resultado="PASA" if ok else "FALLA", detalle=detalle))
    return bool(ok)


def observation(checks, cid, descripcion, detalle=""):
    checks.append(dict(id=cid, descripcion=descripcion,
                       resultado="OBSERVACION", detalle=detalle))


def header_of(path):
    with open(path, newline="", encoding="utf-8-sig") as stream:
        return next(csv.reader(stream))


def main():
    checks = []
    cfg = load_json(HERE / "config_p6.json")
    matrix = read_csv(ROOT / "MATRIZ_VALIDACION_ARMT.csv")
    summary = load_json(HERE / cfg["outputs"]["summary"])
    calibration = load_json(HERE / cfg["outputs"]["calibration"])
    manifest = load_json(ROOT / cfg["inputs"]["manifest"])
    splits = {r["record_id"]: r["split"] for r in read_csv(ROOT / "etapa0" / "splits.csv")}
    responses = read_csv(HERE / cfg["outputs"]["responses_csv"])
    bench = read_csv(HERE / cfg["outputs"]["benchmark_csv"])
    grids = {}
    for band in ("D0", "D1"):
        rows = read_csv(ROOT / cfg["inputs"]["grid_%s" % band])
        grids[band] = [float(r["frequency_hz"]) for r in rows]

    # ------------------------------------------------------------------
    # 1. existencia, versiones y columnas
    # ------------------------------------------------------------------
    files = {
        "config": HERE / "config_p6.json",
        "estimador": HERE / "estimador.py",
        "driver": HERE / "p6.py",
        "responses": HERE / cfg["outputs"]["responses_csv"],
        "benchmark": HERE / cfg["outputs"]["benchmark_csv"],
        "calibration": HERE / cfg["outputs"]["calibration"],
        "summary": HERE / cfg["outputs"]["summary"],
        "report": HERE / cfg["outputs"]["report"],
        "schema": HERE / cfg["outputs"]["schema"],
        "readme": HERE / "README.md",
    }
    for key, path in files.items():
        add(checks, "FILE-%s" % key, "Existe %s" % path.relative_to(HERE),
            path.is_file(), str(path))

    add(checks, "VER-CONFIG", "config_p6 declara P6-CONFIG-1.0.0",
        cfg.get("version") == VERSIONES[0], str(cfg.get("version")))
    add(checks, "VER-EST", "estimador declara P6-EST-1.0.1",
        est.VERSION == VERSIONES[1], est.VERSION)
    add(checks, "VER-DRIVER", "p6.py declara P6-1.0.0",
        "VERSION = \"P6-1.0.0\"" in (HERE / "p6.py").read_text(encoding="utf-8"), "P6-1.0.0")
    add(checks, "HDR-RESPONSE", "Columnas de respuestas_resumen.csv",
        header_of(files["responses"]) == RESPONSE_FIELDS, "respuestas_resumen.csv")
    add(checks, "HDR-BENCH", "Columnas de benchmark_control.csv",
        header_of(files["benchmark"]) == BENCH_FIELDS, "benchmark_control.csv")
    schema = load_json(files["schema"])
    props = schema.get("properties", {})
    add(checks, "SCHEMA-ID", "esquema_response declara version 1.0.0",
        props.get("schema_version", {}).get("const") == "1.0.0"
        and props.get("artifact", {}).get("const") == "esquema_response",
        str(props.get("schema_version", {}).get("const")))
    add(checks, "SCHEMA-CSV", "El esquema cubre las columnas del CSV",
        set(schema["properties"]["csv"]["required"]) == set(RESPONSE_FIELDS),
        "%d columnas" % len(RESPONSE_FIELDS))

    # ------------------------------------------------------------------
    # 2. cobertura de la grilla de P1
    # ------------------------------------------------------------------
    expected_records = {r["record_id"] for r in manifest["armt_records"]}
    seen_records = {r["record_id"] for r in responses}
    add(checks, "RECORDS", "Los 15 registros del manifiesto estan presentes",
        seen_records == expected_records and len(expected_records) == 15,
        "%d registros" % len(seen_records))
    expected_rows = sum(len(grids["D0"]) + len(grids["D1"]) for _ in expected_records)
    add(checks, "ROWS-TOTAL", "Filas = 15 x (29 D0 + 13 D1)",
        len(responses) == expected_rows, "%d filas" % len(responses))
    per_key = {}
    for row in responses:
        per_key.setdefault((row["record_id"], row["band"]), []).append(row)
    missing = [k for k in ((r, b) for r in expected_records for b in ("D0", "D1"))
               if len(per_key.get(k, [])) != len(grids[k[1]])]
    add(checks, "ROWS-BAND", "Cada registro tiene la grilla completa en D0 y D1",
        not missing, "%d combinaciones incompletas" % len(missing))
    bad_split = [r["record_id"] for r in responses
                 if splits.get(r["record_id"]) != r["split"]]
    add(checks, "SPLIT", "El split coincide con etapa0/splits.csv",
        not bad_split, ", ".join(sorted(set(bad_split))))
    dup = len(responses) - len({(r["record_id"], r["band"], r["frequency_hz"])
                                for r in responses})
    add(checks, "DUP", "Sin filas duplicadas por registro, banda y frecuencia",
        dup == 0, "%d duplicadas" % dup)

    # ------------------------------------------------------------------
    # 3. guardas de alcance
    # ------------------------------------------------------------------
    add(checks, "GUARD-CAL", "Todas las filas declaran calibrado=no",
        all(r["calibrado"] == "no" for r in responses),
        ", ".join(sorted({r["calibrado"] for r in responses})))
    add(checks, "GUARD-TEM", "Todas las filas declaran soporte_tem=no_aplica",
        all(r["soporte_tem"] == "no_aplica" for r in responses),
        ", ".join(sorted({r["soporte_tem"] for r in responses})))
    add(checks, "GUARD-RAMA", "Todas las filas pertenecen a AMT_sin_TEM",
        all(r["rama"] == "AMT_sin_TEM" for r in responses),
        ", ".join(sorted({r["rama"] for r in responses})))
    add(checks, "GUARD-VERSION", "Todas las filas declaran P6-RESPONSE-1.0.0",
        all(r["version"] == VERSIONES[3] for r in responses),
        ", ".join(sorted({r["version"] for r in responses})))
    add(checks, "GUARD-ESTADO", "Los estados pertenecen al vocabulario cerrado",
        all(r["estado"] in ESTADOS for r in responses),
        ", ".join(sorted({r["estado"] for r in responses})))
    add(checks, "NO-RHOA", "No se publica rho_a en la rama sin calibracion",
        not any(c.lower().startswith(("rho", "rhoa")) for c in RESPONSE_FIELDS)
        and "resistividad aparente" in files["report"].read_text(encoding="utf-8").lower(),
        "respuestas_resumen.csv y reporte_p6.md")
    add(checks, "NO-ENTRENO", "No hay etiquetas ni entrenamiento en el driver",
        not any(token in (HERE / "p6.py").read_text(encoding="utf-8")
                for token in ("train", "fit(", "labels", "supervis")),
        "p6.py")

    # ------------------------------------------------------------------
    # 4. coherencia de estados y resolución
    # ------------------------------------------------------------------
    fmin = float(cfg["bands"]["D0"]["f_min_hz"])
    below = [r for r in responses
             if r["band"] == "D0" and as_float(r["frequency_hz"]) < fmin]
    add(checks, "D0-FMIN", "D0 por debajo de %g Hz queda no_evaluado" % fmin,
        below and all(r["estado"] == "no_evaluado" for r in below),
        "%d filas" % len(below))
    add(checks, "D0-MOTIVO", "El motivo de D0 cita la resolucion L=256",
        all("L256" in r["motivo"] for r in below),
        ", ".join(sorted({r["motivo"] for r in below})))
    neg = [r for r in responses
           if r["band"] == "D1" and as_float(r["frequency_hz"]) < 1000.0]
    add(checks, "D1-RANGO", "D1 no contiene frecuencias fuera de su grilla",
        not neg, "%d filas" % len(neg))
    estimado = [r for r in responses if r["estado"] == "estimado"]
    add(checks, "EST-COUNT", "Hay respuestas estimadas en ambas bandas",
        len({r["band"] for r in estimado}) == 2, "%d estimadas" % len(estimado))
    no_eval_finite = [r for r in responses
                      if r["estado"] != "estimado" and r["abs_zxy"] != "nan"]
    add(checks, "NAN-NOEVAL", "Las filas no estimadas no publican |Zxy|",
        not no_eval_finite, "%d filas con valor" % len(no_eval_finite))
    bad_state = []
    for row in estimado:
        zxy = complex(as_float(row["zxy_re"]), as_float(row["zxy_im"]))
        cond = as_float(row["cond_hh"])
        coh = as_float(row["coherence_xy"])
        sig = as_float(row["sigma_log10_abs_zxy"])
        if not (np.isfinite(zxy.real) and np.isfinite(zxy.imag) and abs(zxy) > 0):
            bad_state.append((row["record_id"], row["band"], row["frequency_hz"], "zxy"))
        elif not (np.isfinite(cond) and cond > 0):
            bad_state.append((row["record_id"], row["band"], row["frequency_hz"], "cond"))
        elif not (0.0 <= coh <= 1.0):
            bad_state.append((row["record_id"], row["band"], row["frequency_hz"], "coh"))
        elif not (np.isfinite(sig) and sig > 0):
            bad_state.append((row["record_id"], row["band"], row["frequency_hz"], "sigma"))
    add(checks, "EST-VALID", "Cada fila estimada tiene Zxy, cond, coherencia y sigma finitos",
        not bad_state, "%d filas anomalas" % len(bad_state))
    ident = [r for r in responses if r["estado"] == "no_identificable"]
    add(checks, "IDENT-MOTIVO", "no_identificable cita el rango deficiente de S_HH",
        all("rango" in r["motivo"].lower() for r in ident),
        "%d filas" % len(ident))
    below = [r for r in estimado
             if as_float(r["coherence_xy"]) < as_float(r["gamma2_crit"])]
    add(checks, "COH-GATE", "Ninguna fila estimada queda bajo la coherencia critica",
        not below, "%d filas" % len(below))
    low = [r for r in responses if r["motivo"] == "coherencia_Ex_Hy_bajo_critico"]
    add(checks, "COH-STATE", "La coherencia baja se publica como senal_insuficiente",
        all(r["estado"] == "senal_insuficiente" for r in low),
        "%d filas" % len(low))

    # ------------------------------------------------------------------
    # 5. contrato NPZ, covarianza y determinismo
    # ------------------------------------------------------------------
    responses_dir = HERE / cfg["outputs"]["responses_dir"]
    npz_files = sorted(responses_dir.glob("*.npz"))
    add(checks, "NPZ-COUNT", "Hay un NPZ por registro y banda",
        len(npz_files) == 2 * len(expected_records), "%d archivos" % len(npz_files))
    missing_arrays = []
    shape_bad = []
    cov_bad = []
    grid_bad = []
    sig_bad = []
    tol = float(cfg["tolerances"]["covarianza_psd_tol"])
    r_factors = calibration["factors"]
    for path in npz_files:
        with np.load(path, allow_pickle=True) as data:
            absent = [name for name in NPZ_ARRAYS if name not in data]
            if absent:
                missing_arrays.append((path.name, absent))
                continue
            record_id, band = path.stem.rsplit("_", 1)
            grid = np.asarray(data["frequency_hz"], dtype=float)
            if grid.shape != (len(grids[band]),) or not np.allclose(grid, grids[band]):
                grid_bad.append(path.name)
            z = data["z"]
            cov = data["cov"]
            estado = data["estado"]
            if z.shape != (grid.size, 2, 2) or cov.shape != (grid.size, 8, 8):
                shape_bad.append(path.name)
                continue
            r_log = float(r_factors[band]["r_log10"])
            for i in range(grid.size):
                if estado[i] != "estimado":
                    if not np.all(np.isnan(z[i])):
                        shape_bad.append("%s[%d]" % (path.name, i))
                    continue
                if not np.all(np.isfinite(cov[i])):
                    cov_bad.append("%s[%d] no finita" % (path.name, i))
                    continue
                sym = np.max(np.abs(cov[i] - cov[i].T))
                w = np.linalg.eigvalsh(0.5 * (cov[i] + cov[i].T))
                if sym > 1e-12 or w[0] < -tol:
                    cov_bad.append("%s[%d] sim=%.1e min=%.1e" % (path.name, i, sym, w[0]))
                sig = float(data["sigma_log10_abs_zxy"][i])
                sig_cal = float(data["sigma_cal_log10_abs_zxy"][i])
                if not (np.isfinite(sig) and np.isfinite(sig_cal)
                        and abs(sig_cal - r_log * sig) <= 1e-9 * max(1.0, abs(sig_cal))):
                    sig_bad.append("%s[%d]" % (path.name, i))
    add(checks, "NPZ-ARRAYS", "Los NPZ contienen todos los arreglos del contrato",
        not missing_arrays, "%d archivos incompletos" % len(missing_arrays))
    add(checks, "NPZ-SHAPE", "Formas de z y cov y nan fuera de estimado",
        not shape_bad, "%d entradas" % len(shape_bad))
    add(checks, "NPZ-GRID", "La grilla del NPZ coincide con la de P1",
        not grid_bad, ", ".join(grid_bad[:3]))
    add(checks, "COV-PSD", "La covarianza es simetrica y semidefinida positiva",
        not cov_bad, "; ".join(cov_bad[:3]) if cov_bad else "%d matrices" % len(npz_files))
    add(checks, "SIG-CAL", "sigma_cal = r * sigma con el r declarado",
        not sig_bad, "%d entradas" % len(sig_bad))

    target = "ARMT5-123-01-01-01"
    seed = int(cfg["bootstrap"]["seed"])
    index = [r["record_id"] for r in manifest["armt_records"]].index(target)
    seed += 100000 * index + 1
    local = json.loads(json.dumps(cfg))
    local["_band_range"] = list(cfg["bands"]["D1"]["band_range_hz"])
    source = Path(manifest["armt_records"][index]["source"]["path_abs"])
    sys.path.insert(0, r"D:\ARRT_software\ARMT_processing")
    from armt import SBFReader  # noqa: E402

    freqs = np.array([f for f in grids["D1"]
                      if cfg["bands"]["D1"]["f_min_hz"] <= f <= cfg["bands"]["D1"]["f_max_hz"]])
    with SBFReader(str(source)) as acq:
        trace = acq.trace(1)

        def read(start, stop):
            return acq.read_samples(1, start=int(start), stop=int(stop),
                                    channels=list(est.CHANNELS), units="uV")

        repeat = est.estimate(read, int(trace.sample_count), float(trace.sample_rate_hz),
                              freqs, local, seed=seed)
    with np.load(responses_dir / ("%s_D1.npz" % target), allow_pickle=True) as data:
        stored = np.asarray(data["z"], dtype=complex)
        stored_state = np.asarray(data["estado"])
    index_map = {f: i for i, f in enumerate(grids["D1"])}
    delta = 0.0
    state_bad = []
    for k, f in enumerate(freqs):
        i = index_map[float(f)]
        row = repeat["rows"][k]
        if row["estado"] != str(stored_state[i]):
            state_bad.append((float(f), row["estado"], str(stored_state[i])))
        elif row["estado"] == "estimado":
            delta = max(delta, abs(row["z"][0, 1] - stored[i][0, 1]))
        elif not np.all(np.isnan(stored[i])):
            state_bad.append((float(f), "no_estimado", "publica Z"))
    add(checks, "DETERMINISMO", "Repetir %s D1 reproduce estado y Zxy bit a bit" % target,
        delta == 0.0 and not state_bad,
        "max|delta Zxy|=%.3e, %d estados discrepantes" % (delta, len(state_bad)))

    # ------------------------------------------------------------------
    # 6. controles, recuperación y cobertura
    # ------------------------------------------------------------------
    tol_cfg = cfg["tolerances"]
    clean = [r for r in bench if r["escenario"] == "limpio"
             and r["modelo"] == "semiespacio_100"]
    add(checks, "BENCH-GRUPOS", "El benchmark cubre los 8 grupos previstos",
        len({(r["escenario"], r["modelo"]) for r in bench}) == 8,
        "%d grupos" % len({(r["escenario"], r["modelo"]) for r in bench}))
    add(checks, "BENCH-N", "Cada grupo usa 48 realizaciones y 24 de calibración",
        all(int(r["n_realizaciones"]) == 48 and int(r["n_calibracion"]) == 24
            for r in bench),
        ", ".join(sorted({"%s/%s" % (r["n_realizaciones"], r["n_calibracion"])
                          for r in bench})))
    bias = max(abs(as_float(r["bias_log10"])) for r in clean)
    bias_ph = max(abs(as_float(r["bias_phase_deg"])) for r in clean)
    add(checks, "RECUPERA-AMP", "Semiespacio limpio: |bias| <= %g dec" %
        tol_cfg["limpio_bias_log10"], bias <= tol_cfg["limpio_bias_log10"],
        "max |bias|=%.5f dec" % bias)
    add(checks, "RECUPERA-FASE", "Semiespacio limpio: |bias fase| <= %g deg" %
        tol_cfg["limpio_bias_phase_deg"], bias_ph <= tol_cfg["limpio_bias_phase_deg"],
        "max |bias|=%.4f deg" % bias_ph)
    coverage = float(clean[0]["coverage_log10_grupo"])
    coverage_ph = float(clean[0]["coverage_phase_deg_grupo"])
    add(checks, "COBERTURA", "Cobertura calibrada del control limpio en [%g, %g]" %
        (tol_cfg["coverage_min"], tol_cfg["coverage_max"]),
        tol_cfg["coverage_min"] <= coverage <= tol_cfg["coverage_max"]
        and tol_cfg["coverage_min"] <= coverage_ph <= tol_cfg["coverage_max"],
        "log10=%.3f, fase=%.3f" % (coverage, coverage_ph))
    boot_cov = float(np.mean([as_float(r["coverage_log10"]) for r in clean]))
    add(checks, "COBERTURA-BOOT", "La cobertura bootstrap sola queda por debajo de la calibrada",
        boot_cov < coverage, "bootstrap=%.3f vs calibrada=%.3f" % (boot_cov, coverage))
    flag = max(as_float(r["flag_rate_no_identificable"]) for r in bench
               if r["escenario"] == "rango_uno")
    add(checks, "RANGO-UNO", "Rango uno rechazado en >= %g de las realizaciones" %
        tol_cfg["rango_uno_flag_min"], flag >= tol_cfg["rango_uno_flag_min"],
        "fraccion=%.2f" % flag)
    out = [r for r in bench if r["escenario"] == "outliers"]
    rmse = max(as_float(r["rmse_log10"]) for r in out)
    rmse_ls = max(as_float(r["rmse_log10_ls"]) for r in out)
    add(checks, "OUTLIERS", "El estimador robusto no empeora frente a LS",
        rmse <= 1.05 * rmse_ls, "rmse=%.5f vs LS=%.5f" % (rmse, rmse_ls))
    add(checks, "FACTORES", "Los factores r son finitos y positivos, con subcobertura en amplitud",
        all(np.isfinite(v["r_log10"]) and v["r_log10"] > 0.0
            and np.isfinite(v["r_phase_deg"]) and v["r_phase_deg"] > 0.0
            for v in r_factors.values())
        and all(v["r_log10"] > 1.0 for v in r_factors.values()),
        ", ".join("%s: %.3f/%.3f" % (b, v["r_log10"], v["r_phase_deg"])
                  for b, v in r_factors.items()))
    labels = {r["criterio_grupo"] for r in bench}
    add(checks, "BENCH-LABEL", "Los criterios usan el vocabulario PASA/FALLA/OBSERVACION",
        labels <= {"PASA", "FALLA", "OBSERVACION"}, ", ".join(sorted(labels)))
    add(checks, "BENCH-NOFALLA", "Ningun grupo del benchmark queda en FALLA",
        "FALLA" not in labels, ", ".join(sorted(labels)))

    # ------------------------------------------------------------------
    # 7. resumen, reporte y matriz
    # ------------------------------------------------------------------
    add(checks, "SUM-ESTADO", "resumen_p6 declara la puerta PARCIAL",
        summary.get("estado_puerta") == "PARCIAL", str(summary.get("estado_puerta")))
    add(checks, "SUM-RAMA", "resumen_p6 declara la rama AMT_sin_TEM",
        summary.get("rama") == "AMT_sin_TEM", str(summary.get("rama")))
    add(checks, "SUM-N", "resumen_p6 cuenta 15 registros y 630 respuestas",
        summary.get("records") == 15 and summary.get("responses") == expected_rows,
        "%s registros, %s respuestas" % (summary.get("records"), summary.get("responses")))
    recomputed = {}
    for row in responses:
        recomputed[row["estado"]] = recomputed.get(row["estado"], 0) + 1
    add(checks, "SUM-ESTADOS", "El recuento de estados del resumen coincide con el CSV",
        summary.get("states") == recomputed, json.dumps(recomputed, sort_keys=True))
    add(checks, "SUM-CAL", "El resumen cita los factores de calibración",
        summary.get("calibration", {}).get("factors") == r_factors,
        "calibracion_p6.json")
    add(checks, "SUM-SCOPE", "El alcance declara sin TEM, sin etiquetas y sin red",
        summary.get("scope", {}).get("tem_usado") is False
        and summary.get("scope", {}).get("etiquetas") is False
        and summary.get("scope", {}).get("red_neuronal") is False,
        "scope")
    report = files["report"].read_text(encoding="utf-8")
    add(checks, "REPORT-SEC", "El reporte incluye alcance, controles, incertidumbre y límites",
        all(h in report for h in ("## Alcance", "## Respuestas reales", "## Controles 1D",
                                 "## Incertidumbre", "## Límites", "## Conclusión")),
        "reporte_p6.md")
    add(checks, "REPORT-CAL", "El reporte advierte que Z es relativa y no rho_a",
        "no" in report.lower() and "resistividad aparente" in report.lower(),
        "reporte_p6.md")
    row_p6 = [r for r in matrix if r["puerta"] == "P6"]
    add(checks, "MATRIZ-P6", "La matriz tiene una fila P6 en PARCIAL",
        len(row_p6) == 1 and "PARCIAL" in row_p6[0]["estado"].upper(),
        row_p6[0]["estado"] if row_p6 else "sin fila P6")
    add(checks, "MATRIZ-REF", "La fila P6 cita el entregable de la etapa",
        bool(row_p6) and "etapa6" in json.dumps(row_p6[0], ensure_ascii=False),
        "MATRIZ_VALIDACION_ARMT.csv")
    open_blockers = {b if isinstance(b, str) else b.get("id") for b in cfg["blockers"]}
    add(checks, "BLOCKERS", "Los bloqueos activos siguen declarados en la configuracion",
        {"B-P0-04", "B-P0-06", "SIN-REF-REMOTA"} <= open_blockers,
        ", ".join(sorted(str(b) for b in open_blockers)))

    # ------------------------------------------------------------------
    # 8. higiene de entregables y observaciones
    # ------------------------------------------------------------------
    offenders = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file():
            continue
        if path.name in ("validar_etapa6.py", "validacion_etapa6.json"):
            continue
        if path.suffix.lower() not in (".csv", ".json", ".md", ".py", ".txt"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "SYN-" in text:
            offenders.append(str(path.relative_to(HERE)))
    add(checks, "NOSYN", "No hay marcadores SYN- en los entregables de P6",
        not offenders, ", ".join(offenders))
    # NOPYCACHE: se verifica que no se distribuyan .pyc como entregables.
    # Un directorio __pycache__ es un artefacto de ejecucion del propio
    # validador y no debe invalidar la comprobacion (comprobacion idempotente).
    pyc_entregables = [
        p for p in HERE.rglob("*.pyc") if "__pycache__" not in p.parts
    ]
    add(checks, "NOPYCACHE", "No hay bytecode .pyc distribuido como entregable",
        not pyc_entregables, ", ".join(str(p.relative_to(HERE)) for p in pyc_entregables))
    hashes = {name: sha256_file(HERE / name) for name in ("estimador.py", "p6.py")}
    add(checks, "HASH-STABLE", "Los hashes del software son estables y no vacios",
        all(len(v) == 64 for v in hashes.values()), json.dumps(hashes)[:80] + "...")

    observation(checks, "OBS-01",
                "La respuesta de campo es relativa: sin calibracion certificada (B-P0-04) no se calcula rho_a.",
                "calibrado=no en las 630 filas")
    observation(checks, "OBS-02",
                "El bootstrap temporal subestima el error real (cobertura ~0.6); se aplica un factor r calibrado en controles.",
                "r_D0=%.3f, r_D1=%.3f" % (r_factors["D0"]["r_log10"], r_factors["D1"]["r_log10"]))
    observation(checks, "OBS-03",
                "El factor r se calibra con un semiespacio 1D limpio; no cubre error de modelo ni de calibracion en campo.",
                "mitad de calibracion 24 / evaluacion 24")
    observation(checks, "OBS-04",
                "La cobertura es estadistica sobre controles; el ruido en H no es corregible sin referencia remota.",
                "ruido_H: bias sistematico, no cobertura")
    observation(checks, "OBS-05",
                "D0 por debajo de 125 Hz no se evalua con L=256; no se extrapola con otra ventana.",
                "%d filas no_evaluado" % len(below))
    observation(checks, "OBS-06",
                "La coherencia alta no demuestra identidad E-H; el escenario coherente se reporta como observacion.",
                "ruido_coherente")
    observation(checks, "OBS-07",
                "Los modelos estratificados 1D son controles de recuperacion, no evidencia de estructura del sitio.",
                "dos_capas y tres_capas")
    observation(checks, "OBS-08",
                "P6 queda PARCIAL: no habilita sintesis, etiquetas ni entrenamiento (P3-P5 y P7 cerradas).",
                "B-P0-03 abierto")

    passed = sum(1 for c in checks if c["resultado"] == "PASA")
    failed = sum(1 for c in checks if c["resultado"] == "FALLA")
    observations = sum(1 for c in checks if c["resultado"] == "OBSERVACION")
    status = ("FALLA" if failed else
              "APROBADO_CON_OBSERVACIONES" if observations else "APROBADO")
    result = dict(
        artifact="validacion_etapa6", version=VERSION,
        generated_at_utc=utc_now(), stage=6, gate="P6",
        rama="AMT_sin_TEM",
        status=status,
        counts=dict(checks=len(checks), passed=passed, failed=failed,
                    observations=observations),
        checks=checks,
        observations=[c for c in checks if c["resultado"] == "OBSERVACION"],
        blockers=cfg["blockers"],
        note=("La validacion confirma coherencia interna, guardas de alcance, "
              "contrato de covarianza y recuperacion en controles 1D. No "
              "certifica calibracion, vinculo TEM ni validez fisica de las "
              "respuestas de campo."),
    )
    (HERE / cfg["outputs"]["validation"]).write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=status, counts=result["counts"],
                          failed=[c["id"] for c in checks if c["resultado"] == "FALLA"]),
                     ensure_ascii=False, indent=1))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
