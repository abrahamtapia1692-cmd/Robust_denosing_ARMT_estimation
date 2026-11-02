# Anexo A — Por qué la conversión tiempo–frecuencia TEM→MT/AMT no habilita soporte

Versión `P2T-ANEXO-A-1.0.0`. Documenta una decisión ya tomada en el plan (§3.6)
y en P2-T. **No crea una puerta nueva, no modifica estados y no habilita P3.**
En particular, `tem_amt_support.csv` sigue con 630 filas `no_evaluado` por
`B-P0-03`.

Este anexo responde a una pregunta recurrente: si se conoce el modelo de capas
que ajusta el TEM, ¿no basta convertirlo a frecuencia para extender el soporte
hacia D0/D1? La respuesta es que la conversión es correcta como orientación y
como control, pero no puede certificar qué frecuencias predice el TEM.

## A.1 Tres objetos que suelen confundirse

| Objeto | Definición | Requisitos | Por qué no sirve como corte de aceptación |
|---|---|---|---|
| Continuación analítica exacta | El transitorio TEM es la respuesta en tiempo del mismo operador de difusión; en frecuencia se evalúa en `s = iω` | Transitorio completo, sin ruido, modelo 1D estricto, misma geometría de fuente | Reescritura del mismo dato: no añade información ni rompe la no unicidad; numéricamente mal condicionada |
| Equivalencia de profundidad | Igualar profundidad de difusión TEM y skin depth MT conduce a `t = 1/ω`, es decir `f = 1/(2πt)` | Semiespacio, misma resistividad en ambos métodos | Depende de `ρ`, que es lo que se busca (circular); iguala una profundidad de sondeo con una de piel |
| Regla `f = 1/t` | Correspondencia directa tiempo–frecuencia | Ninguno | Sin base física |

El plan §3.6 es explícito: *«No usar f = 1/t ni f = 1/(2πt) como corte de
aceptación»*. La razón no es que la conversión esté mal calculada, sino que el
criterio de soporte no es de frecuencia: es de **información**.

## A.2 Qué exige el plan para admitir una respuesta TEM→MT

`F_TEM` no es «todo el rango que admite el directo». Es el conjunto de
frecuencias cuya **respuesta objetivo** está suficientemente restringida por el
TEM bajo el modelo físico admitido. P2-T lo evaluó con tres condiciones
independientes, por sondeo y banda:

1. **Envolvente entre modelos admisibles**: semiancho ≤ 0,025 dex en
   `log10 ρ_a`, ≤ 1,5° de fase y ≤ 6,5 % en `Z` compleja. Es el criterio de no
   unicidad.
2. **Profundidad**: fracción de sensibilidad MT bajo la DOI TEM ≤ 0,10.
3. **Subespacio nulo**: fracción de sensibilidad MT en direcciones no resueltas
   por el kernel TEM ≤ 0,10.

Y un tope declarado en `config_p2t.json`:

```text
max_state_without_posterior = "condicional"
cap_reason = conjunto_escenario_no_posterior; F_red_validada_no_definida;
             vinculo_TEM_ARMT_no_verificado; DOI_no_validada; calibracion_parcial
```

Es decir: sin posterior probabilístico, **ni siquiera una coincidencia perfecta
entre modelos podría producir `respaldada`**. `respaldada` es lo único que
habilitaría pares TEM→ARMT.

## A.3 El mapeo aplicado a estos gates

Gates usados en la inversión y su conversión con las dos reglas (rango temporal
completo, no gate a gate):

| Sondeo | Gates usados | t mín–máx (ms) | `f = 1/(2πt)` (Hz) | `f = 1/t` (Hz) |
|---|---:|---:|---:|---:|
| SER-09 | 22 | 0,45–10,29 | 15,5–357,7 | 97–2247 |
| SER-10 | 22 | 0,40–10,25 | 15,5–397,9 | 98–2500 |
| SER-11 | 21 | 0,50–10,25 | 15,5–318,3 | 98–2000 |
| SER-12 | 22 | 0,41–10,26 | 15,5–388,2 | 97–2439 |
| SER-13 | 21 | 0,49–10,24 | 15,5–321,5 | 98–2020 |
| SER-14 | 22 | 0,39–10,23 | 15,6–413,4 | 98–2597 |

El mapeo, tomado literalmente, cubre todo el tramo útil de D0 (15–413 Hz con la
regla `1/(2πt)`) y, con `1/t`, hasta 2,6 kHz. **Y sin embargo P2-T no respalda
ninguna frecuencia.** Ese contraste es la prueba de que la conversión no decide:
si bastara, el soporte sería máximo justo donde el dato no restringe nada.

## A.4 Resultado de P2-T sobre 252 filas (6 sondeos × 42 frecuencias)

| Estado | Filas |
|---|---:|
| `respaldada` | **0** |
| `condicional` (solo a nivel sondeo, no transferible) | 15 |
| `no_respaldada` | 231 |
| `no_evaluado` | 6 |

Motivos de `no_respaldada` (una fila puede acumular varios):

| Motivo | Filas |
|---|---:|
| Sensibilidad MT en subespacio no resuelto por TEM | **183** |
| Envolvente de modelos excede tolerancia | 136 |
| Profundidad de sensibilidad MT excede la DOI TEM | 109 |

El motivo dominante es el **subespacio nulo**, no la profundidad. Bandas
condicionales, todas en D0:

| Sondeo | Banda | Rango | Puntos |
|---|---|---|---:|
| SER-09, SER-10 | — | ninguna | 0 |
| SER-11, SER-12, SER-13 | D0 | 124,745–182,131 Hz | 3 |
| SER-14 | D0 | 124,745–321,308 Hz | 6 |

D1 no tiene ninguna frecuencia condicional.

## A.5 Profundidad: dónde se ve y dónde no

`z50` y `z90` son las profundidades que contienen el 50 % y el 90 % de la
sensibilidad MT; la DOI es la operativa del dosier (100 m en SER-09/10, 175 m
en SER-11..14), **no validada** (`doi_validada_m = null`).

| Sondeo | Banda | z50 mediana (m) | z90 mediana (m) | DOI (m) | Frecuencias con `profundidad_ok` |
|---|---|---:|---:|---:|---:|
| SER-09 | D0 | 62,8 | 199,3 | 100 | 31 % |
| SER-10 | D0 | 65,4 | 215,8 | 100 | 28 % |
| SER-11 | D0 | 66,7 | 227,2 | 175 | 41 % |
| SER-12 | D0 | 69,3 | 229,8 | 175 | 41 % |
| SER-13 | D0 | 66,5 | 229,9 | 175 | 41 % |
| SER-14 | D0 | 66,6 | 234,9 | 175 | 41 % |
| todos | D1 | 12,7–14,5 | 37,4–41,6 | 100/175 | 100 % |

Dos lecturas importantes:

- En **D1 la profundidad no es el problema** (z90 ≈ 40 m, muy por encima de la
  DOI). Falla por envolvente y por subespacio nulo. Cualquier argumento basado
  en *loop más grande* o *más tiempo* no toca esa causa.
- En **D0 la profundidad falla en la parte baja, y el umbral depende del sondeo**:
  SER-09 falla hasta 182,1 Hz y SER-10 hasta 220,1 Hz (a 124,7 Hz,
  `frac` = 0,164 y 0,184); SER-11..14 fallan solo por debajo de 124,7 Hz
  (5–103,2 Hz, ya fuera del rango del estimador de P6). A 321 Hz el `z90` es
  93–100 m y `frac` ≤ 0,075 en los seis sondeos. La restricción de D0 no es
  uniforme: es de banda baja y algo mayor en SER-09/10, que además tienen la
  DOI más somera (100 m).

## A.6 El caso del «semiespacio compartido a 300 m»

Una propuesta frecuente es fijar en ambos métodos un semiespacio por debajo de
300 m con la misma resistividad, para «asegurar consistencia». En un modelo 1D
la última capa **ya** es un semiespacio; lo que se añade es **fijar su techo y
su valor**. Eso es una suposición medible.

Se tomó cada uno de los 18 modelos (1 base + 2 de estabilidad por sondeo), se
truncó a 300 m y se sustituyó el semiespacio por 10, 30, 100, 300 y 1000 Ωm.
Máximo sobre los 18 modelos, en `log10|Z|` y su equivalente en `ρ_a`
(`Δlog10 ρ_a ≈ 2·Δlog10|Z|`), frente al presupuesto de 0,025 dex:

| f (Hz) | max abs(Δlog10 Z) (dec) | Δρ_a (dex) | Δfase (°) | Consumo del presupuesto |
|---:|---:|---:|---:|---:|
| 5,00 | 0,2056 | 0,4113 | 30,1 | **1645 %** |
| 15,56 | 0,0512 | 0,1023 | 21,2 | 409 % |
| 33,17 | 0,0410 | 0,0820 | 11,8 | 328 % |
| 124,75 | 0,0169 | 0,0338 | 1,3 | 135 % |
| 150,73 | 0,0112 | 0,0224 | 1,1 | 89 % |
| 321,31 | 0,0017 | 0,0034 | 0,3 | 13 % |
| 684,92 | 0,0002 | 0,0003 | 0,03 | 1 % |
| ≥1000 | <0,0001 | <0,0001 | <0,01 | ≈0 % |

Conclusiones:

- **Por encima de ~320 Hz el semiespacio profundo es irrelevante** (≤13 % del
  presupuesto, y ≤1 % desde 685 Hz). Fijarlo ahí es una regularización benigna y
  declarable.
- **Entre 182 y 265 Hz consume del 15 % al 58 %**; no es despreciable, pero
  tampoco domina.
- **A 124,7–150,7 Hz consume del 89 % al 135 %**: fijarlo no es neutral, es una
  suposición con peso.
- **Por debajo de 124,7 Hz lo excede entre 2 y 16 veces** (188–1645 %).
- Como el TEM tiene DOI 100–175 m, **el valor a 300 m no lo aporta el TEM**.
  Compartir ese parámetro significa que la información fluye del AMT al TEM, no
  al revés: puede ser una inversión conjunta defendible, pero no demuestra que
  el TEM soporte la respuesta AMT.
- Y aunque los dos modelos coincidieran exactamente, el tope
  `max_state_without_posterior = "condicional"` seguiría vigente.

## A.7 Qué sí se puede hacer con la conversión

1. **Tabla de orientación, etiquetada como no-evidencia** (A.3 y A.6). Sirve
   para elegir qué frecuencias inspeccionar y para documentar por qué la regla
   no se usa como criterio.
2. **Directo completo por modelo**: evaluar `Z_MT` con `mt1d` sobre cada modelo
   admisible y medir la envolvente. Es lo que hizo P2-T; es la forma correcta de
   «convertir» TEM a MT.
3. **Casos analíticos de control**: modelo 1D conocido → series AMT sintéticas
   con `mt1d`, con etiqueta de control. No satisface P3 ni genera etiquetas TEM.

Lo que **no** se puede hacer es rellenar `tem_amt_support.csv` con la
conversión: sería declarar verificado lo que `B-P0-03` mantiene abierto, y la
matriz afirmaría un soporte que ningún artefacto respalda.

## A.8 Conclusión

La conversión tiempo–frecuencia es correcta como reescritura del mismo dato y
útil como orientación, pero no certifica soporte. Sobre estos datos:

- el mapeo `f = 1/(2πt)` cubre 15–413 Hz de D0 y aun así el soporte es **0/252**;
- la causa dominante es el **subespacio nulo** (183 filas), seguida de la
  envolvente (136) y de la profundidad (109);
- en D1 la profundidad no es el problema (z90 ≈ 40 m), luego un loop mayor no
  la resolvería;
- fijar un semiespacio común a 300 m es benigno ≥320 Hz, consume el 89–135 %
  del presupuesto a 124,7–150,7 Hz y lo excede entre 2 y 16 veces por debajo de
  124,7 Hz.

El estado de P2-T no cambia: **0 `respaldada`**, 15 condicionales diagnósticas en
D0, 231 no respaldadas y 6 no evaluadas. P3–P5 y P7 siguen cerradas por
`B-P0-03`.

## Reproducibilidad

Las tablas A.3, A.5 y A.6 se regeneran con:

```powershell
python etapa2/anexo_conversion_tf.py
```

Entradas: `etapa2/tem_valid_gates.csv`,
`etapa2/diagnostico_tem/comparacion_sensibilidad_doi.csv`,
`etapa2/model_provenance.json` (18 modelos) y `etapa1/respuesta_interpolada_*.csv`
(grillas). El directo es `etapa2/mt1d.py`. El script no escribe archivos.
