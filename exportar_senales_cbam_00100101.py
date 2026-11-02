#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exportador de Series de Tiempo Limpias de CBAM para el Sondeo 00100101.

Genera:
1. 00100101_cbam_clean.sbf: Archivo SBF nativo clonado con las trazas D0 y D1 limpiadas por CBAM.
   Permite correr directamente cualquier script o estimador de ARMT_processing:
   python run_sounding_processing.py 00100101_cbam_clean.sbf --spectral-engine [cwt|multitaper] ...
2. 00100101_senales_cbam.npz: Arreglos numpy estructurados con las senales limpias (s_hat),
   el ruido removido (n_hat), canales, frecuencias de muestreo y metadatos.
"""
from __future__ import annotations

import os
import sys
import time
import shutil
from pathlib import Path
import numpy as np

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

_ROOT = Path(__file__).resolve().parent
_ARMT_PROC = _ROOT.parent / "ARMT_processing"

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ARMT_PROC) not in sys.path:
    sys.path.insert(0, str(_ARMT_PROC))

from armt import SBFReader
from etapa8.pipeline_armt import ARMTPipeline

def main():
    sbf_src = _ARMT_PROC / "Soundings" / "00100101.sbf"
    out_dir = _ROOT / "salidas_senales_cbam"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    sbf_dst = out_dir / "00100101_cbam_clean.sbf"
    npz_dst = out_dir / "00100101_senales_cbam.npz"

    print("=" * 70)
    print("EXTRACCION Y EXPORTACION DE SENALES LIMPIAS CBAM: 00100101")
    print("=" * 70)

    # 1. Inicializar Pipeline CBAM en GPU
    pipe = ARMTPipeline(config_path="etapa8/config_p8.json")
    print(f"Pipeline CBAM inicializado en dispositivo: {pipe.device}")

    support_synth = {
        "synthetic": True,
        "frequencies": [
            {"band": "D0", "f_hz": 500.0, "status": "respaldada", "aplicacion": "habilitada"},
            {"band": "D1", "f_hz": 5000.0, "status": "respaldada", "aplicacion": "habilitada"}
        ]
    }

    # Clonar archivo SBF base
    shutil.copy(sbf_src, sbf_dst)
    print(f"[OK] Archivo SBF base clonado en: {sbf_dst.name}")

    export_dict = {}

    with SBFReader(sbf_src) as reader:
        # Abrir archivo clonado en modo binario r+b para sustituir las muestras
        with open(sbf_dst, "r+b") as fh_out:
            for trace_idx in (0, 1):
                trace = reader.trace(trace_idx)
                band = "D0" if trace_idx == 0 else "D1"
                fs = float(trace.sample_rate_hz)
                n_samples = trace.sample_count
                channels = [c for c in trace.channels if c in ("Ex", "Ey", "Hx", "Hy", "Hz")]

                print(f"\n--- Procesando Traza {trace_idx} ({band}, fs={fs:.0f} Hz, {n_samples} muestras) ---")
                raw_uV = reader.read_samples(trace_idx, start=0, stop=n_samples, channels=channels, units="uV").astype(np.float32)

                t0 = time.time()
                # Pasar los 4 canales [Ex, Ey, Hx, Hy] por CBAM
                res_cbam = pipe.process_continuous_record(
                    raw_uV[:, :4],
                    record_id="ARMT5-123-01-01-01",
                    band=band,
                    fs_hz=fs,
                    support_source=support_synth,
                    force_mode="auto",
                    batch_size=128
                )
                t_el = time.time() - t0
                pct = res_cbam["intervened_pct"]
                print(f"  [CBAM] Denoising {band} finalizado en {t_el:.2f} s ({pct:.1f}% ventanas intervenidas).")

                s_hat_4ch = res_cbam["s_hat"]
                n_hat_4ch = res_cbam["n_hat"]

                # Recomponer 5 canales completos manteniendo Hz original
                clean_full_uV = np.zeros_like(raw_uV)
                clean_full_uV[:, :4] = s_hat_4ch
                if raw_uV.shape[1] > 4:
                    clean_full_uV[:, 4:] = raw_uV[:, 4:]

                # Guardar en diccionario para exportacion .npz
                export_dict[f"{band}_s_hat_uV"] = clean_full_uV
                export_dict[f"{band}_n_hat_uV"] = raw_uV - clean_full_uV
                export_dict[f"{band}_raw_uV"] = raw_uV
                export_dict[f"{band}_fs_hz"] = fs
                export_dict[f"{band}_channels"] = np.array(channels)

                # Convertir senal limpia a cuentas de ADC para escribir en el SBF clonado
                adc_to_uv = np.asarray(trace.adc_to_uv)[:len(channels)]
                clean_counts = np.round(clean_full_uV / adc_to_uv).astype(np.int32)

                # Posicionarse en el offset exacto de la traza y escribir el payload binario
                fh_out.seek(trace.data_offset)
                raw_bytes = clean_counts.tobytes()
                fh_out.write(raw_bytes)
                print(f"  [SBF] {len(raw_bytes)} bytes de muestras limpias sobreescritos en offset {trace.data_offset}.")

    # Guardar archivo .npz
    np.savez_compressed(npz_dst, **export_dict)
    print(f"\n[OK] Archivo NPZ guardado: {npz_dst}")
    print(f"[OK] Archivo SBF limpio guardado: {sbf_dst}")
    print("\nListo para alimentar directamente a cualquier variante de ARMT_processing sin reentrenar ni correr CBAM nuevamente.")

if __name__ == "__main__":
    main()

