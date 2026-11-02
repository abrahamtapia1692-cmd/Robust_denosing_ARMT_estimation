#!/usr/bin/env python3
"""Valida el banco sintetico de contrato y su aislamiento del piloto P0.

Comprueba formato, determinismo, semantica de escenarios, calculo de soporte y
que ningun identificador ``SYN-`` haya entrado en el manifiesto o en las
particiones reales.
"""

import argparse
import os
import tempfile
from pathlib import Path

import numpy as np

from comun import (
    DEFAULT_MODEL,
    DEFAULT_OUT_DIR,
    REAL_MANIFEST,
    REAL_SPLITS,
    file_entry,
    load_parse_tem,
    load_real_context,
    read_header_value,
    read_json,
    sha256_file,
    utc_now,
    write_json,
)
from modelo_surrogate import (
    APPLICATIONS,
    STATUSES,
    frequency_grid,
)
import generar_tem_sintetico


TMP_ROOT = Path(
    os.environ.get(
        "ARMT_TMP", r"C:\Users\Geotem_User\AppData\Local\Temp\opencode"
    )
)
if not TMP_ROOT.exists():
    TMP_ROOT = Path(tempfile.gettempdir())


class Checker:
    def __init__(self):
        self.checks = []

    def add(self, check_id, ok, detail):
        self.checks.append(
            {
                "id": check_id,
                "estado": "PASA" if ok else "FALLA",
                "detalle": detail,
            }
        )
        return ok


def _scenario_by_id(manifest, scenario_id):
    for scenario in manifest["scenarios"]:
        if scenario["id"] == scenario_id:
            return scenario
    raise KeyError(scenario_id)


def _band_contains(model, band, f_hz):
    low, high = [float(value) for value in model["bands_hz"][band]]
    return (low - 1e-6) <= f_hz <= (high + 1e-6)


def check_real_inputs(checker, manifest, real_context):
    errors = []
    inputs = manifest.get("real_inputs", {})
    if inputs.get("manifest_sha256_p0") != real_context["p0_manifest_sha256"]:
        errors.append("manifest_sha256_p0 no coincide con la validacion P0")
    if inputs.get("splits_sha256_p0") != real_context["p0_splits_sha256"]:
        errors.append("splits_sha256_p0 no coincide con la validacion P0")
    if inputs.get("manifest", {}).get("sha256") != real_context["manifest_sha256"]:
        errors.append("El hash registrado del manifiesto P0 no es el actual")
    if inputs.get("splits", {}).get("sha256") != real_context["splits_sha256"]:
        errors.append("El hash registrado de splits.csv no es el actual")
    checker.add(
        "S-03",
        not errors,
        "Insumos P0 sin cambios y hashes coherentes"
        if not errors
        else "; ".join(errors),
    )

    errors = []
    if manifest.get("target_record", {}).get("record_id") != real_context["record_id"]:
        errors.append("record_id objetivo distinto")
    if manifest.get("target_record", {}).get("split") != real_context["split"]:
        errors.append("split objetivo distinto")
    if real_context["split"] != "desarrollo":
        errors.append("El registro objetivo no esta en desarrollo")
    checker.add(
        "S-04",
        not errors,
        "Registro objetivo en desarrollo y declarado"
        if not errors
        else "; ".join(errors),
    )


def check_no_leak(checker):
    real_manifest = read_json(REAL_MANIFEST)
    synthetic_ids = []
    for candidate in real_manifest.get("tem_candidates", []):
        synthetic_ids.append(candidate.get("sounding_id"))
    for record in real_manifest.get("armt_records", []):
        synthetic_ids.append(record.get("tem_link", {}).get("sounding_id"))
    leaked = [
        value
        for value in synthetic_ids
        if value and str(value).upper().startswith("SYN-")
    ]
    checker.add(
        "S-05",
        not leaked,
        "Sin IDs SYN- en el manifiesto P0"
        if not leaked
        else "IDs sinteticos filtrados: %s" % leaked,
    )

    text = REAL_SPLITS.read_text(encoding="utf-8")
    checker.add(
        "S-06",
        "SYN-" not in text.upper(),
        "Sin IDs SYN- en splits.csv"
        if "SYN-" not in text.upper()
        else "splits.csv contiene IDs sinteticos",
    )


def check_synthetic_flags(checker, manifest, truths, supports):
    errors = []
    objects = [("manifiesto", manifest)]
    objects.extend(("verdad %s" % key, value) for key, value in truths.items())
    objects.extend(("soporte %s" % key, value) for key, value in supports.items())
    for label, obj in objects:
        if obj.get("synthetic") is not True:
            errors.append("%s: synthetic != true" % label)
        if obj.get("scientific_claim") is not False:
            errors.append("%s: scientific_claim != false" % label)

    quarantine = manifest.get("quarantine", {})
    for key in (
        "p2t_evidence",
        "training_labels",
        "real_manifest_modified",
        "real_splits_modified",
    ):
        if quarantine.get(key) is not False:
            errors.append("quarantine.%s != false" % key)
    checker.add(
        "S-07",
        not errors,
        "Marcas de cuarentena y no-afirmacion correctas"
        if not errors
        else "; ".join(errors),
    )


def check_tem_files(checker, manifest, model, parse_tem):
    errors_identity = []
    errors_coordinates = []
    errors_gates = []
    for scenario in manifest["scenarios"]:
        tem_id = scenario["tem_id"]
        path = Path(scenario["tem_file"]["path_abs"])
        parsed = parse_tem(path)

        if not tem_id.startswith("SYN-TEM-"):
            errors_identity.append("%s no usa prefijo SYN-TEM-" % tem_id)
        if "SER-" in tem_id.upper():
            errors_identity.append("%s parece un sondeo real" % tem_id)
        if read_header_value(path, "TEM_ID") != tem_id:
            errors_identity.append("%s: TEM_ID de cabecera distinto" % tem_id)
        if parsed["project"] != "SYNTHETIC_CONTRACT_BENCH":
            errors_identity.append("%s: PROJECT no sintetico" % tem_id)
        if "synthetic" not in (parsed["conditions"] or "").lower():
            errors_identity.append("%s: CONDITIONS sin marca sintetica" % tem_id)

        if parsed["coordinates"]["type"] != "NONE":
            errors_coordinates.append("%s: TYPE distinto de NONE" % tem_id)
        for key in ("rx_x", "rx_y", "tx_x", "tx_y", "elevation", "datum"):
            if parsed["coordinates"].get(key) is not None:
                errors_coordinates.append("%s: coordinates.%s no es null" % (tem_id, key))

        expected_gates = int(model["gates"]["count"])
        if parsed["gates"]["count"] != expected_gates:
            errors_gates.append(
                "%s: %d gates, se esperaban %d"
                % (tem_id, parsed["gates"]["count"], expected_gates)
            )
        if abs(parsed["gates"]["time_min_ms"] - float(model["gates"]["start_ms"])) > 1e-6:
            errors_gates.append("%s: tiempo minimo distinto" % tem_id)
        if abs(parsed["gates"]["time_max_ms"] - float(model["gates"]["stop_ms"])) > 1e-6:
            errors_gates.append("%s: tiempo maximo distinto" % tem_id)
        if parsed["acquisition"]["date"] is not None:
            errors_gates.append("%s: fecha de adquisicion no nula" % tem_id)
        if parsed["acquisition"]["receiver"] != "SYNTHETIC":
            errors_gates.append("%s: receptor no declarado sintetico" % tem_id)

    checker.add(
        "S-08",
        not errors_identity,
        "Identidad TEM sintetica correcta"
        if not errors_identity
        else "; ".join(errors_identity),
    )
    checker.add(
        "S-09",
        not errors_coordinates,
        "Coordenadas vacias y sin datum"
        if not errors_coordinates
        else "; ".join(errors_coordinates),
    )
    checker.add(
        "S-10",
        not errors_gates,
        "Gates, fechas y receptor sinteticos correctos"
        if not errors_gates
        else "; ".join(errors_gates),
    )


def check_truths(checker, manifest, model, truths):
    errors = []
    for scenario in manifest["scenarios"]:
        scenario_id = scenario["id"]
        truth = truths[scenario_id]
        tem_path = Path(scenario["tem_file"]["path_abs"])
        truth_path = Path(scenario["truth_file"]["path_abs"])

        if truth.get("scenario") != scenario_id:
            errors.append("%s: scenario distinto" % scenario_id)
        if truth.get("tem_id") != scenario["tem_id"]:
            errors.append("%s: tem_id distinto" % scenario_id)
        if truth.get("target_record") != model["target_record"]:
            errors.append("%s: target_record distinto" % scenario_id)
        if truth.get("target_split") != model["target_split"]:
            errors.append("%s: target_split distinto" % scenario_id)

        gates = np.asarray(truth.get("gates_ms", []), dtype=float)
        if gates.size != int(model["gates"]["count"]):
            errors.append("%s: numero de gates distinto" % scenario_id)
        elif not np.all(np.diff(gates) > 0):
            errors.append("%s: gates no estrictamente crecientes" % scenario_id)

        voltage = np.asarray(truth.get("voltage_nv_per_a", []), dtype=float)
        if voltage.size != gates.size:
            errors.append("%s: voltaje de longitud distinta" % scenario_id)
        elif not np.all(np.isfinite(voltage)) or not np.all(voltage > 0):
            errors.append("%s: voltaje no finito o no positivo" % scenario_id)

        resistivity = np.asarray(truth.get("resistivity_ohm_m", []), dtype=float)
        if resistivity.size != gates.size:
            errors.append("%s: resistividad de longitud distinta" % scenario_id)
        elif not np.all(np.isfinite(resistivity)):
            errors.append("%s: resistividad no finita" % scenario_id)

        if truth.get("tem_file_sha256") != sha256_file(tem_path):
            errors.append("%s: hash del TEM no coincide" % scenario_id)
        if truth.get("tem_file_size_bytes") != tem_path.stat().st_size:
            errors.append("%s: tamano del TEM no coincide" % scenario_id)
        if not truth_path.exists():
            errors.append("%s: falta la verdad" % scenario_id)

    checker.add(
        "S-11",
        not errors,
        "Verdades sinteticas coherentes con sus archivos"
        if not errors
        else "; ".join(errors),
    )

    errors = []
    s0 = truths["S0"]
    if s0.get("kernels") != []:
        errors.append("S0 debe tener kernels vacios")
    if s0.get("resistivity_interpretable") is not False:
        errors.append("S0 no debe declarar resistividad interpretable")
    if s0.get("data_quality") != "sin_decaimiento_util":
        errors.append("S0 debe declarar ausencia de decaimiento util")

    s1 = truths["S1"]
    if not s1.get("kernels"):
        errors.append("S1 debe tener kernels no vacios")
    if s1.get("resistivity_interpretable") is not True:
        errors.append("S1 debe declarar resistividad interpretable")
    if s1.get("data_quality") != "surrogate_capas":
        errors.append("S1 debe declarar surrogate de capas")

    for index, scenario_id in enumerate(("S0", "S1")):
        expected_seed = int(model["noise"]["seed"]) + index
        if truths[scenario_id].get("seed") != expected_seed:
            errors.append("%s: semilla distinta de %d" % (scenario_id, expected_seed))

    checker.add(
        "S-12",
        not errors,
        "Semantica de S0/S1 y semillas correctas"
        if not errors
        else "; ".join(errors),
    )


def check_determinism(checker, manifest, model, real_context, model_path):
    errors = []
    with tempfile.TemporaryDirectory(prefix="syn_bench_", dir=str(TMP_ROOT)) as tmp:
        temp_manifest = generar_tem_sintetico.build(
            model, real_context, Path(tmp), model_path
        )
        for scenario in temp_manifest["scenarios"]:
            scenario_id = scenario["id"]
            real_scenario = _scenario_by_id(manifest, scenario_id)
            real_tem = Path(real_scenario["tem_file"]["path_abs"])
            temp_tem = Path(scenario["tem_file"]["path_abs"])
            if sha256_file(temp_tem) != sha256_file(real_tem):
                errors.append("%s: TEM no determinista" % scenario_id)
            real_truth = Path(real_scenario["truth_file"]["path_abs"])
            temp_truth = Path(scenario["truth_file"]["path_abs"])
            if sha256_file(temp_truth) != sha256_file(real_truth):
                errors.append("%s: verdad no determinista" % scenario_id)
    checker.add(
        "S-13",
        not errors,
        "Regeneracion determinista de TEM y verdad"
        if not errors
        else "; ".join(errors),
    )


def check_support_metadata(checker, manifest, model, truths, supports):
    errors = []
    expected_frequencies = len(frequency_grid(model))
    for scenario in manifest["scenarios"]:
        scenario_id = scenario["id"]
        support = supports[scenario_id]
        truth = truths[scenario_id]
        truth_path = Path(scenario["truth_file"]["path_abs"])

        if support.get("support_version") != "SYN-FS-1.0.0":
            errors.append("%s: version de soporte distinta" % scenario_id)
        if support.get("sounding_id") != scenario["tem_id"]:
            errors.append("%s: sounding_id distinto" % scenario_id)
        if support.get("target_record") != model["target_record"]:
            errors.append("%s: target_record distinto" % scenario_id)
        if support.get("truth_sha256") != sha256_file(truth_path):
            errors.append("%s: hash de verdad distinto" % scenario_id)
        if support.get("model_sha256") != truth.get("model_sha256"):
            errors.append("%s: hash de modelo distinto" % scenario_id)
        if len(support.get("frequencies", [])) != expected_frequencies:
            errors.append(
                "%s: %d frecuencias, se esperaban %d"
                % (scenario_id, len(support.get("frequencies", [])), expected_frequencies)
            )

    checker.add(
        "S-14",
        not errors,
        "Metadatos de soporte coherentes"
        if not errors
        else "; ".join(errors),
    )


def check_support_frequencies(checker, model, supports):
    errors = []
    support_cfg = model["support"]
    dead_low, dead_high = [float(value) for value in model["amt_dead_band_hz"]]
    for scenario_id, support in supports.items():
        for record in support.get("frequencies", []):
            f_hz = float(record["f_hz"])
            band = record["band"]
            status = record["status"]
            application = record["aplicacion"]
            observation = record["observacion_amt"]
            n_gates = int(record["n_gates"])
            sensitivity_max = float(record["sensitivity_max"])

            if band not in ("D0", "D1"):
                errors.append("%s: banda %s invalida" % (scenario_id, band))
                continue
            if not _band_contains(model, band, f_hz):
                errors.append("%s: %.3f Hz fuera de %s" % (scenario_id, f_hz, band))
            if status not in STATUSES:
                errors.append("%s: status %s invalido" % (scenario_id, status))
            if application not in APPLICATIONS:
                errors.append("%s: aplicacion %s invalida" % (scenario_id, application))
            if observation not in ("favorable", "penalizada"):
                errors.append("%s: observacion %s invalida" % (scenario_id, observation))
            if n_gates < 0 or sensitivity_max < 0:
                errors.append("%s: valores negativos" % scenario_id)

            if status == "respaldada" and not (
                n_gates >= int(support_cfg["min_gates"])
                and sensitivity_max >= float(support_cfg["threshold_supported"])
            ):
                errors.append("%s: respaldada sin sensibilidad/gates" % scenario_id)
            if status == "condicional" and not (
                n_gates >= 1
                and sensitivity_max >= float(support_cfg["threshold_conditional"])
            ):
                errors.append("%s: condicional sin sensibilidad/gates" % scenario_id)
            if status == "no_evaluada" and n_gates != 0:
                errors.append("%s: no_evaluada con gates" % scenario_id)
            if status == "no_respaldada" and not (
                n_gates >= 1
                and sensitivity_max < float(support_cfg["threshold_conditional"])
            ):
                errors.append("%s: no_respaldada incoherente" % scenario_id)

            if application == "habilitada" and not (
                status == "respaldada" and observation == "favorable"
            ):
                errors.append("%s: habilitada sin respaldo favorable" % scenario_id)
            if application == "condicional" and not (
                (status == "respaldada" and observation == "penalizada")
                or status == "condicional"
            ):
                errors.append("%s: condicional incoherente" % scenario_id)
            if application == "no_habilitada" and status not in (
                "no_respaldada",
                "no_evaluada",
            ):
                errors.append("%s: no_habilitada incoherente" % scenario_id)

            expected_observation = (
                "penalizada" if dead_low <= f_hz <= dead_high else "favorable"
            )
            if observation != expected_observation:
                errors.append("%s: observacion AMT incoherente a %.3f Hz" % (scenario_id, f_hz))

    checker.add(
        "S-15",
        not errors,
        "Frecuencias y transiciones de soporte coherentes"
        if not errors
        else "; ".join(errors[:20]),
    )


def check_support_summary(checker, model, supports):
    errors = []
    for scenario_id, support in supports.items():
        summary = support["summary"]
        frequencies = support["frequencies"]
        counts = {
            name: sum(1 for record in frequencies if record["status"] == name)
            for name in STATUSES
        }
        applications = {
            name: sum(1 for record in frequencies if record["aplicacion"] == name)
            for name in APPLICATIONS
        }
        if summary.get("counts") != counts:
            errors.append("%s: counts no coincide" % scenario_id)
        if summary.get("application_counts") != applications:
            errors.append("%s: application_counts no coincide" % scenario_id)
        if summary.get("supported_any") != (counts["respaldada"] > 0):
            errors.append("%s: supported_any incoherente" % scenario_id)
        if summary.get("admissible_any") != (applications["habilitada"] > 0):
            errors.append("%s: admissible_any incoherente" % scenario_id)
        if summary.get("conditional_any") != (applications["condicional"] > 0):
            errors.append("%s: conditional_any incoherente" % scenario_id)
        if summary.get("g0_trigger") != (not summary.get("admissible_any")):
            errors.append("%s: g0_trigger incoherente" % scenario_id)
        if summary.get("empty_intersection") != (
            not (summary.get("admissible_any") or summary.get("conditional_any"))
        ):
            errors.append("%s: empty_intersection incoherente" % scenario_id)
        if set(summary.get("bands", {})) != {"D0", "D1"}:
            errors.append("%s: bandas de resumen distintas" % scenario_id)
            continue
        for band in ("D0", "D1"):
            band_frequencies = [
                record for record in frequencies if record["band"] == band
            ]
            band_counts = {
                name: sum(1 for record in band_frequencies if record["status"] == name)
                for name in STATUSES
            }
            if summary["bands"][band].get("counts") != band_counts:
                errors.append("%s %s: counts por banda no coincide" % (scenario_id, band))

    checker.add(
        "S-16",
        not errors,
        "Resumen de soporte consistente"
        if not errors
        else "; ".join(errors[:20]),
    )


def check_scenario_expectations(checker, supports):
    s0 = supports["S0"]["summary"]
    s0_ok = (
        s0.get("supported_any") is False
        and s0.get("admissible_any") is False
        and s0.get("conditional_any") is False
        and s0.get("empty_intersection") is True
        and s0.get("g0_trigger") is True
        and s0.get("supported_ranges_hz") == []
    )
    checker.add(
        "S-17",
        s0_ok,
        "S0 sin soporte, interseccion vacia y G0 activado"
        if s0_ok
        else "S0 no cumple la expectativa de soporte vacio: %r" % s0,
    )

    s1 = supports["S1"]["summary"]
    d0 = s1.get("bands", {}).get("D0", {})
    d1 = s1.get("bands", {}).get("D1", {})
    s1_ok = (
        s1.get("supported_any") is True
        and s1.get("admissible_any") is True
        and s1.get("empty_intersection") is False
        and s1.get("g0_trigger") is False
        and d0.get("application_counts", {}).get("habilitada", 0) > 0
        and d1.get("application_counts", {}).get("habilitada", 0) == 0
        and d1.get("application_counts", {}).get("condicional", 0) > 0
    )
    checker.add(
        "S-18",
        s1_ok,
        "S1 con soporte D0 habilitado y D1 condicional"
        if s1_ok
        else "S1 no cumple la expectativa de soporte parcial: %r" % s1,
    )

    s1_frequencies = supports["S1"]["frequencies"]
    dead_band_enabled = [
        record
        for record in s1_frequencies
        if record["aplicacion"] == "habilitada"
        and 1000.0 <= float(record["f_hz"]) <= 5000.0
    ]
    checker.add(
        "S-19",
        not dead_band_enabled,
        "Ninguna frecuencia de 1-5 kHz queda habilitada"
        if not dead_band_enabled
        else "Habilitadas en banda muerta: %s"
        % [record["f_hz"] for record in dead_band_enabled],
    )


def check_manifest_support(checker, manifest):
    errors = []
    support = manifest.get("support", {})
    if support.get("status") != "calculado":
        errors.append("support.status != calculado")
    if support.get("version") != "SYN-FS-1.0.0":
        errors.append("support.version distinta")
    if len(support.get("files", [])) != 2:
        errors.append("support.files no tiene dos entradas")
    for scenario in manifest["scenarios"]:
        entry = scenario.get("support_file")
        if not entry:
            errors.append("%s sin support_file" % scenario["id"])
            continue
        path = Path(entry["path_abs"])
        if not path.exists():
            errors.append("%s: falta el archivo de soporte" % scenario["id"])
        elif sha256_file(path) != entry["sha256"]:
            errors.append("%s: hash de soporte distinto" % scenario["id"])
    checker.add(
        "S-20",
        not errors,
        "Manifiesto enlaza soportes con hashes correctos"
        if not errors
        else "; ".join(errors),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    out_dir = Path(args.dir)
    model = read_json(args.model)
    out_path = args.out or (out_dir / "validacion_sintetica.json")
    checker = Checker()

    required = [
        out_dir / "manifiesto_sintetico.json",
        out_dir / "verdad_S0.json",
        out_dir / "verdad_S1.json",
        out_dir / "soporte_S0.json",
        out_dir / "soporte_S1.json",
        out_dir / "datos" / "SYN-TEM-001.tem",
        out_dir / "datos" / "SYN-TEM-002.tem",
    ]
    missing = [str(path) for path in required if not path.exists()]
    checker.add(
        "S-01",
        not missing,
        "Archivos obligatorios presentes"
        if not missing
        else "Faltan: %s" % missing,
    )
    if missing:
        output = {
            "validation_version": "1.0.0",
            "generated_at_utc": utc_now(),
            "result": "RECHAZADO",
            "summary": {"total": 1, "pasa": 0, "falla": 1},
            "checks": checker.checks,
            "notes": ["Ejecute generar_tem_sintetico.py y calcular_soporte.py."],
        }
        write_json(out_path, output)
        print("Resultado: RECHAZADO")
        print("Faltan archivos: %s" % missing)
        return 1

    manifest = read_json(out_dir / "manifiesto_sintetico.json")
    truths = {
        "S0": read_json(out_dir / "verdad_S0.json"),
        "S1": read_json(out_dir / "verdad_S1.json"),
    }
    supports = {
        "S0": read_json(out_dir / "soporte_S0.json"),
        "S1": read_json(out_dir / "soporte_S1.json"),
    }
    checker.add("S-02", True, "Manifiesto, verdades y soportes legibles")

    real_context = load_real_context(model)
    check_real_inputs(checker, manifest, real_context)
    check_no_leak(checker)
    check_synthetic_flags(checker, manifest, truths, supports)

    parse_tem = load_parse_tem()
    check_tem_files(checker, manifest, model, parse_tem)
    check_truths(checker, manifest, model, truths)
    check_determinism(checker, manifest, model, real_context, args.model)
    check_support_metadata(checker, manifest, model, truths, supports)
    check_support_frequencies(checker, model, supports)
    check_support_summary(checker, model, supports)
    check_scenario_expectations(checker, supports)
    check_manifest_support(checker, manifest)

    failures = [check for check in checker.checks if check["estado"] == "FALLA"]
    result = "APROBADO" if not failures else "RECHAZADO"
    output = {
        "validation_version": "1.0.0",
        "generated_at_utc": utc_now(),
        "result": result,
        "summary": {
            "total": len(checker.checks),
            "pasa": len(checker.checks) - len(failures),
            "falla": len(failures),
        },
        "checks": checker.checks,
        "notes": [
            "El banco sintetico no es evidencia TEM del sitio.",
            "No cierra B-P0-03, no cierra P2-T y no habilita etiquetas de entrenamiento.",
            "S0 valida abstencion; S1 valida soporte parcial y penalizacion de la banda muerta AMT.",
            "La regeneracion determinista se comprobo en un directorio temporal.",
        ],
    }
    write_json(out_path, output)

    print("Resultado: %s" % result)
    print(
        "Checks: %d pasa, %d falla"
        % (output["summary"]["pasa"], output["summary"]["falla"])
    )
    print("Reporte: %s" % out_path.resolve())
    for failure in failures:
        print("  FALLA %s: %s" % (failure["id"], failure["detalle"]))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
