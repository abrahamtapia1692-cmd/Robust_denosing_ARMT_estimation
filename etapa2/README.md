# Etapa 2 — P2-T: diagnóstico de soporte TEM–MT/AMT

Estado: **`DIAGNOSTICO_CON_SOPORTE_AMT_VACIO`**.
Validación independiente: **`APROBADO_CON_OBSERVACIONES`** (180 comprobaciones,
170 pasan, 0 fallan, 10 observaciones).

Esta etapa implementa la subpuerta **P2-T** del plan v1.3: documentar qué
frecuencias de D0/D1 están respaldadas por la evidencia TEM disponible, con qué
sensibilidades, envolventes y guardas. Es un **diagnóstico**, no una síntesis ni
un entrenamiento. Un soporte vacío es un resultado válido y cierra la rama
guiada por TEM para los registros ARMT.

## Alcance

- Bandas: D0 (5–1000 Hz) y D1 (1000 Hz–10 kHz). El punto de 10 kHz se conserva
  como escenario separado por el empalme de calibración y queda `no_evaluado`;
  la respuesta útil declarada llega hasta 9.9 kHz.
- Observable: `Zxy` en 1D isótropo, expresado como `rho_a` y fase.
  `Zxx=Zyy=0`, `Zxy=-Zyx` y `T=0` son **supuestos 1D**, no información
  tensorial/3D resuelta por TEM.
- Sondeos TEM: `SER-09` … `SER-14`. Registros ARMT: los 15 de
  `etapa0/manifest.json`.
- Fuera de alcance: D2/D3, RMT, inversión TEM nueva, etiquetas temporales TEM,
  síntesis, entrenamiento e inferencia guiados por TEM.

## Qué no hace

- No genera series temporales sintéticas ni usa el banco `banco_sintetico/`.
- No asigna sondeos TEM a registros ARMT (`B-P0-03` abierto).
- No amplía el soporte por extrapolación.
- No modifica `etapa0/`, `etapa1/` ni los proyectos de origen.
- No usa números aleatorios: la corrida es determinista.

## Insumos (solo lectura)

Locales:

- `etapa0/manifest.json`, `etapa0/splits.csv`
- `etapa1/config_p1.json`, `etapa1/calibration_registry.json`
- `etapa1/respuesta_interpolada_D0.csv`, `etapa1/respuesta_interpolada_D1.csv`

Externos:

- `D:/ARRT_software/TEM_MT_inversion/dosier_doi_20261014/`:
  `ventanas_QC.csv`, `resumen_por_sondeo.csv`, `comprobaciones_modelos.json`,
  `modelos_escenario.json`, `estabilidad_modelos.json`,
  `manifiesto_entradas.json`.
- `D:/WP.2026/GTM26-068-GH-027/Gabinete/Información de entregables/Winglink/TEMS/SER-09.tem` … `SER-14.tem`.

Los hashes de cada insumo quedan en `model_provenance.json`. Los hashes
congelados de P0/P1 se verifican en cada validación.

## Comandos

```powershell
python etapa2/p2t.py
python etapa2/validar_etapa2.py
```

`p2t.py` regenera todos los entregables. `validar_etapa2.py` recalcula las
comprobaciones críticas y escribe `validacion_etapa2.json`; no reescribe los
demás archivos.

## Salidas

| Archivo | Filas | Contenido |
|---|---:|---|
| `tem_valid_gates.csv` | 288 | máscara por gate: tiempo, amplitud, QC, estado, motivo, guardas |
| `tem_amt_support.csv` | 630 | 15 registros × 42 frecuencias; todas `no_evaluado` |
| `model_provenance.json` | — | 18 modelos, 6 candidatas TEM, hallazgos F-P2T-01…08, guardas y bloqueos |
| `diagnostico_tem/envolventes_D0.csv` | 174 | 6 sondeos × 29 frecuencias |
| `diagnostico_tem/envolventes_D1.csv` | 78 | 6 sondeos × 13 frecuencias |
| `diagnostico_tem/soporte_por_sondeo.csv` | 252 | 6 sondeos × 42 frecuencias con estado y motivo |
| `diagnostico_tem/sensibilidades_mt.csv` | 4032 | Jacobiano MT por sondeo/frecuencia/capa |
| `diagnostico_tem/sensibilidades_tem.csv` | 2080 | Jacobiano TEM del modelo base (130 gates × 16 capas) |
| `diagnostico_tem/sensibilidad_tem_svd.csv` | 96 | SVD del Jacobiano TEM ponderado (6 × 16) |
| `diagnostico_tem/comparacion_sensibilidad_doi.csv` | 252 | profundidad, fracción bajo DOI y sensibilidad compartida |
| `diagnostico_tem/pruebas_directo.csv` | 12 | autopruebas del directo MT 1D |
| `diagnostico_tem/resumen_p2t.json` | — | agregados, DOI, sensibilidad y conclusión |
| `reporte_p2t.md` | — | reporte narrativo |
| `validacion_etapa2.json` | — | validación independiente |

## Método

1. **Gates.** Se empareja cada gate `.tem` con la tabla QC del lector por tiempo
   y amplitud. Se excluyen gates sin observación, sin ventana contigua o fuera
   de QC. Se conserva `sigma_effective_nVA` como `C_d` y no se inventa columna
   de error.
2. **Directo MT.** `mt1d.py` (`MT1D-1.0.0`) calcula la impedancia 1D por
   recursión y por matrices `[E,H]`, con convención `exp(+iωt)`. Se valida con
   semiespacio analítico, límites de capa y convergencia.
3. **Envolventes.** Para cada sondeo y frecuencia se calcula `rho_a` y fase de
   los 3 modelos (1 base + 2 de estabilidad) y se mide semiancho de
   `log10 rho_a`, semiancho de fase y `Z_rel`.
4. **Sensibilidad.** Se calcula el Jacobiano MT por perturbación logarítmica y
   el Jacobiano TEM ponderado del modelo base. La SVD da el rango efectivo y la
   fracción de la sensibilidad MT que cae en el subespacio no resuelto por TEM.
5. **Profundidad.** Se calculan `z50`, `z90` y la fracción de sensibilidad bajo
   la `DOI_operativa_creible_m` (100 m en SER-09/10; 175 m en SER-11…14).
6. **Decisión.** Una frecuencia es `condicional` solo si pasan los tres
   criterios: envolvente, profundidad y sensibilidad compartida. `respaldada`
   no se alcanza porque no hay posterior ni `F_red_validada` ni vínculo
   TEM–ARMT verificado.

## Criterios

- Envolvente: semiancho `log10 rho_a` ≤ 0.025 dex, fase ≤ 1.5°, `Z_rel` ≤ 0.065
  respecto de la media compleja de los 3 modelos (`max |Z_i/Z_ref − 1|`).
- Profundidad: `z50 ≤ DOI` y fracción de sensibilidad bajo la DOI ≤ 0.10.
- Sensibilidad compartida: fracción nula TEM ≤ 0.10 con rango efectivo al 1 %.
- Estados: `respaldada`, `condicional`, `no_respaldada`, `no_evaluado`.
  En P2-T el máximo alcanzable es `condicional`.

## Resultado

Gates: **120 válidos, 10 condicionales, 59 excluidos, 99 no exportados** (288
filas del lector; 189 gates en los `.tem`). Los modelos base usan 21–22 gates;
los de estabilidad, 19–22. En total, 130 gates del modelo base participan del
Jacobiano TEM.

Soporte por sondeo (252 filas): **15 `condicional`, 231 `no_respaldada`,
6 `no_evaluado`, 0 `respaldada`**.

Bandas condicionales (solo D0, solo diagnóstico):

| Sondeo | Banda | Rango | Puntos |
|---|---|---|---:|
| SER-09 | — | ninguna | 0 |
| SER-10 | — | ninguna | 0 |
| SER-11 | D0 | 124.745–182.131 Hz | 3 |
| SER-12 | D0 | 124.745–182.131 Hz | 3 |
| SER-13 | D0 | 124.745–182.131 Hz | 3 |
| SER-14 | D0 | 124.745–321.308 Hz | 6 |

D1 no tiene ninguna frecuencia condicional: la sensibilidad MT somera cae en el
subespacio no resuelto por TEM (fracción nula > 0.10). SER-09 y SER-10 no tienen
banda condicional porque, aunque parte de su envolvente D0 entra en tolerancia,
la sensibilidad bajo su DOI de 100 m excede 0.10.

Tabla ARMT: **630 filas, todas `no_evaluado`**, `soporte_habilitado=false`,
motivo `B-P0-03`. `tem_sounding_id` queda vacío y
`candidatos_tem_disponibles` enumera los 6 sondeos sin afirmar correspondencia.
Las columnas de envolvente y sensibilidad quedan vacías: un soporte
`no_evaluado` no hereda los números del sondeo.

Directo MT: **12/12 pruebas pasan**; error relativo máximo `8.797e-08`, dentro
de la meta P2 (`Z ≤ 1 %`, fase ≤ 0.5°). Esa precisión numérica no demuestra
soporte TEM.

## Interpretación de columnas

- `usado_en_inversion`: el gate pertenece a los índices del **modelo base** del
  sondeo, que es el que aporta el Jacobiano TEM usado en la SVD.
- `n_modelos_que_usan_gate`: cuántos de los 3 modelos del sondeo (base + 2 de
  estabilidad) usan ese gate. Puede ser 0, 1, 2 o 3.
- `estado_gate`: `valido`, `valido_condicional`, `excluido` o `no_exportado`.
  Solo los dos primeros son datos TEM utilizables.
- `estado` en `soporte_por_sondeo.csv`: soporte diagnóstico de la frecuencia,
  no una etiqueta utilizable para entrenamiento.
- `evaluado=no`: en D1 corresponde al punto de 10 kHz (empalme de calibración).
- Las frecuencias se escriben con representación exacta (`repr`) para no perder
  la grilla P1 ni confundir 1000 Hz de D0 con 1000 Hz de D1.

## Guardas y bloqueos

Guardas globales:

- no se generan series temporales sintéticas;
- no se habilitan etiquetas TEM;
- no se entrena ni infiere con TEM;
- no se asigna sondeo a registro ARMT;
- no se amplía el soporte por extrapolación;
- no se modifican los proyectos de origen.

Bloqueos abiertos:

- `B-P0-01`: sitio no identificado.
- `B-P0-02`: coordenadas candidatas sin datum.
- `B-P0-03`: vínculo TEM–ARMT no verificado; deja la tabla ARMT `no_evaluado`.
- `B-P0-04`: calibración sin fecha ni certificado.
- `B-P0-06`: `F_red_validada` no definida; impide `respaldada`.
- `B-P0-07`: zona horaria no declarada.

## Limitaciones declaradas

- Directo MT solo 1D isótropo horizontal; no modela 3D, anisotropía, topografía
  ni distorsión galvánica.
- La inversión TEM usó `empymod` con lazo cuadrado coincidente y no incluye
  filtros ni forma de onda periódica completa.
- Los 18 modelos son escenarios regularizados (`lambda` 1–4, `wrms_log`
  0.25–1.35), no un posterior; no hay covarianza.
- La calibración `.clb` no tiene fecha, certificado ni cadena de aplicación.
- La DOI es operativa y no validada (`DOI_validated_m` vacía en los 6 sondeos).
- La amplitud `.tem` y la del lector difieren hasta 12.8 % en la ventana útil;
  la inversión usó la tabla del lector y la diferencia es un sesgo no incluido
  en `C_d`.
- No hay motor MT externo independiente; el directo se contrastó con solución
  analítica, formulación matricial, límites y convergencia.
- El análisis SVD usa el Jacobiano del modelo base; los modelos de estabilidad
  aportan a las envolventes MT, no al rango TEM.
- `t_parser_ms` está desalineado: no es un reloj independiente. El `.tem`
  coincide con `t_ms` en el desplazamiento +1. `clock_max_relative_pct` del
  dosier es un artefacto de alineación de tablas, no una deriva demostrada.

## Observaciones de la validación

1. Diferencia de amplitud `.tem` vs lector en la ventana útil (guarda).
2. `t_parser_ms` desalineado; `clock_max_relative_pct` reclasificado.
3. Sin motor MT externo; validación analítica y de convergencia.
4. DOI operativa, no validada.
5. Rango efectivo TEM 4 al 1 %, 6–7 al 0.1 %, 7–8 al 0.01 %.
6. 10 kHz como escenario separado.
7. 18 modelos son escenarios, no posterior.
8. `tem_amt_support.csv` vacío por `B-P0-03`, no por ausencia de datos TEM.
9. El soporte condicional por sondeo no se transfiere a los registros ARMT.
10. La banda condicional es estrecha y depende de la DOI operativa.

## Conclusión

P2-T se cierra como diagnóstico con soporte ARMT vacío. La evidencia TEM no
permite habilitar frecuencias para síntesis ni para entrenamiento/inferencia
guiados por TEM. La adquisición ARMT se conserva intacta y cualquier uso
convencional posterior debe evaluarse por su propia cadena, sin heredar este
diagnóstico como certificación.

**Efecto sobre P3.** La puerta P3 exige P2-T satisfecha para cada ejemplo TEM y
sin blancos fuera de soporte. Con soporte vacío esa condición no se cumple, de
modo que P3 queda detenida por `B-P0-03` y no se abre síntesis ni
entrenamiento. Para reanudarla hace falta evidencia nueva del vínculo
TEM–ARMT (o un soporte por sondeo que se pueda transferir con trazabilidad), no
una relajación de la máscara.

## Anexo A — conversión tiempo–frecuencia TEM→MT/AMT

[`ANEXO_A_CONVERSION_TF.md`](ANEXO_A_CONVERSION_TF.md) documenta por qué la
conversión `f = 1/t` o `f = 1/(2πt)` no habilita soporte, aunque el modelo de
capas TEM se conozca. Resumen:

- el mapeo de los gates usados (t = 0,39–10,29 ms) cubre 15–413 Hz de D0 con
  `1/(2πt)`, y aun así P2-T respalda **0 de 252** frecuencias;
- la causa dominante es el subespacio nulo (183 filas), no la profundidad
  (109); en D1 la profundidad no es el problema (z90 ≈ 40 m);
- fijar un semiespacio común a 300 m es benigno por encima de ~320 Hz, consume
  el 89 % del presupuesto a 150,7 Hz y lo excede entre 2 y 16 veces por debajo
  de 124,7 Hz; el valor a 300 m no lo aporta el TEM (DOI 100–175 m).

El anexo no crea puerta, no cambia estados y se regenera con
`python etapa2/anexo_conversion_tf.py`. El estado de P2-T sigue siendo
**0 `respaldada`**, 15 condicionales diagnósticas y 231 no respaldadas.
