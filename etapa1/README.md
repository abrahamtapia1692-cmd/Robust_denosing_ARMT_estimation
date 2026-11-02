# Etapa 1 — cerrar la cadena instrumental (puerta P1)

Esta carpeta implementa la Etapa 1 del `PLAN_IMPLEMENTACION_ARMT.md` v1.3 sobre el registro real `ARMT5-700-14-14-01` (`ARMT_processing/ARMT_data/01401401.sbf`, split **desarrollo**). No modifica P0 ni los proyectos de origen: lee los SBF y las calibraciones en modo solo lectura. Desde `P1-CONFIG-2.0.0` la misma cadena de QC y calibración se aplica a los 15 registros de P0, sin reexportar series temporales.

## Estado

**P1 = PARCIAL.**

Lo que sí queda cerrado:

- QC irreversible de D0/D1 sobre las 21 600 000 + 1 440 000 muestras del registro objetivo, extendido a los 15 registros (309 600 000 muestras).
- Registro de calibración con hashes, cobertura, limpieza del empalme de 10 kHz y fase desenrollada.
- Exportación calibrada reversible en µV (solo `counts × adc_to_uv`).
- Presupuesto instrumental con cada término declarado y su estado.

Lo que sigue abierto:

- **B-P0-01 / B-P0-02**: identidad de sitio, coordenadas y datum.
- **B-P0-03**: vínculo TEM–ARMT; **P2-T sigue bloqueado**.
- **B-P0-04**: las 73 `.clb` no tienen fecha, certificado ni sección de ganancia. No se puede certificar amplitud ni fase.
- **B-P0-06**: etiquetas de escenario y familia de ruido.
- **B-P0-07**: zona horaria.

**B-P0-05** se cierra a nivel de QC para los 15 registros en D0/D1 (ver «Barrido de los 15 registros»). La validez metrológica de la calibración (B-P0-04) sigue abierta y no se generaliza.

## Archivos

| Archivo | Función |
|---|---|
| `config_p1.json` | Bandas, umbrales QC, parámetros de calibración y exportación |
| `comun_p1.py` | Utilidades: hashes, JSON, fase, intervalos, máscaras empaquetadas |
| `registro_calibracion.py` | Verifica `.clb`, limpia el empalme, interpola y escribe el registro |
| `qc_tiempo.py` | QC irreversible y máscaras de D0/D1 |
| `exportar_calibrado.py` | Exporta `counts × adc_to_uv` a `.npy` float32 en µV |
| `presupuesto_instrumental.py` | Genera el CSV del presupuesto |
| `construir_etapa1.py` | Orquesta la cadena y verifica que P0 no cambió |
| `validar_etapa1.py` | Valida 76 comprobaciones sobre los entregables |
| `calibration_registry.json` | Serie → `.clb` → canal → banda → ganancia → cobertura |
| `auditoria_ganancias.json` | Auditoría de los 9 directorios de ganancia y de las unidades |
| `respuesta_interpolada_D0.csv` | Respuesta compleja interpolada, 5–1000 Hz |
| `respuesta_interpolada_D1.csv` | Respuesta compleja interpolada, 1000–10 000 Hz |
| `qc_D0_D1.json` | Reporte de QC por banda, canal y comprobación |
| `mascaras_QC_D0.npz`, `mascaras_QC_D1.npz` | Máscaras `bad_<canal>` empaquetadas little-endian |
| `exportaciones/*.npy` | D0: 900 s (3 600 000 × 5); D1: 45 s (1 440 000 × 5) |
| `exportaciones/exportaciones.json` | Metadatos, hashes y estadísticas de las exportaciones |
| `exportaciones/muestras_verificacion.csv` | Comprobación counts → µV en muestras concretas |
| `presupuesto_instrumental.csv` | 24 términos con estado y efecto |
| `construccion_etapa1.json` | Tiempos, hashes y prueba de que la fuente no cambió |
| `validacion_etapa1.json` | Resultado de la validación |
| `config_barrido.json` | Configuración `P1-CONFIG-2.0.0` para los 15 registros |
| `barrido_registros.py` | Barrido de QC y calibración de los 15 registros, sin reexportar series |
| `validar_barrido.py` | Valida hashes, longitudes, máscaras y cobertura del barrido |
| `barrido/` | Registros, máscaras, CSV, reporte y validación del barrido |

## Ejecución

```powershell
python etapa1/construir_etapa1.py
python etapa1/validar_etapa1.py
python etapa1/barrido_registros.py
python etapa1/validar_barrido.py
```

La construcción completa tarda unos 33 s en este equipo y escribe ~101 MB de exportaciones. Cada módulo también se puede ejecutar por separado:

```powershell
python etapa1/registro_calibracion.py
python etapa1/qc_tiempo.py
python etapa1/exportar_calibrado.py
python etapa1/presupuesto_instrumental.py
```

El barrido de los 15 registros lee los 6.91 GB de SBF, calcula el QC de 30 trazas D0/D1 y no escribe series temporales. Tarda varios minutos. `--resumir` regenera los CSV y el reporte desde `barrido/registros/*.json` sin releer los SBF:

```powershell
python etapa1/barrido_registros.py --resumir
```

## Resultado actual

- Validación: **76 comprobaciones, 70 pasan, 0 fallan, 6 observaciones**.
- `resultado = APROBADO_CON_OBSERVACIONES`, `P1 = PARCIAL`.
- P0 intacto: los cuatro hashes congelados coinciden y el SBF de origen conserva su SHA-256.
- Sin identificadores del banco sintético en los entregables de datos.

### QC

| Banda | Muestras | Clipping | Muertos | Pegados | Ceros | Huecos | Saltos (Ex/Ey/Hx/Hy/Hz) |
|---|---:|---:|---:|---:|---:|---:|---|
| D0 | 21 600 000 | 0 | 0 | 0 | 0 | 0 | 113 / 12 / 0 / 0 / 0 |
| D1 | 1 440 000 | 0 | 0 | 0 | 0 | 0 | 511 / 571 / 1 / 0 / 0 |

Las máscaras `bad_*` quedan **vacías**: no hay muestra que deba eliminarse por clipping, valor pegado o relleno de ceros. Los saltos por amplitud se reportan y **no se enmascaran**, porque pueden ser sferics útiles (plan 1.5). El detector de cambios de media por bloque marca algunos eventos en D0; no se interpretan como conmutación de ganancia porque el registro tiene una sola configuración.

### Barrido de los 15 registros

`barrido_registros.py` extendió el QC y el cruce de calibración a los 15 registros de P0, **sin reexportar series temporales** y sin tocar P0 ni los SBF.

| Métrica | Valor |
|---|---:|
| Registros | 15 (10 desarrollo, 3 validación, 2 prueba) |
| Trazas D0/D1 | 30 |
| Muestras | 288 000 000 (D0) + 21 600 000 (D1) = 309 600 000 |
| Clipping / pegados / ceros / canales muertos | 0 / 0 / 0 / 0 |
| Muestras en máscara | 0 |
| Registros en FALLA | 0 |
| Registros con observaciones | 15 |
| Cruces de calibración cubiertos | 150 / 150 |
| Discrepancias SBF ↔ manifiesto | 0 |
| Hashes de origen distintos | 0 |

Los saltos por amplitud suman `Ex = 5946`, `Ey = 6513`, `Hx = 47`, `Hy = 129`, `Hz = 23` y se reportan sin enmascarar. La mayor densidad aparece en `ARMT5-700-24-24-01` (4403 saltos eléctricos) y en `ARMT5-700-44-44-01` (126 magnéticos).

Las duraciones D0 no son uniformes: 900 s en los dos registros A123, 3600 s en `ARMT5-700-44-44-01`, 7200 s en `ARMT5-700-90-90-01` y 5400 s en los diez restantes. D1 es de 45 s en todos.

El barrido usa **tres grupos de ganancia**: `1.0` en `ARMT5-700-01-00`, `-23` y `-24`; `1.77828` (5.000 dB) en once registros; y `3.16228` (10.000 dB) en `ARMT5-123-02-02-01`. Cada canal se cruza con el directorio de calibración más próximo a su ganancia, y los 150 cruces quedan cubiertos.

Validación del barrido: **366 comprobaciones, 362 pasan, 0 fallan, 4 observaciones**. La construcción completa tardó **393 s** y releyó los 6.91 GB de SBF.

Límites: la cobertura de calibración es de frecuencia y hash, **no metrológica**; usa las mismas `.clb` candidatas del inventario. El barrido no cierra B-P0-01, B-P0-02, B-P0-03, B-P0-04, B-P0-06 ni B-P0-07 y no habilita P2-T.

### Calibración y ganancia

- 73 archivos `.clb`, todos con **una sola tabla** y `gain = 1.0`. Ninguno declara secciones de ganancia, aunque el manual (App. 7) las prevé.
- La ganancia de registro es `1.77828` (5.000 dB); la etiqueta del directorio es `1.8`, un redondeo de **+1.2214 %**. Dividir por `1.8` dejaría `−1.2067 %`.
- La amplitud eléctrica **no escala con la ganancia del directorio** y varía hasta **24.1 % a 100 Hz** y **29.1 % a 10 kHz** para el mismo número de serie. La tabla `G1.8` elegida está **+15.8 %** sobre la mediana a 100 Hz. La magnética varía ~4.6 %.
- Por eso **no se aplica ganancia ni respuesta `.clb`**: no hay base para decidir si la tabla ya incluye la ganancia del amplificador. El riesgo de doble compensación es de 5.00 dB.
- El empalme de 10 kHz de las tablas eléctricas tiene tres puntos casi coincidentes (`9999.98902`, `10000.00000`, `10000.01098 Hz`). El punto `10000.00 Hz = −8.10°` es atípico y se excluye **solo para interpolar**; la serie temporal no se toca. El salto restante es de ~12.66° y ~0.65 dB, por debajo del umbral de continuidad. El extremo superior de D1 coincide con el empalme: la respuesta se declara utilizable hasta **9.9 kHz** o se trata 10 kHz como escenario separado.
- La tabla magnética llega a 15 317.4 Hz, por encima de 10 kHz y por debajo de Nyquist (16 kHz). No hay archivos `r*.clb` de calibración de entradas del receptor.
- El manual declara la amplitud magnética en `V/(A/m)`. El código existente `instrument_calibration.py` la multiplica por 1000 como si fuera `mV/nT`: el cociente de sensibilidades es **1.2566** y el campo resultante sería **0.7958** del literal del manual (−20.4 %). La unidad real no está verificada y P1 no aplica la tabla.

### Exportación

`uV = counts × adc_to_uv`. No se aplica ganancia, amplitud/fase `.clb`, longitud de dipolo, polaridad ni orientación.

| Banda | Archivo | Forma | dtype | Unidades |
|---|---|---|---:|---|
| D0 | `01401401_D0_900s_uV.npy` | 3 600 000 × 5 | `<f4` | µV |
| D1 | `01401401_D1_45s_uV.npy` | 1 440 000 × 5 | `<f4` | µV |

D0 exporta los primeros 900 s de 5400 s; D1 exporta los 45 s completos. Las muestras inválidas no se borran: las máscaras van aparte.

## Advertencias

- La exportación **no es campo físico** en V/m o nT. Es una escala reversible a µV con la cadena instrumental caracterizada, no certificada.
- La longitud de dipolo de 20 m está declarada en el SBF (`electric_dipole_lengths_cm = [2000, 2000]`), pero no verificada en campo.
- Los azimuts `[0, 90, 0, 90, 0]` y la polaridad no están verificados.
- No hay comparación con una exportación independiente del fabricante; el alcance de la auditoría SBF es el lector `ARMT_processing`.
- Un soporte TEM vacío sigue siendo un resultado válido; P1 no lo convierte en evidencia.
