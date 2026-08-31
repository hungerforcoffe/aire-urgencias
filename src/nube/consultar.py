"""Conexión a la base de datos del proyecto. Sin descargar nada.

Athena es la base de datos: el catálogo de Glue guarda dónde está cada tabla y
qué columnas tiene, y Athena lee los Parquet directamente desde S3. Los datos
nunca se copian a ninguna parte — se consultan donde están.

Esto es lo que hace innecesario que cada integrante sincronice `data/processed/`.
Se conecta, se consulta, y vuelve un DataFrame de pandas.

Uso desde Python
----------------
    from src.nube.consultar import consultar

    df = consultar("SELECT * FROM dim_ciudad")
    df = consultar("SELECT ciudad_id, COUNT(*) FROM hecho_medicion "
                   "WHERE anio = 2024 GROUP BY ciudad_id")

Uso desde la terminal
---------------------
    python -m src.nube.consultar tablas
    python -m src.nube.consultar sql "SELECT * FROM dim_ciudad"
    python -m src.nube.consultar sql "SELECT ..." --guardar salida.csv

Credenciales
------------
No hay ninguna clave en este archivo. Se leen del perfil de AWS del equipo
(`~/.aws/credentials`), que cada integrante configura una vez con
`aws configure --profile aire-admin`. Nunca en el código ni en un notebook.

Cuánto cuesta
-------------
Athena cobra por byte escaneado: 5 USD por TB. Una consulta que cruza las siete
tablas escanea ~114 MB, o sea 0,0006 USD. Pero `SELECT *` sobre `hecho_urgencia`
sin filtro escanea los 187 MB completos y no sirve de nada: **filtrar por `anio`
usa la partición y evita leer los años que no se piden.**
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

BASE = "aire_urgencias"
PERFIL = "aire-admin"
REGION = "us-east-1"
# Athena deja el resultado de cada consulta en S3 antes de devolverlo. Es un
# requisito del servicio, no una decisión del proyecto.
RESULTADOS = "s3://s3-athena-results-pablo-2026/"


def conectar(perfil: str = PERFIL, region: str = REGION):
    """Conexión DB-API 2.0 a Athena.

    Sirve para cualquier herramienta que hable DB-API: pandas, SQLAlchemy, o un
    cursor a mano. No descarga datos: la consulta corre en AWS y baja el
    resultado.
    """
    from pyathena import connect

    return connect(profile_name=perfil, region_name=region,
                   s3_staging_dir=RESULTADOS, schema_name=BASE)


def consultar(sql: str, perfil: str = PERFIL) -> pd.DataFrame:
    """Corre una consulta y devuelve un DataFrame.

    El esquema por defecto es `aire_urgencias`, así que las tablas se nombran
    sueltas: `FROM dim_ciudad`, no `FROM aire_urgencias.dim_ciudad`.
    """
    with conectar(perfil) as cx:
        return pd.read_sql_query(sql, cx)


def cmd_tablas(args) -> int:
    """Qué hay en la base, leído del catálogo y no de una lista escrita a mano."""
    from src.nube import abrir_sesion

    glue = abrir_sesion(args.perfil).client("glue", region_name=args.region)
    tablas = glue.get_tables(DatabaseName=BASE)["TableList"]
    print(f"\n  base de datos: {BASE}   ({len(tablas)} tablas)\n")
    for t in sorted(tablas, key=lambda x: x["Name"]):
        cols = t["StorageDescriptor"]["Columns"]
        part = [p["Name"] for p in t.get("PartitionKeys", [])]
        extra = f"  particionada por {', '.join(part)}" if part else ""
        print(f"  {t['Name']:<26} {len(cols):>2} columnas{extra}")
        if args.columnas:
            for c in cols:
                print(f"       {c['Name']:<24} {c['Type']}")
            for p in t.get("PartitionKeys", []):
                print(f"       {p['Name']:<24} {p['Type']}  (partición)")
            print()
    if not args.columnas:
        print("\n  para ver las columnas:  ... tablas --columnas")
    return 0


def cmd_sql(args) -> int:
    df = consultar(args.sql, args.perfil)
    print(f"\n  {len(df):,} filas · {len(df.columns)} columnas\n")
    with pd.option_context("display.width", 200, "display.max_columns", 40):
        print(df.head(args.limite).to_string(index=False))
    if len(df) > args.limite:
        print(f"\n  ... {len(df) - args.limite:,} filas más")
    if args.guardar:
        destino = Path(args.guardar)
        if destino.suffix == ".parquet":
            df.to_parquet(destino, index=False)
        else:
            df.to_csv(destino, index=False, encoding="utf-8")
        print(f"\n  guardado en {destino}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--perfil", default=PERFIL)
    p.add_argument("--region", default=REGION)
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("tablas", help="qué tablas y columnas tiene la base")
    t.add_argument("--columnas", action="store_true")
    t.set_defaults(fn=cmd_tablas)

    s = sub.add_parser("sql", help="correr una consulta")
    s.add_argument("sql")
    s.add_argument("--limite", type=int, default=25)
    s.add_argument("--guardar", help="ruta .csv o .parquet donde dejar el resultado")
    s.set_defaults(fn=cmd_sql)

    args = p.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
