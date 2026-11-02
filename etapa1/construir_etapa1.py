#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orquestador de la Etapa 1.

Verifica que P0 no cambio, comprueba el alcance, ejecuta los cuatro modulos y
deja un registro de construccion con tiempos y hashes.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import comun_p1 as comun

import registro_calibracion
import qc_tiempo
import exportar_calibrado
import presupuesto_instrumental


def build(config=None):
    config = config or comun.load_config()
    started = time.time()

    p0_hashes = comun.verify_p0_hashes()
    if not all(row["unchanged"] for row in p0_hashes):
        raise RuntimeError("P0 cambio; P1 no debe escribir sobre un contrato distinto")

    manifest = comun.load_p0_manifest()
    record = comun.target_record(manifest)
    if record["split"]["split"] != "desarrollo":
        raise RuntimeError(
            "el registro objetivo no esta en desarrollo: %s" % record["split"]["split"]
        )

    synthetic_leaks = 0
    for name in ("manifest.json", "splits.csv"):
        text = (comun.ETAPA0 / name).read_text(encoding="utf-8")
        synthetic_leaks += text.count("SYN-")
    if synthetic_leaks:
        raise RuntimeError("hay %d referencias SYN- en P0" % synthetic_leaks)

    source = Path(record["source"]["path_abs"])
    source_sha_before = comun.sha256_file(source)

    steps = []

    def run(name, function):
        step_start = time.time()
        result = function(config)
        steps.append(
            {
                "name": name,
                "seconds": round(time.time() - step_start, 3),
                "result": result,
            }
        )
        return result

    run("registro_calibracion", registro_calibracion.build)
    run("qc_tiempo", qc_tiempo.build)
    run("exportar_calibrado", exportar_calibrado.build)
    run("presupuesto_instrumental", presupuesto_instrumental.build)

    source_sha_after = comun.sha256_file(source)
    source_unchanged = source_sha_before == source_sha_after == record["source"]["sha256"]

    payload = {
        "build_version": "P1-BUILD-1.0.0",
        "generated_at_utc": comun.utc_now(),
        "stage": 1,
        "target_record": comun.TARGET_RECORD,
        "config_version": config["version"],
        "p0_hashes": p0_hashes,
        "synthetic_leaks": synthetic_leaks,
        "source_sha256_before": source_sha_before,
        "source_sha256_after": source_sha_after,
        "source_unchanged": bool(source_unchanged),
        "steps": steps,
        "total_seconds": round(time.time() - started, 3),
        "status": "COMPLETADO",
        "note": "La construccion no modifica P0 ni los proyectos de origen.",
    }
    comun.dump_json(comun.ETAPA1 / "construccion_etapa1.json", payload)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    config = comun.load_config(args.config)
    payload = build(config)
    print("construccion P1: %s" % payload["status"])
    for step in payload["steps"]:
        print("  %-28s %8.3f s" % (step["name"], step["seconds"]))
    print("total: %.3f s" % payload["total_seconds"])
    print("fuente sin cambios: %s" % payload["source_unchanged"])


if __name__ == "__main__":
    main()
