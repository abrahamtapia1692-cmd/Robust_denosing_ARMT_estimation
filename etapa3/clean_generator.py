#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generador de series limpias con física controlada y verdad analítica (Puerta P3).

Implementa la síntesis rigurosa de subbanda para los campos electromagnéticos
MT/AMT según los requisitos de la Etapa 3 del Plan de Implementación v1.3:

1. Excitación magnética de dos grados de libertad con polarización y
   no estacionariedad controladas (evitando colinealidad de rango 1).
2. Conexión electromagnética exacta E_h(f) = Z(f) H_h(f) y Hz(f) = T(f) H_h(f)
   con causalidad, simetría hermítica y relación dispersiva rigurosa.
3. Operador de subbanda común W_b(f) aplicado consistentemente a todos los
   canales, garantizando E_b = W_b E = Z W_b H = Z H_b.
4. Convolución circular protegida mediante guardas temporales extendidas
   (edge buffers) para eliminar efectos de borde y discontinuidades.
5. Cadena instrumental desacoplada: campo ideal, ruido instrumental,
   cuantización ADC y máscaras de saturación/clipping.
6. Comprobación algebraica de residuo relativo ||E - Z H|| / ||E|| < 1e-8.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from etapa2.mt1d import z1d, z1d_matrix

MU0 = 4.0e-7 * math.pi
VERSION = "P3-GEN-1.0.0"
CHANNELS = ("Ex", "Ey", "Hx", "Hy", "Hz")


def make_rotation_matrix_2d(strike_angle_deg: float) -> np.ndarray:
    """Matriz de rotación 2D para tensor Z y vector tipper T."""
    theta = math.radians(strike_angle_deg)
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, s], [-s, c]], dtype=float)


def build_impedance_tensor_1d(
    frequencies_hz: np.ndarray,
    rho_ohm_m: Sequence[float],
    interfaces_m: Sequence[float],
    strike_angle_deg: float = 0.0,
) -> np.ndarray:
    """Construye el tensor Z(f) (2x2) para cada frecuencia a partir de un modelo 1D.

    En 1D isotrópico sin rotación:
        Zxx = Zyy = 0, Zxy = Z_1D, Zyx = -Z_1D.
    Con rotación por ángulo de rumbo theta:
        Z_rot = R(theta) @ Z_1D @ R(theta)^T.
    """
    f = np.asarray(frequencies_hz, dtype=float)
    n_f = len(f)
    z_tensor = np.zeros((n_f, 2, 2), dtype=complex)

    # Evitar evaluar f=0 (DC) en mt1d
    pos_mask = f > 0
    if np.any(pos_mask):
        z_scalar = z1d(f[pos_mask], rho_ohm_m, interfaces_m)
        r_mat = make_rotation_matrix_2d(strike_angle_deg)

        for idx, (is_pos, z_val) in enumerate(zip(pos_mask, z_scalar)):
            if is_pos:
                z_local = np.array([[0.0 + 0.0j, z_val], [-z_val, 0.0 + 0.0j]], dtype=complex)
                z_tensor[idx] = r_mat @ z_local @ r_mat.T

    return z_tensor


def build_tipper_vector_1d(
    frequencies_hz: np.ndarray,
    tipper_vector: Sequence[float] = (0.0, 0.0),
    strike_angle_deg: float = 0.0,
) -> np.ndarray:
    """Construye el vector tipper T(f) = [Tx, Ty] (1x2) para cada frecuencia."""
    f = np.asarray(frequencies_hz, dtype=float)
    n_f = len(f)
    t_tensor = np.zeros((n_f, 1, 2), dtype=complex)

    t_base = np.array([[tipper_vector[0], tipper_vector[1]]], dtype=complex)
    r_mat = make_rotation_matrix_2d(strike_angle_deg)
    t_rot = t_base @ r_mat.T

    pos_mask = f > 0
    t_tensor[pos_mask] = t_rot
    return t_tensor


def compute_subband_filter_weights(
    frequencies_hz: np.ndarray,
    f_pass_min: float,
    f_pass_max: float,
    roll_off_frac: float = 0.1,
    allowed_mask: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Calcula la respuesta en frecuencia del filtro de subbanda común W_b(f).

    W_b(f) es un escalar real en [0, 1] que multiplica a todos los canales.
    Tiene fase cero y transición coseno alzado (Tukey) en los bordes.
    Si se suministra allowed_mask, se anula rigurosamente fuera del soporte.
    """
    f = np.asarray(frequencies_hz, dtype=float)
    w_b = np.zeros_like(f, dtype=float)

    # Identificar zona de paso y transiciones
    df_pass = f_pass_max - f_pass_min
    delta_lo = roll_off_frac * df_pass
    delta_hi = roll_off_frac * df_pass

    f_lo_start = max(0.0, f_pass_min - delta_lo)
    f_lo_end = f_pass_min
    f_hi_start = f_pass_max
    f_hi_end = f_pass_max + delta_hi

    # Zona central unitaria
    pass_core = (f >= f_lo_end) & (f <= f_hi_start)
    w_b[pass_core] = 1.0

    # Rampa de subida
    ramp_up = (f >= f_lo_start) & (f < f_lo_end)
    if np.any(ramp_up) and delta_lo > 0:
        xi = (f[ramp_up] - f_lo_start) / delta_lo
        w_b[ramp_up] = 0.5 - 0.5 * np.cos(math.pi * xi)

    # Rampa de bajada
    ramp_down = (f > f_hi_start) & (f <= f_hi_end)
    if np.any(ramp_down) and delta_hi > 0:
        xi = (f[ramp_down] - f_hi_start) / delta_hi
        w_b[ramp_down] = 0.5 + 0.5 * np.cos(math.pi * xi)

    # Forzar DC a cero exactamente
    w_b[f <= 0] = 0.0

    # Si hay máscara de soporte aprobada por P2-T, enmascarar
    if allowed_mask is not None:
        if len(allowed_mask) != len(f):
            raise ValueError("allowed_mask debe tener la misma longitud que frequencies_hz")
        w_b = w_b * np.asarray(allowed_mask, dtype=float)

    return w_b


def generate_magnetic_sources(
    n_samples_total: int,
    fs: float,
    excitation_mode: str = "two_polarizations",
    seed: int = 20261028,
    amplitude_scale: float = 1.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Genera dos fuentes magnéticas horizontales Hx(t), Hy(t) con control de rango.

    Modos:
    - 'two_polarizations': Dos fuentes estocásticas con rotación lenta de polarización,
      garantizando rango efectivo 2 en SHH.
    - 'single_polarization_rank1': Excitación polarizada colineal (rango 1 para abstención).
    - 'nonstationary_sferics': Variabilidad de energía con ráfagas causales sferic.
    - 'two_polarizations_large_amplitude': Señal de alta amplitud para probar saturación ADC.
    """
    rng = np.random.RandomState(seed)
    dt = 1.0 / float(fs)
    t = np.arange(n_samples_total, dtype=float) * dt

    # Espectro base 1/f^alpha típico del campo natural
    freqs = np.fft.rfftfreq(n_samples_total, d=dt)
    n_freq = len(freqs)

    # Evitar singularidad en DC
    f_eff = np.maximum(freqs, freqs[1] * 0.5)
    spectral_envelope = 1.0 / np.sqrt(f_eff)
    spectral_envelope[0] = 0.0  # DC nulo

    def make_random_series() -> np.ndarray:
        noise_spec = (rng.randn(n_freq) + 1j * rng.randn(n_freq)) * spectral_envelope
        noise_spec[0] = 0.0
        if n_samples_total % 2 == 0:
            noise_spec[-1] = noise_spec[-1].real
        return np.fft.irfft(noise_spec, n=n_samples_total)

    u1 = make_random_series()
    u2 = make_random_series()

    # Normalizar potencia
    u1 = (u1 - np.mean(u1)) / (np.std(u1) + 1e-12)
    u2 = (u2 - np.mean(u2)) / (np.std(u2) + 1e-12)

    if excitation_mode == "single_polarization_rank1":
        # Rango 1 colineal estricto: Hy = 0.75 * Hx, u2 descartado
        hx = u1 * amplitude_scale
        hy = 0.75 * u1 * amplitude_scale
        return hx, hy

    elif excitation_mode == "nonstationary_sferics":
        # Modulación de polarización variable
        drift_rate = 2.0 * math.pi * 0.1  # 0.1 Hz de modulación
        phi = drift_rate * t + 0.5 * np.sin(0.05 * 2.0 * math.pi * t)
        hx = (math.cos(0.3) * u1 * np.cos(phi) - math.sin(0.3) * u2 * np.sin(phi)) * amplitude_scale
        hy = (math.sin(0.3) * u1 * np.sin(phi) + math.cos(0.3) * u2 * np.cos(phi)) * amplitude_scale

        # Inyectar ráfagas transitorias causales (sferics)
        n_sferics = max(3, int(n_samples_total / (fs * 2.0)))
        for _ in range(n_sferics):
            t_idx = rng.randint(int(0.1 * n_samples_total), int(0.9 * n_samples_total))
            t_burst = t[t_idx:] - t[t_idx]
            tau = rng.uniform(0.002, 0.010)  # 2 a 10 ms de duración
            f_burst = rng.uniform(200.0, 800.0)
            amp_burst = rng.uniform(5.0, 15.0) * amplitude_scale
            burst = amp_burst * (t_burst / tau) * np.exp(-t_burst / tau) * np.sin(2.0 * math.pi * f_burst * t_burst)
            # Acoplamiento a ambos canales
            ang = rng.uniform(0, 2.0 * math.pi)
            hx[t_idx:] += burst * math.cos(ang)
            hy[t_idx:] += burst * math.sin(ang)

        return hx, hy

    elif excitation_mode == "two_polarizations_large_amplitude":
        # Multiplicador alto para probar clipping ADC
        hx, hy = generate_magnetic_sources(
            n_samples_total, fs, excitation_mode="two_polarizations", seed=seed, amplitude_scale=50.0
        )
        return hx, hy

    else:
        # Default: 'two_polarizations' estándar
        # Matriz de mezcla variable en el tiempo para garantizar rango 2 en ventanas
        drift_rate = 2.0 * math.pi * 0.05  # Rotación suave a 0.05 Hz
        phi = drift_rate * t
        hx = (u1 * np.cos(phi) - u2 * np.sin(phi)) * amplitude_scale
        hy = (u1 * np.sin(phi) + u2 * np.cos(phi)) * amplitude_scale
        return hx, hy


def apply_physical_transfer_function(
    hx_time: np.ndarray,
    hy_time: np.ndarray,
    fs: float,
    z_tensor_freq: np.ndarray,
    t_tensor_freq: np.ndarray,
    w_subband_freq: np.ndarray,
) -> Dict[str, np.ndarray]:
    """Aplica Z(f) y T(f) con operador de subbanda W_b(f) en el dominio rfft.

    Garantiza causalidad y simetría hermítica:
    E_h(f) = W_b(f) * [Z(f) @ H_h(f)]
    Hz(f)  = W_b(f) * [T(f) @ H_h(f)]
    H_b(f) = W_b(f) * H_h(f)
    """
    n_samples = len(hx_time)
    dt = 1.0 / float(fs)

    hx_fft = np.fft.rfft(hx_time)
    hy_fft = np.fft.rfft(hy_time)
    n_freq = len(hx_fft)

    if len(z_tensor_freq) != n_freq or len(t_tensor_freq) != n_freq or len(w_subband_freq) != n_freq:
        raise ValueError(
            f"Las dimensiones de Z ({len(z_tensor_freq)}), T ({len(t_tensor_freq)}) y W_b ({len(w_subband_freq)}) "
            f"deben coincidir con rfft bins ({n_freq})"
        )

    # Formar vector H_h(f) en cada bin: forma (n_freq, 2)
    h_vec = np.stack([hx_fft, hy_fft], axis=-1)  # (n_freq, 2)

    # E_ideal(f) = Z(f) @ H(f) -> (n_freq, 2)
    # einsum: n=freq, i=salida E (0:Ex, 1:Ey), j=entrada H (0:Hx, 1:Hy)
    e_ideal_fft = np.einsum("nij,nj->ni", z_tensor_freq, h_vec)

    # Hz_ideal(f) = T(f) @ H(f) -> (n_freq, 1) -> (n_freq,)
    hz_ideal_fft = np.einsum("nij,nj->ni", t_tensor_freq, h_vec)[:, 0]

    # Aplicar operador de subbanda común W_b(f) a todos los canales
    w_col = w_subband_freq[:, None]
    e_subband_fft = e_ideal_fft * w_col
    h_subband_fft = h_vec * w_col
    hz_subband_fft = hz_ideal_fft * w_subband_freq

    # Retorno al tiempo vía irfft con longitud exacta
    ex_subband_time = np.fft.irfft(e_subband_fft[:, 0], n=n_samples)
    ey_subband_time = np.fft.irfft(e_subband_fft[:, 1], n=n_samples)
    hx_subband_time = np.fft.irfft(h_subband_fft[:, 0], n=n_samples)
    hy_subband_time = np.fft.irfft(h_subband_fft[:, 1], n=n_samples)
    hz_subband_time = np.fft.irfft(hz_subband_fft, n=n_samples)

    return {
        "Ex_fft": e_subband_fft[:, 0],
        "Ey_fft": e_subband_fft[:, 1],
        "Hx_fft": h_subband_fft[:, 0],
        "Hy_fft": h_subband_fft[:, 1],
        "Hz_fft": hz_subband_fft,
        "Ex": ex_subband_time,
        "Ey": ey_subband_time,
        "Hx": hx_subband_time,
        "Hy": hy_subband_time,
        "Hz": hz_subband_time,
    }


def compute_spectral_closure_residual(
    ex_fft: np.ndarray,
    ey_fft: np.ndarray,
    hx_fft: np.ndarray,
    hy_fft: np.ndarray,
    hz_fft: np.ndarray,
    z_tensor_freq: np.ndarray,
    t_tensor_freq: np.ndarray,
    w_subband_freq: np.ndarray,
    tolerance_threshold: float = 1e-8,
) -> Dict[str, float]:
    """Calcula el residuo relativo ||E - Z H|| / ||E|| en bins con soporte W_b > 0.

    Requisito estricto Puerta P3: residuo relativo espectral < 1e-8.
    """
    valid_bins = np.flatnonzero(w_subband_freq > 1e-6)
    if len(valid_bins) == 0:
        return {"e_rel_residual": 0.0, "hz_rel_residual": 0.0, "n_valid_bins": 0, "pasa_cierre": True}

    h_mat = np.stack([hx_fft[valid_bins], hy_fft[valid_bins]], axis=-1)  # (K, 2)
    e_mat = np.stack([ex_fft[valid_bins], ey_fft[valid_bins]], axis=-1)  # (K, 2)
    hz_vec = hz_fft[valid_bins]  # (K,)

    z_sub = z_tensor_freq[valid_bins]  # (K, 2, 2)
    t_sub = t_tensor_freq[valid_bins]  # (K, 1, 2)

    # Predicción Z @ H y T @ H
    e_pred = np.einsum("kij,kj->ki", z_sub, h_mat)
    hz_pred = np.einsum("kij,kj->ki", t_sub, h_mat)[:, 0]

    # Residuos de Frobenius
    diff_e = e_mat - e_pred
    norm_diff_e = np.linalg.norm(diff_e)
    norm_e = np.linalg.norm(e_mat)

    diff_hz = hz_vec - hz_pred
    norm_diff_hz = np.linalg.norm(diff_hz)
    norm_hz = np.linalg.norm(hz_vec)

    rel_e = float(norm_diff_e / max(norm_e, 1e-30))
    rel_hz = float(norm_diff_hz / max(norm_hz, 1e-30))

    pasa = bool(rel_e < tolerance_threshold and rel_hz < tolerance_threshold)

    return {
        "e_rel_residual": rel_e,
        "hz_rel_residual": rel_hz,
        "n_valid_bins": int(len(valid_bins)),
        "pasa_cierre": pasa,
    }


def apply_instrument_and_adc(
    signals_time: Dict[str, np.ndarray],
    noise_sigma_uv: float = 0.0,
    gain_db: float = 0.0,
    adc_bits: int = 24,
    adc_full_scale_uv: float = 2.5e6,
    simulate_clipping: bool = False,
    clipping_threshold_fraction: float = 0.85,
    seed: int = 20261028,
) -> Dict[str, Any]:
    """Aplica ruido instrumental, ganancia, cuantización ADC y detección de clipping."""
    rng = np.random.RandomState(seed)
    gain_linear = 10.0 ** (gain_db / 20.0)
    lsb_uv = (2.0 * adc_full_scale_uv) / (2.0 ** adc_bits)

    out = {}
    is_clipped_channel = {}
    any_clipped = np.zeros(len(signals_time["Ex"]), dtype=bool)

    clip_level_uv = adc_full_scale_uv * (clipping_threshold_fraction if simulate_clipping else 1.0)

    for ch in CHANNELS:
        s_ideal = signals_time[ch]
        # Ruido sensor gaussiano
        noise = rng.randn(len(s_ideal)) * noise_sigma_uv
        s_inst = s_ideal + noise

        # Ganancia analógica
        s_gained = s_inst * gain_linear

        # Clipping / saturación ADC
        clipped_mask = np.abs(s_gained) >= clip_level_uv
        is_clipped_channel[ch] = clipped_mask
        any_clipped = any_clipped | clipped_mask

        s_clipped = np.clip(s_gained, -adc_full_scale_uv, adc_full_scale_uv)

        # Cuantización ADC
        counts = np.round(s_clipped / lsb_uv)
        s_adc_uv = counts * lsb_uv / gain_linear  # Reconvertido a UV calibrado aparente

        out[f"{ch}_ideal"] = s_ideal
        out[f"{ch}_inst"] = s_inst
        out[f"{ch}_adc_counts"] = counts
        out[f"{ch}_calibrated_uv"] = s_adc_uv

    out["is_clipped"] = any_clipped
    out["is_clipped_by_channel"] = is_clipped_channel
    out["clip_fraction"] = float(np.mean(any_clipped))
    return out


def generate_clean_dataset(
    scenario_cfg: Dict[str, Any],
    bands_cfg: Dict[str, Any],
    guard_time_s: float = 0.5,
    tolerances: Optional[Dict[str, float]] = None,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Función de alto nivel para generar y validar un escenario de síntesis limpia."""
    scenario_id = scenario_cfg["id"]
    band_name = scenario_cfg["band"]
    band_info = bands_cfg[band_name]
    fs = float(band_info["fs"])
    n_samples_target = int(band_info["n_samples"])
    seed = int(scenario_cfg.get("seed", 20261028))

    # Guardas temporales para convolución circular libre de saltos
    n_guard = int(math.ceil(guard_time_s * fs))
    n_samples_total = n_samples_target + 2 * n_guard

    # 1. Grilla de frecuencias rfft para la longitud total
    dt = 1.0 / fs
    freqs_total = np.fft.rfftfreq(n_samples_total, d=dt)

    # 2. Impedancia analítica Z(f) y tipper T(f)
    rho_list = scenario_cfg["rho_ohm_m"]
    interfaces_list = scenario_cfg["interfaces_m"]
    strike_deg = float(scenario_cfg.get("strike_angle_deg", 0.0))
    tipper_vec = scenario_cfg.get("tipper_vector", [0.0, 0.0])

    z_tensor_total = build_impedance_tensor_1d(
        freqs_total, rho_list, interfaces_list, strike_angle_deg=strike_deg
    )
    t_tensor_total = build_tipper_vector_1d(
        freqs_total, tipper_vector=tipper_vec, strike_angle_deg=strike_deg
    )

    # 3. Operador de subbanda W_b(f)
    f_pass_min = float(band_info["f_min"])
    f_pass_max = float(band_info["f_max"])

    allowed_mask = None
    support_source = scenario_cfg.get("support_source", "full_band")
    if support_source != "full_band":
        # Cargar soporte condicionado por TEM (p.ej. de banco_sintetico/soporte_S1.json)
        supp_path = Path(support_source)
        if supp_path.exists():
            with open(supp_path, "r", encoding="utf-8") as f:
                supp_data = json.load(f)
            # Extraer frecuencias habilitadas
            enabled_freqs = [
                float(row["f_hz"])
                for row in supp_data.get("frequencies", [])
                if row.get("band") == band_name and row.get("aplicacion") == "habilitada"
            ]
            if enabled_freqs:
                f_min_supp = min(enabled_freqs)
                f_max_supp = max(enabled_freqs)
                f_pass_min = max(f_pass_min, f_min_supp)
                f_pass_max = min(f_pass_max, f_max_supp)

    w_subband_total = compute_subband_filter_weights(
        freqs_total, f_pass_min, f_pass_max, roll_off_frac=0.08, allowed_mask=allowed_mask
    )

    # 4. Generación de fuentes magnéticas Hx(t), Hy(t)
    excit_mode = scenario_cfg.get("excitation_mode", "two_polarizations")
    hx_raw, hy_raw = generate_magnetic_sources(
        n_samples_total, fs, excitation_mode=excit_mode, seed=seed
    )

    # 5. Aplicación rigurosa de Z(f), T(f) y W_b(f)
    fields_subband = apply_physical_transfer_function(
        hx_raw, hy_raw, fs, z_tensor_total, t_tensor_total, w_subband_total
    )

    # 6. Comprobación algebraica de cierre en bins válidos (Requisito P3)
    tol = tolerances.get("max_relative_spectral_residual", 1e-8) if tolerances else 1e-8
    closure_metrics = compute_spectral_closure_residual(
        fields_subband["Ex_fft"],
        fields_subband["Ey_fft"],
        fields_subband["Hx_fft"],
        fields_subband["Hy_fft"],
        fields_subband["Hz_fft"],
        z_tensor_total,
        t_tensor_total,
        w_subband_total,
        tolerance_threshold=tol,
    )

    # 7. Recorte de guardas temporales para extraer la serie analítica central
    fields_clean = {}
    for ch in CHANNELS:
        fields_clean[ch] = fields_subband[ch][n_guard : n_guard + n_samples_target]

    # 8. Efectos instrumentales
    inst_cfg = scenario_cfg.get("instrument", {})
    inst_out = apply_instrument_and_adc(
        fields_clean,
        noise_sigma_uv=inst_cfg.get("noise_sigma_uv", 0.0),
        gain_db=inst_cfg.get("gain_db", 0.0),
        adc_bits=inst_cfg.get("adc_bits", 24),
        adc_full_scale_uv=inst_cfg.get("adc_full_scale_uv", 2.5e6),
        simulate_clipping=inst_cfg.get("simulate_clipping", False),
        clipping_threshold_fraction=inst_cfg.get("clipping_threshold_fraction", 0.85),
        seed=seed + 100,
    )

    # Preparar resultado
    t_clean = np.arange(n_samples_target, dtype=float) * dt
    dt_freq = np.fft.rfftfreq(n_samples_target, d=dt)

    result = {
        "scenario_id": scenario_id,
        "band": band_name,
        "fs": fs,
        "n_samples": n_samples_target,
        "n_guard": n_guard,
        "time_s": t_clean,
        "freqs_hz": dt_freq,
        "closure_metrics": closure_metrics,
        "fields_clean": fields_clean,
        "instrumental": inst_out,
        "model": {
            "rho_ohm_m": rho_list,
            "interfaces_m": interfaces_list,
            "strike_angle_deg": strike_deg,
            "tipper_vector": tipper_vec,
        },
        "passband_hz": [f_pass_min, f_pass_max],
    }

    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / f"{scenario_id}.npz"

        # Empaquetar matrices para guardado reproducible
        save_dict = {
            "time_s": t_clean,
            "Ex": fields_clean["Ex"],
            "Ey": fields_clean["Ey"],
            "Hx": fields_clean["Hx"],
            "Hy": fields_clean["Hy"],
            "Hz": fields_clean["Hz"],
            "Ex_calibrated_uv": inst_out["Ex_calibrated_uv"],
            "Ey_calibrated_uv": inst_out["Ey_calibrated_uv"],
            "Hx_calibrated_uv": inst_out["Hx_calibrated_uv"],
            "Hy_calibrated_uv": inst_out["Hy_calibrated_uv"],
            "Hz_calibrated_uv": inst_out["Hz_calibrated_uv"],
            "is_clipped": inst_out["is_clipped"],
        }
        np.savez_compressed(out_file, **save_dict)

    return result
