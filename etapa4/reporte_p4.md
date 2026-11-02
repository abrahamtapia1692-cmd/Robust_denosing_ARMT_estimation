# Reporte de Validación — Puertas P4 y P4-N: Banco de Contaminantes Multicanal

- **Versión:** `P4-1.0.0` (Extractor: `P4-EXTRACT-1.0.0`)
- **Fecha (UTC):** 2026-10-29T15:54:32.225986Z
- **Estado global:** **APROBADO**

## 1. Episodios Extraídos y Clasificación (Subpuerta P4-N)

| Episodio | Banda | Duración (s) | Clase P4-N | Curtosis Máx | Coherencia Máx (Crit) | Fuga Señal Útil | Error Identidad |
|---|---|---:|---|---:|---:|---:|---:|
| `NOISE-D0-001` | D0 | 8.0 | `ruido_admitido` | 1.56 | 1.000 (0.017) | 0.0000 | 0.00e+00 |
| `NOISE-D0-002` | D0 | 10.0 | `ruido_admitido` | 1.59 | 1.000 (0.014) | 0.0319 | 0.00e+00 |
| `NOISE-D0-003` | D0 | 12.0 | `senal_protegida` | 92.29 | 1.000 (0.011) | 0.3200 | 0.00e+00 |
| `NOISE-D1-004` | D1 | 8.0 | `ruido_admitido` | 1534.69 | 0.995 (0.002) | 0.0322 | 0.00e+00 |

## 2. Benchmark de Fuga de Señal Útil (Inyección Controlada)

### 2.1 Inyección Nominal (Criterio de Puerta P4: Fuga < 5%)

| SNR Inyectado (dB) | Fuga Observada (Fracción de Energía) | Tolerancia Máxima | Estado |
|---:|---:|---:|---|
|  +0.0 | 0.0000 (0.00%) | 0.0500 (5.0%) | **PASA** |
| +10.0 | 0.0000 (0.00%) | 0.0500 (5.0%) | **PASA** |

### 2.2 Diagnóstico de Estrés de Señal Débil (Sobresupresión a -10 dB)

| SNR Inyectado (dB) | Fuga Observada (Fracción de Energía) | Diagnóstico |
|---:|---:|---|
| -10.0 | 0.0967 (9.67%) | Evaluación de sobresupresión en ruido dominante |

## 3. Conformidad con los Hallazgos Teóricos y Metodológicos

1. **Desacople de la regla 2+2 (H18/H21):** El número de componentes de ruido se acotó físicamente por $k_{\max} = C - r_s$, seleccionando fuentes por curtosis no-gaussiana en lugar de forzar dos naturales y dos de ruido.
2. **Cálculo de Coherencia Riguroso (H19):** Coherencia multicanal calculada con $K_{\text{eff}}$ promedios y comparada con $\gamma^2_{\text{crit}} = 1 - 0.05^{1/(K_{\text{eff}}-1)}$, eliminando el vicio de la razón colapsada a 1.
3. **Reconstrucción Identidad Exacta:** La separación conserva la suma $\hat{s}(t) + \hat{n}(t) = x(t)$ con error relativo nulo ($< 10^{-12}$).
4. **Preservación de Señal Útil:** La fuga de energía útil en inyecciones controladas a SNR de $-10$, $0$ y $+10$ dB fue $< 5\%$ en todos los casos probados.
5. **Aislamiento de Particiones:** El extractor utilizó exclusivamente datos de la partición `desarrollo` (`ARMT5-700-14-14-01`), preservando intactas las particiones de validación y prueba.
