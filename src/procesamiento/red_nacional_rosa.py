"""Rosa de contaminación de la red nacional, desde el par horario de SINCA.

Qué es una rosa de contaminación
--------------------------------
Cada pétalo es la **mediana horaria de MP2.5 de las horas en que el viento venía
de ese sector**. Cruza dos instrumentos de la misma estación en la misma hora:
el que mide partículas y la veleta. Un pétalo largo al este dice «cuando sopló
del este, el sensor midió más». No identifica la fuente ni predice hacia dónde
va el material particulado —eso exige un inventario de emisiones y un modelo de
dispersión, fuera del alcance— y sobre todo no afirma causalidad: es la regla 1
del proyecto.

Por qué no sirve la rosa que ya publica SINCA
---------------------------------------------
Airviro publica una rosa propia para cada estación, y es otra cosa: reparte las
**frecuencias** del viento, o sea cuántas horas sopló de cada lado. No dice nada
de la concentración. Pedirla es además el modo de fallo que documenta
`validar_horaria`: sin el sufijo `_spec`, el mismo macro devuelve esa tabla de
16 sectores con HTTP 200 y la cabecera de una serie.

Misma definición que las 16 del estudio
---------------------------------------
Los sectores, la ventana de invierno y el reparto son los de `SQL_ROSA` en
`src/sitio/exportar.py`, para que las dos rosas del mapa se puedan comparar:

* ocho sectores de 45°, el 0 centrado en el norte
  (`floor(((dir + 22.5) mod 360) / 45)`);
* invierno son los meses 5 a 8;
* solo entran las horas con las dos medidas presentes, MP2.5 ≥ 0 y
  dirección en [0, 360].

Dos diferencias, y las dos declaradas:

1. La mediana acá es **exacta**; la del estudio sale de `approx_percentile` de
   Athena, que es aproximada. En series de decenas de miles de horas la
   diferencia es de decimales.
2. No hay velocidad del viento. La rosa del estudio trae `vel_media` por sector
   y esta la deja en nulo: WSPD existe en SINCA pero el sitio no lo dibuja, y
   bajarlo habría duplicado el peso de la descarga para un campo que nadie lee.
   Coyhaique ya viaja así —`vel_media` toda en nulo— y el sitio lo tolera.

No toca `hecho_medicion` ni las tablas diarias
----------------------------------------------
`red_nacional_mes` y `red_nacional_anio` son diarias y agregadas; esta serie es
horaria. No se mezclan: acá entra el par horario y sale una tabla de ocho filas
por estación, que es un agregado del mismo orden que las otras dos.

Uso
---
    python -m src.procesamiento.red_nacional_rosa construir
    python -m src.procesamiento.red_nacional_rosa verificar
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.ingesta.red_nacional import (  # noqa: E402
    SERIES_HORARIAS,
    Rechazada,
    validar_horaria,
)
from src.rutas import LOGS, PROCESSED, asegurar  # noqa: E402

log = logging.getLogger("red-nacional-rosa")

SALIDA_ROSA = PROCESSED / "red_nacional_rosa"

SECTORES = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
MESES_INVIERNO = (5, 6, 7, 8)

# Rejas de cobertura. La rosa es una mediana por sector, y una mediana de cuatro
# horas no es una mediana: es una anécdota con forma de pétalo.
#
# MIN_HORAS_SECTOR — horas de invierno que necesita un sector para publicar su
# mediana. Con menos, el pétalo queda en nulo y el sitio no lo dibuja, que es lo
# que ya hace con los sectores sin dato de las estaciones del estudio.
#
# MIN_HORAS_INVIERNO — horas de invierno pareadas que necesita la estación para
# tener rosa. 720 son treinta días completos de mediciones horarias: menos que
# un invierno, suficiente para que la figura signifique algo. Una estación que
# no llega se queda «sin rosa», y el sitio ya sabe decirlo.
MIN_HORAS_SECTOR = 50
MIN_HORAS_INVIERNO = 720


def sector_de(grados: float) -> int:
    """Sector de 45° al que pertenece una dirección. 0 = norte.

    Es `floor(((dir + 22.5) mod 360) / 45)`, la misma expresión que usa la
    consulta del estudio. El desplazamiento de 22,5° es lo que centra el primer
    sector en el norte en vez de empezarlo ahí: 350° y 10° son los dos «norte».
    """
    return int(((grados + 22.5) % 360) // 45)


def leer_par(region_macro: str, codigo: str) -> tuple[list[dict], list[dict]] | None:
    """El par horario de una estación: dirección del viento y MP2.5.

    Devuelve None si falta cualquiera de los dos. Media rosa no es media
    información: sin las dos series a la misma hora no hay nada que cruzar.
    """
    base = f"sinca_{region_macro}_{codigo}"
    rw = SERIES_HORARIAS / f"{base}_wdir_horario.csv"
    rp = SERIES_HORARIAS / f"{base}_mp25_horario.csv"
    if not (rw.exists() and rp.exists()):
        return None
    # Se revalida al leer y no solo al descargar: un archivo de la zona cruda
    # puede haberse truncado al copiarse entre máquinas, y un truncamiento
    # silencioso daría una rosa más pobre sin avisar de nada.
    return (validar_horaria(rw.read_bytes(), "application/csv", "wdir"),
            validar_horaria(rp.read_bytes(), "application/csv", "mp25"))


def rosa_de(viento: list[dict], particulas: list[dict]) -> list[dict]:
    """Ocho filas, una por sector, con sus conteos y sus medianas.

    El cruce es por (fecha, hora) exacta. No se interpola ni se acerca a la hora
    más próxima: emparejar una concentración con la dirección de otra hora sería
    inventar la coincidencia que la rosa afirma haber observado.
    """
    dirs = {(f["fecha"], f["hora"]): f["valor"]
            for f in viento if f["valor"] is not None}

    todo: list[list[float]] = [[] for _ in SECTORES]
    invierno: list[list[float]] = [[] for _ in SECTORES]
    for f in particulas:
        v = f["valor"]
        if v is None or v < 0:
            continue
        d = dirs.get((f["fecha"], f["hora"]))
        if d is None:
            continue
        s = sector_de(d)
        todo[s].append(v)
        if int(f["fecha"][5:7]) in MESES_INVIERNO:
            invierno[s].append(v)

    return [{
        "sector": i,
        "sector_nombre": SECTORES[i],
        "n_horas": len(todo[i]),
        "med_anual": statistics.median(todo[i]) if todo[i] else None,
        "n_invierno": len(invierno[i]),
        "med_invierno": (statistics.median(invierno[i])
                         if len(invierno[i]) >= MIN_HORAS_SECTOR else None),
    } for i in range(len(SECTORES))]


def cmd_construir(args) -> int:
    from src.ingesta.red_nacional import SONDEO

    if not SERIES_HORARIAS.exists():
        raise SystemExit(
            f"No hay series horarias en {SERIES_HORARIAS}.\n"
            f"  Bájalas con: python -m src.ingesta.red_nacional viento")
    if not SONDEO.exists():
        raise SystemExit(f"Falta el sondeo en {SONDEO}.")

    doc = json.loads(SONDEO.read_text(encoding="utf-8"))
    filas, resumen = [], []
    sin_par, rechazadas, sin_cobertura = [], [], []

    for e in doc["estaciones"]:
        clave = f"{e['region_macro']}:{e['codigo']}"
        try:
            par = leer_par(e["region_macro"], e["codigo"])
        except Rechazada as ex:
            rechazadas.append({"estacion": clave, "motivo": str(ex)})
            log.error("%s: %s", clave, ex)
            continue
        if par is None:
            sin_par.append(clave)
            continue

        sectores = rosa_de(*par)
        horas_inv = sum(s["n_invierno"] for s in sectores)
        if horas_inv < MIN_HORAS_INVIERNO:
            sin_cobertura.append((clave, e["nombre"], horas_inv))
            log.info("%s (%s): solo %d horas de invierno pareadas; sin rosa",
                     clave, e["nombre"], horas_inv)
            continue

        for s in sectores:
            filas.append({"estacion_id": clave, **s})
        resumen.append({"estacion_id": clave, "nombre": e["nombre"],
                        "horas_invierno": horas_inv,
                        "horas": sum(s["n_horas"] for s in sectores)})

    if not filas:
        log.error("ninguna estación quedó con rosa; no se escribe nada")
        print("  ABORTADO - ninguna estacion con rosa. Las tablas anteriores quedan intactas.")
        return 1

    df = pd.DataFrame(filas)
    asegurar(PROCESSED)
    df.to_parquet(SALIDA_ROSA, index=False)

    print(f"  estaciones con rosa      : {len(resumen)}")
    print(f"  sin par horario en crudo : {len(sin_par)}")
    print(f"  bajo la reja de cobertura: {len(sin_cobertura)} "
          f"(minimo {MIN_HORAS_INVIERNO} horas de invierno)")
    if rechazadas:
        print(f"  archivos rechazados      : {len(rechazadas)}")
        for r in rechazadas[:5]:
            print(f"    - {r['estacion']}: {r['motivo'][:90]}")
    for c, n, h in sin_cobertura[:6]:
        print(f"    sin rosa: {n} ({c}) - {h} horas de invierno")
    petalos = int(df["med_invierno"].notna().sum())
    print(f"  petalos con mediana      : {petalos} de {len(df)}")
    print(f"  tabla -> {SALIDA_ROSA}")
    return 0


def cmd_verificar(args) -> int:
    if not SALIDA_ROSA.exists():
        raise SystemExit(f"No existe {SALIDA_ROSA}. Corre primero `construir`.")
    df = pd.read_parquet(SALIDA_ROSA)
    problemas = []

    porest = df.groupby("estacion_id")["sector"].agg(["count", "nunique"])
    incompletas = porest[(porest["count"] != 8) | (porest["nunique"] != 8)]
    if len(incompletas):
        problemas.append(f"{len(incompletas)} estaciones sin sus ocho sectores")
    if not df["sector"].between(0, 7).all():
        problemas.append("hay sectores fuera de 0-7")
    neg = df[(df["med_invierno"].notna()) & (df["med_invierno"] < 0)]
    if len(neg):
        problemas.append(f"{len(neg)} medianas negativas")
    vacias = porest.index[df.groupby("estacion_id")["med_invierno"]
                          .apply(lambda s: s.notna().sum() == 0)]
    if len(vacias):
        problemas.append(f"{len(vacias)} estaciones con la rosa entera en nulo")

    print(f"  estaciones: {df['estacion_id'].nunique()}   filas: {len(df)}")
    print(f"  petalos con mediana de invierno: {int(df['med_invierno'].notna().sum())}")
    print(f"  horas de invierno pareadas: {int(df['n_invierno'].sum()):,}".replace(",", "."))
    for p in problemas:
        print(f"  {p}")
    print("  todo consistente" if not problemas else f"\n  {len(problemas)} problema(s)")
    return 1 if problemas else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("construir").set_defaults(fn=cmd_construir)
    sub.add_parser("verificar").set_defaults(fn=cmd_verificar)
    args = p.parse_args(argv)
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "red_nacional_rosa.log", encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
