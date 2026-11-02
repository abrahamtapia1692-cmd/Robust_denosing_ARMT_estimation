#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Valida los entregables de la Etapa 1 contra P0 y contra las fuentes.

Comprueba hashes, cobertura de calibracion, continuidad de fase, QC, mascaras,
escala de exportacion, presupuesto instrumental y estado declarado.
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

    def observe(self, check_id, detail):
        self.checks.append({"id": check_id, "estado": "OBSERVACION", "detalle": detail})
        return True

    def require(self, check_id, condition, detail):
        return self.add(check_id, bool(condition), detail)


def load_response(band):
    path = comun.ETAPA1 / ("respuesta_interpolada_%s.csv" % band)
    with open(path, newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        return path, reader.fieldnames, rows


def validate(config, checker):
    manifest = comun.load_p0_manifest()
    record = comun.target_record(manifest)

    # 1. P0 congelado.
    for row in comun.verify_p0_hashes():
        checker.require(
            "P0-HASH-%s" % Path(row["artifact"]).name,
            row["unchanged"],
            "%s: %s" % (row["artifact"], "sin cambios" if row["unchanged"] else "cambio"),
        )

    checker.require(
        "P0-TARGET-SPLIT",
        record["split"]["split"] == "desarrollo",
        "registro %s en split %s" % (comun.TARGET_RECORD, record["split"]["split"]),
    )
    checker.require(
        "P0-NO-SYNTHETIC",
        all(
            "SYN-" not in (comun.ETAPA0 / name).read_text(encoding="utf-8")
            for name in ("manifest.json", "splits.csv")
        ),
        "sin identificadores SYN- en P0",
    )
    source = Path(record["source"]["path_abs"])
    checker.require(
        "SOURCE-HASH",
        comun.sha256_file(source) == record["source"]["sha256"],
        "SBF de origen con SHA-256 del manifiesto",
    )
    checker.require(
        "CONFIG-VERSION",
        config["target_record"] == comun.TARGET_RECORD and config["stage"] == 1,
        "config %s para %s" % (config["version"], config["target_record"]),
    )

    # 2. Registro de calibracion.
    registry_path = comun.ETAPA1 / "calibration_registry.json"
    checker.require("REGISTRY-EXISTS", registry_path.is_file(), str(registry_path))
    registry = comun.load_json(registry_path)
    checker.require(
        "REGISTRY-STATUS",
        registry["status"] == "PARCIAL",
        "estado declarado %s" % registry["status"],
    )
    checker.require(
        "REGISTRY-BANDS",
        sorted(registry["bands"]) == ["D0", "D1"],
        "bandas %s" % sorted(registry["bands"]),
    )

    for band in ("D0", "D1"):
        block = registry["bands"][band]
        channels = [row["channel"] for row in block["channels"]]
        checker.require(
            "REGISTRY-CHANNELS-%s" % band,
            sorted(channels) == sorted(comun.CHANNELS),
            "%s: %s" % (band, channels),
        )
        checker.require(
            "REGISTRY-COUNT-%s" % band,
            block["interp_points"] >= 8,
            "%s: %d puntos interpolados" % (band, block["interp_points"]),
        )
        band_ok = True
        low, high = block["review_range_hz"]
        tol = 1e-6 * max(1.0, abs(low), abs(high))
        details = []
        for row in block["channels"]:
            path = comun.DEFAULT_SOFTWARE_ROOT / row["clb"]["path_ref"]
            checks = {
                "file": path.is_file(),
                "sha": path.is_file() and comun.sha256_file(path) == row["clb"]["sha256"],
                "gain": row["table_gain"] == 1.0,
                "support": row["support_covered"],
                "range": row["frequency_min_hz"] <= low + tol
                and row["frequency_max_hz"] >= high - tol,
                "phase": row["audit"]["phase_continuous"],
            }
            if not all(checks.values()):
                details.append("%s:%s" % (row["channel"], [k for k, v in checks.items() if not v]))
            band_ok &= all(checks.values())
        checker.require(
            "REGISTRY-CHANNEL-FILES-%s" % band,
            band_ok,
            "%s: hashes, gain=1.0, cobertura y continuidad%s"
            % (band, "" if band_ok else " (%s)" % "; ".join(details)),
        )

    e_rows = [
        row
        for band in ("D0", "D1")
        for row in registry["bands"][band]["channels"]
        if row["channel"] == "Ex"
    ]
    splice_ok = all(
        row["audit"]["splice_detected"]
        and len(row["audit"]["outliers_removed"]) == 1
        and abs(row["audit"]["outliers_removed"][0]["frequency_hz"] - 10000.0) < 1.0
        for row in e_rows
    )
    checker.require(
        "REGISTRY-SPLICE-EX",
        splice_ok,
        "empalme de 10 kHz detectado y punto atipico excluido en Ex",
    )
    h_rows = [
        row
        for band in ("D0", "D1")
        for row in registry["bands"][band]["channels"]
        if row["channel"] == "Hx"
    ]
    checker.require(
        "REGISTRY-H-NO-OUTLIER",
        all(len(row["audit"]["outliers_removed"]) == 0 for row in h_rows),
        "Hx sin atipicos de fase",
    )
    corrections = registry["corrections_applied_to_export"]
    checker.require(
        "REGISTRY-ONLY-ADC",
        corrections["adc_to_uv"] is True
        and not any(corrections[key] for key in ("gain", "clb_amplitude", "clb_phase", "dipole_length", "polarity", "orientation")),
        "solo adc_to_uv marcado como aplicado",
    )

    # 3. Respuestas interpoladas.
    for band in ("D0", "D1"):
        path, fields, rows = load_response(band)
        low, high = comun.band_range(config, band)
        effective_low, effective_high = registry["bands"][band]["effective_range_hz"]
        frequencies = np.array([float(row["frequency_hz"]) for row in rows])
        checker.require(
            "RESP-FILE-%s" % band,
            path.is_file() and len(rows) == registry["bands"][band]["interp_points"],
            "%s: %d filas" % (band, len(rows)),
        )
        checker.require(
            "RESP-GRID-%s" % band,
            np.all(np.diff(frequencies) > 0)
            and abs(frequencies[0] - effective_low) <= 1e-9
            and abs(frequencies[-1] - effective_high) <= 1e-6
            and effective_low <= low * (1.0 + 1e-6)
            and effective_high >= high * (1.0 - 1e-6),
            "%s: grilla %.9g-%.9g Hz monotona y cubre la banda" % (band, frequencies[0], frequencies[-1]),
        )
        finite = True
        positive = True
        continuity = True
        for channel in comun.CHANNELS:
            amp = np.array([float(row[channel + "_amplitude"]) for row in rows])
            phase = np.array([float(row[channel + "_phase_deg"]) for row in rows])
            finite &= bool(np.all(np.isfinite(amp)) and np.all(np.isfinite(phase)))
            positive &= bool(np.all(amp > 0))
            continuity &= bool(np.max(np.abs(np.diff(phase))) <= float(config["calibration"]["phase_continuity_deg"]))
        checker.require(
            "RESP-VALUES-%s" % band,
            finite and positive,
            "%s: amplitudes positivas y finitas" % band,
        )
        checker.require(
            "RESP-CONTINUITY-%s" % band,
            continuity,
            "%s: fase continua en la grilla interpolada" % band,
        )

    # 4. Auditoria de ganancias.
    audit = comun.load_json(comun.ETAPA1 / "auditoria_ganancias.json")
    checker.require(
        "GAIN-DIRECTORIES",
        len(audit["directory_map"]) == 9 and sum(1 for row in audit["directory_map"] if row["selected"]) == 1,
        "9 directorios y uno seleccionado",
    )
    checker.require(
        "GAIN-ROUNDING",
        abs(audit["selected_label_delta_pct"] - 1.2214) < 0.001,
        "etiqueta 1.8 vs 1.77828: %.4f %%" % audit["selected_label_delta_pct"],
    )
    checker.require(
        "GAIN-NO-SECTIONS",
        audit["table_structure"]["files_with_gain_sections"] == 0
        and audit["table_structure"]["unique_table_gain_values"] == [1.0],
        "73 archivos con una sola tabla gain=1.0",
    )
    probes = {row["channel"]: row for row in audit["amplitude_probe"]}
    checker.require(
        "GAIN-PROBES",
        sorted(probes) == sorted(comun.CHANNELS),
        "sondas para %s" % sorted(probes),
    )
    e_spread = probes["Ex"]["amplitude_100_hz"]["spread_pct"]
    h_spread = probes["Hx"]["amplitude_100_hz"]["spread_pct"]
    checker.require(
        "GAIN-SPREAD",
        e_spread > 10.0 and h_spread < 10.0,
        "dispersion E %.2f %%, H %.2f %% a 100 Hz" % (e_spread, h_spread),
    )
    checker.require(
        "GAIN-UNIT-AMBIGUITY",
        abs(audit["unit_interpretation"]["existing_code_ratio_to_literal"] - 1.2566) < 0.001,
        "cociente V/(A/m) vs mV/nT documentado",
    )

    # 5. QC.
    qc = comun.load_json(comun.ETAPA1 / "qc_D0_D1.json")
    checker.require(
        "QC-BANDS",
        sorted(qc["bands"]) == ["D0", "D1"],
        "bandas %s" % sorted(qc["bands"]),
    )
    for band in ("D0", "D1"):
        block = qc["bands"][band]
        # La duracion real se lee del SBF: D0 5400 s, D1 45 s.
        duration_expected = 5400.0 if band == "D0" else 45.0
        expected = int(round(duration_expected * float(config["bands"][band]["sample_rate_hz"])))
        checker.require(
            "QC-LENGTH-%s" % band,
            block["n_samples"] == expected,
            "%s: %d muestras" % (band, block["n_samples"]),
        )
        checks = block["checks"]
        required = {
            "clipping",
            "canales_muertos",
            "valores_pegados",
            "relleno_de_ceros",
            "saltos",
            "muestras_faltantes",
            "transitorios_conmutacion",
        }
        checker.require(
            "QC-CHECKS-%s" % band,
            required.issubset(checks),
            "%s: %d comprobaciones" % (band, len(checks)),
        )
        invalid_ok = all(
            checks[key]["estado"] == "PASA"
            for key in ("clipping", "canales_muertos", "valores_pegados", "relleno_de_ceros", "muestras_faltantes")
        )
        checker.require(
            "QC-NO-INVALID-%s" % band,
            invalid_ok,
            "%s: sin clipping, muertos, pegados, ceros ni huecos" % band,
        )
        checker.require(
            "QC-JUMPS-REPORTED-%s" % band,
            checks["saltos"]["enmascarados"] is False and sum(checks["saltos"]["counts"].values()) > 0,
            "%s: saltos reportados y no enmascarados" % band,
        )
        mask = np.load(comun.ETAPA1 / block["bad_mask"]["file"])
        packed_ok = True
        total_bad = 0
        for channel in comun.CHANNELS:
            key = "bad_" + channel
            if key not in mask:
                packed_ok = False
                continue
            unpacked = comun.unpack_bool(mask[key], int(mask["n_samples"]), "little")
            packed_ok &= len(unpacked) == block["n_samples"]
            total_bad += int(unpacked.sum())
        checker.require(
            "QC-MASK-%s" % band,
            packed_ok and total_bad == 0,
            "%s: mascara empaquetada, %d muestras invalidas" % (band, total_bad),
        )

    # 6. Exportacion.
    export = comun.load_json(comun.ETAPA1 / "exportaciones" / "exportaciones.json")
    checker.require(
        "EXPORT-BANDS",
        sorted(export["bands"]) == ["D0", "D1"],
        "bandas %s" % sorted(export["bands"]),
    )
    SBFReader, _ = comun.import_armt()
    with SBFReader(record["source"]["path_abs"]) as acq:
        for band in ("D0", "D1"):
            block = export["bands"][band]
            path = comun.ETAPA1 / block["file"]
            checker.require(
                "EXPORT-FILE-%s" % band,
                path.is_file() and comun.sha256_file(path) == block["sha256"],
                "%s: %s" % (band, path.name),
            )
            data = np.load(path, mmap_mode="r")
            checker.require(
                "EXPORT-SHAPE-%s" % band,
                list(data.shape) == block["shape"] and str(data.dtype) == block["dtype"],
                "%s: %s %s" % (band, data.shape, data.dtype),
            )
            checker.require(
                "EXPORT-UNITS-%s" % band,
                block["units"] == "uV" and block["formula"] == "uV = counts * adc_to_uv",
                "%s: unidades y formula" % band,
            )
            nonfinite = sum(row["nonfinite"] for row in block["stats"].values())
            checker.require(
                "EXPORT-FINITE-%s" % band,
                nonfinite == 0,
                "%s: %d valores no finitos" % (band, nonfinite),
            )
            # Verificacion de escala contra el SBF en el primer bloque.
            trace_index = int(config["bands"][band]["trace_index"])
            adc = np.asarray(block["adc_to_uv"], dtype=np.float64)
            counts = acq.read_samples(
                trace_index,
                start=block["start_sample"],
                stop=block["start_sample"] + 1000,
                channels=block["channels"],
                units="counts",
            )
            expected = (counts.astype(np.float64) * adc).astype(np.float32)
            diff = np.abs(expected - np.asarray(data[:1000]))
            checker.require(
                "EXPORT-SCALE-%s" % band,
                float(diff.max()) <= 1e-3,
                "%s: max |diff| = %.3e uV" % (band, float(diff.max())),
            )
            # Estadisticas contra el archivo completo.
            full = np.asarray(data)
            checker.require(
                "EXPORT-STATS-%s" % band,
                abs(float(full.min()) - min(row["min_uV"] for row in block["stats"].values())) < 1e-3
                and abs(float(full.max()) - max(row["max_uV"] for row in block["stats"].values())) < 1e-3,
                "%s: min/max coherentes" % band,
            )
            del full, data
        verification = comun.ETAPA1 / export["verification_csv"]
        with open(verification, newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        max_diff = max((float(row["abs_diff_uV"]) for row in rows), default=float("inf"))
        checker.require(
            "EXPORT-VERIFICATION",
            rows and max_diff <= 1e-3,
            "%d muestras de verificacion, max |diff| = %.3e uV" % (len(rows), max_diff),
        )

    # 7. Presupuesto instrumental.
    budget_path = comun.ETAPA1 / "presupuesto_instrumental.csv"
    with open(budget_path, newline="", encoding="utf-8") as stream:
        budget = list(csv.DictReader(stream))
    ids = {row["id"] for row in budget}
    expected_ids = {"P1-%02d" % i for i in range(1, 25)}
    checker.require(
        "BUDGET-ROWS",
        expected_ids.issubset(ids),
        "%d filas, IDs P1-01..P1-24" % len(budget),
    )
    by_id = {row["id"]: row for row in budget}
    checker.require(
        "BUDGET-ADC-APPLIED",
        by_id["P1-01"]["aplicado_en_exportacion"] == "si"
        and by_id["P1-02"]["aplicado_en_exportacion"] == "si",
        "ADC aplicado en D0 y D1",
    )
    checker.require(
        "BUDGET-NOT-APPLIED",
        by_id["P1-03"]["aplicado_en_exportacion"] == "no"
        and by_id["P1-05"]["aplicado_en_exportacion"] == "no"
        and by_id["P1-13"]["aplicado_en_exportacion"] == "no",
        "ganancia, respuesta y dipolo no aplicados",
    )
    checker.require(
        "BUDGET-SUMMARY",
        by_id["P1-24"]["estado"] == "parcial"
        and "no certificable" in by_id["P1-24"]["valor"],
        "resumen declara presupuesto no certificable",
    )

    # 8. Construccion y estado.
    construction = comun.load_json(comun.ETAPA1 / "construccion_etapa1.json")
    checker.require(
        "BUILD-STEPS",
        construction["status"] == "COMPLETADO" and len(construction["steps"]) == 4,
        "%d pasos, estado %s" % (len(construction["steps"]), construction["status"]),
    )
    checker.require(
        "BUILD-SOURCE",
        construction["source_unchanged"] is True and construction["synthetic_leaks"] == 0,
        "fuente sin cambios y sin fuga sintetica",
    )
    checker.require(
        "P1-STATUS",
        registry["status"] == "PARCIAL" and len(registry["status_reasons"]) >= 4,
        "P1 PARCIAL con %d razones" % len(registry["status_reasons"]),
    )
    checker.require(
        "B-P0-05-CLOSED",
        any(row["id"] == "B-P0-05" for row in qc["blockers_closed"]),
        "QC irreversible cerrado para el registro objetivo",
    )
    checker.require(
        "B-P0-04-OPEN",
        "B-P0-04" in registry["blockers"],
        "validez de calibracion sigue abierta",
    )
    checker.require(
        "P2-T-BLOCKED",
        record["tem_link"]["status"] != "verificado",
        "vinculo TEM-ARMT sigue no verificado",
    )

    # 9. Fuga sintetica en P1.
    leaks = []
    reports = {"construccion_etapa1.json"}
    for path in comun.ETAPA1.rglob("*"):
        if (
            path.is_file()
            and path.name not in reports
            and not path.name.startswith("validacion_")
            and path.suffix.lower() in (".json", ".csv")
        ):
            if "SYN-" in path.read_text(encoding="utf-8", errors="replace"):
                leaks.append(path.name)
    checker.require("P1-NO-SYNTHETIC", not leaks, "sin SYN- en entregables de datos P1")

    # Observaciones honestas.
    checker.observe(
        "OBS-INDEPENDENT-EXPORT",
        "No hay exportacion independiente del fabricante para comparar signo, bits e intercalado (P1.1).",
    )
    checker.observe(
        "OBS-CALIBRATION-VALIDITY",
        "Las 73 .clb no tienen fecha, certificado ni seccion de ganancia; B-P0-04 sigue abierto.",
    )
    checker.observe(
        "OBS-GAIN-AMBIGUITY",
        "La amplitud electrica no es reproducible entre directorios (hasta ~32 % en D1); no se aplica ganancia.",
    )
    checker.observe(
        "OBS-H-UNITS",
        "La unidad magnetica V/(A/m) del manual no coincide con el factor 1000 del codigo existente.",
    )
    checker.observe(
        "OBS-DIPOLE",
        "La longitud de dipolo de 20 m esta declarada en el SBF, no verificada en campo.",
    )
    checker.observe(
        "OBS-TIMEZONE",
        "La zona horaria de las marcas locales sigue sin declarar (B-P0-07).",
    )

    summary = {
        "total": len(checker.checks),
        "pasa": sum(1 for row in checker.checks if row["estado"] == "PASA"),
        "falla": sum(1 for row in checker.checks if row["estado"] == "FALLA"),
        "observaciones": sum(1 for row in checker.checks if row["estado"] == "OBSERVACION"),
    }
    if summary["falla"]:
        result = "FALLA"
    elif summary["observaciones"]:
        result = "APROBADO_CON_OBSERVACIONES"
    else:
        result = "APROBADO"

    payload = {
        "validacion_version": "1.0.0",
        "generated_at_utc": comun.utc_now(),
        "stage": 1,
        "target_record": comun.TARGET_RECORD,
        "p1_status_declarado": registry["status"],
        "p1_status_calculado": "PARCIAL",
        "resultado": result,
        "summary": summary,
        "checks": checker.checks,
        "blockers_cerrados": [
            {
                "id": "B-P0-05",
                "alcance": "registro %s, D0/D1" % comun.TARGET_RECORD,
                "evidencia": "qc_D0_D1.json, mascaras_QC_D0/D1.npz",
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
        "p2t_status": "BLOQUEADO",
        "observaciones": [row for row in checker.checks if row["estado"] == "OBSERVACION"],
    }
    comun.dump_json(comun.ETAPA1 / "validacion_etapa1.json", payload)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    config = comun.load_config(args.config)
    checker = Checker()
    payload = validate(config, checker)
    print("validacion P1: %s" % payload["resultado"])
    print(
        "  %d comprobaciones: %d pasan, %d fallan, %d observaciones"
        % (
            payload["summary"]["total"],
            payload["summary"]["pasa"],
            payload["summary"]["falla"],
            payload["summary"]["observaciones"],
        )
    )
    print("  P1 declarado: %s" % payload["p1_status_declarado"])
    for row in payload["checks"]:
        if row["estado"] == "FALLA":
            print("  FALLA %s: %s" % (row["id"], row["detalle"]))
    return 0 if payload["summary"]["falla"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
