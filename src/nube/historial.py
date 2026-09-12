"""Extrae de Athena el historial de consultas que construyó la base.

Para qué
--------
El informe final tiene que anexar el DDL real con el que se crearon la base de
datos y sus tablas. Escribirlo a mano sería transcribirlo, y un DDL transcrito no
se puede auditar: hay que compararlo a ojo contra la consola. Este módulo lo baja
del historial de Athena, que es la única fuente que sabe qué se ejecutó de verdad.

Qué escribe
-----------
`docs/informe/anexos/athena_ddl.md`, con el DDL vigente de cada tabla —la última
ejecución con éxito, que es la que manda— en orden cronológico y agrupado por
capa.

Qué NO hace
-----------
No ejecuta nada sobre la base. `list_query_executions` y `get_tables` son
lecturas; el módulo no crea, no borra y no consulta datos.

Las tres capas
--------------
El proyecto no bautizó sus tablas con la nomenclatura medallion, pero la
estructura es esa y el informe la nombra así:

    Bronce   data/raw/ — archivos tal como los entregó cada organismo.
             No pasa por Athena.
    Plata    el modelo en estrella sobre S3, catalogado en Glue: los dos hechos,
             las dimensiones, el denominador de población y la vigilancia viral
             (esta última reservada: se cuenta pero su DDL no se anexa).
    Oro      las tablas analíticas que cruzan lo anterior y ya están recortadas
             a las tres ciudades.

Uso
---
    python -m src.nube.historial ddl        # escribe el anexo
    python -m src.nube.historial tablas     # qué hay hoy en Glue
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.rutas import DOCS, LOGS, asegurar  # noqa: E402

log = logging.getLogger(__name__)

BASE = "aire_urgencias"
PERFIL = "aire-admin"
REGION = "us-east-1"
GRUPO = "primary"
SALIDA = DOCS / "informe" / "anexos" / "athena_ddl.md"

# Las doce del modelo son PLATA + RESERVADAS + ORO. Las demás que haya en la
# base son restos de CTAS y se marcan como tales en el anexo en vez de esconderse.
PLATA = ["hecho_medicion", "hecho_urgencia", "dim_tiempo", "dim_estacion",
         "dim_ciudad", "dim_causa", "dim_establecimiento",
         "poblacion_comuna_anio", "poblacion_ciudad_anio"]
ORO = ["analitico_ciudad_semana"]

# Del modelo, pero su DDL no se anexa: describe columna por columna una base que
# construyó una integrante del equipo y que ella publica primero en su propio
# repositorio. Se cuentan, no se muestran. Ver docs/privado/LEEME.md.
RESERVADAS = ["isp_virus_dia", "isp_virus_semana"]

ES_DDL = re.compile(r"^\s*(CREATE|DROP|ALTER|MSCK)", re.I)


def sesion(perfil: str):
    try:
        return boto3.Session(profile_name=perfil)
    except Exception as e:  # noqa: BLE001
        raise SystemExit(
            f"No se pudo abrir el perfil {perfil!r} de ~/.aws/credentials: {e}\n"
            "Configúralo con: aws configure --profile aire-admin") from None


def historial(ath) -> list[dict]:
    """Todas las ejecuciones del workgroup, con su SQL y su estado."""
    ids: list[str] = []
    for pagina in ath.get_paginator("list_query_executions").paginate(
            WorkGroup=GRUPO):
        ids += pagina["QueryExecutionIds"]
    consultas: list[dict] = []
    for i in range(0, len(ids), 50):   # el batch admite 50 por llamada
        consultas += ath.batch_get_query_execution(
            QueryExecutionIds=ids[i:i + 50])["QueryExecutions"]
    log.info("historial: %d consultas", len(consultas))
    return consultas


def objeto_de(sql: str) -> str | None:
    """A qué tabla o base se refiere un DDL."""
    m = re.search(r"CREATE\s+(?:EXTERNAL\s+)?TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+"
                  r"[`\"]?(?:(\w+)\.)?(\w+)", sql, re.I)
    if m:
        return m.group(2)
    m = re.search(r"CREATE\s+DATABASE(?:\s+IF\s+NOT\s+EXISTS)?\s+[`\"]?(\w+)",
                  sql, re.I)
    return f"DATABASE {m.group(1)}" if m else None


def vigentes(consultas: list[dict]) -> dict[str, dict]:
    """La última ejecución con éxito de cada objeto: la que manda hoy."""
    salida: dict[str, dict] = {}
    for q in sorted(consultas, key=lambda x: x["Status"]["SubmissionDateTime"]):
        sql = q.get("Query", "")
        if not ES_DDL.match(sql) or q["Status"]["State"] != "SUCCEEDED":
            continue
        if re.match(r"^\s*(DROP|MSCK|ALTER)", sql, re.I):
            continue
        nombre = objeto_de(sql)
        if nombre:
            salida[nombre] = q
    return salida


def formatear(sql: str) -> str:
    """Indenta el DDL para que se lea en el informe sin scroll horizontal."""
    sql = " ".join(sql.split())
    sql = re.sub(r"\(\s*", "(\n    ", sql, count=1)
    sql = re.sub(r",\s*(?=\w)", ",\n    ", sql)
    for palabra in ("PARTITIONED BY", "STORED AS", "ROW FORMAT", "LOCATION",
                    "TBLPROPERTIES", "WITH SERDEPROPERTIES", "OUTPUTFORMAT",
                    "INPUTFORMAT", "AS SELECT", "FROM", "WHERE", "GROUP BY"):
        sql = re.sub(rf"\s+{palabra}\s+", f"\n{palabra} ", sql)
    return sql


def cmd_ddl(args) -> int:
    ses = sesion(args.perfil)
    ath = ses.client("athena", region_name=args.region)
    glue = ses.client("glue", region_name=args.region)

    consultas = historial(ath)
    ddl = vigentes(consultas)

    tablas = []
    for pagina in glue.get_paginator("get_tables").paginate(DatabaseName=BASE):
        tablas += pagina["TableList"]
    nombres = {t["Name"] for t in tablas}
    extras = sorted(nombres - set(PLATA) - set(ORO) - set(RESERVADAS))
    reservadas = [t for t in RESERVADAS if t in nombres]

    lineas = [
        "# Anexo · Historial de Athena: el DDL que construyó la base",
        "",
        f"- **Base de datos:** `{BASE}`  ·  **workgroup:** `{GRUPO}`  "
        f"·  **región:** {args.region}",
        f"- **Extraído de:** el historial de consultas de Athena "
        f"({len(consultas)} ejecuciones registradas)",
        f"- **Generado:** {datetime.now():%Y-%m-%d %H:%M} con "
        "`python -m src.nube.historial ddl`",
        "",
        "De cada objeto se anexa **la última ejecución con éxito**, que es el DDL "
        "vigente. El catálogo se reconstruyó varias veces durante el proyecto; "
        "las versiones intermedias no se incluyen porque ya no describen lo que "
        "hay en la base.",
        "",
        "## Las tres capas",
        "",
        "| Capa | Qué es | Dónde vive |",
        "|---|---|---|",
        "| **Bronce** | Los archivos tal como los entregó cada organismo | "
        "`data/raw/`, inmutable. No pasa por Athena |",
        "| **Plata** | El modelo en estrella: hechos, dimensiones, denominador "
        "y vigilancia viral (reservada) | Parquet en S3, catalogado en Glue |",
        "| **Oro** | La tabla analítica, ya recortada a las tres ciudades | "
        "Parquet en S3, catalogado en Glue |",
        "",
        f"Hoy la base tiene **{len(nombres)} tablas**: las "
        f"{len(PLATA) + len(reservadas) + len(ORO)} del modelo "
        f"({len(PLATA) + len(reservadas)} de plata y {len(ORO)} de oro) y "
        f"{len(extras)} restos de "
        "consultas `CREATE TABLE AS SELECT` que no forman parte del modelo.",
        "",
    ]

    def bloque(titulo: str, claves: list[str], nota: str = "") -> None:
        # extend y no `+=`: el aumento convertiría `lineas` en local del cierre.
        lineas.extend([f"## {titulo}", ""])
        if nota:
            lineas.extend([nota, ""])
        for clave in claves:
            q = ddl.get(clave)
            if not q:
                lineas.extend([f"### `{clave}`", "",
                               "_Sin DDL en el historial: la tabla se creó fuera "
                               "del workgroup o el historial ya la rotó._", ""])
                continue
            fecha = q["Status"]["SubmissionDateTime"]
            datos = q.get("Statistics", {}).get("DataScannedInBytes", 0)
            lineas.extend([
                f"### `{clave}`", "",
                f"Ejecutada el {fecha:%Y-%m-%d %H:%M} · "
                f"{datos / 1024:.0f} kB escaneados", "",
                "```sql", formatear(q["Query"]), "```", ""])

    clave_bd = next((k for k in ddl if k.startswith("DATABASE")), None)
    bloque("La base de datos", [clave_bd] if clave_bd else [],
           "" if clave_bd else
           "_No hay `CREATE DATABASE` en el historial: la base se creó desde la "
           "API de Glue (`src/nube/catalogo.py`), que no pasa por Athena._")
    bloque("Capa plata · el modelo en estrella", PLATA)
    if reservadas:
        lineas.extend([
            "### Vigilancia viral · reservada", "",
            f"{len(reservadas)} tablas de la capa plata con la serie de "
            "vigilancia de virus respiratorios. La base la construyó una "
            "integrante del equipo y se publica primero en su propio "
            "repositorio, así que su DDL no se anexa hasta entonces.", ""])
    bloque("Capa oro · la tabla analítica", ORO)
    if extras:
        bloque("Fuera del modelo", extras,
               "Tablas materializadas con `CREATE TABLE AS SELECT` durante el "
               "análisis. Se dejan registradas por transparencia: **no forman "
               "parte del modelo del proyecto** y su ubicación en S3 es el "
               "directorio de resultados de Athena, no la zona `processed/`.")

    asegurar(SALIDA.parent)
    SALIDA.write_text("\n".join(lineas), encoding="utf-8")
    print(f"Escrito: {SALIDA.relative_to(SALIDA.parents[3])}")
    print(f"  consultas en el historial : {len(consultas)}")
    print(f"  DDL vigente recuperado    : {len(ddl)} objetos")
    print(f"  tablas hoy en {BASE:<14}: {len(nombres)} "
          f"({len(PLATA)} plata + {len(reservadas)} reservadas + {len(ORO)} oro "
          f"+ {len(extras)} fuera del modelo)")
    return 0


def cmd_tablas(args) -> int:
    glue = sesion(args.perfil).client("glue", region_name=args.region)
    tablas = []
    for pagina in glue.get_paginator("get_tables").paginate(DatabaseName=BASE):
        tablas += pagina["TableList"]
    print(f"{BASE}: {len(tablas)} tablas\n")
    for t in sorted(tablas, key=lambda x: x["Name"]):
        capa = ("plata" if t["Name"] in PLATA else
                "plata, reservada" if t["Name"] in RESERVADAS else
                "oro" if t["Name"] in ORO else "fuera del modelo")
        cols = len(t["StorageDescriptor"].get("Columns", []))
        print(f"  {t['Name']:<28} {capa:<16} {cols:>3} columnas  "
              f"{t['CreateTime']:%Y-%m-%d}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for nombre, fn in (("ddl", cmd_ddl), ("tablas", cmd_tablas)):
        s = sub.add_parser(nombre)
        s.add_argument("--perfil", default=PERFIL)
        s.add_argument("--region", default=REGION)
        s.set_defaults(fn=fn)

    args = p.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "historial_athena.log",
                                      encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
