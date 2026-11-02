# Especificación de ruido, etiquetas y aprendizaje para MT/AMT

**Versión:** 1.3 · **Fecha:** 28 de octubre de 2026  
**Documento complementario de:** PLAN_IMPLEMENTACION_ARMT.md.  
**Estado:** diseño de implementación; no se ha entrenado ni certificado un separador con este protocolo.

**Registro de cambios v1.3:** se añaden el presupuesto de rango, la coherencia con `K_eff`, la consistencia E/H con TEM, la resolución espectral por subbanda (`F_red_validada`), la detectabilidad previa y el pareo de potencia. No se cambia el alcance D0/D1 ni se relajan P4-N/P5-L/P7.

## 1. Objetivo y restricciones que se conservan

El producto de la etapa de extracción será un **catálogo de episodios contaminantes**: forma de onda, inicio, fin, duración, recurrencia, envolvente, amplitud, espectro, deriva y contribución observada en cada canal. No es necesario entregar las polarizaciones naturales Sx/Sy ni estimar Z como resultado de esta etapa.

Sí se conserva la información multicanal necesaria para reconstruir e inyectar cada episodio. El catálogo puede consultarse por “forma y tiempo de ruido” sin perder, internamente, su escala y acoplamiento a Ex/Ey/Hx/Hy y eventualmente Hz. Eliminar esa información impediría generar contaminación realista para una red multicanal.

El alcance sigue siendo MT/AMT en subintervalos D0/D1. Las etiquetas sintéticas derivadas de TEM se limitan al soporte aprobado por P2-T. D2/D3 y la recuperación neuronal de portadoras RMT no forman parte del trabajo.

## 2. Qué está sustentado por los autores y qué se propone aquí

| Fuente | Alcance comprobado | Consecuencia para este proyecto |
|---|---|---|
| Ogawa et al., 2023 | El resumen institucional describe FDICA con datos locales y magnéticos de referencia, identificación mediante relaciones espectrales con la referencia y selección de supresión mediante propiedades de las respuestas MT. | Reutilizar la separación/reconstrucción como herramientas. Un extractor de episodios sin referencia y sin selección por respuesta MT es una adaptación que debe validarse por separado. |
| Zhang et al., 2024, sección II-A–C y figuras 2–4 | Emplean registros sintéticos y segmentos de campo de bajo ruido; añaden contaminación correlacionada extraída o representativa del sitio. Separan clasificación binaria y reconstrucción supervisada. | Mantener dos conjuntos y dos objetivos distintos; la etiqueta de clasificación no sustituye a la serie limpia necesaria para reconstrucción. |
| Hyvärinen y Oja, 2000 | La ICA lineal requiere supuestos de independencia, distribución y mezcla; tiene ambigüedades de escala y orden. | La coherencia entre canales no basta para asignar identidad física ni garantizar separación. |

Referencias primarias: [Ogawa, registro institucional](https://jopss.jaea.go.jp/search/servlet/search?5075669=&language=1), [Zhang, artículo](https://doi.org/10.1109/TGRS.2024.3361942), [Hyvärinen y Oja, manuscrito de los autores](https://www.cs.helsinki.fi/u/ahyvarin/papers/NN00new.pdf).

La comprobación bibliográfica de Ogawa aquí se limita al resumen institucional y se complementa con lectura del código local; no se declara equivalencia ecuación por ecuación con el artículo completo. La sección metodológica de Zhang sí se consultó. Las máscaras, niveles de evidencia, pruebas de fuga y reglas de aceptación siguientes son **propuestas de diseño**, no garantías atribuidas a esos autores.

En Zhang, el conjunto de identificación se equilibra entre clases 0/1 y se combinan orígenes sintético/campo en partes iguales; son dos balances diferentes. El conjunto de denoising usa entradas contaminadas con su referencia correspondiente. Aquí esas proporciones solo sirven como reproducción inicial, y se ajustan mediante validación. No constituyen una condición teórica de separación.

## 3. Modelo de ruido y límite de identificabilidad

### 3.1 Fuente común y huella multicanal

En un intervalo aproximadamente lineal:

```text
x_c(t) = s_c(t) + Σr n_cr(t) + ε_c(t)
n_cr(t) = h_cr * [g_r(t) q_r(t)]

c: canal observado
r: episodio/familia de fuente
q_r: forma temporal de la fuente
g_r: actividad/envolvente del episodio
h_cr: acoplamiento fuente–canal, con ganancia, fase y retardo
ε_c: otras contribuciones y error instrumental
```

La convolución admite que una misma fuente genere formas diferentes en E y H. En una subbanda estrecha puede aproximarse por una mezcla compleja A(f). Si el acoplamiento cambia, se segmenta el intervalo o se modela su variación.

No se exige n_Ex = n_Ey = n_Hx = n_Hy ni amplitud idéntica. La respuesta de un canal puede ser débil o casi nula por orientación, acoplamiento o piso instrumental. La hipótesis de ruido común se verifica sobre un subconjunto informativo de canales; no se obliga a observarlo con alta coherencia en los cuatro.

El número de ruidos separables está acotado por `k_max(f)=C−r_s(f)`; con cuatro canales y dos polarizaciones, dos; con Hz, tres si su piso lo permite. En frecuencia, el campo natural es aproximadamente complejo gaussiano tras promediar; ICA separa como máximo una fuente gaussiana. No se exige Sx/Sy, pero no se garantiza separar ruido gaussiano. La mezcla `A(f)` debe ser aproximadamente constante dentro de la subbanda; usar subbandas fraccionales y comprobar su estabilidad.

### 3.2 Por qué “coherente en todos los canales” no es una prueba suficiente

Considérese x_c(t) = a_c [s(t) + n(t)]. Todos los canales pueden ser perfectamente coherentes. Sin otra restricción, sustituir s por s+h y n por n−h produce exactamente las mismas observaciones. Hay infinitas descomposiciones compatibles.

La alta coherencia identifica dependencia compartida, no cuál parte es contaminación. Además, dos versiones en cuadratura de una fuente pueden tener correlación instantánea cercana a cero y coherencia espectral elevada. Por eso se conserva fase/retardo y no se usa únicamente Pearson a desfase cero.

En la ICA clásica, independencia/no gaussianidad y rango suficiente permiten separación bajo condiciones concretas, hasta escala y permutación; fuentes gaussianas múltiples, mezcla colineal o fuentes dependientes requieren información adicional o métodos distintos. Esto no significa que todos los ruidos de campo deban cumplir ICA: significa que, si no cumplen sus hipótesis, esa técnica no puede certificarlos como fuentes separadas.

**Regla de decisión propuesta:** admitir una contribución en el banco de ruido solo cuando existe evidencia de contaminación adicional a la coherencia, reconstrucción multicanal estable y fuga de señal útil aceptable. Si solo se conoce que existe un patrón común, etiquetarlo como componente ambigua.

### 3.3 Tres niveles de confianza

| Estado | Evidencia | Uso permitido |
|---|---|---|
| Ruido admitido | Evidencia de origen/actividad contaminante, estabilidad del método y pruebas de preservación satisfactorias. | Plantilla multicanal para inyección, con límites de amplitud, dominio y proveniencia. |
| Candidato o ambiguo | Patrón compartido sin atribución suficiente, separación inestable o posible mezcla con señal natural. | Exploración y pruebas de estrés etiquetadas; no etiqueta limpia ni verdad de ruido físico. |
| Señal protegida | Sferics u otra señal útil sustentada, o componente que no puede retirarse sin sesgar Z. | Control de no eliminación y ejemplos difíciles del detector. |

La repetición armónica, horarios industriales, referencia auxiliar, repetición entre estaciones o sincronía con un equipo son evidencias posibles. Ninguna heurística aislada, ni siquiera un tipper alto, se convierte en prueba universal.

## 4. Extractor de episodios a partir del código BSS

### 4.1 Ruta mínima y función de Ogawa

1. Recibir registros calibrados D0/D1, máscaras y escalas reversibles.
2. Detectar actividad compartida y cambios de régimen mediante espectros, envolventes y retardos.
3. Descomponer intervalos candidatos con el motor FDICA que realmente se ejecute; conservar también comparadores simples de bajo rango como diagnóstico.
4. Seleccionar candidatos por evidencia temporal/espectral y externa disponible.
5. Resolver escala y permutación, reconstruir la contribución en los canales originales.
6. Agrupar eventos repetidos y guardar plantilla/episodios sin perder su identidad de origen.
7. Aprobar, mantener ambiguo o rechazar mediante pruebas de fuga y estabilidad.

No se obliga a que existan exactamente dos componentes de ruido ni a llamar a las otras dos Sx/Sy. Si varias fuentes no pueden separarse, puede guardarse un **episodio compuesto**; no se inventan identidades individuales. La estimación de Z se utiliza posteriormente como control de daño, no como salida obligatoria del extractor.

La polarización queda como diagnóstico opcional. La asociación fuente–canal y la reconstrucción son requisitos; la clasificación de polarizaciones naturales no es un entregable requerido.

### 4.2 Coherencia correctamente estimada

```text
γ²ij(f) = |Sij(f)|² / [Sii(f) Sjj(f)]
```

Los espectros deben promediar realizaciones/tapers/bloques con dependencia y grados de libertad declarados. Con un solo par de coeficientes, |Xi conj(Xj)|² / (|Xi|² |Xj|²) es trivialmente 1 si ambos son no nulos. No usarlo para detectar o clasificar ruido.

Con `K` promedios independientes, `γ²_crit = 1 − 0.05^{1/(K−1)}` (K=8→0.35; K=16→0.18; K=64→0.05). Reportar `K_eff`, no el número nominal de ventanas solapadas; con seis pares de canales, corregir por comparaciones múltiples. La coherencia es una prueba de detección, no de identidad.

Evaluar también fase de Sij, retardos, autovalores y estabilidad temporal. Una componente dominante en PCA indica varianza compartida, no certifica ruido.

### 4.3 Dos representaciones del catálogo

| Representación | Contenido | Uso |
|---|---|---|
| Episodio observado | Matriz N_r de forma tiempo×canal, reloj, fs, unidades, máscaras y residual de reconstrucción. | Inyección empírica de referencia; conserva relaciones reales entre canales. |
| Modelo de forma/acoplamiento | q_r, envolvente, duraciones, recurrencia y h_cr o A_cr(f), con errores de ajuste. | Generar variantes plausibles si se demuestra que el modelo reproduce el episodio observado. |

No copiar una única curva con el mismo valor a todos los canales como receta general. Puede existir un control sintético de modo común idéntico, pero no debe representar todo el banco.

Las variantes cambian conjuntamente intensidad/actividad de la fuente. Cambiar cada canal de forma independiente destruye la coherencia que se pretende aprender. Reutilizar una huella en otra geología sigue siendo una mezcla semisintética empírica; no prueba que esa fuente produzca la misma huella en ese subsuelo.

### 4.4 Pruebas de admisión

- Reconstrucción sin eliminación y suma de contribuciones más residual.
- Estabilidad frente a semilla, tamaño de ventana y subconjunto de canales informativos.
- Recuperación en mezclas conocidas, incluyendo casos donde ICA no puede separar.
- Inyección de señal MT/AMT conocida y cuantificación de cuánto aparece en el ruido extraído.
- Repetición con sferics útiles; conservación de Z, fase y amplitud en el soporte autorizado.
- Comparación entre el episodio observado y variantes paramétricas: tiempos, PSD, espectros cruzados y retardos.

- Consistencia E/H con la envolvente TEM: `ρ_comp` y pendiente–fase como evidencia asimétrica; una componente compatible no prueba origen natural (una fuente lejana de línea estrecha también pasa).

Los umbrales del plan son metas piloto. Si falla la admisión, conservar la plantilla como ambigua; no mejorar artificialmente su etiqueta mediante suavizado.

## 5. Auditoría del código local relevante

La revisión es de código y metadatos MAT; no incluye entrenamiento ni certificación de las etiquetas existentes.

| Archivo | Hallazgo | Acción |
|---|---|---|
| cpp/src/estimator/FDICAReconstructor.cpp | identify_components asigna dos componentes naturales mediante referencia y las otras dos a ruido. | Desacoplar el extractor de episodios de esa asignación fija cuando no exista referencia validada. |
| El mismo archivo, apply_strategy | Calcula una razón por coeficiente que algebraicamente tiende a 1 para amplitudes no nulas. | Sustituirla, si participa en la ruta productiva, por estimación espectral promediada; no usarla como evidencia de coherencia variable. |
| fdica_no_rr.py | El score de polarización inspeccionado incluye autocorrelación. | Corregir/retirar ese score de la rama Python; no trasladar su salida a etiquetas. |
| identification/g12.py | Clasificador de dos salidas y entrada de cuatro canales, con capa final ligada a longitud 256. | Mantener la reproducción como referencia; cualquier cambio de longitud exige adaptar/verificar la arquitectura. |
| identification/g13.py | Asigna etiquetas por posición de fila: primeras 2240 frente a siguientes 2240; validación 500/500. | Crear manifest explícito; comprobar el significado real de cada ejemplo, no inferirlo solo de su posición. |
| identification/g16.py | Propaga la clase de ventanas solapadas y convierte cualquier voto positivo en marca contaminada. | Cuantificar dilatación temporal y falsos positivos; calibrar la agregación de probabilidades y las guardas. |
| denoising/g0.py | Forma pares entre mitades del MAT y usa MSE; entrada = segunda mitad, blanco = primera mitad. | Validar alineación y procedencia antes de usar esas mitades como verdad. |
| denoising/g15.py | Devuelve cuatro series de 256 muestras; es otro modelo respecto al clasificador. | Versionar pesos y objetivo por separado. |

Metadatos comprobados en los archivos disponibles: identificación 4480×4×256 y validación 1000×4×256; denoising 20000×4×256 y validación 2000×4×256, que el script interpreta como 10000 y 1000 pares. Leer esos tamaños no verifica su contenido semántico.

## 6. Tres conjuntos de datos con funciones distintas

### 6.1 Conjunto de identificación D_id

Contiene ventanas multicanal y etiqueta de actividad contaminante: 0, 1 o sin etiqueta confiable. “0” significa ausencia de la contaminación objetivo dentro del criterio documentado; no ausencia de todo ruido instrumental.

El clasificador necesita ejemplos de ambas clases, incluidos sferics útiles en la clase protegida. **No es necesario que cada registro real tenga tramos limpios y contaminados.** Un registro completamente contaminado puede procesarse después del entrenamiento, aunque la ausencia de referencia limpia local aumenta la dificultad de validarlo.

### 6.2 Conjunto de separación D_sep

Contiene pares alineados de la misma realización: entrada contaminada y blanco de referencia conocido o aproximado, indicando cuál de los dos es. Para un ejemplo sintético:

```text
s_ref: señal limpia de referencia en una subbanda aprobada
n_inj: contribución contaminante multicanal conocida
x = s_ref + n_inj
target_clean = s_ref
target_noise = n_inj
```

Si el objetivo es retirar contaminación cultural conservando el piso instrumental, s_ref puede incluir una realización instrumental declarada y compartida en el par. Si se busca retirar también ese piso, cambia el blanco y debe validarse como otro objetivo. No alternar ambos significados sin etiquetarlos.

### 6.3 Conjunto real de evaluación D_real

Contiene registros originales reservados y anotaciones disponibles. Puede medir detección, daño, repetibilidad y respuesta EM. Sin blanco limpio independiente no permite calcular error temporal verdadero ni afirmar SNR absoluto recuperado.

### 6.4 Qué se hace con cada origen

| Tipo | Entrada | Etiqueta de identificación | Blanco de separación | Uso |
|---|---|---|---|---|
| S0: sintético limpio | s | 0 | s | Clase limpia, identidad y controles físicos. |
| S1: sintético contaminado | s + n conocido | Actividad conocida, con detectabilidad declarada | s exacto para ese modelo | Entrenamiento supervisado principal. |
| S2: sintético + ruido extraído | s + N admitido | Actividad inyectada conocida | s exacto como construcción | Semisintético; la atribución de N como ruido real conserva incertidumbre. |
| F0: campo de bajo ruido aceptado | r = s_real + e_residual | 0 aproximado bajo criterios QC | r aproximado | Adaptación e identidad con confianza explícita. |
| F1: F0 con ruido añadido | r + n conocido | Actividad añadida y estado del fondo | r aproximado | Aprender a retirar el ruido añadido; no demuestra eliminación de e_residual. |
| F2: campo original contaminado | x_real | 1 solo donde haya evidencia/anotación; resto sin etiqueta | No disponible | Detección supervisada si está anotado, extracción de candidatos o evaluación. |
| U: campo ambiguo | x_real | Ignorar en pérdida supervisada | No disponible | Inspección/adaptación investigativa independiente. |
| N: solo ruido | n | Actividad de ruido, con ausencia de señal útil | Cero solo en este control diseñado | Comprobar abstención y evitar inventar Z; informar separado. |

“Datos de campo + sintéticos contaminados + limpios” significa **combinar familias de ejemplos trazables en el corpus**, no sumar arbitrariamente sus series ni asignarles el mismo blanco. Añadir x_real contaminado a s_sintético y etiquetar s_sintético como único limpio enseñaría a eliminar también la señal geofísica contenida en x_real. Ese experimento, si se usa, es una prueba artificial de interferencia, no un par limpio real.

TEM determina respuestas posibles de un modelo, pero no la realización temporal natural que ocurrió durante x_real. Por ello una serie TEM sintética no puede ser el blanco alineado del registro de campo original.

### 6.5 Criterio para referencias de campo de bajo ruido

Exigir calibración y QC válidos, ausencia de episodios contaminantes evidentes, amplitud útil por encima del piso y estabilidad compatible con ventanas vecinas/repeticiones. Utilizar referencias externas o inspección independiente cuando existan. No declarar “limpio” únicamente porque la BSS produjo un residual suave o porque la coherencia es alta.

Registrar e_residual como desconocido/acotado por evidencia, sin convertirlo en cero. Si un sitio no ofrece referencia de calidad, utilizar ejemplos sintéticos y, para adaptación, referencias de otros sitios de desarrollo con dominio compatible. Nunca incorporar inadvertidamente la campaña ciega.

## 7. Generación de registros con episodios limpios y contaminados

### 7.1 Generación continua

1. Generar una realización s(t) larga, continua y físicamente consistente en la subbanda aprobada.
2. Muestrear episodios del banco: inicio, duración, intensidad, recurrencia, solapamiento y fuente/grupo.
3. Construir n(t) con sus acoplamientos multicanal y actividad; añadirlo sin cortar ni reiniciar s en las fronteras.
4. Aplicar la cadena de observación en el orden físico correcto, incluidas las máscaras de pérdida de información.
5. Aplicar el mismo operador W_b y guardas a entrada y blanco, manteniendo sus tiempos.
6. Cortar ventanas al final y derivar las etiquetas a partir de la historia completa.

La adición x=s_ref+n es una representación válida en el dominio lineal común. Si se modelan ADC y saturación, mezclar antes de las no linealidades; marcar ejemplos no recuperables. No asumir que el mismo par aditivo sigue siendo exacto después de clipping.

### 7.2 Tipos de ocupación temporal

Incluir registros limpios completos, episodios aislados, ráfagas repetidas, cambios de actividad, ventanas mixtas y contaminación persistente. No imponer silencios artificiales en cada plantilla ni asumir que todos los ruidos son intermitentes.

Duraciones, pendientes de inicio/fin y amplitudes se extraen del catálogo; reservar variaciones no vistas para prueba. Las transiciones industriales pueden ser abruptas: no suavizarlas siempre. A la vez, evitar cortes de concatenación que permitan clasificar por un artefacto que no existe en campo.

### 7.3 Máscaras y detectabilidad

Guardar tres conceptos separados:

- **Actividad de fuente:** dónde se inyectó el episodio antes de filtros.
- **Contaminación efectiva por canal:** dónde la contribución filtrada supera el criterio definido, incluyendo colas y retardos.
- **Validez del dato/blanco:** clipping, huecos, guardas, amplitud nula o etiqueta incierta.

La detectabilidad se define antes de la prueba ciega por SNR de banda, duración y ciclos; calibrar con un detector oráculo y reportar la fracción detectable.

La presencia de ruido muy por debajo del piso no debe forzarse como una tarea perfectamente detectable. Mantener su actividad verdadera en el manifiesto y evaluar detectabilidad por amplitud/SNR. Puede excluirse de la pérdida binaria o reducirse su peso conforme a una regla congelada; no cambiar su verdad para obtener mejor accuracy.

Para ventanas parcialmente contaminadas, guardar fracción temporal y canales afectados. La reproducción de un clasificador por ventana utiliza un criterio de etiquetado explícito; localizar el inicio/fin requiere agregación temporal calibrada o una cabeza de segmentación nueva. El clasificador local no entrega por sí solo una máscara exacta por muestra.

### 7.4 Balance y particiones

Primero separar registros, modelos base y plantillas/eventos por grupos; después generar variantes, mezclas y ventanas. Todas las copias, escalados y recortes de un mismo episodio pertenecen a una sola partición.

Para reproducir el detector, empezar con balance 0/1. Parear la potencia de los negativos limpios con la de los positivos y evaluar un clasificador solo-potencia; de lo contrario Cθ puede aprender energía. Independientemente, comparar proporciones de ejemplos sintéticos frente a referencias reales aceptadas. No imponer 50% de campo si eso obliga a usar blancos de mala calidad.

Validación final con prevalencia realista, además de un conjunto equilibrado de diagnóstico. Con balance artificial, la salida softmax no es automáticamente una probabilidad calibrada para la prevalencia de campo. Separar también familias de ruido y sitios nuevos para comprobar generalización.

No duplicar una misma plantilla miles de veces y contar esos recortes como miles de fuentes independientes. Agrupar errores e intervalos por episodio, registro y sitio.

## 8. Entrenamiento y aplicación en dos etapas

### 8.1 Detector Cθ

Entrada: C canales sincronizados × L muestras de una subbanda autorizada. Salida inicial: probabilidad/clase contaminada por ventana. Entrenar con entropía cruzada sobre etiquetas confiables, pesos de calidad documentados e ignorar U.

Elegir L por duración física y ciclos, no por mantener 256. Fijar `Δf = fs_eff/L` y `f_min = N_c·fs_eff/L` por subbanda y registrar la banda resultante en `F_red_validada` (plan §3.6 y §7.2); la ventana reproduce el régimen, no lo garantiza. Al cambiar L adaptar las capas finales locales. Los negativos difíciles deben incluir sferics, cambios naturales de energía y señales útiles coherentes.

Evaluar precisión, sensibilidad, PR-AUC, falsos positivos por hora/tiempo limpio, error de inicio/fin y calibración. Añadir el baseline solo-potencia y métricas estratificadas por SNR; la calibración de probabilidades se hace con prevalencia realista. Fijar el umbral según el costo de eliminar señal, además de la pérdida promedio.

### 8.2 Separador Dψ

Entrenar con D_sep, inicialmente con la arquitectura local como referencia. Comparar salida limpia directa y predicción residual de ruido. Los términos de error temporal/espectral usan solo blancos con calidad conocida; las restricciones E=ZH usan únicamente modelos y frecuencias habilitados.

El conjunto F1 permite aprender a retirar la contaminación añadida sobre r. No se evalúa como recuperación exacta de s_real. No entrenar el separador con F2 como si tuviera blanco limpio.

Agregar ejemplos identidad como regularización explícita del proyecto y evaluar su peso mediante ablación. Mantener por separado resultados S1, S2, F1 y campo original.

### 8.3 Decisión temporal y reconstrucción

```text
registro D0/D1 → soporte habilitado → Cθ → limpio / contaminado / incierto
limpio: conservar
contaminado y dentro de dominio: Dψ → candidato y residual
incierto, saturado o fuera de dominio: abstención / referencia convencional
```

La abstención puede implementarse mediante dos umbrales y diagnóstico de dominio; no requiere inventar etiquetas limpias para la zona incierta. Para decidir la máscara final se agregan probabilidades solapadas con regla calibrada, evitando la unión indiscriminada de cualquier voto positivo.

Aplicar Dψ con contexto suficiente, conservar la localización del episodio y recomponer con pesos. **La máscara temporal y el filtro de subbanda no conmutan:** si se modifica temporalmente una señal filtrada, la corrección debe volver a proyectarse al soporte aprobado; contabilizar colas y guardas en la preservación de tramos limpios.

Evaluar la cadena detector→separador completa. Un separador bueno con máscara ideal puede fallar al usar la máscara predicha. Una detección positiva no certifica que la reconstrucción sea correcta.

### 8.4 Registros completamente contaminados

No requieren fabricar tramos limpios dentro del registro. Se procesan con el conocimiento externo aprendido y se evalúan como escenario de alta dificultad. Si la contaminación ocupa todo el registro y es indistinguible de la respuesta útil, la salida puede depender del prior aprendido: el sistema debe declararlo fuera de recuperación demostrada.

## 9. Contratos y proveniencia

| Objeto | Campos obligatorios |
|---|---|
| NoiseEpisode | episode_id, parent_record_id, site/campaign, fs, banda, inicio/fin, unidades, canales, N_r, soporte, escala, evidencia, estado y método/versiones. |
| NoiseShapeModel | template_id, episodios de origen, q/envolvente, acoplamientos/retardos, parámetros y error de reproducción. |
| IdentificationExample | input_id, canales, ventana, class_label 0/1/ignore, label_origin, label_confidence, actividad, ocupación, máscara válida y split_group. |
| SeparationExample | input_id, target_id alineado, target_kind exact_synthetic/approx_field, known_injected_noise, fondo residual, soporte P2-T cuando aplica, filtro y grupo. |
| FieldEvaluation | registro reservado, anotaciones independientes, referencias disponibles, blancos ausentes explícitos y método de evaluación permitido. |
| InferenceResult | detector/denoiser y versiones, probabilidades, máscara final, guardas, residual, salida, dominio y abstenciones. |

Construir relaciones de proveniencia entre originales, plantillas, modelos y variantes antes de mezclar. Si un par comparte un original o una plantilla con otra partición, se rechaza. Las palabras “ruido armónico” designan una clase, no un identificador suficiente para rastrear una realización.

Guardar también la versión de la política de etiquetas, no solo los pesos de red. “Cambio de etiqueta por nueva evidencia” requiere regenerar las particiones/resultados afectados.

## 10. Validaciones y reglas de aceptación

Los porcentajes siguientes son propuestas piloto; se fijan según el costo de daño y el presupuesto del plan antes de abrir la prueba final.

| Control | Evidencia requerida | Criterio |
|---|---|---|
| P4-N: admisión del ruido | Reconstrucción, estabilidad, evidencia adicional y fuga de señal | Cumplir P4 y conservar estado ambiguo donde no haya respaldo; no clasificación por coherencia sola. |
| P5-L: etiquetas | Auditoría de todos los pares y su procedencia | Cero blancos inventados para F2/U; cada etiqueta tiene origen/calidad; cero cruces de grupos. |
| P7-I: identificación | Conjunto ciego con limpios, episodios, mixtos y persistentes | Propuesta: FPR sobre tiempo limpio ≤1% y sensibilidad ≥90% en episodios declarados detectables; evaluar intervalos por registro y curvas de compromiso. |
| P7-S: separación | Error con blancos conocidos y preservación | Cumplir las metas de Z/fase/identidad del plan, desglosadas por tipo de blanco y subbanda. |
| P8: cadena completa | Detector real, separador, proyección espectral y guardas | No inferioridad limpia y mejora frente a referencia; sin modificación deliberada fuera de soporte. |
| P9: campo | Registros independientes y referencias externas disponibles | Informar evidencia real sin fabricar SNR/errores de una verdad desconocida. |

La evaluación debe incluir al menos una familia de ruido generada por un mecanismo distinto de la BSS; de lo contrario la comparación es circular. Reportar también B7/B8 del plan. La tasa de falsos positivos temporal se calcula sobre el tiempo realmente marcado tras solapamiento/guardas, no únicamente sobre ventanas aisladas. La sensibilidad propuesta no aplica a contaminación físicamente indetectable; informar qué fracción de eventos queda en esa categoría.

### Ablaciones mínimas

1. Referencia robusta sin red.
2. Detector con y sin información multicanal.
3. Separador con máscara verdadera sintética frente a máscara predicha.
4. Separador aplicado a todo el registro frente a intervención selectiva.
5. Solo S1 frente a S1+S2 y frente a incorporación de F1.
6. Inyección idéntica en canales frente a huellas multicanal realistas.
7. Banco admitido frente a incorporación controlada de plantillas ambiguas, solo como prueba de estrés.
8. Contaminación intermitente frente a persistente, y sitios/familias no vistos.

No elegir exclusivamente por accuracy del detector o MSE del separador. El producto final debe conservar la transferencia EM y reconocer insuficiencia de información.

## 11. Orden concreto de implementación

1. Congelar banda/soporte, particiones y definición de “limpio”.
2. Auditar las etiquetas MAT existentes y la ruta C++/Python que se ejecuta.
3. Exponer un extractor de NoiseEpisode que no dependa de producir Sx/Sy o Zopt.
4. Validar un banco pequeño con episodios y controles de señal útil.
5. Generar registros continuos con actividad conocida y obtener D_id/D_sep.
6. Incorporar campo anotado y referencias de bajo ruido con su nivel de confianza.
7. Reproducir Cθ y Dψ por separado; calibrar su conexión temporal.
8. Comparar cadena completa contra referencia y máscaras ideales en sintéticos.
9. Abrir la prueba de campo reservada y liberar solo el dominio demostrado.

**Regla teórica y operativa de cierre:** una estructura compartida permite proponer una fuente; evidencia adicional y estabilidad permiten admitirla como contaminación; una pareja alineada con blanco conocido permite supervisar la reconstrucción; la prueba independiente de transferencia permite declarar recuperación. Ninguno de esos pasos se deduce automáticamente del anterior.
