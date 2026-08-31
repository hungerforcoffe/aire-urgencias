"""Lee los 81 CSV de SINCA y escribe `hecho_medicion` en Parquet.

Lo que este lector NO hace
--------------------------
No supone el esquema. Cada archivo se clasifica leyendo dos señales
independientes —el nombre y la cabecera— y **se rechaza si discrepan**. De los
81 archivos, 62 traen cabecera `FECHA;HORA;;` y son meteorología; 19 traen
`FECHA;HORA;validados;preliminares;no validados` y son MP2.5. La
correspondencia es perfecta, así que dejó de ser un detector y pasó a ser un
chequeo cruzado: si un archivo dice «MP2.5» en el nombre y llega con cabecera de
meteorología, algo se descargó mal.

Las cinco validaciones (regla 5)
--------------------------------
1. tamaño > 0
2. la cabecera es una de las dos variantes conocidas
3. nombre y cabecera coinciden
4. **la primera columna parsea como fecha `YYMMDD`**
5. filas utilizables > 0

La cuarta es la que atrapa el archivo de rosa de vientos de Nueva Libertad: 399
bytes, extensión correcta, cabecera correcta, y dentro los 16 sectores de
dirección con su frecuencia (`352,5-7,5` → `4,8%`). Pasa las validaciones
baratas y no es una serie temporal. Con la cuarta se rechaza solo.

Decisiones que aplica, todas documentadas en docs/calidad/
----------------------------------------------------------
* **Los tres estados de validación cuentan como dato válido.** Sin filtro. La
  columna `estado_validacion` conserva el valor real, que es lo que mantiene la
  decisión reversible. Ver `estados_validacion_sinca.md`.
* **La dirección del viento es circular.** Se normaliza módulo 360 (el `360`
  que aparece en los datos es el mismo norte que el `0`), y el par
  `(dirección = 0, velocidad = 0.1)` se marca como sin dato: son 222 horas de
  Consultorio San Vicente donde ese par aparece con coincidencia perfecta desde
  mayo de 2024, y no es meteorología. Ver `direccion_viento_circular.md`.
* **Talagante no pertenece a Santiago.** Sus mediciones se cargan igual, con
  `ciudad_id` nulo. Ver `definicion_ciudades.md`.

Uso
---
    python -m src.procesamiento.sinca inventario --bucket <bucket> --perfil <perfil>
    python -m src.procesamiento.sinca construir  --bucket <bucket> --perfil <perfil>
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.procesamiento.tiempo import FIN, INICIO  # noqa: E402
from src.rutas import LOGS, PROCESSED, asegurar  # noqa: E402

log = logging.getLogger("sinca")

# id -> (nombre, unidad, es_circular, deberia_tener_validacion)
PARAMETROS = {
    "mp25":        ("Material particulado MP2,5", "ug/m3", False, True),
    "temperatura": ("Temperatura ambiente", "C", False, False),
    "humedad":     ("Humedad relativa del aire", "%", False, False),
    "vel_viento":  ("Velocidad del viento", "m/s", False, False),
    "dir_viento":  ("Dirección del viento", "grados", True, False),
}

# Orden de lectura: la velocidad ANTES que la dirección, para cada estación.
# El centinela de dirección se decide mirando la velocidad de la misma hora, así
# que cuando toca leer la dirección la velocidad ya tiene que estar leída.
ORDEN = {"vel_viento": 0, "dir_viento": 1}

CAB_V1 = "meteorologia"
CAB_V2 = "mp25"

VELOCIDAD_CENTINELA = 0.1        # el valor exacto que acompaña a dirección = 0
TOLERANCIA_GRADOS = 1.0          # 360.001 es ruido de coma flotante, no un error


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def detectar_parametro(nombre_archivo: str) -> str | None:
    """Deduce el parámetro del nombre del archivo.

    Hay 24 grafías distintas para cinco parámetros: `MP2.5`, `MP2.5 - Horario`,
    `Material_particulado_MP_2,5_horario`, `Dirección_del_viento_10m`… Se
    normaliza y se busca por palabra clave, no por igualdad.
    """
    n = _norm(nombre_archivo)
    if "mp2 5" in n or "mp25" in n or "material particulado" in n:
        return "mp25"
    if "direccion" in n:
        return "dir_viento"
    if "velocidad" in n:
        return "vel_viento"
    if "humedad" in n:
        return "humedad"
    if "temperatura" in n:
        return "temperatura"
    return None


def detectar_variante(cabecera: str) -> str | None:
    campos = [c.strip().lower() for c in cabecera.split(";")]
    if len(campos) < 3 or not campos[0].startswith("fecha"):
        return None
    con_nombre = [c for c in campos[2:] if c]
    if not con_nombre:
        return CAB_V1
    if any("valid" in c for c in con_nombre):
        return CAB_V2
    return None


def _num(txt: str) -> float | None:
    try:
        return float(txt.replace(",", "."))
    except ValueError:
        return None


class Rechazo(Exception):
    """El archivo no pasa alguna de las cinco validaciones."""


def parsear(datos: bytes, nombre: str) -> tuple[list[tuple], dict]:
    """Devuelve (filas, informe). Lanza Rechazo si el archivo no sirve.

    Cada fila es (fecha, hora, valor, estado). El recorte a la ventana del
    estudio ocurre aquí: fuera de 2018-2026 no se carga nada.
    """
    if not datos:
        raise Rechazo("archivo vacío (0 bytes)")

    param = detectar_parametro(nombre)
    if param is None:
        raise Rechazo(f"el nombre no dice qué parámetro es: {nombre}")

    texto = datos.decode("latin-1")
    lineas = texto.splitlines()
    if not lineas:
        raise Rechazo("sin líneas")

    variante = detectar_variante(lineas[0])
    if variante is None:
        raise Rechazo(f"cabecera desconocida: {lineas[0][:70]!r}")

    esperada = CAB_V2 if PARAMETROS[param][3] else CAB_V1
    if variante != esperada:
        raise Rechazo(
            f"el nombre dice «{param}» (cabecera {esperada}) y el archivo trae "
            f"cabecera {variante}. Nombre y contenido no concuerdan: se descarta "
            f"en vez de elegir a cuál creerle")

    estados = ("validado", "preliminar", "no_validado")
    filas: list[tuple] = []
    sin_fecha = fuera_ventana = sin_valor = 0
    for ln in lineas[1:]:
        if not ln.strip():
            continue
        p = ln.split(";")
        cruda = p[0].strip()
        if len(cruda) != 6 or not cruda.isdigit():
            sin_fecha += 1
            continue
        try:
            f = dt.date(2000 + int(cruda[:2]), int(cruda[2:4]), int(cruda[4:6]))
        except ValueError:
            sin_fecha += 1
            continue
        if not (INICIO <= f <= FIN):
            fuera_ventana += 1
            continue
        hhmm = p[1].strip() if len(p) > 1 else ""
        if len(hhmm) != 4 or not hhmm.isdigit():
            sin_fecha += 1
            continue
        hora = int(hhmm[:2])

        celdas = [(p[i].strip() if len(p) > i else "") for i in (2, 3, 4)]
        llenas = [(i, c) for i, c in enumerate(celdas) if c]
        if not llenas:
            sin_valor += 1
            continue
        if len(llenas) > 1:
            raise Rechazo(f"fila con {len(llenas)} valores a la vez; las columnas "
                          f"de validación deberían ser excluyentes: {ln[:70]!r}")
        col, cru = llenas[0]
        v = _num(cru)
        if v is None:
            sin_valor += 1
            continue
        estado = estados[col] if variante == CAB_V2 else "sin_estado"
        filas.append((f, hora, v, estado))

    # La cuarta validación se evalúa aquí: si NINGUNA línea dio una fecha
    # utilizable, no es un archivo vacío, es un archivo que no es una serie.
    if not filas and sin_fecha:
        raise Rechazo(f"ninguna de sus {sin_fecha} líneas empieza por una fecha "
                      f"YYMMDD: no es una serie temporal")
    if not filas:
        raise Rechazo("0 filas dentro de la ventana del estudio")

    return filas, {"parametro": param, "variante": variante,
                   "sin_fecha": sin_fecha, "fuera_ventana": fuera_ventana,
                   "sin_valor": sin_valor}


def normalizar_direccion(v: float) -> float | None:
    """Grados a [0, 360). El 360 de los datos es el mismo norte que el 0."""
    if v < -TOLERANCIA_GRADOS or v > 360 + TOLERANCIA_GRADOS:
        return None
    return v % 360.0


def _claves(s3, bucket: str) -> list[str]:
    pag = s3.get_paginator("list_objects_v2")
    return sorted(o["Key"] for pagina in pag.paginate(Bucket=bucket, Prefix="raw/")
                  for o in pagina.get("Contents", [])
                  if "/SINCA/" in o["Key"] and o["Key"].lower().endswith(".csv"))


def _estacion_de(nombre: str) -> str:
    return nombre.split("_")[0] if "_" in nombre else nombre.split(" - ")[0]


def _dim_estacion():
    import pandas as pd
    ruta = PROCESSED / "dim_estacion" / "dim_estacion.parquet"
    if not ruta.exists():
        raise SystemExit(f"Falta {ruta}. Corre antes «estaciones construir».")
    df = pd.read_parquet(ruta)
    # `ciudad_id` es nulo en las estaciones fuera de alcance, y pandas lo
    # devuelve como NaN, que es un float. Sin convertirlo a None, pyarrow falla
    # al construir una columna de texto — con un error que no menciona la causa.
    df = df.astype(object).where(pd.notna(df), None)
    return {r["clave_cruce"]: r for _, r in df.iterrows()}


def cmd_inventario(args) -> int:
    from src.nube import abrir_sesion
    s3 = abrir_sesion(args.perfil).client("s3", region_name=args.region)
    claves = _claves(s3, args.bucket)
    dim = _dim_estacion()
    from src.procesamiento.geografia import normalizar_nombre

    print(f"  {len(claves)} archivos\n")
    print(f"  {'archivo':<58}{'parám.':<13}{'estación en dim_estacion'}")
    sin_dim, sin_param = [], []
    for k in claves:
        n = k.split("/")[-1]
        p = detectar_parametro(n)
        clave = normalizar_nombre(_estacion_de(n))
        fila = dim.get(clave)
        if p is None:
            sin_param.append(n)
        if fila is None:
            sin_dim.append(n)
        cruce = ("NO CRUZA" if fila is None
                 else f"{fila['estacion_id']} {fila['ciudad_id']}")
        print(f"  {n[:56]:<58}{p or '???':<13}{cruce}")
    print(f"\n  sin parámetro reconocido : {len(sin_param)}")
    print(f"  sin estación en la dim   : {len(sin_dim)}")
    for n in sin_dim:
        print(f"    · {n}")
    return 1 if (sin_dim or sin_param) else 0


def cmd_construir(args) -> int:
    import pyarrow as pa
    import pyarrow.parquet as pq

    from src.nube import abrir_sesion
    from src.procesamiento.geografia import normalizar_nombre

    s3 = abrir_sesion(args.perfil).client("s3", region_name=args.region)
    dim = _dim_estacion()
    claves = _claves(s3, args.bucket)

    # Velocidad antes que dirección, por estación (ver ORDEN).
    def orden(k: str) -> tuple:
        n = k.split("/")[-1]
        return (normalizar_nombre(_estacion_de(n)),
                ORDEN.get(detectar_parametro(n) or "", 2), n)
    claves.sort(key=orden)

    lotes: list[pa.RecordBatch] = []
    vel_centinela: dict[int, set] = defaultdict(set)
    rechazados: list[tuple[str, str]] = []
    resumen: list[dict] = []
    n_centinela = n_fuera_rango = 0

    for k in claves:
        nombre = k.split("/")[-1]
        clave = normalizar_nombre(_estacion_de(nombre))
        fila = dim.get(clave)
        if fila is None:
            rechazados.append((nombre, "la estación no está en dim_estacion"))
            continue
        datos = s3.get_object(Bucket=args.bucket, Key=k)["Body"].read()
        try:
            filas, inf = parsear(datos, nombre)
        except Rechazo as e:
            rechazados.append((nombre, str(e)))
            log.warning("rechazado %s: %s", nombre, e)
            continue

        est = int(fila["estacion_id"])
        ciudad = fila["ciudad_id"]
        param = inf["parametro"]

        if param == "vel_viento":
            for f, h, v, _ in filas:
                if v == VELOCIDAD_CENTINELA:
                    vel_centinela[est].add((f, h))

        fechas, horas, valores, estados = [], [], [], []
        for f, h, v, e in filas:
            if param == "dir_viento":
                if v == 0.0 and (f, h) in vel_centinela[est]:
                    n_centinela += 1
                    continue                    # centinela: no es una medición
                v = normalizar_direccion(v)
                if v is None:
                    n_fuera_rango += 1
                    continue
            fechas.append(f)
            horas.append(h)
            valores.append(v)
            estados.append(e)

        if not fechas:
            rechazados.append((nombre, "todas sus filas se descartaron al limpiar"))
            continue

        lotes.append(pa.RecordBatch.from_arrays([
            pa.array([est] * len(fechas), pa.int32()),
            pa.array([ciudad] * len(fechas), pa.string()),
            pa.array(fechas, pa.date32()),
            pa.array(horas, pa.int8()),
            pa.array([param] * len(fechas), pa.string()),
            pa.array(valores, pa.float64()),
            pa.array(estados, pa.string()),
            pa.array([f.year for f in fechas], pa.int16()),
        ], names=["estacion_id", "ciudad_id", "fecha", "hora",
                  "parametro_id", "valor", "estado_validacion", "anio"]))
        resumen.append({"archivo": nombre, "estacion_id": est, "parametro": param,
                        "filas": len(fechas), "desde": min(fechas), "hasta": max(fechas)})
        log.info("%s -> %d filas", nombre, len(fechas))

    if not lotes:
        raise SystemExit("no se pudo leer ningún archivo")

    tabla = pa.Table.from_batches(lotes)
    destino = PROCESSED / "hecho_medicion"
    asegurar(destino)
    pq.write_to_dataset(tabla, root_path=str(destino), partition_cols=["anio"],
                        compression="snappy", existing_data_behavior="delete_matching")

    print(f"\n  archivos leídos   : {len(resumen)} de {len(claves)}")
    print(f"  filas escritas    : {tabla.num_rows:,}")
    print(f"  particiones       : {len(set(tabla.column('anio').to_pylist()))} años")
    print(f"  centinelas de dirección descartados : {n_centinela}")
    print(f"  direcciones fuera de rango          : {n_fuera_rango}")
    print(f"  destino           : {destino.relative_to(PROCESSED.parent.parent)}")

    if rechazados:
        print(f"\n  RECHAZADOS ({len(rechazados)}):")
        for nombre, motivo in rechazados:
            print(f"    · {nombre[:58]}")
            print(f"        {motivo}")

    print("\n  filas por parámetro:")
    from collections import Counter
    c = Counter(tabla.column("parametro_id").to_pylist())
    for p, n in c.most_common():
        print(f"    {p:<14}{n:>12,}")
    print("\n  filas por estado de validación (los tres cuentan como dato):")
    for e, n in Counter(tabla.column("estado_validacion").to_pylist()).most_common():
        print(f"    {e:<14}{n:>12,}")
    return 0


def cmd_cobertura(args) -> int:
    """Rellena en `dim_estacion` las columnas que solo el lector puede saber.

    Se calculan sobre MP2.5, que es la variable de exposición del estudio: de
    nada sirve una estación con ocho años de temperatura si no midió aire.
    """
    import pandas as pd

    horas_ventana = (FIN - INICIO).days * 24 + 24
    hecho = PROCESSED / "hecho_medicion"
    if not hecho.exists():
        raise SystemExit(f"Falta {hecho}. Corre antes «sinca construir».")
    df = pd.read_parquet(hecho, columns=["estacion_id", "fecha", "hora",
                                         "parametro_id", "estado_validacion"])
    print(f"  hecho_medicion : {len(df):,} filas leídas")

    aire = df[df.parametro_id == "mp25"]
    g = aire.groupby("estacion_id")
    cob = pd.DataFrame({
        "primer_dato": g.fecha.min(),
        "ultimo_dato": g.fecha.max(),
        "horas_ventana": g.size(),
        "horas_validadas_ventana": aire[aire.estado_validacion == "validado"]
                                   .groupby("estacion_id").size(),
    }).fillna({"horas_validadas_ventana": 0})
    cob["horas_validadas_ventana"] = cob["horas_validadas_ventana"].astype("int64")
    cob["pct_validado"] = (100 * cob.horas_validadas_ventana / cob.horas_ventana).round(1)
    cob["cobertura_pct"] = (100 * cob.horas_ventana / horas_ventana).round(1)

    ruta = PROCESSED / "dim_estacion" / "dim_estacion.parquet"
    dim = pd.read_parquet(ruta)
    for c in cob.columns:
        if c in dim.columns:
            dim = dim.drop(columns=c)
    dim = dim.merge(cob, left_on="estacion_id", right_index=True, how="left")
    for c in ("horas_ventana", "horas_validadas_ventana"):
        dim[c] = dim[c].astype("Int64")
    dim.to_parquet(ruta, index=False)

    print(f"  dim_estacion   : {len(dim)} filas, {len(dim.columns)} columnas\n")
    ver = dim[dim.horas_ventana.notna()].sort_values("cobertura_pct", ascending=False)
    print(f"  {'estación':<34}{'ciudad':<12}{'horas':>8}{'cob.%':>8}{'valid.%':>9}")
    for _, r in ver.iterrows():
        print(f"  {r.nombre_sinca[:32]:<34}{str(r.ciudad_id)[:10]:<12}"
              f"{int(r.horas_ventana):>8,}{r.cobertura_pct:>8.1f}{r.pct_validado:>9.1f}")
    sin = dim[dim.horas_ventana.isna()]
    print(f"\n  sin MP2.5 en la ventana: {len(sin)}")
    for _, r in sin.iterrows():
        print(f"    · {r.estacion_id} {r.nombre_sinca} ({r.comuna})")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for nombre, fn in (("inventario", cmd_inventario), ("construir", cmd_construir)):
        s = sub.add_parser(nombre)
        s.add_argument("--bucket", required=True)
        s.add_argument("--region", default="us-east-1")
        s.add_argument("--perfil", default=None)
        s.set_defaults(fn=fn)
    # No necesita S3: trabaja sobre el Parquet ya escrito en local.
    sub.add_parser("cobertura").set_defaults(fn=cmd_cobertura)

    args = p.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "sinca.log", encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
