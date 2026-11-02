# Reporte Técnico de Etapa 8: Inferencia MT/AMT con Soporte Parcial (Puerta P8)

- **Versión:** `P8-2.0.0`
- **Fecha UTC:** 2026-10-29T17:34:04Z
- **Dispositivo:** `cuda` (Tiempo: 2.28 s)
- **Estado Global Puerta P8:** `APROBADO`

## 1. Resumen de Escenarios Evaluados

| Escenario | Descripción | Criterio Clave | Resultado | Estado |
|---|---|---|---|:---:|
| 1. Soporte Parcial | CTRL-03 + NOISE-D0-001 | Selectividad temporal: `0/120` limpio, `245` contaminado; Ganancia SNR: `+13.73 dB` | Intervención condicional exacta | PASA |
| 2. No Inferioridad Limpio | CTRL-01 Continuo | Sesgo Z: `0.0000%` (<=5%), Fase: `0.0000°` (<=2°) | No distorsiona limpio | PASA |
| 3. Compuerta G0 Soporte Vacío | CTRL-01 + soporte_S0 | Red omitida: `True`, Diff señal: `0.0e+00` | Cero intervención | PASA |
| 4. Campo Sin Vínculo TEM | ARMT5-123-01-01-01 | Estado: `soporte_vacio`, Red omitida: `True` | Omitir red | PASA |
| 5. Exclusión Estricta RMT | Bandas D2 y D3 | Omitidos: `True` y `True`, Diff: `0.0e+00` | Bloqueo absoluto RMT | PASA |
| 6. Rango 1 y Abstención | CTRL-04 Linealmente Polarizado | Abstenciones: `3/3` (Cond > 1e4) | Abstención tensor | PASA |
| 7. Invarianza y Reconstrucción | Lote 1 vs 32, Identidad | Diff lote: `5.2e-06`, Error ident: `8.9e-16` | Reconstrucción C1 perfecta | PASA |

## 2. Conclusiones Físicas y de Integración

1. **Recomposición continua C1 sin saltos de costura:** El operador Hanning overlap-add logra una reconstrucción exacta con error del orden de 1e-16 en identidad y garantiza continuidad suave en los bordes de ventana.
2. **Cumplimiento estricto de la compuerta G0:** Ante soporte TEM vacío (tanto sintético como de campo sin vínculo verificado), el pipeline omite automáticamente la red CBAM sin inventar etiquetas ni modificar los datos de campo, regresando al estimador robusto de referencia P6.
3. **Aislamiento absoluto de RMT:** Las bandas D2 y D3 quedan excluidas de la red neuronal por diseño, satisfaciendo el alcance estricto del Plan v1.3 (§8.3).
4. **Recuperación física superior en soporte parcial:** En presencia de contaminación severa, la cadena condicional recupera la respuesta Z(f) con menor error y mayor SNR, respetando F_aplicacion.
