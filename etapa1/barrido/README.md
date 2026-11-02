# Barrido P1 — los 15 registros

Extensión de la Etapa 1 sobre el conjunto completo del manifiesto P0. Reutiliza
los mismos umbrales de QC, el mismo lector SBF y el mismo criterio de
calibración que `../config_p1.json`, pero **no reexporta series temporales**: el
único `.npy` del proyecto sigue siendo el de `ARMT5-700-14-14-01`.

## Ejecución

```powershell
python etapa1/barrido_registros.py
python etapa1/validar_barrido.py
```

El barrido tarda varios minutos porque lee los 6.91 GB de SBF y calcula el
SHA-256 de cada fuente. No escribe en `ARMT_processing/` ni en `etapa0/`.

## Archivos

| Archivo | Función |
|---|---|
| `../config_barrido.json` | Configuración `P1-CONFIG-2.0.0` (bandas, QC, calibración) |
| `../barrido_registros.py` | Recorre los 15 registros y escribe los entregables |
| `../validar_barrido.py` | Comprueba hashes, longitudes, máscaras, cobertura y alcance |
| `registros/<id>.json` | QC, consistencia SBF↔manifiesto y calibración por registro |
| `mascaras/<id>_<banda>.npz` | Máscaras `bad_<canal>` empaquetadas little-endian |
| `qc_registros.csv` | 150 filas: registro × banda × canal |
| `calibracion_cobertura.csv` | 150 filas de cobertura y ganancia por canal |
| `ganancias_registros.csv` | Una fila por registro con ganancia, ADC, dipolo y azimuts |
| `resumen_global.json` | Agregados, tiempos, hashes de P0 y estado declarado |
| `reporte_barrido.md` | Reporte legible del barrido |
| `validacion_barrido.json` | Resultado de la validación |

## Qué cierra y qué no

- **Cierra B-P0-05 a nivel de QC** para los 15 registros en D0/D1: longitud,
  clipping, canales muertos, valores pegados, relleno de ceros, saltos y
  máscaras.
- **No cierra B-P0-04**: la calibración solo se verifica como cobertura de
  frecuencia y hash. Sigue sin fecha, certificado ni sección de ganancia.
- **No cierra B-P0-01, B-P0-02, B-P0-03, B-P0-06 ni B-P0-07.**
- **No habilita P2-T** ni la síntesis guiada por TEM.
- Los saltos por amplitud se reportan y **no se enmascaran**: pueden ser sferics
  útiles.
