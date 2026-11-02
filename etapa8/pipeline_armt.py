#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pipeline de Inferencia MT/AMT Continua con Soporte Parcial (Etapa 8 - Puerta P8).

Implementa la integracion del preprocesamiento, resolucion de soporte F_aplicacion,
exclusion estricta de RMT (D2/D3), ventaneo con recomposicion continua por Hanning
overlap-add (continuidad C1 sin transitorios de costura), cadena condicional C_theta -> D_psi,
guardas temporales y estimacion espectral robusta de impedancia Z(f).
"""
from __future__ import annotations

import os
import sys
import json
import math
import hashlib

# Solucion al conflicto de bibliotecas OpenMP en Windows
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

import numpy as np
import torch

# Asegurar path raiz para imports de modulos
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from etapa7.modelos_cbam import SCNet18_Classifier, CBAM_ResUNet_Denoiser

VERSION = "P8-PIPE-1.0.0"
MU0 = 4.0e-7 * math.pi


class RMTExclusionError(ValueError):
    """Excepcion emitida cuando se intenta aplicar la red CBAM a bandas RMT (D2/D3)."""
    pass


class ARMTPipeline:
    """Motor integral de inferencia MT/AMT continua con soporte parcial y compuertas de seguridad."""

    def __init__(
        self,
        config_path: Union[str, Path] = "etapa8/config_p8.json",
        device: Optional[str] = None
    ) -> None:
        self.config_path = Path(config_path)
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.cfg = json.load(f)

        # Seleccion de dispositivo
        if device is None:
            pref = self.cfg["models"].get("device_preference", "cuda")
            self.device = torch.device("cuda" if torch.cuda.is_available() and pref == "cuda" else "cpu")
        else:
            self.device = torch.device(device)

        # Carga de modelos
        self.detector = None
        self.denoiser = None
        self.detector_tau = float(self.cfg["models"].get("detector_tau", 1.0))
        self.batch_size = int(self.cfg["models"].get("batch_size", 32))
        self._load_checkpoints()

        # Configuracion de ventaneo
        self.reconstruction_cfg = self.cfg["reconstruction"]
        self.window_length = int(self.reconstruction_cfg.get("window_length", 256))
        self.step = int(self.reconstruction_cfg.get("step", 128))
        self.temporal_guard_sec = float(self.reconstruction_cfg.get("temporal_guard_sec", 0.5))

    def _load_checkpoints(self) -> None:
        """Carga y valida los checkpoints de la Etapa 7."""
        det_ckpt = Path(self.cfg["models"]["detector_checkpoint"])
        den_ckpt = Path(self.cfg["models"]["denoiser_checkpoint"])

        if not det_ckpt.exists() or not den_ckpt.exists():
            raise FileNotFoundError(f"Checkpoints no encontrados: {det_ckpt} o {den_ckpt}")

        self.detector = SCNet18_Classifier(in_channels=4, num_classes=2)
        det_state = torch.load(det_ckpt, map_location=self.device, weights_only=True)
        self.detector.load_state_dict(det_state)
        self.detector.to(self.device)
        self.detector.eval()

        self.denoiser = CBAM_ResUNet_Denoiser(in_channels=4, base_channels=32)
        den_state = torch.load(den_ckpt, map_location=self.device, weights_only=True)
        self.denoiser.load_state_dict(den_state)
        self.denoiser.to(self.device)
        self.denoiser.eval()

    def resolve_support(
        self,
        record_id: str,
        band: str,
        support_source: Optional[Union[str, Path, Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Resuelve F_aplicacion y el estado de soporte TEM antes de procesar."""
        # Regla 8.3: Exclusion estricta de bandas RMT
        if band in self.cfg["excluded_bands"]:
            return {
                "record_id": record_id,
                "band": band,
                "support_status": "excluido_rmt",
                "f_aplicacion": [],
                "network_omitted": True,
                "reason": f"Banda {band} excluida de CBAM MT/AMT por diseno fisico (Plan v1.3 §8.3)"
            }

        # Si se provee soporte explicito (p. ej. json de banco sintetico)
        if support_source is not None:
            if isinstance(support_source, (str, Path)):
                s_path = Path(support_source)
                if s_path.exists():
                    with open(s_path, "r", encoding="utf-8") as f:
                        s_data = json.load(f)
                else:
                    s_data = {}
            elif isinstance(support_source, dict):
                s_data = support_source
            else:
                s_data = {}

            freqs_hab = []
            for item in s_data.get("frequencies", []):
                if item.get("band") == band:
                    app = item.get("aplicacion", "no_habilitada")
                    st = item.get("status", "no_respaldada")
                    if app == "habilitada" or st == "respaldada":
                        freqs_hab.append(float(item["f_hz"]))

            if len(freqs_hab) > 0:
                return {
                    "record_id": record_id,
                    "band": band,
                    "support_status": "soporte_parcial" if len(freqs_hab) < len(s_data.get("frequencies", [])) else "soporte_completo",
                    "f_aplicacion": sorted(freqs_hab),
                    "network_omitted": False,
                    "n_frequencies": len(freqs_hab)
                }
            else:
                return {
                    "record_id": record_id,
                    "band": band,
                    "support_status": "soporte_vacio",
                    "f_aplicacion": [],
                    "network_omitted": True,
                    "reason": "Compuerta G0: Soporte TEM vacio o no habilitado para la subbanda"
                }

        # Fallback al catalogo TEM etapa2/tem_amt_support.csv
        cat_path = Path(self.cfg["support_resolution"]["tem_support_catalog"])
        if cat_path.exists():
            import csv
            freqs_hab = []
            with open(cat_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("record_id") == record_id and row.get("band") == band:
                        st = row.get("estado", "")
                        if st == "respaldada":
                            freqs_hab.append(float(row["frequency_hz"]))

            if len(freqs_hab) > 0:
                return {
                    "record_id": record_id,
                    "band": band,
                    "support_status": "soporte_parcial",
                    "f_aplicacion": sorted(freqs_hab),
                    "network_omitted": False,
                    "n_frequencies": len(freqs_hab)
                }

        # Si no hay soporte verificado (caso de campo actual)
        return {
            "record_id": record_id,
            "band": band,
            "support_status": "soporte_vacio",
            "f_aplicacion": [],
            "network_omitted": True,
            "reason": "Compuerta G0: Ausencia de vinculo TEM certificado (B-P0-03)"
        }

    @staticmethod
    def hann_window(length: int) -> np.ndarray:
        """Genera una ventana Hann periodica para analisis/sintesis."""
        n = np.arange(int(length), dtype=float)
        return 0.5 - 0.5 * np.cos(2.0 * math.pi * (n + 0.5) / float(length))

    def reconstruct_overlap_add(
        self,
        windows: np.ndarray,
        total_samples: int,
        step: Optional[int] = None
    ) -> np.ndarray:
        """Reconstruye una serie continua multicanal a partir de ventanas solapadas con Hann.

        Parametros:
            windows: Arreglo (M, L, C) de ventanas.
            total_samples: Longitud total N de la serie a reconstruir.
            step: Paso de avance S (por defecto self.step = 128).

        Retorna:
            Arreglo continuo reconstruido (N, C).
        """
        M, L, C = windows.shape
        S = step or self.step
        taper = self.hann_window(L)

        output = np.zeros((total_samples, C), dtype=float)
        weight_sum = np.zeros(total_samples, dtype=float)

        for i in range(M):
            start = i * S
            end = start + L
            if end > total_samples:
                # Truncar si la ultima ventana se pasa del registro
                valid_len = total_samples - start
                w_taper = taper[:valid_len, None]
                output[start:total_samples] += windows[i, :valid_len] * w_taper
                weight_sum[start:total_samples] += taper[:valid_len]
            else:
                w_taper = taper[:, None]
                output[start:end] += windows[i] * w_taper
                weight_sum[start:end] += taper

        # Normalizacion por la suma de pesos para garantizar particion de la unidad
        mask = weight_sum > 1e-12
        output[mask] /= weight_sum[mask, None]
        return output

    def process_continuous_record(
        self,
        x_continuous: np.ndarray,
        record_id: str,
        band: str,
        fs_hz: float,
        support_source: Optional[Union[str, Path, Dict[str, Any]]] = None,
        force_mode: Optional[str] = None,  # 'auto', 'raw_only', 'denoise_all'
        batch_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """Procesa un registro temporal continuo aplicando la cadena condicional y soporte.

        Parametros:
            x_continuous: Arreglo (N, 4) o (N, C) con canales [Ex, Ey, Hx, Hy].
            record_id: Identificador del sondeo/registro.
            band: 'D0', 'D1', 'D2', 'D3'.
            fs_hz: Frecuencia de muestreo en Hz.
            support_source: Fuente de soporte TEM para resolver F_aplicacion.
            force_mode: Opcion para pruebas ('auto' por defecto, 'raw_only', 'denoise_all').
            batch_size: Tamano de lote para evaluar invarianza (por defecto self.batch_size).

        Retorna:
            Diccionario estructurado con s_hat, n_hat, diagnosticos y metadatos.
        """
        N, C = x_continuous.shape
        bs = batch_size or self.batch_size

        # 1. Regla 8.3: Exclusion estricta de bandas RMT
        if band in self.cfg["excluded_bands"]:
            return {
                "record_id": record_id,
                "band": band,
                "support_status": "excluido_rmt",
                "network_omitted": True,
                "s_hat": x_continuous.copy(),
                "n_hat": np.zeros_like(x_continuous),
                "intervened_windows": 0,
                "total_windows": 0,
                "intervened_pct": 0.0,
                "f_aplicacion": [],
                "reason": f"Banda {band} excluida de CBAM MT/AMT por diseno fisico"
            }

        # 2. Resolucion de soporte TEM
        support_info = self.resolve_support(record_id, band, support_source)

        # Regla 8.6: Si el soporte esta vacio, omitir la red
        if support_info.get("network_omitted", False) and force_mode != "denoise_all":
            return {
                "record_id": record_id,
                "band": band,
                "support_status": support_info.get("support_status", "soporte_vacio"),
                "network_omitted": True,
                "s_hat": x_continuous.copy(),
                "n_hat": np.zeros_like(x_continuous),
                "intervened_windows": 0,
                "total_windows": 0,
                "intervened_pct": 0.0,
                "f_aplicacion": support_info.get("f_aplicacion", []),
                "reason": support_info.get("reason", "Compuerta G0 activada: soporte vacio")
            }

        # 3. Ventaneo de la serie temporal (L=256, S=128)
        L = self.window_length
        S = self.step
        windows = []
        start_indices = []

        start = 0
        while start + L <= N:
            windows.append(x_continuous[start : start + L, :4])
            start_indices.append(start)
            start += S

        total_windows = len(windows)
        if total_windows == 0:
            return {
                "record_id": record_id,
                "band": band,
                "support_status": support_info.get("support_status"),
                "network_omitted": True,
                "s_hat": x_continuous.copy(),
                "n_hat": np.zeros_like(x_continuous),
                "reason": f"Registro demasiado corto ({N} muestras < L={L})"
            }

        windows_arr = np.array(windows, dtype=np.float32)  # (M, L, 4)
        processed_windows = np.zeros_like(windows_arr)

        # 4. Inferencia por lotes
        intervened_flags = []

        with torch.no_grad():
            for i in range(0, total_windows, bs):
                batch_win = windows_arr[i : i + bs]  # (B, L, 4)
                # Formato PyTorch: (B, C, L)
                x_tensor = torch.from_numpy(batch_win).permute(0, 2, 1).to(self.device)

                if force_mode == "raw_only":
                    is_contaminated = np.zeros(len(batch_win), dtype=bool)
                elif force_mode == "denoise_all":
                    is_contaminated = np.ones(len(batch_win), dtype=bool)
                else:
                    # Inferencia del detector C_theta
                    det_logits = self.detector(x_tensor)
                    det_probs = torch.softmax(det_logits, dim=-1)[:, 1].cpu().numpy()
                    is_contaminated = det_probs >= self.detector_tau

                # Guardar flags
                intervened_flags.extend(is_contaminated.tolist())

                # Separacion condicional vectorizada
                contam_local_indices = [j for j, contam in enumerate(is_contaminated) if contam]
                if len(contam_local_indices) > 0:
                    contam_tensors = x_tensor[contam_local_indices]  # (K, 4, L)
                    pred_dict = self.denoiser(contam_tensors)
                    s_preds = pred_dict["s_hat"].permute(0, 2, 1).cpu().numpy()  # (K, L, 4)
                    for idx_k, j in enumerate(contam_local_indices):
                        processed_windows[i + j] = s_preds[idx_k]

                clean_local_indices = [j for j, contam in enumerate(is_contaminated) if not contam]
                for j in clean_local_indices:
                    processed_windows[i + j] = batch_win[j]

        # 5. Recomposicion continua por Hanning Overlap-Add
        s_hat = self.reconstruct_overlap_add(processed_windows, N, S)

        # Si el array original tenia canales extra (p. ej. Hz), conservarlos intactos
        if C > 4:
            s_hat_full = np.zeros_like(x_continuous)
            s_hat_full[:, :4] = s_hat
            s_hat_full[:, 4:] = x_continuous[:, 4:]
            s_hat = s_hat_full

        # 6. Residual exacto
        n_hat = x_continuous - s_hat

        n_intervened = sum(intervened_flags)
        intervened_pct = (n_intervened / total_windows) * 100.0 if total_windows > 0 else 0.0

        return {
            "record_id": record_id,
            "band": band,
            "support_status": support_info.get("support_status", "desconocido"),
            "network_omitted": False,
            "total_windows": total_windows,
            "intervened_windows": n_intervened,
            "intervened_pct": intervened_pct,
            "intervened_flags": intervened_flags,
            "f_aplicacion": support_info.get("f_aplicacion", []),
            "s_hat": s_hat,
            "n_hat": n_hat
        }

    def estimate_transfer_functions(
        self,
        time_series: np.ndarray,
        fs_hz: float,
        target_frequencies: List[float],
        half_width_rel: float = 0.05,
        huber_c: float = 1.345,
        max_cond_rank2: float = 1000.0,
        rank1_threshold: float = 10000.0
    ) -> List[Dict[str, Any]]:
        """Calcula el tensor Z(f), rho_a, fase y coherencia con M-estimador robusto de Etapa 6.

        Parametros:
            time_series: Arreglo (N, 4) con [Ex, Ey, Hx, Hy].
            fs_hz: Frecuencia de muestreo en Hz.
            target_frequencies: Frecuencias autorizadas en F_aplicacion.
            half_width_rel: Semiancho relativo de banda espectral.

        Retorna:
            Lista de diccionarios con estimaciones fisicas por frecuencia.
        """
        N, C = time_series.shape
        guard_samples = int(self.temporal_guard_sec * fs_hz)

        # Descartar guardas temporales de borde
        if 2 * guard_samples < N:
            ts_core = time_series[guard_samples : N - guard_samples]
        else:
            ts_core = time_series

        N_core = len(ts_core)
        L = self.window_length
        S = self.step
        taper = self.hann_window(L)

        # Cortar ventanas de analisis con detrend lineal
        windows = []
        start = 0
        while start + L <= N_core:
            w = ts_core[start : start + L, :4]
            # Detrend lineal
            t = np.arange(L, dtype=float) - 0.5 * (L - 1)
            t2 = float(np.dot(t, t))
            mean = w.mean(axis=0, keepdims=True)
            slope = np.einsum("lc,l->c", w, t)[None, :] / t2
            w_dt = (w - mean - slope * t[:, None]) * taper[:, None]
            windows.append(w_dt)
            start += S

        if len(windows) < 4:
            return []

        win_arr = np.array(windows, dtype=float)  # (W, L, 4)
        spectra = np.fft.rfft(win_arr, axis=1)  # (W, Bins, 4)
        df = fs_hz / L

        results = []

        for f_target in target_frequencies:
            # Bins correspondientes a la frecuencia
            lo = max(1.0, f_target * (1.0 - half_width_rel))
            hi = f_target * (1.0 + half_width_rel)
            k0 = max(1, int(math.ceil(lo / df - 1e-9)))
            k1 = min(L // 2, int(math.floor(hi / df + 1e-9)))
            if k1 < k0:
                k = min(max(int(round(f_target / df)), 1), L // 2)
                bins = np.array([k], dtype=int)
            else:
                bins = np.arange(k0, k1 + 1, dtype=int)

            # Extraer e y h
            e = spectra[:, bins, 0:2]  # (W, n_bins, 2)
            h = spectra[:, bins, 2:4]  # (W, n_bins, 2)

            # Matrices 2x2 por ventana: EE, EH, HH
            ee = np.einsum("wbi,wbj->wij", e, e.conj())
            hh = np.einsum("wbi,wbj->wij", h, h.conj())
            eh = np.einsum("wbi,wbj->wij", e, h.conj())

            # Promedios iniciales
            HH_bar = hh.mean(axis=0)
            EH_bar = eh.mean(axis=0)
            EE_bar = ee.mean(axis=0)

            # Rango y condicion de HH
            s_vals = np.linalg.svd(HH_bar, compute_uv=False)
            cond_hh = float(s_vals[0] / (s_vals[1] + 1e-30))

            if cond_hh > rank1_threshold:
                # Abstencion por Rango 1
                results.append({
                    "f_hz": f_target,
                    "status": "rango_1_abstencion",
                    "cond_hh": cond_hh,
                    "Zxx": None, "Zxy": None, "Zyx": None, "Zyy": None,
                    "rho_a_xy": None, "phase_xy_deg": None,
                    "coherence_xy": None,
                    "message": "Condicion HH > 1e4: campo horizontal linealmente polarizado"
                })
                continue

            # Resolucion por inversion hermitica
            try:
                HH_inv = np.linalg.pinv(HH_bar)
                Z_init = EH_bar @ HH_inv  # (2, 2)
            except Exception:
                continue

            # M-estimador con Huber sobre residuales
            Z = Z_init.copy()
            weights = np.ones(len(windows), dtype=float)

            for _ in range(3):
                res = e - np.einsum("ij,wbj->wbi", Z, h)
                res_norm = np.sqrt(np.sum(np.abs(res) ** 2, axis=(1, 2)) + 1e-30)
                scale = np.median(res_norm) / 0.6745 + 1e-30
                u = res_norm / scale
                w_huber = np.where(u <= huber_c, 1.0, huber_c / (u + 1e-30))
                weights = w_huber / (w_huber.mean() + 1e-30)

                # Actualizar Z reponderado
                EH_w = np.einsum("w,wij->ij", weights, eh)
                HH_w = np.einsum("w,wij->ij", weights, hh)
                Z = EH_w @ np.linalg.pinv(HH_w)

            # Coherencia Ex-Hy
            S_ExHy = EH_bar[0, 1]
            S_ExEx = EE_bar[0, 0].real
            S_HyHy = HH_bar[1, 1].real
            coh_xy = float(abs(S_ExHy) ** 2 / (S_ExEx * S_HyHy + 1e-30))

            # Resistividad aparente y fase
            omega = 2.0 * math.pi * f_target
            Zxy = Z[0, 1]
            rho_a_xy = float(abs(Zxy) ** 2 / (omega * MU0)) if omega > 0 else 0.0
            phase_xy_deg = float(math.atan2(Zxy.imag, Zxy.real) * 180.0 / math.pi)

            results.append({
                "f_hz": f_target,
                "status": "estimada",
                "cond_hh": cond_hh,
                "Zxx": complex(Z[0, 0]),
                "Zxy": complex(Z[0, 1]),
                "Zyx": complex(Z[1, 0]),
                "Zyy": complex(Z[1, 1]),
                "rho_a_xy": rho_a_xy,
                "phase_xy_deg": phase_xy_deg,
                "coherence_xy": coh_xy
            })

        return results
