"""Directo MT 1D isotropo para P2-T.

Implementa la impedancia de superficie de un medio estratificado horizontal
mediante dos formulaciones independientes:

1. recursion de impedancia capa a capa (impedancia caracteristica Q_j);
2. propagacion de matrices [E, H] desde el semiespacio inferior.

Convencion temporal exp(+i*omega*t). La impedancia de un semiespacio es
Z = sqrt(i*omega*mu0*rho), con fase +45 grados y rho_a = rho.

El modulo no lee datos. Las pruebas analiticas y de convergencia se ejecutan
con ``python mt1d.py`` y se exportan desde p2t.py a
``diagnostico_tem/pruebas_directo.csv``.

Limitaciones declaradas:
- solo 1D isotropo y horizontal;
- la ultima capa es un semiespacio;
- no se modelan distortion galvanica, anisotropia, topografia ni 3D;
- las igualdades Zxx=Zyy=0, Zxy=-Zyx y T=0 son supuestos 1D, no informacion
  tensorial resuelta por TEM.
"""
from __future__ import annotations

import json
import math
from typing import Iterable, Sequence

import numpy as np

MU0 = 4.0e-7 * math.pi
VERSION = "MT1D-1.0.0"


def _as_model(rho: Sequence[float], interfaces_m: Sequence[float]):
    rho = np.asarray(rho, dtype=float)
    interfaces = np.asarray(interfaces_m, dtype=float)
    if rho.ndim != 1 or rho.size == 0:
        raise ValueError("rho debe ser un vector 1D no vacio")
    if interfaces.size != rho.size - 1:
        raise ValueError(
            "interfaces_m debe tener len(rho)-1 elementos: "
            f"{interfaces.size} != {rho.size - 1}"
        )
    if not np.all(np.isfinite(rho)) or np.any(rho <= 0):
        raise ValueError("rho debe ser finito y positivo")
    if interfaces.size:
        if not np.all(np.isfinite(interfaces)):
            raise ValueError("interfaces_m debe ser finito")
        if np.any(interfaces <= 0) or np.any(np.diff(interfaces) <= 0):
            raise ValueError("interfaces_m debe ser positivo y creciente")
    return rho, interfaces


def _thickness(interfaces: np.ndarray) -> np.ndarray:
    return np.diff(np.r_[0.0, interfaces])


def _safe_kh(kh: np.ndarray) -> np.ndarray:
    """Recorta la parte real de k*h cuando tanh ya saturo.

    Para Re(k*h) > 50, tanh(k*h) = 1 y cosh/sinh difieren solo en un factor
    comun. Recortar evita desbordamiento sin cambiar Z.
    """
    kh = np.asarray(kh, dtype=complex)
    real = np.clip(kh.real, -50.0, 50.0)
    return real + 1j * kh.imag


def z1d(frequencies_hz: Sequence[float], rho: Sequence[float],
        interfaces_m: Sequence[float]) -> np.ndarray:
    """Impedancia MT por recursion de impedancia (ohm)."""
    rho, interfaces = _as_model(rho, interfaces_m)
    f = np.asarray(frequencies_hz, dtype=float)
    if f.ndim != 1 or np.any(f <= 0) or not np.all(np.isfinite(f)):
        raise ValueError("frecuencias deben ser finitas y positivas")
    omega = 2.0 * math.pi * f
    h = _thickness(interfaces)

    k = np.sqrt(1j * omega[:, None] * MU0 / rho[None, :])
    q = 1j * omega[:, None] * MU0 / k  # = sqrt(i*omega*mu0*rho)
    z = q[:, -1].copy()
    for j in range(rho.size - 2, -1, -1):
        th = np.tanh(_safe_kh(k[:, j] * h[j]))
        z = q[:, j] * (z + q[:, j] * th) / (q[:, j] + z * th)
    return z


def z1d_matrix(frequencies_hz: Sequence[float], rho: Sequence[float],
               interfaces_m: Sequence[float]) -> np.ndarray:
    """Impedancia MT por propagacion de matrices [E,H] (ohm).

    Formulacion independiente de la recursion de impedancia. Se normaliza el
    vector de estado en cada capa para evitar desbordamiento numerico; el
    cociente E/H no cambia.
    """
    rho, interfaces = _as_model(rho, interfaces_m)
    f = np.asarray(frequencies_hz, dtype=float)
    if f.ndim != 1 or np.any(f <= 0) or not np.all(np.isfinite(f)):
        raise ValueError("frecuencias deben ser finitas y positivas")
    omega = 2.0 * math.pi * f
    h = _thickness(interfaces)

    k = np.sqrt(1j * omega[:, None] * MU0 / rho[None, :])
    q = 1j * omega[:, None] * MU0 / k

    # Semiespacio inferior: E=1, H=1/Q. La normalizacion posterior no altera Z.
    e = np.ones_like(omega, dtype=complex)
    hfield = 1.0 / q[:, -1]
    for j in range(rho.size - 2, -1, -1):
        kh = _safe_kh(k[:, j] * h[j])
        c = np.cosh(kh)
        s = np.sinh(kh)
        e_new = c * e + q[:, j] * s * hfield
        h_new = (s / q[:, j]) * e + c * hfield
        scale = np.maximum(np.abs(e_new), np.abs(h_new))
        scale[scale == 0.0] = 1.0
        e = e_new / scale
        hfield = h_new / scale
    return e / hfield


def rhoa_phase(z: Sequence[complex], frequencies_hz: Sequence[float]):
    """Resistividad aparente (ohm*m) y fase (grados) de Z."""
    z = np.asarray(z, dtype=complex)
    f = np.asarray(frequencies_hz, dtype=float)
    if z.shape != f.shape:
        raise ValueError("z y frecuencias deben tener la misma forma")
    rhoa = np.abs(z) ** 2 / (MU0 * 2.0 * math.pi * f)
    phase = np.degrees(np.angle(z))
    return rhoa, phase


def halfspace_z(frequencies_hz: Sequence[float], rho: float) -> np.ndarray:
    f = np.asarray(frequencies_hz, dtype=float)
    return np.sqrt(1j * 2.0 * math.pi * f * MU0 * float(rho))


def subdivide(rho: Sequence[float], interfaces_m: Sequence[float],
              factor: int):
    """Subdivide cada capa finita en ``factor`` subcapas de igual espesor."""
    rho, interfaces = _as_model(rho, interfaces_m)
    if int(factor) < 1:
        raise ValueError("factor debe ser >= 1")
    factor = int(factor)
    tops = np.r_[0.0, interfaces]
    new_rho = []
    new_interfaces = []
    for j in range(rho.size - 1):
        new_rho.append(np.full(factor, rho[j]))
        if j > 0:
            new_interfaces.append(tops[j])
        if factor > 1:
            bounds = np.linspace(tops[j], tops[j + 1], factor + 1)[1:-1]
            new_interfaces.extend(bounds.tolist())
    new_rho.append(np.array([rho[-1]]))
    if interfaces.size:
        new_interfaces.append(tops[-1])
    return np.concatenate(new_rho), np.asarray(new_interfaces, dtype=float)


def self_test(models: Iterable[tuple[str, Sequence[float], Sequence[float]]] | None = None
              ) -> dict:
    """Pruebas analiticas, de formulacion y de convergencia del directo."""
    freqs = np.geomspace(1.0, 1.0e4, 24)
    checks: list[dict] = []

    def add(name, value, limit, unit, passed, detail=""):
        checks.append(dict(prueba=name, valor=float(value), limite=float(limit),
                           unidad=unit, pasa=bool(passed), detalle=detail))

    # 1. Semiespacio analitico: rho_a = rho y fase = 45 grados.
    rho_max_rel = 0.0
    phase_max_abs = 0.0
    for rho in (1.0, 10.0, 100.0, 1000.0):
        z = z1d(freqs, [rho], [])
        rhoa, phase = rhoa_phase(z, freqs)
        rho_max_rel = max(rho_max_rel, float(np.max(np.abs(rhoa / rho - 1.0))))
        phase_max_abs = max(phase_max_abs, float(np.max(np.abs(phase - 45.0))))
        z_ref = halfspace_z(freqs, rho)
        z_rel = float(np.max(np.abs(z / z_ref - 1.0)))
        add(f"semiespacio_rho_{rho:g}_Z", z_rel, 1e-10, "rel", z_rel <= 1e-10,
            "Z vs sqrt(i*omega*mu0*rho)")
    add("semiespacio_rhoa", rho_max_rel, 1e-10, "rel", rho_max_rel <= 1e-10,
        "rho_a/rho - 1 en 4 resistividades")
    add("semiespacio_fase", phase_max_abs, 1e-8, "deg", phase_max_abs <= 1e-8,
        "|fase - 45| en 4 resistividades")

    # 2. Formulacion matricial vs recursion, en modelos estratificados.
    if models is None:
        models = [
            ("dos_capas", [50.0, 200.0], [100.0]),
            ("tres_capas", [30.0, 5.0, 300.0], [40.0, 250.0]),
            ("cuatro_capas", [100.0, 20.0, 500.0, 50.0], [20.0, 100.0, 400.0]),
        ]
    mat_rel = 0.0
    mat_phase = 0.0
    for name, rho, interfaces in models:
        z_rec = z1d(freqs, rho, interfaces)
        z_mat = z1d_matrix(freqs, rho, interfaces)
        mat_rel = max(mat_rel, float(np.max(np.abs(z_mat / z_rec - 1.0))))
        mat_phase = max(mat_phase, float(np.max(np.abs(
            np.degrees(np.angle(z_mat / z_rec))))))
    add("matriz_vs_recursion_Z", mat_rel, 1e-8, "rel", mat_rel <= 1e-8,
        "propagacion [E,H] vs recursion de impedancia")
    add("matriz_vs_recursion_fase", mat_phase, 1e-6, "deg", mat_phase <= 1e-6,
        "diferencia de fase entre formulaciones")

    # 3. Limites analiticos de una capa: espesor nulo y espesor muy grande.
    z_thin = z1d(freqs, [1000.0, 10.0], [1e-6])
    z_half2 = z1d(freqs, [10.0], [])
    thin_rel = float(np.max(np.abs(z_thin / z_half2 - 1.0)))
    add("limite_capa_espesor_nulo", thin_rel, 1e-5, "rel", thin_rel <= 1e-5,
        "h1 -> 0 debe recuperar el semiespacio inferior")
    z_thick = z1d(freqs, [10.0, 1000.0], [1e7])
    z_half1 = z1d(freqs, [10.0], [])
    thick_rel = float(np.max(np.abs(z_thick / z_half1 - 1.0)))
    add("limite_capa_espesor_grande", thick_rel, 1e-5, "rel", thick_rel <= 1e-5,
        "h1 -> infinito debe recuperar el semiespacio superior")

    # 4. Convergencia por subdivision de capas (el directo es exacto para
    # capas uniformes; la subdivision solo debe cambiar el redondeo).
    if models:
        name, rho, interfaces = models[-1]
        z_ref = z1d(freqs, rho, interfaces)
        conv = 0.0
        for factor in (2, 4, 8):
            rho_s, int_s = subdivide(rho, interfaces, factor)
            z_s = z1d(freqs, rho_s, int_s)
            conv = max(conv, float(np.max(np.abs(z_s / z_ref - 1.0))))
        add("convergencia_subdivision", conv, 1e-6, "rel", conv <= 1e-6,
            "factores 2, 4 y 8 sobre el modelo de cuatro capas")

    # 5. Monotonia cualitativa de la fase en un medio conductivo estratificado:
    # no se usa como prueba de correccion, solo como guarda de rango.
    phase_range_ok = True
    for name, rho, interfaces in (models or []):
        _, phase = rhoa_phase(z1d(freqs, rho, interfaces), freqs)
        phase_range_ok = phase_range_ok and bool(np.all((phase > 0.0) & (phase < 90.0)))
    add("fase_en_rango_1D", 0.0 if phase_range_ok else 1.0, 0.0, "bool",
        phase_range_ok, "0 < fase < 90 grados en todos los modelos")

    passed = all(c["pasa"] for c in checks)
    max_z = max([c["valor"] for c in checks if c["unidad"] == "rel"] or [0.0])
    return dict(
        version=VERSION,
        convencion="exp(+i*omega*t); Z = sqrt(i*omega*mu0*rho) en semiespacio",
        frecuencias_prueba_hz=[float(freqs[0]), float(freqs[-1]), int(freqs.size)],
        meta_p2_Z_rel=0.01,
        meta_p2_fase_deg=0.5,
        max_error_rel=float(max_z),
        cumple_meta_p2=bool(max_z <= 0.01),
        pruebas=checks,
        pasa=passed,
    )


if __name__ == "__main__":
    print(json.dumps(self_test(), ensure_ascii=False, indent=1))
