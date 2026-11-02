#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Numeros del Anexo A: conversion tiempo-frecuencia TEM -> MT/AMT.

No crea puertas ni estados: imprime las tablas que documentan por que la
conversion ``f = 1/t`` o ``f = 1/(2*pi*t)`` no habilita soporte. Lee solo
artefactos de la etapa (gates validos, sensibilidad frente a la DOI y los 18
modelos de ``model_provenance.json``) y no modifica ningun archivo.

Uso::

    python etapa2/anexo_conversion_tf.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import mt1d  # noqa: E402

VERSION = "P2T-ANEXO-A-1.0.0"
TOL_DEX = 0.025
HALVES = (10.0, 30.0, 100.0, 300.0, 1000.0)
DEPTH_M = 300.0
SELECTED = (124.7452266, 150.7313464, 321.30845, 684.9213684, 1000.0, 3162.27766)


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def grids():
    out = {}
    for band in ("D0", "D1"):
        rows = read_csv(ROOT / "etapa1" / ("respuesta_interpolada_%s.csv" % band))
        out[band] = np.array([float(r["frequency_hz"]) for r in rows])
    return out


def gate_table():
    gates = read_csv(HERE / "tem_valid_gates.csv")
    print("== A.3  Mapeo de los gates usados en inversion")
    print("El rango temporal se convierte con dos reglas: f=1/(2*pi*t) (equivalencia "
          "de profundidad) y f=1/t (sin base fisica).")
    print()
    print("%-8s %3s %9s %9s %16s %18s" % ("sondeo", "n", "t_min_ms", "t_max_ms",
                                          "f_1/(2pi t)_Hz", "f_1/t_Hz"))
    for sid in sorted({g["sounding_id"] for g in gates}):
        used = [g for g in gates if g["sounding_id"] == sid and g["usado_en_inversion"] == "si"]
        if not used:
            print("%-8s %3d  (sin gates usados)" % (sid, 0))
            continue
        t = np.array([float(g["t_ms_reader"]) for g in used]) / 1000.0
        print("%-8s %3d %9.2f %9.2f %16s %18s" % (
            sid, len(used), t.min() * 1000.0, t.max() * 1000.0,
            "%.1f-%.1f" % (1.0 / (2.0 * np.pi * t.max()), 1.0 / (2.0 * np.pi * t.min())),
            "%.0f-%.0f" % (1.0 / t.max(), 1.0 / t.min())))
    print()


def depth_table():
    rows = read_csv(HERE / "diagnostico_tem" / "comparacion_sensibilidad_doi.csv")
    print("== A.5  Profundidad de sensibilidad MT frente a la DOI TEM")
    print()
    print("%-8s %-2s %3s %8s %8s %8s %7s" % ("sondeo", "b", "n", "z50_m", "z90_m",
                                             "doi_m", "ok"))
    for sid in sorted({r["sounding_id"] for r in rows}):
        for band in ("D0", "D1"):
            sel = [r for r in rows if r["sounding_id"] == sid and r["band"] == band]
            print("%-8s %-2s %3d %8.1f %8.1f %8.1f %7.2f" % (
                sid, band, len(sel),
                float(np.median([float(r["z50_m"]) for r in sel])),
                float(np.median([float(r["z90_m"]) for r in sel])),
                float(sel[0]["doi_m"]),
                float(np.mean([r["profundidad_ok"] == "si" for r in sel]))))
    print()
    print("Detalle en frecuencias seleccionadas (z90, fraccion de sensibilidad "
          "bajo la DOI y veredicto):")
    print()
    print("%-8s %-2s %9s %8s %8s %8s %4s" % ("sondeo", "b", "f_Hz", "z90_m",
                                             "doi_m", "frac", "ok"))
    for sid in sorted({r["sounding_id"] for r in rows}):
        for band in ("D0", "D1"):
            for target in SELECTED:
                sel = [r for r in rows if r["sounding_id"] == sid and r["band"] == band
                       and abs(float(r["frequency_hz"]) - target) <= 1e-6 * max(1.0, target)]
                if not sel:
                    continue
                r = sel[0]
                print("%-8s %-2s %9.2f %8.1f %8.1f %8.3f %4s" % (
                    sid, band, float(r["frequency_hz"]), float(r["z90_m"]),
                    float(r["doi_m"]), float(r["frac_sensibilidad_bajo_doi"]),
                    r["profundidad_ok"]))
    print()


def truncate(rho, interfaces, depth, half):
    keep = sum(1 for top in interfaces if top < depth) + 1
    return (list(rho[:keep]) + [float(half)],
            list(interfaces[: keep - 1]) + [float(depth)])


def halfspace_table():
    models = json.loads((HERE / "model_provenance.json").read_text(encoding="utf-8-sig"))["models"]
    print("== A.6  Sensibilidad al semiespacio terminal fijado a %.0f m" % DEPTH_M)
    print("Cada modelo se trunca a %.0f m y el semiespacio se sustituye por "
          "%s ohm-m; maximo sobre los %d modelos." % (DEPTH_M, HALVES, len(models)))
    print()
    print("%-2s %10s %12s %12s %10s %9s" % ("b", "f_Hz", "max|dl10 Z|",
                                            "rho_a_dex", "fase_deg", "presupuesto"))
    for band, freqs in grids().items():
        worst = np.zeros(freqs.size)
        worst_ph = np.zeros(freqs.size)
        for model in models:
            rho = [float(v) for v in model["rho_ohm_m"]]
            interfaces = [float(v) for v in model["interfaces_m"]]
            z_ref = mt1d.z1d(freqs, rho, interfaces)
            for half in HALVES:
                r2, i2 = truncate(rho, interfaces, DEPTH_M, half)
                z2 = mt1d.z1d(freqs, r2, i2)
                worst = np.maximum(worst, np.abs(np.log10(np.abs(z2) / np.abs(z_ref))))
                worst_ph = np.maximum(worst_ph, np.abs(np.degrees(np.angle(z2 / z_ref))))
        for f, d, p in zip(freqs, worst, worst_ph):
            print("%-2s %10.3f %12.4f %12.4f %10.2f %8.0f%%" % (
                band, f, d, 2.0 * d, p, 100.0 * (2.0 * d) / TOL_DEX))
    print()


def main():
    print("Anexo A (%s)  conversion tiempo-frecuencia TEM -> MT/AMT" % VERSION)
    print("Documentacion de una decision ya tomada: no crea soporte ni estados.")
    print()
    gate_table()
    depth_table()
    halfspace_table()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
