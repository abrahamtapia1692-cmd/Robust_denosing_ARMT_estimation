# Etapa 0 — inventario, contrato y particiones (puerta P0)

Esta carpeta implementa la Etapa 0 del `PLAN_IMPLEMENTACION_ARMT.md` v1.3 con los datos reales disponibles. No modifica los proyectos de origen: lee `ARMT_processing` y el dosier TEM en modo solo lectura.

## Estado

**P0 = PARCIAL.** El inventario, el contrato, las particiones y el protocolo están congelados. No se cierran todavía:

- identidad oficial de sitio;
- verificación independiente de coordenadas y datum;
- vínculo TEM–ARMT;
- validez y cadena de aplicación de calibraciones;
- QC irreversible de clipping, canales muertos, saltos y huecos;
- etiquetas de escenario y familia de ruido;
- zona horaria de las marcas temporales.

Los bloqueos y campos desconocidos están en `manifest.json` (`unknowns` y `blockers`). No se rellenan con valores convenientes.

## Archivos

| Archivo | Función |
|---|---|
| `inventario_armt.py` | Escanea SBF, `.clb` y TEM; calcula SHA-256; genera `manifest.json` y `splits.csv` |
| `schema.json` | JSON Schema draft-07 del manifiesto |
| `splits.csv` | Particiones congeladas a nivel de registro y grupo de sitio |
| `protocolo_validacion.md` | Protocolo de evaluación congelado y criterios de cierre de P0 |
| `validar_muestras.py` | Lee todas las muestras declaradas y comprueba ida y vuelta NPY |
| `validar_etapa0.py` | Valida esquema, hashes, particiones, alcance y estado P0 |
| `manifest.json` | Manifiesto generado |
| `validacion_muestras.json` | Reporte de lectura completa |
| `validacion_etapa0.json` | Reporte de validación de Etapa 0 |

## Ejecución

```powershell
python etapa0/validar_muestras.py
python etapa0/inventario_armt.py
python etapa0/validar_etapa0.py
```

`validar_muestras.py` tarda varios minutos porque lee los ~6.9 GB de SBF. El inventario calcula hashes de todos los archivos de fuente. Para una comprobación rápida sin rehash de fuentes:

```powershell
python etapa0/validar_etapa0.py --no-source-hashes
```

## Resultado actual

- 15 registros SBF, 60 trazas, 300 canales escalares, 6.91 GB.
- 13 registros de 2021 (arreglo 700) y 2 de 2023 (arreglo 123).
- 73 archivos `.clb` en 9 grupos de ganancia.
- 6 sondeos TEM canónicos (`SER-09` a `SER-14`) de un dosier con 22 entradas.
- Particiones: 10 desarrollo, 3 validación, 2 prueba.
- Lectura completa: 15/15 registros aprobados, con spot checks y roundtrip NPY.
- Validación: 24 comprobaciones, 23 pasan, 0 fallan, 1 observación (versión del paquete `0.2.0` frente a `0.1.0` en `pyproject.toml`).

La campaña 2023 queda reservada para prueba. La validación usa tres sitios de 2021 (líneas 43, 55 y 90). El resto de 2021 queda para desarrollo.

## Advertencias

- Las coordenadas crudas se conservan como `UInt32`. La lectura en complemento a dos con escala `radianes × 10^8` produce una candidata plausible (17.8–19.3°N, 99.6–99.7°W), pero no se adopta como coordenada verificada.
- Las calibraciones se emparejan por tipo, serie y ganancia de directorio. Eso no certifica fecha, polaridad, longitud de dipolo ni cadena de aplicación.
- Los tiempos son locales y sin zona declarada.
- Un soporte TEM vacío es un resultado válido; no se extrapola para completar D0/D1.
