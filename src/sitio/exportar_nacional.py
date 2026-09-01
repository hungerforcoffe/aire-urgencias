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
`estaciones.json` con su rosa, su meteograma y su serie horaria; repetirlas acá
sería publicar dos veces el mismo dato y arriesgar que las dos copias se
contradigan.

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

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.procesamiento.red_nacional import (  # noqa: E402
    MIN_DIAS_MES,
    SALIDA_EST,
    SALIDA_MES,
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


class Vacio(Exception):
    """La consulta devolvió menos de lo que este sitio considera publicable."""


def cmd_exportar(args) -> int:
    for ruta in (SALIDA_EST, SALIDA_MES):
        if not ruta.exists():
            raise SystemExit(
                f"Falta {ruta}.\n"
                f"  Constrúyelo con: python -m src.procesamiento.red_nacional construir")

    est = pq.read_table(SALIDA_EST).to_pandas()
    mes = pq.read_table(SALIDA_MES).to_pandas()

    nuevas = est[~est["en_estudio"]].copy()
    mes = mes[mes["estacion_id"].isin(set(nuevas["estacion_id"]))]
    mes = mes[mes["suficiente"]]

    # Regla 5, en el último paso: un vacío silencioso publicado es peor que un
    # error visible. Se aborta ANTES de escribir, así el archivo anterior queda
    # intacto y el sitio sigue mostrando lo último bueno.
    if len(nuevas) < MIN_ESTACIONES:
        raise Vacio(f"solo {len(nuevas)} estaciones nuevas (mínimo {MIN_ESTACIONES})")
    if len(mes) < MIN_FILAS_MES:
        raise Vacio(f"solo {len(mes)} filas estación-mes (mínimo {MIN_FILAS_MES})")
    if nuevas["lat"].isna().any() or nuevas["lon"].isna().any():
        raise Vacio("hay estaciones sin coordenada; el mapa no puede ubicarlas")

    estaciones = [
        {"id": r.estacion_id, "n": r.nombre, "c": r.comuna, "r": r.region_romana,
         "lat": round(float(r.lat), 5), "lon": round(float(r.lon), 5),
         "dias": int(r.dias_totales)}
        for r in nuevas.sort_values("nombre").itertuples()
    ]

    mensual: dict[str, dict[str, list]] = {}
    for r in mes.itertuples():
        clave = f"{int(r.anio):04d}-{int(r.mes):02d}"
        mensual.setdefault(clave, {})[r.estacion_id] = [round(float(r.media), 1),
                                                        int(r.dias)]

    payload = {
        "generado": __import__("datetime").datetime.now(
            __import__("datetime").UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "fuente": "SINCA — red nacional, serie diaria de MP2.5 agregada a mes",
        "min_dias_mes": MIN_DIAS_MES,
        "conteos": {"estaciones": len(estaciones), "meses": len(mensual),
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
    return 1 if (sueltas or fuera) else 0


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
