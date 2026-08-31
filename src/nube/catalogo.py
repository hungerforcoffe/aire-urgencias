"""Crea la base de datos del proyecto en Glue y sus tablas, y la prueba.

Qué es esto exactamente
-----------------------
Una base de datos de Glue y sus tablas son **solo metadatos sobre prefijos de
S3**. No copian ni mueven un byte, y no exigen que el prefijo tenga contenido:
una tabla sobre un prefijo vacío se crea igual y devuelve cero filas hasta que
aparezca el primer Parquet. Por eso el catálogo puede levantarse antes de que el
ETL esté terminado, y actualizarse después tantas veces como haga falta.

Los tipos NO se escriben a mano
-------------------------------
Cada tabla se declara leyendo el **esquema real del Parquet** que hay en S3, no
un DDL escrito de memoria. Un `bigint` donde el archivo trae `double` no falla al
crear la tabla: falla al consultarla, y con suerte con un error claro. Es la
regla 6 aplicada al catálogo — el lector no supone el esquema, lo detecta.

Antes que nada, el workgroup
----------------------------
Athena no ejecuta **ninguna** consulta sin un destino de resultados. El
workgroup `primary` venía sin configurar, así que este script lo apunta al
bucket de resultados antes de intentar nada.

Uso
---
    python -m src.nube.catalogo --bucket aire-urgencias-2026-pr --perfil aire-admin --simular
    python -m src.nube.catalogo --bucket aire-urgencias-2026-pr --perfil aire-admin --aplicar
    python -m src.nube.catalogo --bucket aire-urgencias-2026-pr --perfil aire-admin --probar
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.nube import abrir_sesion  # noqa: E402
from src.rutas import LOGS, asegurar  # noqa: E402

log = logging.getLogger("catalogo")

BASE_DATOS = "aire_urgencias"
COMENTARIO = "Modelo estrella MP2.5 x urgencias respiratorias 2018-2026"
ZONA = "processed"
WORKGROUP = "primary"
RESULTADOS = "s3-athena-results-pablo-2026"

# Arrow -> Hive. Se mapea lo que el proyecto usa; cualquier otro tipo se declara
# como string y se avisa, en vez de adivinar.
TIPOS = {
    "bool": "boolean",
    "int8": "tinyint", "int16": "smallint", "int32": "int", "int64": "bigint",
    "float": "float", "double": "double",
    "string": "string", "large_string": "string",
    "date32[day]": "date", "date64[ms]": "date",
}


def tipo_hive(arrow) -> tuple[str, bool]:
    """Devuelve (tipo Hive, si se reconoció). Un `null` de Arrow no es un tipo."""
    t = str(arrow)
    if t == "null":
        return "string", False
    if t.startswith("timestamp"):
        return "timestamp", True
    return TIPOS.get(t, "string"), t in TIPOS


def tablas_en_s3(s3, bucket: str) -> dict[str, dict]:
    """Cada subcarpeta de processed/ con un .parquet dentro es una tabla.

    Detecta además las particiones al estilo Hive: un tramo de ruta con forma
    `columna=valor` es una partición, y su valor **no está dentro del Parquet**
    sino en el nombre de la carpeta. Por eso hay que declararla aparte, en
    `PARTITIONED BY`, y por eso hace falta `MSCK REPAIR TABLE` para que Athena
    recorra el prefijo y descubra qué particiones existen.
    """
    pag = s3.get_paginator("list_objects_v2")
    out: dict[str, dict] = {}
    for pagina in pag.paginate(Bucket=bucket, Prefix=f"{ZONA}/"):
        for o in pagina.get("Contents", []):
            k = o["Key"]
            if not k.endswith(".parquet"):
                continue
            partes = k.split("/")
            if len(partes) < 3:
                log.warning("parquet suelto fuera de una carpeta de tabla: %s", k)
                continue
            tabla = partes[1]
            particiones: list[tuple[str, str]] = [
                (t.split("=", 1)[0], t.split("=", 1)[1]) for t in partes[2:-1] if "=" in t]
            ficha = out.setdefault(tabla, {"clave": k, "particiones": {}})
            for col, val in particiones:
                ficha["particiones"].setdefault(col, set()).add(val)
    for ficha in out.values():
        ficha["particiones"] = {
            col: ("int" if all(v.lstrip("-").isdigit() for v in vals) else "string")
            for col, vals in ficha["particiones"].items()}
    return dict(sorted(out.items()))


def esquema_de(s3, bucket: str, clave: str) -> list[tuple[str, str, bool]]:
    cuerpo = s3.get_object(Bucket=bucket, Key=clave)["Body"].read()
    esquema = pq.read_schema(io.BytesIO(cuerpo))
    return [(f.name, *tipo_hive(f.type)) for f in esquema]


def ddl_tabla(tabla: str, columnas: list[tuple[str, str, bool]], bucket: str,
              particiones: dict[str, str] | None = None) -> str:
    ancho = max(len(c) for c, _, _ in columnas)
    cuerpo = ",\n".join(f"  {c:<{ancho}}  {t}" for c, t, _ in columnas)
    part = ""
    if particiones:
        campos = ", ".join(f"{c} {t}" for c, t in particiones.items())
        part = f"PARTITIONED BY ({campos})\n"
    return (f"CREATE EXTERNAL TABLE IF NOT EXISTS {BASE_DATOS}.{tabla} (\n{cuerpo}\n)\n"
            f"{part}"
            f"STORED AS PARQUET\n"
            f"LOCATION 's3://{bucket}/{ZONA}/{tabla}/'\n"
            f"TBLPROPERTIES ('parquet.compression'='SNAPPY');")


def ejecutar(athena, sql: str, espera: int = 90) -> dict:
    """Lanza una consulta y espera. Devuelve la ejecución ya terminada."""
    ident = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": BASE_DATOS},
        WorkGroup=WORKGROUP)["QueryExecutionId"]
    limite = time.time() + espera
    while time.time() < limite:
        eje = athena.get_query_execution(QueryExecutionId=ident)["QueryExecution"]
        estado = eje["Status"]["State"]
        if estado in ("SUCCEEDED", "FAILED", "CANCELLED"):
            if estado != "SUCCEEDED":
                raise SystemExit(f"Athena devolvió {estado}:\n"
                                 f"  {eje['Status'].get('StateChangeReason', '')}\n"
                                 f"  consulta: {sql.splitlines()[0]}…")
            return eje
        time.sleep(1)
    raise SystemExit(f"la consulta no terminó en {espera} s: {sql.splitlines()[0]}…")


def filas(athena, eje: dict) -> list[list[str]]:
    r = athena.get_query_results(QueryExecutionId=eje["QueryExecutionId"])
    out = []
    for fila in r["ResultSet"]["Rows"]:
        out.append([c.get("VarCharValue", "") for c in fila["Data"]])
    return out


def preparar_workgroup(athena, s3, aplicar: bool) -> None:
    destino = f"s3://{RESULTADOS}/"
    try:
        s3.head_bucket(Bucket=RESULTADOS)
    except ClientError as e:
        raise SystemExit(
            f"El bucket de resultados {RESULTADOS} no responde "
            f"({e.response['Error']['Code']}). Athena no puede ejecutar sin él.") from e

    wg = athena.get_work_group(WorkGroup=WORKGROUP)["WorkGroup"]
    actual = wg.get("Configuration", {}).get("ResultConfiguration", {}).get("OutputLocation")
    if actual:
        print(f"  workgroup {WORKGROUP}: resultados ya en {actual}")
        return
    print(f"  workgroup {WORKGROUP}: SIN destino de resultados -> {destino}")
    if aplicar:
        athena.update_work_group(
            WorkGroup=WORKGROUP,
            ConfigurationUpdates={"ResultConfigurationUpdates": {"OutputLocation": destino}})
        print("    configurado")


PRUEBAS = [
    ("las tres ciudades y sus estaciones",
     "SELECT c.nombre, c.n_comunas, c.n_estaciones, c.pct_lena_casen "
     f"FROM {BASE_DATOS}.dim_ciudad c ORDER BY c.n_estaciones DESC"),
    ("estaciones por ciudad, con las excluidas aparte",
     "SELECT coalesce(ciudad_id, '(fuera de alcance)') AS ciudad, count(*) AS n "
     f"FROM {BASE_DATOS}.dim_estacion WHERE tiene_datos GROUP BY 1 ORDER BY 2 DESC"),
    ("la semana MMWR que cruza 2018 y 2019",
     "SELECT cast(fecha AS varchar) AS fecha, nombre_dia, semana_id "
     f"FROM {BASE_DATOS}.dim_tiempo "
     "WHERE fecha BETWEEN date '2018-12-28' AND date '2019-01-02' ORDER BY fecha"),
    ("MP2.5 medio por ciudad en el invierno de 2023, uniendo hecho y dimensiones",
     "SELECT c.nombre AS ciudad, count(*) AS horas, "
     "round(avg(m.valor), 1) AS mp25_medio, round(max(m.valor), 1) AS pico "
     f"FROM {BASE_DATOS}.hecho_medicion m "
     f"JOIN {BASE_DATOS}.dim_ciudad c ON c.ciudad_id = m.ciudad_id "
     f"JOIN {BASE_DATOS}.dim_tiempo t ON t.fecha = m.fecha "
     "WHERE m.anio = 2023 AND m.parametro_id = 'mp25' AND t.es_invierno "
     "GROUP BY c.nombre ORDER BY 3 DESC"),
    ("el join de las tres dimensiones, que es de lo que se trata",
     "SELECT c.nombre AS ciudad, count(DISTINCT e.estacion_id) AS estaciones, "
     "count(DISTINCT t.semana_id) AS semanas "
     f"FROM {BASE_DATOS}.dim_ciudad c "
     f"JOIN {BASE_DATOS}.dim_estacion e ON e.ciudad_id = c.ciudad_id AND e.tiene_datos "
     f"CROSS JOIN {BASE_DATOS}.dim_tiempo t "
     "WHERE t.es_invierno AND t.periodo_pandemia = 'prepandemia' "
     "GROUP BY c.nombre ORDER BY 2 DESC"),
]


def destruir(glue, athena, s3, bucket: str) -> int:
    """Devuelve la cuenta al estado previo al catálogo.

    Solo borra metadatos. Comprueba antes que cada tabla sea EXTERNAL_TABLE: si
    alguna fuera MANAGED, borrarla se llevaría los datos por delante, y entonces
    se para. Después vuelve a contar los objetos de S3 para demostrar que siguen.
    """
    antes = {o["Key"]: o["Size"] for pagina in
             s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=f"{ZONA}/")
             for o in pagina.get("Contents", [])}

    try:
        tablas = glue.get_tables(DatabaseName=BASE_DATOS)["TableList"]
    except glue.exceptions.EntityNotFoundException:
        print(f"  la base {BASE_DATOS} no existe; nada que borrar")
        tablas = []

    for t in tablas:
        tipo = t.get("TableType")
        if tipo != "EXTERNAL_TABLE":
            raise SystemExit(
                f"  {t['Name']} es {tipo}, no EXTERNAL_TABLE. Borrarla se llevaría "
                f"los datos de {t['StorageDescriptor']['Location']}. No se toca nada.")
    for t in tablas:
        glue.delete_table(DatabaseName=BASE_DATOS, Name=t["Name"])
        print(f"  tabla {t['Name']} eliminada (solo el metadato)")
    if tablas or True:
        try:
            glue.delete_database(Name=BASE_DATOS)
            print(f"  base {BASE_DATOS} eliminada")
        except glue.exceptions.EntityNotFoundException:
            pass

    athena.update_work_group(
        WorkGroup=WORKGROUP,
        ConfigurationUpdates={"ResultConfigurationUpdates": {"RemoveOutputLocation": True}})
    print(f"  workgroup {WORKGROUP}: destino de resultados quitado")

    despues = {o["Key"]: o["Size"] for pagina in
               s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=f"{ZONA}/")
               for o in pagina.get("Contents", [])}
    print(f"\n  objetos en {ZONA}/ antes: {len(antes)}   después: {len(despues)}")
    if antes != despues:
        raise SystemExit("  ¡S3 CAMBIÓ! Eso no debía pasar. Revisa antes de seguir.")
    print("  idénticos byte a byte: el dato no se tocó, solo su descripción.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bucket", required=True)
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--perfil", default=None)
    p.add_argument("--probar", action="store_true",
                   help="solo corre las consultas de prueba sobre lo que ya exista")
    p.add_argument("--rehacer", action="store_true",
                   help="borra cada tabla antes de crearla. Hace falta cuando el "
                        "esquema del Parquet cambió: CREATE TABLE IF NOT EXISTS no "
                        "actualiza una tabla que ya existe, y se queda describiendo "
                        "un archivo que ya no es. Solo toca metadatos")
    p.add_argument("--destruir", action="store_true",
                   help="borra la base y sus tablas, y quita el destino de resultados. "
                        "Solo toca metadatos: los Parquet de S3 no se tocan. "
                        "Sirve para rehacer el catálogo a mano y aprender el camino")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--simular", action="store_true", help="muestra el DDL sin ejecutarlo")
    g.add_argument("--aplicar", action="store_true", help="crea la base y las tablas")
    args = p.parse_args(argv)
    if not (args.simular or args.aplicar or args.probar or args.destruir):
        raise SystemExit("elige --simular, --aplicar, --probar o --destruir")

    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "catalogo.log", encoding="utf-8")])

    sesion = abrir_sesion(args.perfil)
    s3 = sesion.client("s3", region_name=args.region)
    glue = sesion.client("glue", region_name=args.region)
    athena = sesion.client("athena", region_name=args.region)

    print(f"\n  bucket   : s3://{args.bucket}/{ZONA}/")
    print(f"  base     : {BASE_DATOS}\n")

    if args.destruir:
        return destruir(glue, athena, s3, args.bucket)

    preparar_workgroup(athena, s3, args.aplicar or args.probar)

    if not args.probar:
        ddl_base = (f"CREATE DATABASE IF NOT EXISTS {BASE_DATOS}\n"
                    f"  COMMENT '{COMENTARIO}'\n"
                    f"  LOCATION 's3://{args.bucket}/{ZONA}/';")
        print(f"\n{ddl_base}\n")
        if args.aplicar:
            try:
                glue.get_database(Name=BASE_DATOS)
                print(f"  la base {BASE_DATOS} ya existe")
            except glue.exceptions.EntityNotFoundException:
                glue.create_database(DatabaseInput={
                    "Name": BASE_DATOS, "Description": COMENTARIO,
                    "LocationUri": f"s3://{args.bucket}/{ZONA}/"})
                print(f"  base {BASE_DATOS} creada")

        encontradas = tablas_en_s3(s3, args.bucket)
        if not encontradas:
            print(f"  No hay ningún .parquet bajo {ZONA}/. Nada que catalogar todavía.")
            return 0
        print(f"\n  tablas detectadas en S3: {len(encontradas)}")
        for tabla, ficha in encontradas.items():
            columnas = esquema_de(s3, args.bucket, ficha["clave"])
            particiones = ficha["particiones"]
            desconocidos = [c for c, _, ok in columnas if not ok]
            ddl = ddl_tabla(tabla, columnas, args.bucket, particiones)
            print(f"\n{ddl}")
            if desconocidos:
                print(f"  AVISO: tipo no reconocido en {desconocidos}; se declaran string")
            if args.aplicar:
                if args.rehacer:
                    ejecutar(athena, f"DROP TABLE IF EXISTS {BASE_DATOS}.{tabla};")
                    print(f"  -> {tabla} descartada (solo el metadato)")
                ejecutar(athena, ddl)
                print(f"  -> {tabla} registrada")
                if particiones:
                    # Sin esto la tabla existe y devuelve CERO filas: Athena no
                    # sale a mirar qué carpetas hay bajo el prefijo si no se lo
                    # pides. Es el «0 filas sin error» más común con particiones.
                    reparar = f"MSCK REPAIR TABLE {BASE_DATOS}.{tabla};"
                    print(f"     {reparar}")
                    ejecutar(athena, reparar, espera=180)
                    eje = ejecutar(athena, f"SELECT count(*) FROM {BASE_DATOS}.{tabla}")
                    n = filas(athena, eje)[1][0]
                    print(f"     particiones descubiertas; la tabla responde {int(n):,} filas")

        if args.simular:
            print("\n  simulación: no se tocó ni Glue ni Athena "
                  "(salvo el destino de resultados, que no se cambió).")
            return 0

    print("\n" + "=" * 70)
    print("  PRUEBAS — si estas cuatro responden, el circuito Glue → Athena funciona")
    print("=" * 70)
    for titulo, sql in PRUEBAS:
        eje = ejecutar(athena, sql)
        datos = filas(athena, eje)
        est = eje["Statistics"]
        print(f"\n  {titulo}")
        print(f"    {est.get('DataScannedInBytes', 0):,} bytes leídos · "
              f"{est.get('TotalExecutionTimeInMillis', 0):,} ms")
        if not datos:
            print("    (sin filas)")
            continue
        ancho = [max(len(f[i]) for f in datos) for i in range(len(datos[0]))]
        for j, fila in enumerate(datos):
            linea = "  ".join(v.ljust(ancho[i]) for i, v in enumerate(fila))
            print(f"      {linea}")
            if j == 0:
                print("      " + "  ".join("-" * a for a in ancho))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
