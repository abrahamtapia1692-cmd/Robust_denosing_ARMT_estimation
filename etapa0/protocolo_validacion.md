# Protocolo de validación — Etapa 0 (puerta P0)

**Versión:** 1.0.0  
**Fecha de congelación:** 2026-10-28  
**Ámbito:** inventario, contrato de datos, particiones y reglas de evaluación del piloto ARMT MT/AMT en D0/D1.  
**Documento rector:** `PLAN_IMPLEMENTACION_ARMT.md` v1.3, secciones 3.6 y 4.  
**Estado de la puerta:** **PARCIAL**. El manifiesto existe y las particiones están congeladas, pero la identidad de sitio, las coordenadas, el vínculo TEM–ARMT, la validez de calibración y el QC siguen sin resolverse.

Este protocolo no certifica resultados geofísicos. Fija qué se medirá, con qué unidades, sobre qué registros y con qué reglas se declarará éxito o abstención. Ningún resultado posterior puede ampliar retrospectivamente el alcance aquí escrito.

## 1. Alcance congelado

| Elemento | Decisión |
|---|---|
| Bandas incluidas | D0 y D1 |
| Bandas excluidas | D2 y D3; no se usan para entrenamiento, etiquetas ni evaluación del piloto |
| Portadoras RMT | Fuera de alcance; no se separan ni se envían a la red AMT |
| Productos | MT/AMT: tensor completo, respuesta direccional, tipper y frecuencia no identificable |
| Detector y separador | Tareas separadas: `Cθ` decide intervención; `Dψ` reconstruye. No se exige que la BSS entregue `Sx`, `Sy` ni `Zopt` |
| Soporte TEM | P2-T es obligatoria antes de sintetizar. Un soporte vacío es un resultado válido y cierra la rama TEM de ese sondeo |
| Unidad de partición | Registro SBF completo; nunca ventanas, trazas o canales sueltos |
| Lectura de fuentes | Solo lectura; los proyectos de origen no se modifican |

## 2. Definiciones operativas

- **Registro:** un archivo SBF con su hash SHA-256. Es la unidad indivisible de partición y de trazabilidad.
- **Sitio:** agrupación lógica declarada por `site_group`. En este inventario se deriva de año, arreglo y línea; el nombre oficial del sitio es desconocido.
- **Campaña:** agrupación `campaign_group`, derivada del año y del arreglo. La etiqueta oficial es desconocida.
- **Tramo limpio:** intervalo sin contaminación declarada y con evidencia suficiente. La ausencia de evidencia no lo convierte en limpio.
- **Soporte:** conjunto de frecuencias y observables con respaldo TEM bajo el modelo admitido. No es todo el rango nominal de la banda.
- **Desconocido:** campo declarado `null` y registrado en `unknowns`. No se sustituye por un valor plausible, una media, una calibración unitaria ni una coordenada inferida.
- **Abstención:** salida explícita del sistema cuando el soporte, la calibración o la identificabilidad no permiten una respuesta defendible.

## 3. Universo de datos y manifiesto

El manifiesto `etapa0/manifest.json` es la fuente de verdad del inventario. Contiene, por registro: ruta, SHA-256, tamaño, fecha de modificación, campaña inferida, sitio desconocido, ajustes instrumentales, trazas D0–D3, calibraciones candidatas, partición, vínculo TEM y estado de QC.

Reglas del manifiesto:

1. Todo archivo usado en el piloto tiene hash SHA-256 y tamaño.
2. Todo campo desconocido es `null` y aparece en `unknowns`.
3. Todo bloqueo que impida cerrar P0 aparece en `blockers` con estado y evidencia.
4. Las rutas distinguen `workspace` de `software_root`; no se mezclan bases.
5. El manifiesto no se edita a mano: se regenera con `etapa0/inventario_armt.py`.

### 3.1. Conteo inventariado

| Conjunto | Cantidad | Observación |
|---|---:|---|
| Registros SBF | 15 | 13 de 2021 (arreglo 700) y 2 de 2023 (arreglo 123) |
| Trazas | 60 | Cuatro trazas por registro: D0, D1, D2 y D3 |
| Canales escalares | 300 | Cinco canales por traza: Ex, Ey, Hx, Hy, Hz |
| Archivos de calibración `.clb` | 73 | 9 grupos de ganancia; incluye una variante `e000101-5.6_real.clb` |
| Sondeos TEM candidatos | 6 | `SER-09` a `SER-14`, sin vínculo verificado con ARMT |

Los registros D2/D3 se inventarían para comprobar exclusiones, pero no entran en el conjunto de entrenamiento ni de evaluación.

## 4. Particiones congeladas

Versión de la política: `P0-SPLITS-1.0.0`. Asignación a nivel de registro, con separación por campaña y sitio. La tabla completa, con hashes, está en `etapa0/splits.csv`.

| Partición | Registros | Grupos | Uso permitido |
|---|---:|---|---|
| Desarrollo | 10 | 2021, arreglo 700: líneas 1 (estaciones 0, 23, 24), 14, 24, 32, 34, 42, 44 y 45 | Ajuste, selección y análisis exploratorio |
| Validación | 3 | 2021, arreglo 700: líneas 43, 55 y 90 | Selección de hiperparámetros y comprobación de estabilidad |
| Prueba | 2 | 2023, arreglo 123: líneas 1 y 2 | Bloqueado hasta P9; no se inspecciona para decisiones de diseño |

Reglas de no fuga:

1. Un registro pertenece a una sola partición.
2. Un `site_group` no puede aparecer en dos particiones.
3. La campaña de prueba no puede aparecer en desarrollo ni en validación. Desarrollo y validación pueden compartir campaña solo si los sitios son distintos.
4. Las ventanas, plantillas de ruido o pares derivados heredan el grupo del registro padre; si comparten padre con otra partición, se rechazan.
5. La campaña 2023 queda completamente reservada. No se usa para elegir filtros, umbrales, arquitectura ni épocas.
6. La validación de 2021 no se reutiliza como prueba. Si se necesita una segunda evaluación, se abre otra campaña o se declara no concluyente.
7. Cambiar una asignación exige una nueva versión de `splits.csv`, un nuevo manifiesto y la invalidación de los resultados afectados.

La asignación es una **propuesta congelada**, no una verdad de campo. Se apoya en la campaña y la línea porque no hay nombres de sitio ni coordenadas verificadas. Si la revisión documental demuestra que dos líneas son el mismo sitio físico, el grupo se corrige antes de P9 y se versiona.

## 5. Contrato de datos

El esquema `etapa0/schema.json` (JSON Schema draft-07) fija los campos obligatorios. Los adaptadores deben comprobar forma, unidades y banderas al entrar y salir.

| Objeto | Contenido mínimo |
|---|---|
| Registro | `record_id`, hash, campaña, sitio, ajustes, trazas, calibración, partición, vínculo TEM, QC |
| Traza | banda, máscara, `fs`, `N`, duración, canales, bytes por muestra, tiempos, coordenadas crudas, `adc_to_uv` |
| Calibración | archivo, hash, tipo, serie, ganancia de directorio, tabla, rango de frecuencia, estado |
| Partición | `split`, `split_group`, `campaign_group`, versión y bandera de congelación |
| Soporte | sondeo, banda, frecuencia, observable, máscara, envolvente, sensibilidad, motivo y versión |

Convenciones:

1. Las muestras se conservan en cuentas enteras; la conversión a µV es una vista y debe declararse.
2. El orden de canales es el bit ascendente habilitado `Ex, Ey, Hx, Hy, Hz`; sigue siendo una política a verificar con datos reales.
3. Las marcas de tiempo son locales y sin zona declarada. No se convierten a UTC por conveniencia.
4. Las coordenadas crudas se guardan como `UInt32`. Se registra una candidata con la política `radianes × 10^8` en complemento a dos, pero no se adopta como coordenada verificada mientras no exista confirmación independiente del signo y del datum.
5. Las ganancias y las calibraciones no se aplican en esta etapa. Una calibración ausente no se convierte en respuesta unitaria.
6. La longitud de dipolo, la polaridad y el acoplamiento entre canales quedan como campos a verificar en P1.
7. Las ganancias de registro 1.77828 y 3.16228 se emparejan a los directorios G1.8 y G3.2 con una diferencia relativa de aproximadamente 1.2 %. P0 no corrige esa diferencia; se revisa en P1.

## 6. Protocolo de evaluación

Las reglas siguientes se congelan ahora, aunque se ejecuten en etapas posteriores. Los umbrales son propuestas piloto y se sustituyen solo por una versión explícita del protocolo antes de abrir la prueba.

### 6.1. Endpoint primario

Para cada escenario y subbanda habilitada se evalúa, en este orden:

1. **Identificación:** tasa de falsos positivos sobre tiempo limpio y sensibilidad sobre episodios declarados detectables.
2. **Separación:** error complejo de la respuesta recuperada y preservación de la señal útil.
3. **Cadena completa:** no inferioridad en limpio y mejora frente a la referencia robusta.
4. **Abstención:** proporción de casos correctamente declarados fuera de soporte o no identificables.

No se elige una variante por `accuracy` del detector ni por MSE del separador.

### 6.2. Métricas

| Métrica | Definición | Uso |
|---|---|---|
| FPR temporal | Tiempo limpio marcado como contaminado / tiempo limpio total, tras solapamiento y guardas | Detector |
| Sensibilidad de episodios | Episodios detectados / episodios declarados detectables | Detector |
| Error complejo | `abs(Z_hat - Z) / abs(Z)` en la frecuencia evaluada | Separador y cadena |
| Error en `log10(rho_a)` | Diferencia absoluta en décadas | Separador y cadena |
| Error de fase | Diferencia circular absoluta en grados | Separador y cadena |
| Identidad | Error de reconstrucción con la máscara ideal y con la máscara predicha | Separador |
| Falsa recuperación | Casos declarados recuperados que fallan el criterio de verdad | Cadena |
| Cobertura | Fracción de intervalos que contienen el valor de referencia | Incertidumbre |

El presupuesto se expresa en **1σ**, no en medianas. Se reportan por separado sesgo sistemático y dispersión aleatoria. Las metas de 0.05 décadas y 3° se mantienen como metas independientes; no se colapsan en un único porcentaje.

### 6.3. Comparadores obligatorios

| Comparador | Qué controla |
|---|---|
| B0 | Datos calibrados con estimación robusta; referencia básica |
| B1 | QC y selección espectral sin aprendizaje |
| B7 | Clasificador que solo usa potencia; detecta atajos de energía |
| B8 | Wiener multicanal con covarianza verdadera y estimada; cota lineal |
| B9 | Familia de ruido generada por un mecanismo distinto de la BSS |
| B10 | Oráculo de ruido y máscara ideal; separa errores de detector, separador y estimador |

Si `Cθ` no supera a B7, no se justifica la no linealidad del detector. Si `Dψ` no supera a B8, no se justifica la no linealidad del separador. B9 rompe la circularidad de evaluar con el mismo motor que entrenó.

### 6.4. Umbrales preregistrados

| Control | Umbral propuesto | Consecuencia |
|---|---|---|
| FPR sobre tiempo limpio | ≤ 1 % | Si se supera, el detector no se habilita |
| Sensibilidad en episodios declarados detectables | ≥ 90 % | Se informa junto con la fracción físicamente indetectable |
| Error complejo en soporte | Meta 0.05 décadas y 3° por separado | Se evalúa contra el presupuesto 1σ |
| No inferioridad en limpio | Margen preregistrado; propuesta inicial 10 % relativo en error complejo | Si falla, no se libera |
| Falsa recuperación | > 5 % | Falla G4 y no se libera |
| Sitios independientes por escenario | ≥ 3 | Si hay menos, no se abre la prueba ciega |
| Subconjunto detectable | ≥ 30 % | Si hay menos, el resultado se declara no concluyente |

Estos valores no son resultados. Se congelan antes de ver la prueba y pueden endurecerse, no relajarse, con la evidencia de P1–P8.

### 6.5. Modelo estadístico

1. El endpoint primario se declara antes de abrir la prueba.
2. Sitio y registro entran como efectos aleatorios en un modelo jerárquico.
3. Los intervalos son cluster-robustos por sitio o campaña, según el diseño.
4. Se corrige por comparaciones múltiples con un método fijado antes del análisis.
5. Se reportan cobertura, amplitud y sesgo de los intervalos; un intervalo estrecho no prueba exactitud.
6. Se reportan resultados por subbanda, por observable y por tipo de blanco, no solo el agregado.

## 7. Soporte TEM y abstención

1. Solo las frecuencias clasificadas como **respaldadas** habilitan pares TEM–MT/AMT.
2. Las frecuencias **condicionales**, **no respaldadas** y **no evaluadas** se conservan en el diagnóstico, pero no generan etiquetas limpias ni entrenamiento supervisado.
3. Si la intersección con D0/D1 es vacía, se registra el motivo y se cierra la rama TEM de ese sondeo. No se extrapola para completar la banda.
4. La falta de soporte TEM no prueba que el ARMT observado sea inutilizable; se conserva la adquisición y, si procede, la estimación convencional con su propia evaluación.
5. La máscara de subbanda y la máscara temporal no conmutan. Toda intervención temporal se reproyecta al soporte aprobado.
6. La ausencia de una referencia independiente se declara; no se fabrica un blanco exacto.

## 8. Puertas y escalera de parada

| Puerta | Condición | Decisión |
|---|---|---|
| P0 | Manifiesto completo para el piloto y protocolo congelado, con desconocidos explícitos | Solo entonces se abre P1 |
| P1 | Recuperación instrumental dentro de la tolerancia fijada y datos inválidos marcados | Sin P1 no se interpretan amplitudes ni fases |
| P2-T | Frecuencias respaldadas, excluidas, sensibilidades, envolventes y guardas documentadas | Solo las frecuencias aprobadas continúan |
| G0 | Intersección vacía o sin subbanda admisible en 1–2 sitios | Cerrar la rama TEM; entregar resultado negativo |
| G1 | B0/B1 no recupera casos sintéticos identificables | Corregir el estimador antes de entrenar |
| G2 | B4 no supera a B1/B8 por el margen preregistrado | Mantener la referencia; red experimental |
| G3 | Menos de 3 sitios independientes por escenario o subconjunto detectable < 30 % | No abrir la prueba ciega; reportar no concluyente |
| G4 | Falla la no inferioridad en limpio o la falsa recuperación supera 5 % | No liberar |

## 9. Congelación y control de cambios

1. Este documento, `schema.json` y `splits.csv` se hashean en el manifiesto.
2. Cualquier cambio de alcance, partición, métrica o umbral incrementa la versión y regenera el manifiesto y la validación.
3. No se reasigna un registro después de ver resultados de prueba.
4. No se amplía `F_red_validada` ni la máscara TEM después de observar el desempeño.
5. Los resultados afectados por un cambio de etiqueta se regeneran; no se parchean.
6. La prueba 2023 permanece cerrada hasta que P9 se habilite por escrito.

## 10. Criterios de cierre de P0 y estado actual

| Requisito | Estado | Evidencia |
|---|---|---|
| Inventario de registros, campañas, fechas, bandas, `fs`, duración, canales, sensores, ganancias, orientaciones y dipolos | CUMPLIDO con campos desconocidos explícitos | `manifest.json`, sección `armt_records` |
| Hash de archivos y versiones de software | CUMPLIDO | `manifest.json`, secciones `sources`, `software`, `armt_records` |
| Definición de productos y exclusión D2/D3 | CUMPLIDO | `scope`, este protocolo |
| Separación de datos por campaña y sitio | CUMPLIDO como propuesta congelada | `splits.csv`, sección 4 |
| Contrato común versionado | CUMPLIDO | `schema.json` |
| Presupuesto de error distribuido | PARCIAL | Este protocolo fija metas; falta la calibración instrumental de P1 |
| Protocolo de evaluación congelado | CUMPLIDO | Este documento |
| Identidad de sitio y coordenadas verificadas | PENDIENTE | `unknowns` U-01 a U-04; existe una candidata signed no verificada |
| Vínculo TEM–ARMT | PENDIENTE | `unknowns` U-05; `tem_dataset.link_status` |
| Validez de calibración | PENDIENTE | `blockers` B-P0-04 |
| QC de clipping, canales muertos, saltos y muestras faltantes | PENDIENTE | `blockers` B-P0-05 |
| Lectura completa sin cambiar valores | Verificar con `validar_muestras.py` | `validacion_muestras.json` |

**Conclusión:** P0 se declara **PARCIAL**. El piloto puede continuar hacia P1 con el inventario y las particiones congeladas, pero no puede generar etiquetas TEM, ni afirmar identidad de sitio, ni aplicar calibración como si estuviera verificada.

## 11. Bloqueos abiertos

| ID | Bloqueo | Efecto |
|---|---|---|
| B-P0-01 | Nombre e identificador oficial del sitio desconocidos | No se puede afirmar continuidad espacial ni agrupar por geología |
| B-P0-02 | Coordenadas solo candidatas; politica de hemisferios no verificada | Existe una lectura signed plausible (17.8–19.3°N, 99.6–99.7°W), pero no se adopta sin confirmacion independiente |
| B-P0-03 | Vínculo TEM–ARMT no verificado | Ningún sondeo TEM puede aportar etiquetas al piloto |
| B-P0-04 | Calibraciones sin fecha, certificado ni cadena de aplicación | No se pueden interpretar amplitudes ni fases como campo |
| B-P0-05 | QC no evaluado | No se conocen clipping, canales muertos, saltos ni huecos |
| B-P0-06 | Etiquetas de escenario y familia de ruido ausentes | G3 no es evaluable por escenario |
| B-P0-07 | Zona horaria de las marcas temporales no declarada | No se pueden alinear eventos entre instrumentos |

Estos bloqueos no se cierran con supuestos. Se cierran con documentación del sitio, metadatos del instrumento, verificación independiente o una decisión explícita de excluir el registro del alcance.
