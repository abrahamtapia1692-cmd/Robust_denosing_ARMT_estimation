#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Valida el barrido P1 de los 15 registros.

Comprueba que P0 sigue congelado, que el barrido cubre exactamente los 15
registros del manifiesto, que los hashes de origen y las longitudes coinciden,
que el estado QC se deriva de sus propias comprobaciones, que las mascaras son
coherentes, que la calibracion cubre cada banda y que no se reexportaron series
temporales ni se introdujo contenido sintetico.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import comun_p1 as comun


class Checker:
    def __init__(self):
        self.checks = []

    def add(self, check_id, ok, detail):
        self.checks.append(
            {"id": check_id, "estado": "PASA" if ok else "FALLA", "detalle": detail}
        )
        return ok

    def require(self, check_id, condition, detail):
        return self.add(check_id, bool(condition), detail)

    def observe(self, check_id, detail):
        self.checks.append({"id": check_id, "estado": "OBSERVACION", "detalle": detail})
        return True


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        return reader.fieldnames, rows


def derive_status(checks):
    return comun.status_from_checks(list(checks.values()))


def validate(config, checker):
    manifest = comun.load_p0_manifest()
    records = comun.iter_records(manifest)
    ids = [record["record_id"] for record in records]

    # 1. P0 congelado y alcance.
    for row in comun.verify_p0_hashes():
        checker.require(
            "P0-HASH-%s" % Path(row["artifact"]).name,
            row["unchanged"],
            "%s: %s" % (row["artifact"], "sin cambios" if row["unchanged"] else "cambio"),
        )
    checker.require(
        "P0-NO-SYNTHETIC",
        all(
            "SYN-" not in (comun.ETAPA0 / name).read_text(encoding="utf-8")
            for name in ("manifest.json", "splits.csv")
        ),
        "sin identificadores SYN- en P0",
    )
    checker.require(
        "BARRIDO-CONFIG",
        config["stage"] == 1
        and config["version"] == "P1-CONFIG-2.0.0"
        and config["scope"]["exports_time_series"] is False,
        "config %s, sin exportacion de series" % config["version"],
    )
    checker.require(
        "BARRIDO-RECORDS",
        len(records) == 15,
        "%d registros en el manifiesto" % len(records),
    )

    splits_fields, split_rows = read_csv(comun.ETAPA0 / "splits.csv")
    splits = {row["record_id"]: row for row in split_rows}
    checker.require(
        "BARRIDO-SPLITS-COVERAGE",
        sorted(splits) == sorted(ids),
        "splits.csv y manifiesto cubren los mismos registros",
    )

    registry_dir = comun.BARRIDO / "registros"
    files = sorted(path.stem for path in registry_dir.glob("*.json"))
    checker.require(
        "BARRIDO-FILES",
        files == sorted(ids),
        "%d archivos de registro" % len(files),
    )

    payloads = []
    for record in records:
        path = registry_dir / ("%s.json" % record["record_id"])
        checker.require(
            "BARRIDO-FILE-%s" % record["record_id"], path.is_file(), path.name
        )
        if not path.is_file():
            continue
        payloads.append(comun.load_json(path))

    # 2. Por registro.
    expected_samples = {"D0": 0, "D1": 0}
    expected_traces = 0
    for payload in payloads:
        rid = payload["record_id"]
        record = comun.record_by_id(rid, manifest)
        split_row = splits[rid]

        checker.require(
            "SPLIT-%s" % rid,
            payload["split"]["split"] == split_row["split"]
            == record["split"]["split"],
            "%s en split %s" % (rid, split_row["split"]),
        )
        checker.require(
            "SOURCE-HASH-%s" % rid,
            comun.sha256_file(record["source"]["path_abs"])
            == record["source"]["sha256"]
            == payload["source_sha256_recomputed"]
            and payload["source_sha256_match"] is True,
            "%s: SHA-256 del SBF" % rid,
        )
        checker.require(
            "CONSISTENCY-%s" % rid,
            payload["consistency"]["all_match"] is True
            and all(
                all(row.values()) for row in payload["consistency"]["bands"].values()
            ),
            "%s: SBF y manifiesto coinciden en muestras, fs, canales y ADC" % rid,
        )
        checker.require(
            "SITE-UNRESOLVED-%s" % rid,
            payload["site"]["site_id"] is None
            and payload["site"]["status"] == "no_resuelto",
            "%s: identidad de sitio sigue no resuelta" % rid,
        )

        for band in ("D0", "D1"):
            expected_traces += 1
            block = payload["bands"][band]
            manifest_trace = record["traces"][int(config["bands"][band]["trace_index"])]
            expected_samples[band] += int(manifest_trace["sample_count"])
            checker.require(
                "LENGTH-%s-%s" % (rid, band),
                int(block["n_samples"]) == int(manifest_trace["sample_count"]),
                "%s %s: %d muestras" % (rid, band, block["n_samples"]),
            )
            checker.require(
                "FS-%s-%s" % (rid, band),
                abs(float(block["sample_rate_hz"]) - float(manifest_trace["sample_rate_hz"]))
                <= 1e-9,
                "%s %s: %.3f Hz" % (rid, band, block["sample_rate_hz"]),
            )
            checker.require(
                "CHANNELS-%s-%s" % (rid, band),
                list(block["channels"]) == list(comun.CHANNELS)
                and sorted(block["per_channel"]) == sorted(comun.CHANNELS),
                "%s %s: %s" % (rid, band, block["channels"]),
            )
            checker.require(
                "STATUS-CONSISTENT-%s-%s" % (rid, band),
                block["status"] == derive_status(block["checks"]),
                "%s %s: estado %s derivado de sus comprobaciones"
                % (rid, band, block["status"]),
            )
            mask_path = comun.BARRIDO / "mascaras" / block["bad_mask"]["file"]
            checker.require(
                "MASK-FILE-%s-%s" % (rid, band),
                mask_path.is_file(),
                "%s %s: %s" % (rid, band, block["bad_mask"]["file"]),
            )
            if not mask_path.is_file():
                continue
            mask = np.load(mask_path)
            packed_ok = True
            total = 0
            union = np.zeros(int(block["n_samples"]), dtype=bool)
            for channel in comun.CHANNELS:
                key = "bad_" + channel
                if key not in mask:
                    packed_ok = False
                    continue
                unpacked = comun.unpack_bool(
                    mask[key], int(mask["n_samples"]), config["qc"]["mask_bitorder"]
                )
                packed_ok &= len(unpacked) == int(block["n_samples"])
                total += int(unpacked.sum())
                union |= unpacked
            checker.require(
                "MASK-CONTENT-%s-%s" % (rid, band),
                packed_ok
                and int(mask["n_samples"]) == int(block["n_samples"])
                and total == int(block["bad_mask"]["total_bad_samples_summed"])
                and int(union.sum()) == int(block["bad_mask"]["union_bad_samples"]),
                "%s %s: %d muestras en mascara" % (rid, band, total),
            )

        # Calibracion de las dos bandas.
        for band in ("D0", "D1"):
            rows = payload["calibration"][band]
            checker.require(
                "CAL-CHANNELS-%s-%s" % (rid, band),
                [row["channel"] for row in rows] == list(comun.CHANNELS),
                "%s %s: %d canales" % (rid, band, len(rows)),
            )
            ok = True
            detail = []
            for row in rows:
                clb = comun.DEFAULT_SOFTWARE_ROOT / row["clb_path_ref"]
                checks = {
                    "file": clb.is_file(),
                    "sha": clb.is_file()
                    and comun.sha256_file(clb) == row["clb_sha256"],
                    "covered": row["covered"],
                    "gain": row["table_gain"] == 1.0,
                }
                if not all(checks.values()):
                    ok = False
                    detail.append(
                        "%s:%s"
                        % (row["channel"], [k for k, v in checks.items() if not v])
                    )
            checker.require(
                "CAL-COVERAGE-%s-%s" % (rid, band),
                ok,
                "%s %s: hashes, gain=1.0 y cobertura%s"
                % (rid, band, "" if ok else " (%s)" % "; ".join(detail)),
            )

        checker.require(
            "B-P0-05-%s" % rid,
            payload["blockers"]["B-P0-05"]["estado"]
            == (
                "CERRADO_PARA_ESTE_REGISTRO"
                if payload["status"] in ("PASA", "PASA_CON_OBSERVACIONES")
                else "ABIERTO"
            ),
            "%s: B-P0-05 %s con QC %s"
            % (rid, payload["blockers"]["B-P0-05"]["estado"], payload["status"]),
        )

    # 3. CSV y agregados.
    qc_fields, qc_rows = read_csv(comun.BARRIDO / "qc_registros.csv")
    cal_fields, cal_rows = read_csv(comun.BARRIDO / "calibracion_cobertura.csv")
    gain_fields, gain_rows = read_csv(comun.BARRIDO / "ganancias_registros.csv")

    checker.require(
        "CSV-QC-ROWS",
        len(qc_rows) == 15 * 2 * len(comun.CHANNELS),
        "%d filas = 15 registros x 2 bandas x 5 canales" % len(qc_rows),
    )
    checker.require(
        "CSV-CAL-ROWS",
        len(cal_rows) == 15 * 2 * len(comun.CHANNELS),
        "%d filas de cobertura" % len(cal_rows),
    )
    checker.require(
        "CSV-GAIN-ROWS",
        len(gain_rows) == 15,
        "%d filas de ganancia" % len(gain_rows),
    )
    checker.require(
        "CSV-QC-COLUMNS",
        qc_fields and "record_id" in qc_fields and "jump_count" in qc_fields,
        "columnas de qc_registros.csv",
    )
    checker.require(
        "CSV-CAL-COLUMNS",
        cal_fields and "covered" in cal_fields and "clb_path_ref" in cal_fields,
        "columnas de calibracion_cobertura.csv",
    )
    checker.require(
        "CSV-GAIN-COLUMNS",
        gain_fields and "gain_unique" in gain_fields and "adc_to_uv_d0" in gain_fields,
        "columnas de ganancias_registros.csv",
    )

    summary = comun.load_json(comun.BARRIDO / "resumen_global.json")
    totals = summary["totals"]
    checker.require(
        "TOTAL-RECORDS",
        totals["records"] == 15 and totals["by_split"].get("desarrollo", 0) == 10,
        "%d registros, %d en desarrollo"
        % (totals["records"], totals["by_split"].get("desarrollo", 0)),
    )
    checker.require(
        "TOTAL-TRACES",
        expected_traces == 30,
        "%d trazas D0/D1 procesadas" % expected_traces,
    )
    checker.require(
        "TOTAL-SAMPLES-D0",
        totals["samples"]["D0"] == expected_samples["D0"],
        "D0: %d muestras" % totals["samples"]["D0"],
    )
    checker.require(
        "TOTAL-SAMPLES-D1",
        totals["samples"]["D1"] == expected_samples["D1"],
        "D1: %d muestras" % totals["samples"]["D1"],
    )
    checker.require(
        "TOTAL-SAMPLES",
        totals["samples"]["total"] == expected_samples["D0"] + expected_samples["D1"],
        "total: %d muestras" % totals["samples"]["total"],
    )
    checker.require(
        "TOTAL-BAD-SAMPLES",
        totals["bad_union_samples"]
        == sum(
            int(payload["bands"][band]["bad_mask"]["union_bad_samples"])
            for payload in payloads
            for band in ("D0", "D1")
        ),
        "%d muestras en mascara (union)" % totals["bad_union_samples"],
    )
    checker.require(
        "TOTAL-BAD-BY-CHANNEL",
        totals["bad_samples_by_channel"]
        == sum(
            int(payload["bands"][band]["per_channel"][channel]["bad_samples"])
            for payload in payloads
            for band in ("D0", "D1")
            for channel in comun.CHANNELS
        ),
        "%d muestras en mascara (suma por canal)"
        % totals["bad_samples_by_channel"],
    )
    checker.require(
        "TOTAL-JUMPS",
        all(
            totals["jumps"][channel]
            == sum(
                int(payload["bands"][band]["per_channel"][channel]["jump_count"])
                for payload in payloads
                for band in ("D0", "D1")
            )
            for channel in comun.CHANNELS
        ),
        "conteo de saltos por canal",
    )
    checker.require(
        "TOTAL-STATUS",
        sorted(totals["records_falla"]) == [],
        "ningun registro en FALLA",
    )

    # 4. Sin reexportacion y sin fuga sintetica.
    npy = list(comun.BARRIDO.rglob("*.npy"))
    checker.require(
        "NO-NPY-IN-BARRIDO",
        not npy,
        "%d archivos .npy en barrido" % len(npy),
    )
    export = comun.load_json(comun.ETAPA1 / "exportaciones" / "exportaciones.json")
    unchanged = []
    for band, block in export["bands"].items():
        path = comun.ETAPA1 / block["file"]
        unchanged.append(
            path.is_file() and comun.sha256_file(path) == block["sha256"]
        )
    checker.require(
        "EXPORT-UNCHANGED",
        export["target_record"] == comun.TARGET_RECORD and all(unchanged),
        "las exportaciones del registro objetivo conservan su SHA-256",
    )
    checker.require(
        "ONLY-TARGET-EXPORTED",
        sorted(export["bands"]) == ["D0", "D1"],
        "solo el registro objetivo tiene series exportadas",
    )

    leaks = []
    for path in comun.BARRIDO.rglob("*"):
        if (
            path.is_file()
            and path.suffix.lower() in (".json", ".csv", ".md")
            and not path.name.startswith("validacion_")
        ):
            if "SYN-" in path.read_text(encoding="utf-8", errors="replace"):
                leaks.append(path.name)
    checker.require("NO-SYNTHETIC", not leaks, "sin SYN- en reportes del barrido")

    checker.require(
        "NO-SYNTHETIC-P0",
        "SYN-" not in (comun.ETAPA0 / "manifest.json").read_text(encoding="utf-8"),
        "manifiesto P0 sin SYN-",
    )

    # 5. Estado declarado.
    checker.require(
        "P1-STATUS",
        summary["p1_status"] == "PARCIAL" and len(summary["p1_status_reasons"]) >= 4,
        "P1 PARCIAL con %d razones" % len(summary["p1_status_reasons"]),
    )
    checker.require(
        "P2T-BLOCKED",
        "B-P0-03" in summary["blockers_open"]
        and any("P2-T" in row for row in summary["p1_status_reasons"]),
        "P2-T sigue bloqueado por B-P0-03",
    )
    report = comun.BARRIDO / "reporte_barrido.md"
    checker.require(
        "REPORT",
        report.is_file()
        and "no reexporta series temporales" in report.read_text(encoding="utf-8"),
        "reporte con el alcance declarado",
    )

    checker.observe(
        "OBS-CALIBRATION-VALIDITY",
        "La cobertura de calibracion es de frecuencia, no metrologica: B-P0-04 sigue abierto.",
    )
    checker.observe(
        "OBS-SITE",
        "Los 15 registros siguen sin identidad de sitio ni coordenadas verificadas (B-P0-01/B-P0-02).",
    )
    checker.observe(
        "OBS-TIMEZONE",
        "La zona horaria de las marcas locales no esta declarada (B-P0-07).",
    )
    checker.observe(
        "OBS-NO-INDEPENDENT-EXPORT",
        "No hay exportacion independiente del fabricante para contrastar el lector SBF.",
    )

    counts = {
        "total": len(checker.checks),
        "pasa": sum(1 for row in checker.checks if row["estado"] == "PASA"),
        "falla": sum(1 for row in checker.checks if row["estado"] == "FALLA"),
        "observaciones": sum(
            1 for row in checker.checks if row["estado"] == "OBSERVACION"
        ),
    }
    result = (
        "FALLA"
        if counts["falla"]
        else "APROBADO_CON_OBSERVACIONES"
        if counts["observaciones"]
        else "APROBADO"
    )

    payload = {
        "validacion_version": "1.0.0",
        "generated_at_utc": comun.utc_now(),
        "stage": 1,
        "extension": "barrido de los 15 registros",
        "config_version": config["version"],
        "resultado": result,
        "summary": counts,
        "totals": totals,
        "checks": checker.checks,
        "blockers_cerrados": [
            {
                "id": "B-P0-05",
                "alcance": "los 15 registros, bandas D0/D1",
                "evidencia": "barrido/registros/*.json, barrido/mascaras/*.npz",
            }
        ],
        "blockers_abiertos": [
            "B-P0-01",
            "B-P0-02",
            "B-P0-03",
            "B-P0-04",
            "B-P0-06",
            "B-P0-07",
        ],
        "p1_status": "PARCIAL",
        "p2t_status": "BLOQUEADO",
        "observaciones": [
            row for row in checker.checks if row["estado"] == "OBSERVACION"
        ],
    }
    comun.dump_json(comun.BARRIDO / "validacion_barrido.json", payload)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    config = comun.load_config_barrido(args.config)
    checker = Checker()
    payload = validate(config, checker)
    print("validacion barrido P1: %s" % payload["resultado"])
    print(
        "  %d comprobaciones: %d pasan, %d fallan, %d observaciones"
        % (
            payload["summary"]["total"],
            payload["summary"]["pasa"],
            payload["summary"]["falla"],
            payload["summary"]["observaciones"],
        )
    )
    for row in payload["checks"]:
        if row["estado"] == "FALLA":
            print("  FALLA %s: %s" % (row["id"], row["detalle"]))
    return 0 if payload["summary"]["falla"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
