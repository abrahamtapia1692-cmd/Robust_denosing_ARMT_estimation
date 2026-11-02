# Reporte de Validación — Puertas P5 y P5-L: Datasets sin Fuga

- **Versión:** `P5-1.0.0` (Builder: `P5-BUILD-1.0.0`)
- **Fecha (UTC):** 2026-10-30T16:04:04.289901Z
- **Estado global:** **APROBADO**

## 1. Inventario y Conformidad de Datasets Construidos

| Dataset | Archivo | Muestras / Pares | Distribución de Clases / Tipos de Blanco |
|---|---|---:|---|
| **$D_{\text{id}}$** (Detección) | `D_id.npz` | 11732 | Clase 0: 5866, Clase 1: 5866 |
| **$D_{\text{sep}}$** (Separación) | `D_sep.npz` | 8811 | `exact_synthetic`: 8796, `exact_control`: 15 |
| **$D_{\text{real}}$** (Evaluación) | `D_real.npz` | 61 | Blanco `unavailable` (Cero blancos inventados) |

## 2. Control de Atajo Energético y Benchmark B7 (§5.4c)

- **Pareo de potencia activo:** Señal limpia escalada conjuntamente en $E$ y $H$ preservando $Z(f)$ y $\rho_a$.
- **Área bajo la curva ROC del clasificador B7 (solo-potencia):** **`AUC = 0.4310`** (Meta: $\le 0.65$).
- **Diagnóstico:** El detector $C_\theta$ no puede aprender un atajo trivial de amplitud; la discriminación exige aprender morfología y coherencia multicanal física.

## 3. Aislamiento Disjunto de Grupos (Puerta P5)

- **Grupos de entrenamiento:** `['GRP-ENTR-01', 'GRP-ENTR-02']`
- **Grupos de validación:** `['GRP-VAL-01']`
- **Grupos de prueba:** `['GRP-TEST-01']`
- **Intersección de grupos entre splits:** **0% (Cero fuga verificado)**.

## 4. Subpuerta P5-L: Trazabilidad y Ausencia de Blancos Falsos

1. Todos los pares en $D_{\text{sep}}$ declaran `exact_synthetic` o `exact_control` con procedencia exacta del modelado físico de Etapa 3.
2. Para los datos de campo real $F2$ ($D_{\text{real}}$), el blanco está marcado estrictamente como `unavailable`: ningún modelo BSS ni interpolación fue utilizado como pseudo-verdad de campo.
