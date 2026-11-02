"""Validacion independiente de los entregables P2-T.

No reescribe los entregables. Recalcula las comprobaciones criticas a partir de
los archivos generados, de las fuentes TEM y del directo MT 1D. El resultado se
guarda en ``validacion_etapa2.json``.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import mt1d  # noqa: E402
import tem_parser  # noqa: E402

VERSION = "P2T-VALID-1.0.0"
EXPECTED = {
    "manifest": "5a67b03feab778e44578a37ef04982e85e56fc5f586f05c3c03e20c7b17ee435",
    "splits": "78cccedc36a0f3850fbc2017adcca6b66abeb77fc71a129280d9d87ea21d9352",
    "export_D0": "159541ba3c9eda652c57504387a658405cc1dac76fe9de2b7bdd26a9645b33e4",
    "export_D1": "6d67e074086e051a075a094f4368bb77e0efd31a7fe71b97fc22290a1a21e61d",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def as_float(value, default=float("nan")):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def close(a, b, tol=1e-6):
    return abs(float(a) - float(b)) <= tol


def add(checks, cid, descripcion, ok, detalle=""):
    checks.append(dict(id=cid, descripcion=descripcion,
                       resultado="PASA" if ok else "FALLA",
                       detalle=detalle))
    return bool(ok)


def observation(checks, cid, descripcion, detalle=""):
    checks.append(dict(id=cid, descripcion=descripcion,
                       resultado="OBSERVACION", detalle=detalle))


def expected_header(path: Path, fields: list[str]) -> bool:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        header = next(csv.reader(fh))
    return header == fields


def main():
    checks: list[dict] = []
    cfg = load_json(HERE / "config_p2t.json")
    prov = load_json(HERE / "model_provenance.json")
    summary = load_json(HERE / "diagnostico_tem" / "resumen_p2t.json")
    outpaths = {
        "gates": HERE / cfg["outputs"]["tem_valid_gates"],
        "armt": HERE / cfg["outputs"]["tem_amt_support"],
        "prov": HERE / cfg["outputs"]["model_provenance"],
        "env_D0": HERE / cfg["outputs"]["envelopes_D0"],
        "env_D1": HERE / cfg["outputs"]["envelopes_D1"],
        "support": HERE / cfg["outputs"]["support_by_sounding"],
        "mt": HERE / cfg["outputs"]["mt_sensitivity"],
        "tem": HERE / cfg["outputs"]["tem_sensitivity"],
        "svd": HERE / cfg["outputs"]["tem_svd"],
        "doi": HERE / cfg["outputs"]["doi_comparison"],
        "direct": HERE / cfg["outputs"]["direct_tests"],
        "summary": HERE / cfg["outputs"]["summary"],
        "report": HERE / cfg["outputs"]["report"],
    }

    # ------------------------------------------------------------------
    # 1. existencia y columnas
    # ------------------------------------------------------------------
    for key, path in outpaths.items():
        add(checks, f"FILE-{key}", f"Existe {path.relative_to(HERE)}",
            path.is_file(), str(path))
    add(checks, "CFG-VERSION", "config_p2t tiene la version esperada",
        cfg.get("version") == "P2T-CONFIG-1.0.0", cfg.get("version", ""))
    add(checks, "FILE-README", "Existe etapa2/README.md",
        (HERE / "README.md").is_file(), "README.md")

    headers = {
        "gates": ["sounding_id", "gate_reader", "gate_tem", "t_ms_reader",
                  "t_ms_tem", "t_ms_parser", "voltage_nva_reader",
                  "voltage_nva_tem", "rhoa_ohm_m_tem", "sigma_effective_nva",
                  "relative_error", "snr_effective", "qc", "use_contiguous",
                  "exportado_tem", "emparejamiento_temporal",
                  "desalineacion_amplitud_rel", "usado_en_inversion",
                  "n_modelos_que_usan_gate", "estado_gate", "motivo",
                  "guardas", "version"],
        "env": ["sounding_id", "band", "frequency_hz", "evaluado", "n_modelos",
                "modelos", "log10rhoa_med", "log10rhoa_min", "log10rhoa_max",
                "log10rhoa_semiancho", "phase_med_deg", "phase_min_deg",
                "phase_max_deg", "phase_semiancho_deg", "Z_rel_max",
                "envolvente_ok", "motivo_envolvente", "version"],
        "mt": ["sounding_id", "frequency_hz", "band", "layer_index", "top_m",
               "bottom_m", "rho_ohm_m", "dlnZ_dlnrho_real", "dlnZ_dlnrho_imag",
               "abs_dlnZ_dlnrho", "share", "cumulative_share", "version"],
        "tem": ["sounding_id", "gate_index_inversion", "gate_reader", "t_ms",
                "relative_error", "layer_index", "top_m", "bottom_m",
                "dlogV_dlogrho", "weighted_dlogV_dlogrho", "version"],
        "svd": ["sounding_id", "component", "singular_value",
                "singular_value_normalized", "energy_fraction",
                "cumulative_energy", "rank_effective", "resolved",
                "threshold_rel", "version"],
        "support": ["sounding_id", "band", "frequency_hz", "observable", "estado",
                    "log10rhoa_semiancho", "phase_semiancho_deg", "Z_rel_max",
                    "envolvente_ok", "z50_m", "z90_m", "doi_m",
                    "frac_sensibilidad_bajo_doi", "profundidad_ok",
                    "tem_rank_efectivo", "tem_null_fraction",
                    "sensibilidad_compartida_ok", "n_gates_inversion",
                    "n_modelos", "supuestos", "guardas", "motivo", "version"],
        "doi": ["sounding_id", "band", "frequency_hz", "z50_m", "z90_m", "doi_m",
                "frac_sensibilidad_bajo_doi", "profundidad_ok",
                "tem_null_fraction", "sensibilidad_compartida_ok",
                "tem_rank_efectivo", "n_gates_inversion", "version"],
        "armt": ["record_id", "split", "band", "frequency_hz", "observable",
                 "estado", "tem_sounding_id", "candidatos_tem_disponibles",
                 "log10rhoa_semiancho", "phase_semiancho_deg", "Z_rel_max",
                 "z50_m", "doi_m", "tem_null_fraction", "supuestos", "guardas",
                 "motivo", "version"],
        "direct": ["prueba", "valor", "limite", "unidad", "pasa", "detalle",
                   "version"],
    }
    for key, fields in headers.items():
        path = outpaths["env_D0"] if key == "env" else outpaths[key]
        add(checks, f"HDR-{key}", f"Columnas de {path.name}",
            expected_header(path, fields), path.name)

    # ------------------------------------------------------------------
    # 2. hashes
    # ------------------------------------------------------------------
    for item in prov["inputs"]:
        if not item.get("sha256"):
            continue
        p = Path(item["path_abs"])
        actual = sha256_file(p) if p.is_file() else ""
        add(checks, f"HASH-{item['id']}", f"Hash de {item['id']}",
            actual == item["sha256"], f"{actual[:16]}...")

    frozen = {
        "P0-manifest": (ROOT / "etapa0" / "manifest.json", EXPECTED["manifest"]),
        "P0-splits": (ROOT / "etapa0" / "splits.csv", EXPECTED["splits"]),
        "P1-export-D0": (ROOT / "etapa1" / "exportaciones" /
                         "01401401_D0_900s_uV.npy", EXPECTED["export_D0"]),
        "P1-export-D1": (ROOT / "etapa1" / "exportaciones" /
                         "01401401_D1_45s_uV.npy", EXPECTED["export_D1"]),
    }
    for name, (path, expected) in frozen.items():
        actual = sha256_file(path) if path.is_file() else ""
        add(checks, f"FREEZE-{name}", f"Hash congelado de {name}",
            actual == expected, f"{actual[:16]}...")

    # ------------------------------------------------------------------
    # 3. grillas y modelos
    # ------------------------------------------------------------------
    grids = {}
    for band in ("D0", "D1"):
        spec = cfg["frequency_grid"][band]
        rows = read_csv(ROOT / spec["file"])
        freqs = [float(r["frequency_hz"]) for r in rows]
        grids[band] = freqs
        add(checks, f"GRID-{band}-N", f"{band} tiene {spec['expected_n']} frecuencias",
            len(freqs) == int(spec["expected_n"]), str(len(freqs)))
        add(checks, f"GRID-{band}-RANGE", f"{band} dentro del rango declarado",
            min(freqs) >= spec["range_hz"][0] and max(freqs) <= spec["range_hz"][1],
            f"{min(freqs):.6g}-{max(freqs):.6g}")
    add(checks, "GRID-D1-GUARD", "La grilla D1 conserva 10 kHz como escenario separado",
        10000.0 in grids["D1"], "10000 Hz presente")

    prov_models = prov["models"]
    add(checks, "PROV-MODELS-N", "Hay 18 modelos (6 base + 12 estabilidad)",
        len(prov_models) == 18, str(len(prov_models)))
    roles = Counter(m["role"] for m in prov_models)
    add(checks, "PROV-MODELS-ROLES", "Roles 6 base / 12 estabilidad",
        roles.get("base") == 6 and roles.get("estabilidad") == 12, str(dict(roles)))
    add(checks, "PROV-MODELS-POSTERIOR", "Ningun modelo se declara posterior",
        all(m["is_posterior"] is False for m in prov_models), "is_posterior=false")
    stations = sorted({m["sounding_id"] for m in prov_models})
    add(checks, "PROV-MODELS-STATIONS", "6 sondeos con 3 modelos cada uno",
        len(stations) == 6 and all(
            sum(1 for m in prov_models if m["sounding_id"] == st) == 3 for st in stations),
        ",".join(stations))
    add(checks, "PROV-MODELS-LAYERS", "Todos los modelos tienen 16 capas y 15 interfaces",
        all(m["n_layers"] == 16 and len(m["interfaces_m"]) == 15 for m in prov_models),
        "16 capas")
    add(checks, "PROV-MODELS-GATES", "Todos los modelos declaran 19-22 gates de inversion",
        all(19 <= m["n_gates_inversion"] <= 22 for m in prov_models),
        ", ".join(str(m["n_gates_inversion"]) for m in prov_models))

    # ------------------------------------------------------------------
    # 4. directo MT
    # ------------------------------------------------------------------
    model_list = []
    for m in prov_models:
        model_list.append((m["model_id"], m["rho_ohm_m"], m["interfaces_m"]))
    mt_test = mt1d.self_test(model_list)
    add(checks, "DIR-PASA", "El directo MT pasa todas las pruebas",
        bool(mt_test["pasa"]), f"{len(mt_test['pruebas'])} pruebas")
    add(checks, "DIR-META", "El directo MT cumple la meta P2 (Z <= 1%)",
        bool(mt_test["cumple_meta_p2"]), f"max_error_rel={mt_test['max_error_rel']:.3e}")
    for t in mt_test["pruebas"]:
        add(checks, f"DIR-{t['prueba']}", f"Prueba {t['prueba']}",
            bool(t["pasa"]), f"{t['valor']:.3e} {t['unidad']} <= {t['limite']:.3e}")

    # ------------------------------------------------------------------
    # 5. gates
    # ------------------------------------------------------------------
    gate_rows = read_csv(outpaths["gates"])
    add(checks, "GATE-N", "tem_valid_gates.csv tiene 288 filas",
        len(gate_rows) == 288, str(len(gate_rows)))
    by_st = defaultdict(list)
    for row in gate_rows:
        by_st[row["sounding_id"]].append(row)
    add(checks, "GATE-SOUNDINGS", "6 sondeos x 48 gates",
        len(by_st) == 6 and all(len(v) == 48 for v in by_st.values()),
        str({k: len(v) for k, v in by_st.items()}))
    gate_counts = Counter(r["estado_gate"] for r in gate_rows)
    add(checks, "GATE-COUNTS", "Conteos de estado de gate",
        gate_counts.get("valido") == 120
        and gate_counts.get("valido_condicional") == 10
        and gate_counts.get("excluido") == 59
        and gate_counts.get("no_exportado") == 99,
        str(dict(gate_counts)))
    base_counts = {
        st: next(m["n_gates_inversion"] for m in prov_models
                 if m["sounding_id"] == st and m["role"] == "base")
        for st in by_st
    }
    used_counts = {st: sum(1 for r in v if r["usado_en_inversion"] == "si")
                   for st, v in by_st.items()}
    add(checks, "GATE-USED",
        "Los gates marcados como usados coinciden con el modelo base (130 en total)",
        used_counts == base_counts and sum(used_counts.values()) == 130,
        str(used_counts))
    models_using_ok = all(
        0 <= int(r["n_modelos_que_usan_gate"]) <= 3
        and (r["usado_en_inversion"] != "si" or int(r["n_modelos_que_usan_gate"]) >= 1)
        for r in gate_rows
    )
    add(checks, "GATE-MODELS-USING",
        "n_modelos_que_usan_gate en [0,3] y coherente con usado_en_inversion",
        models_using_ok, "288 filas")

    tem_parsed = {}
    for st, spec in cfg["tem_soundings"].items():
        tem_parsed[st] = tem_parser.parse_tem(Path(spec["tem"]))
    for st, parsed in tem_parsed.items():
        add(checks, f"GATE-TEM-{st}", f"{st}: gates .tem coinciden",
            len([r for r in by_st[st] if r["exportado_tem"] == "si"]) == parsed["n_gates"],
            f"{parsed['n_gates']} gates")
        exported = sorted((r for r in by_st[st] if r["exportado_tem"] == "si"),
                          key=lambda r: int(r["gate_tem"]))
        ok_seq = [int(r["gate_tem"]) for r in exported] == list(range(1, parsed["n_gates"] + 1))
        ok_off = all(int(r["gate_reader"]) == int(r["gate_tem"]) + 1 for r in exported)
        add(checks, f"GATE-SEQ-{st}", f"{st}: gates .tem 1..n y lector = tem+1",
            ok_seq and ok_off, "secuencia y desplazamiento")
        max_dt = max(abs(as_float(r["t_ms_reader"]) - as_float(r["t_ms_tem"]))
                     / max(as_float(r["t_ms_tem"]), 1e-12) for r in exported)
        add(checks, f"GATE-TIME-{st}", f"{st}: tiempo .tem vs lector < 0.1%",
            max_dt <= 1e-3, f"max_dt_rel={max_dt:.3e}")

    bad_valid = [r for r in gate_rows
                 if r["estado_gate"] in ("valido", "valido_condicional")
                 and (r["exportado_tem"] != "si" or r["use_contiguous"] != "True"
                      or r["qc"] not in ("preferente", "condicional"))]
    add(checks, "GATE-VALID-CONSIST", "Todo gate valido esta exportado y en ventana contigua",
        not bad_valid, f"{len(bad_valid)} inconsistencias")
    bad_noexport = [r for r in gate_rows
                    if r["estado_gate"] == "no_exportado"
                    and (r["t_ms_tem"] or r["voltage_nva_tem"])]
    add(checks, "GATE-NOEXPORT-EMPTY", "Los gates no exportados no tienen valores .tem",
        not bad_noexport, f"{len(bad_noexport)} inconsistencias")
    for st, v in summary["gates"]["per_sounding"].items():
        recomputed = max((as_float(r["desalineacion_amplitud_rel"]) for r in by_st[st]
                          if r["use_contiguous"] == "True"
                          and r["desalineacion_amplitud_rel"]), default=0.0)
        add(checks, f"GATE-DV-{st}", f"{st}: maxima diferencia de amplitud coincide",
            close(recomputed, v["max_dv_rel_contiguous"], 1e-6),
            f"{recomputed:.6f} vs {v['max_dv_rel_contiguous']:.6f}")

    # ------------------------------------------------------------------
    # 6. envolventes
    # ------------------------------------------------------------------
    env_rows = {"D0": read_csv(outpaths["env_D0"]), "D1": read_csv(outpaths["env_D1"])}
    for band, rows in env_rows.items():
        add(checks, f"ENV-{band}-N", f"envolventes_{band}.csv tiene 6x{len(grids[band])} filas",
            len(rows) == 6 * len(grids[band]), str(len(rows)))
        by = defaultdict(list)
        for r in rows:
            by[r["sounding_id"]].append(r)
        ok_freq = all([as_float(r["frequency_hz"]) for r in by[st]] == grids[band]
                      for st in by)
        add(checks, f"ENV-{band}-GRID", f"{band}: grilla identica a P1",
            ok_freq, "frecuencias")
        for st in sorted(by):
            for r in by[st]:
                hw = (as_float(r["log10rhoa_max"]) - as_float(r["log10rhoa_min"])) / 2.0
                phw = max(abs(as_float(r["phase_min_deg"]) - as_float(r["phase_med_deg"])),
                          abs(as_float(r["phase_max_deg"]) - as_float(r["phase_med_deg"])))
                ok = (close(hw, r["log10rhoa_semiancho"], 1e-4)
                      and close(phw, r["phase_semiancho_deg"], 1e-4))
                expected_ok = (hw <= 0.025 + 1e-9 and phw <= 1.5 + 1e-9
                               and as_float(r["Z_rel_max"]) <= 0.065 + 1e-9)
                if not (ok and (r["envolvente_ok"] == ("si" if expected_ok else "no"))):
                    add(checks, f"ENV-CONSIST-{band}-{st}", f"{band}/{st}: envolvente consistente",
                        False, r["frequency_hz"])
                    break
            else:
                add(checks, f"ENV-CONSIST-{band}-{st}", f"{band}/{st}: envolvente consistente",
                    True, "semianchos y umbrales")
            evaluated = [r for r in by[st] if r["evaluado"] == "si"]
            ndentro = sum(1 for r in evaluated if r["envolvente_ok"] == "si")
            ref = summary["envelopes"][st][band]
            add(checks, f"ENV-SUM-{band}-{st}",
                f"{band}/{st}: recuentos del resumen excluyen 10 kHz",
                ref["n_evaluado"] == len(evaluated) and ref["n_dentro"] == ndentro
                and ref["n_no_evaluado"] == len(by[st]) - len(evaluated),
                f"{ref['n_evaluado']}/{ref['n_dentro']} vs {len(evaluated)}/{ndentro}")
    guard_rows = [r for r in env_rows["D1"] if r["evaluado"] == "no"]
    add(checks, "ENV-GUARD-10K", "Solo 10 kHz queda no evaluado en D1",
        len(guard_rows) == 6 and all(close(r["frequency_hz"], 10000.0, 1e-6)
                                     for r in guard_rows),
        f"{len(guard_rows)} filas")

    # ------------------------------------------------------------------
    # 7. sensibilidades
    # ------------------------------------------------------------------
    mt_rows = read_csv(outpaths["mt"])
    add(checks, "MT-N", "sensibilidades_mt.csv tiene 6x42x16 filas",
        len(mt_rows) == 6 * 42 * 16, str(len(mt_rows)))
    mt_by = defaultdict(list)
    for r in mt_rows:
        mt_by[(r["sounding_id"], r["band"], r["frequency_hz"])].append(r)
    add(checks, "MT-NGROUPS", "Hay 6x42 grupos sondeo/banda/frecuencia",
        len(mt_by) == 6 * 42, str(len(mt_by)))
    share_ok = True
    cum_ok = True
    for key, rows in mt_by.items():
        rows = sorted(rows, key=lambda r: int(r["layer_index"]))
        if len(rows) != 16:
            share_ok = False
            break
        total = sum(as_float(r["share"]) for r in rows)
        if not close(total, 1.0, 1e-4):
            share_ok = False
        if not close(as_float(rows[-1]["cumulative_share"]), 1.0, 1e-4):
            cum_ok = False
    add(checks, "MT-SHARE", "Las 16 capas suman share=1", share_ok, "6x42 grupos")
    add(checks, "MT-CUM", "La sensibilidad acumulada termina en 1", cum_ok, "6x42 grupos")
    add(checks, "MT-FINITE", "Sensibilidades MT finitas",
        all(math.isfinite(as_float(r["abs_dlnZ_dlnrho"])) for r in mt_rows), "sin NaN/inf")

    tem_rows = read_csv(outpaths["tem"])
    n_tem_gates = sum(m["n_gates_inversion"] for m in prov_models if m["role"] == "base")
    add(checks, "TEM-N", "sensibilidades_tem.csv tiene (gates base)x16 filas",
        len(tem_rows) == n_tem_gates * 16, f"{len(tem_rows)} vs {n_tem_gates * 16}")
    tem_ok = True
    for r in tem_rows:
        rel = as_float(r["relative_error"])
        raw = as_float(r["dlogV_dlogrho"])
        weighted = as_float(r["weighted_dlogV_dlogrho"])
        if not close(weighted, raw / rel, max(1e-5, abs(raw / rel) * 1e-4)):
            tem_ok = False
            break
    add(checks, "TEM-WEIGHT", "Jacobiano TEM ponderado = J/rel", tem_ok, "6x22x16")

    svd_rows = read_csv(outpaths["svd"])
    add(checks, "SVD-N", "sensibilidad_tem_svd.csv tiene 6x16 filas",
        len(svd_rows) == 96, str(len(svd_rows)))
    svd_by = defaultdict(list)
    for r in svd_rows:
        svd_by[r["sounding_id"]].append(r)
    svd_ok = True
    for st, rows in svd_by.items():
        rows = sorted(rows, key=lambda r: int(r["component"]))
        s = [as_float(r["singular_value"]) for r in rows]
        if any(s[i] < s[i + 1] for i in range(len(s) - 1)):
            svd_ok = False
        if sum(1 for r in rows if r["resolved"] == "si") != int(rows[0]["rank_effective"]):
            svd_ok = False
    add(checks, "SVD-ORDER", "Valores singulares no crecientes y resolved coherente",
        svd_ok, "6x16")

    # ------------------------------------------------------------------
    # 8. soporte por sondeo
    # ------------------------------------------------------------------
    support = read_csv(outpaths["support"])
    add(checks, "SUP-N", "soporte_por_sondeo.csv tiene 252 filas",
        len(support) == 252, str(len(support)))
    states = Counter(r["estado"] for r in support)
    add(checks, "SUP-STATES", "Estados permitidos y sin respaldada",
        set(states) <= {"respaldada", "condicional", "no_respaldada", "no_evaluado"}
        and states.get("respaldada", 0) == 0, str(dict(states)))
    bad_cond = []
    bad_no = []
    bad_ne = []
    for r in support:
        env = r["envolvente_ok"] == "si"
        prof = r["profundidad_ok"] == "si"
        shared = r["sensibilidad_compartida_ok"] == "si"
        if r["estado"] == "condicional" and not (env and prof and shared):
            bad_cond.append(r)
        if r["estado"] == "no_respaldada" and (env and prof and shared):
            bad_no.append(r)
        if r["estado"] == "no_evaluado" and not (
                close(r["frequency_hz"], 10000.0, 1e-6)
                and "empalme_calibracion" in r["motivo"]):
            bad_ne.append(r)
    add(checks, "SUP-COND", "Todo condicional cumple los tres criterios",
        not bad_cond, f"{len(bad_cond)} inconsistencias")
    add(checks, "SUP-NO", "Todo no_respaldada falla al menos un criterio",
        not bad_no, f"{len(bad_no)} inconsistencias")
    add(checks, "SUP-NE", "Todo no_evaluado es 10 kHz con guarda de empalme",
        not bad_ne, f"{len(bad_ne)} inconsistencias")
    add(checks, "SUP-DOI", "doi_m coincide con el resumen por sondeo",
        all(close(r["doi_m"], summary["doi"][r["sounding_id"]]["doi_operativa_creible_m"], 1e-6)
            for r in support), "100/175 m")
    add(checks, "SUP-RANK",
        "Rango efectivo TEM coincide con el SVD del modelo base",
        all(int(r["tem_rank_efectivo"])
            == int(summary["tem_svd"][r["sounding_id"]]["rank_effective_1pct"])
            for r in support),
        ", ".join(f"{st}={summary['tem_svd'][st]['rank_effective_1pct']}"
                  for st in sorted(summary["tem_svd"])))
    add(checks, "SUP-MONO", "z50 <= z90 y fracciones en [0,1]",
        all(as_float(r["z50_m"]) <= as_float(r["z90_m"]) + 1e-6
            and 0 <= as_float(r["frac_sensibilidad_bajo_doi"]) <= 1
            and 0 <= as_float(r["tem_null_fraction"]) <= 1 for r in support),
        "252 filas")
    # conteos por sondeo/banda contra el resumen
    sup_by = defaultdict(Counter)
    for r in support:
        sup_by[(r["sounding_id"], r["band"])][r["estado"]] += 1
    ok_counts = True
    for st in cfg["scope"]["tem_soundings"]:
        for band in ("D0", "D1"):
            ref = summary["support"]["per_sounding"][st][band]
            got = sup_by[(st, band)]
            for state in ("condicional", "no_respaldada", "no_evaluado"):
                if got.get(state, 0) != ref[state]:
                    ok_counts = False
    add(checks, "SUP-COUNTS", "Conteos por sondeo/banda coinciden con el resumen",
        ok_counts, "6x2")
    # bandas condicionales contiguas
    bands_ok = True
    for st in cfg["scope"]["tem_soundings"]:
        for band in ("D0", "D1"):
            rows = [r for r in support if r["sounding_id"] == st and r["band"] == band]
            rows.sort(key=lambda r: as_float(r["frequency_hz"]))
            runs = []
            cur = None
            for r in rows:
                if r["estado"] == "condicional":
                    if cur is None:
                        cur = dict(f_min_hz=as_float(r["frequency_hz"]),
                                   f_max_hz=as_float(r["frequency_hz"]), n=1)
                    else:
                        cur["f_max_hz"] = as_float(r["frequency_hz"])
                        cur["n"] += 1
                elif cur is not None:
                    runs.append(cur)
                    cur = None
            if cur is not None:
                runs.append(cur)
            ref = summary["support"]["per_sounding"][st][band]["bandas_condicionales"]
            if len(runs) != len(ref):
                bands_ok = False
                continue
            for a, b in zip(runs, ref):
                if not (close(a["f_min_hz"], b["f_min_hz"], 1e-4)
                        and close(a["f_max_hz"], b["f_max_hz"], 1e-4)
                        and a["n"] == b["n"]):
                    bands_ok = False
    add(checks, "SUP-BANDS", "Bandas condicionales contiguas coinciden",
        bands_ok, "por sondeo/banda")

    # ------------------------------------------------------------------
    # 9. tabla ARMT
    # ------------------------------------------------------------------
    armt = read_csv(outpaths["armt"])
    add(checks, "AMT-N", "tem_amt_support.csv tiene 15x42=630 filas",
        len(armt) == 630, str(len(armt)))
    add(checks, "AMT-STATE", "Todas las filas son no_evaluado",
        all(r["estado"] == "no_evaluado" for r in armt),
        str(dict(Counter(r["estado"] for r in armt))))
    add(checks, "AMT-LINK", "Todas las filas citan B-P0-03 y no tienen sondeo asignado",
        all("B-P0-03" in r["motivo"] and r["tem_sounding_id"] == "" for r in armt),
        "B-P0-03")
    add(checks, "AMT-EMPTY", "Las columnas de envolvente quedan vacias",
        all(all(r[k] == "" for k in ("log10rhoa_semiancho", "phase_semiancho_deg",
                                     "Z_rel_max", "z50_m", "doi_m",
                                     "tem_null_fraction")) for r in armt),
        "vacias")
    add(checks, "AMT-CAND", "Las 6 candidatas TEM estan declaradas",
        all(set(r["candidatos_tem_disponibles"].split(";")) ==
            set(cfg["scope"]["tem_soundings"]) for r in armt), "6 candidatas")
    add(checks, "AMT-FREQ", "La grilla ARMT coincide con P1",
        sorted({(r["band"], as_float(r["frequency_hz"])) for r in armt})
        == sorted({(b, f) for b in ("D0", "D1") for f in grids[b]}), "D0+D1")
    splits = {r["record_id"]: r["split"] for r in
              read_csv(ROOT / "etapa0" / "splits.csv")}
    add(checks, "AMT-SPLIT", "El split de cada fila coincide con splits.csv",
        all(splits[r["record_id"]] == r["split"] for r in armt), "15 registros")
    add(checks, "AMT-RECORDS", "Los 15 registros estan presentes",
        len({r["record_id"] for r in armt}) == 15, "15")

    # ------------------------------------------------------------------
    # 10. proveniencia y resumen
    # ------------------------------------------------------------------
    add(checks, "PROV-CAND", "6 candidatas TEM con vinculo no verificado",
        len(prov["tem_candidates"]) == 6
        and all(c["link_status"] == "no_verificado" for c in prov["tem_candidates"]),
        "6")
    add(checks, "PROV-SOFT", "Hashes de mt1d.py y tem_parser.py coinciden",
        prov["software"]["mt1d"]["sha256"] == sha256_file(HERE / "mt1d.py")
        and prov["software"]["tem_parser"]["sha256"] == sha256_file(HERE / "tem_parser.py"),
        "software local")
    add(checks, "PROV-DIR", "La proveniencia declara el directo aprobado",
        bool(prov["directo"]["pasa"]), "directo.pasa")
    add(checks, "PROV-STATUS", "Estado de proveniencia declarado",
        prov.get("status") == "DIAGNOSTICO_CON_SOPORTE_AMT_VACIO",
        prov.get("status", ""))

    totals = summary["support"]["totals"]
    add(checks, "SUM-TOTALS", "Totales de soporte suman 252 y respaldada=0",
        sum(totals.get(k, 0) for k in
            ("respaldada", "condicional", "no_respaldada", "no_evaluado")) == 252
        and totals.get("respaldada", 0) == 0,
        str(totals))
    add(checks, "SUM-AMT", "El resumen declara 630 filas no_evaluado y soporte deshabilitado",
        summary["armt_support"]["n_rows"] == 630
        and summary["armt_support"]["states"].get("no_evaluado") == 630
        and summary["armt_support"]["soporte_habilitado"] is False,
        str(summary["armt_support"]))
    add(checks, "SUM-CONCLUSION", "La conclusion cierra la rama TEM",
        "no se habilita" in summary["conclusion"].lower()
        and "no_evaluado" in summary["conclusion"],
        summary["conclusion"][:120])
    report_text = outpaths["report"].read_text(encoding="utf-8")
    add(checks, "REP-KEY", "El reporte contiene P2-T, B-P0-03, no_evaluado y sintesis",
        all(x in report_text for x in ("P2-T", "B-P0-03", "no_evaluado", "síntesis")),
        "reporte")
    add(checks, "REP-UTF8", "El reporte no contiene caracteres de reemplazo",
        "\ufffd" not in report_text, "UTF-8")
    readme_text = (HERE / "README.md").read_text(encoding="utf-8")
    add(checks, "README-KEY",
        "El README declara alcance, soporte vacio y bloqueos",
        all(x in readme_text for x in
            ("P2-T", "no_evaluado", "B-P0-03", "banco_sintetico", "condicional")),
        "README.md")

    # ------------------------------------------------------------------
    # 11. coherencia con la matriz raiz
    # ------------------------------------------------------------------
    matrix_path = ROOT / "MATRIZ_VALIDACION_ARMT.csv"
    add(checks, "MATRIZ-FILE", "Existe MATRIZ_VALIDACION_ARMT.csv",
        matrix_path.is_file(), str(matrix_path))
    matrix = {r["puerta"]: r for r in read_csv(matrix_path)} \
        if matrix_path.is_file() else {}
    add(checks, "MATRIZ-ROWS", "La matriz conserva las 16 puertas/subpuertas",
        len(matrix) == 16 and {"P0", "P1", "P2", "P2-T", "P3"} <= set(matrix),
        str(len(matrix)))
    add(checks, "MATRIZ-P0", "P0 figura como PARCIAL o RECHAZADO en la matriz",
        matrix.get("P0", {}).get("estado") in ("PARCIAL", "RECHAZADO"),
        matrix.get("P0", {}).get("estado", ""))
    add(checks, "MATRIZ-P1", "P1 figura como PARCIAL en la matriz",
        matrix.get("P1", {}).get("estado") == "PARCIAL",
        matrix.get("P1", {}).get("estado", ""))
    p2t = matrix.get("P2-T", {})
    add(checks, "MATRIZ-P2T",
        "P2-T figura cerrada como diagnostico con soporte AMT vacio",
        p2t.get("estado", "").startswith("CERRADA COMO DIAGN")
        and "soporte AMT vac" in p2t.get("estado", "")
        and p2t.get("fecha_revision") == "2026-10-28"
        and "B-P0-03" in p2t.get("observaciones", ""),
        p2t.get("estado", ""))
    evid_ok = []
    for rel in (p2t.get("ruta_evidencia", "") or "").split(";"):
        rel = rel.strip()
        if rel:
            evid_ok.append((ROOT / rel).exists())
    add(checks, "MATRIZ-P2T-EVID",
        "Las rutas de evidencia de P2-T existen",
        bool(evid_ok) and all(evid_ok),
        p2t.get("ruta_evidencia", ""))
    p3 = matrix.get("P3", {})
    add(checks, "MATRIZ-P3",
        "P3 se declara solo sintetico y cita el bloqueo de soporte AMT",
        ("Pendiente" in p3.get("estado", "") or "SINTETICO" in p3.get("estado", "").upper())
        and "B-P0-03" in p3.get("observaciones", ""),
        p3.get("estado", ""))

    # ------------------------------------------------------------------
    # 12. no contaminacion sintetica
    # ------------------------------------------------------------------
    offenders = []
    for path in HERE.rglob("*"):
        if not path.is_file():
            continue
        if path.name in ("validacion_etapa2.json", "validar_etapa2.py"):
            # El propio validador contiene el literal que busca; el JSON de
            # validacion puede citarlo. El resto de entregables no.
            continue
        if path.suffix.lower() not in (".csv", ".json", ".md", ".py", ".txt"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "SYN-" in text:
            offenders.append(str(path.relative_to(HERE)))
    add(checks, "NOSYN", "No hay marcadores SYN- en los entregables P2-T",
        not offenders, ", ".join(offenders))

    # ------------------------------------------------------------------
    # 13. observaciones
    # ------------------------------------------------------------------
    max_dv = max(v["max_dv_rel_contiguous"] for v in summary["gates"]["per_sounding"].values())
    observation(checks, "OBS-01",
                "La amplitud .tem y la del lector difieren en la ventana util; se conserva como guarda.",
                f"max_dv_rel={max_dv:.4f}")
    observation(checks, "OBS-02",
                "t_parser_ms esta desalineado; clock_max_relative_pct se reclasifica como artefacto de tablas.",
                f"max_t_parser_rel={summary['alignment']['t_parser_max_relative']:.4f}")
    observation(checks, "OBS-03",
                "No se dispone de un motor MT externo; el directo se valido con semiespacio, formulacion matricial, limites y convergencia.",
                f"max_error_rel={mt_test['max_error_rel']:.3e}")
    observation(checks, "OBS-04",
                "La DOI es operativa y no validada.",
                "DOI_validated_m vacia en los 6 sondeos")
    observation(checks, "OBS-05",
                "El rango efectivo TEM es 4 al 1%; el resultado de sensibilidad compartida depende del umbral.",
                "rank 4 (1%), 6-7 (0.1%), 7-8 (0.01%)")
    observation(checks, "OBS-06",
                "10 kHz queda como escenario separado por el empalme de calibracion.",
                "no_evaluado")
    observation(checks, "OBS-07",
                "Los 18 modelos son escenarios regularizados, no un posterior probabilistico.",
                "lambda 1-4; wrms_log 0.25-1.35")
    observation(checks, "OBS-08",
                "tem_amt_support.csv queda vacio por B-P0-03, no por ausencia de datos TEM.",
                "630 filas no_evaluado")
    observation(checks, "OBS-09",
                "El soporte condicional por sondeo no se transfiere a los registros ARMT.",
                "B-P0-03 abierto")
    observation(checks, "OBS-10",
                "La banda condicional es estrecha y depende de la DOI operativa; SER-09/10 no tienen banda condicional.",
                "DOI 100 m vs 175 m")

    passed = sum(1 for c in checks if c["resultado"] == "PASA")
    failed = sum(1 for c in checks if c["resultado"] == "FALLA")
    observations = sum(1 for c in checks if c["resultado"] == "OBSERVACION")
    status = ("FALLA" if failed else
              "APROBADO_CON_OBSERVACIONES" if observations else "APROBADO")
    result = dict(
        artifact="validacion_etapa2", version=VERSION,
        generated_at_utc=utc_now(), stage=2, substage="P2-T",
        status=status,
        counts=dict(checks=len(checks), passed=passed, failed=failed,
                    observations=observations),
        checks=checks,
        observations=[c for c in checks if c["resultado"] == "OBSERVACION"],
        blockers=cfg["blockers"],
        note=("La validacion no certifica el vinculo TEM-ARMT ni la DOI. "
              "Confirma coherencia interna, hashes, pruebas del directo y "
              "la ausencia de soporte habilitado."),
    )
    (HERE / "validacion_etapa2.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=status, counts=result["counts"],
                          failed=[c["id"] for c in checks if c["resultado"] == "FALLA"]),
                     ensure_ascii=False, indent=1))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
