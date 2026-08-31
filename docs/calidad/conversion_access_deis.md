# Conversión de los .mdb de Access del DEIS (2018-2019) a CSV

- **Fecha:** 2026-08-26
- **Aplica a:** DEIS 2018 y 2019. Salida en `data/interim/deis/`
- **Implementada en:** `src/procesamiento/deis_access.py`
- **Verificable con:** `python -m src.procesamiento.deis_access verificar`

## Qué se observó

El DEIS publica cada año en el formato que le conviene. En la ventana del
estudio hay **tres**:

| Años | Dentro del ZIP | Cabecera | Fecha |
|---|---|---|---|
| 2018, 2019 | `.mdb` de Access, ~1,1 GB | columnas `Col01`…`Col06` | `dd/mm/aaaa` |
| 2020 | `.csv` de 1,04 GB | **ninguna** | `Wed Sep 23 00:00:00 GMT-04:00 2020` |
| 2021-2026 | `.csv` | nombres completos | `dd/mm/aaaa` |

Athena no lee `.mdb`. Spark tampoco. Pandas tampoco sin un driver ODBC. Los dos
primeros años del estudio —**9.039.812 filas**— quedaban fuera de todo.

Los ZIP de 2018, 2019 y 2020 traen además **dos** entradas, no una: el
diccionario oficial `ATENCIONES_DE_URGENCIA.xlsx` (359.866 bytes, idéntico en
los tres) y después el dato. Un lector que se quede con la primera entrada
descarta el año entero creyendo que no hay datos.

## Herramienta

**No hace falta `mdbtools`.** En Windows el driver
`Microsoft Access Driver (*.mdb, *.accdb)` viene instalado con Office y está
registrado para el Python de 64 bits del proyecto; `pyodbc` ya estaba entre las
dependencias. Comprobado con `pyodbc.drivers()`.

Si en otra máquina faltara, el módulo lo detecta por el código de error `IM002` y
lo dice explícitamente en vez de fallar con un error de ODBC ilegible.

## El mapeo de columnas — que no se adivinó

Los `.mdb` llaman a las columnas de datos `Col01` … `Col06`. El nombre no dice
nada, y equivocarse invierte los grupos etarios sin que ninguna consulta
posterior lo note.

La respuesta está **dentro del propio ZIP**, en la hoja `DiccionarioSADU` del
diccionario oficial, que las define por posición:

| N° | Variable en el diccionario | Descripción |
|---|---|---|
| 5 | `TOTAL` | total de atenciones de urgencia |
| 6 | `MENOR_A_1` | menores de 1 año |
| 7 | `Column7` | 1 a 4 años |
| 8 | `__14` | 5 a 14 años |
| 9 | `_5_64` | 15 a 64 años |
| 10 | `_5_MAS` | 65 o más años |

(Los nombres del propio diccionario vienen destrozados por Excel; las
descripciones no.)

Mapeo adoptado, idéntico a la cabecera de 2021-2022:

```
Col01 -> Total          Col04 -> De_5_a_14
Col02 -> Menores_1      Col05 -> De_15_a_64
Col03 -> De_1_a_4       Col06 -> De_65_y_mas
```

**Contrastado contra los datos**, no solo contra el documento:

- `Col01 = Col02+Col03+Col04+Col05+Col06` se cumple en el **100%** de las
  4.488.935 filas de 2018 y de las 4.550.877 de 2019. Cero excepciones.
- Los máximos son coherentes con el orden por edad: en 2018, Col01 = 2.732 (el
  mayor, como debe ser un total) y Col05 = 1.681, el grupo 15-64, que es la
  banda más ancha.

## El mapeo va por POSICIÓN, no por nombre

El `.mdb` de **2019 trae un BOM pegado al nombre de la primera columna**:
`﻿idestablecimiento`. El de 2018 no. Cruzar por nombre funciona en un año y
falla en el otro, que es la peor combinación posible: parece que funciona.

`deis_access.py` pide las columnas en el orden en que las declara el `.mdb` y
solo renombra la cabecera al escribir. **Nada se reordena.**

## Verificación

Un volcado sin releer no está verificado. El módulo comprueba, para cada año:

1. La tabla es única dentro del `.mdb` y tiene exactamente 15 columnas.
2. Las filas escritas coinciden con `COUNT(*)` del `.mdb`.
3. `SUM(Col01)` del `.mdb` coincide con la suma de `Total` del CSV.
4. **Se vuelve a abrir el CSV desde cero** y se recuentan filas, suma y fechas
   distintas.

Si algo no cuadra, sale con código 1.

## ¿Siguen sirviendo estos años?

Sí. El catálogo de causas es **más corto** que en los años recientes —27 causas
frente a 40— pero la diferencia está toda en causas que el estudio no usa: las
de COVID (30-33) y las de salud mental (35-41) no existían todavía.

**Las seis causas respiratorias de detalle están completas en ambos años**, con
la misma glosa y el mismo rango CIE-10 que en 2026:

| IdCausa | Glosa | 2018 | 2019 |
|---|---|---|---|
| 3 | Bronquitis/bronquiolitis aguda (J20-J21) | sí | sí |
| 4 | Influenza (J09-J11) | sí | sí |
| 5 | Neumonía (J12-J18) | sí | sí |
| 6 | Otra causa respiratoria (J22, J30-J39, J47, J60-J98) | sí | sí |
| 10 | IRA Alta (J00-J06) | sí | sí |
| 11 | Crisis obstructiva bronquial (J40-J46) | sí | sí |

También están los agregados 2 y 7 —la trampa de «atenciones» frente a
«hospitalizaciones»— así que la regla de `dim_causa` aplica igual.

Otros contrastes: 365 fechas distintas en cada año, 472 y 475 establecimientos,
52 semanas, y **cero nulos** en `fecha`, `semana`, `Idcausa` y `Col01`.

## Dónde queda

En `data/interim/`, nunca en `data/raw/`. La zona cruda guarda los ZIP tal como
los publicó el DEIS. Un CSV convertido es un intermedio regenerable: si se
pierde, se vuelve a producir desde el ZIP con un comando.

Por lo mismo **no se sube a S3**: `src/nube/sincronizar.py` no sincroniza
`interim/`, y la regla de ciclo de vida del bucket lo expira a los 30 días.

## Efecto colateral: se cierra la validación de semanas MMWR

`src/procesamiento/tiempo.py` solo podía validar 2020-2026 porque 2018 y 2019 no
tenían CSV. Ahora su validador acepta también los CSV de `interim/` como
respaldo cuando el ZIP no trae ninguno, y la ventana queda cubierta entera.

El caso que más importa está justo en el borde: en el CSV convertido de 2018,
las filas del **30 y 31 de diciembre** llevan `semana = 1`. Es correcto según
MMWR —esa semana va del domingo 30 de diciembre de 2018 al sábado 5 de enero de
2019, y su miércoles cae en 2019— y es exactamente donde una implementación con
`isocalendar()` daría otra cosa.
