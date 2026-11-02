"""P2-T: diagnostico de soporte TEM-MT/AMT.

Genera los entregables de la subpuerta P2-T a partir de:

- la grilla de frecuencias P1 (D0/D1);
- la mascara QC por gate y la sigma efectiva del dosier TEM;
- los 6 modelos base y los 12 modelos de estabilidad (18 escenarios);
- el directo MT 1D de ``mt1d.py``.

No genera series temporales, no entrena, no infiere y no asigna sondeos TEM a
registros ARMT. El vinculo TEM-ARMT sigue sin verificar (B-P0-03).
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import mt1d  # noqa: E402
import tem_parser  # noqa: E402

VERSION = "P2T-1.0.0"
GATE_VERSION = "P2T-GATES-1.0.0"
ENV_VERSION = "P2T-ENV-1.0.0"
MTSENS_VERSION = "P2T-MTSENS-1.0.0"
TEMSENS_VERSION = "P2T-TEMSENS-1.0.0"
SVD_VERSION = "P2T-SVD-1.0.0"
DOI_VERSION = "P2T-DOI-1.0.0"
SUPPORT_VERSION = "P2T-SUPPORT-1.0.0"
AMT_VERSION = "P2T-AMT-SUPPORT-1.0.0"
PROV_VERSION = "P2T-PROV-1.0.0"
SUMMARY_VERSION = "P2T-SUMMARY-1.0.0"


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def fnum(x, digits: int = 6, scientific: bool = False) -> str:
    if x is None:
        return ""
    if isinstance(x, (bool, np.bool_)):
        return "si" if bool(x) else "no"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not math.isfinite(v):
        return ""
    if scientific:
        return f"{v:.{digits}e}"
    return f"{v:.{digits}f}"


def fint(x) -> str:
    if x is None:
        return ""
    return str(int(x))


def ffreq(x) -> str:
    """Frecuencia con representacion exacta (ida y vuelta float).

    La grilla P1 se escribe con 9 decimales en algunos puntos. Redondear a 6
    decimales rompe la igualdad estricta con P1 y colapsa 1000 Hz de D0 con
    1000 Hz de D1; ``repr`` conserva el valor exacto leido.
    """
    return repr(float(x))


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n",
                                extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")


def resolve(item: dict) -> Path:
    p = Path(item["path"])
    return p if p.is_absolute() else ROOT / p


def jsonable(x):
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, np.ndarray):
        return x.tolist()
    return x


# ---------------------------------------------------------------------------
# carga de datos
# ---------------------------------------------------------------------------
def load_config() -> dict:
    return load_json(HERE / "config_p2t.json")


def load_grid(cfg: dict, band: str) -> list[float]:
    spec = cfg["frequency_grid"][band]
    rows = read_csv(ROOT / spec["file"])
    freqs = [float(r["frequency_hz"]) for r in rows]
    if len(freqs) != int(spec["expected_n"]):
        raise ValueError(f"{band}: {len(freqs)} frecuencias, se esperaban {spec['expected_n']}")
    return freqs


def load_models(cfg: dict):
    base = load_json(resolve(next(i for i in cfg["inputs"] if i["id"] == "tem_scenarios")))
    est = load_json(resolve(next(i for i in cfg["inputs"] if i["id"] == "tem_stability")))
    by_station: OrderedDict[str, list[dict]] = OrderedDict()
    for m in base:
        st = m["station"]
        by_station.setdefault(st, []).append(dict(
            role="base", variant="base", model=m,
            source_id="tem_scenarios", source_path=resolve(
                next(i for i in cfg["inputs"] if i["id"] == "tem_scenarios")),
        ))
    for m in est:
        st = m["station"]
        by_station.setdefault(st, []).append(dict(
            role="estabilidad", variant=m.get("variant", "sin_variante"), model=m,
            source_id="tem_stability", source_path=resolve(
                next(i for i in cfg["inputs"] if i["id"] == "tem_stability")),
        ))
    for st, models in by_station.items():
        if len(models) != 3 or models[0]["role"] != "base":
            raise ValueError(f"{st}: se esperaban 1 base + 2 estabilidad")
        interfaces = np.asarray(models[0]["model"]["interfaces_m"], dtype=float)
        for item in models:
            rho = np.asarray(item["model"]["rho"], dtype=float)
            if rho.size != interfaces.size + 1:
                raise ValueError(f"{st}/{item['variant']}: rho e interfaces incompatibles")
    return by_station


def load_qc(cfg: dict) -> dict[str, list[dict]]:
    path = resolve(next(i for i in cfg["inputs"] if i["id"] == "tem_qc_windows"))
    rows = read_csv(path)
    out: dict[str, list[dict]] = OrderedDict()
    for row in rows:
        out.setdefault(row["station"], []).append(row)
    for st in out:
        out[st].sort(key=lambda r: int(r["gate"]))
    return out


def load_tem(cfg: dict) -> dict[str, dict]:
    out = {}
    for st, spec in cfg["tem_soundings"].items():
        parsed = tem_parser.parse_tem(Path(spec["tem"]))
        if parsed["tem_id"] != st:
            raise ValueError(f"{spec['tem']}: TEM_ID={parsed['tem_id']} != {st}")
        out[st] = parsed
    return out


def load_summary(cfg: dict) -> dict[str, dict]:
    path = resolve(next(i for i in cfg["inputs"] if i["id"] == "tem_summary"))
    return {r["station"]: r for r in read_csv(path)}


def load_checks(cfg: dict) -> dict[str, dict]:
    path = resolve(next(i for i in cfg["inputs"] if i["id"] == "tem_checks"))
    return {r["station"]: r for r in load_json(path)}


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------
def build_gate_rows(cfg: dict, qc: dict, tem: dict, models: dict):
    rows = []
    per_sounding = {}
    rules = cfg["tem_gate_rules"]
    valid_qc = set(rules["valid_qc"])
    cond_qc = set(rules["conditional_qc"])
    for st, qc_rows in qc.items():
        matches = {m["gate_reader"]: m for m in tem_parser.match_gates(
            tem[st], qc_rows, time_rel_tol=float(rules["time_match_rel_tol"]))}
        station_models = models[st]
        index_sets = [{int(i) for i in it["model"]["indices"]}
                      for it in station_models]
        inversion_indices = index_sets[0]
        counts = Counter()
        max_dt = 0.0
        max_dv_contig = 0.0
        max_t_parser = 0.0
        for row in qc_rows:
            gate = int(row["gate"])
            t_ms = float(row["t_ms"])
            t_parser = float(row["t_parser_ms"])
            max_t_parser = max(max_t_parser,
                               abs(t_parser - t_ms) / max(abs(t_ms), 1e-12))
            match = matches.get(gate)
            estado = ""
            motivo = ""
            guardas = []
            if match is None:
                estado = "no_exportado"
                motivo = "sin_observacion_en_tem"
                guardas.append("sin_observacion_tem")
            else:
                max_dt = max(max_dt, match["dt_rel"])
                if not match["time_match"]:
                    estado = "excluido"
                    motivo = "sin_emparejamiento_temporal"
                    guardas.append("emparejamiento_temporal_fallido")
                elif row["use_contiguous"] != "True" or row["qc"] not in (valid_qc | cond_qc):
                    estado = "excluido"
                    motivo = f"qc={row['qc']};use_contiguous={row['use_contiguous']}"
                    guardas.append("fuera_de_ventana_contigua")
                elif row["qc"] in cond_qc:
                    estado = "valido_condicional"
                    motivo = "qc_condicional_en_ventana_contigua"
                    guardas.extend(["ventana_contigua", "qc_condicional"])
                else:
                    estado = "valido"
                    motivo = "qc_preferente_en_ventana_contigua"
                    guardas.append("ventana_contigua")
                if row["use_contiguous"] == "True":
                    max_dv_contig = max(max_dv_contig, match["dv_rel"])
                if match["dv_rel"] > float(rules["amplitude_match_rel_tol"]):
                    guardas.append("desalineacion_amplitud_tem_lector>5%")
            if gate - 1 in inversion_indices:
                guardas.append("usado_en_inversion")
            n_models_using = sum(1 for s in index_sets if gate - 1 in s)
            counts[estado] += 1
            rows.append(dict(
                sounding_id=st,
                gate_reader=gate,
                gate_tem=fint(match["gate_tem"]) if match else "",
                t_ms_reader=fnum(row["t_ms"], 6),
                t_ms_tem=fnum(match["t_ms_tem"], 6) if match else "",
                t_ms_parser=fnum(row["t_parser_ms"], 6),
                voltage_nva_reader=fnum(row["voltage_median_nVA"], 6, True),
                voltage_nva_tem=fnum(match["voltage_nva_tem"], 6, True) if match else "",
                rhoa_ohm_m_tem=fnum(match["rhoa_ohm_m_tem"], 6) if match else "",
                sigma_effective_nva=fnum(row["sigma_effective_nVA"], 6, True),
                relative_error=fnum(row["relative_error"], 6, True),
                snr_effective=fnum(row["SNR_effective"], 6, True),
                qc=row["qc"],
                use_contiguous=row["use_contiguous"],
                exportado_tem="si" if match else "no",
                emparejamiento_temporal="si" if (match and match["time_match"]) else "no",
                desalineacion_amplitud_rel=fnum(match["dv_rel"], 6, True) if match else "",
                usado_en_inversion="si" if gate - 1 in inversion_indices else "no",
                n_modelos_que_usan_gate=fint(n_models_using),
                estado_gate=estado,
                motivo=motivo,
                guardas=";".join(guardas),
                version=GATE_VERSION,
            ))
        per_sounding[st] = dict(
            n_reader=len(qc_rows),
            n_tem=tem[st]["n_gates"],
            **{k: counts.get(k, 0) for k in
               ("valido", "valido_condicional", "excluido", "no_exportado")},
            n_usado_inversion=len(inversion_indices),
            n_gates_por_modelo=[len(s) for s in index_sets],
            max_dt_rel=float(max_dt),
            max_dv_rel_contiguous=float(max_dv_contig),
            max_t_parser_rel=float(max_t_parser),
        )
    return rows, per_sounding


# ---------------------------------------------------------------------------
# envolventes
# ---------------------------------------------------------------------------
def envelope_for(models: list[dict], freqs: list[float], tol: dict):
    interfaces = np.asarray(models[0]["model"]["interfaces_m"], dtype=float)
    zs = np.array([mt1d.z1d(freqs, m["model"]["rho"], interfaces) for m in models])
    omega = 2.0 * math.pi * np.asarray(freqs, dtype=float)
    rhoa = np.abs(zs) ** 2 / (mt1d.MU0 * omega[None, :])
    phase = np.degrees(np.angle(zs))
    logrhoa = np.log10(rhoa)
    med = np.median(logrhoa, axis=0)
    hw = (logrhoa.max(axis=0) - logrhoa.min(axis=0)) / 2.0
    phmed = np.median(phase, axis=0)
    phw = np.max(np.abs(phase - phmed[None, :]), axis=0)
    zref = zs.mean(axis=0)
    zrel = np.max(np.abs(zs / zref[None, :] - 1.0), axis=0)
    ok = ((hw <= float(tol["envelope_log10rhoa_halfwidth_max_dex"]))
          & (phw <= float(tol["envelope_phase_halfwidth_max_deg"]))
          & (zrel <= float(tol["envelope_complex_rel_max"])))
    return dict(
        logrhoa=logrhoa, phase=phase, rhoa=rhoa, zs=zs,
        med=med, min=logrhoa.min(axis=0), max=logrhoa.max(axis=0), hw=hw,
        phmed=phmed, phmin=phase.min(axis=0), phmax=phase.max(axis=0), phw=phw,
        zmed=zref, zrel=zrel, ok=ok, freqs=list(freqs),
        labels=[f"{m['role']}:{m['variant']}" for m in models],
    )


def build_envelopes(cfg: dict, models: dict, grids: dict):
    tol = cfg["tolerances"]
    out = {}
    rows_by_band = {"D0": [], "D1": []}
    guards = set(cfg["frequency_grid"]["D1"].get("guard_frequencies_hz", []))
    for st, items in models.items():
        out[st] = {}
        for band, freqs in grids.items():
            env = envelope_for(items, freqs, tol)
            out[st][band] = env
            for i, f in enumerate(freqs):
                failures = []
                if env["hw"][i] > float(tol["envelope_log10rhoa_halfwidth_max_dex"]):
                    failures.append("log10rhoa_semiancho>0.025")
                if env["phw"][i] > float(tol["envelope_phase_halfwidth_max_deg"]):
                    failures.append("fase_semiancho>1.5")
                if env["zrel"][i] > float(tol["envelope_complex_rel_max"]):
                    failures.append("Z_rel>0.065")
                evaluado = not (band == "D1" and f in guards)
                rows_by_band[band].append(dict(
                    sounding_id=st, band=band,
                    frequency_hz=ffreq(f),
                    evaluado="si" if evaluado else "no",
                    n_modelos=len(items),
                    modelos=";".join(env["labels"]),
                    log10rhoa_med=fnum(env["med"][i], 6),
                    log10rhoa_min=fnum(env["min"][i], 6),
                    log10rhoa_max=fnum(env["max"][i], 6),
                    log10rhoa_semiancho=fnum(env["hw"][i], 6),
                    phase_med_deg=fnum(env["phmed"][i], 6),
                    phase_min_deg=fnum(env["phmin"][i], 6),
                    phase_max_deg=fnum(env["phmax"][i], 6),
                    phase_semiancho_deg=fnum(env["phw"][i], 6),
                    Z_rel_max=fnum(env["zrel"][i], 6),
                    envolvente_ok="si" if env["ok"][i] else "no",
                    motivo_envolvente="dentro_tolerancia" if not failures else ";".join(failures),
                    version=ENV_VERSION,
                ))
    return out, rows_by_band


# ---------------------------------------------------------------------------
# sensibilidades
# ---------------------------------------------------------------------------
def mt_jacobian(model: dict, freqs: list[float], eps: float = 0.01):
    interfaces = np.asarray(model["interfaces_m"], dtype=float)
    rho = np.asarray(model["rho"], dtype=float)
    z0 = mt1d.z1d(freqs, rho, interfaces)
    jz = np.zeros((len(freqs), rho.size), dtype=complex)
    for j in range(rho.size):
        rp = rho.copy(); rp[j] *= math.exp(eps)
        rm = rho.copy(); rm[j] *= math.exp(-eps)
        zp = mt1d.z1d(freqs, rp, interfaces)
        zm = mt1d.z1d(freqs, rm, interfaces)
        jz[:, j] = (zp - zm) / (2.0 * eps * z0)
    return jz, z0


def depth_at_cumulative(cum: np.ndarray, tops: np.ndarray, bottoms: np.ndarray, q: float) -> float:
    j = int(np.searchsorted(cum, q))
    if j >= len(cum):
        return float(bottoms[-1])
    prev = float(cum[j - 1]) if j > 0 else 0.0
    denom = float(cum[j]) - prev
    frac = (q - prev) / denom if denom > 0 else 0.0
    frac = min(max(frac, 0.0), 1.0)
    return float(tops[j] + frac * (bottoms[j] - tops[j]))


def fraction_below(cum_share: np.ndarray, tops: np.ndarray, bottoms: np.ndarray,
                   depth: float) -> float:
    out = 0.0
    for share, top, bottom in zip(cum_share, tops, bottoms):
        if bottom <= depth:
            continue
        if top >= depth:
            out += float(share)
        else:
            out += float(share) * (bottom - depth) / (bottom - top)
    return out


def build_mt_sensitivities(cfg: dict, models: dict, grids: dict):
    tol = cfg["tolerances"]
    last_bottom = float(cfg["depth_model"]["last_layer_nominal_bottom_m"])
    rows = []
    per_station = {}
    for st, items in models.items():
        base = items[0]["model"]
        interfaces = np.asarray(base["interfaces_m"], dtype=float)
        rho = np.asarray(base["rho"], dtype=float)
        tops = np.r_[0.0, interfaces]
        bottoms = np.r_[interfaces, last_bottom]
        all_freqs = []
        for band in ("D0", "D1"):
            all_freqs.extend(grids[band])
        jz, z0 = mt_jacobian(base, all_freqs)
        absj = np.abs(jz)
        shares = absj / absj.sum(axis=1, keepdims=True)
        cum = np.cumsum(shares, axis=1)
        per_station[st] = dict(
            interfaces=interfaces, rho=rho, tops=tops, bottoms=bottoms,
            jz=jz, absj=absj, shares=shares, cum=cum,
            freqs=all_freqs,
        )
        for i, f in enumerate(all_freqs):
            band = "D0" if i < len(grids["D0"]) else "D1"
            for j in range(rho.size):
                rows.append(dict(
                    sounding_id=st, frequency_hz=ffreq(f), band=band,
                    layer_index=j + 1,
                    top_m=fnum(tops[j], 3), bottom_m=fnum(bottoms[j], 3),
                    rho_ohm_m=fnum(rho[j], 6),
                    dlnZ_dlnrho_real=fnum(jz[i, j].real, 6, True),
                    dlnZ_dlnrho_imag=fnum(jz[i, j].imag, 6, True),
                    abs_dlnZ_dlnrho=fnum(absj[i, j], 6, True),
                    share=fnum(shares[i, j], 6, True),
                    cumulative_share=fnum(cum[i, j], 6, True),
                    version=MTSENS_VERSION,
                ))
    return per_station, rows


def build_tem_sensitivities(cfg: dict, models: dict):
    thresholds = [float(x) for x in cfg["tolerances"]["tem_svd_rank_sensitivity_rel"]]
    main_thr = float(cfg["tolerances"]["tem_svd_effective_rank_rel"])
    sens_rows = []
    svd_rows = []
    per_station = {}
    last_bottom = float(cfg["depth_model"]["last_layer_nominal_bottom_m"])
    for st, items in models.items():
        base = items[0]["model"]
        jac = np.asarray(base["diagnostics"]["jacobian"], dtype=float)
        rel = np.asarray(base["relative_errors"], dtype=float)
        if jac.shape[0] != rel.size:
            raise ValueError(f"{st}: Jacobiano y errores con filas distintas")
        jw = jac / rel[:, None]
        u, s, vt = np.linalg.svd(jw, full_matrices=False)
        energy = s ** 2 / np.sum(s ** 2)
        cum_energy = np.cumsum(energy)
        rank_90 = int(np.searchsorted(cum_energy, 0.90) + 1)
        rank_99 = int(np.searchsorted(cum_energy, 0.99) + 1)
        rank_by_thr = {thr: int((s >= thr * s[0]).sum()) for thr in thresholds}
        interfaces = np.asarray(base["interfaces_m"], dtype=float)
        tops = np.r_[0.0, interfaces]
        bottoms = np.r_[interfaces, last_bottom]
        gate_indices = [int(i) for i in base["indices"]]
        times_ms = [float(t) * 1e3 for t in base["times_s"]]
        for i, gate0 in enumerate(gate_indices):
            for j in range(jac.shape[1]):
                sens_rows.append(dict(
                    sounding_id=st,
                    gate_index_inversion=i + 1,
                    gate_reader=gate0 + 1,
                    t_ms=fnum(times_ms[i], 6),
                    relative_error=fnum(rel[i], 6, True),
                    layer_index=j + 1,
                    top_m=fnum(tops[j], 3),
                    bottom_m=fnum(bottoms[j], 3),
                    dlogV_dlogrho=fnum(jac[i, j], 6, True),
                    weighted_dlogV_dlogrho=fnum(jw[i, j], 6, True),
                    version=TEMSENS_VERSION,
                ))
        for c in range(s.size):
            svd_rows.append(dict(
                sounding_id=st, component=c + 1,
                singular_value=fnum(s[c], 8, True),
                singular_value_normalized=fnum(s[c] / s[0], 8, True),
                energy_fraction=fnum(energy[c], 8, True),
                cumulative_energy=fnum(cum_energy[c], 8, True),
                rank_effective=rank_by_thr[main_thr],
                resolved="si" if c + 1 <= rank_by_thr[main_thr] else "no",
                threshold_rel=fnum(main_thr, 6, True),
                version=SVD_VERSION,
            ))
        per_station[st] = dict(
            s=s, rank_by_thr=rank_by_thr, rank_90=rank_90, rank_99=rank_99,
            jac=jac, jw=jw, rel=rel, vt=vt, gate_indices=gate_indices,
            interfaces=interfaces,
        )
    return per_station, sens_rows, svd_rows


def null_fractions(jz: np.ndarray, svd: dict, thr: float) -> np.ndarray:
    s = svd["s"]
    rank = int((s >= thr * s[0]).sum())
    if rank == 0:
        return np.ones(jz.shape[0])
    vr = svd["vt"][:rank].T
    projection = vr @ vr.T
    identity = np.eye(jz.shape[1])
    return np.array([
        float(np.linalg.norm((identity - projection) @ jz[i]) / np.linalg.norm(jz[i]))
        if np.linalg.norm(jz[i]) > 0 else 1.0
        for i in range(jz.shape[0])
    ])


# ---------------------------------------------------------------------------
# soporte
# ---------------------------------------------------------------------------
def contiguous_runs(freqs: list[float], states: list[str], target: str):
    runs = []
    current = None
    for f, state in zip(freqs, states):
        if state == target:
            if current is None:
                current = dict(f_min_hz=float(f), f_max_hz=float(f), n=1)
            else:
                current["f_max_hz"] = float(f)
                current["n"] += 1
        elif current is not None:
            runs.append(current)
            current = None
    if current is not None:
        runs.append(current)
    return runs


def build_support(cfg: dict, models: dict, grids: dict, envelopes: dict,
                  mt_sens: dict, tem_svd: dict, doi_by_station: dict):
    tol = cfg["tolerances"]
    guards = cfg["frequency_grid"]["D1"].get("guard_frequencies_hz", [])
    guard_set = set(guards)
    support = {}
    rows = []
    for st, items in models.items():
        support[st] = {}
        base = items[0]["model"]
        doi_value = float(doi_by_station[st])
        per_station_rows = []
        for band, freqs in grids.items():
            env = envelopes[st][band]
            n = len(freqs)
            offset = 0 if band == "D0" else len(grids["D0"])
            jz = mt_sens[st]["jz"][offset:offset + n]
            null = null_fractions(jz, tem_svd[st],
                                  float(tol["tem_svd_effective_rank_rel"]))
            z50 = []
            z90 = []
            frac_below = []
            for i in range(n):
                cum = mt_sens[st]["cum"][offset + i]
                z50.append(depth_at_cumulative(cum, mt_sens[st]["tops"],
                                               mt_sens[st]["bottoms"], 0.5))
                z90.append(depth_at_cumulative(cum, mt_sens[st]["tops"],
                                               mt_sens[st]["bottoms"], 0.9))
                frac_below.append(fraction_below(mt_sens[st]["shares"][offset + i],
                                                 mt_sens[st]["tops"],
                                                 mt_sens[st]["bottoms"], doi_value))
            states = []
            for i, f in enumerate(freqs):
                evaluado = not (band == "D1" and f in guard_set)
                env_ok = bool(env["ok"][i])
                prof_ok = bool(z50[i] <= doi_value
                               and frac_below[i] <= float(tol["frac_sensitivity_below_doi_max"]))
                shared_ok = bool(null[i] <= float(tol["tem_null_fraction_max"]))
                if not evaluado:
                    state = "no_evaluado"
                    motivo = "empalme_calibracion_10kHz"
                else:
                    failures = []
                    if not env_ok:
                        failures.append("envolvente_modelos_excede_tolerancia")
                    if not prof_ok:
                        failures.append("profundidad_sensibilidad_MT_excede_DOI_TEM")
                    if not shared_ok:
                        failures.append("sensibilidad_MT_en_subespacio_no_resuelto_por_TEM")
                    if failures:
                        state = "no_respaldada"
                        motivo = ";".join(failures)
                    else:
                        state = "condicional"
                        motivo = ("criterios_numericos_cumplidos;"
                                  "tope_condicional_por_escenarios_y_bloqueos")
                states.append(state)
                per_station_rows.append(dict(
                    sounding_id=st, band=band, frequency_hz=ffreq(f),
                    observable="Zxy(rho_a,fase)", estado=state,
                    log10rhoa_semiancho=fnum(env["hw"][i], 6),
                    phase_semiancho_deg=fnum(env["phw"][i], 6),
                    Z_rel_max=fnum(env["zrel"][i], 6),
                    envolvente_ok="si" if env_ok else "no",
                    z50_m=fnum(z50[i], 3),
                    z90_m=fnum(z90[i], 3),
                    doi_m=fnum(doi_value, 3),
                    frac_sensibilidad_bajo_doi=fnum(frac_below[i], 6),
                    profundidad_ok="si" if prof_ok else "no",
                    tem_rank_efectivo=tem_svd[st]["rank_by_thr"][
                        float(tol["tem_svd_effective_rank_rel"])],
                    tem_null_fraction=fnum(null[i], 6),
                    sensibilidad_compartida_ok="si" if shared_ok else "no",
                    n_gates_inversion=int(tem_svd[st]["jac"].shape[0]),
                    n_modelos=len(items),
                    supuestos=("1D_isotropo;Zxx=Zyy=0;Zxy=-Zyx;T=0;"
                               "lazo_cuadrado_coincidente;"
                               "modelos_escenario_no_posterior;"
                               "C_d=sigma_effective_nVA"),
                    guardas=("conjunto_escenario_no_posterior;"
                             "F_red_validada_no_definida;B-P0-03;B-P0-04;"
                             "DOI_no_validada;sin_sintesis_ni_entrenamiento"),
                    motivo=motivo,
                    version=SUPPORT_VERSION,
                ))
            support[st][band] = dict(
                freqs=freqs, states=states, rows=per_station_rows[-n:],
                z50=z50, z90=z90, frac_below=frac_below, null=null,
                doi_m=doi_value,
            )
        rows.extend(per_station_rows)
    return support, rows


# ---------------------------------------------------------------------------
# tabla ARMT
# ---------------------------------------------------------------------------
def build_armt_support(cfg: dict, grids: dict, manifest: dict, splits: dict):
    soundings = ";".join(cfg["scope"]["tem_soundings"])
    guard_set = set(cfg["frequency_grid"]["D1"].get("guard_frequencies_hz", []))
    rows = []
    for rec in manifest["armt_records"]:
        rid = rec["record_id"]
        split = splits[rid]["split"]
        for band, freqs in grids.items():
            for f in freqs:
                motivo = ("B-P0-03_vinculo_TEM_ARMT_no_verificado; "
                          "B-P0-06_F_red_validada_no_definida; "
                          "B-P0-04_calibracion_parcial")
                if band == "D1" and f in guard_set:
                    motivo += "; empalme_calibracion_10kHz"
                rows.append(dict(
                    record_id=rid, split=split, band=band,
                    frequency_hz=ffreq(f), observable="Zxy(rho_a,fase)",
                    estado="no_evaluado", tem_sounding_id="",
                    candidatos_tem_disponibles=soundings,
                    log10rhoa_semiancho="", phase_semiancho_deg="", Z_rel_max="",
                    z50_m="", doi_m="", tem_null_fraction="",
                    supuestos=("1D_isotropo;Zxx=Zyy=0;Zxy=-Zyx;T=0;"
                               "sin_sondeo_TEM_vinculado"),
                    guardas=("sin_soporte_habilitado;sin_etiquetas_TEM;"
                             "sin_entrenamiento;sin_inferencia"),
                    motivo=motivo, version=AMT_VERSION,
                ))
    return rows


# ---------------------------------------------------------------------------
# proveniencia
# ---------------------------------------------------------------------------
def build_provenance(cfg: dict, inputs: list[dict], models: dict, tem: dict,
                     gates_summary: dict, checks: dict, mt_test: dict,
                     t_parser_max_rel: float):
    model_rows = []
    for st, items in models.items():
        interfaces = np.asarray(items[0]["model"]["interfaces_m"], dtype=float)
        for item in items:
            m = item["model"]
            model_rows.append(dict(
                model_id=f"{st}__{'base' if item['role'] == 'base' else item['variant']}",
                sounding_id=st, role=item["role"], variant=item["variant"],
                source_file=str(item["source_path"]),
                source_sha256=sha256_file(item["source_path"]),
                source_id=item["source_id"],
                n_layers=len(m["rho"]),
                interfaces_m=[float(x) for x in interfaces],
                rho_ohm_m=[float(x) for x in m["rho"]],
                wrms_log=float(m.get("wrms_log", float("nan"))),
                rms_percent=float(m.get("rms_percent", float("nan"))),
                regularization_lambda=float(m.get("regularization_lambda", float("nan"))),
                is_posterior=False,
                n_gates_inversion=len(m.get("indices", [])),
                gate_indices_1based=[int(i) + 1 for i in m.get("indices", [])],
                has_diagnostics_jacobian=bool("diagnostics" in m),
                notes=("escenario de inversion regularizada; "
                       "no es un posterior probabilistico"),
            ))
    candidates = []
    for st, parsed in tem.items():
        spec = cfg["tem_soundings"][st]
        candidates.append(dict(
            sounding_id=st,
            tem_path=spec["tem"], tem_sha256=sha256_file(Path(spec["tem"])),
            model_path=spec["model"], model_sha256=sha256_file(Path(spec["model"])),
            coordinate_type=parsed["coordinate_type"],
            datum=parsed["datum"], elevation=parsed["elevation"],
            rx_x=parsed["rx_x"], rx_y=parsed["rx_y"],
            tx_x=parsed["tx_x"], tx_y=parsed["tx_y"],
            acquisition_date=parsed["acquisition_date"],
            acquisition_time=parsed["acquisition_time"],
            receiver=parsed["receiver"], transmitter=parsed["transmitter"],
            tx_area_m2=parsed["tx_area_m2"], rx_area_m2=parsed["rx_area_m2"],
            current_a=parsed["current_a"], turnoff_us=parsed["turnoff_us"],
            user_delay_us=parsed["user_delay_us"],
            n_gates=parsed["n_gates"], t_min_ms=parsed["t_min_ms"],
            t_max_ms=parsed["t_max_ms"],
            link_status="no_verificado", link_record_ids=[],
            notes=["coordenadas metricas locales sin datum ni elevacion",
                   "fecha y hora de adquisicion vacias",
                   "sin vinculo documentado a los registros ARMT"],
        ))
    findings = [
        dict(id="F-P2T-01",
             descripcion="El gate j del .tem coincide con el gate j+1 de la tabla del lector.",
             evidencia=("Emparejamiento por tiempo y amplitud en los 6 sondeos; "
                        "el .tem exporta los gates 2..n+1 de la tabla del lector.")),
        dict(id="F-P2T-02",
             descripcion="t_parser_ms no es un reloj independiente: esta desalineado respecto de la amplitud de su propia fila desde el gate 4.",
             evidencia=(f"La diferencia relativa maxima entre t_ms y t_parser_ms es "
                        f"{t_parser_max_rel:.4f} global ("
                        + "; ".join(f"{st}={v['max_t_parser_rel']:.4f}"
                                    for st, v in gates_summary.items())
                        + "). El .tem coincide con t_ms en el desplazamiento +1. "
                          "clock_max_relative_pct del dosier (35.7-40.6%) mide el "
                          "cambio de respuesta TEM al sustituir t_ms por t_parser_ms; "
                          "es un artefacto de alineacion de tablas, no una deriva de "
                          "reloj demostrada.")),
        dict(id="F-P2T-03",
             descripcion="La amplitud .tem y la amplitud del lector difieren dentro de la ventana util.",
             evidencia=("Maxima diferencia relativa por sondeo: "
                        + "; ".join(f"{st}={v['max_dv_rel_contiguous']:.3f}"
                                    for st, v in gates_summary.items())
                        + ". La inversion uso la tabla del lector; la diferencia "
                          "es un sesgo sistematico no incluido en C_d.")),
        dict(id="F-P2T-04",
             descripcion="Los 18 modelos son escenarios, no un posterior probabilistico.",
             evidencia=("6 modelos base + 12 modelos de estabilidad; "
                        "regularization_lambda 1.0-4.0; wrms_log 0.25-1.35; "
                        "sin covarianza posterior.")),
        dict(id="F-P2T-05",
             descripcion="El rango efectivo del Jacobiano TEM es bajo y el resultado de sensibilidad compartida depende del umbral de rango.",
             evidencia=("Rango efectivo al 1%: "
                        + "; ".join(f"{st}={v['rank_by_thr'][0.01]}"
                                    for st, v in checks.items())
                        + ". Se reportan umbrales 1%, 0.1% y 0.01%.")),
        dict(id="F-P2T-06",
             descripcion="La DOI no esta validada; solo existe una DOI operativa creible.",
             evidencia="DOI_validated_m vacia en los 6 sondeos; DOI_operativa_creible_m 100 m (SER-09/10) y 175 m (SER-11..14)."),
        dict(id="F-P2T-07",
             descripcion="10 kHz coincide con el empalme de calibracion D1.",
             evidencia="El punto 10000 Hz se conserva como escenario separado y queda no_evaluado."),
        dict(id="F-P2T-08",
             descripcion="No hay vinculo TEM-ARMT verificado.",
             evidencia="B-P0-03 abierto; tem_link.status=no_verificado en los 15 registros y en los 6 sondeos. tem_amt_support.csv queda no_evaluado."),
    ]
    return dict(
        artifact="model_provenance", version=PROV_VERSION,
        generated_at_utc=utc_now(), stage=2, substage="P2-T",
        scope=cfg["scope"],
        inputs=inputs,
        software=dict(
            p2t=dict(version=VERSION, path=str(Path(__file__)),
                     sha256=sha256_file(Path(__file__))),
            mt1d=dict(version=mt1d.VERSION, path=str(HERE / "mt1d.py"),
                      sha256=sha256_file(HERE / "mt1d.py")),
            tem_parser=dict(version=tem_parser.VERSION, path=str(HERE / "tem_parser.py"),
                            sha256=sha256_file(HERE / "tem_parser.py")),
            python=platform.python_version(), numpy=np.__version__,
        ),
        directo=jsonable(mt_test),
        models=model_rows,
        tem_candidates=candidates,
        findings=findings,
        limitations=[
            "Directo MT solo 1D isotropo horizontal; no modela 3D, anisotropia, topografia ni distorsion galvanica.",
            "La inversion TEM uso empymod con lazo cuadrado coincidente y no incluye filtros ni forma de onda periodica completa.",
            "Los modelos son escenarios regularizados, no un posterior; no hay covarianza de error.",
            "La calibracion .clb no tiene fecha, certificado ni cadena de aplicacion verificada.",
            "El vinculo TEM-ARMT no esta verificado; el soporte por sondeo no se transfiere a los registros.",
            "La DOI es operativa y no validada.",
            "La amplitud .tem y la del lector difieren hasta 12.8% en la ventana util.",
            "No se dispone de un motor MT externo independiente; el directo se valido con semiespacio analitico, formulacion matricial, limites y convergencia.",
            "La tabla de soporte ARMT permanece vacia por B-P0-03, no por ausencia de datos TEM.",
        ],
        guards=cfg["guards"]["global"] + cfg["guards"]["data"],
        blockers=cfg["blockers"],
        status="DIAGNOSTICO_CON_SOPORTE_AMT_VACIO",
    )


# ---------------------------------------------------------------------------
# resumen y reporte
# ---------------------------------------------------------------------------
def summarize(cfg: dict, gates_summary: dict, envelopes: dict, support: dict,
              armt_rows: list[dict], mt_test: dict, checks: dict):
    state_totals = Counter()
    per_sounding = {}
    for st, bands in support.items():
        per_sounding[st] = {}
        for band, data in bands.items():
            counts = Counter(data["states"])
            state_totals.update(counts)
            runs = contiguous_runs(data["freqs"], data["states"], "condicional")
            reasons = Counter()
            for row in data["rows"]:
                if row["estado"] == "no_respaldada":
                    for reason in row["motivo"].split(";"):
                        reasons[reason] += 1
            per_sounding[st][band] = dict(
                n=len(data["states"]), **{k: counts.get(k, 0) for k in
                                          ("respaldada", "condicional", "no_respaldada", "no_evaluado")},
                bandas_condicionales=runs,
                motivos_no_respaldada=dict(reasons),
            )
    armt_states = Counter(r["estado"] for r in armt_rows)
    guard_freqs = set(cfg["frequency_grid"]["D1"].get("guard_frequencies_hz", []))
    env_summary = {}
    for st, bands in envelopes.items():
        env_summary[st] = {}
        for band, env in bands.items():
            evaluated = np.array([not (band == "D1" and f in guard_freqs)
                                  for f in env["freqs"]])
            hw_eval = env["hw"][evaluated]
            phw_eval = env["phw"][evaluated]
            zrel_eval = env["zrel"][evaluated]
            env_summary[st][band] = dict(
                n=len(env["ok"]), n_evaluado=int(evaluated.sum()),
                n_dentro=int((env["ok"] & evaluated).sum()),
                n_no_evaluado=int((~evaluated).sum()),
                min_semiancho_log10rhoa=float(np.min(hw_eval)),
                max_semiancho_log10rhoa=float(np.max(hw_eval)),
                min_semiancho_phase_deg=float(np.min(phw_eval)),
                max_semiancho_phase_deg=float(np.max(phw_eval)),
                max_Z_rel=float(np.max(zrel_eval)),
            )
    svd_summary = {}
    for st, data in checks.items():
        svd_summary[st] = dict(
            rank_effective_1pct=data["rank_by_thr"][0.01],
            rank_effective_0p1pct=data["rank_by_thr"][0.001],
            rank_effective_0p01pct=data["rank_by_thr"][0.0001],
            rank_90=data["rank_90"], rank_99=data["rank_99"],
            singular_values=[float(x) for x in data["s"]],
        )
    return dict(
        artifact="resumen_p2t", version=SUMMARY_VERSION,
        generated_at_utc=utc_now(), stage=2, substage="P2-T",
        scope=cfg["scope"],
        directo=jsonable(mt_test),
        gates=dict(per_sounding=gates_summary, totals={
            "n_reader": sum(v["n_reader"] for v in gates_summary.values()),
            "n_tem": sum(v["n_tem"] for v in gates_summary.values()),
            "valido": sum(v["valido"] for v in gates_summary.values()),
            "valido_condicional": sum(v["valido_condicional"] for v in gates_summary.values()),
            "excluido": sum(v["excluido"] for v in gates_summary.values()),
            "no_exportado": sum(v["no_exportado"] for v in gates_summary.values()),
        }),
        envelopes=env_summary,
        support=dict(per_sounding=per_sounding, totals=dict(state_totals)),
        armt_support=dict(
            n_records=15, n_rows=len(armt_rows),
            states=dict(armt_states), soporte_habilitado=False,
            motivo_principal="B-P0-03_vinculo_TEM_ARMT_no_verificado",
        ),
        tem_svd=svd_summary,
        conclusion=("Ninguna frecuencia alcanza el estado respaldada. "
                    "Las bandas condicionales por sondeo son diagnosticas y no se "
                    "transfieren a los registros ARMT. tem_amt_support.csv queda "
                    "no_evaluado por B-P0-03; no se habilita sintesis, etiquetas TEM, "
                    "entrenamiento ni inferencia guiados por TEM."),
    )


def render_report(cfg: dict, summary: dict, provenance: dict) -> str:
    st_names = list(cfg["scope"]["tem_soundings"])
    lines = []
    lines.append("# P2-T — Diagnóstico de soporte TEM–MT/AMT")
    lines.append("")
    lines.append(f"Versión: `{VERSION}`. Generado: `{summary['generated_at_utc']}`.")
    lines.append("")
    lines.append("## Resultado en una línea")
    lines.append("")
    lines.append("No se alcanza ninguna frecuencia `respaldada`. El soporte por sondeo es "
                 "parcial y `condicional`; la tabla `tem_amt_support.csv` queda vacía "
                 "(`no_evaluado`) porque el vínculo TEM–ARMT no está verificado "
                 "(B-P0-03). No se habilita síntesis, etiquetado TEM, entrenamiento ni "
                 "inferencia guiados por TEM.")
    lines.append("")
    lines.append("## Alcance y reglas")
    lines.append("")
    lines.append("- Bandas: D0 (5–1000 Hz) y D1 (1000 Hz–10 kHz). El punto de 10 kHz es un "
                 "escenario separado por el empalme de calibración y queda `no_evaluado`; "
                 "la respuesta útil declarada llega hasta 9.9 kHz.")
    lines.append("- Observable: `Zxy` en 1D isotrópico, expresado como `rho_a` y fase. "
                 "`Zxx=Zyy=0`, `Zxy=-Zyx` y `T=0` son supuestos 1D, no información "
                 "tensorial resuelta por TEM.")
    lines.append("- No se generan series temporales, no se entrena y no se infiere.")
    lines.append("")
    lines.append("## 1. Gates TEM")
    lines.append("")
    lines.append("| Sondeo | Gates lector | Gates .tem | válidos | condicionales | excluidos | no exportados | máx. Δt rel. | máx. ΔV rel. (ventana) |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for st in st_names:
        g = summary["gates"]["per_sounding"][st]
        lines.append(f"| {st} | {g['n_reader']} | {g['n_tem']} | {g['valido']} | "
                     f"{g['valido_condicional']} | {g['excluido']} | {g['no_exportado']} | "
                     f"{g['max_dt_rel']:.2e} | {g['max_dv_rel_contiguous']:.3f} |")
    tot = summary["gates"]["totals"]
    lines.append(f"| **Total** | {tot['n_reader']} | {tot['n_tem']} | {tot['valido']} | "
                 f"{tot['valido_condicional']} | {tot['excluido']} | {tot['no_exportado']} | | |")
    lines.append("")
    lines.append("Hallazgos de alineación:")
    lines.append("")
    lines.append("- El gate *j* del `.tem` coincide con el gate *j+1* de la tabla del lector. "
                 "El `.tem` exporta los gates 2..n+1.")
    lines.append("- `t_parser_ms` está desalineado respecto de la amplitud de su propia fila "
                 "desde el gate 4. La diferencia relativa máxima entre `t_ms` y "
                 "`t_parser_ms` es 22.5–26.0 % por sondeo (26.0 % global), mientras el "
                 "`.tem` coincide con `t_ms` en el desplazamiento +1 con menos de 0.084 % "
                 "de diferencia. `clock_max_relative_pct` del dosier (35.7–40.6 %) mide el "
                 "cambio de respuesta TEM al sustituir `t_ms` por `t_parser_ms`; es un "
                 "artefacto de alineación de tablas, no una deriva de reloj demostrada.")
    lines.append("- La amplitud `.tem` y la del lector difieren hasta 12.8 % dentro de la "
                 "ventana útil. La inversión TEM usó la tabla del lector; la diferencia es "
                 "un sesgo sistemático no incluido en `C_d` y se conserva como guarda.")
    lines.append("- `usado_en_inversion` marca los gates del **modelo base** del sondeo, que es "
                 "el que aporta el Jacobiano TEM usado en el análisis SVD. "
                 "`n_modelos_que_usan_gate` cuenta cuántos de los 3 modelos del sondeo usan "
                 "ese gate: el número de gates de inversión es 21–22 en los modelos base y "
                 "19–22 en los de estabilidad, no siempre 22.")
    lines.append("")
    lines.append("## 2. Directo MT 1D")
    lines.append("")
    lines.append("| Prueba | Valor | Límite | Unidad | Pasa |")
    lines.append("|---|---:|---:|---|---|")
    for t in summary["directo"]["pruebas"]:
        lines.append(f"| {t['prueba']} | {t['valor']:.3e} | {t['limite']:.3e} | "
                     f"{t['unidad']} | {'sí' if t['pasa'] else 'no'} |")
    lines.append("")
    lines.append(f"Error relativo máximo del directo: `{summary['directo']['max_error_rel']:.3e}`. "
                 f"Meta P2 (Z ≤ 1 %, fase ≤ 0.5°): "
                 f"`{'cumple' if summary['directo']['cumple_meta_p2'] else 'no cumple'}`. "
                 "Esta precisión numérica no demuestra soporte TEM.")
    lines.append("")
    lines.append("## 3. Envolventes predictivas")
    lines.append("")
    lines.append("| Sondeo | Banda | n | evaluados | dentro | semiancho log10 rho_a mín–máx | semiancho fase mín–máx (°) | máx. Z rel. |")
    lines.append("|---|---|---:|---:|---:|---|---|---:|")
    for st in st_names:
        for band in ("D0", "D1"):
            e = summary["envelopes"][st][band]
            lines.append(f"| {st} | {band} | {e['n']} | {e['n_evaluado']} | {e['n_dentro']} | "
                         f"{e['min_semiancho_log10rhoa']:.4f}–{e['max_semiancho_log10rhoa']:.4f} | "
                         f"{e['min_semiancho_phase_deg']:.3f}–{e['max_semiancho_phase_deg']:.3f} | "
                         f"{e['max_Z_rel']:.4f} |")
    lines.append("")
    lines.append("Los recuentos y los semianchos excluyen el punto de 10 kHz, que no se "
                 "evalúa. Umbrales de diseño: semiancho de `log10 rho_a` ≤ 0.025 dex, fase "
                 "≤ 1.5° y `Z_rel` ≤ 0.065 respecto de la media compleja de los 3 modelos "
                 "(`max |Z_i/Z_ref − 1|`). Una nube estrecha de 3 modelos con la misma "
                 "regularización no demuestra por sí sola que TEM haya resuelto la "
                 "respuesta; por eso el estado máximo es `condicional`.")
    lines.append("")
    lines.append("## 4. Sensibilidad compartida y DOI")
    lines.append("")
    lines.append("| Sondeo | Rango efectivo TEM al 1 % | Componentes para 90 % de energía (S²) | DOI operativa (m) | Bandas condicionales |")
    lines.append("|---|---:|---:|---:|---|")
    for st in st_names:
        svd = summary["tem_svd"][st]
        runs = []
        for band in ("D0", "D1"):
            for r in summary["support"]["per_sounding"][st][band]["bandas_condicionales"]:
                runs.append(f"{band} {r['f_min_hz']:.3g}–{r['f_max_hz']:.3g} Hz ({r['n']})")
        doi = summary["doi"][st]["doi_operativa_creible_m"]
        lines.append(f"| {st} | {svd['rank_effective_1pct']} | {svd['rank_90']} | "
                     f"{doi:.0f} | {('; '.join(runs)) if runs else 'ninguna'} |")
    lines.append("")
    lines.append("La DOI usada es `DOI_operativa_creible_m` (100 m en SER-09/10; 175 m en "
                 "SER-11..14). `DOI_validated_m` está vacía en los 6 sondeos. El criterio "
                 "de profundidad exige `z50 ≤ DOI` y una fracción de sensibilidad bajo la "
                 "DOI ≤ 0.10.")
    lines.append("")
    lines.append("El rango efectivo del Jacobiano TEM es 4 al 1 %, 6–7 al 0.1 % y 7–8 al "
                 "0.01 %; `resumen_p2t.json` conserva los tres umbrales para dejar visible "
                 "la dependencia. El diagnóstico principal se informa al 1 %, que es el más "
                 "exigente de los tres. El Jacobiano TEM usado es el del modelo base; los 12 "
                 "modelos de estabilidad aportan a las envolventes MT, no al análisis SVD.")
    lines.append("")
    lines.append("La columna de energía no es un rango de resolución: cuenta cuántos "
                 "componentes acumulan el 90 % de la energía de los valores singulares al "
                 "cuadrado. Como el primero concentra más del 90 %, vale 1 aunque 4 "
                 "componentes superen el 1 % de `s1`. El criterio de sensibilidad compartida "
                 "usa ese rango al 1 %, no la energía.")
    lines.append("")
    lines.append("Las bandas condicionales dependen de la DOI operativa y no son intervalos "
                 "de confianza: son rangos diagnósticos de una nube de escenarios. SER-09 y "
                 "SER-10 no tienen banda condicional porque la sensibilidad MT a esas "
                 "frecuencias se reparte bajo su DOI de 100 m.")
    lines.append("")
    lines.append("## 5. Decisión de soporte")
    lines.append("")
    lines.append("| Sondeo | Banda | condicional | no respaldada | no evaluado | motivos principales |")
    lines.append("|---|---|---:|---:|---:|---|")
    for st in st_names:
        for band in ("D0", "D1"):
            s = summary["support"]["per_sounding"][st][band]
            reasons = ", ".join(f"{k} ({v})" for k, v in
                                sorted(s["motivos_no_respaldada"].items(),
                                       key=lambda kv: -kv[1])[:3])
            lines.append(f"| {st} | {band} | {s['condicional']} | {s['no_respaldada']} | "
                         f"{s['no_evaluado']} | {reasons or '—'} |")
    lines.append("")
    lines.append("Ninguna fila alcanza `respaldada`. Las bandas condicionales son "
                 "diagnósticas del sondeo TEM; no se transfieren a los registros ARMT.")
    lines.append("")
    lines.append("## 6. Tabla ARMT")
    lines.append("")
    a = summary["armt_support"]
    lines.append(f"`tem_amt_support.csv`: {a['n_rows']} filas "
                 f"({a['n_records']} registros × D0/D1 × grilla P1). Estados: "
                 f"`{a['states']}`. `soporte_habilitado = false`. Motivo principal: "
                 f"`{a['motivo_principal']}`.")
    lines.append("")
    lines.append("`tem_sounding_id` queda vacío porque no hay vínculo verificado: no se "
                 "asigna sondeo por proximidad ni por conveniencia. "
                 "`candidatos_tem_disponibles` enumera los 6 sondeos existentes como "
                 "posibles, sin afirmar correspondencia. Las columnas de envolvente y "
                 "sensibilidad quedan vacías: un soporte `no_evaluado` no hereda los "
                 "números diagnósticos del sondeo.")
    lines.append("")
    lines.append("Esto es un soporte vacío, no una afirmación de que el ARMT observado sea "
                 "inutilizable. La adquisición se conserva y la estimación convencional "
                 "sigue su propia evaluación.")
    lines.append("")
    lines.append("## 7. Bloqueos y guardas")
    lines.append("")
    for b in cfg["blockers"]:
        lines.append(f"- `{b['id']}`: {b['impact']}")
    lines.append("")
    lines.append("Guardas: no se generan series sintéticas, no se habilitan etiquetas TEM, "
                 "no se entrena ni infiere con TEM, no se asigna sondeo a registro ARMT y "
                 "no se amplía el soporte por extrapolación.")
    lines.append("")
    lines.append("## 8. Reproducción")
    lines.append("")
    lines.append("```powershell")
    lines.append("python etapa2/p2t.py")
    lines.append("python etapa2/validar_etapa2.py")
    lines.append("```")
    lines.append("")
    lines.append("Entregables: `tem_valid_gates.csv`, `tem_amt_support.csv`, "
                 "`model_provenance.json`, `diagnostico_tem/envolventes_D0.csv`, "
                 "`diagnostico_tem/envolventes_D1.csv`, "
                 "`diagnostico_tem/soporte_por_sondeo.csv`, "
                 "`diagnostico_tem/sensibilidades_mt.csv`, "
                 "`diagnostico_tem/sensibilidades_tem.csv`, "
                 "`diagnostico_tem/sensibilidad_tem_svd.csv`, "
                 "`diagnostico_tem/comparacion_sensibilidad_doi.csv`, "
                 "`diagnostico_tem/pruebas_directo.csv` y `diagnostico_tem/resumen_p2t.json`.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    cfg = load_config()
    HERE.mkdir(parents=True, exist_ok=True)
    outdir = HERE / "diagnostico_tem"
    outdir.mkdir(parents=True, exist_ok=True)

    # inputs y hashes
    inputs = []
    for item in cfg["inputs"]:
        p = resolve(item)
        entry = dict(id=item["id"], path=item["path"], base=item["base"],
                     role=item["role"], path_abs=str(p))
        if p.is_file():
            entry["sha256"] = sha256_file(p)
            entry["size_bytes"] = p.stat().st_size
        else:
            entry["sha256"] = ""
            entry["size_bytes"] = ""
        inputs.append(entry)

    manifest = load_json(resolve(next(i for i in cfg["inputs"] if i["id"] == "p0_manifest")))
    splits_rows = read_csv(resolve(next(i for i in cfg["inputs"] if i["id"] == "p0_splits")))
    splits = {r["record_id"]: r for r in splits_rows}
    models = load_models(cfg)
    qc = load_qc(cfg)
    tem = load_tem(cfg)
    tem_summary = load_summary(cfg)
    checks = load_checks(cfg)
    grids = {band: load_grid(cfg, band) for band in ("D0", "D1")}

    # gates
    gate_rows, gate_summary = build_gate_rows(cfg, qc, tem, models)
    write_csv(HERE / cfg["outputs"]["tem_valid_gates"], [
        "sounding_id", "gate_reader", "gate_tem", "t_ms_reader", "t_ms_tem",
        "t_ms_parser", "voltage_nva_reader", "voltage_nva_tem",
        "rhoa_ohm_m_tem", "sigma_effective_nva", "relative_error",
        "snr_effective", "qc", "use_contiguous", "exportado_tem",
        "emparejamiento_temporal", "desalineacion_amplitud_rel",
        "usado_en_inversion", "n_modelos_que_usan_gate", "estado_gate",
        "motivo", "guardas", "version",
    ], gate_rows)

    # envolventes
    envelopes, env_rows = build_envelopes(cfg, models, grids)
    write_csv(outdir / "envolventes_D0.csv", [
        "sounding_id", "band", "frequency_hz", "evaluado", "n_modelos",
        "modelos", "log10rhoa_med", "log10rhoa_min", "log10rhoa_max",
        "log10rhoa_semiancho", "phase_med_deg", "phase_min_deg",
        "phase_max_deg", "phase_semiancho_deg", "Z_rel_max",
        "envolvente_ok", "motivo_envolvente", "version",
    ], env_rows["D0"])
    write_csv(outdir / "envolventes_D1.csv", [
        "sounding_id", "band", "frequency_hz", "evaluado", "n_modelos",
        "modelos", "log10rhoa_med", "log10rhoa_min", "log10rhoa_max",
        "log10rhoa_semiancho", "phase_med_deg", "phase_min_deg",
        "phase_max_deg", "phase_semiancho_deg", "Z_rel_max",
        "envolvente_ok", "motivo_envolvente", "version",
    ], env_rows["D1"])

    # sensibilidades
    mt_sens, mt_rows = build_mt_sensitivities(cfg, models, grids)
    write_csv(outdir / "sensibilidades_mt.csv", [
        "sounding_id", "frequency_hz", "band", "layer_index", "top_m",
        "bottom_m", "rho_ohm_m", "dlnZ_dlnrho_real", "dlnZ_dlnrho_imag",
        "abs_dlnZ_dlnrho", "share", "cumulative_share", "version",
    ], mt_rows)
    tem_svd, tem_rows, svd_rows = build_tem_sensitivities(cfg, models)
    write_csv(outdir / "sensibilidades_tem.csv", [
        "sounding_id", "gate_index_inversion", "gate_reader", "t_ms",
        "relative_error", "layer_index", "top_m", "bottom_m",
        "dlogV_dlogrho", "weighted_dlogV_dlogrho", "version",
    ], tem_rows)
    write_csv(outdir / "sensibilidad_tem_svd.csv", [
        "sounding_id", "component", "singular_value",
        "singular_value_normalized", "energy_fraction", "cumulative_energy",
        "rank_effective", "resolved", "threshold_rel", "version",
    ], svd_rows)

    # soporte (necesita DOI por estacion)
    doi_by_station = {st: float(tem_summary[st]["DOI_operativa_creible_m"])
                      for st in models}
    support, support_rows = build_support(cfg, models, grids, envelopes, mt_sens,
                                          tem_svd, doi_by_station)
    write_csv(outdir / "soporte_por_sondeo.csv", [
        "sounding_id", "band", "frequency_hz", "observable", "estado",
        "log10rhoa_semiancho", "phase_semiancho_deg", "Z_rel_max",
        "envolvente_ok", "z50_m", "z90_m", "doi_m",
        "frac_sensibilidad_bajo_doi", "profundidad_ok", "tem_rank_efectivo",
        "tem_null_fraction", "sensibilidad_compartida_ok",
        "n_gates_inversion", "n_modelos", "supuestos", "guardas",
        "motivo", "version",
    ], support_rows)
    write_csv(outdir / "comparacion_sensibilidad_doi.csv", [
        "sounding_id", "band", "frequency_hz", "z50_m", "z90_m", "doi_m",
        "frac_sensibilidad_bajo_doi", "profundidad_ok", "tem_null_fraction",
        "sensibilidad_compartida_ok", "tem_rank_efectivo",
        "n_gates_inversion", "version",
    ], [dict(r, version=DOI_VERSION) for r in support_rows])

    # tabla ARMT
    armt_rows = build_armt_support(cfg, grids, manifest, splits)
    write_csv(HERE / cfg["outputs"]["tem_amt_support"], [
        "record_id", "split", "band", "frequency_hz", "observable", "estado",
        "tem_sounding_id", "candidatos_tem_disponibles",
        "log10rhoa_semiancho", "phase_semiancho_deg", "Z_rel_max",
        "z50_m", "doi_m", "tem_null_fraction", "supuestos", "guardas",
        "motivo", "version",
    ], armt_rows)

    # pruebas del directo
    model_list = [(f"{st}:{it['variant']}", it["model"]["rho"],
                   models[st][0]["model"]["interfaces_m"])
                  for st, items in models.items() for it in items]
    mt_test = mt1d.self_test(model_list)
    write_csv(outdir / "pruebas_directo.csv",
              ["prueba", "valor", "limite", "unidad", "pasa", "detalle", "version"],
              [dict(t, version=mt1d.VERSION) for t in mt_test["pruebas"]])

    # maxima diferencia t_ms vs t_parser_ms (evidencia de alineacion)
    t_parser_max_rel = 0.0
    for row in qc_rows_all(cfg):
        t1 = float(row["t_ms"]); t2 = float(row["t_parser_ms"])
        t_parser_max_rel = max(t_parser_max_rel, abs(t2 - t1) / max(abs(t1), 1e-12))

    # proveniencia y resumen
    provenance = build_provenance(cfg, inputs, models, tem, gate_summary,
                                  tem_svd, mt_test, t_parser_max_rel)
    write_json(HERE / cfg["outputs"]["model_provenance"], jsonable(provenance))

    summary = summarize(cfg, gate_summary, envelopes, support, armt_rows,
                        mt_test, tem_svd)
    summary["doi"] = {st: dict(
        doi_operativa_creible_m=float(tem_summary[st]["DOI_operativa_creible_m"]),
        doi_validada_m=tem_summary[st]["DOI_validated_m"] or None,
        doi_status=tem_summary[st]["DOI_status"],
        bloques_validados_m=tem_summary[st]["bloques_validados_m"],
        deepest_detected_block_bottom_m=checks[st].get("deepest_detected_block_bottom_m"),
        clock_max_relative_pct=float(checks[st].get("clock_max_relative_pct", 0.0)),
    ) for st in models}
    summary["alignment"] = dict(
        t_parser_max_relative=t_parser_max_rel,
        per_sounding={st: dict(
            max_t_parser_relative=float(v["max_t_parser_rel"]),
            max_dt_tem_reader_relative=float(v["max_dt_rel"]),
            clock_max_relative_pct=float(checks[st].get("clock_max_relative_pct", 0.0)),
        ) for st, v in gate_summary.items()},
        note=("t_parser_ms esta desalineado respecto de la amplitud y no es un "
              "reloj independiente; el .tem coincide con t_ms en +1 gate. "
              "clock_max_relative_pct mide el efecto de usar t_parser_ms, "
              "no una deriva de reloj demostrada."),
    )
    # bandas condicionales con DOI, para el reporte
    for st in models:
        for band in ("D0", "D1"):
            for run in summary["support"]["per_sounding"][st][band]["bandas_condicionales"]:
                run["doi_m"] = float(tem_summary[st]["DOI_operativa_creible_m"])
    write_json(outdir / "resumen_p2t.json", jsonable(summary))

    (HERE / cfg["outputs"]["report"]).write_text(
        render_report(cfg, summary, provenance), encoding="utf-8")

    print(json.dumps({
        "version": VERSION,
        "gates": summary["gates"]["totals"],
        "support_totals": summary["support"]["totals"],
        "armt_support": summary["armt_support"],
        "directo_pasa": summary["directo"]["pasa"],
        "files": sorted(p.name for p in HERE.rglob("*") if p.is_file()),
    }, ensure_ascii=False, indent=1))


def qc_rows_all(cfg: dict):
    path = resolve(next(i for i in cfg["inputs"] if i["id"] == "tem_qc_windows"))
    return read_csv(path)


if __name__ == "__main__":
    main()
