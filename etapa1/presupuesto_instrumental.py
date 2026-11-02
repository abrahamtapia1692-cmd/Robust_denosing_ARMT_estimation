#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Presupuesto instrumental de P1 en CSV.

Cada fila declara un termino de la cadena, su valor, si esta aplicado en la
exportacion y su efecto conocido o no resuelto sobre amplitud y fase. El
objetivo no es certificar el campo, sino dejar explicito que falta.
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import comun_p1 as comun


FIELDS = [
    "id",
    "categoria",
    "termino",
    "canal",
    "banda",
    "magnitud",
    "valor",
    "unidad",
    "estado",
    "aplicado_en_exportacion",
    "efecto_amplitud_pct",
    "efecto_fase_deg",
    "incertidumbre",
    "fuente",
    "nota",
]


def response_ranges(band):
    path = comun.ETAPA1 / ("respuesta_interpolada_%s.csv" % band)
    with open(path, newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    ranges = {}
    for channel in comun.CHANNELS:
        amp = np.array([float(row[channel + "_amplitude"]) for row in rows])
        phase = np.array([float(row[channel + "_phase_deg"]) for row in rows])
        ranges[channel] = {
            "amp_min": float(amp.min()),
            "amp_max": float(amp.max()),
            "phase_min": float(phase.min()),
            "phase_max": float(phase.max()),
            "points": len(rows),
        }
    return ranges


def row(**kwargs):
    missing = [key for key in FIELDS if key not in kwargs]
    if missing:
        raise KeyError("faltan columnas: %s" % missing)
    return {key: kwargs[key] for key in FIELDS}


def build(config=None):
    config = config or comun.load_config()
    record = comun.target_record()
    registry = comun.load_json(comun.ETAPA1 / "calibration_registry.json")
    audit = comun.load_json(comun.ETAPA1 / "auditoria_ganancias.json")
    qc = comun.load_json(comun.ETAPA1 / "qc_D0_D1.json")

    d0 = response_ranges("D0")
    d1 = response_ranges("D1")
    adc_d0 = record["traces"][0]["adc_to_uv"][0]
    adc_d1 = record["traces"][1]["adc_to_uv"][0]
    settings = record["settings"]
    gain = float(settings["gains"][0][0])
    gain_db = 20.0 * np.log10(gain)
    dipoles = settings["electric_dipole_lengths_cm"]
    azimuths = settings["sensor_azimuth_degrees"]
    delay = settings["delay_seconds"]
    lat_s = settings["start_time_local"]

    e_amp_d0 = "%.4f-%.4f" % (d0["Ex"]["amp_min"], d0["Ex"]["amp_max"])
    e_amp_d1 = "%.4f-%.4f" % (d1["Ex"]["amp_min"], d1["Ex"]["amp_max"])
    h_amp_d0 = "%.4f-%.4f" % (d0["Hx"]["amp_min"], d0["Hx"]["amp_max"])
    h_amp_d1 = "%.4f-%.4f" % (d1["Hx"]["amp_min"], d1["Hx"]["amp_max"])
    e_ph_d0 = "%.2f a %.2f" % (d0["Ex"]["phase_min"], d0["Ex"]["phase_max"])
    e_ph_d1 = "%.2f a %.2f" % (d1["Ex"]["phase_min"], d1["Ex"]["phase_max"])
    h_ph_d0 = "%.2f a %.2f" % (d0["Hx"]["phase_min"], d0["Hx"]["phase_max"])
    h_ph_d1 = "%.2f a %.2f" % (d1["Hx"]["phase_min"], d1["Hx"]["phase_max"])

    splits = registry["bands"]["D0"]["channels"]
    splice = next((ch for ch in splits if ch["audit"]["splice_detected"]), None)
    if splice and splice["audit"]["outliers_removed"]:
        group = splice["audit"]["splice_groups"][0]["frequencies_hz"]
        outlier = splice["audit"]["outliers_removed"][0]
        splice_detail = "10 kHz: %s Hz; atipico %.2f Hz = %.2f grados" % (
            ", ".join("%.5f" % value for value in group),
            outlier["frequency_hz"],
            outlier["phase_deg"],
        )
    else:
        splice_detail = "no detectado"
    splice_amp = splice["audit"]["splice_amplitude_jump_db"] if splice else 0.0
    splice_phase = splice["audit"]["splice_phase_jump_deg"] if splice else 0.0
    max_phase_step = max(
        ch["audit"]["max_phase_step_deg"] for ch in splits
    )
    unit = audit["unit_interpretation"]
    spread_e = next(p for p in audit["amplitude_probe"] if p["channel"] == "Ex")

    jumps_d0 = qc["bands"]["D0"]["checks"]["saltos"]["counts"]
    jumps_d1 = qc["bands"]["D1"]["checks"]["saltos"]["counts"]

    def format_counts(counts):
        return ", ".join("%s=%d" % (channel, counts[channel]) for channel in comun.CHANNELS)

    jumps_value = "D0: %s; D1: %s" % (format_counts(jumps_d0), format_counts(jumps_d1))

    rows = [
        row(
            id="P1-01",
            categoria="ADC",
            termino="Coeficiente LSB -> microvoltio",
            canal="Ex,Ey,Hx,Hy,Hz",
            banda="D0",
            magnitud="adc_to_uv",
            valor="%.6f" % adc_d0,
            unidad="uV/count",
            estado="aplicado",
            aplicado_en_exportacion="si",
            efecto_amplitud_pct="0 (definicion de la escala)",
            efecto_fase_deg="0",
            incertidumbre="no documentada; se toma el valor del SBF",
            fuente="SBF trace.adc_to_uv",
            nota="Unico factor aplicado en P1. No incluye ganancia ni respuesta de sensor.",
        ),
        row(
            id="P1-02",
            categoria="ADC",
            termino="Coeficiente LSB -> microvoltio",
            canal="Ex,Ey,Hx,Hy,Hz",
            banda="D1",
            magnitud="adc_to_uv",
            valor="%.6f" % adc_d1,
            unidad="uV/count",
            estado="aplicado",
            aplicado_en_exportacion="si",
            efecto_amplitud_pct="0 (definicion de la escala)",
            efecto_fase_deg="0",
            incertidumbre="no documentada; se toma el valor del SBF",
            fuente="SBF trace.adc_to_uv",
            nota="D0 y D1 difieren en 1.5e-6 uV/count; no se corrige.",
        ),
        row(
            id="P1-03",
            categoria="Ganancia",
            termino="Ganancia de registro del amplificador",
            canal="todos",
            banda="D0,D1",
            magnitud="ganancia",
            valor="%.5f (%.3f dB)" % (gain, gain_db),
            unidad="adimensional",
            estado="declarada_no_aplicada",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="+%.2f si se interpreta como campo sin dividir" % gain_db,
            efecto_fase_deg="0",
            incertidumbre="etiqueta de directorio 1.8: desviacion %.4f %%" % audit["selected_label_delta_pct"],
            fuente="SBF settings.gains[0][0]; auditoria_ganancias.json",
            nota="La tabla .clb no declara secciones de ganancia; solo el nombre del directorio la identifica.",
        ),
        row(
            id="P1-04",
            categoria="Ganancia",
            termino="Redondeo etiqueta 1.8 frente a 1.77828",
            canal="todos",
            banda="D0,D1",
            magnitud="desviacion relativa",
            valor="+%.4f %%" % audit["selected_label_delta_pct"],
            unidad="porcentaje",
            estado="no_resuelto",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="dividir por 1.8 deja %.4f %% respecto de 1.77828" % audit["divide_by_label_result_pct"],
            efecto_fase_deg="0",
            incertidumbre="1.22 %",
            fuente="auditoria_ganancias.json",
            nota="No se usa 1.8 como ganancia exacta; se conserva 1.77828 del SBF.",
        ),
        row(
            id="P1-05",
            categoria="Respuesta electrica",
            termino="Amplitud de la tabla electrica",
            canal="Ex,Ey",
            banda="D0",
            magnitud="|T|",
            valor=e_amp_d0,
            unidad="V/V",
            estado="candidata_no_verificada",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="factor no aplicado",
            efecto_fase_deg="0",
            incertidumbre="hasta ~25 %% entre directorios de ganancia",
            fuente="CLB_G1.8_Ex_shifted/e000100.clb, e000101.clb",
            nota="La amplitud no escala con la ganancia del directorio; el valor absoluto no es certificable.",
        ),
        row(
            id="P1-06",
            categoria="Respuesta electrica",
            termino="Amplitud de la tabla electrica",
            canal="Ex,Ey",
            banda="D1",
            magnitud="|T|",
            valor=e_amp_d1,
            unidad="V/V",
            estado="candidata_no_verificada",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="factor no aplicado",
            efecto_fase_deg="0",
            incertidumbre="hasta ~32 %% entre directorios de ganancia",
            fuente="CLB_G1.8_Ex_shifted/e000100.clb, e000101.clb",
            nota="Incluye el tramo posterior al empalme de 10 kHz.",
        ),
        row(
            id="P1-07",
            categoria="Respuesta electrica",
            termino="Fase de la tabla electrica",
            canal="Ex,Ey",
            banda="D0,D1",
            magnitud="fase",
            valor="D0 %s; D1 %s" % (e_ph_d0, e_ph_d1),
            unidad="grados",
            estado="candidata_no_verificada",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="0",
            efecto_fase_deg="fase no aplicada",
            incertidumbre="continuidad maxima %.2f grados" % max_phase_step,
            fuente="tablas .clb corregidas por rama",
            nota="La fase incluye un desfase cercano a -180 grados en baja frecuencia; el signo no se verifico.",
        ),
        row(
            id="P1-08",
            categoria="Respuesta electrica",
            termino="Empalme anomalo cerca de 10 kHz",
            canal="Ex,Ey",
            banda="D0,D1",
            magnitud="punto atipico y salto de fase",
            valor=splice_detail,
            unidad="grados",
            estado="corregido_solo_para_interpolar",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="~%.2f dB en el empalme tras quitar el atipico" % splice_amp,
            efecto_fase_deg="~%.2f grados en el empalme tras quitar el atipico" % splice_phase,
            incertidumbre="procedimiento de limpieza no certificado",
            fuente="auditoria de las 9 tablas electricas",
            nota=(
                "El punto 10000.00 Hz con -8.10 grados se excluye de la interpolacion; la serie "
                "temporal no se toca. El extremo D1 en 10 kHz coincide con el empalme: usar hasta "
                "9.9 kHz o tratar 10 kHz como escenario separado."
            ),
        ),
        row(
            id="P1-09",
            categoria="Respuesta magnetica",
            termino="Amplitud de la tabla magnetica",
            canal="Hx,Hy,Hz",
            banda="D0",
            magnitud="|T|",
            valor=h_amp_d0,
            unidad="V/(A/m)",
            estado="candidata_no_verificada",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="factor no aplicado",
            efecto_fase_deg="0",
            incertidumbre="~5 %% entre directorios de ganancia",
            fuente="CLB_G1.8_Ex_shifted/h000200.clb, h000201.clb, h000202.clb",
            nota="La unidad literal del manual es V/(A/m); no se convierte a nT en P1.",
        ),
        row(
            id="P1-10",
            categoria="Respuesta magnetica",
            termino="Amplitud de la tabla magnetica",
            canal="Hx,Hy,Hz",
            banda="D1",
            magnitud="|T|",
            valor=h_amp_d1,
            unidad="V/(A/m)",
            estado="candidata_no_verificada",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="factor no aplicado",
            efecto_fase_deg="0",
            incertidumbre="~5 %% entre directorios de ganancia",
            fuente="CLB_G1.8_Ex_shifted/h000200.clb, h000201.clb, h000202.clb",
            nota="La tabla magnetica llega a 15 317.4 Hz, por encima de 10 kHz y por debajo de Nyquist 16 kHz.",
        ),
        row(
            id="P1-11",
            categoria="Respuesta magnetica",
            termino="Fase de la tabla magnetica",
            canal="Hx,Hy,Hz",
            banda="D0,D1",
            magnitud="fase",
            valor="D0 %s; D1 %s" % (h_ph_d0, h_ph_d1),
            unidad="grados",
            estado="candidata_no_verificada",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="0",
            efecto_fase_deg="fase no aplicada",
            incertidumbre="paso maximo ~4.3 grados",
            fuente="tablas .clb",
            nota="Sin saltos de rama en la banda revisada.",
        ),
        row(
            id="P1-12",
            categoria="Respuesta magnetica",
            termino="Interpretacion de unidad V/(A/m) frente a mV/nT",
            canal="Hx,Hy,Hz",
            banda="D0,D1",
            magnitud="cociente de sensibilidades",
            valor="%.4f" % unit["existing_code_ratio_to_literal"],
            unidad="adimensional",
            estado="no_resuelto",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="campo del codigo existente = %.4f del literal (-%.2f %%)" % (
                unit["field_ratio_code_over_literal"],
                100.0 * (1.0 - unit["field_ratio_code_over_literal"]),
            ),
            efecto_fase_deg="0",
            incertidumbre="1.2566 en sensibilidad; 20.4 %% en campo",
            fuente="manual App.7 p.70; armt/instrument_calibration.py",
            nota="El codigo existente multiplica por 1000 como si la tabla fuera mV/nT; el manual dice V/(A/m).",
        ),
        row(
            id="P1-13",
            categoria="Geometria",
            termino="Longitud de dipolo electrico",
            canal="Ex,Ey",
            banda="D0,D1",
            magnitud="L",
            valor="Ex %.0f cm, Ey %.0f cm" % (dipoles[0], dipoles[1]),
            unidad="cm",
            estado="declarada_no_verificada",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="el campo E escala como 1/L",
            efecto_fase_deg="0",
            incertidumbre="no documentada",
            fuente="SBF settings.electric_dipole_lengths_cm",
            nota="20 m declarados en el SBF; no hay medicion de campo ni certificado.",
        ),
        row(
            id="P1-14",
            categoria="Geometria",
            termino="Azimut de sensores",
            canal="Ex,Ey,Hx,Hy,Hz",
            banda="D0,D1",
            magnitud="orientacion",
            valor="Ex %.0f, Ey %.0f, Hx %.0f, Hy %.0f, Hz %.0f"
            % (azimuths[0], azimuths[1], azimuths[2], azimuths[3], azimuths[4]),
            unidad="grados",
            estado="declarada_no_verificada",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="afecta la proyeccion, no la amplitud escalar",
            efecto_fase_deg="no cuantificado",
            incertidumbre="no documentada",
            fuente="SBF settings.sensor_azimuth_degrees",
            nota="No hay prueba de rotacion ni de polaridad.",
        ),
        row(
            id="P1-15",
            categoria="Geometria",
            termino="Polaridad de canales",
            canal="todos",
            banda="D0,D1",
            magnitud="signo",
            valor="no verificada",
            unidad="adimensional",
            estado="no_verificado",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="0",
            efecto_fase_deg="180 si un canal esta invertido",
            incertidumbre="180 grados",
            fuente="sin prueba de polaridad",
            nota="Una inversion de un solo canal cambia el signo de Z y de la tipper.",
        ),
        row(
            id="P1-16",
            categoria="Sincronizacion",
            termino="Retardo declarado entre canales",
            canal="todos",
            banda="D0,D1",
            magnitud="delay_seconds",
            valor="%s" % delay,
            unidad="s",
            estado="declarada_no_aplicada",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="0",
            efecto_fase_deg="0 si el retardo es realmente nulo",
            incertidumbre="reloj no verificado",
            fuente="SBF settings.delay_seconds",
            nota="No se dispone de un pulso de sincronizacion comun para medir el retardo real.",
        ),
        row(
            id="P1-17",
            categoria="Sincronizacion",
            termino="Sensibilidad de fase a un retardo",
            canal="todos",
            banda="D1",
            magnitud="1 microsegundo a 10 kHz",
            valor="%.2f" % (360.0 * 10000.0 * 1e-6),
            unidad="grados",
            estado="referencia",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="0",
            efecto_fase_deg="3.6 por microsegundo a 10 kHz; 1 grado = 0.278 microsegundos",
            incertidumbre="depende de la exactitud del reloj",
            fuente="plan v1.3, seccion 1.4",
            nota="El presupuesto se evalua en 1-10 kHz, no en todo D1.",
        ),
        row(
            id="P1-18",
            categoria="Sincronizacion",
            termino="Marca temporal y zona horaria",
            canal="n/a",
            banda="D0,D1",
            magnitud="inicio local",
            valor=lat_s,
            unidad="fecha-hora local",
            estado="no_verificado",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="0",
            efecto_fase_deg="0",
            incertidumbre="zona horaria desconocida",
            fuente="SBF trace.start_time; manifiesto P0",
            nota="No se puede alinear con TEM ni con otros instrumentos sin zona declarada (B-P0-07).",
        ),
        row(
            id="P1-19",
            categoria="Filtros",
            termino="Respuesta del filtro anti-alias D0/D1",
            canal="todos",
            banda="D0,D1",
            magnitud="H(f)",
            valor="no documentada",
            unidad="compleja",
            estado="no_verificado",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="no cuantificado",
            efecto_fase_deg="no cuantificado",
            incertidumbre="no documentada",
            fuente="manual ARMT-5; sin tabla de filtro",
            nota="La fase del filtro no se puede separar de la fase de la tabla .clb.",
        ),
        row(
            id="P1-20",
            categoria="Receptor",
            termino="Calibracion de entradas del receptor (r*.clb)",
            canal="todos",
            banda="D0,D1",
            magnitud="archivo",
            valor="ausente",
            unidad="n/a",
            estado="ausente",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="no cuantificado",
            efecto_fase_deg="no cuantificado",
            incertidumbre="no documentada",
            fuente="Calibrations/ (solo archivos e*.clb y h*.clb)",
            nota="El manual preve archivos r*.clb para las entradas del receptor; no existen en el conjunto.",
        ),
        row(
            id="P1-21",
            categoria="Interpolacion",
            termino="Interpolacion compleja de la tabla",
            canal="todos",
            banda="D0,D1",
            magnitud="grilla log10(f)",
            valor="%d puntos/decada" % int(config["calibration"]["interp_grid_per_decade"]),
            unidad="puntos",
            estado="aplicada_solo_a_la_tabla",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="error de interpolacion no cuantificado",
            efecto_fase_deg="error de interpolacion no cuantificado",
            incertidumbre="no cuantificada",
            fuente="respuesta_interpolada_D0/D1.csv",
            nota="La interpolacion se usa para caracterizar la respuesta; no se aplica a la serie temporal.",
        ),
        row(
            id="P1-22",
            categoria="QC",
            termino="Saltos impulsivos candidatos",
            canal="todos",
            banda="D0,D1",
            magnitud="conteo |diff-mediana| > 50 sigma",
            valor=jumps_value,
            unidad="eventos",
            estado="reportado_no_enmascarado",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="0",
            efecto_fase_deg="0",
            incertidumbre="pueden ser sferics utiles o defectos",
            fuente="qc_D0_D1.json",
            nota="No se borran por amplitud; se conservan y se identifican.",
        ),
        row(
            id="P1-23",
            categoria="Cobertura",
            termino="Soporte de calibracion frente a la banda revisada",
            canal="todos",
            banda="D0,D1",
            magnitud="frecuencias",
            valor="E 5-1e6 Hz; H 5-15317.4 Hz",
            unidad="Hz",
            estado="cubierta_en_la_banda_revisada",
            aplicado_en_exportacion="no",
            efecto_amplitud_pct="0",
            efecto_fase_deg="0",
            incertidumbre="fuera de 5 Hz no hay tabla",
            fuente="calibration_registry.json",
            nota="D0 revisa 5-1000 Hz y D1 1000-10000 Hz; ambos quedan dentro del soporte.",
        ),
        row(
            id="P1-24",
            categoria="Resumen",
            termino="Presupuesto instrumental total",
            canal="todos",
            banda="D0,D1",
            magnitud="certificacion",
            valor="no certificable",
            unidad="n/a",
            estado="parcial",
            aplicado_en_exportacion="solo adc_to_uv",
            efecto_amplitud_pct="no acotado: ganancia, respuesta y unidad H sin resolver",
            efecto_fase_deg="no acotado: filtro, retardo y polaridad sin verificar",
            incertidumbre="mayor que la tolerancia P1 de 1 %% / 1 grado",
            fuente="este presupuesto",
            nota="P1 cierra el QC y caracteriza la cadena; no certifica el campo fisico.",
        ),
    ]

    path = comun.ETAPA1 / "presupuesto_instrumental.csv"
    with open(path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return {"file": str(path), "rows": len(rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    config = comun.load_config(args.config)
    result = build(config)
    print("presupuesto instrumental: %s (%d filas)" % (result["file"], result["rows"]))


if __name__ == "__main__":
    main()
