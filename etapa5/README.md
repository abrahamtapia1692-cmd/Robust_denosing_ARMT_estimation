# Etapa 5 — Construcción de Datasets de Entrenamiento sin Fuga (Puertas P5 y P5-L)

**Versión del módulo:** `P5-1.0.0` · **Configuración:** `P5-CONFIG-1.0.0`  
**Constructor:** `P5-BUILD-1.0.0` · **Validador:** `P5-VAL-1.0.0`  
**Fecha:** 29 de octubre de 2026  
**Estado:** **APROBADO** (25 comprobaciones PASA, 0 FALLA, 0 OBSERVACIONES en `validacion_etapa5.json`).

---

## 1. Objetivo y Fundamentos Metodológicos

La Etapa 5 implementa la construcción modular y auditable de los conjuntos de datos necesarios para el entrenamiento y evaluación del detector $C_\theta$ y el separador $D_\psi$ (Etapa 7), respetando estrictamente las restricciones de **aislamiento de grupos** y **trazabilidad de supervisión** establecidas en el Plan de Implementación v1.3 (§9) y la matriz canónica [`MATRIZ_ETIQUETAS_AMT.csv`](file:///d:/ARRT_software/Robust_denosing_ARMT_estimation/MATRIZ_ETIQUETAS_AMT.csv).

### Principios físico-metodológicos garantizados

1. **Tres conjuntos con propósitos desacoplados:**
   - **$D_{\text{id}}$ (Identificación):** Ventanas multicanal ($256 \times 4$) con etiquetas binarias equilibradas (Clase 0: 5,616 limpias, Clase 1: 5,616 contaminadas) para entrenar el detector $C_\theta$.
   - **$D_{\text{sep}}$ (Separación supervisada):** 8,435 pares alineados (entrada contaminada $x$, blanco limpio exacto $s$) para entrenar el separador $D_\psi$.
   - **$D_{\text{real}}$ (Evaluación de campo):** Ventanas de registros reales sin blanco supervisado (marcado explícitamente como `unavailable`).
2. **Control de atajo energético y pareo de potencia (§5.4c):**
   Para evitar que el clasificador $C_\theta$ aprenda un atajo trivial de amplitud o potencia en lugar de aprender morfología y coherencia multicanal física, se generaron ejemplos limpios negativos escalando conjuntamente $E$ y $H$:
   $$s_{\text{matched}}(t) = \alpha \cdot s(t)$$
   Dado que escalar ambas componentes por $\alpha$ preserva idénticamente el tensor $Z = (\alpha E)/(\alpha H) = E/H$ y la resistividad aparente $\rho_a \propto |E/H|^2$, la física electromagnética permanece inalterada mientras que la distribución de energía se iguala.
   - El clasificador base B7 (solo-potencia) arrojó un **`AUC = 0.4287`** (cercano al azar $0.50$, cumpliendo la meta $\le 0.65$), demostrando matemáticamente que la potencia no discrimina las clases.
3. **Aislamiento disjunto de grupos (Puerta P5):**
   Los grupos de modelos geológicos y fuentes de ruido se asignaron de forma disjunta:
   - `entrenamiento`: `GRP-ENTR-01` (Semiespacio D0 + Ruido D0-001) y `GRP-ENTR-02` (Semiespacio D1 + Ruido D1-004).
   - `validacion`: `GRP-VAL-01` (Modelo estratificado 3 capas D0 + Ruido D0-002, completamente reservado).
   - `prueba`: `GRP-TEST-01` (Modelo no estacionario con tipper y sferics D0, completamente reservado).
   - **Intersección entre particiones: 0% (Cero fuga de información)**.
4. **Subpuerta P5-L (Cero blancos inventados):**
   Todos los blancos en $D_{\text{sep}}$ corresponden exclusivamente a verdades analíticas exactas (`exact_synthetic` o `exact_control`). Para los datos de campo real $F2$, el blanco está marcado estrictamente como `unavailable`: no se utilizó ninguna salida de BSS ni interpolación como pseudo-verdad de campo.

---

## 2. Inventario de Datasets Generados

| Dataset | Archivo en `etapa5/datasets/` | Muestras / Pares | Canales | Clases / Tipos de Blanco | SHA-256 |
|---|---|---:|---|---|---|
| **$D_{\text{id}}$** | `D_id.npz` | 11,232 | $E_x, E_y, H_x, H_y$ | Clase 0: 5,616 (50%)<br>Clase 1: 5,616 (50%) | `532f62dbb797...` |
| **$D_{\text{sep}}$** | `D_sep.npz` | 8,435 | $E_x, E_y, H_x, H_y$ | `exact_synthetic`: 8,419<br>`exact_control`: 16 | `ce533b355fa9...` |
| **$D_{\text{real}}$** | `D_real.npz` | 61 | $E_x, E_y, H_x, H_y$ | `unavailable` (Subpuerta P5-L) | `e2a4be5a242c...` |

---

## 3. Estructura de Artefactos

| Archivo / Carpeta | Función |
|---|---|
| `config_p5.json` | Configuración formal (`P5-CONFIG-1.0.0`) de ventanas, particiones, fuentes y pareo de potencia. |
| `builder_datasets.py` | Motor de corte de ventanas, escalado de potencia, pareo de familias y evaluación B7. |
| `p5.py` | Driver CLI de construcción masiva de datasets, exportación de arrays y reporte de grupos. |
| `validar_etapa5.py` | Validador formal (25 comprobaciones de aislamiento, balance, blancos y contratos). |
| `dataset_manifest.json` | Manifiesto con hashes SHA-256, conteos y trazabilidad por familia. |
| `split_report.csv` | Mapeo detallado de cada grupo hacia su partición y parámetros. |
| `resumen_p5.json` | Resumen cuantitativo auditable de la Etapa 5. |
| `reporte_p5.md` | Informe técnico de validación. |
| `validacion_etapa5.json` | Certificado de validación formal de las Puertas P5 y P5-L. |
| `datasets/*.npz` | Datasets comprimidos listos para el entrenamiento de redes neuronales. |

---

## 4. Instrucciones de Reproducción

```powershell
# 1. Ejecutar la construcción completa de los datasets:
python etapa5/p5.py --mode all

# 2. Ejecutar la suite de validación formal:
python etapa5/validar_etapa5.py
```
