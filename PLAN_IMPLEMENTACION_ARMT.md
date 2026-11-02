# Ruta de implementación para la recuperación robusta de sondeos ARMT en MT/AMT

**Versión:** 1.3 · **Fecha:** 28 de octubre de 2026  
**Proyectos:** ARMT_validacion, TEM_MT_inversion, preprocesamiento/BSS, Denoise_MT y ARMT_processing.  
**Producto de esta entrega:** plan de integración, fundamentos, subetapas, entregables y criterios verificables. Las correcciones y los entrenamientos descritos son trabajo futuro.

**Alcance revisado:** trabajar con la señal MT/AMT de D0/D1 y limitar la síntesis guiada por TEM a las frecuencias cuya respuesta esté suficientemente restringida por los datos TEM. D2/D3 y el denoising de portadoras RMT quedan fuera de esta implementación. No se exige cubrir completas D0 o D1.

**Especificación de ruido y aprendizaje:** [DISENO_RUIDOS_DATASET_AMT.md](DISENO_RUIDOS_DATASET_AMT.md) desarrolla la extracción de formas/episodios, evidencia bibliográfica, tipos de etiquetas y conexión detector–separador. Sus reglas forman parte del plan.

**Registro de cambios v1.3:** se corrigen las evidencias H10/H11/H19, se añaden H21–H27, se cuantifica `F_red_validada` (`f_min`, `Δf`, ciclos), se define el presupuesto de error en 1σ, se añaden los comparadores B7–B10, la definición de detectabilidad y la escalera de parada G0–G4. No se elimina alcance ni se amplía D0/D1; los cambios son aditivos y quedan sujetos a las mismas puertas.

## 1. Decisión central y alcance

La ruta propuesta es viable como programa de investigación e implementación, con una condición fundamental: **la recuperación se debe juzgar por la conservación y exactitud de la respuesta electromagnética, junto con su incertidumbre e identificabilidad**. Reducir la energía, aumentar la coherencia o suavizar las curvas no demuestra recuperación.

El objetivo es obtener, dentro de las subbandas MT/AMT habilitadas de D0/D1, el tensor complejo Z(f), resistividad aparente, fase y, si Hz está disponible y es confiable, el tipper. En frecuencias con una sola polarización se entregará una respuesta direccional o escalar bajo supuestos explícitos. Donde falte información se entregará una bandera de no identificabilidad. Tener un modelo TEM con el que se pueda calcular Z a cualquier frecuencia no significa que los datos TEM restrinjan todas esas predicciones.

Se propone una ruta de desarrollo y otra de aplicación:

1. **Desarrollo:** gates TEM válidos → conjunto de modelos admisibles → evaluación de sensibilidad e incertidumbre de Z(f) → selección de subbandas D0/D1 → síntesis físicamente consistente y ruido multicanal → entrenamiento y evaluación ciega.
2. **Aplicación:** registro ARMT D0/D1 → calibración y control de calidad → máscara de frecuencias habilitadas → comparación entre procesamiento de referencia y limpieza candidata en esa máscara → estimación robusta → incertidumbre y decisión de aceptación.

La BSS caracteriza formas, tiempos y contribuciones de episodios contaminantes para construir el banco de ruido; no necesita entregar polarizaciones naturales ni Zopt. Conserva internamente la huella multicanal y su incertidumbre para poder inyectar ese ruido. Su aplicación directa antes de la red será una variante experimental; no se presupone que ambas limpiezas consecutivas mejoren el resultado.

El aprendizaje consta de **dos tareas y dos conjuntos**: identificación de ventanas limpias/contaminadas, y separación con pares contaminado–referencia alineados. Los registros originales de campo pueden aportar episodios y etiquetas de identificación verificadas; sin referencia limpia no son pares supervisados de reconstrucción.

**No hay garantía universal de recuperación.** La saturación, ausencia de excitación, mezcla indistinguible entre señal y ruido o falta de polarizaciones pueden destruir la información necesaria. El sistema debe reconocer esos casos y abstenerse de producir una impedancia aparentemente precisa.

### Flujo y puntos de control

```text
TEM → gates válidos → modelos admisibles → sensibilidad y dispersión de Z
                                                     │
ARMT → inventario D0/D1 → calibración/QC ──→ soporte común por sondeo
          D2/D3 fuera de la red                       │
                                     ¿hay subbanda habilitada?
                                      │ sí                  │ no
                              síntesis MT/AMT       sin síntesis TEM
                                      │             ni red en ese tramo
D0/D1 de desarrollo → BSS → ruido multicanal
                                      │
                             D_id: ventanas y clase / D_sep: pares
                                      │
                             detector Cθ y separador Dψ MT/AMT
                                      │
Real D0/D1 → soporte → Cθ → Dψ selectivo / conservar / abstenerse
                  │                   │
                  └─→ referencia ─────┤
                                      │
                             Z + incertidumbre dentro del soporte
                                      │
                             evaluación ciega → aceptación / abstención
```

TEM aporta información geológica previa; no determina la realización temporal de la fuente ARMT. Las estadísticas de excitación y la respuesta instrumental son entradas adicionales. El banco de modelos teóricos sirve para comprobaciones matemáticas y físicas independientes; no justifica completar bandas que el TEM de un sondeo no restringe.

## 2. Lo que se encontró en los proyectos

Se revisaron archivos representativos y se hicieron comprobaciones aisladas. No se ejecutaron los cinco pipelines completos, una inversión TEM de producción ni un entrenamiento. La presencia de código o de una prueba no equivale a validación física.

| Proyecto | Evidencia revisada | Aprovechamiento y trabajo necesario |
|---|---|---|
| ARMT_validacion | simulacion_armt5_multibanda.py; test_simulacion.py; aborde_correccion.txt | Hay recursión 1D, generación multicanal, contaminación y ADC. Adaptar la exportación a D0/D1 y a una máscara de soporte TEM por sondeo; la simulación RMT existente queda fuera de este desarrollo. |
| TEM_MT_inversion | mt_1d.py; tem_1d.py; pipeline.py; dosier_doi_20261014/README.md | Hay modelado e inversión. Usar conjuntos de modelos admisibles y explicitar las aproximaciones del sistema TEM. El dosier existente distingue modelos de escenario de una DOI certificada. |
| Preprocesamiento/BSS | fdica_no_rr.py; main_pipeline_integrado.py; cpp/src/estimator/ComplexFastICA.cpp; FDICANoRR.cpp; FDICAReconstructor.cpp | Hay ramas Python y C++ con diferencias. Elegir y versionar el motor efectivo. Verificar separación, reconstrucción física y exportación del ruido multicanal. |
| Denoise_MT | CBAM_AMT_Denoising/README.md; denoising/g0.py, g10.py, g15.py | Corresponde al trabajo de Zhang y colaboradores de 2024. El código local usa cuatro canales, 256 muestras, MSE y normalización específica. Necesita adaptación de dominio, trazabilidad y evaluación por impedancia. |
| ARMT_processing | armt/processor.py; instrument_calibration.py; comb_spectral.py; peak_picking.py; dispersion_smoothing.py; tests | Ya existe procesamiento más amplio que el descrito en el README: calibración, portadoras, estimador híbrido y fusión. Será la plataforma del estimador de referencia y la salida final, previa revisión de sus reglas físicas. |

### Hallazgos que condicionan el orden de implementación

| ID | Hallazgo y alcance | Acción exigida antes de usarlo como evidencia |
|---|---|---|
| H01 | El simulador fija 2.4 MHz para D2/D3. La tabla del manual local indica 400 kHz y 4 MHz, respectivamente. | Hallazgo de inventario fuera del alcance actual: no es necesario reparar la síntesis RMT para cerrar este plan. Para D0/D1 leer fs, banda y duración del SBF real y contrastarlos con el manual. |
| H02 | El tensor sintético se construye con dos respuestas 1D, una con resistividades multiplicadas por 1.05, y luego se rota. | Es útil para pruebas algebraicas; no certifica una solución Maxwell 2D ni una anisotropía material particular. Incorporar un directo 2D/3D independiente para esos escenarios. |
| H03 | En D1 se multiplican E y H por una envolvente después de aplicar Z(f). | La modulación temporal no conmuta en general con una transferencia dispersiva. Modular primero las fuentes y volver a calcular E y Hz. |
| H04 | Se prescribe Hz = 0.04 Hx − 0.03 Hy para un escenario construido a partir de capas 1D. | En el caso 1D isotrópico de onda plana usar T = 0. Si se prescribe T, etiquetarlo como prueba algebraica o calcularlo con un directo apropiado. |
| H05 | ch_limpio contiene ruido instrumental. | Exportar por separado campo ideal, campo con ruido instrumental, contaminación y adquisición digital; definir qué significa la etiqueta limpia. |
| H06 | La rama Python de main_pipeline_integrado.py deja la integración FDICA no-RR en un pass. Hay implementación C++ adicional. | Confirmar el ejecutable y recorrido usados realmente. No evaluar la BSS productiva a partir del archivo Python incompleto. |
| H07 | physical_polarization_score de fdica_no_rr.py compara una componente consigo misma entre sus referencias. La comprobación con cuatro componentes independientes devuelve cuatro valores ≈1. | Corregir o retirar ese criterio de la rama Python. El C++ revisado utiliza canales originales y no presenta esa misma expresión; requiere su propia validación. |
| H08 | En process_fdica_no_rr se retienen las primeras cuatro componentes tras dividir temporalmente los canales. | Demostrar correspondencia temporal, dimensiones y reconstrucción. El orden ICA no identifica canales físicos; dividir tiempos no crea sensores simultáneos independientes. |
| H09 | El procesamiento usa un umbral de tipper de 0.25; algunas rutas combinan la norma del tipper estimado con el cociente de amplitudes vertical/horizontal. | Separar ambas magnitudes y convertir el umbral en diagnóstico condicionado por geología, rango y SNR. Un tipper geológico alto no demuestra campo cercano. |
| H10 | band_bracket presenta las estimaciones directa e inversa como intervalo de identificabilidad. | Documentar sus supuestos. Con E=10u y H=2u, el código devuelve [0.5, 0.5] porque `rho_psd` es la razón de autopotencias del campo total; la ρa de la señal (0.02) no es identificable con una sola realización. El ancho es monótono en (1−γ²) y se anula en γ²=1: solo es cota bajo ruido independiente E/H con un canal limpio. Añadir Monte Carlo con K ventanas y R repeticiones; no usar `rho_fwd/rho_rev` como intervalo de regresión. |
| H11 | bode_check utiliza 45(1−s), con s = d log ρa / d log f. | Revisar signo y alcance. Para Z ∝ (iω)^0.75, s=0.5 y la fase correcta es 45(1+s)=67.5°; el código calcula 45(1−s)=22.5°. La forma equivalente en período es 45(1−s_T). Es una prueba de consistencia 1D, no una identidad para 2D/3D. Corregir el código y añadir la prueba; el plegado mod(φ,180) solo se admite dentro de este diagnóstico, nunca en la fase exportada. |
| H12 | dispersion_smoothing.py alinea signos a cuadrantes esperados y filtra por rangos de fase. | Resolver polaridad con geometría/calibración. No corregir una fase por el hecho de que no parezca 1D; las respuestas 3D pueden salir de esos rangos. |
| H13 | g0.py calcula normalizaciones diferentes para entrenamiento y validación, usando los pares completos; g10.py usa otra escala del registro. | Fijar un procedimiento reproducible disponible durante inferencia, sin consultar etiquetas de validación. Verificar el significado de ambas mitades de los archivos MAT. |
| H14 | g10.py construye matrices de tamaño L×L para recomponer ventanas. | Sustituir por acumuladores de suma/pesos y procesamiento por bloques antes de usar registros ARMT largos. |
| H15 | El estimador se describe como Siegel con breakdown de 50%, pero el núcleo inspeccionado agrega soluciones espectrales por pares. | No trasladar automáticamente el teorema de la mediana repetida al algoritmo híbrido. Evaluar sesgo, contaminación y puntos de alto leverage con experimentos específicos. |
| H16 | El plan anterior no exigía una máscara por frecuencia que demostrara qué predicciones Z(f) estaban restringidas por TEM. | Añadir la puerta P2-T antes de generar pares; una predicción extrapolada no es una etiqueta validada por TEM. |
| H17 | El plan anterior incluía adaptación neuronal a RMT como hito. | Retirar ese hito. La red se limita al ámbito MT/AMT de D0/D1 con validación específica de cada subbanda. |
| H18 | FDICAReconstructor.cpp asigna dos componentes naturales mediante referencia y dos restantes como ruido. | Desacoplar un extractor de episodios de esa asignación fija; no exigir Sx/Sy ni Zopt para formar el banco. |
| H19 | apply_strategy en ese archivo calcula una razón de coherencia por coeficiente que tiende algebraicamente a 1 fuera del piso numérico. | La razón abs(x·conj(y))²/(abs(x)²·abs(y)²) es idénticamente 1 si ambos son no nulos; solo cae a 0 en el piso numérico. El umbral `coh_thresh` es inerte y la supresión efectiva es un gate de amplitud por percentil. Comprobar la ruta efectiva y sustituirla por coherencia promediada con grados de libertad. |
| H20 | identification/g13.py fija etiquetas según posición de fila del MAT; g16.py propaga cualquier voto positivo de ventanas superpuestas. | Auditar etiquetas con manifiesto; validar agregación temporal y falsos positivos después del solapamiento. |
| H21 | FDICAReconstructor.cpp usa CA_Ry = abs(mean(Y·conj(Ry)))²/(Pyy²) y CA_Rx análogo. | El denominador omite abs(R)²; con S blanqueado, CA≈P_R·γ². La selección 2+2 depende de la potencia de la referencia, no solo de la coherencia. Normalizar a γ²=abs(mean)²/(Pyy·P_RR), verificar la normalización del llamador y no imponer dos naturales más dos ruidos. |
| H22 | La ventana de 256 muestras fija f_min y Δf, no solo la duración. | Con L=256, D0 tiene Δf=15.6 Hz y f_min=125 Hz (8 ciclos); D1 tiene Δf=125 Hz y f_min=1 kHz, y no resuelve armónicos de 50/60 Hz. Definir F_red_validada por subbanda con L, fs_eff, Δf, f_min y N_c; validar W_b y la supresión de peine. |
| H23 | La mezcla FDICA instantánea se supone constante en la banda de análisis. | Una ventana de 256 muestras a 4 kHz cubre 2 kHz; la respuesta del sensor y el acoplamiento pueden variar en esa banda. Usar subbandas fraccionales (p. ej. 1/3 de octava) y comprobar la estabilidad de A(f) entre subbandas. |
| H24 | D1 nominal 1–10 kHz solapa la banda muerta AMT de 1–5 kHz. | Incorporar la banda muerta como prior/penalización en F_observacion_AMT, no como máscara dura. Reportar el piso de ruido y la señal natural por sitio; no afirmar cobertura de D1 1–10 kHz sin demostrarla. |
| H25 | Las metas 0.05 dec y 3° se tratan como si fueran un único error de 5.9 %. | 0.05 dec en ρa = 12.2 % (5.9 % en abs(Z)); 3° = 2·sin(1.5°) = 5.2 % de error complejo. El par combinado es 7.9 % de abs(Z) ≈ 0.066 dec en ρa. Mantener las métricas separadas, reportar el error complejo como diagnóstico y expresar el presupuesto en 1σ, no en medianas. |
| H26 | La evaluación no incluye comparadores lineales ni un control de que Cθ aprenda potencia. | Añadir B7 (clasificador solo-potencia), B8 (Wiener multicanal con S_nn verdadera y estimada) y B9 (familia de ruido generada por un mecanismo distinto de la BSS). Si la red no supera B7/B8, no se justifica la no linealidad. |
| H27 | El análisis de P9 no fija el modelo estadístico ni congela toda la cadena de preprocesamiento. | Endpoint primario preregistrado; modelo jerárquico con sitio/registro como efectos aleatorios; intervalos cluster-robustos; corrección por comparaciones múltiples; sharpness de intervalos; hash de W_b, escalas, umbrales y F_aplicacion antes de abrir la prueba ciega. |

Los resultados numéricos H07, H10, H11, H19 y H21, y la comprobación analítica favorable del semiespacio 1D, están en **VERIFICACION_SUPUESTOS.json**. La recursión del simulador reproduce el semiespacio de 100 Ωm con error relativo máximo de 2.5×10⁻¹⁶ en esa comprobación, del orden de la precisión de máquina. Esto no valida las capas, el ADC ni el generador completo. H18 y H20 quedan como lectura de código con hash (`tipo_evidencia: lectura_de_codigo`), no como ejecución de los pipelines.

## 3. Marco físico y estadístico común

### 3.1 Qué se desea recuperar

Para una excitación compatible con el modelo de onda plana:

```text
E_h(f,k) = Z(f) H_h(f,k)
Hz(f,k)  = T(f) H_h(f,k)

E_h = [Ex, Ey]ᵀ ; H_h = [Hx, Hy]ᵀ
Z es 2×2 complejo ; T es 1×2 complejo
k identifica una realización o ventana.
```

Con campos en SI, Z_H = E/H en ohmios:

```text
ρa,ij = |Z_H,ij|² / (μ0 ω)
φij   = atan2(Im Z_H,ij, Re Z_H,ij)
ω     = 2πf
```

Muchos instrumentos y programas llaman H al canal que realmente representa B en nT. Para evitar un error de unidades:

```text
Z_B = E/B ; Z_H = μ0 Z_B       [campo magnético en aire, μ ≈ μ0]
ρa  = μ0 |Z_B|² / ω           [E en V/m y B en T]
ρa  = 0.2 |Z_num|² / f        [Z_num en (mV/km)/nT]
```

El factor 0.2 solo vale con esas unidades. Cada archivo debe indicar si representa B o H. La fase de Zyx puede diferir 180° de la de Zxy en un medio 1D por la orientación; no debe resolverse plegando fases automáticamente.

### 3.2 Modelo de observación

```text
u(t) = C * [s(t) + n_ext(t)] + n_elec(t)
x(t) = Q{clip[G u(t)]}
```

C incluye sensores, electrodos, cables y filtros lineales según el punto de referencia; G representa únicamente las ganancias no incluidas ya en C; Q representa el ADC. El ruido electrónico puede entrar en distintos puntos y debe ubicarse según el instrumento.

En el dominio calibrado, cuando la cadena es lineal:

```text
X(f,k) = S(f,k) + A_n(f,k) U_n(f,k) + N_inst(f,k)
```

La suma debe ocurrir antes de clipping y cuantización en una simulación instrumental completa. Sumar ruido a un registro ya saturado no representa correctamente la adquisición.

El ruido electromagnético de una fuente cercana puede depender de la misma geología que la señal útil. Reutilizar su huella multicanal medida es válido como prueba empírica, pero no implica que esa huella sea una simulación física de la misma fuente en otro subsuelo.

### 3.3 Límites de identificación

La coherencia entre E y H puede ser elevada para señal útil, ruido local o mezcla de ambos. La curtosis o negentropía tampoco identifica por sí sola ruido: las descargas atmosféricas útiles pueden ser impulsivas.

El objetivo de extraer una forma común no elimina este límite. En x_c = a_c(s+n), todos los canales pueden ser perfectamente coherentes y aun así no hay una descomposición única de s y n. Una fuente compartida puede observarse con ganancias, fases y retardos distintos, e incluso quedar bajo el piso en algunos canales. La huella multicanal se conserva; identificar sus polarizaciones naturales no es un requisito del catálogo de ruido. [Fundamento de ICA](https://www.cs.helsinki.fi/u/ahyvarin/papers/NN00new.pdf).

En cada bin de frecuencia, el campo natural es aproximadamente complejo gaussiano después de promediar; el ruido cultural suele ser no gaussiano (impulsivo, periódico o de línea estrecha). ICA separa como máximo una fuente gaussiana; dos o más gaussianas solo se identifican salvo rotación. Por eso no se exige Sx/Sy, pero tampoco se garantiza separar ruido gaussiano. Reportar negentropía/kurtosis por componente y no usarla como prueba de ruido.

El número de ruidos separables está acotado por el rango: `k_max(f) = C − r_s(f)`, con `r_s=2` para dos polarizaciones y `r_s=1` para una sola. Con cuatro canales y dos polarizaciones, `k_max=2`; con Hz, `k_max=3` solo si Hz aporta un quinto canal con ruido propio por encima de su piso. Si `k > k_max`, usar un episodio compuesto; no inventar identidades.

Una matriz magnética con rango efectivo uno no determina cuatro elementos independientes del tensor. El rango debe evaluarse **por frecuencia y conjunto de ventanas**, no por el número total de emisoras detectadas en toda la banda. Regularizar una matriz singular estabiliza números, pero no agrega información.

La regresión robusta controla ciertos valores atípicos; no elimina automáticamente el sesgo por ruido en H ni una relación E–H contaminante estable durante todo el registro. Los estimadores de influencia acotada y referencia remota ofrecen herramientas concretas bajo supuestos que deben comprobarse. [Chave y Thomson, 2004](https://doi.org/10.1111/j.1365-246X.2004.02203.x).

### 3.4 Las cuatro bandas del ARMT-5 y el alcance elegido

La tabla de bandas de la página impresa 7 del manual local especifica los muestreos y límites superiores; la tabla 9 da la división nominal de procesamiento. La banda de adquisición no equivale a su frecuencia de muestreo ni al intervalo útil certificado de cada registro.

| Banda | fs nominal | Intervalo nominal de procesamiento | Papel en este plan |
|---|---|---|---|
| D0 | 4 kHz | DC–1 kHz | Candidata para señal MT/AMT de banda ancha. DC queda excluida de Z; el límite inferior útil depende de sensor, duración, señal y soporte TEM. |
| D1 | 32 kHz | 1–10 kHz | Candidata AMT, únicamente en los subintervalos habilitados. |
| D2 | 400 kHz | 10–100 kHz | RMT; fuera del entrenamiento y la inferencia de esta red. |
| D3 | 4 MHz | 100–1000 kHz | RMT; fuera del entrenamiento y la inferencia de esta red. |

D0 incluye frecuencias usualmente denominadas MT además de AMT; no se afirma que toda D0 pertenezca estrictamente a AMT. El ámbito operativo es **la señal natural MT/AMT observada en D0/D1**, con adaptación comprobada a su muestreo. El identificador D0/D1 por sí solo no garantiza ese régimen: una adquisición de fuente controlada o una portadora aislada requiere clasificar su origen antes de admitirla.

La banda muerta AMT (aproximadamente 1–5 kHz) solapa la mitad inferior de D1. No es un cero físico: depende de latitud, estación, actividad solar y ruido local. Se incorpora como **prior/penalización** en `F_observacion_AMT`, no como máscara dura; la parte útil de D1 puede concentrarse en ~5–10 kHz y debe demostrarse con el piso de ruido del sitio.

### 3.5 Regímenes físicos y exclusiones

| Régimen | Excitación útil | Tratamiento |
|---|---|---|
| AMT con excitación natural suficiente | Banda ancha y variabilidad temporal de polarización | Estimación espectral por bandas estrechas y ventanas, con control del rango magnético. |
| RMT pasivo | Portadoras observadas | Fuera del alcance neuronal actual, incluidas portadoras aisladas que aparezcan dentro de un registro D0/D1. Conservar su procesamiento independiente. |
| Fuente controlada en campo lejano demostrado | Excitación compatible con aproximación elegida | No forma parte del conjunto AMT natural por defecto; exige otro protocolo de admisión. |
| Fuente finita en transición/campo cercano | Dependencia importante de posición, orientación y distancia | Puede aportar contaminación a las pruebas; su respuesta no se etiqueta como impedancia AMT útil. |
| Sin excitación o saturación severa | Información insuficiente | No recuperable bajo este flujo; conservar dato y motivo. |

Un tipper elevado puede responder a estructuras geológicas. Existen observaciones MT con magnitudes superiores a 0.25 asociadas a estructura; por ello ese umbral no puede ser un separador físico universal. [Informe de datos USGS](https://pubs.usgs.gov/of/2005/1037/508OF05-1037.html).

Dentro del intervalo MT/AMT seleccionado, comprobar la aproximación cuasiestática si la resistividad/permitividad lo requieren. La razón η = ωερ es un indicador preliminar; la decisión depende del efecto sobre Z frente al presupuesto de error. La referencia sobre corrientes de desplazamiento en RMT queda como antecedente físico, sin abrir una tarea de adaptación a D2/D3. [Kalscheuer y colaboradores, 2008](https://academic.oup.com/gji/article/175/2/486/618122).

### 3.6 Soporte TEM–MT/AMT: condición previa a la síntesis

**No existe una correspondencia universal “un gate TEM = una frecuencia AMT”.** No usar f = 1/t ni f = 1/(2πt) como corte de aceptación. Cada dato tiene sensibilidad distribuida, y los operadores TEM y MT son distintos. Tiempo, profundidad de difusión y skin depth pueden orientar una exploración preliminar, pero no certifican qué frecuencias se pueden predecir.

La ventana TEM válida debe excluir gates dominados por rampa no modelada, recuperación instrumental, ruido o tiempos inciertos. Con esos datos se determina un conjunto de modelos admisibles y se evalúa la variabilidad de su respuesta MT/AMT. La resolución EM depende también de la respuesta del sistema y del ruido; una profundidad calculada únicamente con el último tiempo no basta. [Christiansen y Auken, 2012](https://doi.org/10.1190/GEO2011-0393.1).

Para cada sondeo s y banda b:

```text
F_candidata(s,b) = B_b ∩ F_calibrada(s,b) ∩ F_TEM(s)
                  ∩ F_observacion_AMT(s,b)       ; b ∈ {D0,D1}

F_aplicacion(s,b) = F_candidata(s,b) ∩ F_red_validada
```

`F_red_validada` no es un flag global: se define por subbanda, sensor y familia de ruido. Para una ventana de `L` muestras y una frecuencia efectiva `fs_eff`:

```text
F_red_validada(s,b) = { f ∈ B_b : f_min ≤ f ≤ f_max,
                        Δf ≤ espaciado mínimo de líneas a resolver,
                        SNR_red(f) ≥ umbral,
                        N_indep(f) ≥ mínimo,
                        dominio de sensor/amplitud/ruido verificado }

f_min = N_c · fs_eff / L ;  Δf = fs_eff / L
```

La tabla de `L`, `fs_eff`, `Δf` y `f_min` por subbanda está en §7.2. `F_red_validada` se congela antes de la prueba ciega y no se amplía retrospectivamente.

F_TEM contiene frecuencias cuya **respuesta objetivo** está suficientemente restringida por TEM bajo el modelo físico admitido; no es todo el rango que admite el directo. F_observacion_AMT exige señal útil sustentada, duración y resolución adecuadas, sin decidirlo solo por potencia/coherencia altas. En casos sintéticos de control se conoce la excitación; en campo, soporte incierto permanece condicional.

La intersección puede ser parcial, discontinua o vacía. Por ejemplo, si una evaluación hipotética respaldara 300–1600 Hz y los otros criterios se cumplieran, se habilitarían aproximadamente 300–1000 Hz de D0 y 1000–1600 Hz de D1, con guardas; no toda D0/D1. **Este ejemplo no es un resultado de los datos TEM disponibles.**

En esta rama guiada por TEM, una frecuencia sin soporte no recibe etiqueta limpia TEM, no entra en las pérdidas supervisadas y no recibe denoising neuronal habilitado. Se conserva la adquisición y, si procede, la estimación convencional con su propia evaluación; la falta de soporte TEM no prueba que el ARMT observado sea inutilizable. Un conjunto vacío es un resultado válido, no un motivo para ampliar por extrapolación.

## 4. Etapa 0 — Fijar alcance, datos y criterios antes de optimizar

**Objetivo:** establecer qué se está midiendo, qué versión se comparará y cómo se decidirá el éxito.

**0.1. Inventario.** Registrar sondeos, campañas, fechas, ubicaciones, bandas, fs, duración, canales, sensores, ganancias, orientaciones, longitudes de dipolo, calibraciones, recortes ADC y disponibilidad de referencia remota. Conservar hash de archivos y versiones del software.

**0.2. Definición de productos.** Limitar la red a MT/AMT en D0/D1. Distinguir tensor completo, respuesta direccional, tipper y frecuencia no identificable dentro del soporte aprobado. Definir rango prioritario, escala geológica y exclusión D2/D3; no imponer cobertura de las cuatro bandas.

**0.3. Separación de datos.** Antes de cortar ventanas, asignar registros completos a desarrollo, validación y prueba final. Separar por campaña/sitio y, cuando sea posible, por familia de ruido, configuración instrumental y familia geológica.

**0.4. Contrato común.** Adoptar un contenedor versionado con muestras de forma (tiempo, canal), orden explícito, unidades, marcas temporales, máscaras, fs y proveniencia. Puede implementarse con HDF5/Zarr o NPY + JSON; la elección de formato no modifica el contrato físico.

**0.5. Presupuesto de error.** Distribuir tolerancias entre soporte predictivo TEM, calibración, sincronización, generación, separación, red, estimador e incertidumbre. Separar error aleatorio de sesgo sistemático. Predefinir escenarios recuperables y pruebas de abstención, incluidos sondeos sin intersección TEM–MT/AMT.

**Validaciones:** lectura/escritura sin cambiar valores; identificación inequívoca de unidades/canales; ausencia de intersección de grupos entre particiones; reproducción de una corrida fijando configuración y semilla.

**Puerta P0:** manifiesto completo para el piloto y protocolo de evaluación congelado. Los campos desconocidos quedan explícitos y limitan el alcance; no se rellenan con valores convenientes.

**Entregables:** manifest.json, schema.json, splits.csv y protocolo_validacion.md.

## 5. Etapa 1 — Cerrar la cadena instrumental

**Objetivo:** que amplitudes, fases y tiempos tengan significado físico antes de interpretar o entrenar.

**1.1. Auditoría SBF.** Usar ARMT_processing para confirmar signo, bits, intercalado, coeficientes y correspondencia de eventos. Comparar un subconjunto con una exportación independiente del software del fabricante, si está disponible.

**1.2. Calibración por canal.** Resolver sensor, tabla, banda y ganancia reales. Construir una tabla que indique dónde ya están aplicados ganancia, coeficiente ADC, respuesta eléctrica y longitud del dipolo. Evitar compensaciones duplicadas. Ausencia de calibración no puede convertirse silenciosamente en respuesta unitaria.

**1.3. Interpolación compleja.** Validar desenrollado de fase y continuidad antes de interpolar; excluir frecuencias fuera del soporte de calibración o tratarlas como escenario separado. Revisar el redondeo al directorio de ganancia más próximo que hace el código actual.

**1.4. Sincronización.** Medir retardos relativos entre canales y filtros de D0/D1. La fase introducida por un retardo es Δφ = 360 f Δt en grados; a 10 kHz, 1° equivale a 0.278 μs. El presupuesto se evalúa en el intervalo realmente habilitado y refleja la calibración efectiva.

**1.5. QC irreversible.** Detectar clipping, canales muertos, saltos, muestras faltantes y transitorios de conmutación. Aplicar máscaras conjuntas y guardas temporales. No borrar impulsos únicamente por amplitud, pues pueden ser sferics útiles.

**1.6. Dominio del aprendizaje.** Preferir campos calibrados y escalados de manera reversible para una primera versión. Si se trabaja en voltajes/cuentas, la red debe recibir configuración instrumental y estar entrenada en ese dominio. La inversión de C debe limitarse a la banda estable y evitar amplificar extremos.

**Validaciones:** seno multicanal de amplitud/fase conocida; prueba de polaridad y rotación; ida y vuelta campo → instrumento → calibración; calibración ausente/fuera de rango; retardo conocido; cambio de ganancia; continuidad en superposición entre bandas sin asumir simultaneidad.

**Puerta P1:** recuperación dentro de la tolerancia instrumental fijada en P0 y datos inválidos marcados. Propuesta inicial para banco numérico ideal: ≤1% en amplitud y ≤1° en fase; sustituir por especificaciones y mediciones reales antes de certificar campo.

**Entregables:** calibration_registry.json, presupuesto_instrumental.csv, registros calibrados y reporte de QC.

## 6. Etapa 2 — Determinar qué respuesta MT/AMT está respaldada por TEM

**Objetivo:** obtener un conjunto de modelos compatibles con los gates TEM válidos y determinar, antes de sintetizar, en qué frecuencias de D0/D1 sus predicciones son suficientemente estables y están sustentadas por los datos.

**2.1. Ventana TEM y directo.** Confirmar unidades observadas, geometría Tx/Rx, número de vueltas, momento, tiempos de gates, integración temporal, rampa, forma de onda y filtros. Construir una máscara por gate con error y motivo de exclusión. Los tiempos temprano/tardío nominales del instrumento no se consideran válidos automáticamente. Comparar semiespacio y capas con solución analítica aplicable o motor independiente.

**2.2. Inversión TEM independiente.** Para una evaluación externa, invertir primero TEM sin utilizar el ARMT que se quiere recuperar. Si se utiliza inversión conjunta TEM–MT, documentar la dependencia y reservar datos independientes para comprobarla.

**2.3. Conjunto admisible.** Variar parametrización, resistividades iniciales, regularización y supuestos instrumentales; usar muestreo probabilístico cuando sea viable. Admitir modelos mediante un criterio de ajuste a los gates válidos y su covarianza de error. Si solo se generan perturbaciones/multarranques, llamarlos conjunto de escenarios, no posterior probabilístico. Una nube estrecha producida por la misma regularización fuerte no demuestra que TEM haya resuelto la respuesta.

**2.4. Resolución y profundidad.** Evaluar sensibilidades, equivalencias y DOI con un método definido. Diversificar la estructura poco resuelta; no convertir extrapolaciones profundas en etiquetas exactas ni equiparar profundidad de penetración con resolución.

**2.5. Predicción exploratoria de Z/T.** Calcular las respuestas del conjunto en una malla candidata D0/D1 para determinar soporte; este cálculo exploratorio no autoriza generar etiquetas temporales en toda la malla. En 1D isotrópico: Zxx = Zyy = 0, Zxy = −Zyx y T = 0 con los ejes y convención acordados. Estas igualdades son supuestos 1D, no información tensorial/3D resuelta por TEM. Los modelos 2D/3D de control exigen un directo adecuado y proveniencia independiente.

**2.6. Desacoplar entrenamiento y evaluación.** Reservar familias de modelos y calcular parte del banco ciego con otro directo o una discretización más fina. Evitar que generador y evaluador compartan el mismo error numérico.

**2.7. Distorsión y escalas espaciales.** TEM y ARMT no tienen necesariamente el mismo volumen de sensibilidad. Evaluar la compatibilidad lateral antes de transferir modelos o corregir static shift. Una matriz galvánica real Cg puede dar E_observada = Cg E_regional: distinguir la transferencia local medida de la respuesta regional deseada. No etiquetar automáticamente esa distorsión como ruido temporal ni eliminarla durante denoising; estimarla en una etapa geofísica explícita si hay información suficiente.

**2.8. Sensibilidad compartida.** Calcular el Jacobiano TEM de los gates válidos, ponderado por errores, y las sensibilidades de la respuesta MT/AMT en la misma parametrización. Buscar perturbaciones poco detectables por TEM que cambien apreciablemente Z(f). Para una perturbación δm, el diagnóstico local compara:

```text
||C_d^(-1/2) J_TEM δm||       contra la tolerancia de ajuste TEM
||W_Z(f) J_Z(f) δm||         contra el presupuesto de error de Z(f)
```

C_d es la covarianza de error TEM; W_Z escala las partes real e imaginaria o la respuesta objetivo con tolerancias declaradas. Si una variación cabe dentro del error TEM pero excede el presupuesto en Z, esa frecuencia no queda respaldada. Usar SVD/perfiles de parámetros para explorar direcciones mal resueltas y comprobar las perturbaciones con los directos completos: la linealización no es una garantía global.

**2.9. Dispersión predictiva y dependencia de supuestos.** Por frecuencia, cuantificar la envolvente de Z, log10 ρa y fase circular entre modelos admisibles. Evaluar también errores de geometría, rampa, tiempos, filtros y estructura no resuelta. No exigir que cada capa esté identificada si la respuesta Z es estable; tampoco aceptar Z porque un solo modelo ajuste bien TEM. En conjuntos no probabilísticos usar envolventes/rangos sin llamarlos intervalos de confianza. Comprobar sensibilidad al ensanchar priors y cambiar regularización, especialmente en capas superficiales y profundas que TEM no restringe.

**2.10. Máscara y tolerancias.** Construir F_TEM(s) y su intersección de la sección 3.6, por sondeo y por observable. Fijar tolerancias predictivas antes de evaluar la red. Como punto de partida de diseño, considerar semiancho máximo de la envolvente de log10 ρa ≤0.025 décadas y de fase ≤1.5°, más un criterio de error complejo de Z: reserva parte de las metas finales de 0.05 décadas/3° para los otros errores. No son umbrales universales ni sustituyen un presupuesto de sesgos conservador.

**2.11. Decisión de soporte.** Clasificar cada frecuencia como respaldada, condicional, no respaldada o no evaluada. Solo respaldada habilita pares TEM. Si no hay intersección con D0/D1, registrar la ausencia de soporte y detener esa rama del sondeo. Guardar la razón: gates insuficientes, equivalencia de modelos, falta de calibración, señal AMT no sustentada, etc.

**Validaciones:** semiespacio y límites de capas; comparación de directos; sensibilidad instrumental; dos modelos que ajustan TEM pero divergen en AMT; priors estrechos frente a amplios; pérdida de gates tempranos/tardíos; soporte parcial/discontinuo/vacío. Ante pérdida de datos, cualquier ampliación del soporte se revisa explícitamente: no puede presentarse como ganancia informativa sin otra evidencia.

**Puerta P2:** cada modelo tiene alcance, régimen, ajuste y limitaciones documentadas. El directo pasa las pruebas analíticas y de convergencia; meta numérica inicial: diferencia de Z ≤1% y fase ≤0.5° frente al referente. Esa precisión numérica no demuestra soporte TEM.

**Subpuerta P2-T — obligatoria antes de síntesis TEM:** están documentadas las frecuencias respaldadas y excluidas, sus sensibilidades, envolventes predictivas, dependencia de supuestos y guardas. Solo las frecuencias aprobadas continúan. Un resultado sin soporte cierra el diagnóstico del sondeo sin habilitar entrenamiento o inferencia guiados por TEM.

**Entregables:** earth_models, model_provenance.json, tem_valid_gates.csv, tem_amt_support.csv, prediction_envelopes y matrices de sensibilidad. Cada fila de tem_amt_support.csv incluye sondeo, banda, frecuencia/intervalo, observable, estado, envolvente, supuestos, guardas, motivo y versión. Z_true/T_true de cada sintético son verdades condicionadas al modelo generado, no la verdad observada del sitio. El dosier TEM existente aporta escenarios, no una certificación adicional.

## 7. Etapa 3 — Generar series limpias con verdad física controlada

**Objetivo:** que la etiqueta limpia satisfaga el modelo elegido exclusivamente en subbandas autorizadas por P2-T, antes de añadir efectos de observación. Los casos analíticos de control se identifican aparte.

**3.1. Fuente AMT.** Generar dos grados de libertad de excitación con espectro, polarización y no estacionariedad controlados. Reproducir cambios de energía y banda muerta a partir de datos observados, incluyendo ráfagas útiles.

**3.2. Síntesis limitada al soporte.** Generar ejemplos por subbanda admitida de D0/D1; no completar espectros TEM fuera de soporte para obtener una serie de banda completa. Una realización limitada en frecuencia representa esa proyección de banda, no una afirmación de que el campo fuera de ella sea cero. Incluir también excitación polarizada de rango uno como prueba de abstención, sin convertirla en entrenamiento RMT.

**3.3. Aplicar la respuesta.** Construir H con la no estacionariedad deseada y después E = ZH y Hz = TH. Alternativamente combinar campos de dos polarizaciones calculados por un directo. Mantener simetría hermítica, condición real en DC/Nyquist y tratamiento de bordes.

**3.4. Control temporal.** Usar registros largos o convolución con guardas para evitar artefactos de periodicidad. Si se sintetiza por segmentos, garantizar continuidad compatible con el método y excluir bordes afectados del estimador.

**3.5. Instrumento y etiquetas.** Guardar al menos campo ideal, ruido externo, ruido instrumental, señal antes del ADC, cuentas observadas y máscaras. Mantener separados un blanco ideal de campo y una referencia realizable con ruido instrumental conocido.

**3.6. Densidad y duración.** Elegir duración suficiente para ventanas y ciclos en la frecuencia mínima; registrar grados de libertad efectivos. Zero padding no aporta resolución ni realizaciones independientes.

**3.7. Operador de subbanda común.** Definir W_b(f), el mismo filtro para todos los canales, y aplicarlo de forma consistente a entrada, blanco y ruido. En su zona útil, E_b = W_b E = Z W_b H = Z H_b. Dejar bandas de transición y guardas temporales dentro del dominio aprobado; descartar bordes si no hay soporte suficiente. Evaluar sesgo por filtrado y ventaneo. Una simple máscara en la pérdida no legitima blancos temporales de banda completa construidos por extrapolación.

La síntesis basada en modelado directo y combinaciones de polarizaciones tiene un precedente específico en Wang y colaboradores; aquí se exige además una validación instrumental y del dominio ARMT. [Wang et al., 2023](https://www.frontiersin.org/journals/earth-science/articles/10.3389/feart.2023.1086749/full).

**Validaciones:** E−ZH y Hz−TH en el espectro generado; reconstrucción FFT; PSD y espectros cruzados; recuperación de Z con dos polarizaciones y reconocimiento de rango uno; ausencia de discontinuidades; pruebas con ADC lineal y saturado.

**Puerta P3:** P2-T satisfecha para cada ejemplo TEM, sin blancos fuera de soporte; para el generador algebraico ideal, residuo relativo espectral <10⁻⁸ en bins válidos, con tolerancia absoluta para señales nulas. En recuperación por ventanas, error compatible con filtrado, suavizado y tamaño muestral. Los casos analíticos independientes conservan etiqueta de control y no amplían el alcance de un sondeo.

**Entregables:** clean_generator API, banco sintético versionado y pruebas de cierre.

## 8. Etapa 4 — Extraer y validar un banco de contaminantes

**Objetivo:** obtener un catálogo de formas y episodios contaminantes con inicio/fin, duración, recurrencia, amplitud y huella multicanal. No se exige reconstruir Sx/Sy como producto. El procedimiento detallado y su contraste con los autores están en la especificación de ruido y dataset.

**4.1. Selección de entradas.** Utilizar registros MT/AMT calibrados de D0/D1 del conjunto de desarrollo. La BSS puede caracterizar ruido en un intervalo instrumental más amplio, pero su incorporación a pares TEM debe respetar el soporte del ejemplo. Preservar saturaciones y huecos como máscaras; no incorporarlos como fuentes lineales normales.

**4.2. Dominio y rango.** Comparar STFT/multitaper y CWT en subbandas. Estimar rango efectivo y estabilidad del blanqueamiento antes de ICA. Especificar hipótesis de mezcla instantánea por frecuencia y cuánto puede variar entre ventanas.

Con `K` promedios independientes, el nivel crítico de coherencia al 95 % es `γ²_crit = 1 − 0.05^{1/(K−1)}` (K=8→0.35; K=16→0.18; K=64→0.05). Reportar `K_eff`, no el número nominal de ventanas solapadas; con seis pares de canales, corregir por comparaciones múltiples. La coherencia es una prueba de detección, no de identidad: sigue haciendo falta evidencia adicional (P4-N).

Si se usa esferización o normalización robusta, conservar la transformación y su escala. Normalizar cada observación a longitud unitaria elimina información de amplitud; puede servir para construir pesos o explorar direcciones, pero no reemplaza los campos físicos al estimar impedancias o reconstruir ruido. Una reducción de rango solo permite reconstruir el subespacio conservado: registrar también la parte descartada.

**4.3. Modelo de separación.** No imponer dos fuentes naturales más dos ruidos. Modelar n_cr = h_cr * (g_r q_r): forma q_r, actividad g_r y acoplamiento h_cr por canal. La cantidad separable está limitada por rango y supuestos del método. Puede conservarse un episodio compuesto cuando sus fuentes no se separan; no inventar identidades individuales.

El límite es `k_max(f) = C − r_s(f)`; con cuatro canales y dos polarizaciones, dos ruidos; con Hz, tres si su piso lo permite. La mezcla `A(f)` debe ser aproximadamente constante dentro de la subbanda: una ventana de 256 muestras a 4 kHz cubre 2 kHz y puede violar esa hipótesis. Usar subbandas fraccionales y comprobar la estabilidad de `A` entre ellas.

**4.4. Ambigüedades.** Resolver escala, signo/fase y permutación entre frecuencias antes de reconstruir series. Conservar A, W, blanqueamiento, medias, escalas, máscara de componentes y criterios de selección.

**4.5. Identificación con evidencia múltiple.** Priorizar morfología, duración, recurrencia, estabilidad/deriva de frecuencia, horarios y referencias externas disponibles. La polarización y el acoplamiento vertical son diagnósticos opcionales. La coherencia compartida propone candidatos; se requiere evidencia adicional para admitirlos como ruido. Usar tres clases: ruido admitido, señal protegida y componente ambigua.

Para cada componente extraída, calcular `ρ_comp(f) = |E_n/H_n|²/(μ0ω)` y compararla con la envolvente TEM y la relación pendiente–fase. Una componente incompatible es candidata a ruido de campo cercano; una compatible es solo **compatible** con onda plana, no prueba de origen natural: una fuente lejana de línea estrecha también pasa y produce un problema de rango uno. El test es asimétrico y no sustituye a P4-N. Si el soporte TEM se usa para admitir la componente, la evaluación posterior en ese sitio es transductiva y debe declararse.

**4.6. Reconstrucción física.** Exportar n_hat(f,k) = A_n(f,k) u_hat_n(f,k), con canales originales. Una componente ICA normalizada no es todavía ruido en Ex/Ey/Hx/Hy/Hz. Validar inversión CWT/STFT, solapamiento y extremos.

**4.7. Cuantificar fuga.** Inyectar señales MT/AMT conocidas a datos de desarrollo y medir cuánto de ellas termina en n_hat. Cambiar la señal útil manteniendo el ruido y comprobar estabilidad. Examinar especialmente sferics y cambios geológicos; una componente estrecha ambigua no se incorpora automáticamente al banco de ruido.

**4.8. Transferibilidad del banco.** Conservar versiones por sitio y sensor. La reutilización de una huella completa sirve para pruebas semisintéticas; una simulación de nueva geología exige remuestrear el modelo de acoplamiento o resolver la fuente finita.

**4.9. Catálogo de episodios.** Guardar la matriz observada de contribuciones por canal y, opcionalmente, un modelo paramétrico de forma/acoplamiento. Conservar tiempos, envolvente, recurrencia, retardos, fuentes de origen y calidad. No copiar sistemáticamente una única curva idéntica a todos los canales ni exigir que todos detecten el evento.

El método FDICA de Ogawa y colaboradores utiliza datos de referencia para identificar componentes. La variante sin referencia de este proyecto requiere demostración propia y no hereda automáticamente esa garantía experimental. [Ogawa et al., 2023](https://jopss.jaea.go.jp/search/servlet/search?5075669=&language=1).

**Validaciones:** mezcla conocida; mezcla no separable; eliminación de cero componentes; suma de señal reconstruida, ruido y residual; alineación entre frecuencias; estabilidad entre semillas; casos con ruido dominante, limpio, sferics y una fuente polarizada.

**Puerta P4:** reconstrucción identidad dentro de tolerancia y fuga por debajo del presupuesto definido. Propuesta inicial: <1% RMS de reconstrucción y <5% de energía útil extraída en inyecciones controladas; son metas de ingeniería, no garantías de pureza en campo. Las fuentes ambiguas permanecen etiquetadas.

**Subpuerta P4-N:** cada episodio admitido tiene evidencia adicional a la coherencia, huella multicanal, proveniencia y prueba de estabilidad/fuga. Un candidato sin esa evidencia permanece ambiguo; no se usa como verdad de ruido físico.

**Entregables:** noise_bank, noise_episodes.csv, mixing_models, fichas de formas/tiempos y reporte de fuga/estabilidad. El catálogo es consultable por episodio; no necesita categorías Sx/Sy.

## 9. Etapa 5 — Construir el conjunto de entrenamiento sin fuga de información

**Objetivo:** construir D_id para detección, D_sep para reconstrucción supervisada y D_real para evaluación, con funciones y niveles de verdad separados.

**5.1. Clases de evidencia.** Distinguir sintéticos limpios, sintéticos contaminados, campo de bajo ruido aceptado, campo original contaminado y datos ambiguos. Para D_id, usar etiquetas 0/1/ignore con origen y confianza. Para D_sep, exigir un blanco alineado exacto sintético o aproximado de campo, declarado como tal. Una salida BSS no se convierte automáticamente en verdad limpia.

| Familia | Grupo de papel | Entrada | Etiqueta de identificación | Blanco de separación | Uso |
|---|---|---|---|---|---|
| S0 | Sintético limpio | s | 0 | s exacto | Identidad y controles físicos. |
| S1 | Sintético contaminado | s+n conocido | Actividad inyectada; detectabilidad declarada | s exacto | Entrenamiento supervisado principal; P2-T en etiquetas TEM. |
| S2 | Sintético con ruido extraído | s+N admitido | Actividad de inyección conocida | s exacto de construcción | Semisintético; la pureza de N conserva incertidumbre. |
| F0 | Campo de bajo ruido aceptado | r | 0 aproximado con evidencia | r aproximado | Identidad y adaptación con confianza explícita. |
| F1 | Campo F0 con ruido añadido | r+n conocido | Actividad añadida y estado del fondo | r aproximado | Retirar el ruido añadido; no certifica el residual de r. |
| F2 | Campo original contaminado | x_real | 1 solo en episodios anotados; resto ignore | No disponible | Detección anotada, extracción o evaluación; no par exacto. |
| U | Campo ambiguo | x_real | Ignorar en pérdida supervisada | No disponible | Inspección o investigación separada. |
| N | Solo ruido diseñado | n | Actividad conocida y ausencia de señal | 0 diseñado | Control de no alucinación, peso bajo y reporte aparte. |

Las cinco filas de roles de la versión anterior quedan agrupadas en la columna “Grupo de papel”; la fuente autorizada de las ocho familias es `MATRIZ_ETIQUETAS_AMT.csv`. La combinación de estas familias es una mezcla de ejemplos en el corpus, no una suma indiscriminada de registros. x_real contiene señal geofísica además de ruido; sumarlo a s y etiquetar solo s como limpio enseñaría a eliminar parte de la señal útil. TEM tampoco proporciona la realización temporal exacta que ocurrió en x_real.

**5.2. Mezcla multicanal.** Mantener amplitudes relativas, fases, retardos y coherencia cruzada de cada fuente. Variar intensidad de fuente y acoplamiento de forma conjunta; no elegir un SNR independiente por canal que destruya la estructura original.

**5.3. SNR.** Definir SNR por canal y banda como 10 log10(P_señal/P_ruido) dentro de una máscara conocida. Para una métrica conjunta, usar campos adimensionalizados mediante escalas físicas declaradas: sumar directamente E² y H² carece de significado dimensional.

**5.4. Variabilidad.** Incluir ruido industrial de frecuencia variable, transitorios, ruido instrumental, interferencia coherente persistente, mezcla de fuentes y componentes ambiguas en MT/AMT. Las líneas estrechas no se convierten automáticamente en señal útil ni en ruido. Las portadoras RMT no son objetivos de recuperación neuronal. Las saturaciones se etiquetan como pérdida de información.

**5.4a. Episodios sobre señal continua.** Generar s(t) antes de insertar ruido; preservar su continuidad entre tramos limpios y contaminados. Variar inicio/fin, duración, recurrencia, intensidad y solapamiento del ruido. Incluir ejemplos completamente limpios, mixtos y persistentemente contaminados; no forzar segmentos limpios en todo registro de campo. Aplicar filtros/ADC en orden físico y registrar colas/transiciones.

**5.4b. Etiquetas temporales.** Separar actividad inyectada, contaminación efectiva por canal y validez del dato/blanco. Guardar ocupación de ventanas mixtas. Ruido bajo el piso conserva su actividad verdadera, pero no se exige que el detector lo reconozca perfectamente; su peso/exclusión supervisada sigue una regla congelada.

**5.4c. Pareo de potencia y control de atajo.** S0 y S1 no deben distinguirse solo por potencia total. Generar negativos limpios con la misma distribución de potencia de banda que los positivos (escalando la señal completa, lo que preserva Z, o estratificando por potencia en campo) y evaluar un clasificador solo-potencia como B7. Reportar métricas estratificadas por SNR. Si Cθ no supera a B7, aprendió energía, no contaminación.

**5.5. Escenarios difíciles y controles.** Incluir datos limpios, solo ruido, ausencia de señal, campo cercano que imita una respuesta MT, Hz con bajo SNR, polarización única, sensores desalineados y calibración perturbada.

La familia N se mantiene como control de peso bajo y se reporta aparte; con blanco cero puede enseñar “patrón coherente fuerte → salida nula”. Añadir la prueba inversa: señal útil pequeña sobre ruido fuerte (p. ej. SNR −20 dB) y medir sobresupresión y sesgo de Z. Si Dψ la anula, no se admite como separador.

**5.6. Separación por grupos.** Crear particiones antes del ventaneo. Ningún registro padre, fuente de ruido, variante de un mismo modelo base o intervalo solapado puede cruzar entre entrenamiento y prueba. Mantener grupos disjuntos de modelos, ruidos y fuentes; generar las mezclas dentro de cada partición.

Reservar al menos una familia de ruido de evaluación generada por un mecanismo distinto de la BSS (paramétrica ARMA, otro sitio u otro motor). Si el ruido de prueba procede del mismo motor que el de entrenamiento, la evaluación favorece a la red por artefactos compartidos.

**5.7. Normalización.** Ajustar escalas en entrenamiento o calcularlas de la entrada mediante una regla fija reproducible. Guardarlas y revertirlas por canal. No usar la etiqueta limpia para decidir la escala de validación/inferencia. Verificar que la transformación no altere de manera irreversible las razones E/H.

**5.7a. Balance.** Separar balance limpio/contaminado de proporción sintético/campo. Reproducir primero el detector con clases equilibradas y evaluar después con prevalencia realista. No cumplir una cuota de campo mediante referencias de baja calidad. Calibrar probabilidades/umbrales antes de trasladar el clasificador equilibrado a campo.

**5.8. Banco final bloqueado.** Reservar al menos una campaña y familias de ruido/geología no utilizadas en selección. Si se extrae ruido del mismo sondeo de prueba para adaptar la red, declarar evaluación transductiva y mantener otra evaluación externa intacta. Congelar antes de P9 el hash de `W_b`, escalas, umbrales, regla de agregación y `F_aplicacion`; cualquier cambio invalida la prueba ciega.

**5.9. Soporte por ejemplo.** Adjuntar banda, máscara TEM, observable, envolvente predictiva y filtro W_b. El entrenamiento de una subbanda solo usa ejemplos respaldados allí; no tomar la unión de máscaras como si todos los modelos sostuvieran todas las frecuencias. No reutilizar un mismo modelo TEM a través de distintas subbandas en particiones diferentes. Perturbar dentro del conjunto admisible para representar incertidumbre de etiquetas, en lugar de fijar una única respuesta como verdad del sitio.

**Validaciones:** búsqueda por identificador/hash y similitud de fragmentos; consistencia de escalas; suma de componentes; estadísticos PSD, matriz espectral cruzada, polarización y duración comparados con campo; doble conteo de ruido instrumental.

**Puerta P5:** cero intersección de grupos; generador reproducible; ninguna etiqueta TEM fuera de P2-T; cobertura por subbanda documentada; normalización disponible sin etiquetas. Una división 70/15/15 puede ser un inicio, pero el número de sitios y familias independientes importa más que la cantidad de ventanas.

**Subpuerta P5-L:** cada etiqueta tiene origen/calidad y cada par de separación tiene blanco alineado y tipo exact_synthetic/approx_field. Cero blancos inventados para campo contaminado o ambiguo; las variantes de una misma plantilla no cruzan particiones.

**Entregables:** D_id, D_sep, D_real, dataset_manifest, split_report, políticas de etiquetado y matriz de usos permitidos MATRIZ_ETIQUETAS_AMT.csv.

## 10. Etapa 6 — Estimador de referencia e incertidumbre

**Esta etapa comienza temprano, en paralelo lógico con las etapas 2–3 una vez disponible P1.** Se necesita un estimador confiable para juzgar la síntesis y la red; dejarlo para el final impediría detectar sesgos. Puede estimar respuestas convencionales fuera del soporte TEM si los datos ARMT lo permiten, pero esas respuestas no se presentan como recuperadas por la rama neuronal validada.

**6.1. Espectros.** Definir detrend, ventanas, FFT/multitaper, solapamiento, calibración, ancho de banda y máscaras comunes. Tratar la dependencia entre ventanas y tapers; no contabilizarlos como realizaciones independientes.

**6.2. Regresión compleja.** Implementar una referencia transparente:

```text
Z_hat(f) = [Σk wk E_k H_kᴴ] [Σk wk H_k H_kᴴ]⁻¹
```

ᴴ significa transpuesta conjugada. Usar solucionadores QR/SVD adecuados, no inversión explícita sin diagnóstico. Una regresión robusta iterativa puede expresarse con pesos adaptativos, pero sus propiedades dependen de cómo se calculan.

**6.3. Ruido en predictores.** Comparar LS, estimador robusto documentado y el híbrido existente. Para ruido en H, considerar referencia remota válida o modelos de errores en variables con covarianza identificable. TLS sin estructura de covarianza adecuada tampoco es una corrección universal.

El “bracket” de `band_bracket` solo es cota bajo ruido independiente E/H con un canal limpio; con ruido coherente se colapsa sobre la razón contaminada. No usarlo como indicador de identificabilidad. Sustituirlo por una covarianza completa (delta method o bootstrap por bloques) y reportar cobertura Monte Carlo.

**6.4. Referencia remota opcional.** Con R sincronizada:

```text
Z_RR = [Σk wk E_k R_kᴴ] [Σk wk H_k R_kᴴ]⁻¹
```

Comprobar relevancia/rango de la referencia, coherencia de señal y ausencia de contaminación compartida. No descartarla o aceptarla solo por la frecuencia o distancia geográfica. Una referencia fabricada con la misma salida del denoiser no es validación externa.

**6.5. Identificabilidad.** Exportar autovalores, número de condición, sensibilidad al ruido y diversidad de polarización de S_HH. El ruido instrumental puede inflar un segundo autovalor: rango numérico dos no basta. Definir umbrales mediante simulación y piso instrumental.

**6.6. Incertidumbre.** Guardar covarianza de las partes real e imaginaria de Z, dependencias relevantes entre componentes y, cuando importe, entre frecuencias. Evaluar bootstrap/jackknife por bloques temporales de longitud relacionada con la dependencia observada, sin remuestrear ventanas superpuestas como independientes.

El presupuesto se expresa en 1σ; las metas de P9 son medianas y no se suman en cuadratura. Para una gaussiana, mediana ≈ 0.674σ. Propuesta de asignación (1σ): TEM 0.025 dec/1.5°, calibración 0.010/0.5°, estimador 0.020/1.2°, BSS 0.015/1.0°, red 0.020/1.2°; cuadratura 0.042 dec/2.53°, compatible con una mediana de 0.05 dec/3°.

| Componente | ρa (dec, 1σ) | Fase (°, 1σ) |
|---|---:|---:|
| TEM predictivo | 0.025 | 1.5 |
| Calibración/instrumento | 0.010 | 0.5 |
| Estimador | 0.020 | 1.2 |
| BSS/banco | 0.015 | 1.0 |
| Red | 0.020 | 1.2 |
| **Cuadratura** | **0.042** | **2.53** |

**6.7. Propagación completa.** Separar incertidumbre condicional del estimador, incertidumbre por selección/BSS/red y sistemáticas de calibración. Repetir pasos adaptativos en el remuestreo donde sea viable; usar perturbaciones de calibración y varios entrenamientos para evaluar sensibilidad. Una red congelada puede añadir sesgo que el bootstrap final no detecta.

**6.8. Producto primario.** Conservar Z compleja sin suavizado y fases con su convención. Cualquier regularización, curva suave o inversión será un producto derivado, con datos originales preservados.

La literatura muestra que la estabilidad de las funciones de transferencia y la confiabilidad de sus varianzas requieren evaluación explícita; no basta con una dispersión pequeña entre ventanas. [Estabilidad y varianzas de funciones MT](https://academic.oup.com/gji/article/144/1/65/767364).

**Validaciones:** semiespacio y capas limpios; ruido solo en E, solo en H y coherente E/H; outliers y alto leverage; ventanas dependientes; RR limpia y contaminada; fuente única; convergencia con duración; cobertura Monte Carlo.

**Puerta P6:** referencia recupera la verdad en escenarios identificables y rechaza los no identificables; intervalos calibrados con realizaciones independientes. El híbrido existente puede conservarse como candidato, sin asumir que sus comentarios prueban robustez estadística.

**Entregables:** reference_estimator, estimator_benchmark y formato response_with_covariance.

## 11. Etapa 7 — Reproducir y adaptar el enfoque CBAM

**Objetivo:** entrenar y validar por separado un detector Cθ y un separador Dψ, y demostrar que su conexión preserva la transferencia EM.

**7.1. Reproducción acotada.** Confirmar arquitectura, significado de entradas/blancos MAT y normalización del código local. Registrar resultados reproducibles sobre el ejemplo disponible antes de modificar arquitectura.

La distinción entre los dos conjuntos y modelos se basa en [Zhang et al., 2024](https://doi.org/10.1109/TGRS.2024.3361942); la especificación complementaria documenta la metodología consultada. La adaptación temporal a D0/D1 requiere validación propia y no incluye RMT.

**7.2. Escala temporal y resolución espectral.** La ventana de `L` muestras no solo fija la duración: fija `Δf = fs/L` y `f_min = N_c·fs/L`. La tabla siguiente es la referencia de `F_red_validada`; `N_c` es un parámetro de diseño (8 como mínimo, 16 como margen).

| Caso | fs_eff | L | T | Δf | f_min (8) | f_min (16) | Ciclos de 50 Hz |
|---|---:|---:|---:|---:|---:|---:|---:|
| D0 | 4 kHz | 256 | 64 ms | 15.6 Hz | 125 Hz | 250 Hz | 3.2 |
| D1 | 32 kHz | 256 | 8 ms | 125 Hz | 1 kHz | 2 kHz | 0.4 |
| D0 dec ×2 | 2 kHz | 256 | 128 ms | 7.8 Hz | 62.5 Hz | 125 Hz | 6.4 |
| D0 dec ×4 | 1 kHz | 256 | 256 ms | 3.9 Hz | 31.25 Hz | 62.5 Hz | 12.8 |
| D1, L=4096 | 32 kHz | 4096 | 128 ms | 7.8 Hz | 62.5 Hz | 125 Hz | 6.4 |
| D1, L=8192 | 32 kHz | 8192 | 256 ms | 3.9 Hz | 31.25 Hz | 62.5 Hz | 12.8 |

Con L=256, D0 no cubre por debajo de 125–250 Hz sin decimar; D1 cubre la señal de 1–10 kHz, pero no resuelve armónicos de 50/60 Hz (Δf=125 Hz) y los ve como un peine. Validar que `W_b` atenúa esas líneas (≥60 dB) antes de la ventana y que Dψ suprime el peine sin distorsionar Z. No usar una sola L para D0 y D1: elegir L por subbanda y ciclos, con arquitectura multi-resolución o banco de filtros. Si se decima, filtrar contra aliasing, compensar el retardo de grupo y verificar con un retardo conocido. No se necesita volver a la fs original para estimar Z si se preservan soporte, tiempo y calibración.

**7.3. Arquitectura inicial.** Conservar inicialmente los cuatro canales Ex/Ey/Hx/Hy para comparar con el código disponible; Hz se usa como diagnóstico independiente. El tipper calculado combinando Hz sin limpiar con H horizontal limpiado necesita validación propia. Una variante de cinco canales exige entrenamiento, calibración y evaluación nuevos.

**7.4. Detector y separador.** Cθ aprende de D_id con entropía cruzada sobre etiquetas confiables; devuelve probabilidad/clase por ventana. Dψ aprende de D_sep a recuperar la referencia alineada. Comparar la salida directa local con n_hat = Dψ(x), s_hat = x−n_hat. Cθ no proporciona una serie limpia; Dψ no crea un blanco verdadero donde no existe.

**7.5. Pérdidas del separador.** Introducirlas gradualmente y evaluar aparte la clasificación:

```text
L = λt L_tiempo + λf L_espectro_complejo
  + λc L_espectros_cruzados + λz L_transferencia + λid L_identidad

L_transferencia ∝ ||E_hat − Z_true H_hat||²
```

Todas las partes deben normalizarse por escalas conocidas y usar la intersección de la máscara TEM aprobada, la subbanda W_b y la identificabilidad de cada ejemplo. L_transferencia se usa donde existe verdad sintética confiable; la incertidumbre del conjunto TEM acompaña las etiquetas. Por sí sola admite E_hat = H_hat = 0: necesita términos de fidelidad y preservación de potencia. Pérdidas de fase requieren máscaras cuando la amplitud es cercana a cero. No usar la coherencia de un solo coeficiente como objetivo, porque es trivialmente unitaria.

En pares de campo r+n→r se aprende a retirar n, y r puede contener contaminación residual. No reportar ese objetivo aproximado como recuperación exacta de la señal natural. Las etiquetas ignore no contribuyen a la clasificación supervisada y los registros sin blanco no contribuyen a pérdidas de reconstrucción supervisada.

**7.6. Protección de señal.** Incluir identidad sobre entradas limpias MT/AMT, conservación de ráfagas naturales, rotaciones consistentes y cambios de ganancia con reescalado exacto. Medir la respuesta al inyectar señal pequeña conocida sobre distintos fondos. Verificar además que el enrutamiento excluya D2/D3 y no modifique frecuencias fuera de la máscara de intervención.

**7.7. Entrenamiento.** Fijar semillas, versiones, criterio de parada y selección de checkpoint por métricas de validación física. Evaluar al menos tres semillas iniciales si el costo lo permite; ampliar solo cuando la variabilidad observada lo requiera.

**7.8. Abstención.** Establecer dominio válido en subbanda D0/D1, fs, sensores, amplitud y ruido. La ausencia de soporte TEM o de aprobación de la red deshabilita esta rama, incluso si el clasificador parece confiado. Calibrar detección fuera de distribución con datos reservados; desacuerdo entre redes o confianza de un clasificador son indicadores, no pruebas de corrección.

**7.9. Conexión temporal.** Calibrar la agregación de ventanas y la máscara de intervención. No convertir cualquier voto aislado en modificación de todos los tiempos cubiertos por la ventana. Comparar máscara sintética verdadera frente a predicha, y separación global frente a selectiva. No se requiere un tramo limpio en cada adquisición para inferencia; contaminación persistente se evalúa por separado.

La detectabilidad se define antes de la prueba ciega: un episodio es detectable si, tras `W_b` y la cadena de observación, su SNR de banda supera el umbral y su duración cubre `N_c` ciclos. Calibrar el umbral con un detector oráculo (ruido y máscara verdaderos) que alcance ≥90 % de sensibilidad con ≤1 % de FPR; si el oráculo no puede, el episodio no es detectable. Reportar la fracción detectable y la sensibilidad incondicional.

**Validaciones:** identidad, solo ruido, fuerte coherencia contaminante, ruido nuevo, modelo geológico nuevo, fase, ganancia, bordes de subbanda/ventana, saturación, señal débil y rango uno. Añadir exclusión D2/D3, soporte TEM parcial y soporte vacío. Examinar siempre x−s_hat para detectar señal útil eliminada.

**Puerta P7:** mejora en error de Z/ρa/fase frente a la mejor referencia admisible, no solo en MSE/SNR; no inferioridad en datos limpios y cumplimiento de abstención. Si falla, conservar la referencia y mantener la red experimental.

**Subpuerta P7-I:** detector calibrado y evaluado tras solapamiento; propuesta piloto FPR temporal ≤1% sobre tramos limpios y sensibilidad ≥90% en episodios declarados detectables, con intervalos por registro. Ajustar por costo de daño antes de la prueba ciega.

**Subpuerta P7-S:** separador evaluado con blancos exactos/aproximados por separado, y cadena completa Cθ→Dψ sin daño excesivo a señal útil. La máscara ideal no sustituye la evaluación con detector real.

**Entregables:** pesos y fichas separadas de Cθ/Dψ, normalizadores, política temporal, dominio de uso y ablaciones.

## 12. Etapa 8 — Integrar la inferencia MT/AMT con soporte parcial

**8.1. Adaptador común.** Encapsular lectura, calibración, bandas, máscaras y escalado. Resolver F_aplicacion(s,b) antes de invocar la red. Conservar correspondencia exacta entre muestras de entrada, salida y residual. Usar bloques con contexto y acumulación de pesos para recomposición.

`F_aplicacion` incluye `F_red_validada` por subbanda; no es una máscara global. Reportar `K_eff` y `γ²_crit` cuando se use coherencia para admitir componentes.

**8.2. Procesamiento D0/D1.** Aplicar el mismo operador de subbanda validado durante entrenamiento. Cθ decide conservar, intervenir mediante Dψ o abstenerse, con contexto y guardas. Proteger sferics y estimar solo en la zona útil. Validar si la energía natural permite recuperación; no transformar silencios en señal. No es obligatorio habilitar ambas bandas ni completar sus intervalos nominales.

**8.3. Exclusión RMT.** D2/D3 y los tramos identificados como portadoras RMT no se envían a CBAM, no se remuestrean para aparentar AMT y no requieren un nuevo denoiser para cerrar este proyecto. Si se conservan productos de procesamiento RMT ya existentes, su proveniencia y validación son independientes.

**8.4. Una frecuencia, una evaluación de rango.** Evaluar polarizaciones y ruido dentro de cada frecuencia/subbanda estrecha habilitada. No combinar indiscriminadamente ventanas de frecuencias diferentes para completar rango. La respuesta direccional se exporta como tal cuando no puede determinarse el tensor.

**8.5. Reconstrucción y unión.** La salida científica preferida es la serie de subbanda y su respuesta. Si se entrega además un registro completo, insertar únicamente la corrección filtrada al soporte autorizado y conservar el resto de la señal; verificar fuga en frecuencia y transitorios con tolerancia numérica/de filtrado preregistrada. “Cero intervención fuera de soporte” prohíbe procesar deliberadamente esos tramos, y la fuga residual debe quedar dentro de ese presupuesto. Unir resultados D0/D1 solo donde exista soporte y compatibilidad. Si comparten datos, incorporar covarianza o elegir una estimación; no imponer independencia ni crear un solapamiento inexistente.

La máscara temporal de episodios y W_b no conmutan. Proyectar nuevamente la corrección en frecuencia después de la selección temporal y contabilizar sus colas/guardas al medir preservación de segmentos limpios.

**8.6. Decisión.** Evaluar candidato, referencia y soporte disponible con reglas congeladas en validación. No elegir automáticamente la curva más suave, el menor error estimado o la que más se aproxime al modelo TEM.

**8.7. Frecuencias ausentes o no respaldadas.** Conservar huecos de excitación y exclusiones TEM con motivos distintos. Interpolar para visualizar no equivale a recuperar una observación. Si toda la intersección está vacía, omitir la inferencia del sondeo y registrar el resultado sin forzar D0, D1 ni otra banda.

**Validaciones:** igualdad entre procesamiento completo y por bloques; solapamiento sin costuras; memoria; invariancia ante cambio de lote; máscaras y calibración reproducibles; soporte parcial/vacío; ausencia de cambios fuera de soporte y de puntos nuevos en bandas sin señal; exclusión D2/D3.

**Puerta P8:** inferencia estable y trazable únicamente en F_aplicacion de D0/D1; resultados direccionales, frecuencias sin soporte TEM y no identificables correctamente codificados; cero intervenciones de la red en D2/D3.

**Entregables:** pipeline_armt, configuración por banda, salidas comparables y reporte por sondeo.

## 13. Etapa 9 — Evaluación ciega de extremo a extremo

**Objetivo:** decidir si el sistema recupera información útil y bajo qué condiciones.

### 9.1 Comparaciones obligatorias

| Variante | Qué mide |
|---|---|
| B0: datos calibrados + estimación robusta | Referencia básica del flujo completo. |
| B1: QC/selección espectral + estimación robusta | Beneficio alcanzable sin aprendizaje. |
| B2: BSS directa + estimación robusta | Aporte y posible fuga de la separación. |
| B3: CBAM reproducido + estimación robusta | Referencia del enfoque publicado/local. |
| B4: CBAM adaptado + estimación robusta | Aporte del nuevo conjunto, contexto y pérdidas. |
| B5: BSS seguida de CBAM | Comprueba si la doble intervención ayuda o daña. |
| B6: referencia remota robusta, si existe | Comparador independiente bajo sus supuestos. |
| Oráculo sintético: serie limpia + estimador | Separa error del estimador del error de limpieza. |
| Máscara ideal frente a predicha | Cuantifica el error del detector dentro de la cadena de recuperación. |
| Intervención global frente a selectiva | Mide beneficio y daño de proteger tramos limpios. |
| B7: clasificador solo-potencia | Control de atajo: ¿Cθ aprende contaminación o energía? |
| B8: Wiener multicanal con S_nn verdadera y estimada | Cota lineal y coste de estimar la covarianza; si Dψ no lo supera, no se justifica la no linealidad. |
| B9: familia de ruido independiente (ARMA/otro sitio/otro motor) | Rompe la circularidad de evaluar con el mismo motor BSS que entrenó. |
| B10: oráculo de ruido (n verdadero) + máscara ideal | Separa error del detector, del separador y del estimador. |

Todas las comparaciones deben mostrar resultados sobre soporte común y, por separado, cobertura adicional dentro de la máscara habilitada. Reportar como denominadores tanto el intervalo originalmente solicitado como las frecuencias respaldadas por TEM, las observables y las finalmente aceptadas. El evaluador no puede estrechar retrospectivamente la máscara para ocultar fallos. Las pruebas de no regresión controlan cambios, pero no certifican que la referencia sea físicamente correcta.

### 9.2 Escalera de evidencia

**9.2.1. Sintético físico:** verdad exacta y simulador de control independiente. Medir errores, sesgo, cobertura y tasa de falsas recuperaciones.

**9.2.2. Semisintético:** señal conocida y ruido de campo reservado. La mezcla es controlada, pero la pureza del ruido extraído tiene incertidumbre; reportar esa limitación y sensibilidad a fuga.

**9.2.3. Campo:** usar campañas/sitios reservados, repeticiones independientes, períodos relativamente limpios y referencia externa cuando exista. En ausencia de verdad limpia no reportar “SNR verdadero recuperado” ni error absoluto de Z.

**9.2.4. Consistencia geológica:** contrastar TEM, pozos, geología y repetibilidad dentro de sus resoluciones. Un ajuste a TEM que ya alimentó el entrenamiento no constituye validación independiente.

**9.2.5. Estabilidad de interpretación:** comparar inversión de respuestas originales y candidatas con el mismo método y presupuesto de errores. Evaluar si la limpieza inventa o elimina estructuras en sintéticos, además de revisar las curvas.

**9.2.6. Validez del soporte TEM:** diseñar casos con banda común parcial y vacía; retirar gates tempranos/tardíos; comprobar equivalencias de modelos y sensibilidad al prior. En sintéticos con verdad conocida, verificar que la puerta P2-T no apruebe predicciones erróneas con falsa precisión. Mantener un conjunto ciego para esta puerta además del destinado a la red.

### 9.3 Métricas y puertas cuantitativas iniciales

Las siguientes cifras son **propuestas para el piloto**, no normas publicadas ni resultados logrados. Se ajustan al presupuesto instrumental y a la aplicación antes de abrir el conjunto final.

| Aspecto | Métrica | Meta inicial y condición |
|---|---|---|
| Datos limpios | Cambio de amplitud de Z y fase | En casos identificables, percentil 95 ≤2% y ≤1°. Evaluar cada banda, no solo promedio global. |
| Recuperación con ruido | Error de log10 ρa y diferencia circular de fase | En el subconjunto recuperable predefinido: mediana ≤0.05 décadas y ≤3°; P90 ≤0.15 décadas y ≤8°. |
| Tensor completo | Norma de error complejo y error por elemento | Normalizar por escala del tensor/piso cuando un elemento sea cercano a cero; no dividir por Zxx=0. |
| Beneficio de red | Diferencia de error frente al mejor comparador | Reducción objetivo ≥20% de la mediana, con intervalo por bloques/sitios que sustente mejora y sin deterioro material de colas. |
| Incertidumbre | Cobertura empírica de intervalos nominales de 95% | Meta orientativa 90–98%; evaluar con intervalo binomial, sesgo y anchura por escenario. No pasa por usar intervalos arbitrariamente amplios. |
| Falsa recuperación | Fracción de casos no identificables reportados como válidos | Objetivo ≤5%, incluyendo ausencia de señal, rango uno y clipping severo. Informar también límite superior de confianza. |
| Cobertura útil | Frecuencias aceptadas respecto a solicitadas, respaldadas por TEM y observables | No inferior a referencia en soporte común; no penalizar la falta física de solapamiento ni ocultarla del informe. |
| Respeto del alcance | Etiquetas e intervenciones fuera de soporte | Cero etiquetas TEM fuera de P2-T y cero intervenciones neuronales en D2/D3 o fuera de F_aplicacion. |
| Identificación temporal | FPR, sensibilidad, PR-AUC, calibración y error de inicio/fin | P7-I; medir tras agregación y guardas, por registro y calidad de etiqueta. |
| Validez de supervisión | Proveniencia y alineación del blanco | P5-L; cero pares exactos inventados para registros de campo sin referencia. |
| Señal extraída como ruido | Energía útil perdida y sesgo de transferencia | Evaluación de inyección y controles limpios; no aceptar mejora de SNR a costa de sesgo de Z. |
| Repetibilidad | Variación entre corridas, sitios y semillas | Dentro de incertidumbre esperada; explicar dependencias sistemáticas. |

Una diferencia de 0.05 décadas en resistividad equivale aproximadamente a 12% como factor multiplicativo, y 0.15 décadas a 41%; estas metas deben revisarse si la interpretación requiere más precisión.

El error complejo derivado es `||ΔZ||/|Z| = sqrt((Δ|Z|/|Z|)² + (Δφ)²)`; el par 0.05 dec/3° corresponde a ~7.9 %, no a 5.9 %. Reportarlo como diagnóstico, no como puerta. Añadir sharpness de intervalos (ancho mediano / ancho oráculo) y un modelo jerárquico con sitio/registro como efectos aleatorios; corregir por comparaciones múltiples y no contar ventanas solapadas como sitios.

Para cobertura de intervalos, unas 200 realizaciones independientes por escenario principal dan un error estándar cercano a 1.5 puntos porcentuales alrededor de 95%. Es una escala inicial de diseño; no contar miles de ventanas de un mismo sitio como miles de campañas. Elegir finalmente el tamaño mediante precisión estadística requerida.

### 9.4 Escenarios mínimos

| Grupo | Casos |
|---|---|
| Tierra | Semiespacio; capas conductoras/resistivas; modelo no visto; 2D/3D; perturbaciones de distorsión galvánica. |
| Fuentes | Dos polarizaciones; una polarización; ráfagas AMT; excitación ausente; entrada RMT como prueba de exclusión. |
| Ruido | Independiente en E; independiente en H; coherente E/H; más fuentes que rango; deriva de red; transitorios; fuente cercana. |
| Instrumento | Variación de ganancia; error de fase; desalineación; huecos; clipping; calibración incompleta; Hz ruidoso. |
| Dominio | Subbandas D0/D1; soporte TEM parcial/discontinuo/vacío; D2/D3 como rechazo de alcance; nueva campaña. |
| Controles | Identidad; solo ruido; inyección conocida; reconstrucción sin supresión; directo independiente. |

**Puerta P9:** resultados congelados y reproducibles, validez de P2-T evaluada y rendimiento de la red por subbanda D0/D1 especificado. Sin exigir cobertura RMT. Si no se supera la referencia, mantenerla y registrar por qué la red no se habilita.

**Entregables:** informe ciego, tabla por escenario/sitio/frecuencia, intervalos y lista de restricciones.

## 14. Etapa 10 — Liberación controlada y trazabilidad

**10.1. Salidas por sondeo.** Entregar muestras calibradas, candidato de subbanda limpio, residual extraído, gates TEM válidos, máscara/envolventes TEM, filtro y guardas, Z original/candidata, covarianzas, ρa/fase, tipper cuando proceda, número de ventanas y razones de exclusión. Identificar qué parte nominal de D0/D1 quedó sin respaldo y conservar D2/D3 fuera de la red.

**10.2. Proveniencia.** Fijar versiones de lector, calibración, BSS, banco, modelo de red, estimador, configuración y hashes. El procesamiento original debe poder reproducirse.

**10.3. Exportación.** Usar EDI donde corresponda, y JSON/HDF5 complementario para covarianzas completas, respuestas direccionales, banderas y metadatos que EDI no represente adecuadamente.

**10.4. Operación.** Detectar nuevas configuraciones/sensores y desviaciones del dominio. Un cambio de pesos, calibración o selección de frecuencias requiere repetir las puertas afectadas.

**10.5. Política de salida.** Cada punto recibe una categoría: aceptado, condicional, direccional, sin soporte TEM, fuera del dominio MT/AMT o no identificable, con razón trazable. No confundir falta de soporte TEM con falta de señal ARMT. Una categoría condicional no se convierte en medición de calidad por suavizado posterior.

**Puerta P10:** ejecución reproducible por otra persona, reporte completo y mecanismo para volver a la referencia.

## 15. Organización de la implementación

Mantener los proyectos existentes como motores y crear una capa de coordinación en esta carpeta. Evitar copiar algoritmos entre proyectos sin versión. El siguiente árbol es una propuesta, no código ya implementado:

```text
armt_recovery/
  contracts/        unidades, metadatos, máscaras y esquemas
  adapters/         interfaces con los cinco proyectos
  calibration/      cadenas instrumentales y soporte
  earth_models/     conjuntos TEM y modelos de control
  support/          gates TEM, soporte por frecuencia y guardas
  synthesis/        fuentes, campos e instrumento
  noise_bank/       contribuciones y mezclas trazables
  datasets/         generación y particiones por grupos
  denoisers/        referencia CBAM y variantes
  estimation/       respuestas, rango e incertidumbre
  validation/       escenarios y comparación ciega
  reporting/        reportes y exportaciones
configs/            configuraciones versionadas
artifacts/          productos separados por identificador de corrida
```

### Contratos de intercambio

| Objeto | Contenido mínimo |
|---|---|
| Acquisition | muestras, fs, tiempos, canales, unidad por canal, sensores, ganancias, orientación, máscaras y hash. |
| EarthModel | geometría, propiedades EM, escenario, gates TEM válidos, ajuste, supuestos y parámetros del directo. |
| FrequencySupport | sondeo, banda D0/D1, observable, máscara TEM, envolvente de predicción, sensibilidad, dominio instrumental, filtro/guardas, motivo y versión. |
| CleanExample | campos de subbanda, Z/T condicionados al modelo, fuentes, cadena instrumental y FrequencySupport aprobado. |
| NoiseExample | contribución por canal, fuente/grupo, método BSS, mezcla, escalas, incertidumbre de etiqueta y proveniencia. |
| NoiseEpisode | forma, inicio/fin, duración, recurrencia, envolvente, amplitud, huella/acoplamientos, evidencia de ruido y registro padre. |
| IdentificationExample | ventana, label 0/1/ignore, origen/confianza, actividad, ocupación, máscaras y grupo. |
| TrainingPair | entrada/blanco alineado de subbanda, tipo exact_synthetic/approx_field, ruido añadido conocido, fondo residual, soporte y grupo. |
| DenoiseResult | salida, residual, F_aplicacion, filtro, probabilidades de Cθ, máscara de intervención, versiones de Cθ/Dψ y abstención. |
| ResponseResult | frecuencia, tipo tensor/direccional, Z/T, covarianza, rango, soporte temporal, QC y métodos. |

Los adaptadores deben comprobar forma, unidades y banderas al entrar y salir. Cuando falte información obligatoria, producir un estado explícito; no completar con una calibración unitaria o una curva interpolada.

## 16. Orden de ejecución, hitos y responsabilidades

| Hito | Trabajo | Dependencia y evidencia de cierre |
|---|---|---|
| M1 — Base física | Inventario D0/D1 y gates TEM; etapas 0–1; abrir etapa 6; revisar H09–H12 | P0/P1 y ejemplo de estimación calibrada trazable. |
| M2 — Soporte y banco de verdad | Etapa 2, incluida P2-T; después síntesis de etapa 3 y validación inicial de etapa 6 | Intervalo común demostrado o diagnóstico de ausencia de soporte; P3 solo donde esté habilitado. |
| M3 — Episodios y etiquetas | Extraer formas/tiempos con huella multicanal; auditar MAT; construir D_id/D_sep/D_real | P4-N/P5-L, pruebas P4/P5 y conjunto ciego reservado. |
| M4 — Piloto MT/AMT | Entrenar detector y separador en una subbanda respaldada; comparar cadena completa | P6/P7-I/P7-S/P8 limitadas al intervalo elegido. |
| M5 — Cobertura D0/D1 sustentada | Incorporar otros subintervalos únicamente si P2-T y la validación de red lo permiten | No es obligatorio cubrir ambas bandas; comprobar soporte parcial/vacío y exclusión D2/D3. |
| M6 — Campo y liberación | Etapas 9–10 | P9/P10, modelo habilitado solo en dominios aprobados. |

La ruta crítica es calibración y gates válidos → soporte TEM–MT/AMT demostrado → síntesis de subbanda/estimador → banco de ruido validado → datos separados → red → prueba ciega. La red no debe bloquear la referencia. El hito de extensión a RMT de la versión 1.0 se retira del alcance actual.

### Escalera de parada

| Puerta | Condición | Decisión |
|---|---|---|
| G0, tras P2-T piloto | Intersección vacía o sin subbanda admisible en 1–2 sitios | Cerrar la rama guiada por TEM; entregar B0/B1 y resultado negativo; no extrapolar |
| G1, tras P6 | B0/B1 no recupera casos sintéticos identificables | Corregir el estimador antes de entrenar |
| G2, tras M4 | B4 no supera a B1/B8 por el margen preregistrado | Mantener la referencia; red experimental |
| G3, antes de P9 | Menos de 3 sitios independientes por escenario clave o subconjunto detectable <30 % | No abrir la prueba ciega; reportar no concluyente |
| G4, tras P9 | Falla no inferioridad en limpio o falsa recuperación >5 % | No liberar |

Los umbrales son propuestas y se congelan antes de ver resultados. La ausencia de soporte TEM en G0 es un resultado válido, no un motivo para ampliar la máscara.

Se recomienda planificar cada hito en iteraciones de dos semanas con entregable verificable; el número de iteraciones se estima después de M1, cuando se conocen volumen, duración, GPU, estado C++ y disponibilidad de calibraciones/referencias. Asignar desde el inicio responsables funcionales de física EM, instrumento/datos, BSS, aprendizaje y evaluación; una persona puede cubrir más de una función, pero la prueba final debe mantener sus datos bloqueados.

### Primera iteración concreta

1. Seleccionar un sitio con TEM y registros D0/D1, metadatos y calibraciones; inventariar otro grupo reservado. No exigir que ambas bandas tengan soporte.
2. Fijar convenciones E/H/B, fase, orientación y unidades; comparar una exportación independiente si existe.
3. Crear el adaptador y registrar gates TEM válidos. Explorar modelos equivalentes y determinar una primera máscara TEM–MT/AMT; si está vacía, no generar pares de ese sitio.
4. Desactivar para la referencia experimental los rechazos universales basados en tipper/cuadrante y corregir la prueba pendiente–fase; conservar una corrida original reproducible para comparación.
5. Exportar un semiespacio de control y, solo si P2-T lo permite, ejemplos del conjunto TEM en una subbanda habilitada; pasar identidad, filtrado y recuperación de Z.
6. Ejecutar B0 y B1 sobre esos casos; documentar sesgo y no identificabilidad.
7. Revisar la BSS productiva y demostrar reconstrucción sin supresión antes de catalogar episodios. Exponer la extracción sin obligar a producir Sx/Sy o Zopt.
8. Auditar etiquetas MAT y generar ejemplos continuos limpios/mixtos/contaminados con clases y blancos distintos para D_id/D_sep. Reservar campo sin blanco para usos permitidos.

**Resultado esperado de esa iteración:** una decisión explícita sobre el soporte TEM–MT/AMT y una cadena pequeña que preserve unidades y respuesta donde corresponda. La ausencia de soporte también es un resultado válido. El entrenamiento masivo empieza después de demostrar una intersección utilizable.

## 17. Riesgos y respuestas previstas

| Riesgo | Cómo se detecta | Respuesta |
|---|---|---|
| La BSS extrae señal útil | Inyección conocida, controles limpios y cambios de fuente | Componentes ambiguas protegidas; mejorar evidencia o descartar plantilla. |
| El ruido queda codificado como geología | Error de Z y comparación con modelos reservados | Diversificar modelos/mezclas; revisar pérdidas y sesgos del banco. |
| La red aprende una resistividad preferida | Barrido de modelos nuevos y sesgo por ρ | Ampliar dominio, quitar restricciones circulares y reducir intervención. |
| Calibración equivocada parece ruido | Prueba instrumental y diferencia sistemática por sensor | Corregir cadena antes de entrenar. |
| Entrada RMT enviada a la red AMT | Identificador de banda y clasificación de régimen | Exclusión D2/D3 y portadoras; preservar procesamiento independiente. |
| Error pequeño con tensor no identificable | Rango, piso de ruido y prueba de fuente única | Respuesta direccional/abstención; no ocultar con regularización. |
| Incertidumbre artificialmente pequeña | Cobertura Monte Carlo y repetición de campo | Propagar selección, dependencia, calibración y sesgo. |
| Buen resultado solo en sitio de entrenamiento | Prueba por campaña/ruido/geología nuevos | Limitar dominio y reentrenar con separación correcta. |
| Mejora visual sin recuperación | Error complejo, señal eliminada e inversión sintética | Mantener referencia y rechazar variante. |
| Etiquetas extrapoladas desde TEM | Envolvente de Z, sensibilidad y perturbación de modelos equivalentes | P2-T obligatoria; no generar pares en frecuencias no respaldadas. |
| Falsa certeza por regularización TEM | Variar priors, parametrización y gates; comprobar datos frente a supuestos | Marcar soporte condicional/no respaldado y ampliar análisis. |
| Fuga desde bordes de la subbanda | Pruebas de W_b, ventanas y corrección fuera de máscara | Guardas, descarte de transiciones y filtro común por canal. |
| Contexto/memoria insuficientes en D0/D1 | Tiempo físico cubierto, memoria y duración real | Bloques y decimación validada por subbanda. |
| Campo contaminado usado como ruido puro | Auditoría de pares y registro padre | Extraer/admitir contribuciones; no etiquetar señal real de fondo como contaminación. |
| Blanco de campo falsamente exacto | Falta de referencia independiente/alineación | Declarar approx_field o ausencia de blanco; excluir pérdidas exactas improcedentes. |
| Detector elimina sferics útiles | Negativos difíciles y FPR temporal | Calibrar umbrales y evaluar cadena completa con protección/abstención. |
| Clasificación aprende las costuras sintéticas | Comparación de transiciones reales/sintéticas | Generar fuente limpia continua e insertar episodios sin reiniciar la señal. |

## 18. Fuentes y alcance de las recomendaciones

Las puertas, métricas, arquitectura de integración y porcentajes propuestos son decisiones de diseño de este plan. Las referencias sustentan piezas del fundamento; ninguna certifica el pipeline combinado ni las implementaciones locales.

1. [Wang, Chen y Zhang (2023), síntesis MT basada en modelado directo](https://doi.org/10.3389/feart.2023.1086749): antecedente de generación de campos con respuesta conocida.
2. [Zhang y colaboradores (2024), identificación y supresión multicomponente mediante CBAM](https://doi.org/10.1109/TGRS.2024.3361942): método identificado en Denoise_MT. [Registro institucional y acceso al trabajo](https://repository.tudelft.nl/record/uuid%3Afc625a4f-c5bc-4ba2-8a25-1663f031444a).
3. [Ogawa y colaboradores (2023), FDICA y continuidad de respuestas](https://doi.org/10.1016/j.jappgeo.2023.105012): antecedente con referencia; no equivale a una validación de la extensión local sin referencia.
4. [Chave y Thomson (2004), estimación de influencia acotada](https://doi.org/10.1111/j.1365-246X.2004.02203.x): tratamiento de outliers, leverage y referencia.
5. [Kalscheuer y colaboradores (2008), RMT con corrientes de desplazamiento](https://academic.oup.com/gji/article/175/2/486/618122): alcance de la aproximación cuasiestática.
6. [Weckmann y colaboradores (2005), selección espectral de datos de una estación](https://academic.oup.com/gji/article/161/3/635/557193): contexto para QC espectral y sesgos.
7. [Estabilidad de funciones de transferencia y confiabilidad de varianzas](https://academic.oup.com/gji/article/144/1/65/767364): referencia para evaluar incertidumbre.
8. [USGS, datos MT de Española Basin](https://pubs.usgs.gov/of/2005/1037/508OF05-1037.html): ejemplo de tipper asociado a estructura geológica.
9. [Comeau, tesis doctoral, ecuación 4.33](https://sites.ualberta.ca/~unsworth/theses/Comeau_Matthew_J_201509_PhD.pdf): relación aproximada pendiente–fase expresada en período. Al cambiar a frecuencia cambia el signo de la derivada. Una aproximación local no reemplaza una prueba integral de causalidad.
10. [empymod, documentación oficial](https://empymod.emsig.xyz/): motor independiente candidato para pruebas EM donde la geometría y el régimen sean compatibles.
11. **Manual local ARMT-5:** D:/ARRT_software/ARMT_processing/ARMT-5_user_manual_1.0_ENG_as_2.pdf, tabla de bandas en página impresa 7 y tabla 9 de procesamiento. Contrastar siempre con metadatos del equipo concreto.
12. [Christiansen y Auken (2012), A global measure for depth of investigation](https://doi.org/10.1190/GEO2011-0393.1): fundamento para considerar sensibilidad, respuesta instrumental y ruido al evaluar soporte; no establece una conversión universal de tiempo TEM a frecuencia AMT.
13. [Análisis de sensibilidad de respuestas MT (2023)](https://academic.oup.com/gji/article/233/3/1746/6993073): las distintas respuestas MT tienen sensibilidades diferentes. La prueba cruzada J_TEM/J_Z y sus umbrales aquí propuestos constituyen un diseño específico de validación.
14. [Hyvärinen y Oja (2000), Independent Component Analysis: Algorithms and Applications](https://www.cs.helsinki.fi/u/ahyvarin/papers/NN00new.pdf): supuestos y ambigüedades de separación; fuente primaria para delimitar las garantías de ICA.

### Rutas de los proyectos revisados

```text
D:/ARRT_software/ARMT_validacion
D:/ARRT_software/TEM_MT_inversion
D:/ARRT_software/Preproces_Time_series_M_boundedInfluence_preprocess_teoria_sperical_datawindos_FFT_cwt_escalas_densas_optimized
D:/ARRT_software/Denoise_MT
D:/ARRT_software/ARMT_processing
```

### Cómo usar esta entrega

El archivo MATRIZ_VALIDACION_ARMT.csv convierte las 11 puertas P0–P10 y las subpuertas P2-T/P4-N/P5-L/P7-I/P7-S en 16 controles. MATRIZ_ETIQUETAS_AMT.csv especifica los usos de las ocho familias de ejemplos del documento complementario. VERIFICACION_SUPUESTOS.json conserva las comprobaciones preliminares iniciales; no certifica soporte TEM, etiquetas ni entrenamiento. herramientas/verificar_supuestos.py permite repetir esas comprobaciones aisladas.

DISENO_RUIDOS_DATASET_AMT.md es la especificación operativa y la **fuente canónica**; los `.docx` se generan con `herramientas/preparar_entrega.py` y no se editan a mano. Los Word v1_3 incluyen este plan y esa especificación en archivos separados; los v1_2 se conservan como histórico. Las comprobaciones H19/H21 y la tabla de `Δf`/`f_min` están en `VERIFICACION_SUPUESTOS.json`; H18/H20 son lectura de código con hash y se identifican como tales.

La implementación se considerará concluida cuando P10 cierre para subintervalos explícitos de D0/D1 y P9 haya demostrado el resultado, incluida la validez de P2-T. No requiere cobertura de D2/D3. Ampliar a otra subbanda, sensor, geología o régimen de ruido exige nuevas validaciones; una posible investigación RMT sería un proyecto independiente.
