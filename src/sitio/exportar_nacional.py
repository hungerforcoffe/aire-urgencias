"""Exporta `nacional.json`: la capa de red nacional que dibuja el mapa.

Por qué no pasa por Athena
--------------------------
`src/sitio/exportar.py` consulta Athena porque sus cifras salen de las tablas
grandes del proyecto, que viven en S3 y no caben en el repositorio. Esta capa es
otra cosa: son 111 estaciones con su media mensual, un Parquet de pocos cientos
de kB que se construye entero en local desde la zona cruda. Hacerla pasar por
S3 y el catálogo de Glue no agregaría ni un dato y sí una credencial y dos pasos
más a la cadena.

Si algún día la red nacional entra al análisis, cambia: ahí sí tendría que subir
a `processed/` y declararse en Glue como las demás. Hoy es contexto del mapa.

Qué sale
--------
Solo las estaciones que **no** son del estudio. Las 16 del estudio ya viajan en
`estaciones.json`; repetirlas acá sería publicar dos veces el mismo dato y
arriesgar que las dos copias se contradigan.

El registro de cada estación tiene **la misma forma que en `estaciones.json`**
—mismos campos, mismo bloque `anual`, `rosa` en null— para que el mapa no tenga
que saber de qué colección viene la estación que está dibujando. La serie mensual
también guarda las mismas tres posiciones `[media, días, sobre50]`, que es lo que
lee el panel de episodios del meteograma.

Uso
---
    python -m src.sitio.exportar_nacional
    python -m src.sitio.exportar_nacional --verificar
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.procesamiento.red_nacional import (  # noqa: E402
    MIN_DIAS_MES,
    SALIDA_ANIO,
    SALIDA_EST,
    SALIDA_MES,
)
from src.procesamiento.red_nacional_rosa import (  # noqa: E402
    MIN_HORAS_INVIERNO,
    MIN_HORAS_SECTOR,
    SALIDA_ROSA,
    SECTORES,
)
from src.rutas import LOGS, RAIZ, asegurar  # noqa: E402

log = logging.getLogger("sitio.nacional")

SALIDA = RAIZ / "sitio" / "assets" / "datos"
ARCHIVO = "nacional.json"

# Mínimos por debajo de los cuales se aborta. Están puestos en el orden de
# magnitud de lo medido —111 estaciones, 104 meses— y no en 1: un archivo con
# tres estaciones pasaría un chequeo de «no vacío» y dejaría el mapa casi
# vacío sin que nadie se enterara.
MIN_ESTACIONES = 40
MIN_FILAS_MES = 2000
MIN_FILAS_ANIO = 300


class Vacio(Exception):
    """La consulta devolvió menos de lo que este sitio considera publicable."""


def cmd_exportar(args) -> int:
    for ruta in (SALIDA_EST, SALIDA_MES, SALIDA_ANIO):
        if not ruta.exists():
            raise SystemExit(
                f"Falta {ruta}.\n"
                f"  Constrúyelo con: python -m src.procesamiento.red_nacional construir")

    est = pq.read_table(SALIDA_EST).to_pandas()
    mes = pq.read_table(SALIDA_MES).to_pandas()
    anio = pq.read_table(SALIDA_ANIO).to_pandas()

    # La rosa es opcional: se construye con un par horario que no todas las
    # estaciones tienen y que se baja aparte. Si la tabla no está, las estaciones
    # salen sin rosa —igual que hoy— en vez de abortar la exportación entera.
    rosa = None
    if SALIDA_ROSA.exists():
        rosa = pq.read_table(SALIDA_ROSA).to_pandas()
    else:
        log.info("sin %s: las estaciones saldrán sin rosa", SALIDA_ROSA)

    nuevas = est[~est["en_estudio"]].copy()
    ids = set(nuevas["estacion_id"])
    mes = mes[mes["estacion_id"].isin(ids) & mes["suficiente"]]
    anio = anio[anio["estacion_id"].isin(ids)]

    # Regla 5, en el último paso: un vacío silencioso publicado es peor que un
    # error visible. Se aborta ANTES de escribir, así el archivo anterior queda
    # intacto y el sitio sigue mostrando lo último bueno.
    if len(nuevas) < MIN_ESTACIONES:
        raise Vacio(f"solo {len(nuevas)} estaciones nuevas (mínimo {MIN_ESTACIONES})")
    if len(mes) < MIN_FILAS_MES:
        raise Vacio(f"solo {len(mes)} filas estación-mes (mínimo {MIN_FILAS_MES})")
    if len(anio) < MIN_FILAS_ANIO:
        raise Vacio(f"solo {len(anio)} filas estación-año (mínimo {MIN_FILAS_ANIO})")
    if nuevas["lat"].isna().any() or nuevas["lon"].isna().any():
        raise Vacio("hay estaciones sin coordenada; el mapa no puede ubicarlas")

    # La rosa por estación, con la misma forma que en estaciones.json: ocho
    # posiciones en el orden N, NE, E, SE, S, SO, O, NO. `vel_media` va en nulo
    # porque esta capa no baja la velocidad del viento —el sitio no la dibuja—;
    # Coyhaique ya viaja así entre las del estudio y el mapa lo tolera.
    rosas: dict[str, dict] = {}
    if rosa is not None:
        for eid, g in rosa.groupby("estacion_id"):
            g = g.sort_values("sector")
            if len(g) != len(SECTORES):
                log.warning("%s: la rosa no trae ocho sectores; se descarta", eid)
                continue
            rosas[eid] = {
                "invierno": [None if pd.isna(v) else round(float(v), 1)
                             for v in g.med_invierno],
                "anual": [None if pd.isna(v) else round(float(v), 1)
                          for v in g.med_anual],
                "horas_invierno": [int(v) for v in g.n_invierno],
                "horas": [int(v) for v in g.n_horas],
                "vel_media": [None] * len(SECTORES),
            }

    # El bloque `anual` por estación, con la misma forma que en estaciones.json.
    anual: dict[str, dict] = {}
    for r in anio.itertuples():
        anual.setdefault(r.estacion_id, {})[str(int(r.anio))] = {
            "dias": int(r.dias), "media": round(float(r.media), 1),
            "sobre50": int(r.sobre50), "p98": round(float(r.p98), 1),
            "completo": bool(r.completo),
        }

    estaciones = [
        {
            "id": r.estacion_id,
            "nombre": r.nombre,
            # `ciudad` es null a propósito: estas estaciones NO son del estudio y
            # no deben entrar en ningún promedio de ciudad. `ciudad_estudio` dice
            # si su comuna pertenece a una de las tres, y existe solo para
            # marcarlas en la barra lateral — nunca para agregar.
            "ciudad": None,
            "ciudad_estudio": r.ciudad_estudio if isinstance(r.ciudad_estudio, str) else None,
            "comuna": r.comuna,
            "region": r.region,
            "orden_region": int(r.orden_region),
            "lat": round(float(r.lat), 5),
            "lon": round(float(r.lon), 5),
            # Sin par horario de viento y partículas no hay rosa. El sitio ya
            # sabe dibujar ese caso: tres de las 16 del estudio están igual.
            "mide_viento": r.estacion_id in rosas,
            "rosa": rosas.get(r.estacion_id),
            "anual": anual.get(r.estacion_id, {}),
        }
        for r in nuevas.sort_values(["orden_region", "comuna", "nombre"]).itertuples()
    ]

    # Tercera posición = días sobre 50 µg/m³, igual que en mensual.json, que es
    # lo que lee el panel de episodios del meteograma.
    mensual: dict[str, dict[str, list]] = {}
    for r in mes.itertuples():
        clave = f"{int(r.anio):04d}-{int(r.mes):02d}"
        mensual.setdefault(clave, {})[r.estacion_id] = [
            round(float(r.media), 1), int(r.dias), int(r.sobre50)]

    payload = {
        "generado": __import__("datetime").datetime.now(
            __import__("datetime").UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "fuente": "SINCA — red nacional, serie diaria de MP2.5 agregada a mes y año",
        "min_dias_mes": MIN_DIAS_MES,
        "min_horas_invierno_rosa": MIN_HORAS_INVIERNO,
        "min_horas_sector_rosa": MIN_HORAS_SECTOR,
        "conteos": {"estaciones": len(estaciones), "meses": len(mensual),
                    "con_rosa": sum(1 for e in estaciones if e["rosa"]),
                    "del_estudio_excluidas": int(est["en_estudio"].sum())},
        "estaciones": estaciones,
        "mensual": mensual,
    }

    asegurar(SALIDA)
    ruta = SALIDA / ARCHIVO
    ruta.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    print(f"  {ARCHIVO}: {ruta.stat().st_size / 1024:.1f} kB")
    print(f"  estaciones nuevas en el mapa: {len(estaciones)}")
    print(f"  meses con dato              : {len(mensual)}")
    print(f"  con rosa de contaminacion   : {sum(1 for e in estaciones if e['rosa'])}")
    print(f"  regiones                    : {nuevas['region_romana'].nunique()} de 16")
    return 0


def cmd_verificar(args) -> int:
    ruta = SALIDA / ARCHIVO
    if not ruta.exists():
        raise SystemExit(f"No existe {ruta}. Corre primero el exportador.")
    d = json.loads(ruta.read_text(encoding="utf-8"))
    est = {e["id"] for e in d["estaciones"]}
    sueltas = {i for m in d["mensual"].values() for i in m} - est
    print(f"  generado {d['generado']}")
    print(f"  estaciones {len(est)}   meses {len(d['mensual'])}")
    print("  ids del mensual sin ficha:", len(sueltas) or "ninguno")
    fuera = [e for e in d["estaciones"]
             if not (-56 <= e["lat"] <= -17.3 and -110 <= e["lon"] <= -66)]
    print("  coordenadas fuera de Chile:", len(fuera) or "ninguna")
    con_rosa = [e for e in d["estaciones"] if e["rosa"]]
    malas = [e["id"] for e in con_rosa
             if len(e["rosa"]["invierno"]) != 8
             or all(v is None for v in e["rosa"]["invierno"])
             or e["mide_viento"] is not True]
    print(f"  con rosa: {len(con_rosa)}   rosas mal formadas: {len(malas) or 'ninguna'}")
    return 1 if (sueltas or fuera or malas) else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--verificar", action="store_true",
                   help="relee lo escrito en vez de volver a generarlo")
    args = p.parse_args(argv)
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "sitio_exportar.log", encoding="utf-8")])
    try:
        return cmd_verificar(args) if args.verificar else cmd_exportar(args)
    except Vacio as e:
        log.error("no se publica: %s", e)
        print(f"  ABORTADO — {e}\n  El {ARCHIVO} anterior queda intacto.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
