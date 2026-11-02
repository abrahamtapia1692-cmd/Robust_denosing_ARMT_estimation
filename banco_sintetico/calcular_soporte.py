#!/usr/bin/env python3
"""Calcula el soporte sintetico de S0 y S1 y actualiza el manifiesto del banco.

La clasificacion usa sensibilidad de diferencias finitas del surrogate, guardas
de turn-off/borde y la penalizacion de la banda muerta AMT. No es P2-T: es una
prueba de la logica de contrato con una verdad declarada.
"""

import argparse
from pathlib import Path

from comun import (
    DEFAULT_MODEL,
    DEFAULT_OUT_DIR,
    file_entry,
    read_json,
    utc_now,
    write_json,
)
from modelo_surrogate import build_support


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    model = read_json(args.model)
    manifest_path = out_dir / "manifiesto_sintetico.json"
    manifest = read_json(manifest_path)

    support_files = []
    for scenario in manifest["scenarios"]:
        truth_path = Path(scenario["truth_file"]["path_abs"])
        truth = read_json(truth_path)
        support = build_support(model, truth, truth_path)

        support_path = out_dir / ("soporte_%s.json" % scenario["id"])
        write_json(support_path, support)
        scenario["support_file"] = file_entry(support_path)
        support_files.append(scenario["support_file"])

        summary = support["summary"]
        print(
            "%s %s | respaldadas %s | aplicacion %s | condicionales %s | G0 %s"
            % (
                scenario["id"],
                scenario["tem_id"],
                summary["supported_ranges_hz"],
                summary["application_ranges_hz"],
                summary["conditional_ranges_hz"],
                summary["g0_trigger"],
            )
        )

    manifest["support"] = {
        "status": "calculado",
        "version": "SYN-FS-1.0.0",
        "generated_at_utc": utc_now(),
        "files": support_files,
    }
    write_json(manifest_path, manifest)
    print("Soporte escrito en: %s" % out_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
