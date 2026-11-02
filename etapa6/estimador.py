#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Estimador de referencia MT/AMT de la Etapa 6 (rama AMT sin TEM).

Implementa una cadena transparente y reproducible:

1. ventanas de ``L`` muestras con solape, detrend lineal y taper Hann;
2. espectros por ventana y promedio de productos cruzados en una banda
   estrecha alrededor de cada frecuencia objetivo;
3. regresion compleja ``Z = S_EH S_HH^-1`` resuelta por descomposicion
   hermitica, con numero de condicion y rango efectivo;
4. reponderacion robusta tipo Huber sobre el misfit relativo por ventana;
5. bootstrap por bloques temporales para la covarianza de Z;
6. compuerta de coherencia: si la coherencia Ex-Hy cae bajo el valor
   critico de ruido para ``k_eff`` ventanas, la frecuencia se marca
   ``senal_insuficiente`` y no se publica Z.

No lee TEM, no sintetiza para entrenamiento, no etiqueta y no entrena. La
respuesta de campo se obtiene sin calibracion aplicada: es una respuesta
relativa, no una resistividad aparente fisica.
"""
from __future__ import annotations

import math

import numpy as np

MU0 = 4.0e-7 * math.pi
VERSION = "P6-EST-1.0.1"
CHANNELS = ("Ex", "Ey", "Hx", "Hy", "Hz")
_EPS = 1e-30


def hann_window(length: int) -> np.ndarray:
    """Ventana Hann periodica, la habitual en analisis espectral por segmentos."""
    n = np.arange(int(length), dtype=float)
    return 0.5 - 0.5 * np.cos(2.0 * math.pi * n / float(length))


def band_bins(frequency_hz, fs, n_samples, half_width_rel, band_range):
    """Bins rfft dentro de la banda relativa, recortados al rango de la subbanda."""
    df = float(fs) / float(n_samples)
    lo = max(float(band_range[0]), float(frequency_hz) * (1.0 - half_width_rel))
    hi = min(float(band_range[1]), float(frequency_hz) * (1.0 + half_width_rel))
    k0 = max(1, int(math.ceil(lo / df - 1e-9)))
    k1 = min(n_samples // 2, int(math.floor(hi / df + 1e-9)))
    if k1 < k0:
        k = int(round(float(frequency_hz) / df))
        k = min(max(k, 1), n_samples // 2)
        k0 = k1 = k
    return np.arange(k0, k1 + 1, dtype=int)


def window_blocks(read, n_samples, n_window, step, chunk_windows):
    """Genera bloques de ventanas alineadas a la grilla ``step``.

    ``read(a, b)`` devuelve muestras ``[a, b)`` con forma ``(m, canales)``.
    El primer indice global de ventana de cada bloque se devuelve junto con el
    arreglo ``(n_ventanas, L, canales)``.
    """
    start = 0
    while start + n_window <= n_samples:
        core = int(chunk_windows) * int(step)
        stop = min(start + core, n_samples)
        block = np.asarray(read(start, stop), dtype=float)
        if block.shape[0] < n_window:
            break
        view = np.lib.stride_tricks.sliding_window_view(block, n_window, axis=0)
        windows = view[::step].transpose(0, 2, 1)
        n_win = windows.shape[0]
        if n_win == 0:
            break
        yield start // step, windows
        start += n_win * step


def window_spectra(windows, taper):
    """Detrend lineal por ventana, aplica taper y devuelve el rfft por canal."""
    x = np.asarray(windows, dtype=float)
    n_win, n_window, n_chan = x.shape
    t = np.arange(n_window, dtype=float) - 0.5 * (n_window - 1)
    t2 = float(np.dot(t, t))
    mean = x.mean(axis=1, keepdims=True)
    slope = np.einsum("wlc,l->wc", x, t)[:, None, :] / t2
    x = x - mean - slope * t[None, :, None]
    x *= taper[None, :, None]
    return np.fft.rfft(x, axis=1)


def cross_products(spectra, bins):
    """Matrices 2x2 por ventana: EE, EH y HH (E/H horizontales)."""
    e = spectra[:, bins, 0:2]
    h = spectra[:, bins, 2:4]
    ee = np.einsum("wbi,wbj->wij", e, e.conj())
    hh = np.einsum("wbi,wbj->wij", h, h.conj())
    eh = np.einsum("wbi,wbj->wij", e, h.conj())
    return ee, eh, hh


def residual_trace(ee, eh, hh, z):
    """Traza de <(E - Z H)(E - Z H)^H> por ventana, a partir de las matrices."""
    z = np.asarray(z, dtype=complex)
    she = np.conj(np.transpose(eh, (0, 2, 1)))
    zshe = np.einsum("ij,wjk->wik", z, she)
    zhhz = np.einsum("ij,wjk,kl->wil", z, hh, z.conj().T)
    term = (zshe[:, 0, 0].real + zshe[:, 1, 1].real)
    quad = (zhhz[:, 0, 0].real + zhhz[:, 1, 1].real)
    energy = ee[:, 0, 0].real + ee[:, 1, 1].real
    return np.maximum(energy - 2.0 * term + quad, 0.0), energy


def huber_weights(ee, eh, hh, z, scale, c):
    """Pesos acotados en [0, 1] sobre el misfit relativo de cada ventana."""
    if z is None or not np.isfinite(scale) or scale <= 0.0:
        return np.ones(ee.shape[0], dtype=float)
    resid, energy = residual_trace(ee, eh, hh, z)
    u = np.sqrt(resid / np.maximum(energy, _EPS))
    return np.minimum(1.0, float(c) * float(scale) / np.maximum(u, 1e-12))


def _hermitian(matrix):
    return 0.5 * (matrix + matrix.conj().T)


def solve_z(s_eh, s_hh, rcond=1e-12):
    """Resuelve Z = S_EH S_HH^-1 con pseudoinversa hermitica."""
    s_hh = _hermitian(np.asarray(s_hh, dtype=complex))
    w, v = np.linalg.eigh(s_hh)
    w_max = float(w[-1]) if w.size else 0.0
    if w_max <= 0.0 or not np.isfinite(w_max):
        return np.full((2, 2), np.nan + 0j), float("inf"), 0.0, w
    keep = w > rcond * w_max
    inv = (v[:, keep] * (1.0 / w[keep])) @ v[:, keep].conj().T
    z = np.asarray(s_eh, dtype=complex) @ inv
    ratio = float(w[0] / w_max)
    cond = float(w_max / w[0]) if w[0] > 0.0 else float("inf")
    return z, cond, ratio, w


def _block_reduce(values, block_ids, first_block, last_block):
    """Suma por bloque contiguo sin bucles por ventana."""
    edges = np.searchsorted(
        block_ids, np.arange(first_block, last_block + 2, dtype=block_ids.dtype)
    )
    return np.add.reduceat(values, edges[:-1], axis=0)


def accumulate(read, n_samples, fs, freqs, bins, n_window, step, taper,
               band_range, chunk_windows, block_windows, z_prev=None,
               scales=None, c_huber=1.5, collect_subsample=False,
               subsample_stride=64):
    """Una pasada sobre los datos: matrices por bloque y totales.

    Devuelve (ee_b, eh_b, hh_b, sub) donde ``sub`` contiene las matrices
    submuheadas para estimar la escala robusta de la pasada siguiente.
    """
    n_freq = len(freqs)
    n_win_total = n_samples // step
    n_blocks = int(math.ceil(n_win_total / float(block_windows)))
    ee_b = np.zeros((n_freq, n_blocks, 2, 2), dtype=complex)
    eh_b = np.zeros((n_freq, n_blocks, 2, 2), dtype=complex)
    hh_b = np.zeros((n_freq, n_blocks, 2, 2), dtype=complex)
    sub = {i: ([], [], [], []) for i in range(n_freq)} if collect_subsample else None

    for first_window, windows in window_blocks(read, n_samples, n_window, step,
                                               chunk_windows):
        spectra = window_spectra(windows, taper)
        n_win = spectra.shape[0]
        idx = np.arange(first_window, first_window + n_win)
        block_ids = idx // block_windows
        b0 = int(block_ids[0])
        b1 = int(block_ids[-1])
        take = None
        if collect_subsample:
            take = np.flatnonzero(idx % subsample_stride == 0)
        for fi in range(n_freq):
            ee, eh, hh = cross_products(spectra, bins[fi])
            if z_prev is not None and scales is not None:
                w = huber_weights(ee, eh, hh, z_prev[fi], scales[fi], c_huber)
            else:
                w = np.ones(n_win, dtype=float)
            if collect_subsample and take.size:
                ee_s = ee[take]
                eh_s = eh[take]
                hh_s = hh[take]
                sub[fi][0].append(idx[take])
                sub[fi][1].append(ee_s)
                sub[fi][2].append(eh_s)
                sub[fi][3].append(hh_s)
            if np.all(w == 1.0):
                ee_w, eh_w, hh_w = ee, eh, hh
            else:
                ww = w[:, None, None]
                ee_w = ee * ww
                eh_w = eh * ww
                hh_w = hh * ww
            ee_b[fi, b0:b1 + 1] += _block_reduce(ee_w, block_ids, b0, b1)
            eh_b[fi, b0:b1 + 1] += _block_reduce(eh_w, block_ids, b0, b1)
            hh_b[fi, b0:b1 + 1] += _block_reduce(hh_w, block_ids, b0, b1)

    if collect_subsample:
        packed = {}
        for fi in range(n_freq):
            if not sub[fi][0]:
                packed[fi] = None
                continue
            packed[fi] = (
                np.concatenate(sub[fi][0]),
                np.concatenate(sub[fi][1]),
                np.concatenate(sub[fi][2]),
                np.concatenate(sub[fi][3]),
            )
        sub = packed
    return ee_b, eh_b, hh_b, sub


def scale_from_subsample(sub_fi, z):
    """Mediana del misfit relativo en la submuestra; escala robusta de Huber."""
    if sub_fi is None or z is None:
        return float("nan")
    _, ee, eh, hh = sub_fi
    resid, energy = residual_trace(ee, eh, hh, z)
    u = np.sqrt(resid / np.maximum(energy, _EPS))
    u = u[np.isfinite(u)]
    if u.size == 0:
        return float("nan")
    return float(np.median(u))


def bootstrap_covariance(ee_b, eh_b, hh_b, replicates, seed):
    """Bootstrap por bloques de la respuesta compleja y sus derivadas."""
    n_freq, n_blocks = eh_b.shape[0], eh_b.shape[1]
    rng = np.random.default_rng(int(seed))
    z_reps = np.full((replicates, n_freq, 2, 2), np.nan + 0j, dtype=complex)
    valid = np.zeros((replicates, n_freq), dtype=bool)
    for r in range(replicates):
        pick = rng.integers(0, n_blocks, n_blocks)
        for fi in range(n_freq):
            z, _, _, _ = solve_z(eh_b[fi, pick].sum(axis=0),
                                 hh_b[fi, pick].sum(axis=0))
            if np.all(np.isfinite(z)):
                z_reps[r, fi] = z
                valid[r, fi] = True
    return z_reps, valid


def covariance_and_sigma(z_reps, valid, freqs):
    """Covarianza de [Re, Im] de los cuatro componentes y sigma de Zxy."""
    n_freq = z_reps.shape[1]
    cov = np.full((n_freq, 8, 8), np.nan, dtype=float)
    sigma_log10 = np.full(n_freq, np.nan, dtype=float)
    sigma_phase = np.full(n_freq, np.nan, dtype=float)
    for fi in range(n_freq):
        rows = z_reps[valid[:, fi], fi]
        if rows.shape[0] < 8:
            continue
        vec = np.concatenate([rows[:, 0, 0].real[:, None], rows[:, 0, 0].imag[:, None],
                              rows[:, 0, 1].real[:, None], rows[:, 0, 1].imag[:, None],
                              rows[:, 1, 0].real[:, None], rows[:, 1, 0].imag[:, None],
                              rows[:, 1, 1].real[:, None], rows[:, 1, 1].imag[:, None]],
                             axis=1)
        cov[fi] = np.cov(vec, rowvar=False, ddof=1)
        zxy = rows[:, 0, 1]
        if np.all(np.abs(zxy) > 0):
            sigma_log10[fi] = float(np.std(np.log10(np.abs(zxy)), ddof=1))
            sigma_phase[fi] = float(np.std(np.degrees(np.angle(zxy)), ddof=1))
    return cov, sigma_log10, sigma_phase


def coherence(s_eh, s_ee, s_hh, row, col):
    denom = s_ee[row, row].real * s_hh[col, col].real
    if denom <= 0.0:
        return float("nan")
    return float(min(1.0, abs(s_eh[row, col]) ** 2 / denom))


def gamma2_crit(k_eff, alpha):
    if k_eff is None or k_eff < 2:
        return float("nan")
    return float(1.0 - alpha ** (1.0 / (k_eff - 1.0)))


def estimate(read, n_samples, fs, freqs, cfg, bins=None, seed=None):
    """Estima Z y su covarianza para una banda de un registro.

    ``read`` debe devolver muestras en uV (o unidades consistentes) con forma
    ``(m, 5)``. El resultado es una respuesta relativa si la calibracion no se
    aplica antes. Cada frecuencia recibe un ``estado``: ``estimado``,
    ``no_identificable`` (S_HH mal condicionada) o ``senal_insuficiente``
    (ventanas insuficientes, Z no finita o coherencia bajo el critico).
    """
    est = cfg["estimator"]
    rob = cfg["robust"]
    boot = cfg["bootstrap"]
    ident = cfg["identifiability"]
    n_window = int(est["window_samples"])
    step = max(1, int(round(n_window * (1.0 - float(est["overlap_fraction"])))))
    taper = hann_window(n_window)
    band_range = tuple(float(v) for v in cfg["_band_range"])
    if bins is None:
        bins = [band_bins(f, fs, n_window, float(est["band_half_width_rel"]), band_range)
                for f in freqs]
    chunk_windows = 8192
    block_windows = max(1, int(round(float(boot["block_seconds"]) * fs / step)))
    n_blocks = int(math.ceil(n_samples / float(step) / block_windows))
    common = dict(n_window=n_window, step=step, taper=taper, band_range=band_range,
                  chunk_windows=chunk_windows, block_windows=block_windows,
                  c_huber=float(rob["huber_c"]),
                  subsample_stride=int(rob["subsample_stride"]))

    ee_b, eh_b, hh_b, sub = accumulate(read, n_samples, fs, freqs, bins,
                                       collect_subsample=True, **common)
    z_ls = np.array([solve_z(eh_b[i].sum(axis=0), hh_b[i].sum(axis=0))[0]
                     for i in range(len(freqs))])
    z_final = z_ls.copy()
    scales = np.array([scale_from_subsample(sub[i], z_ls[i])
                       for i in range(len(freqs))])
    for _ in range(int(rob["passes"]) if rob.get("enabled", True) else 0):
        ee_b, eh_b, hh_b, sub = accumulate(read, n_samples, fs, freqs, bins,
                                           z_prev=z_final, scales=scales,
                                           collect_subsample=True, **common)
        z_final = np.array([solve_z(eh_b[i].sum(axis=0), hh_b[i].sum(axis=0))[0]
                            for i in range(len(freqs))])
        scales = np.array([scale_from_subsample(sub[i], z_final[i])
                           for i in range(len(freqs))])

    z_reps, valid = bootstrap_covariance(ee_b, eh_b, hh_b,
                                         int(boot["replicates"]),
                                         boot["seed"] if seed is None else seed)
    cov, sigma_log10, sigma_phase = covariance_and_sigma(z_reps, valid, freqs)

    rows = []
    for fi, f in enumerate(freqs):
        s_ee = ee_b[fi].sum(axis=0)
        s_eh = eh_b[fi].sum(axis=0)
        s_hh = hh_b[fi].sum(axis=0)
        z = z_final[fi]
        z_solved, cond, eig_ratio, _ = solve_z(s_eh, s_hh)
        n_valid = int(valid[:, fi].sum())
        k_eff = min(n_blocks, n_valid) if n_valid else 0
        finite = bool(np.all(np.isfinite(z)))
        coh_xy = coherence(s_eh, s_ee, s_hh, 0, 1)
        coh_yx = coherence(s_eh, s_ee, s_hh, 1, 0)
        g_crit = gamma2_crit(int(k_eff), float(ident["gamma2_alpha"]))
        if not finite or n_valid < int(ident["min_windows"]):
            estado = "senal_insuficiente"
            motivo = "sin_ventanas_suficientes_o_Z_no_finita"
        elif cond > float(ident["cond_max"]) or eig_ratio < float(ident["eig_ratio_min"]):
            estado = "no_identificable"
            motivo = "S_HH_rango_deficiente"
        elif np.isfinite(g_crit) and coh_xy < g_crit:
            estado = "senal_insuficiente"
            motivo = "coherencia_Ex_Hy_bajo_critico"
        else:
            estado = "estimado"
            motivo = ""
        f_bins = np.asarray(bins[fi], dtype=float) * (float(fs) / float(n_window))
        rows.append(dict(
            frequency_hz=float(f),
            z=z,
            z_ls=z_ls[fi],
            cov=cov[fi],
            sigma_log10_abs_zxy=sigma_log10[fi],
            sigma_phase_zxy_deg=sigma_phase[fi],
            coherence_xy=coh_xy,
            coherence_yx=coh_yx,
            cond_hh=cond,
            eig_ratio=eig_ratio,
            n_windows=int(n_samples // step),
            n_blocks=int(n_blocks),
            k_eff=int(k_eff),
            gamma2_crit=g_crit,
            estado=estado,
            motivo=motivo,
            bins=bins[fi],
            band_lo_hz=float(f_bins[0]),
            band_hi_hz=float(f_bins[-1]),
            n_bins=int(f_bins.size),
        ))
    return dict(rows=rows, z_final=z_final, z_ls=z_ls, scales=scales,
                n_samples=int(n_samples), fs=float(fs), n_window=n_window,
                step=step, block_windows=block_windows, n_blocks=n_blocks)


# ----------------------------------------------------------------------
# Controles sinteticos (sin TEM): verdad 1D de mt1d y series controladas
# ----------------------------------------------------------------------
def _smooth_band(nf, fs, n_samples, band):
    f = np.fft.rfftfreq(int(n_samples), 1.0 / float(fs))
    lo, hi = float(band[0]), float(band[1])
    mask = np.zeros(nf, dtype=float)
    inside = (f >= lo) & (f <= hi)
    mask[inside] = 1.0
    width = 0.08 * (hi - lo)
    left = (f >= lo - width) & (f < lo)
    right = (f > hi) & (f <= hi + width)
    mask[left] = 0.5 * (1.0 - np.cos(math.pi * (f[left] - (lo - width)) / width))
    mask[right] = 0.5 * (1.0 + np.cos(math.pi * (f[right] - hi) / width))
    return mask


def synthesize(fs, n_samples, rho, interfaces, band, seed, snr_db=None,
               noise_target=None, coherent_rel=0.0, outliers=0.0,
               rango_uno=False, amplitude=1.0):
    """Genera E y H con relacion E = Z H y contaminacion controlada."""
    from mt1d import z1d

    rng = np.random.default_rng(int(seed))
    n_samples = int(n_samples)
    nf = n_samples // 2 + 1
    f = np.fft.rfftfreq(n_samples, 1.0 / float(fs))
    mask = _smooth_band(nf, fs, n_samples, band)

    hx = (rng.normal(size=nf) + 1j * rng.normal(size=nf)) * mask
    hy = (rng.normal(size=nf) + 1j * rng.normal(size=nf)) * mask
    if rango_uno:
        hy = 0.6 * hx

    z_spec = np.zeros(nf, dtype=complex)
    positive = f > 0
    z_spec[positive] = z1d(f[positive], rho, interfaces)
    ex = z_spec * hy
    ey = -z_spec * hx

    def to_time(spec):
        spec = spec.copy()
        spec[0] = 0.0
        spec[-1] = spec[-1].real
        return np.fft.irfft(spec, n=n_samples)

    h = np.column_stack([to_time(hx), to_time(hy)])
    e = np.column_stack([to_time(ex), to_time(ey)])
    h *= float(amplitude)
    e *= float(amplitude)

    def add_band_noise(signal, target_std, seed_offset):
        local = np.random.default_rng(int(seed) + seed_offset)
        white = local.normal(size=(n_samples, signal.shape[1]))
        spec = np.fft.rfft(white, axis=0) * mask[:, None]
        noise = np.fft.irfft(spec, n=n_samples, axis=0)
        noise *= target_std / max(np.std(noise), _EPS)
        return signal + noise

    band_std_e = float(np.std(e))
    band_std_h = float(np.std(h))
    if snr_db is not None and noise_target == "E":
        sigma = band_std_e / (10.0 ** (float(snr_db) / 20.0))
        e = add_band_noise(e, sigma, 101)
    elif snr_db is not None and noise_target == "H":
        sigma = band_std_h / (10.0 ** (float(snr_db) / 20.0))
        h = add_band_noise(h, sigma, 202)

    if coherent_rel > 0.0:
        local = np.random.default_rng(int(seed) + 303)
        base = (local.normal(size=nf) + 1j * local.normal(size=nf)) * mask
        base[0] = 0.0
        base[-1] = base[-1].real
        common = np.fft.irfft(base, n=n_samples)
        common /= max(np.std(common), _EPS)
        e = e + (float(coherent_rel) * band_std_e) * common[:, None]
        h = h + (float(coherent_rel) * band_std_h) * common[:, None]

    if outliers > 0.0:
        n_spikes = int(round(float(outliers) * n_samples))
        if n_spikes:
            idx = rng.integers(0, n_samples, n_spikes)
            amp = 12.0 * float(np.std(e))
            for row in idx:
                width = int(rng.integers(1, 4))
                stop = min(n_samples, row + width)
                e[row:stop, 0] += amp
                e[row:stop, 1] -= 0.7 * amp

    return dict(e=e, h=h, f=f, z_true=z_spec, band_std_e=band_std_e,
                band_std_h=band_std_h, mask=mask)


def truth_impedance(freqs, rho, interfaces):
    from mt1d import z1d
    return z1d(np.asarray(freqs, dtype=float), rho, interfaces)
