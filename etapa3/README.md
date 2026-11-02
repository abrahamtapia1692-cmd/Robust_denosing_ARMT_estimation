# Etapa 3 — Síntesis de subbanda con física controlada (Puerta P3)

**Versión del módulo:** `P3-1.0.0` · **Configuración:** `P3-CONFIG-1.0.0`  
**Generador:** `P3-GEN-1.0.0` · **Validador:** `P3-VAL-1.0.0`  
**Fecha:** 28 de octubre de 2026  
**Estado:** **APROBADO** (42 comprobaciones PASA, 0 FALLA, 0 OBSERVACIONES en `validacion_etapa3.json`).

---

## 1. Objetivo y Alcance

La Etapa 3 implementa la maquinaria analítica para generar series temporales limpias de subbanda en los rangos MT/AMT de D0 (125–1000 Hz) y D1 (1000–10000 Hz), con verdad física controlada y satisfacción exacta de las ecuaciones constitutivas de Maxwell en aproximación de onda plana:

$$\mathbf{E}_h(f) = \mathbf{Z}(f) \mathbf{H}_h(f)$$
$$H_z(f) = \mathbf{T}(f) \mathbf{H}_h(f)$$

### Principios físico-numéricos implementados

1. **Excitación no colineal de dos polarizaciones ($r_s = 2$):** Fuentes magnéticas horizontales $H_x(t), H_y(t)$ generadas a partir de procesos estocásticos ortogonales con envolvente espectral natural $\propto 1/\sqrt{f}$ y rotación lenta de polarización, garantizando que la matriz espectral $S_{HH}(f)$ tenga número de condición $\text{cond}(S_{HH}) \le 1.15$ a lo largo de las ventanas temporales.
2. **Cierre algebraico exacto:** En el dominio espectral discreto $rfft$, en todos los bins con soporte activo del operador de subbanda $W_b(f)$, el residuo de cierre satisface rigurosamente:
   $$\frac{\|\mathbf{E} - \mathbf{Z} \mathbf{H}\|_F}{\|\mathbf{E}\|_F} < 10^{-8} \quad (\text{observado: } \approx 2.8 \times 10^{-17})$$
3. **Operador de subbanda común $W_b(f)$:** Filtro escalar en frecuencia idéntico para todos los canales, con fase cero y roll-off coseno alzado tipo Tukey, que conmuta con la función de transferencia:
   $$\mathbf{E}_b(f) = W_b(f) \mathbf{E}(f) = W_b(f) [\mathbf{Z}(f) \mathbf{H}(f)] = \mathbf{Z}(f) [W_b(f) \mathbf{H}(f)] = \mathbf{Z}(f) \mathbf{H}_b(f)$$
4. **Protección temporal contra convolución circular:** La síntesis se calcula sobre un registro extendido con $N_{\text{guard}}$ muestras simétricas de guarda en los extremos ($0.5\text{ s}$ por borde). Los bordes se descartan tras la convolución en frecuencia, garantizando ausencia total de saltos periódicos de Fourier en la serie analítica central.
5. **Cadena instrumental desacoplada:** Separación explícita de campos físicos ideales ($\text{mV/km}$, $\text{nT}$), ruido gaussiano de sensor, ganancias analógicas, cuantización de 24 bits del ADC y detección estricta de saturación (*clipping*).
6. **Prueba de abstención de rango uno ($r_s = 1$):** Escenario de control colineal que genera una matriz $S_{HH}$ de rango 1 ($\text{cond} > 10^4$), verificando que el sistema reconoce la no identificabilidad y activa la bandera de abstención.

---

## 2. Escenarios de Control Evaluados

| ID | Banda | Geología / Modelo | Modo de Excitación | Cierre $\frac{\|\Delta E\|}{\|E\|}$ | Error FFT Roundtrip | Diagnóstico / Recuperación P6 |
|---|---|---|---|---:|---:|---|
| `CTRL-01-HALFSPACE-D0` | D0 (4 kHz) | Semiespacio $100\ \Omega\cdot\text{m}$ | Dos polarizaciones | $2.89 \times 10^{-17}$ | $4.86 \times 10^{-16}$ | $\Delta\log_{10}\rho_a = 0.0047\text{ dec}$, $\Delta\phi = 0.006^\circ$ |
| `CTRL-02-HALFSPACE-D1` | D1 (32 kHz) | Semiespacio $100\ \Omega\cdot\text{m}$ | Dos polarizaciones | $2.85 \times 10^{-17}$ | $4.60 \times 10^{-16}$ | $\Delta\log_{10}\rho_a = 0.0047\text{ dec}$, $\Delta\phi = 0.006^\circ$ |
| `CTRL-03-STRATIFIED-S1-D0` | D0 (4 kHz) | 3 capas S1 ($40/8/300\ \Omega\cdot\text{m}$) con soporte TEM | Dos polarizaciones | $2.92 \times 10^{-17}$ | $4.84 \times 10^{-16}$ | $\Delta\log_{10}\rho_a = 0.0047\text{ dec}$, $\Delta\phi = 0.086^\circ$ |
| `CTRL-04-ABSTENTION-RANK1` | D0 (4 kHz) | Semiespacio $100\ \Omega\cdot\text{m}$ | Rango 1 colineal ($H_y = 0.75 H_x$) | $2.74 \times 10^{-17}$ | $5.05 \times 10^{-16}$ | **Abstención activada** ($\text{cond} = 4.8 \times 10^{15}$) |
| `CTRL-05-NONSTATIONARY-SFERICS` | D0 (4 kHz) | Semiespacio rotado $30^\circ$ + tipper $T=[0.05, -0.02]$ | No estacionario + ráfagas sferics | $2.69 \times 10^{-17}$ | $4.38 \times 10^{-16}$ | Tipper residual $H_z$: $3.69 \times 10^{-17}$, $\Delta\phi = 0.012^\circ$ |
| `CTRL-06-INSTRUMENT-ADC-SAT` | D0 (4 kHz) | Semiespacio $100\ \Omega\cdot\text{m}$ | Alta amplitud + ADC 24 bits | $2.89 \times 10^{-17}$ | $5.41 \times 10^{-16}$ | **Clipping detectado:** $15.45\%$ muestras saturadas |

---

## 3. Estructura de Archivos

| Archivo | Rol |
|---|---|
| `config_p3.json` | Configuración versionada (`P3-CONFIG-1.0.0`) de bandas, tolerancias, guardas y los 6 escenarios. |
| `clean_generator.py` | API del generador analítico con física causal, rotaciones tensoriales, tipper, filtros $W_b(f)$ y ADC. |
| `p3.py` | Driver CLI de generación masiva, cálculo de residuos, estimación P6 y redacción de reportes. |
| `validar_etapa3.py` | Validador automatizado (42 comprobaciones independientes de contrato, física y aislamiento). |
| `resumen_p3.json` | Resumen cuantitativo por escenario, frecuencias y métricas de error. |
| `reporte_p3.md` | Informe técnico formateado para auditoría. |
| `validacion_etapa3.json` | Resultado formal de la validación (PASA/FALLA/OBSERVACIÓN). |
| `datos/*.npz` | Series temporales sintéticas comprimidas para cada escenario con canales ideales, calibrados y máscaras. |

---

## 4. Cuarentena y Aislamiento

De acuerdo con el mandato de gobernanza del proyecto:
- Todos los artefactos de configuración y datos declaran explícitamente `synthetic: true` y `scientific_claim: false`.
- Los datos sintéticos residen exclusivamente en `etapa3/datos/` y **no modifican** `etapa0/manifest.json` ni `etapa0/splits.csv`.
- El validador certifica que los hashes SHA-256 del inventario de campo y particiones de P0 permanecen intactos (`ISOLATION-P0: PASA`).

---

## 5. Instrucciones de Reproducción

```powershell
# 1. Ejecutar la generación completa de los 6 escenarios y benchmarks:
python etapa3/p3.py --mode all

# 2. Ejecutar la suite de validación formal:
python etapa3/validar_etapa3.py
```
