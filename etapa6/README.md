# Etapa 6 — Estimador de referencia e incertidumbre (rama AMT sin TEM)

Versión de la etapa `P6-1.0.0`; configuración `P6-CONFIG-1.0.0`; estimador
`P6-EST-1.0.1`.

## 1. Por qué esta etapa existe sin TEM

El plan v1.3 (§10) sitúa la Etapa 6 en paralelo lógico con las etapas 2–3: sin un
estimador de referencia no se puede juzgar ninguna síntesis ni ninguna red. La
sección también autoriza explícitamente estimar respuestas convencionales
**fuera del soporte TEM**, siempre que no se presenten como recuperadas por la
rama neuronal validada.

Con `B-P0-03` abierto (vínculo TEM–ARMT no verificado), P3, P4, P5 y P7 siguen
cerradas por diseño: exigen P2-T satisfecha. P6 es la única puerta que puede
avanzar desde P1, y por eso se cierra aquí como **PARCIAL**.

## 2. Alcance

**Se hace**

- estimación de la impedancia tensorial `Z(f)` en D0 (125–1000 Hz) y D1
  (1000–10000 Hz) sobre los 15 registros de P0;
- covarianza de `Z` por bootstrap de bloques temporales;
- controles 1D con el directo `etapa2/mt1d.py` (semiespacio, dos capas, tres
  capas) y escenarios de ruido, outliers y rango uno;
- calibración de la incertidumbre con una partición calibración/evaluación.

**No se hace**

- no se lee TEM, no se usa `tem_amt_support.csv`, no se declara soporte;
- no hay síntesis guiada por TEM, ni etiquetas, ni entrenamiento, ni inferencia;
- no se aplica calibración: `Z` es **relativa**;
- no se convierte a resistividad aparente (`rho_a`) ni se interpreta
  geológicamente;
- no se agrupa por sitio (`B-P0-01`) ni se comparan coordenadas (`B-P0-02`).

La guarda queda escrita en cada fila: `calibrado=no`, `soporte_tem=no_aplica`,
`rama=AMT_sin_TEM`.

## 3. Método

1. **Ventanas.** `L=256` muestras, solape 50 %, detrend lineal por ventana y
   taper Hann periódica. Con `N_c=8`, `f_min = N_c·fs/L`; por eso D0 queda en
   125 Hz y todo lo que está por debajo se marca `no_evaluado` en lugar de
   estimarse con otra ventana.
2. **Bandas.** Para cada frecuencia objetivo se promedian los bins `rfft`
   dentro de ±12,25 %. El estimador mide una respuesta **promediada en banda**;
   por eso el benchmark compara contra `Z` promediada en los mismos bins y no
   contra la `Z` central.
3. **Regresión compleja.** `Z_hat = S_EH S_HH⁻¹` con descomposición hermítica,
   número de condición y rango efectivo de `S_HH`. No se invierte sin
   diagnóstico.
4. **Robusto.** Dos pasadas de reponderación Huber sobre el misfit relativo de
   cada ventana; la escala se estima en una submuestra y se recalcula por
   pasada. La salida conserva también la solución LS para comparar.
5. **Bootstrap.** 200 réplicas por bloques temporales de 5 s sobre las matrices
   ponderadas. Las ventanas solapadas no se tratan como independientes.
6. **Compuerta de coherencia.** Una frecuencia solo se publica como `estimado`
   si la coherencia `γ²(Ex–Hy)` supera el valor crítico de ruido
   `γ²_crit = 1 − α^(1/(k_eff−1))` con `α=0,05` y `k_eff` ventanas efectivas.
   Bajo el umbral, `Z` está dominada por ruido incoherente y se marca
   `senal_insuficiente` con motivo `coherencia_Ex_Hy_bajo_critico`; no se
   publica `Z` ni `σ`. La coherencia es invariante a un desfase constante, así
   que un retardo fijo entre E y H no la reduce: un valor bajo implica ruido
   independiente o desfase variable, no un simple desalineamiento.
7. **Incertidumbre.** El bootstrap mide la variabilidad temporal, pero no el
   error sistemático de ventana y ancho de banda. En el control limpio su
   cobertura es ≈0,6. Se estima un factor
   `r = RMS(error)/RMS(σ_bootstrap)` en la **mitad de calibración** de las
   realizaciones y la cobertura se mide en la **mitad de evaluación**,
   independiente. La respuesta publica ambas: `sigma_*` (bootstrap) y
   `sigma_cal_*` (con `r`).

## 4. Cobertura de frecuencias

| Banda | fs_eff | L | Δf | f_min (N_c=8) | Rango estimado |
|---|---:|---:|---:|---:|---|
| D0 | 4 kHz | 256 | 15,6 Hz | 125 Hz | 150,7–1000 Hz (11 de 29 puntos) |
| D1 | 32 kHz | 256 | 125 Hz | 1 kHz | 1000–10000 Hz (13 de 13 puntos) |

1000 Hz se estima por separado en D0 y D1 y **no se fusiona**. La cobertura es
instrumental: `F_red_validada` por familia de ruido sigue pendiente
(`B-P0-06`).

La tabla anterior es la cobertura **instrumental** (lo que la ventana puede
resolver). La cobertura **efectiva** la decide la compuerta de coherencia: una
frecuencia resoluble pero sin correlación E–H suficiente queda
`senal_insuficiente` y no se publica. Los recuentos efectivos están en
`resumen_p6.json` (`per_band`) y en `reporte_p6.md`.

## 5. Entradas y salidas

Entradas (solo lectura)

- `etapa0/manifest.json`, `etapa0/splits.csv`;
- `etapa1/respuesta_interpolada_D0.csv`, `..._D1.csv` (grillas de 29 y 13
  frecuencias);
- SBF originales vía `SBFReader.read_samples(..., units="uV")`;
- `etapa2/mt1d.py` para la verdad de los controles.

Salidas

| Archivo | Contenido |
|---|---|
| `respuestas/<registro>_<banda>.npz` | `Z` compleja (n,2,2), covarianza (n,8,8), estados y diagnósticos |
| `respuestas_resumen.csv` | una fila por registro, banda y frecuencia (630 filas) |
| `benchmark_control.csv` | sesgo, RMSE, cobertura y criterio por escenario y modelo |
| `calibracion_p6.json` | factor `r` por banda y partición calibración/evaluación |
| `resumen_p6.json` | recuentos, diagnóstico y límites |
| `reporte_p6.md` | reporte legible |
| `esquema_response.json` | contrato del CSV y del NPZ |
| `validacion_etapa6.json` | comprobaciones del validador |

## 6. Comandos

```powershell
# Cadena completa: controles -> calibración -> respuestas -> resumen
python etapa6/p6.py --mode all

# Solo controles (escribe benchmark_control.csv y calibracion_p6.json)
python etapa6/p6.py --mode controls

# Solo respuestas reales (usa el factor r ya calibrado)
python etapa6/p6.py --mode real

# Prueba rápida con un registro y pocas realizaciones
python etapa6/p6.py --mode all --records ARMT5-123-01-01-01 --realizations 8

# Validación
python etapa6/validar_etapa6.py
```

El orden importa: la calibración se obtiene de los controles y se aplica a las
respuestas. `--mode real` sin `calibracion_p6.json` deja `sigma_cal_*` sin
escalar; el validador lo detecta.

## 7. Controles y criterios

| Escenario | Modelo | Criterio |
|---|---|---|
| `limpio` | semiespacio 100 Ωm | sesgo ≤0,01 dec, fase ≤0,2°, cobertura calibrada en [0,45; 0,88] |
| `ruido_E` | semiespacio | sesgo ≤0,02 dec, fase ≤0,4°, misma cobertura |
| `ruido_H` | semiespacio | **observación**: sin referencia remota el sesgo no es corregible |
| `ruido_coherente` | semiespacio | **observación**: coherencia no es identidad |
| `outliers` | semiespacio | sesgo ≤0,03 dec y RMSE robusto ≤ LS |
| `rango_uno` | semiespacio | ≥95 % de las realizaciones marcadas `no_identificable` |
| `limpio` | dos y tres capas | **observación**: recuperación de banda, no estructura del sitio |

La cobertura se **agrega por escenario** (frecuencias × realizaciones). Tomar el
mínimo por frecuencia con 48 realizaciones produce falsas fallas por resolución
de la proporción.

## 8. Límites declarados

- Sin calibración certificada (`B-P0-04`), `Z` es relativa: no es `rho_a`.
- Sin referencia remota (`SIN-REF-REMOTA`), el ruido en H sesga `Z`; el escenario
  queda como observación.
- El factor `r` se calibra con un semiespacio 1D limpio: corrige la
  subcobertura del bootstrap, no el error de modelo ni el de calibración en
  campo.
- La cobertura de frecuencias es instrumental (`B-P0-06`).
- La compuerta de coherencia descarta las frecuencias sin correlación E–H: una
  respuesta bajo el umbral crítico no se publica como `estimado`.
- Los dos registros del split `prueba` (`ARMT5-123-01-01-01`,
  `ARMT5-123-02-02-01`) presentan la coherencia más alta y la `sigma_cal` más
  baja (≈0,002–0,006 dec): un régimen casi determinista distinto del resto. Se
  reportan sin interpretación y no intervienen en la calibración.
- Con `L=256`, D0 no resuelve por debajo de 125 Hz; no se extrapola con otra
  ventana dentro de esta etapa.
- Los controles 1D no demuestran estructura del sitio ni soporte TEM.

## 9. Estado de la puerta

P6 = **PARCIAL**. El estimador, la covarianza y los controles están
implementados y validados; la calibración, la familia de ruido y la referencia
remota siguen abiertas. La etapa **no habilita** síntesis, etiquetado ni
entrenamiento, y no modifica el estado cerrado de P3–P5 y P7.

Véase `reporte_p6.md` para los resultados de la corrida vigente y
`validacion_etapa6.json` para el recuento de comprobaciones.
