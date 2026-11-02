# Banco sintético de contrato (`banco_sintetico/`)

Fixture aislado para ejercitar la maquinaria de soporte TEM de P2-T **sin afirmar
nada del sitio**. No es una medición TEM, no es una inversión, no es una solución
de Maxwell y no sustituye a P2-T.

- `synthetic: true` y `scientific_claim: false` en todos los artefactos.
- Registro objetivo: `ARMT5-700-14-14-01` (`ARMT_processing/ARMT_data/01401401.sbf`),
  split `desarrollo` de `P0-SPLITS-1.0.0`.
- Solo se copian del manifiesto P0 el identificador, la partición y las trazas
  D0/D1. **No se leen muestras del SBF** ni se toca validación ni prueba.
- IDs `SYN-TEM-*`, nunca `SER-*`.
- No se registra en `etapa0/manifest.json` ni en `etapa0/splits.csv`.

## Advertencia de alcance

Este banco **no cierra `B-P0-03`**, no cierra P2-T y **no habilita etiquetas de
entrenamiento**. Sirve únicamente para comprobar que el contrato de soporte
(ingestión, gates, guardas, clasificación, abstención, reproducibilidad y
aislamiento) funciona antes de disponer de un vínculo TEM–ARMT verificado.

## Estructura

| Ruta | Contenido |
|---|---|
| `modelo_control.json` | Parámetros declarados: bandas, capas, kernels, gates, ruido, umbrales y escenarios. |
| `modelo_surrogate.py` | Modelo directo sintético, sensibilidad por diferencias finitas y clasificación de soporte. |
| `comun.py` | Rutas, hashes, lectura/escritura JSON y verificación de que P0 no cambió. |
| `generar_tem_sintetico.py` | Genera `datos/SYN-TEM-*.tem`, `verdad_S*.json` y `manifiesto_sintetico.json`. |
| `calcular_soporte.py` | Calcula `soporte_S0.json` y `soporte_S1.json` y los enlaza en el manifiesto. |
| `validar_banco_sintetico.py` | Ejecuta las 20 comprobaciones y escribe `validacion_sintetica.json`. |
| `datos/` | Fixtures `.tem` con 48 gates de 0.05–20 ms. |
| `verdad_S*.json` | Verdad declarada: capas, kernels, semilla, ruido y voltajes. |
| `soporte_S*.json` | Frecuencias, sensibilidades, guardas y rangos por banda. |

## Escenarios

| ID | Archivo | Significado | Qué valida |
|---|---|---|---|
| `S0` | `SYN-TEM-001.tem` | Señal constante sin decaimiento útil, sin kernels de capa. | Abstención: intersección vacía, `g0_trigger = true`, ninguna etiqueta limpia. |
| `S1` | `SYN-TEM-002.tem` | Surrogate declarado con capas 40 / 8 / 300 Ω·m. | Soporte parcial: D0 habilitado, D1 condicional por banda muerta AMT. |

El modelo directo es fenomenológico y declarado:

```text
log10 V(t) = log10 A(t) + Σ k_i(t) · log10(ρ_i / ρ_i_ref)
```

`A(t)` es un decaimiento log-lineal entre anclas y `k_i(t)` son kernels gaussianos
en `log10(t)`. **No** se calibró contra ningún instrumento ni contra el subsuelo
del sitio.

## Uso

Desde la raíz del proyecto, en este orden:

```text
python banco_sintetico/generar_tem_sintetico.py
python banco_sintetico/calcular_soporte.py
python banco_sintetico/validar_banco_sintetico.py
```

El generador falla si `etapa0/manifest.json` o `etapa0/splits.csv` no coinciden
con los hashes de `etapa0/validacion_etapa0.json`; así el banco nunca se construye
sobre un P0 alterado.

## Resultados actuales

Validación: **APROBADO**, 20 comprobaciones, 0 fallas (`validacion_sintetica.json`).

**S0 — abstención**

- `supported_ranges_hz`: `[]`
- `application_ranges_hz`: `[]`
- `conditional_ranges_hz`: `[]`
- `empty_intersection`: `true`, `g0_trigger`: `true`
- 0 respaldadas, 48 no respaldadas, 17 no evaluadas (por encima de la ventana de
  difusión disponible).

**S1 — soporte parcial**

- Respaldadas: `125.0–2053.5 Hz` (43 frecuencias).
- Aplicación habilitada: `125.0–937.1 Hz` (32 frecuencias).
- Condicionales: `1000.0–2942.7 Hz` (16 frecuencias), por banda muerta AMT.
- No evaluadas: `3162.3–10000 Hz` (17 frecuencias), sin gates en la ventana.
- Ninguna frecuencia de 1–5 kHz queda habilitada.

Guardas aplicadas: `t ≥ 0.08 ms` y `t ≤ 18.0 ms` (10 % final de la ventana).

## Contrato de soporte

- Mapeo declarado: `t_ms = 1000 / (2π f_hz)`.
- Ventana de difusión: `±0.20 dex` alrededor de `t_eq`.
- Sensibilidad: `|Δlog10 V / Δlog10 ρ|` con perturbación de ±10 % por capa.
- Umbrales: `≥ 0.08` respaldada (con `≥ 3` gates), `≥ 0.03` condicional.
- Banda muerta AMT `1–5 kHz`: penaliza la aplicación, no borra la observación.
- Estados: `respaldada`, `condicional`, `no_respaldada`, `no_evaluada`.
- Aplicaciones: `habilitada`, `condicional`, `no_habilitada`.

## Qué prueba y qué no

**Prueba:** ingestión del formato `.tem`, unidades, gates, guardas, contrato de
soporte, clasificación, rama de abstención, penalización de la banda muerta,
determinismo por semilla y ausencia de fuga hacia P0.

**No prueba:** que exista un TEM real en el sitio, que D0/D1 estén respaldados
físicamente, que el vínculo TEM–ARMT sea válido, ni que las calibraciones sean
aplicables. Tampoco valida el modelo directo como física del subsuelo.

## Cuarentena

`validar_banco_sintetico.py` comprueba explícitamente que:

- los hashes de `etapa0/manifest.json` y `etapa0/splits.csv` siguen coincidiendo
  con `etapa0/validacion_etapa0.json`;
- ningún `SYN-` aparece en el manifiesto P0 ni en `splits.csv`;
- todas las marcas de cuarentena y no-afirmación son correctas;
- regenerar el banco produce hashes idénticos.
