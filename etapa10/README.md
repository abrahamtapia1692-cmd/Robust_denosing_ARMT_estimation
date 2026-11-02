# Etapa 10: Liberación Controlada y Trazabilidad Final (Puerta P10)

## 1. Resumen Ejecutivo y Alcance
La **Etapa 10 (Puerta P10)** constituye el hito final de cierre, certificación y liberación oficial de la suite robusta para reducción de ruido y estimación de funciones de transferencia magnetotelúricas / audiomagnetotelúricas (**ARMT/AMT/MT**), desarrollada conforme a los contratos físicos y numéricos del **Plan de Implementación v1.3**.

El propósito fundamental de esta etapa es garantizar que los modelos entrenados, el pipeline de inferencia continua, las compuertas de seguridad de dominio y los estimadores físicos de transferencia queden **estrictamente congelados, trazables criptográficamente mediante hashes SHA-256, y reproducibles por terceros independientes**. Asimismo, se implementa la exportación estándar en formato **SEG-EDI** (Wight, 1988), el formato extendido **JSON-COV** con covarianzas $4 \times 4$, la política formal de seis categorías de salida (§10.5) y el circuito de desacoplamiento seguro con reversión automática al estimador clásico Huber B0 (*fallback*).

---

## 2. Arquitectura de Salida y Contratos de Exportación

### 2.1. Formato Estándar SEG-EDI (Magnetotelúrica)
El formato SEG-EDI generado por el módulo `EmpaquetadorLiberacion` implementa la especificación formal recomendada por el *SEG Engineering and Groundwater Committee* (1987) y la *Society of Exploration Geophysicists* (Wight, 1988):
- **Bloque `>HEAD`:** Metadatos del sondeo, identificador único `DATAID`, coordenadas `LAT`, `LONG`, `ELEV`, fecha de adquisición y versión de software (`PROGVERS="P10-PACK-1.0.0"`).
- **Bloque `>INFO`:** Trazabilidad criptográfica del pipeline, hashes SHA-256 de los pesos congelados, arquitectura neuronal (CBAM ResUNet residual B4), y comentarios de categorización geofísica.
- **Bloque `>=DEFINITIONS`:** Definición del sistema de coordenadas cartesianas locales, asignación de canales magnéticos ($H_x, H_y, H_z$) y eléctricos ($E_x, E_y$), y unidades físicas de impedancia ($[\text{mV/km}]/[\text{nT}]$).
- **Sección `>FREQ`:** Lista de frecuencias evaluadas (Hz).
- **Secciones Tensoriales:** Componentes reales, imaginarias y varianzas de la matriz de impedancia:
  - `>ZXXR`, `>ZXXI`, `>ZXX.VAR`
  - `>ZXYR`, `>ZXYI`, `>ZXY.VAR`
  - `>ZYXR`, `>ZYXI`, `>ZYX.VAR`
  - `>ZYYR`, `>ZYYI`, `>ZYY.VAR`
- **Secciones Escalares:** Resistividad aparente $\rho_a$ ($\Omega\cdot\text{m}$) y fase $\phi$ (grados sexagesimales) para los modos principales:
  - `>RHOXY`, `>PHASXY`
  - `>RHOYX`, `>PHASYX`

### 2.2. Formato Extendido JSON-COV
Diseñado para enriquecer la entrega con variables que exceden el formato ASCII tradicional de SEG-EDI:
- **`provenance`:** Hash SHA-256 de los 9 archivos congelados del sistema, versión de software (`1.3.0`), fecha UTC de ejecución y metadatos de hardware.
- **`domain_governance`:** Banderas booleanas que certifican la exclusión de $D2/D3$ (`zero_d2_d3_intervention`), la ausencia de blancos de campo inventados (`zero_fake_field_targets`) y la no extrapolación fuera de soporte TEM (`zero_support_extrapolation`).
- **`window_statistics`:** Conteo riguroso de ventanas temporales (total, limpias detectadas por $C_\theta$, contaminadas intervenidas por $D_\psi$ y porcentaje de intervención).
- **`residual_decomposition`:** Verificación continua muestra a muestra del error de descomposición residual $\|x(t) - (\hat{s}(t) + \hat{n}(t))\|_\infty$.
- **`transfer_functions` (por frecuencia):**
  - Matriz de covarianza completa $4 \times 4$ de $[Z_{xx}, Z_{xy}, Z_{yx}, Z_{yy}]$.
  - Número de condición horizontal $\text{cond}(S_{HH})$ para diagnóstico de rango.
  - Coherencia multicanal $\gamma_{xy}^2$.
  - Categoría formal de salida y código de razón geofísica trazable.
  - Indicador booleano `fallback_to_b0` y justificación de reversión cuando aplique.

---

## 3. Política Formal de Seis Categorías de Salida (§10.5)

Cada estimación de transferencia se clasifica de forma determinista y auditable en una de las seis categorías reglamentadas:

| Categoría | Código de Razón | Condición Física / Numérica | Comportamiento del Sistema |
|---|---|---|---|
| **`aceptado`** | `CAT_ACCEPTED_RANK2_COHERENT` | Rango 2 ($\text{cond}(S_{HH}) \le 10^3$), coherencia $\gamma_{xy}^2 \ge 0.60$, fase física en cuadrante y soporte TEM verificado. | Transferencia candidata aprobada para inversión 1D/2D/3D. |
| **`condicional`** | `CAT_CONDITIONAL_INTERMEDIATE_QUALITY` | Coherencia intermedia ($0.20 \le \gamma_{xy}^2 < 0.60$) o soporte TEM condicional (§2.9). | Se entrega con advertencia de incertidumbre; prohibido elevar a calidad plena por suavizado. |
| **`direccional`** | `CAT_DIRECTIONAL_RANK1_POLARIZED` | Campo magnético colineal / linealmente polarizado ($\text{cond}(S_{HH}) > 10^4$, Rango 1). | Abstención de estimación tensorial 2D; cálculo limitado a modo polarizado predominante. |
| **`sin_soporte_tem`** | `CAT_UNSUPPORTED_TEM_GATE_EMPTY` | Ausencia o vacío de soporte TEM demostrable (Gate G0 / B-P0-03). | Omisión total de la red ($\hat{\mathbf{s}} \equiv \mathbf{x}$); estimación delegada exclusivamente a B0 clásico. |
| **`fuera_de_dominio_rmt`** | `CAT_OUT_OF_DOMAIN_RMT_EXCLUDED` | Frecuencias superiores a 10 kHz o bandas RMT ($D2/D3$). | Exclusión estricta; cero intervención de la red CBAM por limitación contractual de alcance. |
| **`no_identificable`** | `CAT_UNIDENTIFIABLE_SNR_DEFICIT` | Coherencia $\gamma_{xy}^2 < 0.10$, déficit severo de SNR o fase no física ($> 180^\circ$). | Rechazo de estimación; no se publica valor o se etiqueta como no identificable. |

---

## 4. Circuito de Reversión Segura a la Referencia (*Fallback B0*)

Conforme a la Puerta P10, ante cualquier evento de divergencia o comportamiento anómalo detectado durante la inferencia o estimación:
1. **Divergencia Numérica:** Impedancia nula, $\text{NaN}$ o salto de amplitud superior a $1000\times$ frente a la estimación cruda.
2. **Fase No Física:** Ángulo de fase fuera del rango físico $[-180^\circ, 180^\circ]$.
3. **Incertidumbre de Soporte:** Activación de la compuerta G0 ante registros de campo con vínculo TEM no demostrado.

**Acción de Fallback:** El empaquetador revierte automáticamente ese punto o sondeo completo a la estimación clásica robusta Huber B0 (Etapa 6), documentando el evento en el archivo JSON (`"fallback_to_b0": true`, `"fallback_reason": "..."`) y en los comentarios del archivo EDI.

---

## 5. Registro Criptográfico de Hashes Congelados

Los siguientes archivos constituyen el núcleo inmutable del sistema versionado `1.3.0`:

| Archivo / Componente | Función en el Sistema | Hash SHA-256 Congelado |
|---|---|---|
| `etapa7/checkpoints/c_theta_scnet18.pt` | Detector temporal de ruido $C_\theta$ (SCNet18) | `1e1d92b89b04afc4af6301ac0ad84c99e472161b05cb8573da5cfb90348acd08` |
| `etapa7/checkpoints/d_psi_b3_scnet18.pt` | Comparador B3 Zhang et al. (2024) | `35c5e45c9676cead3b2c32eeddf0899bfbd861072e4f514670f63fc962a25f4e` |
| `etapa7/checkpoints/d_psi_b4_cbam.pt` | Separador neuronal residual CBAM B4 $D_\psi$ | `c987c9713ce4dbcc1597b3fc956fa7bbe05c9e1e9809fd6f20599ec6dc6f7be3` |
| `etapa8/pipeline_armt.py` | Motor de inferencia continua Hanning overlap-add | `8e37cd1a23c0266697b5772633d67777c93d757d2b5e9baf6c46cdf0d4578191` |
| `etapa8/config_p8.json` | Configuración operativa de Etapa 8 | `dd197dd2d5987347548d88381a3e529edfd85259960f52f1625c5d72986e43c8` |
| `etapa9/evaluador_ciego.py` | Motor de evaluación ciega de 7 comparadores | `9499a9a38fc552774368beec71ba452e081c83ca9827a1b59c4da7d6e6207c65` |
| `etapa9/config_p9.json` | Configuración y metas preregistradas de Etapa 9 | `c24f6f755a547c4944426d91263808b7cf68dcebb99a995ec263aa164747507c` |
| `banco_sintetico/soporte_S1.json` | Soporte TEM estratificado S1 de control | `a6b50cfb1c64c832644078867f4b381802752f810e93dd41a8ba7fa12a8ffffd` |
| `etapa4/noise_episodes.csv` | Catálogo BSS multicanal de episodios de ruido | `1f3be6d1e78e3cd79e6d90ab3d29799fe41c04793143bb40741d00f13c730f69` |

---

## 6. Sondeos Oficiales de Liberación Generados

Los productos de liberación se encuentran disponibles en `etapa10/salidas/`:

1. **`SND-BLIND-01` (Control Sintético Limpio):**
   - Semiespacio homogéneo $100\ \Omega\cdot\text{m}$.
   - Demuestra no inferioridad en limpio ($0.0\%$ falsas alarmas, error nulo).
   - Archivos: [SND-BLIND-01.edi](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-BLIND-01.edi), [SND-BLIND-01.json](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-BLIND-01.json).
   - Categoría: `aceptado`.

2. **`SND-BLIND-02` (Estratificado Contaminado):**
   - Modelo $100 // 10 // 500\ \Omega\cdot\text{m}$ con inyección de ruido de campo a $0\text{ dB}$ SNR.
   - Demuestra recuperación robusta de la red CBAM B4 ($52.00\%$ error $Z$, superando ampliamente a Wiener B8 con $140.85\%$).
   - Archivos: [SND-BLIND-02.edi](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-BLIND-02.edi), [SND-BLIND-02.json](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-BLIND-02.json).
   - Categoría: `aceptado`.

3. **`SND-FIELD-EMPTY` (Campo sin Soporte TEM):**
   - Registro de campo representativo bajo la condición abierta B-P0-03.
   - Demuestra la compuerta G0: omisión total de la red CBAM ($\hat{\mathbf{s}} \equiv \mathbf{x}$), fallback seguro a B0 clásico.
   - Archivos: [SND-FIELD-EMPTY.edi](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-FIELD-EMPTY.edi), [SND-FIELD-EMPTY.json](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-FIELD-EMPTY.json).
   - Categoría: `sin_soporte_tem`.

4. **`SND-RANK1-TEST` (Control de Campo Colineal):**
   - Simulación de campo horizontal linealmente polarizado ($H_y = 0.75 H_x$, $\text{cond}(S_{HH}) = 1.67 \times 10^{16}$).
   - Demuestra detección automática de polarización y abstención tensorial.
   - Archivos: [SND-RANK1-TEST.edi](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-RANK1-TEST.edi), [SND-RANK1-TEST.json](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-RANK1-TEST.json).
   - Categoría: `direccional`.

5. **`SND-RMT-SCOPE` (Exclusión Estricta RMT):**
   - Frecuencias en bandas $D2/D3$ ($> 10\text{ kHz}$).
   - Demuestra exclusión contractual fuera de la red.
   - Archivos: [SND-RMT-SCOPE.edi](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-RMT-SCOPE.edi), [SND-RMT-SCOPE.json](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-RMT-SCOPE.json).
   - Categoría: `fuera_de_dominio_rmt`.

6. **`SND-FALLBACK-ANOMALY` (Prueba de Reversión Segura):**
   - Perturbación anómala inducida ($Z_{xy} = 10^8$) para evaluar desacoplamiento automático.
   - Demuestra activación exitosa del fallback a B0 con bandera transparente `"fallback_to_b0": true`.
   - Archivos: [SND-FALLBACK-ANOMALY.edi](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-FALLBACK-ANOMALY.edi), [SND-FALLBACK-ANOMALY.json](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-FALLBACK-ANOMALY.json).
   - Categoría: Reversión certificada.

---

## 7. Instrucciones de Reproducción por Terceros

Para reproducir de forma 100% independiente la verificación y empaquetado oficial:

```bash
# 1. Comprobar integridad de hashes y generar productos de liberacion
python etapa10/p10.py

# 2. Ejecutar la suite formal de 32 comprobaciones contractuales
python etapa10/validar_etapa10.py
```

El resultado oficial de la validación se almacena en:
- `etapa10/validacion_etapa10.json` (**32 PASA, 0 FALLA**).
- `etapa10/manifest_liberacion.json` (Manifiesto de salida con hashes SHA-256 de los 12 archivos generados).
- `etapa10/resumen_p10.json` (Resumen cuantitativo de ejecución).
- `etapa10/reporte_p10.md` (Reporte técnico final para auditoría externa).
