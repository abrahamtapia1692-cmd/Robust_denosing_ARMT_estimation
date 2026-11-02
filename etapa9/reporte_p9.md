# Reporte Técnico de Etapa 9: Evaluación Ciega de Extremo a Extremo (Puerta P9)

- **Versión:** `P9-2.0.0`
- **Fecha UTC:** 2026-10-30T16:04:40Z
- **Naturaleza de los datos:** **sintético** (`synthetic: true`, `scientific_claim: false`)
- **Modelo de verdad:** `etapa3/config_p3.json` → $\rho=[40.0, 8.0, 300.0]$, interfaces=[30.0, 120.0]$
- **Semilla:** `20261030`
- **Compuerta de Seguridad G4:** `BLOQUEADO`
- **Estado Puerta P9:** `BLOQUEADO`

## 1. Tabla Comparativa de Benchmarks (SND-BLIND-02 Estratificado)

| Benchmark | Tipo | Mediana Err Z (%) | Mediana Err ρa (dec) | Mediana Err Fase (°) | P90 Err ρa (dec) | P90 Err Fase (°) |
|---|---|---:|---:|---:|---:|---:|
| **B0** | Datos calibrados + estimador robusto Huber | 1.24% | 0.0077 | 0.24° | 0.0224 | 0.86° |
| **B1** | Pre-QC espectral + estimador robusto | 1.18% | 0.0069 | 0.30° | 0.0225 | 0.90° |
| **B3** | SCNet18 reproducido (Zhang et al. 2024) | 242.90% | 0.9009 | 77.44° | 1.3230 | 210.47° |
| **B4** | CBAM Adaptado Plan v1.3 (CBAM_ResUNet) | 36.57% | 0.2638 | 1.84° | 0.5525 | 4.40° |
| **B8** | Filtro multicanal de Wiener 4x4 (cota analítica lineal) | 1.35% | 0.0084 | 0.21° | 0.0187 | 1.00° |
| **B10** | Oráculo de ruido y máscara ideal | 0.42% | 0.0037 | 0.02° | 0.0166 | 0.24° |

- **B4 forzado sobre todas las ventanas (`denoise_all`):** Z=65.26%, ρa=0.4264 dec, fase=2.52°
- **B7 (AUC solo-potencia):** 1.0000 (meta ≤ 0.65)
- **Ventanas intervenidas por B4 (auto):** 50.3%

## 2. Métricas frente a Metas Preregistradas

| Criterio Físico / Numérico | Meta Preregistrada (P9) | Valor Observado | Estado |
|---|---|---|:---:|
| No inferioridad en limpio (P95 sesgo Z) | $\le 2.0\%$ | **2.1990%** | **FALLA** |
| No inferioridad en limpio (P95 fase) | $\le 1.0^\circ$ | **1.1072°** | **FALLA** |
| Recuperación con ruido (mediana $\rho_a$) | $\le 0.05\text{ dec}$ | **0.2638 dec** | **FALLA** |
| Recuperación con ruido (mediana fase) | $\le 3.0^\circ$ | **1.84°** | **PASA** |
| Mejora de impedancia vs B0 | $\ge 20.0\%$ | **-2844.90%** | **FALLA** |
| Control de atajo B7 (AUC solo-potencia) | $\le 0.65$ | **1.0000** | **FALLA** |
| Tasa de falsa recuperación | $\le 5.0\%$ | **0.0%** | **PASA** |
| Sondeo SND-BLIND-01 limpio | Todos los criterios | **—** | **FALLA** |
| Sondeo SND-BLIND-02 estratificado | Todos los criterios | **—** | **FALLA** |
| Sondeo SND-BLIND-03 sferics | Todos los criterios | **—** | **FALLA** |
| Sondeo SND-BLIND-04 textura F1 | Todos los criterios | **—** | **PASA** |
| Sondeo Sondeos no identificables | Todos los criterios | **—** | **PASA** |

## 3. Comparadores

- **Evaluados:** `['B0', 'B1', 'B10', 'B3', 'B4', 'B7', 'B8', 'B9']`
  - `B2`: Requiere separacion BSS por registro no congelada en etapa4
  - `B5`: Depende de B2
  - `B6`: No existe referencia remota en el conjunto actual
- **B9 (ruido independiente NOISE-D0-003):** B0=6.06%, B4=68.49%

## 4. Conclusiones

1. **La puerta P9 NO se aprueba.** Uno o más endpoints preregistrados no se cumplen.
2. El pipeline **no debe liberarse** ni declararse recuperación de datos.
3. Los productos de Etapa 10 quedan en cuarentena sintética.
