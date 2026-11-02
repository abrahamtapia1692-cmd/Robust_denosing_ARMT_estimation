# Reporte Técnico de Etapa 7: Detector y Separador Neuronal CBAM MT/AMT

- **Versión:** `P7-2.0.0`
- **Fecha:** 2026-10-29T17:11:05Z
- **Dispositivo:** `cuda` (Tiempo de cómputo: 334.29 s)

## 1. Subpuerta P7-I: Validación del Detector SCNet18 (Zhang et al. 2024)

- **Modelo:** `SCNet18_Classifier` (identification/g12.py)
- **Umbral calibrado (tau):** `1.0000`
- **FPR en tiempo limpio:** `0.00%` (Criterio: <= 1.0% -> PASA)
- **Sensibilidad en episodios detectables:** `99.60%` (Criterio: >= 90.0% -> PASA)
- **Exactitud global:** `99.80%`
- **ROC-AUC Detector CBAM:** `1.0000`
- **ROC-AUC Comparador B7 (solo-potencia):** `0.5768` (Atajo neutralizado por matching de potencia)
- **Resultado Subpuerta P7-I:** `APROBADO`

## 2. Subpuerta P7-S: Separación y Preservación de Física

### A. No Inferioridad en Tramos Limpios (S0)

| Modelo | Sesgo Relativo Zxy (%) | Error de Fase (°) | Pasa Criterio (<=5%, <=2°) |
|---|---:|---:|---:|
| B3 (SCNet18 Zhang et al. 2024) | 6.42% | 3.12° | No |
| B8 (Filtro de Wiener Multicanal) | 0.99% | 1.69° | Sí |
| **B4 (CBAM Adaptado Plan v1.3)** | **0.74%** | **0.63°** | **Sí** |

### B. Recuperación en Tramos Contaminados (S2)

| Modelo | SNR Salida (dB) | Delta SNR (dB) | Error Relativo Zxy (%) | Error de Fase (°) |
|---|---:|---:|---:|---:|
| B0 (Sin procesar / Raw) | -2.41 | 0.00 | 0.71% | 0.32° |
| B3 (SCNet18 Zhang et al. 2024) | -22.16 | +-19.75 | 1.72% | 22.02° |
| B8 (Wiener Multicanal) | -0.65 | +1.76 | 1.27% | 1.53° |
| **B4 (CBAM Adaptado Plan v1.3)** | **16.75** | **+19.16** | **0.65%** | **0.75°** |

- **Prueba de Sobresupresión a SNR Negativo:** Ratio `1.095` (Meta >= 0.80 -> PASA)
- **Resultado Subpuerta P7-S:** `APROBADO`

## 3. Puerta P7: Cadena Completa Integrada C_theta -> D_psi

- **Intervención selectiva:** `66.5%` de las ventanas procesadas
- **Error Zxy Integrado:** `0.44%` (vs. Raw: `0.44%`, Wiener: `1.14%`)
- **Error de Fase Integrado:** `0.47°` (vs. Raw: `0.21°`)
- **Sesgo en subconjunto limpio tras agregación:** `0.00%` (Meta <= 5.0%)
- **Resultado Puerta P7:** `APROBADO`
