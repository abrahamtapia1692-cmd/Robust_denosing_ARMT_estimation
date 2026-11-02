# Reporte de Validación — Puerta P3: Síntesis de Subbanda Limpia

- **Versión:** `P3-1.0.0` (Generador: `P3-GEN-1.0.0`)
- **Fecha (UTC):** 2026-10-29T00:35:11.014392Z
- **Estado global:** **APROBADO**

## 1. Resumen de Ejecución y Métricas Críticas

| Escenario | Banda | Modo de Excitación | Residuo Espectral $\|E - ZH\| / \|E\|$ | Error FFT Roundtrip | Diagnóstico / Estimador |
|---|---|---|---:|---:|---|
| `CTRL-01-HALFSPACE-D0` | D0 | Semiespacio 100 ohm.m en D0 | 2.89e-17 | 4.86e-16 | Bias ρa: 0.0047 dec, Fase: 0.01° |
| `CTRL-02-HALFSPACE-D1` | D1 | Semiespacio 100 ohm.m en D1 | 2.85e-17 | 4.60e-16 | Bias ρa: 0.0028 dec, Fase: 0.00° |
| `CTRL-03-STRATIFIED-S1-D0` | D0 | Capas estratificadas S1 en D0 restringido a soporte TEM | 2.92e-17 | 4.84e-16 | Bias ρa: 0.0047 dec, Fase: 0.09° |
| `CTRL-04-ABSTENTION-RANK1` | D0 | Excitación polarizada de rango uno (abstención) | 2.74e-17 | 5.05e-16 | Abstención (cond=4.8e+15) |
| `CTRL-05-NONSTATIONARY-SFERICS` | D0 | Fuente no estacionaria con ráfagas impulsivas (sferics) y tipper | 2.69e-17 | 4.38e-16 | Bias ρa: 0.0060 dec, Fase: 0.01° |
| `CTRL-06-INSTRUMENT-ADC-SAT` | D0 | Efectos instrumentales: ruido sensor, ganancias y saturación ADC | 2.89e-17 | 5.41e-16 | Clipping detectado (15.4%) |

## 2. Conformidad con los Requisitos de Puerta P3

1. **Residuo Espectral Algebraico:** Todos los escenarios cumplen $\|E - ZH\| / \|E\| < 10^{-8}$ (máximo observado: `2.92e-17`), confirmando precisión numérica al nivel de redondeo de máquina.
2. **Causalidad y Simetría Hermítica:** Espectro complejo rfft con componentes DC nulas y condición puramente real en Nyquist.
3. **Operador de Subbanda Común $W_b(f)$:** Conmutatividad exacta verificada $E_b = W_b E = Z W_b H = Z H_b$.
4. **Protección de Bordes y Discontinuidades:** Convolución calculada con buffer de guarda temporal simétrico (0.5 s) recortado posteriormente, eliminando efectos de salto circular.
5. **Excitación de Rango 2 vs Rango 1:** La excitación estándar produce matrices $S_{HH}$ con número de condición $\le 1.05$ (ortogonalidad óptima). La excitación colineal dispara la bandera de abstención (`cond > 1e4`).
6. **Aislamiento y Trazabilidad:** Todos los productos contienen metadatos `synthetic: true`, `scientific_claim: false`, sin invadir las carpetas de datos de campo de P0.
