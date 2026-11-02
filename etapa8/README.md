# Etapa 8 — Integración de Inferencia MT/AMT con Soporte Parcial (Puerta P8)

**Versión del módulo:** `P8-2.0.0` · **Configuración:** `P8-CONFIG-1.0.0`  
**Pipeline:** `P8-PIPE-1.0.0` · **Validador:** `P8-VAL-2.0.0`  
**Fecha:** 29 de octubre de 2026  
**Estado:** **APROBADO** (32 comprobaciones PASA, 0 FALLA en [`validacion_etapa8.json`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa8/validacion_etapa8.json)).

---

## 1. Objetivo y Fundamentos Metodológicos

La Etapa 8 implementa la integración completa de la inferencia continua sobre registros de series temporales magnetotelúricas (MT/AMT) en las bandas $D0$ ($125-1000\text{ Hz}$) y $D1$ ($1000-10000\text{ Hz}$), cumpliendo estrictamente los requisitos teóricos y físicos del Plan de Implementación v1.3 (§12).

### Principios Fundamentales del Pipeline Integrado:
1. **Resolución de Soporte y Compuerta G0 (§8.1, §8.7):**
   - Antes de invocar la red neuronal, el pipeline resuelve la máscara de frecuencias autorizadas $F_{\text{aplicacion}}(s, b)$ a partir del soporte TEM verificado (catálogo [`tem_amt_support.csv`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa2/tem_amt_support.csv) o soporte sintético certificado).
   - **Regla de Soporte Vacío:** Si el soporte TEM es nulo o no verificado (como en los sondeos de campo actuales debido a la observación `B-P0-03`), el pipeline **omite la red neuronal por completo** (`network_omitted = True`), no altera la señal de entrada ($\hat{\mathbf{s}} \equiv \mathbf{x}, \hat{\mathbf{n}} \equiv \mathbf{0}$) y recurre al estimador robusto de referencia P6.
   - En soporte parcial (p. ej. `CTRL-03` con soporte $S_1$ en $D0$), la inferencia se activa y la respuesta final se calcula únicamente en las 33 frecuencias respaldadas.
2. **Exclusión Estricta de RMT (§8.3):**
   - Las bandas de radio-magnetotelúrica ($D2$ y $D3$, $10\text{ kHz}-4\text{ MHz}$) y las portadoras RMT quedan **estrictamente excluidas** de la red neuronal CBAM por diseño físico.
   - Cualquier intento de procesamiento en $D2/D3$ activa la compuerta de exclusión (`support_status: "excluido_rmt"`), retornando la señal intacta con residual cero.
3. **Recomposición Temporal Continua por Hanning Overlap-Add (§8.1, §8.5):**
   - El registro continuo se segmenta en ventanas de longitud $L=256$ con paso $S=128$ (solapamiento al $50\%$).
   - La síntesis continua se realiza ponderando cada ventana por un taper de Hann periódico $w[n]$ y normalizando por el acumulador de pesos:
     $$\hat{\mathbf{s}}(t) = \frac{\sum_k w_k(t) \cdot \hat{\mathbf{s}}_k(t)}{\sum_k w_k(t)}$$
   - Esto garantiza que en tramos limpios o de identidad, la reconstrucción es **idéntica a la entrada** hasta precisión de máquina ($\|x - \hat{s}\|_\infty < 10^{-15}$) y proporciona una transición suave $C^1$ **sin discontinuidades ni saltos de costura** en los bordes de ventana.
4. **Cadena Condicional $C_\theta \to D_\psi$ con Selectividad Temporal (§7.9, §8.2):**
   - El detector calibrado $C_\theta$ evalúa cada ventana con umbral $\tau = 1.0000$.
   - En ventanas clasificadas como limpias ($C_\theta < \tau$), se preserva la entrada exacta ($\hat{\mathbf{s}}_k = \mathbf{x}_k$).
   - En ventanas contaminadas ($C_\theta \ge \tau$), se aplica el separador adaptado $D_\psi$.
   - Se obtiene la descomposición continua aditiva exacta muestra a muestra:
     $$\mathbf{x}(t) \equiv \hat{\mathbf{s}}(t) + \hat{\mathbf{n}}(t)$$
5. **Detección de Rango 1 y Abstención (§8.4):**
   - Cuando el campo magnético horizontal está linealmente polarizado (número de condición de $S_{HH} > 10^4$), el tensor $2 \times 2$ no es identificable. El pipeline activa la bandera de abstención (`rango_1_abstencion`) en lugar de inventar una impedancia espuria.
6. **Guardas Temporales de Borde (§8.2):**
   - Se descartan $0.5\text{ s}$ en cada extremo del registro para la estimación espectral, absorbiendo posibles transitorios de convolución.

---

## 2. Resultados de los Escenarios Evaluados

La evaluación se ejecutó sobre la suite completa de 7 escenarios físicos y numéricos:

| Escenario | Registro / Configuración | Criterio de Aceptación | Resultado Observado | Estado |
|---|---|---|---|:---:|
| **1. Soporte Parcial Contaminado** | `CTRL-03` ($D0$) + Ruido de campo `NOISE-D0-001` inyectado (4–12 s) | Selectividad temporal perfecta; $\Delta\text{SNR} > +10.0\text{ dB}$ | Prefijo limpio: `0/120` intervenciones<br>Contaminado: `245/245` detectados (`100%`)<br>Sufijo limpio: `0/124` intervenciones<br>Ganancia: **+13.73 dB** | **PASA** |
| **2. No Inferioridad Limpio** | `CTRL-01` ($D0$) continuo sin ruido | Sesgo $Z_{xy} \le 5.0\%$, Fase $\le 2.0^\circ$ | Sesgo $Z_{xy}$: **0.0000%**<br>Error de fase: **0.0000°** | **PASA** |
| **3. Compuerta G0 Soporte Vacío** | `CTRL-01` ($D0$) + `soporte_S0.json` (vacío) | Red omitida; $\hat{\mathbf{s}} \equiv \mathbf{x}$, $\hat{\mathbf{n}} \equiv \mathbf{0}$ | `network_omitted: true`<br>$\|x - \hat{s}\|_\infty = 0.0$, $\|\hat{n}\|_\infty = 0.0$ | **PASA** |
| **4. Campo Sin Vínculo TEM** | `ARMT5-123-01-01-01` ($D0$, campo real) | Red omitida; caída a referencia P6 | `support_status: "soporte_vacio"`<br>`network_omitted: true` | **PASA** |
| **5. Exclusión Estricta RMT** | Registros en bandas $D2$ y $D3$ | Bloqueo absoluto de CBAM; señal intacta | Bandas $D2$ y $D3$ marcadas `excluido_rmt`<br>Cero intervención ($\|x - \hat{s}\|_\infty = 0.0$) | **PASA** |
| **6. Detección Rango 1** | `CTRL-04` (colineal $H_y = 0.75 H_x$) | $\text{cond}(S_{HH}) > 10^4 \implies$ abstención | $\text{cond}(S_{HH}) = 1.67 \times 10^{16}$<br>Abstención: **3/3 frecuencias (100%)** | **PASA** |
| **7. Invarianza y Reconstrucción** | Invarianza lote 1 vs 32; Identidad | Diferencia lote $< 10^{-5}$<br>Error identidad $< 10^{-12}$ | Diferencia lote: **$5.25 \times 10^{-6}$**<br>Error identidad: **$8.88 \times 10^{-16}$**<br>Residual $x = \hat{s} + \hat{n}$: **$2.22 \times 10^{-16}$** | **PASA** |

---

## 3. Estructura de Artefactos de la Etapa 8

| Archivo | Descripción |
|---|---|
| [`config_p8.json`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa8/config_p8.json) | Configuración formal (`P8-CONFIG-1.0.0`) de bandas, modelos, parámetros de ventaneo y escenarios. |
| [`pipeline_armt.py`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa8/pipeline_armt.py) | Módulo central con clase `ARMTPipeline`: soporte, ventaneo Hanning overlap-add, inferencia y M-estimador P6. |
| [`p8.py`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa8/p8.py) | Driver de ejecución y evaluación integral de los 7 escenarios de prueba. |
| [`validar_etapa8.py`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa8/validar_etapa8.py) | Validador formal independiente con 32 comprobaciones de contrato, física y gobernanza. |
| [`resumen_p8.json`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa8/resumen_p8.json) | Resumen estructurado cuantitativo auditable de la ejecución. |
| [`reporte_p8.md`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa8/reporte_p8.md) | Informe técnico sintético de la etapa. |
| [`validacion_etapa8.json`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa8/validacion_etapa8.json) | Certificado formal de validación de la Puerta P8 (**32/32 PASA**). |

---

## 4. Gobernanza y Cumplimiento de Contratos

- **Dominio de inferencia acotado:** La inferencia neuronal opera exclusivamente sobre subbandas MT/AMT autorizadas ($D0$ y $D1$). Las bandas $D2/D3$ quedan completamente blindadas.
- **Compuerta G0 infranqueable:** No se inventan blancos ni se aplican redes neuronales a ciegas sobre datos de campo sin soporte TEM certificado; en tales casos el sistema se abstiene de intervenir y recurre al estimador clásico de referencia.
- **Aislamiento de particiones:** La evaluación continua utilizó modelos y pesos congelados de la Etapa 7 sin reentrenamiento sobre los datos de prueba.

---

## 5. Instrucciones de Reproducción

```powershell
# 1. Ejecutar la suite de evaluación continua de Etapa 8:
python etapa8/p8.py

# 2. Ejecutar la validación formal de la Puerta P8 (32 comprobaciones):
python etapa8/validar_etapa8.py
```
