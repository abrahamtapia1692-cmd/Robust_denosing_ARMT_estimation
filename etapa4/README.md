# Etapa 4 — Banco de contaminantes multicanal BSS (Puertas P4 y P4-N)

**Versión del módulo:** `P4-1.0.0` · **Configuración:** `P4-CONFIG-1.0.0`  
**Extractor BSS:** `P4-EXTRACT-1.0.0` · **Validador:** `P4-VAL-1.0.0`  
**Fecha:** 29 de octubre de 2026  
**Estado:** **APROBADO** (34 comprobaciones PASA, 0 FALLA, 0 OBSERVACIONES en `validacion_etapa4.json`).

---

## 1. Objetivo y Fundamentos Teóricos

La Etapa 4 implementa la caracterización y extracción rigurosa de episodios de ruido multicanal a partir de los registros de desarrollo D0 y D1 (`ARMT5-700-14-14-01`), preservando la huella espacial, retardos, envolventes y acoplamientos entre canales ($E_x, E_y, H_x, H_y, H_z$), de acuerdo con el Plan de Implementación v1.3 (§8) y la especificación de ruido complementaria.

### Correcciones analíticas a vicios de código previo

1. **Desacople de la regla fija 2+2 (H18 y H21):**
   Se descartó la asignación heurística arbitraria de 2 componentes naturales + 2 de ruido de `FDICAReconstructor.cpp`. La cantidad de fuentes separables está acotada por el rango físico:
   $$k_{\max}(f) = C - r_s(f)$$
   donde $C$ es el número de canales informativos ($4$ u $5$) y $r_s=2$ es el rango de la excitación natural de onda plana. Las fuentes se ordenan por no-gaussianidad (curtosis excesiva).
2. **Cálculo de coherencia estadísticamente riguroso (H19):**
   Se erradicó la razón por coeficiente aislado $\frac{|X \cdot Y^*|^2}{|X|^2 |Y|^2}$ que colapsaba idénticamente a 1 fuera del piso numérico. Toda coherencia se calcula promediada en ventanas con $K_{\text{eff}}$ grados de libertad:
   $$\gamma^2_{ij}(f) = \frac{|\langle X_i(f) X_j^*(f) \rangle|^2}{\langle |X_i(f)|^2 \rangle \langle |X_j(f)|^2 \rangle}$$
   comparándose contra el nivel crítico de significancia al 95%:
   $$\gamma^2_{\text{crit}} = 1 - 0.05^{1/(K_{\text{eff}}-1)}$$
   (para $K=16 \implies \gamma^2_{\text{crit}} \approx 0.181$; para $K=64 \implies \gamma^2_{\text{crit}} \approx 0.050$).
3. **Reconstrucción física en canales de sensor:**
   Las componentes BSS normalizadas se proyectan nuevamente a las unidades físicas de campo mediante la matriz de mezcla compleja $\hat{\mathbf{n}}(t) = \mathbf{A}_n \hat{\mathbf{u}}_n(t)$, garantizando la reconstrucción identidad exacta:
   $$\|\mathbf{x}(t) - (\hat{\mathbf{s}}(t) + \hat{\mathbf{n}}(t))\| = 0 \quad (\text{error nulo } < 10^{-16})$$
4. **Subpuerta P4-N (Taxonomía de 3 niveles de evidencia):**
   Ninguna componente se admite solo por tener coherencia compartida. Se clasifica en:
   - `ruido_admitido`: Coherencia $\ge \gamma^2_{\text{crit}}$, alta curtosis ($\kappa \ge 1.2$) y fuga de señal útil $< 5\%$.
   - `candidato_o_ambiguo`: Correlación compartida con separación marginal.
   - `senal_protegida`: Componentes donde la extracción generaría fuga inaceptable de energía útil ($> 5\%$) o compatibles con la respuesta de onda plana.
5. **Control de fuga por inyección controlada:**
   Se inyecta la señal MT limpia de control generada en la Etapa 3 (`CTRL-01-HALFSPACE-D0.npz`) y se cuantifica la energía de señal útil absorbida por el estimador de ruido, exigiendo $< 5\%$ en inyecciones nominales.

---

## 2. Catálogo de Episodios Extraídos

Los episodios extraídos de `ARMT5-700-14-14-01` y catalogados en [`noise_episodes.csv`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa4/noise_episodes.csv) son:

| ID | Banda | Duración | Clase P4-N | Curtosis Máx | Coherencia Máx ($\gamma^2_{\text{crit}}$) | Fuga Señal Útil | Error Identidad |
|---|---|---:|---|---:|---:|---:|---:|
| `NOISE-D0-001` | D0 (4 kHz) | 8.0 s | `ruido_admitido` | 1.56 | 1.000 (0.017) | 0.00% | $4.97 \times 10^{-18}$ |
| `NOISE-D0-002` | D0 (4 kHz) | 10.0 s | `ruido_admitido` | 1.59 | 1.000 (0.014) | 3.19% | $4.23 \times 10^{-18}$ |
| `NOISE-D0-003` | D0 (4 kHz) | 12.0 s | `senal_protegida` | 92.29 | 1.000 (0.011) | 32.00% | $1.90 \times 10^{-17}$ |
| `NOISE-D1-004` | D1 (32 kHz) | 8.0 s | `ruido_admitido` | 1534.69 | 0.995 (0.002) | 3.22% | $1.52 \times 10^{-17}$ |

*Nota metodológica:* El episodio `NOISE-D0-003` exhibió alta curtosis pero una fuga de señal útil del 32% en inyecciones de prueba; en estricto cumplimiento de la **Subpuerta P4-N**, fue clasificado como `senal_protegida` para evitar eliminar componentes naturales durante el entrenamiento.

---

## 3. Benchmark de Fuga de Señal Útil

| Nivel de Inyección | SNR (dB) | Fuga Observada (Fracción de Energía) | Tolerancia Puerta P4 | Diagnóstico |
|---|---:|---:|---:|---|
| **Nominal (P4)** | $+10.0$ dB | **0.00%** | $\le 5.0\%$ | **PASA** |
| **Nominal (P4)** | $0.0$ dB | **0.00%** | $\le 5.0\%$ | **PASA** |
| **Estrés (§5.5)** | $-10.0$ dB | 9.67% | N/A (Estrés) | Diagnóstico de sobresupresión en ruido dominante |

---

## 4. Estructura de Artefactos

| Archivo / Carpeta | Función |
|---|---|
| `config_p4.json` | Configuración formal (`P4-CONFIG-1.0.0`) de bandas, tolerancias, splits autorizados y umbrales. |
| `extractor_ruido.py` | API BSS multicanal con cálculo riguroso de $\gamma^2(f)$, FastICA sin regla 2+2 y prueba de fuga. |
| `p4.py` | Driver CLI de extracción masiva, benchmark de inyección y generación de reportes. |
| `validar_etapa4.py` | Validador automatizado (34 comprobaciones formales de contrato, física, aislamiento y fuga). |
| `noise_episodes.csv` | Catálogo estructurado de episodios para consulta y uso en Etapa 5. |
| `noise_bank/*.npz` | Episodios multicanal almacenados con arrays de ruido, residual y matrices de mezcla $\mathbf{A}$. |
| `resumen_p4.json` | Resumen cuantitativo por episodio y resultados del benchmark. |
| `reporte_p4.md` | Informe técnico formateado. |
| `validacion_etapa4.json` | Certificado de validación formal de las Puertas P4 y P4-N. |

---

## 5. Instrucciones de Reproducción

```powershell
# 1. Ejecutar la extracción de episodios y benchmark de fuga:
python etapa4/p4.py --mode all

# 2. Ejecutar la suite de validación formal:
python etapa4/validar_etapa4.py
```
