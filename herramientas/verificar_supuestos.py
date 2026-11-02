"""Comprobaciones acotadas y de solo lectura de funciones de los proyectos fuente.

No importa sus módulos completos ni ejecuta los pipelines. Salida: JSON en stdout.
Las pruebas H10/H11/H19/H21 son aisladas; H18/H20 son lectura de código con hash.
"""
import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

ROOT = Path(r"D:\ARRT_software")
BSS = ROOT / "Preproces_Time_series_M_boundedInfluence_preprocess_teoria_sperical_datawindos_FFT_cwt_escalas_densas_optimized"
SIM = ROOT / "ARMT_validacion" / "simulacion_armt5_multibanda.py"
COMB = ROOT / "ARMT_processing" / "armt" / "comb_spectral.py"
CPP = BSS / "cpp" / "src" / "estimator" / "FDICAReconstructor.cpp"
G13 = ROOT / "Denoise_MT" / "CBAM_AMT_Denoising" / "identification" / "g13.py"
G16 = ROOT / "Denoise_MT" / "CBAM_AMT_Denoising" / "identification" / "g16.py"


def sha256(path: Path):
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(path, names):
    raw = path.read_bytes()
    tree = ast.parse(raw.decode("utf-8-sig"))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(selected) == len(names), (path, names)
    scope = {"np": np, "Dict": Dict, "Tuple": Tuple, "MU0": 4 * np.pi * 1e-7}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), scope)
    return scope, hashlib.sha256(raw).hexdigest()


def ci_complex(rng, n, power=1.0):
    z = rng.normal(size=n) + 1j * rng.normal(size=n)
    return z * np.sqrt(power / 2.0)


def coherence_single_pair(x, y):
    """Razón por coeficiente: trivialmente 1 fuera del piso numérico."""
    num = np.abs(x * np.conj(y)) ** 2
    den = np.abs(x) ** 2 * np.abs(y) ** 2
    return num / (den + 1e-300)


def coherence_averaged(x, y):
    """Coherencia promediada con K pares; no es la razón por coeficiente."""
    num = np.abs(np.mean(x * np.conj(y))) ** 2
    den = np.mean(np.abs(x) ** 2) * np.mean(np.abs(y) ** 2)
    return float(num / (den + 1e-300))


def monte_carlo_bracket(band_bracket, rng, repetitions=500, k=32, f=10.0, noise_power=0.5):
    """Cobertura empírica del bracket para ruido independiente y coherente."""
    rho_signal = 1.0 / (5.0 * f)  # Z=1 en las unidades del código
    out = {}
    for name in ("independiente", "coherente"):
        cover = []
        widths = []
        psd = []
        g2 = []
        for _ in range(repetitions):
            s = ci_complex(rng, k)
            if name == "independiente":
                e = s + ci_complex(rng, k, noise_power)
                h = s + ci_complex(rng, k, noise_power)
            else:
                u = ci_complex(rng, k)
                e = s + 10.0 * u
                h = s + 2.0 * u
            r = band_bracket(e, h, f)
            cover.append(r["rho_fwd"] <= rho_signal <= r["rho_rev"])
            widths.append(r["rho_rev"] - r["rho_fwd"])
            psd.append(r["rho_psd"])
            g2.append(r["g2"])
        out[name] = {
            "cobertura": float(np.mean(cover)),
            "ancho_mediano": float(np.median(widths)),
            "rho_psd_mediano": float(np.median(psd)),
            "g2_mediano": float(np.median(g2)),
        }
    out["rho_senal_verdadera"] = rho_signal
    out["replicas"] = repetitions
    out["ventanas_por_replica"] = k
    return out


def ca_replica(y_power=1.0, r_power=2.0, n=4096, seed=20261028):
    """Replica la fórmula CA del C++: |mean(Y conj(R))|^2 / (Pyy^2)."""
    rng = np.random.default_rng(seed)
    y = ci_complex(rng, n, y_power)
    r = ci_complex(rng, n, r_power)
    pyy = float(np.mean(np.abs(y) ** 2))
    prr = float(np.mean(np.abs(r) ** 2))
    cross = np.mean(y * np.conj(r))
    ca = float(np.abs(cross) ** 2 / (pyy ** 2 + 1e-12))
    gamma2 = float(np.abs(cross) ** 2 / (pyy * prr + 1e-30))
    # Escalar la referencia duplica su potencia: CA debería cuadruplicarse.
    ca_r2 = float(np.abs(np.mean(y * np.conj(2.0 * r))) ** 2 / (pyy ** 2 + 1e-12))
    # Escalar Y sin renormalizar: CA cae por alpha^2.
    ca_y2 = float(np.abs(np.mean(2.0 * y * np.conj(r))) ** 2 / ((4.0 * pyy) ** 2 + 1e-12))
    return {
        "Pyy": pyy,
        "P_RR": prr,
        "ca_P2": ca,
        "ca_P2_escala_R2": ca_r2,
        "ca_escala_Y2": ca_y2,
        "gamma2_normalizada": gamma2,
        "hallazgo": "CA no es invariante a la potencia de la referencia; solo coincide con gamma^2 si P_RR=1. Verificar la normalización del llamador antes de atribuir la selección 2+2 a la física.",
    }


def window_resolution():
    casos = [
        ("D0", 4000, 256),
        ("D1", 32000, 256),
        ("D0_dec_x2", 2000, 256),
        ("D0_dec_x4", 1000, 256),
        ("D1_L4096", 32000, 4096),
        ("D1_L8192", 32000, 8192),
    ]
    out = {}
    for name, fs, length in casos:
        out[name] = {
            "fs_eff": fs,
            "L": length,
            "duracion_s": length / fs,
            "delta_f_hz": fs / length,
            "f_min_8_hz": 8.0 * fs / length,
            "f_min_16_hz": 16.0 * fs / length,
            "ciclos_50_hz": (length / fs) * 50.0,
        }
    return out


def main():
    sources = {}
    sim, sources[str(SIM)] = extract(SIM, {"forward_mt_wait_1d"})
    f = np.geomspace(1, 1e6, 100)
    z = sim["forward_mt_wait_1d"](f, [100.0], [])
    expected = np.sqrt(1j * 2 * np.pi * f * 4 * np.pi * 1e-7 * 100)
    halfspace_error = float(np.max(np.abs(z - expected) / np.abs(expected)))

    bss, sources[str(BSS / "fdica_no_rr.py")] = extract(BSS / "fdica_no_rr.py", {"physical_polarization_score"})
    rng = np.random.default_rng(20261028)
    y = rng.normal(size=(4, 1024)) + 1j * rng.normal(size=(4, 1024))
    scores = bss["physical_polarization_score"](y)

    comb, sources[str(COMB)] = extract(COMB, {"bode_check", "band_bracket"})

    exponent = 0.75
    zp = (1j * 2 * np.pi * f) ** exponent
    rhop = np.abs(zp) ** 2 / (2 * np.pi * f * 4 * np.pi * 1e-7)
    s_val, prediction, _ = comb["bode_check"](f, rhop, np.rad2deg(np.angle(zp)))

    # Prueba original: E=10u, H=2u con el mismo u. La señal de referencia es u.
    u = ci_complex(rng, 2048)
    bracket = comb["band_bracket"](10.0 * u, 2.0 * u, 10.0)

    # Monte Carlo: cobertura del bracket bajo ruido independiente y coherente.
    mc = monte_carlo_bracket(comb["band_bracket"], rng)

    # H19: razón por coeficiente vs coherencia promediada.
    x19 = ci_complex(rng, 2048)
    y19 = ci_complex(rng, 2048)
    ratio = coherence_single_pair(x19, y19)
    coh_avg = {}
    for k in (8, 16, 64):
        vals = []
        for _ in range(2000):
            xk = ci_complex(rng, k)
            yk = ci_complex(rng, k)
            vals.append(coherence_averaged(xk, yk))
        coh_avg[str(k)] = float(np.mean(vals))

    # H21: réplica de la CA del C++.
    ca = ca_replica()

    results = {
        "version": "1.3",
        "fecha_revision": "2026-10-28",
        "alcance": "Pruebas aisladas y lectura de código; no certifican los pipelines ni modifican fuentes.",
        "sha256_fuentes": sources,
        "tipo_evidencia": {
            "H07": "prueba_aislada",
            "H10": "prueba_aislada_mas_monte_carlo",
            "H11": "prueba_aislada",
            "H18": "lectura_de_codigo",
            "H19": "prueba_aislada",
            "H20": "lectura_de_codigo",
            "H21": "formula_replicada",
        },
        "sha256_codigo_no_ejecutado": {
            str(CPP): sha256(CPP),
            str(G13): sha256(G13),
            str(G16): sha256(G16),
        },
        "semiespacio_100_ohm_m": {
            "error_relativo_maximo": halfspace_error,
        },
        "score_polarizacion_python": {
            "scores_4_componentes_independientes": scores.tolist(),
            "hallazgo": "Incluye autocorrelacion: los cuatro scores son aproximadamente 1. No discrimina estas componentes. No se atribuye este resultado al motor C++.",
        },
        "bode_ley_potencia": {
            "exponente_Z": exponent,
            "pendiente_logrho_logf": float(np.median(s_val)),
            "fase_correcta_frecuencia_grados": 45.0 * (1.0 + 0.5),
            "fase_correcta_periodo_grados": 45.0 * (1.0 - (-0.5)),
            "fase_predicha_codigo_mediana_grados": float(np.median(prediction)),
            "error_grados": float(np.median(prediction) - 67.5),
            "hallazgo": "El codigo usa 45(1-s) con s en frecuencia; la forma correcta es 45(1+s)=67.5 grados (o 45(1-s_T) en periodo). Es una prueba 1D, no una identidad 2D/3D.",
        },
        "bracket_ruido_coherente": {
            "rho_senal_verdadera": 1.0 / (5.0 * 10.0),
            "rho_campo_total": float(bracket["rho_psd"]),
            "salida_codigo": bracket,
            "hallazgo": "Con E=10u y H=2u el codigo devuelve [0.5, 0.5] porque rho_psd es la razon de autopotencias del campo total; la rho de la senal (0.02) no es identificable con una sola realizacion. El ancho es monotono en (1-gamma^2) y se anula en gamma^2=1.",
        },
        "bracket_monte_carlo": mc,
        "h19_ratio_por_coeficiente": {
            "ratio_mediana": float(np.median(ratio)),
            "ratio_min": float(np.min(ratio)),
            "ratio_max": float(np.max(ratio)),
            "coherencia_promediada_K": coh_avg,
            "hallazgo": "La razon por coeficiente es 1 si ambos son no nulos; no es una coherencia. La coherencia promediada de pares independientes tiende a 1/K.",
        },
        "h21_ca_normalizacion": ca,
        "resolucion_ventana": window_resolution(),
        "duracion_256_muestras_segundos": {str(fs): 256 / fs for fs in [150, 4000, 32000, 400000, 4000000]},
    }
    text = json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False)
    if "--out" in sys.argv:
        target = Path(sys.argv[sys.argv.index("--out") + 1])
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            handle.write(text.replace("\n", "\r\n"))
        print(f"Escrito {target}")
    else:
        print(text)


if __name__ == "__main__":
    main()
