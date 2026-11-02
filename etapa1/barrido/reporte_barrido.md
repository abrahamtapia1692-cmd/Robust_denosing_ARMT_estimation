# Barrido P1 de los 15 registros

Generado por `etapa1/barrido_registros.py` con la configuracion `P1-CONFIG-2.0.0`.

El barrido **no reexporta series temporales** y **no modifica P0 ni los SBF de origen**. Extiende el QC y el cruce de calibracion del registro objetivo al conjunto completo de P0.

## Resumen

| Metrica | Valor |
|---|---:|
| Registros | 15 |
| Desarrollo | 10 |
| Validacion | 3 |
| Prueba | 2 |
| Muestras D0 | 288000000 |
| Muestras D1 | 21600000 |
| Muestras totales | 309600000 |
| Muestras en mascara (union) | 0 |
| Muestras en mascara (suma por canal) | 0 |
| Canales muertos | 0 |
| Tramos de clipping | 0 |
| Tramos pegados | 0 |
| Tramos de ceros | 0 |
| Registros en FALLA | 0 |
| Registros con observaciones | 15 |
| Cobertura de calibracion incompleta | 0 |
| Hashes de origen distintos | 0 |

Saltos por canal (todos los registros, D0+D1): Ex = 5946, Ey = 6513, Hx = 47, Hy = 129, Hz = 23.

Grupos de ganancia de registro: 1 (3 registros: ARMT5-700-01-00-01, ARMT5-700-01-23-01, ARMT5-700-01-24-01); 1.77828 (11 registros: ARMT5-123-01-01-01, ARMT5-700-14-14-01, ARMT5-700-24-24-01, ARMT5-700-32-32-01, ARMT5-700-34-34-01, ARMT5-700-42-42-01, ARMT5-700-43-43-01, ARMT5-700-44-44-01, ARMT5-700-45-45-01, ARMT5-700-55-55-01, ARMT5-700-90-90-01); 3.16228 (1 registro: ARMT5-123-02-02-01). La calibracion cruzada usa el directorio mas proximo a cada ganancia.

## Registros

| Registro | Split | D0 (s) | D1 (s) | QC D0 | QC D1 | Saltos E | Saltos H | Mala (muestras) | Calibracion | Estado |
|---|---|---:|---:|---|---|---:|---:|---:|---|---|
| ARMT5-123-01-01-01 | prueba | 900 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 0 | 0 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-123-02-02-01 | prueba | 900 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 0 | 0 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-700-01-00-01 | desarrollo | 5400 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 215 | 9 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-700-01-23-01 | desarrollo | 5400 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 12 | 0 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-700-01-24-01 | desarrollo | 5400 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 533 | 1 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-700-14-14-01 | desarrollo | 5400 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 1207 | 1 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-700-24-24-01 | desarrollo | 5400 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 4403 | 22 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-700-32-32-01 | desarrollo | 5400 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 201 | 3 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-700-34-34-01 | desarrollo | 5400 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 657 | 1 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-700-42-42-01 | desarrollo | 5400 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 441 | 5 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-700-43-43-01 | validacion | 5400 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 1671 | 10 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-700-44-44-01 | desarrollo | 3600 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 565 | 126 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-700-45-45-01 | desarrollo | 5400 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 711 | 2 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-700-55-55-01 | validacion | 5400 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 290 | 12 | 0 | cubierta | PASA_CON_OBSERVACIONES |
| ARMT5-700-90-90-01 | validacion | 7200 | 45 | PASA_CON_OBSERVACIONES | PASA_CON_OBSERVACIONES | 1553 | 7 | 0 | cubierta | PASA_CON_OBSERVACIONES |

## Limites

- El QC es el mismo que P1: clipping, canales muertos, valores pegados, relleno de ceros, saltos y huecos. Los saltos se reportan y **no se enmascaran**.
- La calibracion sigue siendo **candidata no verificada**: no hay fecha, certificado ni seccion de ganancia (B-P0-04).
- La cobertura de calibracion solo indica soporte de frecuencia, no validez metrologica.
- La identidad de sitio, las coordenadas, el vinculo TEM-ARMT y la zona horaria siguen sin resolver (B-P0-01, B-P0-02, B-P0-03, B-P0-07).
- Este barrido no habilita P2-T ni la sintesis guiada por TEM.
