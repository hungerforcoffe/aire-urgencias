"""Convierte los .mdb de Access del DEIS (2018-2019) a CSV, y lo verifica.

Por qué hace falta
------------------
El DEIS publica cada año en el formato que le viene bien. Entre 2018 y 2026 hay
al menos tres:

    2018, 2019   ZIP con un .mdb de Access de ~1,1 GB
    2020         ZIP con CSV sin cabecera y fecha en formato Date.toString() de Java
    2021-2026    ZIP con CSV con cabecera y fecha dd/mm/aaaa

Athena no lee `.mdb`, Spark tampoco, y pandas tampoco sin un driver ODBC. Los
dos primeros años del estudio quedaban fuera de todo. Este módulo los pasa a
CSV con **la misma cabecera que los años 2021-2022**, de modo que un solo lector
sirva para los nueve años.

En Windows no hace falta `mdbtools`: el driver «Microsoft Access Driver
(*.mdb, *.accdb)» ya viene instalado con Office y `pyodbc` está entre las
dependencias del proyecto.

El mapeo de columnas no se adivina
----------------------------------
Los .mdb llaman a las columnas de datos `Col01` … `Col06`, que no dicen nada. El
**diccionario oficial** que viaja dentro del propio ZIP
(`ATENCIONES_DE_URGENCIA.xlsx`, hoja `DiccionarioSADU`) las define por posición:

    5  TOTAL       total de atenciones
    6  MENOR_A_1   menores de 1 año
    7  Column7     1 a 4 años
    8  __14        5 a 14 años
    9  _5_64       15 a 64 años
    10 _5_MAS      65 o más años

Comprobado además contra los datos: `Col01 = Col02+…+Col06` se cumple en el
**100%** de las 4.488.935 filas de 2018 y de las 4.550.877 de 2019.

Dónde escribe
-------------
En `data/interim/`, nunca en `data/raw/`. La zona cruda guarda los ZIP tal como
los publicó el DEIS y no se toca (regla 3). Un CSV convertido es un
intermedio regenerable: si se pierde, se vuelve a generar desde el ZIP.

Uso
---
    python -m src.procesamiento.deis_access convertir
    python -m src.procesamiento.deis_access convertir --anios 2018
    python -m src.procesamiento.deis_access verificar
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.rutas import INTERIM, LOGS, RAW, asegurar  # noqa: E402

log = logging.getLogger("deis-access")

DRIVER = "{Microsoft Access Driver (*.mdb, *.accdb)}"
DESTINO = INTERIM / "deis"

# Orden posicional del .mdb -> nombre de la cabecera de 2021-2022.
# La clave es la posición, no el nombre: el .mdb de 2019 trae un BOM pegado al
# primer nombre de columna (`﻿idestablecimiento`), así que cruzar por
# nombre falla en un año y funciona en el otro, que es la peor combinación.
CABECERA = ["IdEstablecimiento", "NEstablecimiento", "IdCausa", "GlosaCausa",
            "Total", "Menores_1", "De_1_a_4", "De_5_a_14", "De_15_a_64", "De_65_y_mas",
            "fecha", "semana",
            "GLOSATIPOESTABLECIMIENTO", "GLOSATIPOATENCION", "GlosaTipoCampana"]

LOTE = 50_000
ENCODING = "latin-1"      # el mismo que usan los CSV del DEIS de los otros años


def _conectar(mdb: Path):
    import pyodbc
    try:
        return pyodbc.connect(f"DRIVER={DRIVER};DBQ={mdb.resolve()};",
                              autocommit=True, readonly=True)
    except pyodbc.Error as e:
        if "IM002" in str(e):
            raise SystemExit(
                "No hay driver de Access registrado para esta arquitectura de Python.\n"
                "  Instala «Microsoft Access Database Engine» de 64 bits, o usa un\n"
                "  Python de 32 bits si el Office instalado es de 32.") from e
        raise SystemExit(f"No se pudo abrir {mdb.name}: {e}") from e


def extraer_mdb(anio: int) -> Path:
    """Saca el .mdb del ZIP crudo a interim/, si no está ya."""
    zips = list(RAW.glob(f"deis/*{anio}*.zip"))
    if not zips:
        raise SystemExit(f"No hay ZIP del DEIS de {anio} en {RAW / 'deis'}")
    with zipfile.ZipFile(zips[0]) as z:
        mdbs = [i for i in z.infolist() if i.filename.lower().endswith(".mdb")]
        if not mdbs:
            dentro = ", ".join(i.filename for i in z.infolist())
            raise SystemExit(f"{zips[0].name} no tiene .mdb; contiene {dentro}")
        destino = DESTINO / Path(mdbs[0].filename).name
        if destino.exists() and destino.stat().st_size == mdbs[0].file_size:
            log.info("%s ya extraído", destino.name)
            return destino
        asegurar(DESTINO)
        log.info("extrayendo %s (%.2f GB)", mdbs[0].filename, mdbs[0].file_size / 1024**3)
        with z.open(mdbs[0]) as origen, open(destino, "wb") as fh:
            while bloque := origen.read(8 * 1024 * 1024):
                fh.write(bloque)
    return destino


def convertir(mdb: Path, salida: Path) -> dict:
    """Vuelca la tabla del .mdb a CSV y devuelve lo medido durante el volcado."""
    cn = _conectar(mdb)
    cur = cn.cursor()
    tablas = [r.table_name for r in cur.tables(tableType="TABLE")]
    if len(tablas) != 1:
        raise SystemExit(f"{mdb.name} tiene {len(tablas)} tablas ({tablas}); se esperaba 1")
    tabla = tablas[0]

    columnas = [c.column_name for c in cur.columns(table=tabla)]
    if len(columnas) != len(CABECERA):
        raise SystemExit(f"{mdb.name}: {len(columnas)} columnas, se esperaban "
                         f"{len(CABECERA)}.\n  Encontradas: {columnas}")
    log.info("%s: tabla %s, columnas originales %s", mdb.name, tabla, columnas)

    cur.execute(f"SELECT COUNT(*) FROM [{tabla}]")
    esperadas = cur.fetchone()[0]
    cur.execute(f"SELECT SUM(CLng(Col01)) FROM [{tabla}]")
    suma_origen = int(cur.fetchone()[0])

    # Se pide por posición y en el orden del .mdb; el renombrado ocurre solo en
    # la cabecera del CSV. Nada se reordena.
    seleccion = ", ".join(f"[{c}]" for c in columnas)
    cur.execute(f"SELECT {seleccion} FROM [{tabla}]")

    escritas = 0
    suma_total = 0
    fechas: set[str] = set()
    asegurar(salida.parent)
    with open(salida, "w", encoding=ENCODING, newline="", errors="strict") as fh:
        w = csv.writer(fh, delimiter=";", lineterminator="\n")
        w.writerow(CABECERA)
        while lote := cur.fetchmany(LOTE):
            for fila in lote:
                w.writerow(["" if v is None else v for v in fila])
                suma_total += int(fila[4] or 0)
                fechas.add(fila[10])
            escritas += len(lote)
            if escritas % (LOTE * 20) == 0:
                log.info("  %s: %d/%d filas", salida.name, escritas, esperadas)
    cn.close()
    return {"tabla": tabla, "columnas_origen": columnas, "esperadas": esperadas,
            "escritas": escritas, "suma_origen": suma_origen, "suma_csv": suma_total,
            "fechas": len(fechas)}


def verificar(salida: Path, medido: dict) -> list[str]:
    """Vuelve a leer el CSV desde cero. Un volcado sin releer no está verificado."""
    fallos = []
    if medido["escritas"] != medido["esperadas"]:
        fallos.append(f"se escribieron {medido['escritas']:,} filas de "
                      f"{medido['esperadas']:,}")
    if medido["suma_csv"] != medido["suma_origen"]:
        fallos.append(f"la suma de Total no cuadra: {medido['suma_csv']:,} en el CSV "
                      f"contra {medido['suma_origen']:,} en el .mdb")

    lineas = 0
    suma = 0
    fechas: set[str] = set()
    with open(salida, encoding=ENCODING, newline="") as fh:
        r = csv.reader(fh, delimiter=";")
        cabecera = next(r)
        if cabecera != CABECERA:
            fallos.append(f"cabecera releída distinta: {cabecera}")
        for fila in r:
            lineas += 1
            if len(fila) != len(CABECERA):
                fallos.append(f"línea {lineas + 1}: {len(fila)} campos")
                break
            suma += int(fila[4] or 0)
            fechas.add(fila[10])
    if lineas != medido["esperadas"]:
        fallos.append(f"releído: {lineas:,} filas, se esperaban {medido['esperadas']:,}")
    if suma != medido["suma_origen"]:
        fallos.append(f"releído: suma {suma:,}, se esperaba {medido['suma_origen']:,}")
    if len(fechas) != medido["fechas"]:
        fallos.append(f"releído: {len(fechas)} fechas, se esperaban {medido['fechas']}")
    return fallos


def cmd_convertir(args) -> int:
    anios = [int(a) for a in args.anios.split(",")] if args.anios else [2018, 2019]
    problemas = 0
    for anio in anios:
        print(f"\n  {anio}")
        mdb = extraer_mdb(anio)
        salida = DESTINO / f"AtencionesUrgencia{anio}.csv"
        if salida.exists() and not args.rehacer:
            print(f"    ya existe {salida.name}; usa --rehacer para regenerarlo")
            continue
        print(f"    origen  : {mdb.name}  ({mdb.stat().st_size / 1024**3:.2f} GB)")
        medido = convertir(mdb, salida)
        print(f"    tabla   : {medido['tabla']}")
        print(f"    filas   : {medido['escritas']:,}")
        print(f"    fechas  : {medido['fechas']}")
        print(f"    salida  : {salida.name}  "
              f"({salida.stat().st_size / 1024**3:.2f} GB, {ENCODING}, separador «;»)")

        fallos = verificar(salida, medido)
        if fallos:
            problemas += 1
            print("    VERIFICACIÓN FALLIDA:")
            for f in fallos:
                print(f"      · {f}")
        else:
            print(f"    verificado: releído entero, {medido['escritas']:,} filas y "
                  f"suma de Total = {medido['suma_origen']:,} coinciden")
    return 1 if problemas else 0


def cmd_verificar(args) -> int:
    """Contrasta cada CSV convertido contra su .mdb, sin volver a convertir."""
    csvs = sorted(DESTINO.glob("AtencionesUrgencia*.csv"))
    if not csvs:
        raise SystemExit(f"No hay CSV convertidos en {DESTINO}. Corre «convertir» antes.")
    malos = 0
    for ruta in csvs:
        anio = ruta.stem[-4:]
        mdb = next(DESTINO.glob(f"*{anio}*.mdb"), None)
        if mdb is None:
            print(f"  {ruta.name}: sin .mdb con el que contrastar")
            continue
        cn = _conectar(mdb)
        cur = cn.cursor()
        tabla = [r.table_name for r in cur.tables(tableType="TABLE")][0]
        cur.execute(f"SELECT COUNT(*), SUM(CLng(Col01)) FROM [{tabla}]")
        n_mdb, suma_mdb = cur.fetchone()
        cn.close()

        n_csv = suma_csv = 0
        fechas = set()
        with open(ruta, encoding=ENCODING, newline="") as fh:
            r = csv.reader(fh, delimiter=";")
            next(r)
            for fila in r:
                n_csv += 1
                suma_csv += int(fila[4] or 0)
                fechas.add(fila[10])
        ok = (n_csv == n_mdb) and (suma_csv == int(suma_mdb))
        malos += 0 if ok else 1
        print(f"  {'OK ' if ok else '!! '}{ruta.name:<28} "
              f"filas {n_csv:>9,} vs {n_mdb:>9,}   "
              f"suma {suma_csv:>11,} vs {int(suma_mdb):>11,}   fechas {len(fechas)}")
    return 1 if malos else 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convertir")
    c.add_argument("--anios", default=None, help="por defecto 2018,2019")
    c.add_argument("--rehacer", action="store_true", help="regenera aunque el CSV exista")
    c.set_defaults(fn=cmd_convertir)
    sub.add_parser("verificar").set_defaults(fn=cmd_verificar)

    args = p.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "deis_access.log", encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
