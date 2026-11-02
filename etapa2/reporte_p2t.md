# P2-T — Diagnóstico de soporte TEM–MT/AMT

Versión: `P2T-1.0.0`. Generado: `2026-10-28T21:11:29.946802Z`.

## Resultado en una línea

No se alcanza ninguna frecuencia `respaldada`. El soporte por sondeo es parcial y `condicional`; la tabla `tem_amt_support.csv` queda vacía (`no_evaluado`) porque el vínculo TEM–ARMT no está verificado (B-P0-03). No se habilita síntesis, etiquetado TEM, entrenamiento ni inferencia guiados por TEM.

## Alcance y reglas

- Bandas: D0 (5–1000 Hz) y D1 (1000 Hz–10 kHz). El punto de 10 kHz es un escenario separado por el empalme de calibración y queda `no_evaluado`; la respuesta útil declarada llega hasta 9.9 kHz.
- Observable: `Zxy` en 1D isotrópico, expresado como `rho_a` y fase. `Zxx=Zyy=0`, `Zxy=-Zyx` y `T=0` son supuestos 1D, no información tensorial resuelta por TEM.
- No se generan series temporales, no se entrena y no se infiere.

## 1. Gates TEM

| Sondeo | Gates lector | Gates .tem | válidos | condicionales | excluidos | no exportados | máx. Δt rel. | máx. ΔV rel. (ventana) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SER-09 | 48 | 35 | 21 | 1 | 13 | 13 | 6.28e-04 | 0.038 |
| SER-10 | 48 | 27 | 21 | 1 | 5 | 21 | 2.17e-16 | 0.078 |
| SER-11 | 48 | 35 | 19 | 2 | 14 | 13 | 8.39e-04 | 0.073 |
| SER-12 | 48 | 26 | 20 | 2 | 4 | 22 | 1.95e-16 | 0.107 |
| SER-13 | 48 | 32 | 19 | 2 | 11 | 16 | 6.29e-04 | 0.050 |
| SER-14 | 48 | 34 | 20 | 2 | 12 | 14 | 6.30e-04 | 0.128 |
| **Total** | 288 | 189 | 120 | 10 | 59 | 99 | | |

Hallazgos de alineación:

- El gate *j* del `.tem` coincide con el gate *j+1* de la tabla del lector. El `.tem` exporta los gates 2..n+1.
- `t_parser_ms` está desalineado respecto de la amplitud de su propia fila desde el gate 4. La diferencia relativa máxima entre `t_ms` y `t_parser_ms` es 22.5–26.0 % por sondeo (26.0 % global), mientras el `.tem` coincide con `t_ms` en el desplazamiento +1 con menos de 0.084 % de diferencia. `clock_max_relative_pct` del dosier (35.7–40.6 %) mide el cambio de respuesta TEM al sustituir `t_ms` por `t_parser_ms`; es un artefacto de alineación de tablas, no una deriva de reloj demostrada.
- La amplitud `.tem` y la del lector difieren hasta 12.8 % dentro de la ventana útil. La inversión TEM usó la tabla del lector; la diferencia es un sesgo sistemático no incluido en `C_d` y se conserva como guarda.
- `usado_en_inversion` marca los gates del **modelo base** del sondeo, que es el que aporta el Jacobiano TEM usado en el análisis SVD. `n_modelos_que_usan_gate` cuenta cuántos de los 3 modelos del sondeo usan ese gate: el número de gates de inversión es 21–22 en los modelos base y 19–22 en los de estabilidad, no siempre 22.

## 2. Directo MT 1D

| Prueba | Valor | Límite | Unidad | Pasa |
|---|---:|---:|---|---|
| semiespacio_rho_1_Z | 2.850e-16 | 1.000e-10 | rel | sí |
| semiespacio_rho_10_Z | 2.469e-16 | 1.000e-10 | rel | sí |
| semiespacio_rho_100_Z | 2.326e-16 | 1.000e-10 | rel | sí |
| semiespacio_rho_1000_Z | 2.577e-16 | 1.000e-10 | rel | sí |
| semiespacio_rhoa | 6.661e-16 | 1.000e-10 | rel | sí |
| semiespacio_fase | 1.421e-14 | 1.000e-08 | deg | sí |
| matriz_vs_recursion_Z | 1.266e-15 | 1.000e-08 | rel | sí |
| matriz_vs_recursion_fase | 4.782e-14 | 1.000e-06 | deg | sí |
| limite_capa_espesor_nulo | 8.797e-08 | 1.000e-05 | rel | sí |
| limite_capa_espesor_grande | 2.400e-16 | 1.000e-05 | rel | sí |
| convergencia_subdivision | 2.775e-15 | 1.000e-06 | rel | sí |
| fase_en_rango_1D | 0.000e+00 | 0.000e+00 | bool | sí |

Error relativo máximo del directo: `8.797e-08`. Meta P2 (Z ≤ 1 %, fase ≤ 0.5°): `cumple`. Esta precisión numérica no demuestra soporte TEM.

## 3. Envolventes predictivas

| Sondeo | Banda | n | evaluados | dentro | semiancho log10 rho_a mín–máx | semiancho fase mín–máx (°) | máx. Z rel. |
|---|---|---:|---:|---:|---|---|---:|
| SER-09 | D0 | 29 | 29 | 5 | 0.0019–0.1037 | 0.139–5.521 | 0.1475 |
| SER-09 | D1 | 13 | 12 | 0 | 0.0394–0.1176 | 2.627–3.612 | 0.1427 |
| SER-10 | D0 | 29 | 29 | 4 | 0.0003–0.1175 | 0.317–6.112 | 0.1668 |
| SER-10 | D1 | 13 | 12 | 0 | 0.0359–0.1088 | 2.412–3.529 | 0.1351 |
| SER-11 | D0 | 29 | 29 | 29 | 0.0001–0.0142 | 0.041–0.937 | 0.0234 |
| SER-11 | D1 | 13 | 12 | 12 | 0.0089–0.0202 | 0.180–0.701 | 0.0242 |
| SER-12 | D0 | 29 | 29 | 7 | 0.0007–0.0850 | 0.201–4.629 | 0.1245 |
| SER-12 | D1 | 13 | 12 | 0 | 0.0230–0.0603 | 1.169–2.204 | 0.0776 |
| SER-13 | D0 | 29 | 29 | 15 | 0.0010–0.0679 | 0.103–3.398 | 0.0968 |
| SER-13 | D1 | 13 | 12 | 12 | 0.0115–0.0230 | 0.286–1.118 | 0.0321 |
| SER-14 | D0 | 29 | 29 | 14 | 0.0007–0.1038 | 0.128–5.272 | 0.1505 |
| SER-14 | D1 | 13 | 12 | 12 | 0.0025–0.0079 | 0.089–0.506 | 0.0110 |

Los recuentos y los semianchos excluyen el punto de 10 kHz, que no se evalúa. Umbrales de diseño: semiancho de `log10 rho_a` ≤ 0.025 dex, fase ≤ 1.5° y `Z_rel` ≤ 0.065 respecto de la media compleja de los 3 modelos (`max |Z_i/Z_ref − 1|`). Una nube estrecha de 3 modelos con la misma regularización no demuestra por sí sola que TEM haya resuelto la respuesta; por eso el estado máximo es `condicional`.

## 4. Sensibilidad compartida y DOI

| Sondeo | Rango efectivo TEM al 1 % | Componentes para 90 % de energía (S²) | DOI operativa (m) | Bandas condicionales |
|---|---:|---:|---:|---|
| SER-09 | 4 | 1 | 100 | ninguna |
| SER-10 | 4 | 1 | 100 | ninguna |
| SER-11 | 4 | 2 | 175 | D0 125–182 Hz (3) |
| SER-12 | 4 | 2 | 175 | D0 125–182 Hz (3) |
| SER-13 | 4 | 2 | 175 | D0 125–182 Hz (3) |
| SER-14 | 4 | 2 | 175 | D0 125–321 Hz (6) |

La DOI usada es `DOI_operativa_creible_m` (100 m en SER-09/10; 175 m en SER-11..14). `DOI_validated_m` está vacía en los 6 sondeos. El criterio de profundidad exige `z50 ≤ DOI` y una fracción de sensibilidad bajo la DOI ≤ 0.10.

El rango efectivo del Jacobiano TEM es 4 al 1 %, 6–7 al 0.1 % y 7–8 al 0.01 %; `resumen_p2t.json` conserva los tres umbrales para dejar visible la dependencia. El diagnóstico principal se informa al 1 %, que es el más exigente de los tres. El Jacobiano TEM usado es el del modelo base; los 12 modelos de estabilidad aportan a las envolventes MT, no al análisis SVD.

La columna de energía no es un rango de resolución: cuenta cuántos componentes acumulan el 90 % de la energía de los valores singulares al cuadrado. Como el primero concentra más del 90 %, vale 1 aunque 4 componentes superen el 1 % de `s1`. El criterio de sensibilidad compartida usa ese rango al 1 %, no la energía.

Las bandas condicionales dependen de la DOI operativa y no son intervalos de confianza: son rangos diagnósticos de una nube de escenarios. SER-09 y SER-10 no tienen banda condicional porque la sensibilidad MT a esas frecuencias se reparte bajo su DOI de 100 m.

## 5. Decisión de soporte

| Sondeo | Banda | condicional | no respaldada | no evaluado | motivos principales |
|---|---|---:|---:|---:|---|
| SER-09 | D0 | 0 | 29 | 0 | envolvente_modelos_excede_tolerancia (24), profundidad_sensibilidad_MT_excede_DOI_TEM (20), sensibilidad_MT_en_subespacio_no_resuelto_por_TEM (16) |
| SER-09 | D1 | 0 | 12 | 1 | envolvente_modelos_excede_tolerancia (12), sensibilidad_MT_en_subespacio_no_resuelto_por_TEM (12) |
| SER-10 | D0 | 0 | 29 | 0 | envolvente_modelos_excede_tolerancia (25), profundidad_sensibilidad_MT_excede_DOI_TEM (21), sensibilidad_MT_en_subespacio_no_resuelto_por_TEM (16) |
| SER-10 | D1 | 0 | 12 | 1 | envolvente_modelos_excede_tolerancia (12), sensibilidad_MT_en_subespacio_no_resuelto_por_TEM (12) |
| SER-11 | D0 | 3 | 26 | 0 | sensibilidad_MT_en_subespacio_no_resuelto_por_TEM (21), profundidad_sensibilidad_MT_excede_DOI_TEM (17) |
| SER-11 | D1 | 0 | 12 | 1 | sensibilidad_MT_en_subespacio_no_resuelto_por_TEM (12) |
| SER-12 | D0 | 3 | 26 | 0 | envolvente_modelos_excede_tolerancia (22), sensibilidad_MT_en_subespacio_no_resuelto_por_TEM (20), profundidad_sensibilidad_MT_excede_DOI_TEM (17) |
| SER-12 | D1 | 0 | 12 | 1 | envolvente_modelos_excede_tolerancia (12), sensibilidad_MT_en_subespacio_no_resuelto_por_TEM (12) |
| SER-13 | D0 | 3 | 26 | 0 | sensibilidad_MT_en_subespacio_no_resuelto_por_TEM (20), profundidad_sensibilidad_MT_excede_DOI_TEM (17), envolvente_modelos_excede_tolerancia (14) |
| SER-13 | D1 | 0 | 12 | 1 | sensibilidad_MT_en_subespacio_no_resuelto_por_TEM (12) |
| SER-14 | D0 | 6 | 23 | 0 | sensibilidad_MT_en_subespacio_no_resuelto_por_TEM (18), profundidad_sensibilidad_MT_excede_DOI_TEM (17), envolvente_modelos_excede_tolerancia (15) |
| SER-14 | D1 | 0 | 12 | 1 | sensibilidad_MT_en_subespacio_no_resuelto_por_TEM (12) |

Ninguna fila alcanza `respaldada`. Las bandas condicionales son diagnósticas del sondeo TEM; no se transfieren a los registros ARMT.

## 6. Tabla ARMT

`tem_amt_support.csv`: 630 filas (15 registros × D0/D1 × grilla P1). Estados: `{'no_evaluado': 630}`. `soporte_habilitado = false`. Motivo principal: `B-P0-03_vinculo_TEM_ARMT_no_verificado`.

`tem_sounding_id` queda vacío porque no hay vínculo verificado: no se asigna sondeo por proximidad ni por conveniencia. `candidatos_tem_disponibles` enumera los 6 sondeos existentes como posibles, sin afirmar correspondencia. Las columnas de envolvente y sensibilidad quedan vacías: un soporte `no_evaluado` no hereda los números diagnósticos del sondeo.

Esto es un soporte vacío, no una afirmación de que el ARMT observado sea inutilizable. La adquisición se conserva y la estimación convencional sigue su propia evaluación.

## 7. Bloqueos y guardas

- `B-P0-01`: sitio no identificado; no se agrupa por sitio
- `B-P0-02`: coordenadas candidatas sin datum; no se comparan espacialmente
- `B-P0-03`: vinculo TEM-ARMT no verificado; tem_amt_support queda no_evaluado
- `B-P0-04`: calibracion sin fecha ni certificado; no se certifica amplitud/fase
- `B-P0-06`: F_red_validada no definida; no se alcanza respaldada
- `B-P0-07`: zona horaria no declarada; no afecta la grilla de frecuencias

Guardas: no se generan series sintéticas, no se habilitan etiquetas TEM, no se entrena ni infiere con TEM, no se asigna sondeo a registro ARMT y no se amplía el soporte por extrapolación.

## 8. Reproducción

```powershell
python etapa2/p2t.py
python etapa2/validar_etapa2.py
```

Entregables: `tem_valid_gates.csv`, `tem_amt_support.csv`, `model_provenance.json`, `diagnostico_tem/envolventes_D0.csv`, `diagnostico_tem/envolventes_D1.csv`, `diagnostico_tem/soporte_por_sondeo.csv`, `diagnostico_tem/sensibilidades_mt.csv`, `diagnostico_tem/sensibilidades_tem.csv`, `diagnostico_tem/sensibilidad_tem_svd.csv`, `diagnostico_tem/comparacion_sensibilidad_doi.csv`, `diagnostico_tem/pruebas_directo.csv` y `diagnostico_tem/resumen_p2t.json`.
