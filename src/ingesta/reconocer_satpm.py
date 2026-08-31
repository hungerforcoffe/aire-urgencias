"""Reconocimiento de SatPM2.5 (ACAG, Washington University) en S3.

Estimación de MP2.5 en superficie a partir de profundidad óptica de aerosoles
(MODIS, MISR, SeaWiFS, VIIRS) combinada con GEOS-Chem y calibrada con una red
neuronal convolucional contra monitores en tierra.

Su papel en este proyecto es ESPACIAL, no temporal: la resolución es mensual y
no sirve como variable de exposición de un análisis con rezagos de 0 a 2
semanas. Sirve para caracterizar la distribución de MP2.5 alrededor de cada
ciudad, evaluar si una estación es representativa de su comuna, y posicionar a
Chile frente al mundo. La exposición temporal sigue siendo SINCA.

Bucket público, sin credenciales: se usa firma UNSIGNED.

Subcomandos
-----------
    acceso      ¿responde el bucket sin credenciales? distingue 403 de vacío
    particion   cómo está organizado el árbol de prefijos
    contar      archivos y bytes por región/frecuencia; aísla los `._` inválidos
    paises      MP2.5 ponderado por población, 246 países (marco internacional)
    descargar   baja un mes a data/raw/ con cadena de validación
    ciudades    extrae las tres ciudades de un .nc ya descargado

Uso
---
    python -m src.ingesta.reconocer_satpm acceso
    python -m src.ingesta.reconocer_satpm contar --region SA --frecuencia Monthly
    python -m src.ingesta.reconocer_satpm paises --pais Chile
    python -m src.ingesta.reconocer_satpm descargar 202307 --region SA
    python -m src.ingesta.reconocer_satpm ciudades data/raw/satpm/satpm_SA_202307.nc
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import sys
from pathlib import Path

import boto3
import botocore
from botocore import UNSIGNED
from botocore.config import Config

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.rutas import LOGS, RAW, asegurar  # noqa: E402

BUCKET = "satpmdata"
REGION_AWS = "us-west-2"
VERSION = "V6GL03"

# El árbol real es <version>/<resolucion>/<region>/<frecuencia>/<anio>/<archivo>.nc
# El nivel <anio> no se ve listando con Delimiter sobre <frecuencia>/: hay que
# bajar un nivel más. Costó un NoSuchKey descubrirlo.
RESOLUCIONES = ("FineResolution", "CoarseResolution")
REGIONES = ("GL", "SA", "NA", "EU", "AF", "AS")
FRECUENCIAS = ("Annual", "Monthly")

RESUMEN_PAISES = (
    f"{VERSION}/RegionSummaries/GlobalPM25-{VERSION}-Annual-1998-2024-wThresFrac.csv"
)

# Firma HDF5. Los .nc de esta colección son NetCDF-4, no NetCDF clásico: un
# lector basado en scipy.io.netcdf_file falla. Se comprueba antes de aceptar.
MAGIA_HDF5 = b"\x89HDF\r\n\x1a\n"

# La variable PM25 NO declara _FillValue ni missing_value. El "sin dato" viene
# como -999.9 crudo y sin enmascarar. Un promedio ingenuo sobre celdas de mar
# devuelve un número enorme y negativo sin avisar de nada: es exactamente el
# fallo silencioso que la regla 5 obliga a atrapar.
SENTINELA = -999.0

# Rango plausible de MP2.5 en superficie. Sirve de control de cordura sobre un
# archivo recién bajado, no de filtro analítico.
PM25_MAX_PLAUSIBLE = 1000.0

# Puntos de referencia del reconocimiento: las estaciones SINCA de referencia de
# cada ciudad. Son aproximados y están aquí para contrastar magnitudes, no para
# producción — en producción las coordenadas salen del catálogo de SINCA
# (`src/ingesta/sinca_cliente.py:catalogo_region`), que las publica por estación.
CIUDADES = {
    "Santiago": (-33.4636, -70.6605),
    "Talcahuano": (-36.7249, -73.1168),
    "Coyhaique": (-45.5752, -72.0662),
}

log = logging.getLogger("satpm")


def cliente():
    """Cliente S3 sin firmar. El bucket es público: no hay ni debe haber claves."""
    cfg = Config(
        signature_version=UNSIGNED,
        connect_timeout=15,
        read_timeout=120,
        retries={"max_attempts": 3, "mode": "standard"},
    )
    return boto3.client("s3", config=cfg, region_name=REGION_AWS)


def clasificar_error(e: Exception) -> str:
    """Traduce un fallo de red a una de dos categorías que exigen decisiones opuestas.

    El proyecto corre detrás de CGNAT y CloudFront devuelve 403 por IP. Confundir
    "me bloquearon" con "no existe" lleva a descartar datos que sí están.
    """
    if isinstance(e, botocore.exceptions.ClientError):
        code = e.response["Error"]["Code"]
        http = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in ("AccessDenied", "403", "AllAccessDisabled") or http == 403:
            return f"BLOQUEADO (HTTP {http}, {code}) - probable CGNAT/IP, no ausencia de dato"
        if code in ("NoSuchKey", "NoSuchBucket", "404") or http == 404:
            return f"NO EXISTE (HTTP {http}, {code}) - el recurso no está publicado"
        return f"ERROR S3 ({code}, HTTP {http})"
    if isinstance(e, botocore.exceptions.EndpointConnectionError):
        return "SIN CONEXION - no se alcanzó el endpoint"
    if isinstance(e, botocore.exceptions.ReadTimeoutError):
        return "TIMEOUT - puede ser CGNAT; reintentar antes de concluir ausencia"
    return f"{type(e).__name__}: {e}"


def es_basura_applesingle(clave: str) -> bool:
    """¿Es un resto AppleDouble de macOS?

    El archivo contiene entradas `._V6GL03....nc` de 0 bytes. Llevan extensión
    `.nc` y NO son NetCDF. Un lector que confíe en la extensión falla, o peor,
    devuelve vacío en silencio. Aparecen en Annual/ y en RegionSummaries/.
    """
    return clave.rsplit("/", 1)[-1].startswith("._")


def prefijo(resolucion: str, region: str, frecuencia: str) -> str:
    return f"{VERSION}/{resolucion}/{region}/{frecuencia}/"


# --------------------------------------------------------------------------
# acceso
# --------------------------------------------------------------------------
def cmd_acceso(args) -> dict:
    s3 = cliente()
    out = {"bucket": BUCKET, "region_aws": REGION_AWS, "firma": "UNSIGNED"}
    try:
        r = s3.list_objects_v2(Bucket=BUCKET, Delimiter="/", MaxKeys=10)
        out["http"] = r["ResponseMetadata"]["HTTPStatusCode"]
        out["responde_sin_credenciales"] = True
        out["prefijos_raiz"] = [p["Prefix"] for p in r.get("CommonPrefixes", [])]
        log.info("acceso anónimo OK (HTTP %s)", out["http"])
    except Exception as e:  # noqa: BLE001
        out["responde_sin_credenciales"] = False
        out["diagnostico"] = clasificar_error(e)
        log.error("acceso anónimo falló: %s", out["diagnostico"])

    # Varias fuentes web citan este bucket. No existe; queda registrado para que
    # nadie vuelva a perder el rato con él.
    out["bucket_erroneo_citado_en_la_web"] = {"nombre": "v6.gl.02.04", "estado": "NoSuchBucket"}
    return out


# --------------------------------------------------------------------------
# particion
# --------------------------------------------------------------------------
def cmd_particion(args) -> dict:
    s3 = cliente()

    def hijos(pref: str) -> list[str]:
        r = s3.list_objects_v2(Bucket=BUCKET, Prefix=pref, Delimiter="/", MaxKeys=50)
        return [p["Prefix"] for p in r.get("CommonPrefixes", [])]

    niveles = [
        {"prefijo": "", "hijos": hijos("")},
        {"prefijo": f"{VERSION}/", "hijos": hijos(f"{VERSION}/")},
        {"prefijo": f"{VERSION}/FineResolution/", "hijos": hijos(f"{VERSION}/FineResolution/")},
    ]
    base = prefijo("FineResolution", args.region, args.frecuencia)
    anios = hijos(base)
    niveles.append({"prefijo": base,
                    "hijos_son_anios": [a.rstrip("/").split("/")[-1] for a in anios]})
    if anios:
        r = s3.list_objects_v2(Bucket=BUCKET, Prefix=anios[-1], MaxKeys=5)
        niveles.append({"prefijo": anios[-1],
                        "objetos": [(o["Key"], o["Size"]) for o in r.get("Contents", [])]})

    return {
        "patron": (f"{VERSION}/<resolucion>/<region>/<frecuencia>/[<anio>/]"
                   f"{VERSION}.CNNPM25.<region>.<AAAAMM>-<AAAAMM>.nc"),
        "resoluciones": list(RESOLUCIONES),
        "regiones": list(REGIONES),
        "frecuencias": list(FRECUENCIAS),
        "granularidad_objeto": "un archivo por región-mes (o región-año)",
        "formato": "NetCDF-4 sobre HDF5",
        "trampa": (
            "el nivel <anio> no aparece listando con Delimiter sobre <frecuencia>/; "
            "una clave construida sin él devuelve NoSuchKey"
        ),
        "niveles": niveles,
    }


# --------------------------------------------------------------------------
# contar
# --------------------------------------------------------------------------
def cmd_contar(args) -> dict:
    s3 = cliente()
    base = prefijo(args.resolucion, args.region, args.frecuencia)
    pag = s3.get_paginator("list_objects_v2")

    validos, bytes_validos = 0, 0
    basura: list[str] = []
    por_anio: dict[str, int] = {}
    primero = ultimo = None
    try:
        for page in pag.paginate(Bucket=BUCKET, Prefix=base):
            for o in page.get("Contents", []):
                clave = o["Key"]
                if es_basura_applesingle(clave):
                    basura.append(clave)
                    continue
                if not clave.endswith(".nc"):
                    continue
                validos += 1
                bytes_validos += o["Size"]
                # Monthly cuelga de <anio>/; Annual no. Se toma el año del nombre
                # del archivo, que en ambos casos lo lleva.
                anio = clave.rsplit(".", 2)[-2][:4]
                por_anio[anio] = por_anio.get(anio, 0) + 1
                primero = primero or clave
                ultimo = clave
    except Exception as e:  # noqa: BLE001
        return {"prefijo": base, "exhaustivo": False, "diagnostico": clasificar_error(e)}

    return {
        "prefijo": base,
        "archivos_validos": validos,
        "bytes": bytes_validos,
        "gigabytes": round(bytes_validos / 1e9, 2),
        "anios": sorted(por_anio),
        "archivos_por_anio": dict(sorted(por_anio.items())),
        "primero": primero,
        "ultimo": ultimo,
        "descartados_applesingle": len(basura),
        "ejemplos_descartados": basura[:5],
        "exhaustivo": True,
    }


# --------------------------------------------------------------------------
# paises
# --------------------------------------------------------------------------
def cmd_paises(args) -> dict:
    """MP2.5 anual ponderado por población, por país.

    Este CSV de menos de 1 MB cubre el papel de marco internacional que el
    archivo de OpenAQ resolvería con 16,2 millones de objetos. Trae además la
    fracción de población por encima de cada umbral, ya calculada.
    """
    s3 = cliente()
    try:
        cuerpo = s3.get_object(Bucket=BUCKET, Key=RESUMEN_PAISES)["Body"].read()
    except Exception as e:  # noqa: BLE001
        return {"clave": RESUMEN_PAISES, "estado": "fallo", "diagnostico": clasificar_error(e)}

    filas = list(csv.DictReader(io.StringIO(cuerpo.decode("utf-8", errors="replace"))))
    paises = sorted({f["Region"] for f in filas})
    out = {
        "clave": RESUMEN_PAISES,
        "bytes": len(cuerpo),
        "filas": len(filas),
        "paises": len(paises),
        "columnas": list(filas[0]) if filas else [],
        "anios": sorted({f["Year"] for f in filas}),
    }
    if args.pais:
        serie = [f for f in filas if f["Region"].lower() == args.pais.lower()]
        if not serie:
            out["aviso"] = f"'{args.pais}' no aparece; revisa la grafía exacta"
        out["serie"] = [
            {"anio": int(f["Year"]),
             "pm25_ponderado_poblacion": float(f["Population-Weighted PM2.5 [ug/m3]"]),
             "pct_pob_sobre_5": float(f["% pop >= 5 ug/m3 [%]"]),
             "pct_pob_sobre_15": float(f["% pop >= 15 ug/m3 [%]"]),
             "pct_pob_sobre_25": float(f["% pop >= 25 ug/m3 [%]"])}
            for f in serie
            if not args.desde or int(f["Year"]) >= args.desde
        ]
    return out


# --------------------------------------------------------------------------
# descargar
# --------------------------------------------------------------------------
def _validar_netcdf(ruta: Path) -> dict:
    """Cadena de validación: un fallo nunca puede parecer un éxito (regla 5).

    Cinco controles: tamaño, firma binaria, apertura, variable esperada y rango
    de valores. Se importa netCDF4 aquí y no arriba para que los subcomandos que
    no leen archivos funcionen aunque la dependencia falte.
    """
    import netCDF4  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    tam = ruta.stat().st_size
    if tam == 0:
        return {"valido": False, "motivo": "archivo de 0 bytes"}
    with ruta.open("rb") as fh:
        magia = fh.read(8)
    if magia != MAGIA_HDF5:
        return {"valido": False, "motivo": f"firma {magia!r} no es HDF5/NetCDF-4"}

    try:
        d = netCDF4.Dataset(ruta)
    except Exception as e:  # noqa: BLE001
        return {"valido": False, "motivo": f"no abre como NetCDF: {type(e).__name__}"}
    try:
        if "PM25" not in d.variables:
            return {"valido": False, "motivo": f"sin variable PM25; hay {list(d.variables)}"}
        pm = d.variables["PM25"][:]
        celdas = int(pm.size)
        if celdas == 0:
            return {"valido": False, "motivo": "PM25 sin celdas"}
        con_dato = np.asarray(pm)[np.asarray(pm) > SENTINELA]
        if con_dato.size == 0:
            return {"valido": False, "motivo": "todas las celdas son centinela -999.9"}
        maximo = float(con_dato.max())
        if maximo > PM25_MAX_PLAUSIBLE:
            return {"valido": False, "motivo": f"máximo {maximo} fuera de rango plausible"}
        return {
            "valido": True,
            "bytes": tam,
            "celdas": celdas,
            "celdas_con_dato": int(con_dato.size),
            "pct_con_dato": round(100 * con_dato.size / celdas, 2),
            "pm25_min": round(float(con_dato.min()), 2),
            "pm25_media": round(float(con_dato.mean()), 2),
            "pm25_max": round(maximo, 2),
            "unidades": getattr(d.variables["PM25"], "units", None),
            "periodo_declarado": str(getattr(d, "TIMECOVERAGE", "")),
        }
    finally:
        d.close()


def cmd_descargar(args) -> dict:
    """Baja un archivo región-mes a data/raw/. La zona cruda es inmutable."""
    s3 = cliente()
    anio = args.periodo[:4]
    base = prefijo(args.resolucion, args.region, args.frecuencia)
    # Asimetría del árbol, comprobada listando: Monthly reparte los archivos en
    # subcarpetas por año y Annual los deja sueltos. Construir la clave por
    # analogía con el otro caso devuelve NoSuchKey.
    if args.frecuencia == "Monthly":
        nombre = f"{VERSION}.CNNPM25.{args.region}.{args.periodo}-{args.periodo}.nc"
        clave = f"{base}{anio}/{nombre}"
    else:
        nombre = f"{VERSION}.CNNPM25.{args.region}.{anio}01-{anio}12.nc"
        clave = f"{base}{nombre}"

    destino = RAW / "satpm" / f"satpm_{args.region}_{args.periodo}.nc"
    asegurar(destino.parent)
    if destino.exists() and not args.forzar:
        return {"clave": clave, "destino": str(destino), "estado": "ya existe, no se sobrescribe"}

    # A un archivo temporal: si la validación falla, no queda nada en la zona
    # cruda. Un archivo que no pasa validación va a la cola de errores, no a raw.
    temporal = destino.with_suffix(".nc.parcial")
    try:
        s3.download_file(BUCKET, clave, str(temporal))
    except Exception as e:  # noqa: BLE001
        temporal.unlink(missing_ok=True)
        return {"clave": clave, "estado": "fallo", "diagnostico": clasificar_error(e)}

    veredicto = _validar_netcdf(temporal)
    if not veredicto["valido"]:
        rechazado = destino.with_suffix(".nc.rechazado")
        temporal.replace(rechazado)
        log.error("descarga rechazada: %s", veredicto["motivo"])
        return {"clave": clave, "estado": "rechazado", "motivo": veredicto["motivo"],
                "archivo_en_cola_de_errores": str(rechazado)}

    temporal.replace(destino)
    log.info("%s -> %s (%s bytes)", clave, destino.name, veredicto["bytes"])
    return {"clave": clave, "destino": str(destino), "estado": "ok", **veredicto}


# --------------------------------------------------------------------------
# ciudades
# --------------------------------------------------------------------------
def cmd_ciudades(args) -> dict:
    """Extrae MP2.5 en las tres ciudades desde un .nc ya descargado.

    Devuelve la celda exacta y una ventana alrededor. La ventana importa: una
    estación mide en un punto y la celda promedia ~1,1 km, de modo que la
    dispersión dentro de la ventana dice cuánto depende el número de dónde se
    puso el monitor.
    """
    import netCDF4  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    ruta = Path(args.archivo)
    if not ruta.exists():
        raise SystemExit(f"No existe {ruta}. Bájalo antes con el subcomando 'descargar'.")

    d = netCDF4.Dataset(ruta)
    try:
        lat = np.asarray(d.variables["lat"][:])
        lon = np.asarray(d.variables["lon"][:])
        pm = np.asarray(d.variables["PM25"][:])
        r = args.radio
        salida = {}
        for nombre, (la, lo) in CIUDADES.items():
            i = int(np.abs(lat - la).argmin())
            j = int(np.abs(lon - lo).argmin())
            caja = pm[max(i - r, 0):i + r + 1, max(j - r, 0):j + r + 1]
            con_dato = caja[caja > SENTINELA]
            celda = float(pm[i, j])
            salida[nombre] = {
                "lat_pedida": la, "lon_pedida": lo,
                "lat_celda": round(float(lat[i]), 4), "lon_celda": round(float(lon[j]), 4),
                "pm25_celda": round(celda, 2) if celda > SENTINELA else None,
                "ventana_celdas": f"{caja.shape[0]}x{caja.shape[1]}",
                "pm25_media_ventana": round(float(con_dato.mean()), 2) if con_dato.size else None,
                "pm25_min_ventana": round(float(con_dato.min()), 2) if con_dato.size else None,
                "pm25_max_ventana": round(float(con_dato.max()), 2) if con_dato.size else None,
            }
        return {
            "archivo": str(ruta),
            "periodo_declarado": str(getattr(d, "TIMECOVERAGE", "")),
            "resolucion_grados": float(getattr(d, "LAT_DELTA", 0)),
            "ciudades": salida,
        }
    finally:
        d.close()


# --------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--salida-json", type=Path, help="guarda el resultado como JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    def con_salida(s):
        """Acepta --salida-json también DESPUÉS del subcomando.

        Es donde se escribe por instinto, al final de la línea. SUPPRESS impide
        que el valor del parser padre quede pisado con None cuando no se pasa
        aquí. Mismo arreglo que en `src/nube/sincronizar.py`.
        """
        s.add_argument("--salida-json", type=Path, default=argparse.SUPPRESS,
                       help="guarda el resultado como JSON")
        return s

    con_salida(sub.add_parser("acceso")).set_defaults(fn=cmd_acceso)

    pa = con_salida(sub.add_parser("particion"))
    pa.add_argument("--region", choices=REGIONES, default="SA")
    pa.add_argument("--frecuencia", choices=FRECUENCIAS, default="Monthly")
    pa.set_defaults(fn=cmd_particion)

    c = con_salida(sub.add_parser("contar"))
    c.add_argument("--resolucion", choices=RESOLUCIONES, default="FineResolution")
    c.add_argument("--region", choices=REGIONES, default="SA")
    c.add_argument("--frecuencia", choices=FRECUENCIAS, default="Monthly")
    c.set_defaults(fn=cmd_contar)

    pl = con_salida(sub.add_parser("paises"))
    pl.add_argument("--pais", help="serie anual de un país, p. ej. Chile")
    pl.add_argument("--desde", type=int, help="recorta la serie desde este año")
    pl.set_defaults(fn=cmd_paises)

    d = con_salida(sub.add_parser("descargar"))
    d.add_argument("periodo", help="AAAAMM para Monthly, AAAA para Annual")
    d.add_argument("--resolucion", choices=RESOLUCIONES, default="FineResolution")
    d.add_argument("--region", choices=REGIONES, default="SA")
    d.add_argument("--frecuencia", choices=FRECUENCIAS, default="Monthly")
    d.add_argument("--forzar", action="store_true", help="permite reescribir la zona cruda")
    d.set_defaults(fn=cmd_descargar)

    ci = con_salida(sub.add_parser("ciudades"))
    ci.add_argument("archivo", help="ruta a un .nc ya descargado")
    ci.add_argument("--radio", type=int, default=5, help="celdas a cada lado (5 => ventana 11x11)")
    ci.set_defaults(fn=cmd_ciudades)

    args = p.parse_args(argv)

    # La consola de Windows usa cp1252 y destroza las tildes del JSON. Se fuerza
    # UTF-8 en la salida para poder escribir en español sin mojibake.
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")

    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "reconocer_satpm.log", encoding="utf-8"),
                  logging.StreamHandler(sys.stderr)],
    )

    res = args.fn(args)
    print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    if args.salida_json:
        asegurar(args.salida_json.parent)
        args.salida_json.write_text(
            json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
