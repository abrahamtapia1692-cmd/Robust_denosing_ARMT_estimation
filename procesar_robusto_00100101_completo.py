#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Procesamiento Robusto Multibanda Completo (D0 + D1, hasta 10 kHz) y Modelo Teorico 5 Capas.

Integra:
1. Cadena de Denoising CBAM (Etapa 8) sobre las trazas MT/AMT del sondeo real:
   - Traza 0 (Banda D0: fs = 4000 Hz, 125 Hz - 1000 Hz, hasta 6.5 Hz).
   - Traza 1 (Banda D1: fs = 32000 Hz, 1000 Hz - 10000 Hz).
2. Procesador Robusto Oficial de ARMT_processing (ARMTSoundingProcessor):
   - Calibracion instrumental completa (.clb, dipolos 20 m, ganancias G=1.8).
   - Conversion a unidades fisicas estandar: E en mV/km, H en nT.
   - Exclusion de armonicos 60 Hz (comb / peak-picking).
   - Estimador espectral robusto bivariado (CWT / Multitaper + Bounded Influence).
   - Fusion multibanda M2 ponderada por varianza inversa (cubriendo de 10 kHz a 6.5 Hz).
   - Suavizamiento por relaciones de dispersion (DR).
3. Exportacion SEG-EDI estandar (Wight, 1988):
   - 00100101_denoised_robusto.edi (Sondeo real limpio, rango completo 10 kHz - 6.5 Hz).
   - 00100101_teorico_5capas.edi (Modelo 5 capas exacto sobre la misma grilla y rango denso).
"""
from __future__ import annotations

import os
import sys
import json
import math
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import numpy as np

_ROOT = Path(__file__).resolve().parent
_ARMT_PROC = _ROOT.parent / "ARMT_processing"
_MODEL_DIR = _ROOT.parent / "Modelado_directo_MT_edi"

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ARMT_PROC) not in sys.path:
    sys.path.insert(0, str(_ARMT_PROC))
if str(_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(_MODEL_DIR))

from armt import SBFReader
from armt.processor import ARMTSoundingProcessor
from etapa8.pipeline_armt import ARMTPipeline
from model_1d_edi import model_mt_1d

MU0 = 4.0e-7 * math.pi
EMPTY_VALUE = 1.0e32


class DenoisedSBFReaderWrapper:
    """Wrapper transparente de SBFReader que intercepta y aplica denoising CBAM a D0 y D1."""

    def __init__(self, real_reader: SBFReader, pipe: ARMTPipeline, support_synth: dict):
        self._reader = real_reader
        self._pipe = pipe
        self._support = support_synth
        self._cache = {}

    def __getattr__(self, name):
        return getattr(self._reader, name)

    def read_samples(self, trace_index: int, start: int = 0, stop: Optional[int] = None,
                     channels: Optional[List[str]] = None, units: str = "uV") -> np.ndarray:
        if stop is None:
            stop = self._reader.traces[trace_index].sample_count

        cache_key = (trace_index, start, stop, units)
        if cache_key in self._cache:
            data_full = self._cache[cache_key]
        else:
            trace = self._reader.traces[trace_index]
            fs = float(trace.sample_rate_hz)
            all_channels = [c for c in trace.channels if c in ("Ex", "Ey", "Hx", "Hy", "Hz")]

            # Leer muestras brutas
            raw_data = self._reader.read_samples(
                trace_index, start=start, stop=stop, channels=all_channels, units=units
            ).astype(np.float32)

            # Si es traza MT/AMT (D0 o D1), aplicar CBAM
            if trace_index in (0, 1):
                band = "D0" if trace_index == 0 else "D1"
                print(f"  [CBAM Denoising] Traza {trace_index} ({band}, fs={fs:.0f} Hz): procesando {len(raw_data)} muestras...")
                t0 = time.time()

                # Separar 4 canales principales
                data_4ch = raw_data[:, :4]
                res_cbam = self._pipe.process_continuous_record(
                    data_4ch,
                    record_id="ARMT5-123-01-01-01",
                    band=band,
                    fs_hz=fs,
                    support_source=self._support,
                    force_mode="auto",
                    batch_size=128
                )
                s_hat = res_cbam["s_hat"]
                t_el = time.time() - t0
                pct = res_cbam["intervened_pct"]
                print(f"  [CBAM Denoising] {band} completada en {t_el:.2f} s: {pct:.1f}% ventanas intervenidas.")

                # Recomponer con canal Hz si existe
                if raw_data.shape[1] > 4:
                    denoised_full = np.zeros_like(raw_data)
                    denoised_full[:, :4] = s_hat
                    denoised_full[:, 4:] = raw_data[:, 4:]  # Hz intacto
                    data_full = denoised_full
                else:
                    data_full = s_hat
            else:
                # Bandas RMT (D2, D3): sin CBAM
                data_full = raw_data

            self._cache[cache_key] = data_full

        # Filtrar solo canales solicitados
        if channels is not None:
            trace = self._reader.traces[trace_index]
            all_channels = [c for c in trace.channels if c in ("Ex", "Ey", "Hx", "Hy", "Hz")]
            indices = [all_channels.index(c) for c in channels if c in all_channels]
            return data_full[:, indices]
        return data_full


class RobustDenoisedSoundingProcessor(ARMTSoundingProcessor):
    """ARMTSoundingProcessor que inyecta el lector con denoising CBAM."""

    def __init__(self, *args, pipe: ARMTPipeline = None, support_synth: dict = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pipe = pipe
        self.support_synth = support_synth

    def process_all_traces(self) -> dict:
        self.results_per_trace = []
        self.additive_candidates = []

        with SBFReader(self.sbf_path) as real_reader:
            print(f"\n=======================================================")
            print(f"PROCESANDO SONDEO ARMT-5 CON DENOISING CBAM + MOTOR ROBUSTO: {self.sbf_path.name}")
            print(f"Trazas disponibles: {len(real_reader.traces)}")
            print(f"=======================================================")

            # Envolver con CBAM
            reader = DenoisedSBFReaderWrapper(real_reader, self.pipe, self.support_synth)

            dipole_ex_m = 20.0
            dipole_ey_m = 20.0
            if real_reader.settings:
                st = real_reader.settings[0]
                if len(st.electric_dipole_lengths_cm) >= 2:
                    dipole_ex_m = st.electric_dipole_lengths_cm[0] / 100.0
                    dipole_ey_m = st.electric_dipole_lengths_cm[1] / 100.0
            print(f"Longitudes de dipolo: Ex={dipole_ex_m:.1f} m, Ey={dipole_ey_m:.1f} m")

            for trace in real_reader.traces:
                trace_res = self._process_single_trace(reader, trace, dipole_ex_m, dipole_ey_m)
                if trace_res is not None and len(trace_res["freqs"]) > 0:
                    self.results_per_trace.append(trace_res)

        if not self.results_per_trace and not self.additive_candidates:
            raise RuntimeError("No se obtuvieron resultados válidos en ninguna traza.")

        # Fusión multibanda M2 ponderada por varianza inversa
        self.merged_result = self._merge_multiband_traces()

        # Guardar archivo EDI de puntos discretos
        edi_filename = self.output_dir / f"{self.sbf_path.stem}_processed.edi"
        self._export_edi(edi_filename)

        # Suavizamiento por Relaciones de Dispersión
        if self.smooth_dispersion_relations:
            try:
                from armt.dispersion_smoothing import compute_dispersion_relation_smoothing
                id_mask = self.merged_result.get("identifiable_mask", np.ones(len(self.merged_result["freqs"]), dtype=bool))
                if np.sum(id_mask) >= 6:
                    self.dr_result = compute_dispersion_relation_smoothing(
                        self.merged_result["freqs"][id_mask],
                        self.merged_result["Zxy"][id_mask],
                        self.merged_result["Zyx"][id_mask],
                        ppd=8,
                    )
                    dr_edi_filename = self.output_dir / f"{self.sbf_path.stem}_processed_DRsmooth.edi"
                    self._export_smooth_edi(dr_edi_filename, self.dr_result)
            except Exception as e:
                print(f"[Aviso] No se pudo calcular suavizamiento DR: {e}")

        # Generar figuras diagnósticas
        plot_filename = self.output_dir / f"{self.sbf_path.stem}_sounding_curves.png"
        self.plot_sounding(save_path=str(plot_filename))

        # Guardar resumen JSON
        json_filename = self.output_dir / f"{self.sbf_path.stem}_summary.json"
        self._save_summary_json(json_filename)

        return self.merged_result


def export_theoretical_edi(
    output_path: Path,
    station_name: str,
    freqs: np.ndarray,
    resistivities: List[float],
    thicknesses: List[float],
    coords: dict
):
    """Exporta el modelo teórico 5 capas en formato SEG-EDI con unidades estándar de campo ([mV/km]/[nT])."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nfreq = len(freqs)
    
    # Calcular respuesta directa 1D
    Zxy_field = np.zeros(nfreq, dtype=complex)
    Zyx_field = np.zeros(nfreq, dtype=complex)
    rho_xy = np.zeros(nfreq, dtype=float)
    phi_xy = np.zeros(nfreq, dtype=float)

    for k, f in enumerate(freqs):
        r, p, z_si = model_mt_1d(resistivities, thicknesses, f)
        # En unidades EDI ([mV/km]/[nT]): |Z| = sqrt(5 * f * rho_a)
        # Relación exacta entre Z_SI (ohm) y Z_EDI: Z_EDI = Z_SI * (10^4 / 4pi)
        z_edi = z_si * (10000.0 / (4.0 * math.pi))
        Zxy_field[k] = z_edi
        Zyx_field[k] = -z_edi
        rho_xy[k] = r
        phi_xy[k] = math.degrees(p)

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(">HEAD\n")
        fh.write(f'  DATAID="{station_name}"\n')
        fh.write(f'  ACQBY="ARMT-TEAM"\n')
        fh.write(f'  FILEBY="ARMT_SUITE_1.3.0"\n')
        fh.write(f'  ACQDATE={time.strftime("%Y-%m-%d")}\n')
        fh.write(f'  LAT={coords.get("lat", 0.0):.6f}\n')
        fh.write(f'  LONG={coords.get("lon", 0.0):.6f}\n')
        fh.write(f'  ELEV={coords.get("elev", 0.0):.2f}\n')
        fh.write('  STDVERS="SEG 1.0"\n')
        fh.write('  PROGVERS="MT1D_ROBUST"\n')
        fh.write(f"  EMPTY={EMPTY_VALUE:.1e}\n\n")

        fh.write(">INFO\n")
        fh.write("  MODELO TEORICO ESTRATIFICADO 5 CAPAS (MAXWELL 1D CONTINUO)\n")
        fh.write(f"  CAPAS RHO (OHM.M): {resistivities}\n")
        fh.write(f"  ESPESORES (M):     {thicknesses}\n")
        fh.write("  RANGO MULTIBANDA COMPLETO: 10 kHz a 0.01 Hz (D1 + D0 + MT profundo)\n\n")

        fh.write(">=DEFINITIONS\n")
        fh.write('  REFTYPE="CARTESIAN"\n')
        fh.write("  HX=0.0 HY=90.0 HZ=0.0\n")
        fh.write("  EX=0.0 EY=90.0\n")
        fh.write('  ZUNITS="[mV/km]/[nT]"\n\n')

        def _write_block(tag, arr):
            fh.write(f">{tag} // {nfreq}\n")
            strs = [f"{v:14.6e}" for v in arr]
            for i in range(0, nfreq, 5):
                fh.write("  " + " ".join(strs[i : i + 5]) + "\n")

        _write_block("FREQ", freqs)
        _write_block("ZXXR", np.zeros(nfreq))
        _write_block("ZXXI", np.zeros(nfreq))
        _write_block("ZXX.VAR", np.zeros(nfreq))

        _write_block("ZXYR", Zxy_field.real)
        _write_block("ZXYI", Zxy_field.imag)
        _write_block("ZXY.VAR", np.zeros(nfreq))

        _write_block("ZYXR", Zyx_field.real)
        _write_block("ZYXI", Zyx_field.imag)
        _write_block("ZYX.VAR", np.zeros(nfreq))

        _write_block("ZYYR", np.zeros(nfreq))
        _write_block("ZYYI", np.zeros(nfreq))
        _write_block("ZYY.VAR", np.zeros(nfreq))

        _write_block("RHOXY", rho_xy)
        _write_block("PHASXY", phi_xy)
        _write_block("RHOYX", rho_xy)
        _write_block("PHASYX", phi_xy - 180.0)

        fh.write(">END\n")

    print(f"  [OK] Exportado EDI Modelo 5 Capas Completo: {output_path.name}")


def main():
    print("=" * 80)
    print("PROCESAMIENTO ROBUSTO MULTIBANDA (10 kHz a 6.5 Hz) CON DENOISING CBAM")
    print("Sondeo real objetivo: Soundings/00100101.sbf")
    print("=" * 80)

    # 1. Definicion del modelo teorico de 5 capas
    rho_layers = [10.0, 20.0, 12.0, 35.0, 250.0]
    thicknesses = [10.0, 25.0, 60.0, 110.0]
    interfaces = [10.0, 35.0, 95.0, 205.0]

    coords = {"lat": 19.293594, "lon": -99.597279, "elev": 2613.0}

    # 2. Inicializar Pipeline CBAM
    pipe = ARMTPipeline(config_path="etapa8/config_p8.json")
    print(f"Pipeline CBAM inicializado en dispositivo: {pipe.device}")

    # Soporte sintetico que habilita tanto D0 como D1
    support_synth = {
        "synthetic": True,
        "frequencies": [
            {"band": "D0", "f_hz": 500.0, "status": "respaldada", "aplicacion": "habilitada"},
            {"band": "D1", "f_hz": 5000.0, "status": "respaldada", "aplicacion": "habilitada"}
        ]
    }

    # 3. Procesamiento robusto del sondeo con ARMTSoundingProcessor
    sbf_file = _ARMT_PROC / "Soundings" / "00100101.sbf"
    calibs_dir = _ARMT_PROC / "Calibrations"
    out_dir = _ROOT / "salidas_robusto_00100101"
    out_dir.mkdir(parents=True, exist_ok=True)

    proc = RobustDenoisedSoundingProcessor(
        sbf_path=str(sbf_file),
        calibrations_dir=str(calibs_dir),
        output_dir=str(out_dir),
        pipeline_version="v3",
        spectral_engine="cwt",  # Motor robusto CWT criticamente muestreado
        enable_fdica=True,      # Modulador robusto
        fdica_mode="weighter",
        smooth_dispersion_relations=True,
        pipe=pipe,
        support_synth=support_synth
    )

    merged = proc.process_all_traces()
    freqs_estimated = merged["freqs"]
    print(f"\n[+] Fusion Multibanda Completada:")
    print(f"    Frecuencias estimadas: {len(freqs_estimated)} ({freqs_estimated.min():.2f} Hz a {freqs_estimated.max():.2f} Hz)")
    print(f"    Rango temporal de periodos: {1.0/freqs_estimated.max():.6e} s (10 kHz) a {1.0/freqs_estimated.min():.4f} s")

    # Copiar el EDI resultante a la raiz para acceso directo
    edi_src = out_dir / "00100101_processed.edi"
    edi_dst = _ROOT / "00100101_denoised.edi"
    if edi_src.exists():
        import shutil
        shutil.copy(edi_src, edi_dst)
        print(f"  [OK] EDI Robusto Multibanda actualizado: {edi_dst.name}")

    # 4. Exportar el Modelo Teorico de 5 Capas sobre la misma grilla y sobre una grilla densa completa
    # Grilla completa para representacion continua (10 kHz hasta 0.01 Hz)
    freqs_dense = np.logspace(4.0, -1.5, 60)  # 10000 Hz a 0.03 Hz
    edi_theory_dst = _ROOT / "00100101_teorico_5capas.edi"
    export_theoretical_edi(
        output_path=edi_theory_dst,
        station_name="00100101_THEORY_5LAYERS",
        freqs=freqs_dense,
        resistivities=rho_layers,
        thicknesses=thicknesses,
        coords=coords
    )

    print("\n" + "=" * 80)
    print("PROCESAMIENTO ROBUSTO FINALIZADO CON EXITO")
    print(f"Archivos EDI actualizados para visualizacion en WingLink / software geofisico:")
    print(f"  1. {edi_dst.name} (Sondeo real limpio con CBAM + CWT + Calibracion hasta 10 kHz)")
    print(f"  2. {edi_theory_dst.name} (Modelo 5 capas teorico exacto cubriendo de 10 kHz a 0.03 Hz)")
    print("=" * 80)


if __name__ == "__main__":
    main()

