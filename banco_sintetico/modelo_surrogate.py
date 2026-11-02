"""Modelo directo declarado del banco sintetico y logica de soporte.

El modelo es un *surrogate* de contrato: no resuelve Maxwell ni representa el
subsuelo del sitio. Su unica funcion es producir una tabla de gates con una
sensibilidad conocida a parametros de capa, para ejercitar el contrato de
``FrequencySupport`` y la rama de abstencion.
"""

import math

import numpy as np

from comun import sha256_file


STATUSES = ("respaldada", "condicional", "no_respaldada", "no_evaluada")
APPLICATIONS = ("habilitada", "condicional", "no_habilitada")


def gate_times_ms(model):
    gates = model["gates"]
    return np.logspace(
        math.log10(float(gates["start_ms"])),
        math.log10(float(gates["stop_ms"])),
        int(gates["count"]),
    )


def _amplitude(t_ms, anchors):
    t = np.asarray(t_ms, dtype=float)
    xs = np.log10([float(item[0]) for item in anchors])
    ys = np.log10([float(item[1]) for item in anchors])
    return 10.0 ** np.interp(np.log10(t), xs, ys)


def _reference_rhos(model):
    return {layer["id"]: float(layer["rho_ohm_m"]) for layer in model["layers"]}


def forward(t_ms, model, rhos, kernels=None, anchors=None):
    """Voltaje sintetico en nV/A.

    ``kernels=[]`` produce una respuesta independiente de las capas; se usa en
    S0 para que la sensibilidad sea exactamente nula.
    """
    t = np.asarray(t_ms, dtype=float)
    if kernels is None:
        kernels = model["surrogate"]["kernels"]
    if anchors is None:
        anchors = model["surrogate"]["amplitude_anchors_ms_nv_per_a"]
    reference = _reference_rhos(model)
    log_voltage = np.log10(_amplitude(t, anchors))
    for kernel in kernels:
        layer = kernel["layer"]
        weight = float(kernel["amplitude"]) * np.exp(
            -((np.log10(t / float(kernel["center_ms"])) / float(kernel["width_dex"])) ** 2)
        )
        log_voltage = log_voltage + weight * np.log10(
            float(rhos[layer]) / reference[layer]
        )
    return 10.0 ** log_voltage


def apparent_resistivity(t_ms, model):
    """Resistividad aparente suave solo para la columna de presentacion."""
    t = np.asarray(t_ms, dtype=float)
    layers = model["layers"]
    log_rho = [math.log10(float(layer["rho_ohm_m"])) for layer in layers]
    transitions = model["surrogate"].get(
        "apparent_resistivity_transitions_ms", [0.25, 4.0]
    )
    width = float(model["surrogate"].get("apparent_resistivity_width_dex", 0.25))
    s12 = 1.0 / (1.0 + 10.0 ** (-(np.log10(t / float(transitions[0])) / width)))
    s23 = 1.0 / (1.0 + 10.0 ** (-(np.log10(t / float(transitions[1])) / width)))
    log_value = log_rho[0] + (log_rho[1] - log_rho[0]) * s12
    log_value = log_value + (log_rho[2] - log_rho[1]) * s23
    return 10.0 ** log_value


def sensitivity(t_ms, model, rhos, kernels=None, anchors=None, delta=0.10):
    """Sensibilidad logaritmica por capa: d log10(V) / d log10(rho)."""
    t = np.asarray(t_ms, dtype=float)
    base = {key: float(value) for key, value in rhos.items()}
    denominator = math.log10(1.0 + delta) - math.log10(1.0 - delta)
    result = {}
    for layer, value in base.items():
        plus = dict(base)
        minus = dict(base)
        plus[layer] = value * (1.0 + delta)
        minus[layer] = value * (1.0 - delta)
        v_plus = forward(t, model, plus, kernels, anchors)
        v_minus = forward(t, model, minus, kernels, anchors)
        result[layer] = np.abs(
            (np.log10(v_plus) - np.log10(v_minus)) / denominator
        )
    return result


def frequency_grid(model):
    bands = model["bands_hz"]
    d0 = np.geomspace(float(bands["D0"][0]), float(bands["D0"][1]), 33)
    d1 = np.geomspace(float(bands["D1"][0]), float(bands["D1"][1]), 33)[1:]
    records = [(float(f), "D0") for f in d0]
    records.extend((float(f), "D1") for f in d1)
    return records


def guard_mask(t_ms, model):
    t = np.asarray(t_ms, dtype=float)
    if t.size == 0:
        return np.zeros(0, dtype=bool)
    support = model["support"]
    early = float(support["guard_early_ms"])
    late = (1.0 - float(support["guard_late_fraction"])) * float(t.max())
    return (t >= early) & (t <= late)


def classify_frequency(f_hz, band, t_ms, sensitivities, model):
    support = model["support"]
    t_eq = 1000.0 / (2.0 * math.pi * float(f_hz))
    low = t_eq / (10.0 ** float(support["window_dex"]))
    high = t_eq * (10.0 ** float(support["window_dex"]))
    mask = (t_ms >= low) & (t_ms <= high) & guard_mask(t_ms, model)
    n_gates = int(mask.sum())

    sensitivity_max = 0.0
    if n_gates:
        sensitivity_max = max(
            float(np.median(values[mask])) for values in sensitivities.values()
        )

    if n_gates == 0:
        status = "no_evaluada"
        reason = "sin gates en la ventana de difusion"
    elif (
        sensitivity_max >= float(support["threshold_supported"])
        and n_gates >= int(support["min_gates"])
    ):
        status = "respaldada"
        reason = "sensibilidad suficiente y gates suficientes"
    elif sensitivity_max >= float(support["threshold_conditional"]):
        status = "condicional"
        reason = "sensibilidad baja o menos gates de los requeridos"
    else:
        status = "no_respaldada"
        reason = "sensibilidad insuficiente"

    dead_low, dead_high = [float(value) for value in model["amt_dead_band_hz"]]
    observation = "penalizada" if dead_low <= f_hz <= dead_high else "favorable"

    if status == "respaldada" and observation == "favorable":
        application = "habilitada"
    elif status == "respaldada" and observation == "penalizada":
        application = "condicional"
        reason = reason + "; banda muerta AMT 1-5 kHz"
    elif status == "condicional":
        application = "condicional"
    else:
        application = "no_habilitada"

    return {
        "f_hz": round(float(f_hz), 6),
        "band": band,
        "t_eq_ms": round(float(t_eq), 6),
        "n_gates": n_gates,
        "sensitivity_max": round(float(sensitivity_max), 6),
        "status": status,
        "observacion_amt": observation,
        "aplicacion": application,
        "reason": reason,
    }


def _ranges(records, key, value):
    result = []
    current = None
    previous = None
    for record in sorted(records, key=lambda item: item["f_hz"]):
        if record[key] == value:
            if current is None:
                current = [record["f_hz"], record["f_hz"]]
            elif previous is not None and record["f_hz"] / previous > 1.20:
                result.append(current)
                current = [record["f_hz"], record["f_hz"]]
            else:
                current[1] = record["f_hz"]
            previous = record["f_hz"]
        else:
            if current is not None:
                result.append(current)
                current = None
            previous = None
    if current is not None:
        result.append(current)
    return [[round(float(a), 6), round(float(b), 6)] for a, b in result]


def _range_summary(records):
    return {
        "supported_ranges_hz": _ranges(records, "status", "respaldada"),
        "application_ranges_hz": _ranges(records, "aplicacion", "habilitada"),
        "conditional_ranges_hz": _ranges(records, "aplicacion", "condicional"),
        "unsupported_ranges_hz": _ranges(records, "status", "no_respaldada"),
        "not_evaluated_ranges_hz": _ranges(records, "status", "no_evaluada"),
    }


def summarize(records, model):
    counts = {name: 0 for name in STATUSES}
    application_counts = {name: 0 for name in APPLICATIONS}
    for record in records:
        counts[record["status"]] += 1
        application_counts[record["aplicacion"]] += 1

    supported_any = counts["respaldada"] > 0
    admissible_any = application_counts["habilitada"] > 0
    conditional_any = application_counts["condicional"] > 0

    summary = {
        "counts": counts,
        "application_counts": application_counts,
        "supported_any": supported_any,
        "admissible_any": admissible_any,
        "conditional_any": conditional_any,
        "empty_intersection": not (admissible_any or conditional_any),
        "g0_trigger": not admissible_any,
    }
    summary.update(_range_summary(records))

    bands = {}
    for band in model["bands_hz"]:
        band_records = [record for record in records if record["band"] == band]
        bands[band] = _range_summary(band_records)
        bands[band]["counts"] = {
            name: sum(1 for record in band_records if record["status"] == name)
            for name in STATUSES
        }
        bands[band]["application_counts"] = {
            name: sum(1 for record in band_records if record["aplicacion"] == name)
            for name in APPLICATIONS
        }
    summary["bands"] = bands
    return summary


def build_support(model, truth, truth_path):
    gates = np.asarray(truth["gates_ms"], dtype=float)
    rhos = {
        layer["id"]: float(layer["rho_ohm_m"]) for layer in truth["layers"]
    }
    kernels = truth["kernels"]
    anchors = truth["amplitude_anchors_ms_nv_per_a"]
    sensitivities = sensitivity(gates, model, rhos, kernels, anchors)

    records = []
    for f_hz, band in frequency_grid(model):
        records.append(classify_frequency(f_hz, band, gates, sensitivities, model))

    return {
        "support_version": "SYN-FS-1.0.0",
        "sounding_id": truth["tem_id"],
        "scenario": truth["scenario"],
        "target_record": truth["target_record"],
        "synthetic": True,
        "scientific_claim": False,
        "model_version": model["version"],
        "model_sha256": truth["model_sha256"],
        "truth_sha256": sha256_file(truth_path),
        "mapping": model["support"]["mapping"],
        "guard": {
            "early_ms": float(model["support"]["guard_early_ms"]),
            "late_fraction": float(model["support"]["guard_late_fraction"]),
            "late_ms": round(
                (1.0 - float(model["support"]["guard_late_fraction"]))
                * float(gates.max()),
                6,
            ),
        },
        "bands_hz": model["bands_hz"],
        "frequencies": records,
        "summary": summarize(records, model),
        "note": (
            "Soporte calculado por sensibilidad de un surrogate de contrato. "
            "No es P2-T, no es evidencia TEM del sitio y no habilita etiquetas "
            "de entrenamiento."
        ),
    }
