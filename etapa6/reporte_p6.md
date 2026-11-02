# P6 — Estimador de referencia e incertidumbre (rama AMT sin TEM)

Versión `P6-1.0.0`; generado 2026-10-28T23:29:05.956085Z.

## Alcance

La rama sin TEM mantiene cerradas P3–P5 y P7: no hay síntesis guiada por TEM, ni etiquetas, ni entrenamiento. Esta etapa implementa el estimador de referencia que el plan §10 permite ejecutar en paralelo desde P1, incluso fuera del soporte TEM.

## Respuestas reales

| Banda | Filas | Estimadas | No evaluadas | No identificables | Sin señal | Rango estimado |
|---|---:|---:|---:|---:|---:|---|
| D0 | 435 | 111 | 270 | 0 | 54 | 150.731–1000 Hz |
| D1 | 195 | 30 | 0 | 0 | 165 | 1000–10000 Hz |

Mediana de σ(log10|Zxy|) de las filas estimadas = 0.01009; mediana de coherencia γ²(Ex–Hy) de las filas estimadas = 0.3587.

**Compuerta de coherencia.** Una frecuencia solo se publica como `estimado` si γ²(Ex–Hy) supera el valor crítico de ruido γ²_crit = 1 − α^(1/(k_eff−1)) con α = 0,05. Bajo ese umbral la estimación está dominada por ruido incoherente y se marca `senal_insuficiente`. La coherencia se mide sobre el espectro apilado y es invariante a un desfase constante, de modo que un retardo fijo no la reduce: un valor bajo implica ruido independiente o desfase variable, no un simple desalineamiento.

Las respuestas se guardan sin calibración aplicada. El cociente E/H usa µV del ADC en ambos canales: es una respuesta relativa y **no** una resistividad aparente física.

## Controles 1D

| Escenario | Modelo | Criterio | Detalle |
|---|---|---|---|
| limpio | semiespacio_100 | PASA | bias=0.0002 dec, fase=0.002 deg, cobertura calibrada=0.70/0.72 (evaluacion independiente) |
| ruido_E | semiespacio_100 | PASA | bias=0.0050 dec, fase=0.028 deg, cobertura calibrada=0.70/0.70 |
| ruido_H | semiespacio_100 | OBSERVACION | sin referencia remota: el ruido en H sesga Z; bias=0.0414 dec, cobertura=0.00 |
| ruido_coherente | semiespacio_100 | OBSERVACION | coherencia no es identidad; bias=0.0316 dec, fase=8.475 deg |
| outliers | semiespacio_100 | PASA | bias=0.0000 dec, rmse robusto=0.0002 vs LS=0.0022 |
| rango_uno | semiespacio_100 | PASA | fraccion marcada no_identificable=1.00 |
| limpio | dos_capas | OBSERVACION | modelo estratificado: bias de banda=0.0002 dec |
| limpio | tres_capas | OBSERVACION | modelo estratificado: bias de banda=0.0002 dec |

## Incertidumbre

El bootstrap por bloques mide la variabilidad temporal del estimador, pero no el error sistemático de ventana y ancho de banda. Sobre el control limpio, la cobertura del bootstrap solo es ≈0,6. Se calibra un factor `r = RMS(error) / RMS(σ_bootstrap)` en la mitad de calibración y la cobertura se mide en la mitad de evaluación, independiente.

| Banda | r(σ log10) | r(σ fase) |
|---|---:|---:|
| D0 | 1.323 | 1.08 |
| D1 | 1.738 | 0.9037 |

Cobertura del control limpio en evaluación: log10 0.698, fase 0.719 (bootstrap solo: 0.482).

En las respuestas de campo, `sigma_log10_abs_zxy` es la incertidumbre estadística condicional del bootstrap y `sigma_cal_log10_abs_zxy` la incertidumbre con el factor calibrado. Ninguna de las dos cubre el error de calibración (B-P0-04) ni el de modelo.

## Límites

- Sin calibracion aplicada: Z es relativa y no se convierte a rho_a.
- Sin referencia remota: el ruido en H no es corregible.
- D0 por debajo de 125 Hz queda no_evaluado con L=256 (N_c=8).
- La compuerta de coherencia descarta las frecuencias sin correlacion Ex-Hy: una respuesta bajo el critico no se publica.
- La cobertura de frecuencias es instrumental; F_red_validada por familia de ruido sigue pendiente (B-P0-06).
- El factor r de incertidumbre se calibra en controles 1D: no cubre error de calibracion ni de modelo en campo.
- P3-P5 y P7 siguen cerradas: no hay sintesis guiada por TEM, etiquetas ni entrenamiento.

## Conclusión

P6 se cierra como PARCIAL en la rama AMT sin TEM: el estimador recupera la verdad en controles identificables, rechaza el rango uno y produce respuestas relativas con covarianza; no habilita la rama neuronal.

P6 queda **PARCIAL**: el estimador y la covarianza están implementados y validados en controles, pero la calibración (B-P0-04), la familia de ruido (B-P0-06) y la referencia remota siguen abiertas. No se habilita síntesis, etiquetado ni entrenamiento.
