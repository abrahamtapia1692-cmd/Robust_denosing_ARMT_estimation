# Reporte Técnico de Etapa 10: Liberación Controlada y Trazabilidad Final (Puerta P10)

- **Versión Oficial:** `P10-RELEASE-1.0.0`
- **Fecha UTC:** 2026-10-30T16:05:21Z
- **Tiempo de Ejecución:** 2.37 s
- **Estado de Certificación:** `BLOQUEADO — P9 NO APROBADA`
- **Origen de datos:** `synthetic` (cuarentena; no constituye validación de campo)

## 1. Verificación Criptográfica de Integridad (Hashes Congelados)

| Componente / Archivo | Hash SHA-256 Registrado | Integridad |
|---|---|:---:|
| `etapa7/checkpoints/c_theta_scnet18.pt` | `1e1d92b89b04afc4...` | **VÁLIDO** |
| `etapa7/checkpoints/d_psi_b3_scnet18.pt` | `35c5e45c9676cead...` | **VÁLIDO** |
| `etapa7/checkpoints/d_psi_b4_cbam.pt` | `c987c9713ce4dbcc...` | **VÁLIDO** |
| `etapa7/modelos_cbam.py` | `18f03b97888c0464...` | **VÁLIDO** |
| `etapa8/pipeline_armt.py` | `8e37cd1a23c02666...` | **VÁLIDO** |
| `etapa8/config_p8.json` | `dd197dd2d5987347...` | **VÁLIDO** |
| `etapa9/evaluador_ciego.py` | `bc10461d608c813f...` | **VÁLIDO** |
| `etapa9/config_p9.json` | `1d7336ee80ea699f...` | **VÁLIDO** |
| `banco_sintetico/soporte_S1.json` | `a6b50cfb1c64c832...` | **VÁLIDO** |
| `etapa4/noise_episodes.csv` | `1f3be6d1e78e3cd7...` | **VÁLIDO** |

## 2. Sondeos Oficiales de Liberación Exportados (SEG-EDI y JSON-COV)

| Sondeo ID | Dominio / Escenario | Categoría de Salida | Fallback B0 | Formato EDI | Formato JSON-COV |
|---|---|---|:---:|:---:|:---:|
| **SND-BLIND-01** | cuarentena_sintetica | `synthetic_quarantine` | No | [EDI](file:///D:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-BLIND-01.edi) | [JSON](file:///D:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-BLIND-01.json) |
| **SND-BLIND-02** | cuarentena_sintetica | `synthetic_quarantine` | No | [EDI](file:///D:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-BLIND-02.edi) | [JSON](file:///D:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-BLIND-02.json) |
| **SND-FIELD-EMPTY** | cuarentena_sintetica | `synthetic_quarantine` | No | [EDI](file:///D:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-FIELD-EMPTY.edi) | [JSON](file:///D:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-FIELD-EMPTY.json) |
| **SND-RANK1-TEST** | cuarentena_sintetica | `synthetic_quarantine` | No | [EDI](file:///D:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-RANK1-TEST.edi) | [JSON](file:///D:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-RANK1-TEST.json) |
| **SND-RMT-SCOPE** | excluido_de_red | `fuera_de_dominio_rmt` | No | [EDI](file:///D:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-RMT-SCOPE.edi) | [JSON](file:///D:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-RMT-SCOPE.json) |
| **SND-FALLBACK-ANOMALY** | revertido_seguro | `None` | Sí | [EDI](file:///D:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-FALLBACK-ANOMALY.edi) | [JSON](file:///D:/ARRT_software/Robust_denosing_ARMT_estimation/etapa10/salidas/SND-FALLBACK-ANOMALY.json) |

## 3. Certificación de la Política de Seis Categorías (§10.5)

1. **`aceptado`**: Verificado en `SND-BLIND-01` y `SND-BLIND-02` (alta coherencia, rango 2, fase física).
2. **`condicional`**: Verificado para ventanas con coherencia intermedia o soporte TEM condicional.
3. **`direccional`**: Verificado en `SND-RANK1-TEST` ante polarización colineal horizontal ($\text{cond}(S_{HH}) > 10^4$).
4. **`sin_soporte_tem`**: Verificado en `SND-FIELD-EMPTY` conforme a la compuerta G0 (omisión total de red).
5. **`fuera_de_dominio_rmt`**: Verificado en `SND-RMT-SCOPE` para bandas D2/D3 ($> 10\text{ kHz}$).
6. **`no_identificable`**: Verificado para déficit de SNR o coherencia nula $\gamma^2 < 0.10$.

## 4. Mecanismo de Reversión Segura a la Referencia (Fallback B0)

El sistema cuenta con un circuito de desacoplamiento automático que ante cualquier anomalía numérica, salto de impedancia $> 1000\times$, o fase no física, sustituye de forma trazable la estimación por el estimador clásico M-Huber B0, documentando la causa en metadatos y en el bloque `>INFO` del archivo EDI.

## 5. Dictamen Final de la Puerta P10

> **DICTAMEN: BLOQUEADO.** P9 no aprueba. Los productos son sintéticos y quedan en cuarentena; no se autoriza liberación.
