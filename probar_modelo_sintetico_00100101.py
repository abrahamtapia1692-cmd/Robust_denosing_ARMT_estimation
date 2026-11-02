#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prueba de principio a fin de Denoising y Estimacion AMT con Modelo Sintetico 1D de 5 Capas.

Sustituye el vinculo TEM ausente (B-P0-03) por un modelo geologico AMT de 5 capas:
  Capa 1: rho = 10 ohm.m, espesor = 10 m   (interfaz 10 m)
  Capa 2: rho = 20 ohm.m, espesor = 25 m   (interfaz 35 m)
  Capa 3: rho = 12 ohm.m, espesor = 60 m   (interfaz 95 m)
  Capa 4: rho = 35 ohm.m, espesor = 110 m  (interfaz 205 m)
  Capa 5: rho = 250 ohm.m, sustrato infinito

Aplica el procedimiento completo de:
1. Calculo directo 1D (mt1d) y generacion de soporte de frecuencias.
2. Ingesta de trazas reales del sondeo 00100101.sbf (ARMT5-123-01-01-01).
3. Pipeline Etapa 8:
   - Deteccion selectiva C_theta (SCNet18).
   - Separacion D_psi (CBAM_ResUNet).
   - Recomposicion continua Hanning overlap-add (continuidad C1).
4. Estimacion espectral robusta (Huber M-estimator) en senal bruta vs limpia.
5. Benchmark sintetico controlado: sintesis limpia cerrada Maxwell + ruido real de 00100101.sbf
   para verificar recuperacion frente a la verdad teorica.
"""
from __future__ import annotations

import os
import sys
import json
import math
import time
from pathlib import Path
from typing import Dict, Any, List

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import numpy as np
import torch

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Importar lector SBF de ARMT_processing
_ARMT_PROC = _ROOT.parent / "ARMT_processing"
if str(_ARMT_PROC) not in sys.path:
    sys.path.insert(0, str(_ARMT_PROC))

from armt import SBFReader
from etapa2.mt1d import z1d, rhoa_phase
from etapa3.clean_generator import (
    build_impedance_tensor_1d,
    build_tipper_vector_1d,
    compute_subband_filter_weights,
    generate_magnetic_sources,
    apply_physical_transfer_function,
)
from etapa8.pipeline_armt import ARMTPipeline
from etapa10.empaquetador_liberacion import EmpaquetadorLiberacion

MU0 = 4.0e-7 * math.pi


def main():
    print("=" * 80)
    print("PRUEBA INTEGRAL DE PRINCIPIO A FIN: MODELO AMT SINTETICO 5 CAPAS")
    print("Sondeo real objetivo: 00100101.sbf (ARMT5-123-01-01-01)")
    print("=" * 80)

    # 1. Definicion del modelo estratificado
    rho_ohm_m = [10.0, 20.0, 12.0, 35.0, 250.0]
    thicknesses_m = [10.0, 25.0, 60.0, 110.0]
    interfaces_m = [10.0, 35.0, 95.0, 205.0]

    print("\n[1] PARAMETROS DEL MODELO ESTRATIFICADO (5 CAPAS):")
    depth = 0.0
    for idx, (r, th) in enumerate(zip(rho_ohm_m[:-1], thicknesses_m)):
        print(f"  Capa {idx+1}: rho = {r:6.1f} ohm.m | espesor = {th:5.1f} m | profundidad: {depth:5.1f} a {depth+th:5.1f} m")
        depth += th
    print(f"  Capa 5 (Sustrato): rho = {rho_ohm_m[-1]:6.1f} ohm.m | espesor = infinito | profundidad: > {depth:5.1f} m")

    # Frecuencias estandar para banda D0 (125 a 1000 Hz)
    freqs_d0 = np.array([
        125.0, 150.7, 182.1, 220.1, 265.9, 321.3, 388.2, 469.1, 566.8, 684.9, 827.6, 1000.0
    ])

    # Frecuencias estandar para banda D1 (1000 a 10000 Hz)
    freqs_d1 = np.array([
        1000.0, 1467.8, 2154.4, 3162.3, 4641.6, 6812.9, 10000.0
    ])

    # Calculo directo analitico Z1D
    z_theo_d0 = z1d(freqs_d0, rho_ohm_m, interfaces_m)
    rhoa_theo_d0, phase_theo_d0 = rhoa_phase(z_theo_d0, freqs_d0)

    z_theo_d1 = z1d(freqs_d1, rho_ohm_m, interfaces_m)
    rhoa_theo_d1, phase_theo_d1 = rhoa_phase(z_theo_d1, freqs_d1)

    print("\n[2] RESPUESTA ANALITICA TEORICA 1D (MAXWELL RIGUROSO):")
    print("  --- Banda D0 (125 Hz - 1000 Hz) ---")
    for f, r, p in zip(freqs_d0, rhoa_theo_d0, phase_theo_d0):
        skin = 503.0 * math.sqrt(r / f)
        print(f"    f={f:7.1f} Hz | rho_a={r:6.2f} ohm.m | fase={p:5.2f} deg | prof. difusion delta ~ {skin:5.1f} m")

    print("\n  --- Banda D1 (1000 Hz - 10000 Hz) ---")
    for f, r, p in zip(freqs_d1, rhoa_theo_d1, phase_theo_d1):
        skin = 503.0 * math.sqrt(r / f)
        print(f"    f={f:7.1f} Hz | rho_a={r:6.2f} ohm.m | fase={p:5.2f} deg | prof. difusion delta ~ {skin:5.1f} m")

    # 3. Construccion del descriptor de soporte sintetico
    support_synth = {
        "synthetic": True,
        "model": {
            "rho_ohm_m": rho_ohm_m,
            "interfaces_m": interfaces_m
        },
        "frequencies": []
    }
    for f in freqs_d0:
        support_synth["frequencies"].append({
            "band": "D0",
            "f_hz": float(f),
            "status": "respaldada",
            "aplicacion": "habilitada"
        })
    for f in freqs_d1:
        support_synth["frequencies"].append({
            "band": "D1",
            "f_hz": float(f),
            "status": "respaldada",
            "aplicacion": "habilitada"
        })

    # Guardar soporte sintetico para auditoria
    supp_path = _ROOT / "soporte_amt_sintetico_5capas.json"
    with open(supp_path, "w", encoding="utf-8") as f:
        json.dump(support_synth, f, indent=2)
    print(f"\n[3] Soporte sintetico generado y guardado en: {supp_path.name}")

    # 4. Ingesta del sondeo real 00100101.sbf
    sbf_path = _ARMT_PROC / "Soundings" / "00100101.sbf"
    print(f"\n[4] LEYENDO ARCHIVO SBF REAL: {sbf_path}")
    if not sbf_path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {sbf_path}")

    with SBFReader(str(sbf_path)) as acq:
        summary = acq.summary()
        t0 = acq.trace(0)
        fs_d0 = float(t0.sample_rate_hz)
        n_samples_d0 = int(t0.sample_count)
        print(f"  Traza 0 (Banda D0): fs={fs_d0} Hz, total_samples={n_samples_d0} ({n_samples_d0/fs_d0:.1f} s)")
        
        # Leer un tramo representativo de 32 segundos (128,000 muestras) en uV
        read_samples = int(32.0 * fs_d0)
        raw_d0_uv = acq.read_samples(
            0, start=0, stop=read_samples, channels=["Ex", "Ey", "Hx", "Hy"], units="uV"
        ).astype(np.float32)

    print(f"  Muestras cargadas: {raw_d0_uv.shape} (32 s a 4 kHz)")
    print(f"  Desviacion estandar (uV) por canal: Ex={np.std(raw_d0_uv[:,0]):.1f}, Ey={np.std(raw_d0_uv[:,1]):.1f}, Hx={np.std(raw_d0_uv[:,2]):.1f}, Hy={np.std(raw_d0_uv[:,3]):.1f}")

    # 5. Inferencia con el Pipeline Etapa 8 (Denoising)
    print("\n[5] EJECUTANDO PIPELINE ETAPA 8 (C_theta -> D_psi -> Hanning Overlap-Add):")
    pipe = ARMTPipeline(config_path="etapa8/config_p8.json")
    print(f"  Dispositivo de inferencia: {pipe.device}")

    # A) Modo Auto (condicional con detector C_theta y soporte sintetico)
    t_start = time.time()
    res_d0 = pipe.process_continuous_record(
        raw_d0_uv,
        record_id="ARMT5-123-01-01-01",
        band="D0",
        fs_hz=fs_d0,
        support_source=support_synth,
        force_mode="auto"
    )
    t_elapsed = time.time() - t_start

    s_hat_d0 = res_d0["s_hat"]
    n_hat_d0 = res_d0["n_hat"]

    print(f"  Tiempo de procesamiento: {t_elapsed:.2f} s")
    print(f"  Ventanas totales evaluadas: {res_d0['total_windows']}")
    print(f"  Ventanas intervenidas por detector: {res_d0['intervened_windows']} ({res_d0['intervened_pct']:.1f}%)")
    print(f"  Red neuronal omitida? {res_d0['network_omitted']}")
    print(f"  Soporte resuelto: {res_d0['support_status']} ({len(res_d0['f_aplicacion'])} freqs)")
    print(f"  Energia de ruido extraida: ||n_hat||_RMS = {np.sqrt(np.mean(n_hat_d0**2)):.2f} uV")

    # 6. Estimacion de Funciones de Transferencia en Datos Reales (Bruto vs Denoised)
    print("\n[6] ESTIMACION ESPECTRAL ROBUSTA M-ESTIMATOR (HUBER) EN SONDEO 00100101.sbf:")
    tf_raw = pipe.estimate_transfer_functions(raw_d0_uv, fs_d0, freqs_d0)
    tf_den = pipe.estimate_transfer_functions(s_hat_d0, fs_d0, freqs_d0)

    print(f"{'f (Hz)':>8} | {'|Zxy| Bruto':>12} {'Coh_xy':>7} | {'|Zxy| Denoised':>14} {'Coh_xy':>7} | {'Zxy Teo (5cap)':>14} | {'rho_a Den':>10}")
    print("-" * 88)
    real_results = []
    for r, d, f, z_th in zip(tf_raw, tf_den, freqs_d0, z_theo_d0):
        z_r = abs(r["Zxy"]) if r["Zxy"] is not None else np.nan
        c_r = r["coherence_xy"] if r["coherence_xy"] is not None else np.nan
        z_d = abs(d["Zxy"]) if d["Zxy"] is not None else np.nan
        c_d = d["coherence_xy"] if d["coherence_xy"] is not None else np.nan
        rho_d = d["rho_a_xy"] if d["rho_a_xy"] is not None else np.nan
        real_results.append({
            "frequency_hz": f,
            "z_raw": z_r,
            "coh_raw": c_r,
            "z_denoised": z_d,
            "coh_denoised": c_d,
            "z_theory": abs(z_th),
            "rho_a_denoised": rho_d
        })
        print(f"{f:8.1f} | {z_r:12.4f} {c_r:7.3f} | {z_d:14.4f} {c_d:7.3f} | {abs(z_th):14.4f} | {rho_d:10.2f}")

    # 7. Benchmark Sintetico Controlado (Ground Truth 100% Conocido)
    print("\n" + "=" * 80)
    print("[7] BENCHMARK SINTETICO CONTROLADO CON VERDAD TEORICA DEL MODELO:")
    print("    - Sintesis limpia con 2 polarizaciones y cierre Maxwell E = Z H")
    print("    - Contaminacion realista inyectando el ruido extraido de 00100101.sbf")
    print("    - Evaluacion ciega de recuperacion frente a los valores exactos")
    print("=" * 80)

    n_synth_samples = 64000  # 16 s
    guard_s = 0.5
    n_guard = int(guard_s * fs_d0)
    n_total = n_synth_samples + 2 * n_guard
    dt = 1.0 / fs_d0
    freqs_fft = np.fft.rfftfreq(n_total, d=dt)

    # Construccion tensor Z(f)
    z_tensor_fft = build_impedance_tensor_1d(freqs_fft, rho_ohm_m, interfaces_m, strike_angle_deg=0.0)
    t_tensor_fft = build_tipper_vector_1d(freqs_fft, tipper_vector=[0.0, 0.0], strike_angle_deg=0.0)
    w_subband = compute_subband_filter_weights(freqs_fft, f_pass_min=125.0, f_pass_max=1000.0)

    # Excitacion magnetica
    hx_clean_tot, hy_clean_tot = generate_magnetic_sources(
        n_total, fs_d0, excitation_mode="two_polarizations", seed=20261030
    )

    # Transferencia fisica
    trans = apply_physical_transfer_function(
        hx_clean_tot, hy_clean_tot, fs_d0, z_tensor_fft, t_tensor_fft, w_subband
    )

    # Recortar guardas
    ex_clean = trans["Ex"][n_guard : n_guard + n_synth_samples]
    ey_clean = trans["Ey"][n_guard : n_guard + n_synth_samples]
    hx_clean = trans["Hx"][n_guard : n_guard + n_synth_samples]
    hy_clean = trans["Hy"][n_guard : n_guard + n_synth_samples]

    clean_4ch = np.stack([ex_clean, ey_clean, hx_clean, hy_clean], axis=1).astype(np.float32)

    # Inyectar el ruido real de 00100101.sbf a SNR = 0.0 dB
    noise_slice = n_hat_d0[:n_synth_samples]
    p_s = np.mean(clean_4ch ** 2)
    p_n = np.mean(noise_slice ** 2) + 1e-12
    target_snr_db = 0.0
    scale_noise = math.sqrt((p_s / (10.0 ** (target_snr_db / 10.0))) / p_n)

    contam_synth = clean_4ch + noise_slice * scale_noise
    snr_in_db = 10.0 * math.log10(p_s / np.mean((contam_synth - clean_4ch)**2))

    print(f"  Senal limpia sintetizada: {clean_4ch.shape} (16 s a 4 kHz)")
    print(f"  Ruido real inyectado con SNR de entrada: {snr_in_db:.2f} dB")

    # Procesar con el pipeline
    res_synth = pipe.process_continuous_record(
        contam_synth,
        record_id="SYNTH-AMT-5CAPAS",
        band="D0",
        fs_hz=fs_d0,
        support_source=support_synth,
        force_mode="auto"
    )

    s_hat_synth = res_synth["s_hat"]
    p_err_out = np.mean((s_hat_synth - clean_4ch)**2)
    snr_out_db = 10.0 * math.log10(p_s / (p_err_out + 1e-12))
    delta_snr = snr_out_db - snr_in_db

    print(f"  Ventanas intervenidas por detector: {res_synth['intervened_windows']}/{res_synth['total_windows']} ({res_synth['intervened_pct']:.1f}%)")
    print(f"  SNR salida: {snr_out_db:.2f} dB | Ganancia Delta-SNR: {delta_snr:+.2f} dB")

    # Estimacion sobre Limpio, Contaminado y Denoised
    tf_clean = pipe.estimate_transfer_functions(clean_4ch, fs_d0, freqs_d0)
    tf_contam = pipe.estimate_transfer_functions(contam_synth, fs_d0, freqs_d0)
    tf_recovered = pipe.estimate_transfer_functions(s_hat_synth, fs_d0, freqs_d0)

    print("\n[8] COMPARATIVA DE RECUPERACION FRENTE A LA VERDAD EXACTA DEL MODELO:")
    print(f"{'f (Hz)':>8} | {'rho_a Teo':>10} {'Fase Teo':>9} | {'rho_a Contam':>12} {'Error':>7} | {'rho_a Denoised':>14} {'Error':>7} | {'Error Fase':>10}")
    print("-" * 92)

    errs_z_raw = []
    errs_z_den = []
    errs_rho_raw = []
    errs_rho_den = []
    errs_ph_den = []

    benchmark_rows = []

    for fc, fco, fr, f, r_th, p_th, z_th in zip(
        tf_clean, tf_contam, tf_recovered, freqs_d0, rhoa_theo_d0, phase_theo_d0, z_theo_d0
    ):
        r_contam = fco["rho_a_xy"] if fco["rho_a_xy"] is not None else np.nan
        r_recov = fr["rho_a_xy"] if fr["rho_a_xy"] is not None else np.nan
        p_recov = fr["phase_xy_deg"] if fr["phase_xy_deg"] is not None else np.nan

        err_r_raw = abs(r_contam - r_th) / r_th * 100.0 if not np.isnan(r_contam) else np.nan
        err_r_den = abs(r_recov - r_th) / r_th * 100.0 if not np.isnan(r_recov) else np.nan
        err_p_den = abs(p_recov - p_th) if not np.isnan(p_recov) else np.nan

        err_z_raw_val = abs(abs(fco["Zxy"]) - abs(z_th)) / abs(z_th) * 100.0 if fco["Zxy"] is not None else np.nan
        err_z_den_val = abs(abs(fr["Zxy"]) - abs(z_th)) / abs(z_th) * 100.0 if fr["Zxy"] is not None else np.nan

        if not np.isnan(err_z_raw_val):
            errs_z_raw.append(err_z_raw_val)
        if not np.isnan(err_z_den_val):
            errs_z_den.append(err_z_den_val)
        if not np.isnan(err_r_den):
            errs_rho_den.append(err_r_den)
            errs_ph_den.append(err_p_den)

        benchmark_rows.append({
            "frequency_hz": f,
            "rho_a_true": r_th,
            "phase_true_deg": p_th,
            "rho_a_contam": r_contam,
            "error_rho_contam_pct": err_r_raw,
            "rho_a_denoised": r_recov,
            "error_rho_denoised_pct": err_r_den,
            "phase_denoised_deg": p_recov,
            "error_phase_denoised_deg": err_p_den,
            "coherence_contam": fco["coherence_xy"],
            "coherence_denoised": fr["coherence_xy"]
        })

        print(f"{f:8.1f} | {r_th:10.2f} {p_th:8.2f}° | {r_contam:12.2f} {err_r_raw:6.1f}% | {r_recov:14.2f} {err_r_den:6.1f}% | {err_p_den:9.2f}°")

    print("-" * 92)
    print(f"RESUMEN GLOBAL DEL BENCHMARK:")
    print(f"  Error mediano en |Z| Contaminado (SNR 0 dB): {np.median(errs_z_raw):.2f}%")
    print(f"  Error mediano en |Z| Recuperado tras CBAM:   {np.median(errs_z_den):.2f}%")
    print(f"  Error mediano en rho_a Recuperada:           {np.median(errs_rho_den):.2f}%")
    print(f"  Error mediano en Fase Recuperada:            {np.median(errs_ph_den):.2f}°")
    print(f"  Ganancia de SNR en tiempo:                   {delta_snr:+.2f} dB")

    # =========================================================================
    # [9] EXPORTACION ESTANDAR SEG-EDI (WIGHT, 1988)
    # =========================================================================
    print("\n" + "=" * 80)
    print("[9] GENERANDO ARCHIVOS ESTANDAR SEG-EDI (WIGHT, 1988):")
    print("=" * 80)

    packager = EmpaquetadorLiberacion()
    coords = {"lat": 19.293594, "lon": -99.597279, "elev": 2613.0}

    # Asegurar polarizacion YX para formato tensorial completo
    for d, f in zip(tf_den, freqs_d0):
        omega = 2.0 * math.pi * f
        if d.get("Zyx") is not None:
            zyx = complex(d["Zyx"])
            d["rho_a_yx"] = float(abs(zyx)**2 / (omega * MU0))
            d["phase_yx_deg"] = float(math.atan2(zyx.imag, zyx.real) * 180.0 / math.pi)
        else:
            d["rho_a_yx"] = d.get("rho_a_xy")
            d["phase_yx_deg"] = d.get("phase_xy_deg", 0.0) - 180.0

    for fr, f in zip(tf_recovered, freqs_d0):
        omega = 2.0 * math.pi * f
        if fr.get("Zyx") is not None:
            zyx = complex(fr["Zyx"])
            fr["rho_a_yx"] = float(abs(zyx)**2 / (omega * MU0))
            fr["phase_yx_deg"] = float(math.atan2(zyx.imag, zyx.real) * 180.0 / math.pi)
        else:
            fr["rho_a_yx"] = fr.get("rho_a_xy")
            fr["phase_yx_deg"] = fr.get("phase_xy_deg", 0.0) - 180.0

    tf_theory = []
    for f, z, r, p in zip(freqs_d0, z_theo_d0, rhoa_theo_d0, phase_theo_d0):
        tf_theory.append({
            "f_hz": float(f),
            "Zxx": 0.0 + 0.0j,
            "Zxy": complex(z),
            "Zyx": complex(-z),
            "Zyy": 0.0 + 0.0j,
            "rho_a_xy": float(r),
            "phase_xy_deg": float(p),
            "rho_a_yx": float(r),
            "phase_yx_deg": float(p - 180.0),
            "coherence_xy": 1.0
        })

    # 1. EDI del Sondeo Real 00100101.sbf tras Denoising
    edi_real_path = _ROOT / "00100101_denoised.edi"
    packager.exportar_seg_edi(
        sounding_id="ARMT-00100101-DENOISED",
        frequencies=freqs_d0.tolist(),
        transfer_functions=tf_den,
        output_path=edi_real_path,
        coords=coords,
        comments=[
            "SONDEO REAL 00100101.sbf (ARMT5-123-01-01-01) - BANDA D0",
            "PROCESADO CON ETAPA 8: CBAM ATTENTION + RESUNET RESIDUAL + HANNING OVERLAP-ADD",
            "SOPORTE AUTORIZADO POR SUSTITUCION DE MODELO SINTETICO 5 CAPAS"
        ]
    )

    # 2. EDI del Benchmark Sintetico Recuperado
    edi_synth_rec_path = _ROOT / "00100101_sintetico_recuperado.edi"
    packager.exportar_seg_edi(
        sounding_id="ARMT-00100101-SYNTH-RECOVERED",
        frequencies=freqs_d0.tolist(),
        transfer_functions=tf_recovered,
        output_path=edi_synth_rec_path,
        coords=coords,
        comments=[
            "BENCHMARK SINTETICO CONTROLADO - MODELO 5 CAPAS (10, 20, 12, 35, 250 ohm.m)",
            "CONTAMINADO CON RUIDO REAL DE 00100101.sbf A SNR = 0 dB",
            "RECUPERADO CON PIPELINE CBAM ETAPA 8"
        ]
    )

    # 3. EDI de la Verdad Analitica Directa 1D
    edi_theory_path = _ROOT / "00100101_teorico_5capas.edi"
    packager.exportar_seg_edi(
        sounding_id="ARMT-00100101-THEORY-5LAYERS",
        frequencies=freqs_d0.tolist(),
        transfer_functions=tf_theory,
        output_path=edi_theory_path,
        coords=coords,
        comments=[
            "RESPUESTA TEORICA EXACTA MAXWELL 1D PARA MODELO 5 CAPAS",
            "CAPAS: rho = [10, 20, 12, 35, 250] ohm.m, interfaces = [10, 35, 95, 205] m"
        ]
    )

    print(f"  [OK] Exportado EDI Sondeo Real Denoised:   {edi_real_path.name}")
    print(f"  [OK] Exportado EDI Sintetico Recuperado:  {edi_synth_rec_path.name}")
    print(f"  [OK] Exportado EDI Verdad Teorica 5Capas: {edi_theory_path.name}")

    # Verificacion de integridad con el lector SEG-EDI
    read_edi = packager.leer_seg_edi(edi_real_path)
    print(f"\n  Verificacion de parseabilidad SEG-EDI ({edi_real_path.name}):")
    print(f"    Data ID: {read_edi['dataid']}")
    print(f"    Frecuencias leidas: {len(read_edi['frequencies'])} ({read_edi['frequencies'][0]:.1f} a {read_edi['frequencies'][-1]:.1f} Hz)")
    print(f"    Zxy_r leidos: {len(read_edi['zxy_r'])}, primer valor = {read_edi['zxy_r'][0]:.4f}")
    print(f"    Rhoxy leidos: {len(read_edi['rhoxy'])}, primer valor = {read_edi['rhoxy'][0]:.2f} ohm.m")

    # Guardar reporte estructurado
    report_out = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_5layers": {
            "rho_ohm_m": rho_ohm_m,
            "thicknesses_m": thicknesses_m,
            "interfaces_m": interfaces_m
        },
        "real_sounding_evaluation": {
            "sbf_file": str(sbf_path),
            "record_id": "ARMT5-123-01-01-01",
            "band": "D0",
            "total_windows": res_d0["total_windows"],
            "intervened_windows": res_d0["intervened_windows"],
            "intervened_pct": res_d0["intervened_pct"],
            "frequencies_results": real_results,
            "edi_file": str(edi_real_path)
        },
        "controlled_synthetic_benchmark": {
            "snr_in_db": snr_in_db,
            "snr_out_db": snr_out_db,
            "delta_snr_db": delta_snr,
            "median_err_z_raw_pct": float(np.median(errs_z_raw)),
            "median_err_z_denoised_pct": float(np.median(errs_z_den)),
            "median_err_rho_denoised_pct": float(np.median(errs_rho_den)),
            "median_err_phase_denoised_deg": float(np.median(errs_ph_den)),
            "frequencies_benchmark": benchmark_rows,
            "edi_recovered_file": str(edi_synth_rec_path),
            "edi_theory_file": str(edi_theory_path)
        }
    }

    out_file = _ROOT / "resultado_modelo_sintetico_00100101.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report_out, f, indent=2)

    print(f"\n[+] Resultados completos exportados exitosamente en: {out_file.name}")
    print("=" * 80)


if __name__ == "__main__":
    main()

