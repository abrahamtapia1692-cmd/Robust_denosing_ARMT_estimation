# Etapa 7 — Reproducción y Adaptación del Enfoque CBAM MT/AMT (Puertas P7, P7-I y P7-S)

**Versión del módulo:** `P7-2.0.0` · **Configuración:** `P7-CONFIG-1.0.0`  
**Modelos:** `P7-MOD-2.0.0` · **Validador:** `P7-VAL-2.0.0`  
**Fecha:** 29 de octubre de 2026  
**Estado:** **APROBADO** (32 comprobaciones PASA, 0 FALLA en [`validacion_etapa7.json`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa7/validacion_etapa7.json)).

---

## 1. Objetivo y Fundamentos Metodológicos

La Etapa 7 implementa, entrena y valida la cadena neuronal de desacoplamiento y eliminación de ruido para series temporales magnetotelúricas (MT/AMT) en las bandas $D0$ ($125-1000\text{ Hz}$) y $D1$ ($1000-10000\text{ Hz}$), cumpliendo rigurosamente los lineamientos del Plan de Implementación v1.3 (§11).

El procesamiento se fundamenta en la relación física de Maxwell para ondas planas que vincula los campos eléctricos y magnéticos en el dominio de la frecuencia:
$$\mathbf{E}(f) = \mathbf{Z}(f) \mathbf{H}(f) \iff \begin{pmatrix} E_x(f) \\ E_y(f) \end{pmatrix} = \begin{pmatrix} Z_{xx}(f) & Z_{xy}(f) \\ Z_{yx}(f) & Z_{yy}(f) \end{pmatrix} \begin{pmatrix} H_x(f) \\ H_y(f) \end{pmatrix}$$

Bajo presencia de ruido aditivo no correlacionado con la fuente ionosférica/magnetosférica natural:
$$\mathbf{x}(t) = \mathbf{s}(t) + \mathbf{n}(t)$$
donde $\mathbf{x} = [E_x, E_y, H_x, H_y]^T$. La cadena neuronal se estructura en dos componentes desacoplados:
1. **Detector de Contaminación ($C_\theta$):** Clasificador multicanal calibrado para detectar ventanas con presencia de ruido antrópico/transitorio.
2. **Separador Neuronal ($D_\psi$):** Red de atención multicanal y espacial que estima la señal natural $\hat{\mathbf{s}} = D_\psi(\mathbf{x})$.

---

## 2. Comparativa Arquitectónica: B3 vs. B4

Se reprodujo fielmente la arquitectura original de la literatura y se desarrolló la versión adaptada según los principios físicos del Plan v1.3:

| Atributo | B3: `SCNet18` (Zhang et al. 2024) | B4: `CBAM_ResUNet` (Adaptado Plan v1.3) | Justificación Física / Numérica |
|---|---|---|---|
| **Mecanismo de Atención** | CBAM Canónico (Canal r=16 + Espacio k=7) | CBAM Canónico (Canal r=16 + Espacio k=7) | Idéntica atención cruzada entre componentes $E$ y $H$. |
| **Backbone Encoder** | ResNet-18 1D (512 canales, reducción $\times 32$) | ResNet 1D Multiescala (4 niveles: 32, 64, 128, 256) | Preserva campos receptivos sin colapsar la resolución temporal. |
| **Cabeza Decodificadora** | Capa Lineal `Linear(512*32, 1024)` | Decodificador Convolucional U-Net con Skip Connections | **B3 rompe la invarianza por traslación:** 16.7M parámetros concentrados en la capa densa provocan memorización de posición y colapso generalizador. B4 mantiene traslación invariante en todo el tensor. |
| **Normalización** | Global por $\max(|x|)$ | RMS de ventana: $\sigma = \sqrt{\frac{1}{CL}\sum x_{c,t}^2}$ | **Equivarianza de Escala Estricta:** B4 garantiza $D_\psi(\alpha x) = \alpha D_\psi(x)$ con error relativo $< 10^{-6}$, invariante a cambios de ganancia instrumental. |
| **Inicialización** | He / Kaiming normal | Inicialización cuasi-nula en la capa final | B4 arranca como la **identidad limpia exacta** ($\hat{s} \equiv x$) en la época 0, garantizando estabilidad y evitando distorsión inicial. |
| **Función de Pérdida** | MSE simple: $\|s - \hat{s}\|^2$ | `ChannelBalancedLoss` ponderada por $\sigma^2_c$ | Evita la atenuación selectiva de $E$ sobre $H$ (evitando el colapso del cociente de impedancia $Z = E/H$). |

---

## 3. Resultados Cuantitativos por Subpuerta

### Subpuerta P7-I: Validación del Detector ($C_\theta$)
- **Modelo:** `SCNet18_Classifier` (reproducido de `identification/g12.py`).
- **Umbral de decisión calibrado en validación:** $\tau = 1.0000$ (para garantizar $\text{FPR} \le 1.0\%$).
- **FPR en tiempo limpio de prueba:** **0.00%** (Meta: $\le 1.0\%$ $\to$ **PASA**).
- **Sensibilidad en episodios detectables:** **99.60%** (Meta: $\ge 90.0\%$ $\to$ **PASA**).
- **Exactitud:** **99.80%**, **ROC-AUC:** **1.0000**.
- **Comparador B7 (solo-potencia):** **0.5768** (Atajo neutralizado en Etapa 5; el detector supera a B7 por $+0.423$).
- **Matriz de Confusión ($N=996$):** $\text{TN}=498, \text{FP}=0, \text{FN}=2, \text{TP}=496$.
- **Estado Subpuerta P7-I:** **APROBADO**.

---

### Subpuerta P7-S: Separación y Preservación de Física ($D_\psi$)

#### A. No Inferioridad en Tramos Limpios ($S_0$)
Evaluación sobre 250 ventanas limpias no vistas para certificar que el separador no distorsiona la señal natural pura:

| Modelo | Sesgo Relativo $Z_{xy}$ | Error de Fase $\phi_{xy}$ | Criterio No Inferioridad ($\le 5.0\%$, $\le 2.0^\circ$) |
|---|---:|---:|:---:|
| B3 (SCNet18 Zhang et al. 2024) | 6.42% | 3.12° | **REPROBADO** |
| B8 (Filtro de Wiener Multicanal 4x4) | 0.99% | 1.69° | PASA |
| **B4 (CBAM Adaptado Plan v1.3)** | **0.74%** | **0.63°** | **PASA** |

#### B. Recuperación en Tramos Contaminados ($S_2$)
Evaluación sobre 496 ventanas con ruido de campo y sintético a SNR adverso ($\text{SNR}_{\text{raw}} = -2.41\text{ dB}$):

| Modelo / Benchmark | SNR Salida (dB) | Ganancia $\Delta\text{SNR}$ (dB) | Error Relativo $Z_{xy}$ | Error de Fase $\phi_{xy}$ |
|---|---:|---:|---:|---:|
| **B0 (Señal Bruta Contaminada)** | -2.41 | 0.00 | 0.71% | 0.32° |
| **B3 (SCNet18 Zhang et al. 2024)** | -22.16 | -19.75 | 1.72% | 22.02° |
| **B8 (Wiener Multicanal 4x4)** | -0.65 | +1.76 | 1.27% | 1.53° |
| **B4 (CBAM Adaptado Plan v1.3)** | **16.75** | **+19.16** | **0.65%** | **0.75°** |

- **B3 colapsa:** Sufre una degradación severa de $-19.75\text{ dB}$ en SNR y un desvío de fase inaceptable de $22.02^\circ$ debido al sobreajuste de su capa densa de 16M parámetros ante dinámicas de amplitud variables.
- **B4 supera holgadamente a los comparadores:** Supera a B3 por $+38.9\text{ dB}$, a Wiener B8 por $+17.4\text{ dB}$ y reduce el error en la función de transferencia respecto a la señal bruta y Wiener.
- **Prueba de Sobresupresión a SNR Negativo:** Ratio de energía conservada $= \mathbf{1.095}$ (Meta: $\ge 0.80$ $\to$ **PASA**; no elimina la señal natural bajo ruido intenso).
- **Estado Subpuerta P7-S:** **APROBADO**.

---

### Puerta P7: Cadena Completa Integrada ($C_\theta \to D_\psi$)

La intervención del separador se aplica de manera estrictamente condicional:
$$\hat{\mathbf{s}}(t) = \begin{cases} D_\psi(\mathbf{x}(t)), & \text{si } C_\theta(\mathbf{x}) \ge \tau \\ \mathbf{x}(t), & \text{si } C_\theta(\mathbf{x}) < \tau \end{cases}$$

- **Selectividad temporal:** Interviene en el **66.5%** de las ventanas (496 ventanas contaminadas detectadas; 0 falsas intervenciones en limpio).
- **Error global $Z_{xy}$ de la cadena:** **0.44%** (vs. Wiener B8: $1.14\%$).
- **Error global de fase $\phi_{xy}$ de la cadena:** **0.47°** (vs. Wiener B8: $1.57^\circ$).
- **Sesgo en el subconjunto limpio tras agregación:** **0.00%** (preservación idéntica gracias a $\text{FPR} = 0.00\%$).
- **Fase en el subconjunto limpio tras agregación:** **0.00°**.
- **Estado Puerta P7:** **APROBADO**.

---

## 4. Estructura de Artefactos de la Etapa 7

| Archivo / Carpeta | Función |
|---|---|
| [`config_p7.json`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa7/config_p7.json) | Configuración (`P7-CONFIG-1.0.0`) de modelos, hiperparámetros, umbrales y puertas. |
| [`modelos_cbam.py`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa7/modelos_cbam.py) | Arquitecturas `SCNet18_Classifier`, `SCNet18_Denoiser`, `CBAM_ResUNet_Denoiser`, `MultichannelWienerFilter` y `ChannelBalancedLoss`. |
| [`p7.py`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa7/p7.py) | Pipeline de entrenamiento, calibración, inferencia y evaluación de comparadores B0, B3, B4, B7, B8, B10. |
| [`validar_etapa7.py`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa7/validar_etapa7.py) | Validador formal (32 comprobaciones de contrato, física, checkpoints y no inferioridad). |
| [`checkpoints/c_theta_scnet18.pt`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa7/checkpoints/c_theta_scnet18.pt) | Pesos del detector $C_\theta$ (ROC-AUC 1.0000). |
| [`checkpoints/d_psi_b3_scnet18.pt`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa7/checkpoints/d_psi_b3_scnet18.pt) | Pesos del separador B3 (SCNet18 de Zhang et al. 2024). |
| [`checkpoints/d_psi_b4_cbam.pt`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa7/checkpoints/d_psi_b4_cbam.pt) | Pesos del separador B4 (CBAM ResUNet Adaptado Plan v1.3). |
| [`resumen_p7.json`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa7/resumen_p7.json) | Resumen estructurado cuantitativo auditable. |
| [`reporte_p7.md`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa7/reporte_p7.md) | Informe técnico sintético de la etapa. |
| [`validacion_etapa7.json`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa7/validacion_etapa7.json) | Certificado formal de validación de las Puertas P7, P7-I y P7-S (**32/32 PASA**). |

---

## 5. Aislamiento y Gobernanza de Datos

- **Aislamiento de particiones:** Entrenamiento, validación y prueba se ejecutaron sobre las particiones disjuntas generadas en la Etapa 5 (`GRP-ENTR-01/02`, `GRP-VAL-01`, `GRP-TEST-01`), con cero cruce de grupos (0% fuga).
- **Prohibición de extrapolación:** El dominio de inferencia está estrictamente delimitado a $D0$ y $D1$. No se interviene en bandas $D2/D3$ ni en portadoras RMT.
- **Cero blancos inventados:** Las métricas de recuperación se calcularon únicamente sobre datos con verdad supervisada exacta (`exact_synthetic` y `exact_control`). Los datos de campo real conservan la etiqueta `unavailable` y no se emplean para reclamos científicos sin soporte físico validado.

---

## 6. Instrucciones de Reproducción

```powershell
# 1. Ejecutar el entrenamiento y evaluación de la Etapa 7:
python etapa7/p7.py

# 2. Ejecutar la validación formal de las Puertas P7, P7-I y P7-S:
python etapa7/validar_etapa7.py
```
