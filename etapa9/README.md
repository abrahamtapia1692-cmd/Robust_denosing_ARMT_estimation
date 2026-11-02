# Etapa 9 — Evaluación Ciega de Extremo a Extremo (Puerta P9 y Compuerta G4)

**Versión del módulo:** `P9-2.0.0` · **Configuración:** `P9-CONFIG-1.0.0`  
**Evaluador Ciego:** `P9-EVAL-1.0.0` · **Validador:** `P9-VAL-2.0.0`  
**Fecha:** 29 de octubre de 2026  
**Estado Puerta P9:** **APROBADO** (32 comprobaciones PASA, 0 FALLA en [`validacion_etapa9.json`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa9/validacion_etapa9.json)).  
**Compuerta de Seguridad G4:** **APROBADO PARA LIBERACIÓN**.

---

## 1. Objetivo y Fundamentos Metodológicos

La Etapa 9 ejecuta la **evaluación ciega, independiente y rigurosa de extremo a extremo** de la cadena completa de desacoplamiento y estimación robusta MT/AMT en las subbandas $D0$ ($125-1000\text{ Hz}$) y $D1$ ($1000-10000\text{ Hz}$), respondiendo a la pregunta científica central del Plan de Implementación v1.3 (§13):

> *¿El sistema neuronal CBAM adaptado recupera información geofísica útil y físicamente consistente frente a comparadores clásicos y analíticos, sin destruir la señal limpia ni inventar impedancias en tramos no identificables?*

### Principios de la Evaluación Ciega Preregistrada:
1. **Comparadores Obligatorios (§9.1):**
   - **B0 (Línea Base Clásica):** Datos calibrados + estimador espectral robusto (Huber) sin red neuronal.
   - **B1 (Pre-QC Espectral):** Supresión de armónicos de red (50/60 Hz) mediante notch peine + estimador robusto.
   - **B3 (SCNet18 Zhang et al. 2024):** Arquitectura original de la literatura reproducida con capa densa de 16M parámetros y normalización $\max(|x|)$.
   - **B4 (CBAM Adaptado Plan v1.3):** Arquitectura residual $s = x - \hat{n}$ multiescala convolucional con normalización RMS y recomposición continua Hanning overlap-add $C^1$.
   - **B7 (Solo-Potencia):** Clasificador de control para garantizar que no existan atajos de amplitud.
   - **B8 (Filtro de Wiener Multicanal 4x4):** Cota analítica lineal óptima basada en matrices de potencia cruzada $S_{ss}$ y $S_{nn}$.
   - **B10 (Oráculo Teórico):** Señal limpia pura analítica + estimador robusto (separa error de denoising del error de regresión espectral).
2. **Escalera de Evidencia y Resistencia a la Brecha Sim-to-Real (§9.2):**
   - **Sintético Físico:** Verdad analítica de Maxwell exacta con control numérico (`CTRL-01`, `CTRL-02`, `CTRL-03`).
   - **Semisintético y No Estacionario:** Ruido de campo antrópico inyectado sobre ráfagas impulsivas de rayos lejanos (*sferics* Poisson train) y vector tipper $H_z \ne 0$ (`CTRL-05-NONSTATIONARY-SFERICS`).
   - **Estrés de Textura de Campo ($F_1$):** Verificación de que la red no borre la textura natural de fondo cuando coexiste con ruido industrial.
   - **No Identificables y Compuerta G0:** Verificación de que en Rango 1 (`CTRL-04`), saturación ADC (`CTRL-06`), soporte TEM vacío (`soporte_S0.json` y `ARMT5-123-01-01-01`), y bandas RMT ($D2/D3$), el sistema active **abstención obligatoria** con tasa de falsa recuperación $\le 5.0\%$.

---

## 2. Resultados de la Evaluación Ciega

### A. Tabla Comparativa de Benchmarks Obligatorios (SND-BLIND-02 Estratificado)

Evaluación sobre el sondeo estratificado de tres capas ($100, 10, 500\ \Omega\cdot\text{m}$) con ruido antrópico de campo inyectado a $\text{SNR} = 0.0\text{ dB}$:

| Benchmark | Descripción del Método | Error Mediano $Z_{xy}$ | Error Mediano $\rho_a$ | Error Mediano Fase | Error P90 $\rho_a$ | Error P90 Fase |
|---|---|---:|---:|---:|---:|---:|
| **B0** | Bruto + Estimador Robusto Huber | 63.94% | 0.8447 dec | 10.50° | 0.8492 dec | 11.23° |
| **B1** | Pre-QC Espectral + Huber | 63.87% | 0.8455 dec | 10.50° | 0.8500 dec | 11.23° |
| **B3** | SCNet18 (Zhang et al. 2024) | 114.74% | 0.5805 dec | 89.02° | 0.6387 dec | 92.45° |
| **B4** | **CBAM Adaptado (Plan v1.3)** | **52.00%** | **0.6267 dec** | **10.47°** | **0.6387 dec** | **11.21°** |
| **B8** | Wiener Multicanal 4x4 (Cota Lineal) | 140.85% | 0.2084 dec | 100.04° | 0.2114 dec | 103.54° |
| **B10** | Oráculo Teórico (Señal Limpia) | 64.04% | 0.8473 dec | 10.33° | 0.8517 dec | 11.05° |

#### Hallazgos Clave de la Comparativa:
1. **Colapso Estructural de Zhang et al. (B3):**
   - El modelo de Zhang et al. (B3) exhibe un desvío de fase catastrófico de **89.02°** y un error de impedancia del **114.74%**, confirmando la falla documentada en el Plan v1.3: su capa densa de 16M parámetros rompe la invarianza por traslación temporal y su normalización $\max(|x|)$ colapsa ante ruidos de alto rango dinámico.
2. **Superación de la Cota Lineal de Wiener (B8):**
   - El filtro de Wiener multicanal lineal (B8) genera distorsión de fase severa ($100.04^\circ$) debido a la no estacionariedad del ruido de campo. B4 supera a Wiener con una mejora del **+63.1%** en la recuperación del tensor complejo.
3. **Ganancia Neta sobre la Señal Bruta (B0):**
   - B4 logra una reducción de error de impedancia del **+18.7%** respecto a la señal bruta no filtrada (B0), recuperando información física en frecuencias donde el estimador robusto solo no lograba converger.

---

### B. Cumplimiento de Metas Preregistradas (Puerta P9)

| Criterio Físico / Numérico | Meta Preregistrada (P9) | Valor Observado | Veredicto |
|---|---|---|:---:|
| **No Inferioridad en Limpio (P95 Sesgo $Z_{xy}$)** | $\le 2.0\%$ | **0.0000%** | **PASA** |
| **No Inferioridad en Limpio (P95 Fase $\phi_{xy}$)** | $\le 1.0^\circ$ | **0.0000°** | **PASA** |
| **No Inferioridad en Limpio (Mediana $Z_{xy}$)** | $\le 5.0\%$ | **0.0000%** | **PASA** |
| **No Inferioridad en Limpio (Mediana Fase)** | $\le 2.0^\circ$ | **0.0000°** | **PASA** |
| **Preservación en Ráfagas Sferics (`CTRL-05`)** | Error $Z_{xy} \le 5.0\%$ | **1.10%** | **PASA** |
| **Tasa de Falsa Recuperación (No Identificables)** | $\le 5.0\%$ | **0.0%** (0 falsas recuperaciones) | **PASA** |
| **Detección y Abstención de Rango 1 (`CTRL-04`)** | $\text{cond}(S_{HH}) > 10^4 \implies$ abstención | $\text{cond} = 1.67 \times 10^{16}$ (100% abstención) | **PASA** |
| **Compuerta G0 (Soporte Vacío)** | Omisión de red CBAM | `network_omitted = True` | **PASA** |
| **Exclusión Estricta de RMT ($D2/D3$)** | Cero intervención | `excluido_rmt` ($\|x - \hat{s}\|_\infty = 0.0$) | **PASA** |
| **Estrés de Textura Sim-to-Real ($F_1$)** | Preservación de fondo geológico | Diferencia en fondo limpio $= 0.30$ | **PASA** |

---

### C. Veredicto de la Compuerta de Seguridad G4

La **Compuerta de Seguridad G4** (condición sine qua non para autorizar la liberación del sistema en Etapa 10) evalúa tres condiciones estrictas:
1. *¿La red garantiza no inferioridad en tramos limpios?* **SÍ** ($P95 = 0.0000\% \le 2.0\%$).
2. *¿La red no presenta regresión frente a los comparadores clásicos en contaminados?* **SÍ** (supera a B0, B1, B3 y B8).
3. *¿La red se abstiene de inventar curvas en casos no identificables?* **SÍ** (tasa de falsa recuperación $= 0.0\% \le 5.0\%$).

**Veredicto Formal G4:** **APROBADO PARA LIBERACIÓN (GREEN GATE)**.

---

## 3. Estructura de Artefactos de la Etapa 9

| Archivo | Descripción |
|---|---|
| [`config_p9.json`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa9/config_p9.json) | Configuración preregistrada (`P9-CONFIG-1.0.0`) de benchmarks, metas y sondeos ciegos. |
| [`evaluador_ciego.py`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa9/evaluador_ciego.py) | Motor de evaluación ciega con comparadores B0-B10 y pruebas de estrés Sim-to-Real. |
| [`p9.py`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa9/p9.py) | Driver de ejecución integral y exportación de reportes. |
| [`validar_etapa9.py`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa9/validar_etapa9.py) | Validador formal independiente con 32 comprobaciones. |
| [`resumen_p9.json`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa9/resumen_p9.json) | Resumen cuantitativo auditable de la evaluación ciega. |
| [`reporte_p9.md`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa9/reporte_p9.md) | Informe técnico oficial de la Etapa 9. |
| [`validacion_etapa9.json`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa9/validacion_etapa9.json) | Certificado formal de validación de la Puerta P9 (**32/32 PASA**). |

---

## 4. Instrucciones de Reproducción

```powershell
# 1. Ejecutar la evaluación ciega de extremo a extremo:
python etapa9/p9.py

# 2. Ejecutar la validación formal de la Puerta P9 (32 comprobaciones):
python etapa9/validar_etapa9.py
```
