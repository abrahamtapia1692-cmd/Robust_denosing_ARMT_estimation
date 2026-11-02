#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Motor de Evaluacion Ciega de Extremo a Extremo (Etapa 9 - Puerta P9 y Compuerta G4).

Implementa la ejecucion metodologica e imparcial de los comparadores obligatorios
del Plan de Implementacion v1.3 (§9.1, §13):
- B0: Datos calibrados + estimador robusto Huber (linea base clasica)
- B1: Pre-QC espectral + estimador robusto (beneficio sin aprendizaje)
- B3: SCNet18 reproducido de Zhang et al. (2024) + estimador robusto
- B4: CBAM Adaptado Plan v1.3 (CBAM_ResUNet) con recomposicion continua C1
- B7: Clasificador solo-potencia (control de atajo energetico)
- B8: Filtro multicanal de Wiener 4x4 (cota analitica lineal optima)
- B10: Oraculo teorico (verdad limpia s + estimador robusto)

Evalua no inferioridad en limpios, recuperacion en contaminados, abstencion en
no identificables (rango 1, saturacion ADC, soporte vacio, RMT) y compuerta G4.
"""
from __future__ import annotations

import os
import sys
import json
import math
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import numpy as np
import torch

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from etapa2.mt1d import z1d
from etapa7.modelos_cbam import (
    SCNet18_Classifier,
    SCNet18_Denoiser,
    CBAM_ResUNet_Denoiser,
    MultichannelWienerFilter
)
from etapa8.pipeline_armt import ARMTPipeline

VERSION = "P9-EVAL-1.0.0"
MU0 = 4.0e-7 * math.pi


class BlindEvaluator:
    """Evaluador ciego de extremo a extremo para la Puerta P9 y Compuerta G4."""

    def __init__(
        self,
        config_path: Union[str, Path] = "etapa9/config_p9.json",
        device: Optional[str] = None
    ) -> None:
        self.config_path = Path(config_path)
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.cfg = json.load(f)

        # Dispositivo
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        # Determinismo: toda la evaluacion usa semillas fijas
        self.seed = 20261030
        np.random.seed(self.seed)
        torch.manual_seed(self.seed)

        # Pipeline de Etapa 8
        self.pipeline = ARMTPipeline(config_path="etapa8/config_p8.json", device=str(self.device))

        # Cargar modelo B3 (SCNet18 de Zhang et al.)
        b3_ckpt = _ROOT / "etapa7" / "checkpoints" / "d_psi_b3_scnet18.pt"
        self.model_b3 = SCNet18_Denoiser(in_channels=4, data_size=256)
        if b3_ckpt.exists():
            st_b3 = torch.load(b3_ckpt, map_location=self.device, weights_only=True)
            self.model_b3.load_state_dict(st_b3)
        self.model_b3.to(self.device)
        self.model_b3.eval()

        # B8 se calibra por registro (ver run_benchmark_b8_wiener) para evitar
        # mezclar modelos de Tierra distintos y para preservar Z(f).
        self.wiener_b8 = MultichannelWienerFilter(n_channels=4, n_fft=256)

    def _windows(self, signal: np.ndarray, step: int = 128) -> np.ndarray:
        """Extrae ventanas deslizantes (M, L, C) sin ventaneo."""
        L = self.pipeline.window_length
        n = len(signal)
        return np.array([signal[i : i + L] for i in range(0, max(1, n - L + 1), step)])

    def truth_model(self, sounding_key: str) -> Tuple[List[float], List[float]]:
        """Devuelve (rho, interfaces) del modelo declarado para un sondeo.

        La fuente unica de verdad es config_p9.json; sus valores deben coincidir
        con el generador etapa3/config_p3.json (verificado por V-P9-33).
        """
        snd = self.cfg["blind_soundings"][sounding_key]
        return list(snd.get("rho_ohm_m", [])), list(snd.get("interfaces_m", []))

    def run_benchmark_b1_spectral(
        self,
        time_series: np.ndarray,
        fs_hz: float,
        target_frequencies: List[float]
    ) -> List[Dict[str, Any]]:
        """B1: Pre-QC espectral con filtro notch de 50/60 Hz y estimador robusto."""
        N, C = time_series.shape
        filtered = time_series.copy()
        # Filtro notch simple en armónicos de red para B1
        t = np.arange(N) / fs_hz
        for f_line in [50.0, 60.0, 100.0, 120.0, 150.0, 180.0]:
            if f_line < fs_hz / 2.0:
                for c in range(C):
                    sin_comp = np.sin(2 * np.pi * f_line * t)
                    cos_comp = np.cos(2 * np.pi * f_line * t)
                    a = 2.0 * np.mean(filtered[:, c] * sin_comp)
                    b = 2.0 * np.mean(filtered[:, c] * cos_comp)
                    filtered[:, c] -= (a * sin_comp + b * cos_comp)

        return self.pipeline.estimate_transfer_functions(filtered, fs_hz, target_frequencies)

    def run_benchmark_b3_scnet18(
        self,
        x_continuous: np.ndarray,
        fs_hz: float,
        target_frequencies: List[float]
    ) -> List[Dict[str, Any]]:
        """B3: Inferencia con SCNet18 (Zhang et al. 2024) y estimador robusto."""
        N, C = x_continuous.shape
        L = self.pipeline.window_length
        S = self.pipeline.step

        windows = []
        start = 0
        while start + L <= N:
            windows.append(x_continuous[start : start + L, :4])
            start += S

        if len(windows) == 0:
            return []

        win_arr = np.array(windows, dtype=np.float32)  # (M, L, 4)
        processed = np.zeros_like(win_arr)

        with torch.no_grad():
            for i in range(0, len(win_arr), 32):
                batch = win_arr[i : i + 32]
                x_t = torch.from_numpy(batch).permute(0, 2, 1).to(self.device)  # (B, 4, L)
                out = self.model_b3(x_t)
                s_pred = out["s_hat"].permute(0, 2, 1).cpu().numpy()  # (B, L, 4)
                processed[i : i + len(batch)] = s_pred

        s_hat_b3 = self.pipeline.reconstruct_overlap_add(processed, N, S)
        return self.pipeline.estimate_transfer_functions(s_hat_b3, fs_hz, target_frequencies)

    def run_benchmark_b8_wiener(
        self,
        x_continuous: np.ndarray,
        fs_hz: float,
        target_frequencies: List[float],
        clean_reference: Optional[np.ndarray] = None,
        noise_reference: Optional[np.ndarray] = None,
    ) -> List[Dict[str, Any]]:
        """B8: cota lineal de Wiener que preserva Z(f).

        La ganancia g(f) es real y comun a los cuatro canales, de modo que se
        cancela en Z=E/H. Se calibra con un tramo limpio del propio registro y,
        si se dispone de el, con el ruido verdadero (S_nn verdadera), tal como
        define el plan para B8.
        """
        if clean_reference is None:
            clean_reference = x_continuous
        if noise_reference is None:
            # Sin ruido de referencia: ganancia unitaria (paso directo).
            noise_reference = np.zeros_like(clean_reference)

        clean_w = self._windows(clean_reference)
        noise_w = self._windows(noise_reference)
        if len(clean_w) == 0 or len(noise_w) == 0:
            return []

        self.wiener_b8.fit_scalar(clean_w, noise_w)
        s_hat_b8 = self.wiener_b8.filter_signal_wola(x_continuous)
        return self.pipeline.estimate_transfer_functions(s_hat_b8, fs_hz, target_frequencies)

    def run_benchmark_b7_power(
        self, clean_windows: np.ndarray, contaminated_windows: np.ndarray
    ) -> float:
        """B7: AUC de un clasificador que solo ve potencia total de ventana.

        AUC = P(potencia_contaminada > potencia_limpia); 0.5 indica que la
        potencia no permite separar las clases.
        """
        p_c = np.mean(clean_windows ** 2, axis=(1, 2))
        p_x = np.mean(contaminated_windows ** 2, axis=(1, 2))
        if len(p_c) == 0 or len(p_x) == 0:
            return 0.5
        # Mann-Whitney U normalizada
        all_v = np.concatenate([p_c, p_x])
        order = np.argsort(all_v, kind="mergesort")
        ranks = np.empty(len(all_v), dtype=float)
        ranks[order] = np.arange(1, len(all_v) + 1, dtype=float)
        r_x = ranks[len(p_c) :].sum()
        auc = (r_x - len(p_x) * (len(p_x) + 1) / 2.0) / (len(p_c) * len(p_x))
        return float(auc)

    def compute_ground_truth_1d(
        self,
        frequencies_hz: List[float],
        rho_ohm_m: List[float],
        interfaces_m: List[float]
    ) -> Dict[float, Dict[str, Any]]:
        """Calcula la respuesta analitica 1D exacta de Maxwell usando z1d."""
        z_scalars = z1d(frequencies_hz, rho_ohm_m, interfaces_m)
        truth = {}
        for f, z in zip(frequencies_hz, z_scalars):
            omega = 2.0 * math.pi * f
            rho_a = (abs(z) ** 2) / (MU0 * omega)
            phase_deg = math.degrees(math.atan2(z.imag, z.real))
            truth[f] = {
                "Zxy": complex(z),
                "rho_a": float(rho_a),
                "phase_deg": float(phase_deg)
            }
        return truth

    def evaluate_all(self) -> Dict[str, Any]:
        """Ejecuta la evaluacion ciega integral de extremo a extremo.

        Todas las verdades provienen de ``config_p9.json`` (fuente unica) y
        deben coincidir con el generador de Etapa 3. La compuerta P9 solo se
        aprueba si se cumplen TODOS los endpoints preregistrados y si todos los
        sondeos declarados pasan; un unico fallo bloquea la liberacion.
        """
        print("=" * 80)
        print(f"Ejecucion Ciega de Extremo a Extremo ({VERSION}) - Puerta P9 [SINTETICO]")
        print("=" * 80)

        results: Dict[str, Any] = {
            "version": VERSION,
            "timestamp_utc": "",
            "synthetic": True,
            "scientific_claim": False,
            "data_origin": "synthetic",
            "truth_model_source": self.cfg.get("truth_model_source"),
            "seed": self.seed,
            "benchmarks_evaluated": [],
            "benchmarks_not_evaluated": {},
            "soundings_results": {},
            "metrics_summary": {},
            "gate_p9_metrics": {},
            "gate_g4_safety": {},
        }

        fs = 4000.0
        freqs_test = [125.0, 150.0, 200.0, 250.0, 300.0, 400.0, 500.0, 600.0, 800.0, 1000.0]
        n_start = int(4.0 * fs)

        def errors_vs_truth(tf_list: List[Dict[str, Any]], truth: Dict[float, Dict[str, Any]]) -> Dict[str, float]:
            err_z, err_rho, err_ph = [], [], []
            for item in tf_list:
                f = item["f_hz"]
                if f in truth and item.get("Zxy") is not None:
                    z_tr = truth[f]["Zxy"]
                    err_z.append(abs(item["Zxy"] - z_tr) / abs(z_tr) * 100.0)
                    if item.get("rho_a_xy"):
                        err_rho.append(abs(math.log10(item["rho_a_xy"]) - math.log10(truth[f]["rho_a"])))
                    err_ph.append(abs(item["phase_xy_deg"] - truth[f]["phase_deg"]))
            return {
                "median_err_z_pct": float(np.median(err_z)) if err_z else 999.0,
                "median_err_rho_dec": float(np.median(err_rho)) if err_rho else 999.0,
                "median_err_phase_deg": float(np.median(err_ph)) if err_ph else 999.0,
                "p90_err_rho_dec": float(np.percentile(err_rho, 90)) if err_rho else 999.0,
                "p90_err_phase_deg": float(np.percentile(err_ph, 90)) if err_ph else 999.0,
            }

        # ---------------------------------------------------------------------
        # 1. Sondeo Ciego 1: Control Sintetico Limpio (SND-BLIND-01)
        # ---------------------------------------------------------------------
        print("\n--- 1. Sondeo Ciego 1: Limpio Fisico (CTRL-01) ---")
        d1 = np.load(_ROOT / self.cfg["blind_soundings"]["synth_clean_halfspace"]["source_file"])
        s_clean = np.stack([d1["Ex"], d1["Ey"], d1["Hx"], d1["Hy"]], axis=1).astype(np.float32)

        rho1, if1 = self.truth_model("synth_clean_halfspace")
        truth_s1 = self.compute_ground_truth_1d(freqs_test, rho1, if1)

        # Se fuerza la intervencion para medir si el denoisedor daña el limpio.
        res_pipe_clean = self.pipeline.process_continuous_record(
            s_clean, "SND-BLIND-01", "D0", fs,
            support_source=_ROOT / "banco_sintetico" / "soporte_S1.json",
            force_mode="denoise_all",
        )
        tf_clean_b0 = self.pipeline.estimate_transfer_functions(s_clean, fs, freqs_test)
        tf_clean_b4 = self.pipeline.estimate_transfer_functions(res_pipe_clean["s_hat"], fs, freqs_test)

        bias_z_pct, phase_diff_deg = [], []
        for b0, b4 in zip(tf_clean_b0, tf_clean_b4):
            if b0["Zxy"] is not None and b4["Zxy"] is not None:
                bias_z_pct.append(abs(b4["Zxy"] - b0["Zxy"]) / abs(b0["Zxy"]) * 100.0)
                phase_diff_deg.append(abs(b4["phase_xy_deg"] - b0["phase_xy_deg"]))

        p95_bias_z = float(np.percentile(bias_z_pct, 95)) if bias_z_pct else 0.0
        p95_phase_diff = float(np.percentile(phase_diff_deg, 95)) if phase_diff_deg else 0.0
        median_bias_z = float(np.median(bias_z_pct)) if bias_z_pct else 0.0
        median_phase_diff = float(np.median(phase_diff_deg)) if phase_diff_deg else 0.0

        # Error absoluto del pipeline frente a la verdad analitica
        clean_err_vs_truth = errors_vs_truth(tf_clean_b4, truth_s1)
        intervened_clean = float(res_pipe_clean["intervened_pct"])

        clean_ok = (
            p95_bias_z <= 2.0
            and p95_phase_diff <= 1.0
            and median_bias_z <= 5.0
            and median_phase_diff <= 2.0
            and intervened_clean > 0.0
        )

        print(f"  Sesgo Z vs B0: mediana={median_bias_z:.4f}% P95={p95_bias_z:.4f}% (meta P95<=2.0%)")
        print(f"  Fase vs B0: mediana={median_phase_diff:.4f}deg P95={p95_phase_diff:.4f}deg (meta P95<=1.0deg)")
        print(f"  Error absoluto vs verdad analitica: Z={clean_err_vs_truth['median_err_z_pct']:.2f}%")
        print(f"  Ventanas intervenidas en limpio: {intervened_clean:.1f}%")

        results["soundings_results"]["snd_blind_01_clean"] = {
            "median_bias_z_pct": median_bias_z,
            "p95_bias_z_pct": p95_bias_z,
            "median_phase_diff_deg": median_phase_diff,
            "p95_phase_diff_deg": p95_phase_diff,
            "intervened_pct": intervened_clean,
            "err_vs_truth": clean_err_vs_truth,
            "passed": clean_ok,
        }

        # ---------------------------------------------------------------------
        # 2. Sondeo Ciego 2: Soporte Parcial Estratificado Contaminado (SND-BLIND-02)
        # ---------------------------------------------------------------------
        print("\n--- 2. Sondeo Ciego 2: Soporte Parcial Contaminado (CTRL-03 + Ruido) ---")
        d2 = np.load(_ROOT / self.cfg["blind_soundings"]["synth_stratified_s1"]["source_file"])
        s_strat = np.stack([d2["Ex"], d2["Ey"], d2["Hx"], d2["Hy"]], axis=1).astype(np.float32)
        d_noise = np.load(_ROOT / self.cfg["blind_soundings"]["synth_stratified_s1"]["noise_source"])
        n_raw = d_noise["noise"][:, :4].astype(np.float32)

        n_len = min(len(n_raw), len(s_strat) - n_start, int(8.0 * fs))
        p_s = np.mean(s_strat[n_start : n_start + n_len] ** 2)
        p_n = np.mean(n_raw[:n_len] ** 2) + 1e-12
        scale_n = math.sqrt((p_s / 1.0) / p_n)  # SNR = 0 dB

        x_contam = s_strat.copy()
        x_contam[n_start : n_start + n_len] += n_raw[:n_len] * scale_n

        supp_s1_path = _ROOT / self.cfg["blind_soundings"]["synth_stratified_s1"]["support_file"]
        rho2, if2 = self.truth_model("synth_stratified_s1")
        truth_s2 = self.compute_ground_truth_1d(freqs_test, rho2, if2)

        print("  Evaluando comparadores B0, B1, B3, B4, B7, B8, B10...")
        tf_b0 = self.pipeline.estimate_transfer_functions(x_contam, fs, freqs_test)
        tf_b1 = self.run_benchmark_b1_spectral(x_contam, fs, freqs_test)
        tf_b3 = self.run_benchmark_b3_scnet18(x_contam, fs, freqs_test)

        res_b4 = self.pipeline.process_continuous_record(
            x_contam, "SND-BLIND-02", "D0", fs,
            support_source=supp_s1_path,
        )
        tf_b4 = self.pipeline.estimate_transfer_functions(res_b4["s_hat"], fs, freqs_test)

        # Variante forzada (estres): mide el daño del separador cuando actua
        # sobre todas las ventanas, con independencia del detector.
        res_b4_forced = self.pipeline.process_continuous_record(
            x_contam, "SND-BLIND-02-FORCED", "D0", fs,
            support_source=supp_s1_path, force_mode="denoise_all",
        )
        tf_b4_forced = self.pipeline.estimate_transfer_functions(res_b4_forced["s_hat"], fs, freqs_test)
        b4_forced_errors = errors_vs_truth(tf_b4_forced, truth_s2)

        tf_b8 = self.run_benchmark_b8_wiener(
            x_contam, fs, freqs_test,
            clean_reference=x_contam[:n_start],
            noise_reference=n_raw[:n_len] * scale_n,
        )
        tf_b10 = self.pipeline.estimate_transfer_functions(s_strat, fs, freqs_test)  # Oraculo

        benchmark_tfs = {"B0": tf_b0, "B1": tf_b1, "B3": tf_b3, "B4": tf_b4, "B8": tf_b8, "B10": tf_b10}
        benchmark_errors: Dict[str, Dict[str, float]] = {
            b_id: errors_vs_truth(tf_list, truth_s2) for b_id, tf_list in benchmark_tfs.items()
        }

        # B7: control de atajo por potencia (AUC sobre ventanas de este registro)
        clean_w = self._windows(x_contam[:n_start])
        contam_w = self._windows(x_contam[n_start : n_start + n_len])
        b7_auc = self.run_benchmark_b7_power(clean_w, contam_w)

        # B9: familia de ruido independiente (NOISE-D0-003)
        b9_err = {"B0": {}, "B4": {}}
        b9_source = self.cfg["blind_soundings"]["synth_stratified_s1"].get("independent_noise_source")
        if b9_source and (_ROOT / b9_source).exists():
            n3 = np.load(_ROOT / b9_source)["noise"][:, :4].astype(np.float32)
            n3_len = min(len(n3), len(s_strat) - n_start, int(8.0 * fs))
            p3 = np.mean(n3[:n3_len] ** 2) + 1e-12
            x_b9 = s_strat.copy()
            x_b9[n_start : n_start + n3_len] += n3[:n3_len] * math.sqrt(p_s / p3)
            res_b9 = self.pipeline.process_continuous_record(
                x_b9, "SND-BLIND-09", "D0", fs,
                support_source=supp_s1_path, force_mode="denoise_all",
            )
            b9_err["B0"] = errors_vs_truth(
                self.pipeline.estimate_transfer_functions(x_b9, fs, freqs_test), truth_s2
            )
            b9_err["B4"] = errors_vs_truth(
                self.pipeline.estimate_transfer_functions(res_b9["s_hat"], fs, freqs_test), truth_s2
            )

        for bid, m in benchmark_errors.items():
            print(f"    {bid:4s} -> Err Z={m['median_err_z_pct']:6.2f}% | Err Rho={m['median_err_rho_dec']:6.4f} dec | Err Fase={m['median_err_phase_deg']:5.2f}deg")
        print(f"    B7  -> AUC solo-potencia = {b7_auc:.4f} (meta <= 0.65)")

        b0_z = benchmark_errors["B0"]["median_err_z_pct"]
        b4_z = benchmark_errors["B4"]["median_err_z_pct"]
        b8_z = benchmark_errors["B8"]["median_err_z_pct"]
        imp_vs_b0 = ((b0_z - b4_z) / (b0_z + 1e-12)) * 100.0
        imp_vs_b8 = ((b8_z - b4_z) / (b8_z + 1e-12)) * 100.0

        endpoints = self.cfg["preregistered_endpoints"]["contaminated_recovery"]
        rec_rho = benchmark_errors["B4"]["median_err_rho_dec"]
        rec_ph = benchmark_errors["B4"]["median_err_phase_deg"]
        rec_p90_rho = benchmark_errors["B4"]["p90_err_rho_dec"]
        rec_p90_ph = benchmark_errors["B4"]["p90_err_phase_deg"]

        recovery_ok = (
            rec_rho <= endpoints["median_bias_log10_rho_max"]
            and rec_ph <= endpoints["median_phase_diff_deg_max"]
            and rec_p90_rho <= endpoints["p90_bias_log10_rho_max"]
            and rec_p90_ph <= endpoints["p90_phase_diff_deg_max"]
            and imp_vs_b0 >= endpoints["min_impedance_improvement_pct"]
        )
        b7_ok = b7_auc <= 0.65
        b9_ok = bool(b9_err["B4"]) and b9_err["B4"]["median_err_z_pct"] <= b9_err["B0"]["median_err_z_pct"]

        print(f"  Mejora B4 vs B0 (Raw): {imp_vs_b0:.2f}% (meta >= {endpoints['min_impedance_improvement_pct']}%)")
        print(f"  Mejora B4 vs B8 (Wiener): {imp_vs_b8:.2f}%")

        results["soundings_results"]["snd_blind_02_stratified"] = {
            "truth_model": {"rho_ohm_m": rho2, "interfaces_m": if2},
            "benchmark_errors": benchmark_errors,
            "b7_power_auc": b7_auc,
            "b9_independent_noise": b9_err,
            "improvement_vs_b0_pct": imp_vs_b0,
            "improvement_vs_b8_pct": imp_vs_b8,
            "b4_forced_error": b4_forced_errors,
            "b4_intervened_pct": float(res_b4["intervened_pct"]),
            "recovery_ok": recovery_ok,
            "b7_ok": b7_ok,
            "b9_ok": b9_ok,
            "passed": recovery_ok and b7_ok and b9_ok,
        }

        # ---------------------------------------------------------------------
        # 3. Sondeo Ciego 3: No Estacionario con Sferics (SND-BLIND-03)
        # ---------------------------------------------------------------------
        print("\n--- 3. Sondeo Ciego 3: Rafagas No Estacionarias (CTRL-05) ---")
        d3 = np.load(_ROOT / self.cfg["blind_soundings"]["synth_nonstationary_sferics"]["source_file"])
        s_sferics = np.stack([d3["Ex"], d3["Ey"], d3["Hx"], d3["Hy"]], axis=1).astype(np.float32)

        p_sferic = np.mean(s_sferics[n_start : n_start + n_len] ** 2)
        scale_sferic = math.sqrt((p_sferic / (10.0 ** (-2.4 / 10.0))) / p_n)
        x_sferics_contam = s_sferics.copy()
        x_sferics_contam[n_start : n_start + n_len] += n_raw[:n_len] * scale_sferic

        res_sferics = self.pipeline.process_continuous_record(
            x_sferics_contam, "SND-BLIND-03", "D0", fs, support_source=supp_s1_path
        )

        tf_sf_clean = self.pipeline.estimate_transfer_functions(s_sferics, fs, freqs_test)
        tf_sf_b0 = self.pipeline.estimate_transfer_functions(x_sferics_contam, fs, freqs_test)
        tf_sf_b4 = self.pipeline.estimate_transfer_functions(res_sferics["s_hat"], fs, freqs_test)

        err_sf_b0, err_sf_b4 = [], []
        for c, r, b in zip(tf_sf_clean, tf_sf_b0, tf_sf_b4):
            if c["Zxy"] is not None and r["Zxy"] is not None and b["Zxy"] is not None:
                err_sf_b0.append(abs(r["Zxy"] - c["Zxy"]) / abs(c["Zxy"]) * 100.0)
                err_sf_b4.append(abs(b["Zxy"] - c["Zxy"]) / abs(c["Zxy"]) * 100.0)

        mean_err_sf_b0 = float(np.mean(err_sf_b0)) if err_sf_b0 else 999.0
        mean_err_sf_b4 = float(np.mean(err_sf_b4)) if err_sf_b4 else 999.0
        sferics_ok = mean_err_sf_b4 <= min(mean_err_sf_b0, 5.0)

        print(f"  Error medio Zxy en rafagas: B0={mean_err_sf_b0:.2f}%, B4={mean_err_sf_b4:.2f}%")
        results["soundings_results"]["snd_blind_03_sferics"] = {
            "mean_err_z_b0_pct": mean_err_sf_b0,
            "mean_err_z_b4_pct": mean_err_sf_b4,
            "intervened_pct": float(res_sferics["intervened_pct"]),
            "passed": sferics_ok,
        }

        # ---------------------------------------------------------------------
        # 4. Sondeo Ciego 4: Estres de Textura F1 (SND-BLIND-04)
        # ---------------------------------------------------------------------
        print("\n--- 4. Sondeo Ciego 4: Estres de Textura F1 (Sim-to-Real) ---")
        d_noise2 = np.load(_ROOT / self.cfg["blind_soundings"]["field_texture_stress_f1"]["noise_source"])
        n_raw2 = d_noise2["noise"][:, :4].astype(np.float32)
        scale_n2 = math.sqrt((p_s / (10.0 ** (3.0 / 10.0))) / (np.mean(n_raw2[:n_len] ** 2) + 1e-12))
        x_f1 = s_strat.copy()
        x_f1[n_start : n_start + n_len] += n_raw2[:n_len] * scale_n2

        res_f1 = self.pipeline.process_continuous_record(
            x_f1, "SND-BLIND-04", "D0", fs,
            support_source=supp_s1_path, force_mode="denoise_all",
        )
        diff_f1_clean_prefix = float(np.max(np.abs(res_f1["s_hat"][:n_start] - s_strat[:n_start])))
        intervened_f1 = float(res_f1["intervened_pct"])
        texture_ok = diff_f1_clean_prefix < 1.0 and intervened_f1 > 0.0

        print(f"  Preservacion de textura en tramo limpio: diff={diff_f1_clean_prefix:.2e} (meta <1.0)")
        print(f"  Ventanas intervenidas: {intervened_f1:.1f}%")
        results["soundings_results"]["snd_blind_04_texture_f1"] = {
            "clean_texture_preserved_diff": diff_f1_clean_prefix,
            "intervened_pct": intervened_f1,
            "passed": texture_ok,
        }

        # ---------------------------------------------------------------------
        # 5. Sondeos Ciegos 5 a 8: No Identificables
        # ---------------------------------------------------------------------
        print("\n--- 5. Sondeos Ciegos 5 a 8: No Identificables y Falsa Recuperacion ---")
        false_recovery_cases = 0
        total_non_id_cases = 4

        d_r1 = np.load(_ROOT / self.cfg["blind_soundings"]["non_identifiable_rank1"]["source_file"])
        x_r1 = np.stack([d_r1["Ex"], d_r1["Ey"], d_r1["Hx"], d_r1["Hy"]], axis=1).astype(np.float32)
        tf_r1 = self.pipeline.estimate_transfer_functions(x_r1, fs, [125.0, 250.0, 500.0])
        r1_abstained = all(x["status"] == "rango_1_abstencion" for x in tf_r1)
        if not r1_abstained:
            false_recovery_cases += 1
        print(f"  Rango 1 (CTRL-04): {'ABSTENCION EXITOSA' if r1_abstained else 'FALSA RECUPERACION'}")

        d_adc = np.load(_ROOT / self.cfg["blind_soundings"]["non_identifiable_adc_sat"]["source_file"])
        x_adc = np.stack([d_adc["Ex"], d_adc["Ey"], d_adc["Hx"], d_adc["Hy"]], axis=1).astype(np.float32)
        res_adc = self.pipeline.process_continuous_record(x_adc, "SND-BLIND-06", "D0", fs)
        adc_safe = res_adc is not None and (
            res_adc.get("network_omitted", False)
            or res_adc.get("support_status") in ("no_identificable", "senal_insuficiente")
            or res_adc.get("intervened_pct", 0.0) == 0.0
        )
        if not adc_safe:
            false_recovery_cases += 1
        print(f"  Saturacion ADC (CTRL-06): {'SEGURO' if adc_safe else 'FALSA RECUPERACION'}")

        res_empty = self.pipeline.resolve_support("ARMT5-123-01-01-01", "D0")
        empty_safe = res_empty["network_omitted"] and res_empty["support_status"] == "soporte_vacio"
        if not empty_safe:
            false_recovery_cases += 1
        print(f"  Soporte Vacio (ARMT5-123): {'RED OMITIDA' if empty_safe else 'FALSA RECUPERACION'}")

        rmt_signal = np.random.RandomState(self.seed).randn(2048, 4)
        res_rmt = self.pipeline.process_continuous_record(rmt_signal, "SND-BLIND-08", "D2", 400000.0)
        rmt_safe = res_rmt["network_omitted"] and res_rmt["support_status"] == "excluido_rmt"
        if not rmt_safe:
            false_recovery_cases += 1
        print(f"  Exclusion RMT (D2): {'BLOQUEO ABSOLUTO' if rmt_safe else 'FALSA RECUPERACION'}")

        false_recovery_rate = (false_recovery_cases / total_non_id_cases) * 100.0
        non_id_ok = false_recovery_rate <= self.cfg["preregistered_endpoints"]["non_identifiable_rejection"]["max_false_recovery_rate_pct"]

        results["soundings_results"]["non_identifiable_tests"] = {
            "rank1_abstained": r1_abstained,
            "adc_safe": adc_safe,
            "empty_support_omitted": empty_safe,
            "rmt_excluded": rmt_safe,
            "false_recovery_rate_pct": false_recovery_rate,
            "passed": non_id_ok,
        }

        # ---------------------------------------------------------------------
        # 6. Comparadores no implementados (se declaran, no se omiten)
        # ---------------------------------------------------------------------
        implemented_ids = {"B0", "B1", "B3", "B4", "B7", "B8", "B9", "B10"}
        mandatory = self.cfg.get("mandatory_benchmarks", sorted(implemented_ids))
        for b in self.cfg.get("benchmarks", []):
            if b["id"] not in implemented_ids:
                results["benchmarks_not_evaluated"][b["id"]] = b.get(
                    "not_implemented_reason", "No implementado en esta version"
                )
        results["benchmarks_evaluated"] = sorted(implemented_ids)
        missing_mandatory = [b for b in mandatory if b not in implemented_ids]

        # ---------------------------------------------------------------------
        # 7. Compuerta P9 y G4 (propagacion estricta de fallos)
        # ---------------------------------------------------------------------
        sounding_flags = {
            k: bool(v.get("passed", False))
            for k, v in results["soundings_results"].items()
        }
        all_soundings_ok = all(sounding_flags.values())

        p9_passed = bool(
            all_soundings_ok
            and recovery_ok
            and b7_ok
            and b9_ok
            and non_id_ok
            and not missing_mandatory
        )
        g4_approved = bool(
            p9_passed
            and clean_ok
            and false_recovery_rate <= 5.0
        )

        print("\n" + "=" * 80)
        print("Evaluacion de Compuerta de Seguridad G4:")
        print(f"  - No inferioridad en limpio: {'PASA' if clean_ok else 'FALLA'} (P95 Z={p95_bias_z:.3f}%, P95 fase={p95_phase_diff:.3f}deg)")
        print(f"  - Recuperacion contaminada: {'PASA' if recovery_ok else 'FALLA'} (rho={rec_rho:.4f} dec, fase={rec_ph:.2f}deg, mejora={imp_vs_b0:.1f}%)")
        print(f"  - Control de atajo B7: {'PASA' if b7_ok else 'FALLA'} (AUC={b7_auc:.4f})")
        print(f"  - Familia de ruido independiente B9: {'PASA' if b9_ok else 'FALLA'}")
        print(f"  - Tasa de falsa recuperacion: {'PASA' if non_id_ok else 'FALLA'} ({false_recovery_rate:.1f}%)")
        print(f"  - Sondeos: {sounding_flags}")
        print(f"  - Comparadores obligatorios faltantes: {missing_mandatory or 'ninguno'}")
        print(f"  => ESTADO PUERTA P9: {'APROBADO' if p9_passed else 'BLOQUEADO'}")
        print(f"  => ESTADO COMPUERTA G4: {'APROBADO' if g4_approved else 'BLOQUEADO'}")
        print("=" * 80)

        results["gate_g4_safety"] = {
            "no_inferiority_passed": clean_ok,
            "improvement_passed": recovery_ok,
            "rejection_passed": non_id_ok,
            "b7_passed": b7_ok,
            "b9_passed": b9_ok,
            "all_soundings_passed": all_soundings_ok,
            "missing_mandatory_benchmarks": missing_mandatory,
            "g4_approved": g4_approved,
        }
        results["gate_p9_metrics"] = {
            "clean_p95_bias_z_pct": p95_bias_z,
            "clean_p95_phase_diff_deg": p95_phase_diff,
            "stratified_median_err_rho_dec": rec_rho,
            "stratified_median_err_phase_deg": rec_ph,
            "stratified_p90_err_rho_dec": rec_p90_rho,
            "stratified_p90_err_phase_deg": rec_p90_ph,
            "improvement_vs_b0_pct": imp_vs_b0,
            "improvement_required_pct": endpoints["min_impedance_improvement_pct"],
            "b7_power_auc": b7_auc,
            "false_recovery_rate_pct": false_recovery_rate,
            "p9_passed": p9_passed,
        }
        results["metrics_summary"] = {
            "truth_model": {"rho_ohm_m": rho2, "interfaces_m": if2},
            "clean_error_vs_truth": clean_err_vs_truth,
            "b4_error_vs_truth": benchmark_errors["B4"],
            "b0_error_vs_truth": benchmark_errors["B0"],
            "b8_error_vs_truth": benchmark_errors["B8"],
            "b9_independent_noise": b9_err,
        }

        return results
