# Informe de verificación de rigor — suite ARMT (P0–P10)

**Fecha:** 2026-10-30
**Ámbito:** `D:\ARRT_software\Robust_denosing_ARMT_estimation`
**Pregunta auditada:** ¿se ejecutaron/completaron los sets de prueba con el rigor necesario?
**Veredicto:** **NO. Las suites se ejecutaron, pero el rigor no está asegurado.** Varias validaciones se auto-confirman, la evaluación "ciega" P9 usa un modelo de Tierra distinto al del generador y sus conclusiones están invertidas. **El resultado no es liberable.**

---

## 1. Resumen ejecutivo

Los JSON de validación declaraban prácticamente todo aprobado (etapa3 42/42, etapa4 34/34, etapa5 25/25, etapa7 32/32, etapa8 32/32, etapa9 32/32, etapa10 32/32, etapa0 y etapa2/6 "APROBADO_CON_OBSERVACIONES"). Al **re-ejecutar** los validadores y **recalcular de forma independiente** los resultados:

| Etapa | Estado declarado (original) | Estado reproducido | Causa |
|---|---|---|---|
| P0 | APROBADO_CON_OBSERVACIONES, 24/24 | **RECHAZADO** | `V-09`, `V-10`: archivos externos de `ARMT_processing` cambiaron de tamaño |
| P2 | APROBADO_CON_OBSERVACIONES, 180/180 | **FALLA** | `MATRIZ-P3`: contradicción P2-T vacío vs P3 aprobado |
| P6 | APROBADO_CON_OBSERVACIONES | **FALLA** | check `NOPYCACHE` se auto-invalida al ejecutar Python |
| P7 | APROBADO, 32/32 | **FALLA 31/32** | `V-P7-11` no determinista (entrada aleatoria sin semilla) |
| P9 | APROBADO, 32/32 | APROBADO 32/32 **pero inválido** | validador solo relee el resumen; 9 checks hardcodeados; verdad de referencia errónea |
| P10 | 32/32 | 32/32 **pero inválido** | publica salidas sintéticas como `soporte_aprobado` / `aceptado` |
| P3/P4/P5/P8 | APROBADO | reproducen el conteo | pero miden estructura/tautologías, no validez científica (ver §4) |

El hallazgo más grave: **P9 mide contra un modelo de Tierra que no es el que generó los datos**. Contra la verdad correcta, el denoisedor **empeora** el resultado ~30× (B0 = 1.24 % → B4 = 36.57 % de error mediano en Z), mientras el informe publicado declara que B4 "mejora" a B0.

---

## 2. Metodología

1. Copia de seguridad de todos los `validacion_etapa*.json` originales en `verificacion_rigor/originales/`.
2. Re-ejecución de cada validador desde la raíz del proyecto (Python 3.8.19), guardando la salida en `verificacion_rigor/reejecuciones/`.
3. Recalculo independiente de P9 contra el modelo real del generador (`verificacion_rigor/reevaluar_p9_verdad_correcta.py`).
4. Prueba aislada de B8/Wiener sobre señal limpia (`verificacion_rigor/b8_sobre_senal_limpia.py`).
5. Contraste con los objetivos preregistrados del `PLAN_IMPLEMENTACION_ARMT.md` y de `etapa9/config_p9.json`.

> **Estado del repositorio:** los `validacion_etapa*.json` canónicos fueron **restaurados** a su contenido original; las salidas de mi re-ejecución quedaron en `verificacion_rigor/reejecuciones/`. Se eliminó únicamente el `etapa6/__pycache__` que generó la propia re-ejecución. No se borró ni alteró ningún artefacto científico original.

---

## 3. Hallazgos críticos (bloquean liberación)

### C1. P9 evalúa contra un modelo de Tierra equivocado → conclusión invertida

- El generador (`etapa3/config_p3.json`, caso `CTRL-03-STRATIFIED-S1-D0`) usa `rho = [40, 8, 300] Ω·m`, `interfaces = [30, 120] m`.
- El evaluador (`etapa9/config_p9.json` y `etapa9/evaluador_ciego.py`, ~línea 280) usa `rho = [100, 10, 500] Ω·m`, `interfaces = [200, 800] m`.

Con el modelo equivocado reproduzco **exactamente** las cifras publicadas (B0 63.94 %, B4 52.00 %, B8 140.85 %), lo que demuestra que la tabla es real pero medida contra la referencia errónea. Contra la verdad del generador:

| Benchmark | Error mediano Z (verdad publicada) | Error mediano Z (verdad correcta) |
|---|---|---|
| B0 (sin denoising) | 63.94 % | **1.24 %** |
| B4 (CBAM) | 52.00 % | **36.57 %** |
| B8 (Wiener) | 140.85 % | **261.85 %** |

Señal limpia (sin ruido) contra la verdad correcta: 0.424 % en Z, 0.0037 dec en ρa, 0.02° en fase. Es decir, **la señal de entrada ya es casi perfecta y el pipeline la degrada**.

Evidencia: `verificacion_rigor/reevaluacion_p9_verdad_correcta.json`.

### C2. Etiquetas "PASA" falsas en el informe P9

`etapa9/reporte_p9.md` marca como **PASA**:

- Mediana ρa = **0.6267 dec** frente a objetivo preregistrado **≤ 0.05 dec** (12.5× por encima).
- Mediana de fase = **10.47°** frente a objetivo **≤ 3.0°** (3.5× por encima).
- Mejora vs B0 = **18.66 %** frente al mínimo preregistrado de **20 %**.

Ninguna de las tres cumple. El informe las presenta como aprobadas.

### C3. Compuertas incoherentes: un test falla y la compuerta se abre igual

`etapa9/resumen_p9.json`:

- `soundings_results.snd_blind_02_stratified.passed = false`
- `gate_p9_metrics.p9_passed = true`
- `gate_g4_safety.g4_approved = true`

No hay lógica que impida que un fallo se propague; el estado global se calcula ignorando el fallo.

### C4. B8/Wiener está roto (no es una cota lineal válida)

Aplicado a la **señal limpia** (sin ruido), B8 da **261.78 %** de error mediano en Z y fases de **−38° a −44°** frente a verdades de **+38° a +60°**. Un "óptimo lineal" no puede fallar sobre datos limpios. Por tanto la comparación "B4 mejora 63 % vs B8" no significa nada: el rival está mal implementado.

Evidencia: `verificacion_rigor/b8_sobre_senal_limpia.json`.

### C5. Validadores con checks hardcodeados en `True`

En `etapa9/validar_etapa9.py`, 9 de 32 checks pasan sin evaluar nada:

`V-P9-19, V-P9-22, V-P9-24, V-P9-25, V-P9-26, V-P9-27, V-P9-28, V-P9-29, V-P9-31`

En `etapa7/validar_etapa7.py`: `V-P7-29` y `V-P7-31`.

Además, `validar_etapa9.py` **no recalcula** nada: relee `resumen_p9.json`, que a su vez fue producido por el evaluador con la verdad errónea. La validación es circular. Un "32/32 PASA" aquí no certifica nada.

### C6. Fuga de fuente de ruido entre entrenamiento y prueba

`etapa5/split_report.csv` y `etapa5/p5.py` usan la **misma** fuente `NOISE-D0-001` en:

- entrenamiento: `GRP-ENTR-01 / CTRL-01-HALFSPACE-D0`
- prueba: `GRP-TEST-01 / CTRL-05-NONSTATIONARY-SFERICS`

El check de fuga solo compara **etiquetas de grupo**, así que `zero_group_leakage: true` es una falsa garantía: el ruido de test fue visto en entrenamiento.

### C7. La "no inferioridad en limpio" es tautológica

`snd_blind_01_clean.intervened_pct = 0.0`: la red no intervino ninguna ventana, por lo que la salida de B4 es idéntica a la entrada de B0. El 0.0000 % de diferencia no demuestra preservación; demuestra que no se ejecutó el denoisedor sobre esa señal.

### C8. El "ciego" P9 no es ciego

Reutiliza registros ya vistos en otras fases:

- `SND-BLIND-01` ← `CTRL-01` (entrenamiento)
- `SND-BLIND-02` / `SND-BLIND-04` ← `CTRL-03` (validación)
- `SND-BLIND-03` ← `CTRL-05` (prueba)

No hay familia de datos independiente. El plan (§9.1) exige soporte común y comparadores sobre datos no usados en ajuste.

### C9. Faltan comparadores obligatorios del plan

`resumen_p9.json` declara `benchmarks_evaluated = [B0, B1, B3, B4, B7, B8, B10]`, pero en `soundings_results` **B7 no aparece calculado**. Además faltan **B2, B5, B6 y B9** (B7 clasificador solo-potencia, B8 Wiener, B9 familia de ruido independiente son exigidos por el plan, §9.1 / H26). Sin B7 y B9 no se puede afirmar que la red aprendió contaminación y no energía, ni romper la circularidad del mismo motor de ruido.

### C10. P10 libera salidas sintéticas sin marcarlas

`etapa10/salidas/SND-BLIND-02.json` (y otros) declaran:

- `domain_governance.tem_support_status = "soporte_aprobado"`
- `transfer_functions[*].category = "aceptado"` (las 10 funciones de transferencia)

aunque el soporte es sintético (`banco_sintetico/soporte_S1.json`), P9 falló, y `banco_sintetico/README.md` dice explícitamente que el banco sintético **no habilita etiquetas de entrenamiento**. No hay bandera de `synthetic`/`quarantine` en `provenance` ni en la gobernanza del producto. Un consumidor de los `.edi`/`.json` no puede distinguir dato real de sintético.

---

## 4. Hallazgos altos

### A1. Reproducibilidad rota en P7

`V-P7-11` (equivarianza de escala) usa `torch.randn(4,4,256)` **sin semilla** en `etapa7/validar_etapa7.py:133`. El valor almacenado fue `8.28e-05` (PASA, umbral `<1e-4`); en la re-ejecución salió `6.82e-04` (FALLA). El "aprobado" original fue una tirada afortunada.

### A2. El congelamiento P0 está roto hoy

Re-ejecutado, P0 da **RECHAZADO**:

- `V-09`: `ARMT_processing/outputs/soundings_batch/survey_batch_summary.json` = 3946 bytes ≠ 2969 esperados.
- `V-10`: `ARMT_processing/armt/calibration.py` = 4306 bytes ≠ 4143 esperados.

Los hashes/tamaños congelados ya no coinciden con el estado actual de las dependencias.

### A3. Contradicción de gobernanza P2-T vs P3

`etapa2` concluye `soporte_habilitado = false`, 0 filas `respaldada` y **630/630 `no_evaluado`** (bloqueos `B-P0-01 … B-P0-07` abiertos). Aun así, la matriz marca P3 como `APROBADO (Casos de Control Sintético)` y las etapas 5/7/8/9/10 entrenan y liberan con ese soporte. `MATRIZ-P3` falla exactamente por esto.

### A4. El check `NOPYCACHE` de P6 se auto-invalida

Basta con ejecutar el validador (Python crea `etapa6/__pycache__`) para que el check falle. No mide el artefacto: mide si se ejecutó Python antes. Es un check no idempotente.

### A5. Cobertura P6 muy por debajo del diseño, con banda de aceptación relajada

Observado: **0.698** (log10) y **0.719** (fase); bootstrap solo **0.482**. El plan fija una escala de diseño en torno al **95 %** (±1.5 pp). El validador cambió la banda a `[0.45, 0.88]` y marca PASA. Se ajustó el criterio al resultado, no al revés.

### A6. `identity_reconstruction_error = 0.0` es tautológico

En etapa4, la señal se define como `s := x − n`, por lo que `x = s + n` se cumple por construcción. No verifica reconstrucción ICA ni separabilidad.

### A7. La validación P3 (42/42) mide estructura, no ciencia

P3 es sintético y declara `scientific_claim: false`. Sus 42 checks son de archivos/esquema/estructura. No aporta evidencia sobre datos reales, pero se usa como base de P5–P10.

### A8. Se liberó con bloqueos P0 abiertos

`B-P0-01` (sitio no identificado), `B-P0-02` (coordenadas sin datum), `B-P0-03` (vínculo TEM-ARMT no verificado), `B-P0-04` (calibración sin certificado), `B-P0-06` (`F_red_validada` no definida), `B-P0-07` (zona horaria) siguen abiertos, y sin embargo las etapas 7–10 ya entrenaron y publicaron productos.

---

## 5. Hallazgos medios

- **M1.** P9 cubre **un solo escenario sintético por familia**; G3 exige ≥3 sitios independientes por escenario clave antes de abrir la prueba ciega.
- **M2.** Sin repeticiones Monte Carlo: no hay barras de error ni potencia estadística; una sola realización por caso no permite concluir nada.
- **M3.** Los informes (`reporte_p9.md`, matrices) no reconcilian "PASA" con los umbrales numéricos; el texto y los números se contradicen.
- **M4.** No hay pruebas de regresión que detecten cambios en `ARMT_processing` (por eso P0 pasó de aprobado a rechazado sin que nadie lo notara).
- **M5.** Los `.edi` liberados no incluyen metadatos de incertidumbre ni de procedencia sintética.

---

## 6. Qué sí es válido

Para no sobredimensionar el veredicto: sí funcionan y son reproducibles

- la integridad de hashes internos y esquemas de formato;
- la estructura de los productos EDI/JSON y sus contratos de campos;
- el pipeline de orquestación P8–P10 (ejecuta y produce archivos);
- la reproducibilidad de P3/P4/P5/P8 en cuanto a **conteo de checks** (aunque su semántica sea débil).

El problema no es que "no corra": es que **corre y aprueba cosas que no debería aprobar**.

---

## 7. Recomendaciones priorizadas

### P0 — antes de cualquier liberación

1. **Corregir la verdad de P9**: alinear `config_p9.json`/`evaluador_ciego.py` con `config_p3.json` (`rho=[40,8,300]`, `interfaces=[30,120]`) y **re-ejecutar**. Publicar el resultado real (B4 ≈ 36.57 % vs B0 ≈ 1.24 %), no el actual.
2. **Eliminar los checks hardcodeados** (`V-P9-19/22/24/25/26/27/28/29/31`, `V-P7-29/31`) o implementarlos de verdad.
3. **Hacer que `passed=false` bloquee** `p9_passed` y `g4_approved` (propagación de fallos).
4. **Reparar B8/Wiener** y validarlo sobre señal limpia (debe dar error ≈ 0).
5. **Corregir el etiquetado del informe P9**: 0.6267 dec y 10.47° son FALLA, no PASA.
6. **Marcar todo producto sintético** como `synthetic`/`quarantine` en `provenance` y bloquear su publicación como `aceptado`.
7. **Separar fuente de ruido** entre train/val/test y verificar solapamiento por hash de fuente, no solo por etiqueta de grupo.

### P1 — rigor estadístico

8. Sembrar todas las entradas aleatorias (P7 y demás) y añadir test de determinismo (dos ejecuciones → mismo hash).
9. Reemplazar el check `NOPYCACHE` por una comprobación sobre el artefacto, no sobre el entorno.
10. Añadir B2, B5, B6, B7, B9 y reportar sobre soporte común.
11. Evaluar con ≥3 sitios/escenarios independientes y ≥200 realizaciones; reportar IC y potencia.
12. Restaurar la banda de cobertura P6 al criterio de diseño (~95 %) y reportar la subcobertura como hallazgo, no ampliar el intervalo.

### P2 — gobernanza

13. Reconciliar `etapa2` (P2-T vacío) con la matriz y con P3–P10: o se habilita soporte real, o se etiqueta todo como sintético y no liberable.
14. Cerrar o degradar formalmente los bloqueos `B-P0-*` antes de permitir P7–P10.
15. Añadir un gate de release que verifique que P0 y P2 siguen aprobando **hoy**, no solo cuando se escribieron.

---

## 8. Artefactos de esta verificación

| Archivo | Contenido |
|---|---|
| `verificacion_rigor/originales/` | Copia de los `validacion_etapa*.json` originales |
| `verificacion_rigor/reejecuciones/` | Salidas de la re-ejecución (P0 RECHAZADO, P2/P6/P7 FALLA) |
| `verificacion_rigor/reevaluar_p9_verdad_correcta.py` | Recalculo P9 contra la verdad del generador |
| `verificacion_rigor/reevaluacion_p9_verdad_correcta.json` | B0 1.24 %, B4 36.57 %, B8 261.85 % |
| `verificacion_rigor/b8_sobre_senal_limpia.py` | Prueba de B8 sobre señal limpia |
| `verificacion_rigor/b8_sobre_senal_limpia.json` | B8 261.78 % de error con datos limpios |

### Reproducir

```powershell
cd D:\ARRT_software\Robust_denosing_ARMT_estimation
python verificacion_rigor\reevaluar_p9_verdad_correcta.py
python verificacion_rigor\b8_sobre_senal_limpia.py
python etapa7\validar_etapa7.py   # repetir 2-3 veces: V-P7-11 cambia
```

---

## 9. Conclusión

Los sets de prueba **se corrieron**, pero **no aseguraron el rigor**. La suite tiene tres fallas estructurales: (i) validadores que se auto-confirman o están hardcodeados, (ii) una evaluación "ciega" que mide contra la Tierra equivocada y reutiliza datos de entrenamiento, y (iii) compuertas que no propagan fallos y publican salidas sintéticas como reales.

Con la referencia correcta, **el denoisedor no recupera: degrada** (1.24 % → 36.57 % de error mediano). Mientras eso no se corrija y se re-ejecute con semillas fijas, datos independientes y comparadores completos, **no corresponde declarar P9/P10 aprobadas ni liberar los productos**.
