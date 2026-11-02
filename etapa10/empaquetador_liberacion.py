#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Empaquetador de Liberacion Oficial y Trazabilidad MT/AMT (Etapa 10 - Puerta P10).

Implementa la exportacion estandar SEG-EDI para magnetotelurica (Wight, 1988),
el formato extendido JSON-COV con covarianzas completas 4x4, trazabilidad
criptografica, clasificacion formal de puntos segun la politica de seis categorias
(aceptado, condicional, direccional, sin_soporte_tem, fuera_de_dominio_rmt, no_identificable)
y el mecanismo de reversion segura a la referencia clasica B0 (fallback).
"""
from __future__ import annotations

import os
import sys
import json
import math
import time
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

import numpy as np

# Asegurar path raiz para imports
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

MU0 = 4.0e-7 * math.pi
VERSION = "P10-PACK-1.0.0"

# Categorias formales de salida segun Politica 10.5
VALID_CATEGORIES = {
    "aceptado",
    "condicional",
    "direccional",
    "sin_soporte_tem",
    "fuera_de_dominio_rmt",
    "no_identificable",
    "synthetic_quarantine",
}


class EmpaquetadorLiberacion:
    """Motor de empaquetado, exportacion SEG-EDI, JSON-COV y gobernanza de salida."""

    def __init__(self, config_path: Union[str, Path] = "etapa10/config_p10.json") -> None:
        self.config_path = Path(config_path)
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.cfg = json.load(f)

        self.frozen_hashes = self.cfg.get("frozen_hashes", {})
        self.output_categories = self.cfg.get("output_categories", list(VALID_CATEGORIES))
        self.governance_rules = self.cfg.get("governance_rules", {})
        self.fallback_policy = self.cfg.get("fallback_policy", {})

    def verificar_integridad_hashes(self) -> Dict[str, Any]:
        """Comprueba criptograficamente que ningun archivo congelado haya sido alterado."""
        resultados = {}
        todos_pasan = True

        for rel_path, expected_hash in self.frozen_hashes.items():
            full_path = _ROOT / rel_path
            if not full_path.exists():
                resultados[rel_path] = {
                    "exists": False,
                    "expected": expected_hash,
                    "actual": None,
                    "match": False
                }
                todos_pasan = False
                continue

            content = full_path.read_bytes()
            actual_hash = hashlib.sha256(content).hexdigest()
            match = (actual_hash == expected_hash)
            if not match:
                todos_pasan = False

            resultados[rel_path] = {
                "exists": True,
                "expected": expected_hash,
                "actual": actual_hash,
                "match": match
            }

        return {
            "all_verified": todos_pasan,
            "checked_count": len(self.frozen_hashes),
            "files": resultados
        }

    def clasificar_punto(
        self,
        f_hz: float,
        band: str,
        cond_hh: float,
        coherence_xy: float,
        tem_support_status: str,
        phase_xy_deg: Optional[float] = None,
        is_identifiable: bool = True,
        anomaly_detected: bool = False
    ) -> Tuple[str, str]:
        """Asigna una de las 6 categorias de salida con justificacion trazable.

        Retorna:
            (categoria, codigo_razon)
        """
        # 1. Fuera de dominio RMT (D2/D3 o f > 10 kHz)
        if band in ["D2", "D3"] or f_hz > 10000.0:
            return "fuera_de_dominio_rmt", "CAT_OUT_OF_DOMAIN_RMT_EXCLUDED"

        # 2. Direccional por colinealidad / Rango 1
        if cond_hh > 1e4:
            return "direccional", "CAT_DIRECTIONAL_RANK1_POLARIZED"

        # 3. No identificable por coherencia nula, deficit de SNR o anomalia no recuperable
        if (not is_identifiable) or (coherence_xy is None) or (coherence_xy < 0.10) or np.isnan(coherence_xy):
            return "no_identificable", "CAT_UNIDENTIFIABLE_SNR_DEFICIT"

        # 4. Sin soporte TEM (ausencia de vinculo TEM-MT/AMT segun Gate G0)
        if tem_support_status == "sin_soporte":
            return "sin_soporte_tem", "CAT_UNSUPPORTED_TEM_GATE_EMPTY"

        # 5. Condicional por coherencia intermedia o soporte TEM condicional
        if tem_support_status == "condicional" or coherence_xy < 0.60:
            return "condicional", "CAT_CONDITIONAL_INTERMEDIATE_QUALITY"

        # 6. Verificacion de consistencia fisica de fase
        if phase_xy_deg is not None:
            # Fase fisica esperada en cuadrante MT [0, 90] o [-180, 180]
            if abs(phase_xy_deg) > 180.0 or np.isnan(phase_xy_deg):
                return "no_identificable", "CAT_UNIDENTIFIABLE_UNPHYSICAL_PHASE"

        # 7. Aceptado plenamente
        return "aceptado", "CAT_ACCEPTED_RANK2_COHERENT"

    def evaluar_fallback_b0(
        self,
        transfer_functions: List[Dict[str, Any]],
        raw_transfer_functions: List[Dict[str, Any]],
        anomaly_threshold_jump: float = 1000.0
    ) -> List[Dict[str, Any]]:
        """Aplica la politica de reversion segura a la referencia B0 ante divergencias.

        Si se detecta una anomalia severa (ej. salto no fisico en impedancia,
        o fase fuera de rango) entre la red y el dato crudo, revierte ese punto
        a la estimacion clasica B0 de forma totalmente documentada.
        """
        reverted_results = []

        for tf_opt, tf_raw in zip(transfer_functions, raw_transfer_functions):
            tf_out = dict(tf_opt)
            tf_out["fallback_to_b0"] = False

            # Verificar si se requiere reversion
            revert = False
            revert_reason = ""

            # Check 1: Impedancia nula o NaN
            if tf_opt.get("Zxy") is None or np.isnan(abs(tf_opt.get("Zxy", 0))):
                revert = True
                revert_reason = "FALLBACK_NULL_OR_NAN_IMPEDANCE"

            # Check 2: Salto no fisico extremo frente a estimacion cruda
            elif tf_raw.get("Zxy") is not None and abs(tf_raw["Zxy"]) > 0:
                ratio = abs(tf_opt["Zxy"]) / abs(tf_raw["Zxy"])
                if ratio > anomaly_threshold_jump or ratio < (1.0 / anomaly_threshold_jump):
                    revert = True
                    revert_reason = "FALLBACK_ANOMALOUS_IMPEDANCE_JUMP"

            # Check 3: Fase completamente anomala
            phase = tf_opt.get("phase_xy_deg")
            if phase is not None and (np.isnan(phase) or abs(phase) > 180.0):
                revert = True
                revert_reason = "FALLBACK_UNPHYSICAL_PHASE"

            # Aplicar reversion si aplica
            if revert:
                tf_out["Zxx"] = tf_raw.get("Zxx")
                tf_out["Zxy"] = tf_raw.get("Zxy")
                tf_out["Zyx"] = tf_raw.get("Zyx")
                tf_out["Zyy"] = tf_raw.get("Zyy")
                tf_out["rho_a_xy"] = tf_raw.get("rho_a_xy")
                tf_out["phase_xy_deg"] = tf_raw.get("phase_xy_deg")
                tf_out["coherence_xy"] = tf_raw.get("coherence_xy")
                tf_out["fallback_to_b0"] = True
                tf_out["fallback_reason"] = revert_reason
                tf_out["message"] = f"Reversion automatica a B0 clasico: {revert_reason}"

            reverted_results.append(tf_out)

        return reverted_results

    def exportar_seg_edi(
        self,
        sounding_id: str,
        frequencies: List[float],
        transfer_functions: List[Dict[str, Any]],
        output_path: Union[str, Path],
        coords: Optional[Dict[str, float]] = None,
        comments: Optional[List[str]] = None
    ) -> Path:
        """Exporta las funciones de transferencia en el formato estandar SEG-EDI (Wight, 1988)."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lat = coords.get("lat", 0.0) if coords else 0.0
        lon = coords.get("lon", 0.0) if coords else 0.0
        elev = coords.get("elev", 0.0) if coords else 0.0

        num_freq = len(frequencies)
        date_str = time.strftime("%Y-%m-%d", time.gmtime())

        lines = []
        lines.append(">HEAD")
        lines.append(f'  DATAID="{sounding_id}"')
        lines.append(f'  ACQBY="ARMT-TEAM"')
        lines.append(f'  FILEBY="ARMT_SUITE_1.3.0"')
        lines.append(f'  ACQDATE={date_str}')
        lines.append(f'  PROGVERS="{VERSION}"')
        lines.append(f'  LAT={lat:.6f}')
        lines.append(f'  LONG={lon:.6f}')
        lines.append(f'  ELEV={elev:.2f}')
        lines.append(">INFO")
        lines.append("  ROBUST DENOISING ARMT SUITE V1.3.0 (PLAN V1.3)")
        lines.append("  CBAM ATTENTION + RESUNET RESIDUAL DENOISING (B4)")
        lines.append("  PIPELINE SHA-256: 8e37cd1a23c0266697b5772633d67777c93d757d2b5e9baf6c46cdf0d4578191")
        if comments:
            for c in comments:
                lines.append(f"  {c}")
        lines.append(">=DEFINITIONS")
        lines.append('  REFTYPE="CARTESIAN"')
        lines.append("  HX=0.0 HY=90.0 HZ=0.0")
        lines.append("  EX=0.0 EY=90.0")
        lines.append('  ZUNITS="[mV/km]/[nT]"')

        # Seccion FREQ
        lines.append(f">FREQ // {num_freq}")
        freq_strs = [f"{f:.4e}" for f in frequencies]
        for i in range(0, num_freq, 5):
            lines.append("  " + " ".join(freq_strs[i : i + 5]))

        # Seccion ZROT
        lines.append(f">ZROT // {num_freq}")
        zrot_strs = ["0.000" for _ in frequencies]
        for i in range(0, num_freq, 5):
            lines.append("  " + " ".join(zrot_strs[i : i + 5]))

        # Componentes de Impedancia (Zxx, Zxy, Zyx, Zyy)
        components = ["ZXX", "ZXY", "ZYX", "ZYY"]

        for comp in components:
            real_vals = []
            imag_vals = []
            var_vals = []

            comp_keys = [comp, comp.upper(), comp.lower(), f"Z{comp[1:].lower()}"]

            for tf in transfer_functions:
                z_val = None
                for k in comp_keys:
                    if k in tf and tf[k] is not None:
                        z_val = tf[k]
                        break

                if z_val is None or np.isnan(complex(z_val).real):
                    real_vals.append(1.0e32)
                    imag_vals.append(1.0e32)
                    var_vals.append(1.0e32)
                else:
                    zc = complex(z_val)
                    real_vals.append(zc.real)
                    imag_vals.append(zc.imag)
                    # Estimacion de varianza
                    v = None
                    for k in comp_keys:
                        if f"{k}_var" in tf:
                            v = tf[f"{k}_var"]
                            break
                        if f"{k.lower()}_var" in tf:
                            v = tf[f"{k.lower()}_var"]
                            break

                    if v is None:
                        # Varianza basada en coherencia o error residual (~2% nominal)
                        coh = tf.get("coherence_xy", 0.95) or 0.95
                        rel_err = max(0.01, 1.0 - coh)
                        v = (abs(zc) * rel_err) ** 2
                    var_vals.append(v)

            # Real
            lines.append(f">{comp}R // {num_freq}")
            for i in range(0, num_freq, 5):
                lines.append("  " + " ".join(f"{v:14.6e}" for v in real_vals[i : i + 5]))

            # Imag
            lines.append(f">{comp}I // {num_freq}")
            for i in range(0, num_freq, 5):
                lines.append("  " + " ".join(f"{v:14.6e}" for v in imag_vals[i : i + 5]))

            # Var
            lines.append(f">{comp}.VAR // {num_freq}")
            for i in range(0, num_freq, 5):
                lines.append("  " + " ".join(f"{v:14.6e}" for v in var_vals[i : i + 5]))

        # Secciones RHO y PHASE para XY e YX
        for pair, r_name, p_name in [("xy", "RHOXY", "PHASXY"), ("yx", "RHOYX", "PHASYX")]:
            rho_vals = []
            phase_vals = []
            for tf in transfer_functions:
                rho = tf.get(f"rho_a_{pair}")
                phase = tf.get(f"phase_{pair}_deg")
                if rho is None or np.isnan(rho):
                    rho_vals.append(1.0e32)
                else:
                    rho_vals.append(rho)

                if phase is None or np.isnan(phase):
                    phase_vals.append(1.0e32)
                else:
                    phase_vals.append(phase)

            lines.append(f">{r_name} // {num_freq}")
            for i in range(0, num_freq, 5):
                lines.append("  " + " ".join(f"{v:14.6e}" for v in rho_vals[i : i + 5]))

            lines.append(f">{p_name} // {num_freq}")
            for i in range(0, num_freq, 5):
                lines.append("  " + " ".join(f"{v:14.6e}" for v in phase_vals[i : i + 5]))

        lines.append(">END")

        content = "\n".join(lines) + "\n"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return output_path

    def leer_seg_edi(self, edi_path: Union[str, Path]) -> Dict[str, Any]:
        """Lector de verificacion para parsear archivos SEG-EDI y comprobar integridad numerica."""
        edi_path = Path(edi_path)
        with open(edi_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        data: Dict[str, Any] = {
            "dataid": "",
            "frequencies": [],
            "zxx_r": [], "zxx_i": [],
            "zxy_r": [], "zxy_i": [],
            "zyx_r": [], "zyx_i": [],
            "zyy_r": [], "zyy_i": [],
            "rhoxy": [], "phasxy": [],
            "rhoyx": [], "phasyx": []
        }

        current_section = None
        current_tokens: List[float] = []

        def store_section(sec: str, tokens: List[float]):
            sec_lower = sec.lower()
            if sec_lower == "freq":
                data["frequencies"] = tokens
            elif sec_lower == "zxxr":
                data["zxx_r"] = tokens
            elif sec_lower == "zxxi":
                data["zxx_i"] = tokens
            elif sec_lower == "zxyr":
                data["zxy_r"] = tokens
            elif sec_lower == "zxyi":
                data["zxy_i"] = tokens
            elif sec_lower == "zyxr":
                data["zyx_r"] = tokens
            elif sec_lower == "zyxi":
                data["zyx_i"] = tokens
            elif sec_lower == "zyyr":
                data["zyy_r"] = tokens
            elif sec_lower == "zyyi":
                data["zyy_i"] = tokens
            elif sec_lower == "rhoxy":
                data["rhoxy"] = tokens
            elif sec_lower == "phasxy":
                data["phasxy"] = tokens
            elif sec_lower == "rhoyx":
                data["rhoyx"] = tokens
            elif sec_lower == "phasyx":
                data["phasyx"] = tokens

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            if line_str.startswith(">"):
                if current_section and current_tokens:
                    store_section(current_section, current_tokens)
                    current_tokens = []

                # Nuevo encabezado
                parts = line_str[1:].split("//")
                sec_name = parts[0].strip()
                if sec_name in ["HEAD", "INFO", "DEFINITIONS", "=DEFINITIONS", "END"]:
                    current_section = sec_name
                else:
                    current_section = sec_name
                continue

            if current_section == "HEAD":
                if line_str.startswith("DATAID="):
                    data["dataid"] = line_str.split("=")[1].replace('"', "").strip()
            elif current_section not in ["HEAD", "INFO", "DEFINITIONS", "=DEFINITIONS", "END"]:
                # Parsear tokens numericos
                tokens = line_str.split()
                for t in tokens:
                    try:
                        current_tokens.append(float(t))
                    except ValueError:
                        pass

        if current_section and current_tokens:
            store_section(current_section, current_tokens)

        return data

    def exportar_json_cov(
        self,
        sounding_id: str,
        frequencies: List[float],
        transfer_functions: List[Dict[str, Any]],
        output_path: Union[str, Path],
        provenance: Optional[Dict[str, Any]] = None,
        band: str = "D0",
        tem_support_status: str = "soporte_aprobado",
        window_stats: Optional[Dict[str, Any]] = None,
        residual_stats: Optional[Dict[str, Any]] = None,
        data_origin: str = "unknown",
        release_allowed: bool = False,
    ) -> Path:
        """Exporta el sondeo con covarianzas completas 4x4, categorias y proveniencia en JSON-COV."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        timestamp_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Construir array de puntos
        puntos = []
        for i, (f_hz, tf) in enumerate(zip(frequencies, transfer_functions)):
            cond_hh = tf.get("cond_hh", 1.0)
            coh_xy = tf.get("coherence_xy", 1.0)
            phase_xy = tf.get("phase_xy_deg")
            is_ident = tf.get("status") != "no_identificable"

            # Categorizacion formal segun Politica 10.5
            cat, cat_reason = self.clasificar_punto(
                f_hz=f_hz,
                band=band,
                cond_hh=cond_hh,
                coherence_xy=coh_xy,
                tem_support_status=tem_support_status,
                phase_xy_deg=phase_xy,
                is_identifiable=is_ident
            )
            if data_origin == "synthetic" and not release_allowed:
                cat, cat_reason = "synthetic_quarantine", "SYNTHETIC_DATA_NOT_RELEASABLE"

            # Extraer tensores de impedancia de forma case-agnostic
            def get_comp(c_name: str):
                for k in [c_name, c_name.upper(), c_name.lower(), f"Z{c_name[1:].lower()}"]:
                    if k in tf and tf[k] is not None:
                        return tf[k]
                return None

            zxx = get_comp("Zxx")
            zxy = get_comp("Zxy")
            zyx = get_comp("Zyx")
            zyy = get_comp("Zyy")

            def to_c_dict(val):
                if val is None or np.isnan(complex(val).real):
                    return None
                c = complex(val)
                return {"real": float(c.real), "imag": float(c.imag)}

            # Matriz de covarianza 4x4 para [Zxx, Zxy, Zyx, Zyy]
            # Si no viene explicita, se construye la diagonal robusta
            cov_4x4 = tf.get("cov_4x4")
            if cov_4x4 is None:
                # Matriz 4x4 diagonal estimada a partir de coherencia
                rel_v = max(0.001, (1.0 - (coh_xy or 0.9)) ** 2)
                cov_mat = np.zeros((4, 4), dtype=float)
                for idx, comp in enumerate([zxx, zxy, zyx, zyy]):
                    if comp is not None and not np.isnan(complex(comp).real):
                        cov_mat[idx, idx] = (abs(complex(comp)) ** 2) * rel_v
                cov_4x4 = cov_mat.tolist()

            punto_dict = {
                "f_hz": float(f_hz),
                "band": band,
                "category": cat,
                "category_reason": cat_reason,
                "fallback_to_b0": bool(tf.get("fallback_to_b0", False)),
                "cond_hh": float(cond_hh),
                "coherence_xy": float(coh_xy) if coh_xy is not None else None,
                "Z": {
                    "Zxx": to_c_dict(zxx),
                    "Zxy": to_c_dict(zxy),
                    "Zyx": to_c_dict(zyx),
                    "Zyy": to_c_dict(zyy)
                },
                "cov_4x4": cov_4x4,
                "rho_a": {
                    "rho_a_xy": float(tf["rho_a_xy"]) if tf.get("rho_a_xy") is not None else None,
                    "rho_a_yx": float(tf["rho_a_yx"]) if tf.get("rho_a_yx") is not None else None
                },
                "phase_deg": {
                    "phase_xy_deg": float(tf["phase_xy_deg"]) if tf.get("phase_xy_deg") is not None else None,
                    "phase_yx_deg": float(tf["phase_yx_deg"]) if tf.get("phase_yx_deg") is not None else None
                },
                "tipper": tf.get("tipper", None)
            }
            puntos.append(punto_dict)

        # Documento completo JSON-COV
        doc = {
            "format": "JSON-COV",
            "format_version": "1.0.0",
            "sounding_id": sounding_id,
            "timestamp_utc": timestamp_utc,
            "provenance": {
                "software": "ARMT MT/AMT Suite",
                "software_version": self.cfg.get("software_version", "1.3.0"),
                "release_title": self.cfg.get("release_title", ""),
                "data_origin": data_origin,
                "synthetic": bool(data_origin == "synthetic"),
                "frozen_hashes": self.frozen_hashes,
                "operator_metadata": provenance or {}
            },
            "domain_governance": {
                "band": band,
                "tem_support_status": tem_support_status,
                "release_allowed": bool(release_allowed),
                "quarantine": bool(not release_allowed),
                "zero_d2_d3_intervention": bool(self.governance_rules.get("zero_d2_d3_intervention", True)),
                "zero_fake_field_targets": bool(self.governance_rules.get("zero_fake_field_targets", True)),
                "zero_support_extrapolation": bool(self.governance_rules.get("zero_support_extrapolation", True))
            },
            "window_statistics": window_stats or {
                "total_windows": 0,
                "clean_windows": 0,
                "contaminated_windows": 0,
                "intervened_windows": 0
            },
            "residual_decomposition": residual_stats or {
                "identity_error_norm_inf": 0.0,
                "relative_signal_leakage_pct": 0.0
            },
            "transfer_functions": puntos
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)

        return output_path
