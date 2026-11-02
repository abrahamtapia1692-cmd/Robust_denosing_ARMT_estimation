#!/usr/bin/env python3
"""Valida la Etapa 0 contra el esquema, los hashes y las particiones.

Comprueba:
  - que schema.json sea un JSON Schema valido y que manifest.json lo cumpla;
  - que los hashes de SBF, calibraciones, TEM y artefactos coincidan;
  - que splits.csv sea consistente con el manifiesto y no cruce grupos;
  - que el alcance D0/D1 y la exclusion D2/D3 se respeten;
  - que el estado P0 declarado coincida con el calculado.

Uso:
    python etapa0/validar_etapa0.py
    python etapa0/validar_etapa0.py --no-source-hashes
"""

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_ETAPA = WORKSPACE / "etapa0"
DEFAULT_SOFTWARE_ROOT = Path(r"D:\ARRT_software")

SPLIT_COLUMNS = [
    "record_id",
    "split",
    "split_group",
    "campaign_group",
    "protocol_version",
    "array_index",
    "line_index",
    "station_index",
    "repeat_index",
    "campaign_year",
    "source_file",
    "sha256",
    "n_traces",
    "has_d0",
    "has_d1",
    "d0_duration_s",
    "d1_duration_s",
    "notes",
]
REQUIRED_ARTIFACTS = {
    "etapa0/schema.json",
    "etapa0/splits.csv",
    "etapa0/protocolo_validacion.md",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def resolve(entry):
    path = Path(entry["path_abs"])
    if path.exists():
        return path
    base = entry.get("path_base")
    if base == "workspace":
        return WORKSPACE / entry["path_ref"]
    if base == "software_root":
        return DEFAULT_SOFTWARE_ROOT / entry["path_ref"]
    return Path(entry["path_ref"])


class Checker:
    def __init__(self):
        self.checks = []

    def add(self, check_id, ok, detail, severity="falla"):
        self.checks.append(
            {
                "id": check_id,
                "estado": "PASA" if ok else "FALLA",
                "detalle": detail,
            }
        )
        return ok

    def observe(self, check_id, detail):
        self.checks.append({"id": check_id, "estado": "OBSERVACION", "detalle": detail})

    def fail(self, check_id, detail):
        return self.add(check_id, False, detail)


def verify_file(checker, cache, entry, check_id, label):
    path = resolve(entry)
    if not path.exists():
        return checker.fail(check_id, "%s no existe: %s" % (label, path))
    if path.stat().st_size != entry["size_bytes"]:
        return checker.fail(
            check_id,
            "%s cambió de tamano: %d != %d"
            % (label, path.stat().st_size, entry["size_bytes"]),
        )
    key = str(path.resolve())
    if key not in cache:
        cache[key] = sha256_file(path)
    if cache[key] != entry["sha256"]:
        return checker.fail(check_id, "%s cambió de SHA-256: %s" % (label, path))
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--etapa-dir", type=Path, default=DEFAULT_ETAPA)
    parser.add_argument("--no-source-hashes", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    etapa = args.etapa_dir.resolve()
    manifest_path = etapa / "manifest.json"
    schema_path = etapa / "schema.json"
    splits_path = etapa / "splits.csv"
    protocol_path = etapa / "protocolo_validacion.md"
    samples_path = etapa / "validacion_muestras.json"
    out_path = args.out or (etapa / "validacion_etapa0.json")

    checker = Checker()
    hashes = {}

    for path in (manifest_path, schema_path, splits_path, protocol_path):
        if not path.exists():
            print("Falta el archivo requerido: %s" % path, file=sys.stderr)
            return 2

    manifest = load_json(manifest_path)
    schema = load_json(schema_path)

    # 1. Esquema y validacion estructural.
    try:
        import jsonschema

        jsonschema.Draft7Validator.check_schema(schema)
        checker.add("V-01", True, "schema.json es un JSON Schema draft-07 valido")
        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(manifest), key=lambda error: list(error.path))
        if errors:
            detail = "; ".join(
                "%s: %s" % ("/".join(str(part) for part in error.path), error.message)
                for error in errors[:10]
            )
            checker.fail("V-02", "manifest.json no cumple el esquema: %s" % detail)
        else:
            checker.add("V-02", True, "manifest.json cumple schema.json")
    except ImportError:
        checker.fail("V-01", "jsonschema no esta instalado")

    # 2. Integridad de artefactos.
    artifact_refs = {item["artifact"]["path_ref"] for item in manifest.get("artifacts", [])}
    missing_artifacts = REQUIRED_ARTIFACTS - artifact_refs
    checker.add(
        "V-03",
        not missing_artifacts,
        "Artefactos obligatorios ausentes: %s" % sorted(missing_artifacts)
        if missing_artifacts
        else "Los tres artefactos obligatorios estan declarados",
    )
    artifacts_ok = True
    for item in manifest.get("artifacts", []):
        artifacts_ok &= verify_file(
            checker,
            hashes,
            item["artifact"],
            "V-04",
            "Artefacto %s" % item["artifact"]["path_ref"],
        )
    checker.add("V-04", artifacts_ok, "Hashes de artefactos verificados")

    # 3. Generador.
    generator_path = WORKSPACE / manifest["generator"]["script"]
    if not generator_path.exists():
        checker.fail("V-05", "No existe el generador %s" % generator_path)
    else:
        digest = sha256_file(generator_path)
        checker.add(
            "V-05",
            digest == manifest["generator"]["sha256"],
            "El generador coincide con el hash declarado"
            if digest == manifest["generator"]["sha256"]
            else "El generador cambio desde que se genero el manifiesto",
        )

    # 4. Hashes de fuentes.
    if not args.no_source_hashes:
        source_ok = True
        total = 0
        for record in manifest["armt_records"]:
            total += 1
            source_ok &= verify_file(
                checker,
                hashes,
                record["source"],
                "V-06",
                "SBF %s" % record["record_id"],
            )
        for entry in manifest["calibration_files"]:
            total += 1
            source_ok &= verify_file(
                checker, hashes, entry, "V-07", "Calibracion %s" % entry["path_ref"]
            )
        for candidate in manifest["tem_candidates"]:
            total += 1
            source_ok &= verify_file(
                checker,
                hashes,
                candidate["source"],
                "V-08",
                "TEM %s" % candidate["sounding_id"],
            )
        for group in ("governing_documents", "derived_products"):
            key = "documento" if group == "governing_documents" else "product"
            for item in manifest[group]:
                total += 1
                source_ok &= verify_file(
                    checker, hashes, item[key], "V-09", "%s %s" % (group, item[key]["path_ref"])
                )
        for item in manifest["software"]["modules"]:
            total += 1
            source_ok &= verify_file(
                checker, hashes, item["module"], "V-10", "Modulo %s" % item["module"]["path_ref"]
            )
        for label, entry in (
            ("Manifiesto TEM", manifest["sources"]["tem_manifest"]),
            ("Manifiesto TEM (dataset)", manifest["tem_dataset"]["source_manifest"]),
        ):
            total += 1
            source_ok &= verify_file(checker, hashes, entry, "V-11", label)
        if source_ok:
            checker.add("V-06", True, "Hashes de %d archivos de fuente verificados" % total)
    else:
        checker.observe("V-06", "Hashes de fuentes omitidos por --no-source-hashes")

    # 5. Particiones.
    with open(splits_path, encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        split_rows = list(reader)
        headers = reader.fieldnames or []
    checker.add(
        "V-12",
        headers == SPLIT_COLUMNS,
        "Cabecera de splits.csv correcta" if headers == SPLIT_COLUMNS else "Cabecera inesperada: %s" % headers,
    )

    manifest_by_id = {record["record_id"]: record for record in manifest["armt_records"]}
    row_by_id = {}
    duplicates = []
    for row in split_rows:
        if row["record_id"] in row_by_id:
            duplicates.append(row["record_id"])
        row_by_id[row["record_id"]] = row
    checker.add(
        "V-13",
        not duplicates and set(row_by_id) == set(manifest_by_id),
        "splits.csv cubre exactamente los %d registros" % len(manifest_by_id)
        if not duplicates and set(row_by_id) == set(manifest_by_id)
        else "IDs duplicados o faltantes en splits.csv: %s" % duplicates,
    )

    split_errors = []
    for record_id, row in row_by_id.items():
        record = manifest_by_id.get(record_id)
        if record is None:
            continue
        expected = {
            "split": record["split"]["split"],
            "split_group": record["split"]["split_group"],
            "campaign_group": record["split"]["campaign_group"],
            "protocol_version": record["split"]["protocol_version"],
            "array_index": str(record["settings"]["array_index"]),
            "line_index": str(record["settings"]["line_index"]),
            "station_index": str(record["settings"]["station_index"]),
            "repeat_index": str(record["settings"]["repeat_index"]),
            "campaign_year": str(record["campaign"]["year"]),
            "source_file": record["source"]["path_ref"],
            "sha256": record["source"]["sha256"],
            "n_traces": str(len(record["traces"])),
        }
        for key, value in expected.items():
            if row.get(key) != value:
                split_errors.append("%s.%s: %r != %r" % (record_id, key, row.get(key), value))
        bands = {trace["band"] for trace in record["traces"]}
        if row.get("has_d0") != ("si" if "D0" in bands else "no"):
            split_errors.append("%s.has_d0" % record_id)
        if row.get("has_d1") != ("si" if "D1" in bands else "no"):
            split_errors.append("%s.has_d1" % record_id)
    checker.add(
        "V-14",
        not split_errors,
        "Filas de splits.csv consistentes con el manifiesto"
        if not split_errors
        else "Inconsistencias: %s" % "; ".join(split_errors[:10]),
    )

    by_split = {}
    by_campaign = {}
    for row in split_rows:
        by_split.setdefault(row["split"], set()).add(row["split_group"])
        by_campaign.setdefault(row["split"], set()).add(row["campaign_group"])
    split_names = sorted(by_split)
    group_cross = []
    campaign_cross = []
    for i, first in enumerate(split_names):
        for second in split_names[i + 1 :]:
            if by_split[first] & by_split[second]:
                group_cross.append((first, second, sorted(by_split[first] & by_split[second])))
    test_campaigns = by_campaign.get("prueba", set())
    other_campaigns = by_campaign.get("desarrollo", set()) | by_campaign.get("validacion", set())
    if test_campaigns & other_campaigns:
        campaign_cross.append(sorted(test_campaigns & other_campaigns))
    checker.add(
        "V-15",
        not group_cross,
        "Grupos de sitio disjuntos entre particiones" if not group_cross else str(group_cross),
    )
    checker.add(
        "V-16",
        not campaign_cross,
        "La campana de prueba no comparte grupo con desarrollo ni validacion"
        if not campaign_cross
        else str(campaign_cross),
    )

    declared_counts = manifest["counts"]["splits"]
    computed_counts = {name: 0 for name in ("desarrollo", "validacion", "prueba")}
    for row in split_rows:
        computed_counts[row["split"]] = computed_counts.get(row["split"], 0) + 1
    checker.add(
        "V-17",
        declared_counts == computed_counts,
        "Conteos de particion coinciden" if declared_counts == computed_counts else "%r != %r" % (declared_counts, computed_counts),
    )

    # 6. Alcance y consistencia fisica.
    scope = manifest["scope"]
    checker.add(
        "V-18",
        scope["bandas_incluidas"] == ["D0", "D1"]
        and scope["bandas_excluidas"] == ["D2", "D3"]
        and scope["rmt_portadoras"] == "fuera_de_alcance",
        "Alcance D0/D1 y exclusion D2/D3/RMT declarados",
    )
    scope_errors = []
    for record in manifest["armt_records"]:
        bands = {}
        for trace in record["traces"]:
            bands[trace["band"]] = trace
            if trace["in_scope"] != (trace["band"] in ("D0", "D1")):
                scope_errors.append("%s.%s.in_scope" % (record["record_id"], trace["band"]))
        if "D0" not in bands or "D1" not in bands:
            scope_errors.append("%s sin D0/D1" % record["record_id"])
    checker.add(
        "V-19",
        not scope_errors,
        "Cada registro tiene D0 y D1 y solo esas bandas estan in_scope"
        if not scope_errors
        else "; ".join(scope_errors),
    )
    checker.add(
        "V-20",
        manifest["counts"]["armt_records"] == len(manifest["armt_records"])
        and manifest["counts"]["armt_traces"]
        == sum(len(record["traces"]) for record in manifest["armt_records"]),
        "Conteos de registros y trazas coinciden",
    )

    # 7. Incognitas y enlaces TEM.
    required_unknowns = {"U-%02d" % index for index in range(1, 14)}
    unknown_ids = {item["id"] for item in manifest["unknowns"]}
    checker.add(
        "V-21",
        required_unknowns <= unknown_ids,
        "Incognitas U-01 a U-13 declaradas"
        if required_unknowns <= unknown_ids
        else "Faltan incognitas: %s" % sorted(required_unknowns - unknown_ids),
    )
    link_errors = []
    for record in manifest["armt_records"]:
        if record["site"]["site_id"] is not None or record["site"]["site_name"] is not None:
            link_errors.append("%s declara sitio sin evidencia" % record["record_id"])
        if record["site"]["latitude_deg"] is not None or record["site"]["longitude_deg"] is not None:
            link_errors.append("%s declara coordenadas sin politica" % record["record_id"])
        link = record["tem_link"]
        if link["status"] != "no_verificado" and not link.get("evidence"):
            link_errors.append("%s vincula TEM sin evidencia" % record["record_id"])
    for candidate in manifest["tem_candidates"]:
        if candidate["link_to_armt"]["status"] != "no_verificado":
            link_errors.append("%s vincula ARMT sin evidencia" % candidate["sounding_id"])
        if not candidate["dossier_sha256_matches"]:
            link_errors.append("%s no coincide con el hash del dosier" % candidate["sounding_id"])
    checker.add(
        "V-22",
        not link_errors,
        "Sin vinculos TEM-ARMT inventados" if not link_errors else "; ".join(link_errors),
    )

    # 8. Calibraciones.
    calibration_errors = []
    calibration_refs = {entry["path_ref"]: entry for entry in manifest["calibration_files"]}
    for record in manifest["armt_records"]:
        calibration = record["calibration"]
        if calibration["channels_matched"] > calibration["channels_total"]:
            calibration_errors.append("%s canales emparejados > total" % record["record_id"])
        for trace in record["traces"]:
            for channel in trace["calibration_channels"]:
                if channel["selected"] is None:
                    if channel["status"] != "sin_candidata":
                        calibration_errors.append(
                            "%s %s sin seleccion pero estado %s"
                            % (record["record_id"], channel["channel"], channel["status"])
                        )
                    continue
                selected = channel["selected"]
                entry = calibration_refs.get(selected["path_ref"])
                if entry is None:
                    calibration_errors.append(
                        "%s %s apunta a una calibracion no inventariada"
                        % (record["record_id"], channel["channel"])
                    )
                    continue
                if entry["sha256"] != selected["sha256"]:
                    calibration_errors.append(
                        "%s %s hash de calibracion distinto" % (record["record_id"], channel["channel"])
                    )
                if entry["serial_number"] != channel["serial_number"]:
                    calibration_errors.append(
                        "%s %s serie distinta" % (record["record_id"], channel["channel"])
                    )
                expected_kind = (
                    "electrical_amplifier"
                    if channel["sensor_type"] == "electrical_amplifier"
                    else "magnetic_sensor"
                )
                if entry["kind"] != expected_kind:
                    calibration_errors.append(
                        "%s %s tipo distinto" % (record["record_id"], channel["channel"])
                    )
    checker.add(
        "V-23",
        not calibration_errors,
        "Calibraciones candidatas coherentes" if not calibration_errors else "; ".join(calibration_errors[:10]),
    )
    checker.add(
        "V-24",
        manifest["counts"]["calibration_files"] == len(manifest["calibration_files"]),
        "Conteo de calibraciones coincide",
    )

    if manifest["software"]["version_consistency"] != "consistente":
        checker.observe(
            "V-29",
            "Version del paquete inconsistente: __init__.py=%s, pyproject=%s"
            % (
                manifest["software"]["armt_processing_version"],
                manifest["software"]["armt_processing_pyproject_version"],
            ),
        )

    # 9. Estado P0.
    computed_status = (
        "COMPLETO"
        if all(
            item["estado"] in ("CUMPLIDO", "NO_APLICA")
            for item in manifest["p0_checklist"]
        )
        and not any(
            blocker["estado"] == "abierto" and blocker["afecta_p0"]
            for blocker in manifest["blockers"]
        )
        else "PARCIAL"
    )
    checker.add(
        "V-25",
        computed_status == scope["p0_status"],
        "Estado P0 declarado %s y calculado %s" % (scope["p0_status"], computed_status),
    )
    checker.add(
        "V-26",
        any(blocker["estado"] == "abierto" for blocker in manifest["blockers"]),
        "Existen bloqueos abiertos declarados",
    )

    # 10. Reporte de lectura completa.
    if samples_path.exists():
        try:
            samples = load_json(samples_path)
            sample_ids = {item["record_id"] for item in samples.get("records", [])}
            samples_ok = (
                samples.get("resultado") == "APROBADO"
                and sample_ids == set(manifest_by_id)
            )
            checker.add(
                "V-27",
                samples_ok,
                "validacion_muestras.json cubre los 15 registros y aprueba"
                if samples_ok
                else "validacion_muestras.json incompleto o fallido",
            )
            p0_12 = next(
                (item for item in manifest["p0_checklist"] if item["id"] == "P0-12"), None
            )
            checker.add(
                "V-28",
                p0_12 is not None and p0_12["estado"] == "CUMPLIDO",
                "P0-12 refleja la lectura completa aprobada"
                if p0_12 is not None and p0_12["estado"] == "CUMPLIDO"
                else "P0-12 no esta CUMPLIDO pese al reporte aprobado",
            )
        except (ValueError, OSError) as error:
            checker.fail("V-27", "No se pudo leer validacion_muestras.json: %s" % error)
    else:
        checker.observe(
            "V-27",
            "No existe validacion_muestras.json; ejecute etapa0/validar_muestras.py",
        )

    failures = [check for check in checker.checks if check["estado"] == "FALLA"]
    observations = [check for check in checker.checks if check["estado"] == "OBSERVACION"]
    if failures:
        result = "RECHAZADO"
    elif computed_status == "PARCIAL" or observations:
        result = "APROBADO_CON_OBSERVACIONES"
    else:
        result = "APROBADO"

    output = {
        "validacion_version": "1.0.0",
        "generated_at_utc": utc_now(),
        "manifest_sha256": sha256_file(manifest_path),
        "schema_sha256": sha256_file(schema_path),
        "splits_sha256": sha256_file(splits_path),
        "protocolo_sha256": sha256_file(protocol_path),
        "samples_sha256": (
            sha256_file(samples_path) if samples_path.exists() else None
        ),
        "p0_status_declarado": scope["p0_status"],
        "p0_status_calculado": computed_status,
        "resultado": result,
        "summary": {
            "total": len(checker.checks),
            "pasa": sum(1 for check in checker.checks if check["estado"] == "PASA"),
            "falla": len(failures),
            "observaciones": len(observations),
        },
        "checks": checker.checks,
        "bloqueos_abiertos": [
            blocker
            for blocker in manifest["blockers"]
            if blocker["estado"] == "abierto"
        ],
        "observaciones": [
            item
            for item in manifest["p0_checklist"]
            if item["estado"] in ("PARCIAL", "PENDIENTE")
        ],
    }
    out_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print("Resultado: %s" % result)
    print(
        "Checks: %d pasa, %d falla, %d observaciones"
        % (output["summary"]["pasa"], len(failures), len(observations))
    )
    print("P0 declarado/calculado: %s / %s" % (scope["p0_status"], computed_status))
    print("Reporte: %s" % out_path.resolve())
    for failure in failures:
        print("  FALLA %s: %s" % (failure["id"], failure["detalle"]))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
