"""Reconocimiento del archivo publico de OpenAQ en S3.

OpenAQ NO es fuente de aire para Chile (cosecha desde SINCA; usarlo seria contar
la misma medicion dos veces). Su rol es el marco de referencia internacional.
Este script caracteriza el archivo para evaluar si ese rol es viable.

Bucket publico, sin credenciales: se usa firma UNSIGNED.

Subcomandos
-----------
    acceso      ¿responde el bucket sin credenciales? distingue 403 de vacio
    particion   como esta organizado el arbol de prefijos
    contar      cuantas estaciones (locationid) hay en total
    muestrear   muestrea estaciones: coordenadas, parametros, cobertura, peso
    descargar   baja un archivo dia-estacion a data/raw/ (zona cruda, inmutable)

Uso
---
    python -m src.ingesta.reconocer_openaq acceso
    python -m src.ingesta.reconocer_openaq contar --limite 200000
    python -m src.ingesta.reconocer_openaq muestrear --n 400 --hilos 16
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import logging
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

import boto3
import botocore
from botocore import UNSIGNED
from botocore.config import Config

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.rutas import LOGS, RAW, RECONOCIMIENTO, asegurar  # noqa: E402

BUCKET = "openaq-data-archive"
REGION = "us-east-1"
PREFIJO = "records/csv.gz/"

# Caja envolvente de Chile continental + austral. Sirve para identificar
# estaciones chilenas sin depender de la API (que exige credenciales).
# Deliberadamente generosa: es un filtro de reconocimiento, no de produccion.
CHILE_BBOX = {"lat_min": -56.0, "lat_max": -17.0, "lon_min": -76.0, "lon_max": -66.0}

log = logging.getLogger("openaq")


def cliente():
    """Cliente S3 sin firmar. El bucket es publico: no hay ni debe haber claves."""
    cfg = Config(
        signature_version=UNSIGNED,
        connect_timeout=15,
        read_timeout=60,
        retries={"max_attempts": 3, "mode": "standard"},
    )
    return boto3.client("s3", config=cfg, region_name=REGION)


def clasificar_error(e: Exception) -> str:
    """Traduce un fallo de red a una de dos categorias que exigen decisiones opuestas.

    El proyecto corre detras de CGNAT y CloudFront devuelve 403 por IP. Confundir
    "me bloquearon" con "no existe" lleva a descartar datos que si estan.
    """
    if isinstance(e, botocore.exceptions.ClientError):
        code = e.response["Error"]["Code"]
        http = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in ("AccessDenied", "403", "AllAccessDisabled") or http == 403:
            return f"BLOQUEADO (HTTP {http}, {code}) - probable CGNAT/IP, no ausencia de dato"
        if code in ("NoSuchKey", "NoSuchBucket", "404") or http == 404:
            return f"NO EXISTE (HTTP {http}, {code}) - el recurso no esta publicado"
        return f"ERROR S3 ({code}, HTTP {http})"
    if isinstance(e, botocore.exceptions.EndpointConnectionError):
        return "SIN CONEXION - no se alcanzo el endpoint"
    if isinstance(e, botocore.exceptions.ReadTimeoutError):
        return "TIMEOUT - puede ser CGNAT; reintentar antes de concluir ausencia"
    return f"{type(e).__name__}: {e}"


# --------------------------------------------------------------------------
# acceso
# --------------------------------------------------------------------------
def cmd_acceso(args) -> dict:
    s3 = cliente()
    out = {"bucket": BUCKET, "region": REGION, "firma": "UNSIGNED"}
    try:
        r = s3.list_objects_v2(Bucket=BUCKET, Delimiter="/", MaxKeys=10)
        out["http"] = r["ResponseMetadata"]["HTTPStatusCode"]
        out["responde_sin_credenciales"] = True
        out["prefijos_raiz"] = [p["Prefix"] for p in r.get("CommonPrefixes", [])]
        log.info("acceso anonimo OK (HTTP %s)", out["http"])
    except Exception as e:  # noqa: BLE001
        out["responde_sin_credenciales"] = False
        out["diagnostico"] = clasificar_error(e)
        log.error("acceso anonimo fallo: %s", out["diagnostico"])
    return out


# --------------------------------------------------------------------------
# particion
# --------------------------------------------------------------------------
def cmd_particion(args) -> dict:
    s3 = cliente()
    niveles = []

    def listar(prefijo: str, n: int = 8):
        r = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefijo, Delimiter="/", MaxKeys=n)
        return (
            [p["Prefix"] for p in r.get("CommonPrefixes", [])],
            [(o["Key"], o["Size"]) for o in r.get("Contents", [])],
            r["IsTruncated"],
        )

    pre, _, trunc = listar("")
    niveles.append({"prefijo": "", "hijos": pre, "truncado": trunc})
    pre, _, trunc = listar(PREFIJO)
    niveles.append({"prefijo": PREFIJO, "ejemplo_hijos": pre[:5], "truncado": trunc})

    loc = pre[0] if pre else None
    if loc:
        anios, _, _ = listar(loc)
        niveles.append({"prefijo": loc, "hijos": anios})
        if anios:
            meses, _, _ = listar(anios[-1])
            niveles.append({"prefijo": anios[-1], "hijos": meses})
            if meses:
                _, objs, _ = listar(meses[0])
                niveles.append({"prefijo": meses[0], "objetos": objs[:5]})

    return {
        "patron": "records/csv.gz/locationid=<id>/year=<yyyy>/month=<mm>/location-<id>-<yyyymmdd>.csv.gz",
        "granularidad_objeto": "un archivo por estacion-dia",
        "formato": "CSV comprimido con gzip",
        "niveles": niveles,
    }


# --------------------------------------------------------------------------
# contar
# --------------------------------------------------------------------------
def cmd_contar(args) -> dict:
    """Cuenta prefijos locationid=. Es el conteo de estaciones del archivo."""
    s3 = cliente()
    pag = s3.get_paginator("list_objects_v2")
    total, maximo, paginas = 0, -1, 0
    anomalos: list[str] = []
    try:
        for page in pag.paginate(
            Bucket=BUCKET, Prefix=PREFIJO, Delimiter="/", PaginationConfig={"PageSize": 1000}
        ):
            cps = page.get("CommonPrefixes", [])
            total += len(cps)
            paginas += 1
            for cp in cps:
                try:
                    maximo = max(maximo, int(cp["Prefix"].split("locationid=")[1].strip("/")))
                except (ValueError, IndexError):
                    # Prefijo que no sigue el patron locationid=<n>. Se cuenta como
                    # estacion igual, pero no aporta al id maximo.
                    anomalos.append(cp["Prefix"])
            if paginas % 20 == 0:
                log.info("  %s estaciones listadas...", total)
            if args.limite and total >= args.limite:
                log.warning("corte por --limite en %s; el conteo NO es exhaustivo", total)
                return {"estaciones": total, "id_maximo": maximo, "exhaustivo": False,
                        "prefijos_anomalos": anomalos[:20]}
    except Exception as e:  # noqa: BLE001
        return {"estaciones": total, "exhaustivo": False, "diagnostico": clasificar_error(e),
                "prefijos_anomalos": anomalos[:20]}
    return {"estaciones": total, "id_maximo": maximo, "exhaustivo": True, "paginas": paginas,
            "prefijos_anomalos": anomalos[:20]}


# --------------------------------------------------------------------------
# muestrear
# --------------------------------------------------------------------------
@dataclass
class Estacion:
    location_id: int
    nombre: str | None = None
    lat: float | None = None
    lon: float | None = None
    parametros: list[str] = field(default_factory=list)
    anios: list[str] = field(default_factory=list)
    archivos: int = 0
    bytes_gz: int = 0
    en_chile: bool = False
    error: str | None = None


def _perfilar(s3, lid: int, anios_interes: set[str]) -> Estacion:
    """Perfila una estacion: años cubiertos, peso y una lectura de cabecera."""
    est = Estacion(location_id=lid)
    base = f"{PREFIJO}locationid={lid}/"
    try:
        r = s3.list_objects_v2(Bucket=BUCKET, Prefix=base, Delimiter="/")
        est.anios = sorted(
            p["Prefix"].split("year=")[-1].strip("/") for p in r.get("CommonPrefixes", [])
        )
        if not est.anios:
            est.error = "sin años (estacion vacia)"
            return est

        # Peso y numero de archivos de un año del periodo de interes, si existe.
        objetivo = sorted(anios_interes & set(est.anios)) or est.anios[-1:]
        pag = s3.get_paginator("list_objects_v2")
        for page in pag.paginate(Bucket=BUCKET, Prefix=f"{base}year={objetivo[0]}/"):
            for o in page.get("Contents", []):
                est.archivos += 1
                est.bytes_gz += o["Size"]

        # Una lectura real: coordenadas, nombre y parametros medidos.
        r2 = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"{base}year={objetivo[0]}/", MaxKeys=1)
        # bajar al primer objeto real recorriendo mes
        rm = s3.list_objects_v2(
            Bucket=BUCKET, Prefix=f"{base}year={objetivo[0]}/", Delimiter="/"
        )
        meses = [p["Prefix"] for p in rm.get("CommonPrefixes", [])]
        if meses:
            ro = s3.list_objects_v2(Bucket=BUCKET, Prefix=meses[0], MaxKeys=1)
            if ro.get("Contents"):
                key = ro["Contents"][0]["Key"]
                crudo = gzip.decompress(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
                # El archivo viene en UTF-8 (µ se codifica \xc2\xb5).
                texto = crudo.decode("utf-8", errors="replace")
                import csv as _csv

                filas = list(_csv.DictReader(io.StringIO(texto)))
                if filas:
                    est.nombre = filas[0].get("location")
                    try:
                        est.lat = float(filas[0]["lat"])
                        est.lon = float(filas[0]["lon"])
                    except (KeyError, ValueError, TypeError):
                        pass
                    est.parametros = sorted({f["parameter"] for f in filas if f.get("parameter")})
        if est.lat is not None and est.lon is not None:
            est.en_chile = (
                CHILE_BBOX["lat_min"] <= est.lat <= CHILE_BBOX["lat_max"]
                and CHILE_BBOX["lon_min"] <= est.lon <= CHILE_BBOX["lon_max"]
            )
    except Exception as e:  # noqa: BLE001
        est.error = clasificar_error(e)
    return est


def cmd_muestrear(args) -> dict:
    s3 = cliente()
    rng = random.Random(args.semilla)
    anios_interes = {str(a) for a in range(2018, 2025)}

    if args.ids:
        ids = [int(x) for x in args.ids.split(",")]
    else:
        ids = rng.sample(range(1, args.id_max + 1), args.n)

    resultados: list[Estacion] = []
    with ThreadPoolExecutor(max_workers=args.hilos) as ex:
        futs = {ex.submit(_perfilar, s3, i, anios_interes): i for i in ids}
        for j, f in enumerate(as_completed(futs), 1):
            resultados.append(f.result())
            if j % 50 == 0:
                log.info("  %s/%s perfiladas", j, len(ids))

    vivas = [e for e in resultados if e.anios and not e.error]
    con_pm25 = [e for e in vivas if "pm25" in e.parametros]
    en_periodo = [e for e in vivas if anios_interes & set(e.anios)]
    chilenas = [e for e in vivas if e.en_chile]
    bloqueadas = [e for e in resultados if e.error and "BLOQUEADO" in e.error]

    bytes_anio = [e.bytes_gz for e in en_periodo if e.bytes_gz > 0]
    archivos_anio = [e.archivos for e in en_periodo if e.archivos > 0]
    media_bytes = sum(bytes_anio) / len(bytes_anio) if bytes_anio else 0
    media_arch = sum(archivos_anio) / len(archivos_anio) if archivos_anio else 0

    resumen = {
        "muestreadas": len(ids),
        "id_max_usado": args.id_max,
        "con_datos": len(vivas),
        "vacias_o_inexistentes": len(resultados) - len(vivas) - len(bloqueadas),
        "bloqueadas_403": len(bloqueadas),
        "con_pm25": len(con_pm25),
        "con_datos_2018_2024": len(en_periodo),
        "en_bbox_chile": len(chilenas),
        "tasa_id_vivos": round(len(vivas) / len(ids), 4),
        "media_bytes_gz_por_estacion_anio": round(media_bytes),
        "media_archivos_por_estacion_anio": round(media_arch, 1),
        "parametros_vistos": sorted({p for e in vivas for p in e.parametros}),
        "chilenas_detectadas": [
            {"id": e.location_id, "nombre": e.nombre, "lat": e.lat, "lon": e.lon,
             "parametros": e.parametros, "anios": e.anios}
            for e in chilenas
        ],
        "detalle": [asdict(e) for e in resultados] if args.detalle else "omitido (usar --detalle)",
    }
    return resumen


# --------------------------------------------------------------------------
# inventario: paises y estaciones via la particion por proveedor
# --------------------------------------------------------------------------
def _contar_prefijos(s3, prefijo: str, clave: str) -> list[str]:
    """Devuelve los valores de <clave>=<valor>/ colgando de un prefijo."""
    pag = s3.get_paginator("list_objects_v2")
    out = []
    for page in pag.paginate(Bucket=BUCKET, Prefix=prefijo, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            p = cp["Prefix"]
            if f"{clave}=" in p:
                out.append(p.split(f"{clave}=")[1].strip("/"))
    return out


def cmd_inventario(args) -> dict:
    """Recorre provider -> country -> locationid.

    La particion por proveedor incluye el pais, cosa que la particion plana por
    locationid no tiene. Es la unica via para contar paises sin la API v3, que
    exige credenciales.
    """
    s3 = cliente()
    provs = _contar_prefijos(s3, PREFIJO, "provider")
    log.info("%s proveedores", len(provs))

    def por_proveedor(prov: str):
        base = f"{PREFIJO}provider={prov}/"
        paises = _contar_prefijos(s3, base, "country")
        det = {}
        for c in paises:
            locs = _contar_prefijos(s3, f"{base}country={c}/", "locationid")
            det[c] = len(locs)
        return prov, det

    inventario = {}
    with ThreadPoolExecutor(max_workers=args.hilos) as ex:
        futs = {ex.submit(por_proveedor, p): p for p in provs}
        for j, f in enumerate(as_completed(futs), 1):
            prov, det = f.result()
            inventario[prov] = det
            log.info("  [%s/%s] %s -> %s", j, len(provs), prov, det)

    por_pais: dict[str, int] = {}
    for det in inventario.values():
        for c, n in det.items():
            por_pais[c] = por_pais.get(c, 0) + n

    return {
        "proveedores": len(provs),
        "paises": len(por_pais),
        "estaciones_via_proveedor": sum(por_pais.values()),
        "estaciones_por_pais": dict(sorted(por_pais.items(), key=lambda kv: -kv[1])),
        "por_proveedor": inventario,
    }


# --------------------------------------------------------------------------
# barrer: ubicar estaciones por coordenadas, sin depender de la API
# --------------------------------------------------------------------------
def _sondear(s3, lid: int, anios: tuple[int, ...]) -> dict | None:
    """Lee la primera fila disponible de una estacion. Dos peticiones S3.

    Sin Delimiter, list_objects_v2 lista recursivamente: con MaxKeys=1 devuelve
    el primer archivo del año pedido en una sola llamada.
    """
    for a in anios:
        try:
            r = s3.list_objects_v2(
                Bucket=BUCKET, Prefix=f"{PREFIJO}locationid={lid}/year={a}/", MaxKeys=1
            )
            if not r.get("Contents"):
                continue
            key = r["Contents"][0]["Key"]
            crudo = gzip.decompress(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
            lineas = crudo.decode("utf-8", errors="replace").splitlines()
            if len(lineas) < 2:
                continue
            campos = lineas[1].split(",")
            # location_id,sensors_id,location,datetime,lat,lon,parameter,units,value
            # El nombre puede traer comas; se cuenta desde el final para no romper.
            return {
                "id": lid,
                "nombre": ",".join(campos[2:-6]) if len(campos) > 9 else campos[2],
                "lat": float(campos[-5]),
                "lon": float(campos[-4]),
                "parametro": campos[-3],
                "anio": a,
            }
        except (ValueError, IndexError):
            continue
        except Exception:  # noqa: BLE001
            continue
    return None


def cmd_barrer(args) -> dict:
    """Barre un rango de ids leyendo coordenadas, y reporta los que caen en Chile."""
    s3 = cliente()
    anios = tuple(range(args.anio_min, args.anio_max + 1))

    if args.ids:
        ids = [int(x) for x in args.ids.split(",")]
    elif args.paso > 1:
        ids = list(range(args.id_min, args.id_max + 1, args.paso))
    else:
        ids = list(range(args.id_min, args.id_max + 1))

    vistos, chilenas = [], []
    with ThreadPoolExecutor(max_workers=args.hilos) as ex:
        futs = {ex.submit(_sondear, s3, i, anios): i for i in ids}
        for j, f in enumerate(as_completed(futs), 1):
            r = f.result()
            if r:
                vistos.append(r)
                if (
                    CHILE_BBOX["lat_min"] <= r["lat"] <= CHILE_BBOX["lat_max"]
                    and CHILE_BBOX["lon_min"] <= r["lon"] <= CHILE_BBOX["lon_max"]
                ):
                    chilenas.append(r)
                    log.info("CHILE: id=%s %s (%.4f, %.4f)", r["id"], r["nombre"], r["lat"], r["lon"])
            if j % 200 == 0:
                log.info("  %s/%s sondeados, %s vivos, %s en Chile", j, len(ids), len(vistos), len(chilenas))

    return {
        "ids_sondeados": len(ids),
        "rango": [min(ids), max(ids)] if ids else None,
        "paso": args.paso,
        "con_datos_en_periodo": len(vistos),
        "tasa_vivos": round(len(vistos) / len(ids), 4) if ids else 0,
        "en_bbox_chile": len(chilenas),
        "chilenas": sorted(chilenas, key=lambda x: x["id"]),
        "muestra_global": vistos[: args.mostrar] if args.mostrar else [],
    }


# --------------------------------------------------------------------------
# descargar
# --------------------------------------------------------------------------
def cmd_descargar(args) -> dict:
    """Baja un archivo estacion-dia a data/raw/. La zona cruda es inmutable."""
    s3 = cliente()
    key = (
        f"{PREFIJO}locationid={args.location_id}/year={args.fecha[:4]}/"
        f"month={args.fecha[4:6]}/location-{args.location_id}-{args.fecha}.csv.gz"
    )
    destino = RAW / "openaq" / f"openaq_loc{args.location_id}_{args.fecha}.csv.gz"
    asegurar(destino.parent)
    if destino.exists() and not args.forzar:
        return {"key": key, "destino": str(destino), "estado": "ya existe, no se sobrescribe"}
    try:
        cuerpo = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    except Exception as e:  # noqa: BLE001
        return {"key": key, "estado": "fallo", "diagnostico": clasificar_error(e)}
    destino.write_bytes(cuerpo)
    texto = gzip.decompress(cuerpo).decode("utf-8", errors="replace")
    return {
        "key": key,
        "destino": str(destino.relative_to(RAW.parent.parent)),
        "bytes_gz": len(cuerpo),
        "bytes_planos": len(texto),
        "filas": len(texto.splitlines()) - 1,
        "cabecera": texto.splitlines()[0] if texto else None,
    }


# --------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--salida-json", type=Path, help="guarda el resultado como JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("acceso").set_defaults(fn=cmd_acceso)
    sub.add_parser("particion").set_defaults(fn=cmd_particion)

    c = sub.add_parser("contar")
    c.add_argument("--limite", type=int, default=0, help="0 = sin corte (exhaustivo)")
    c.set_defaults(fn=cmd_contar)

    m = sub.add_parser("muestrear")
    m.add_argument("--n", type=int, default=300)
    m.add_argument("--id-max", type=int, default=400000)
    m.add_argument("--hilos", type=int, default=16)
    m.add_argument("--semilla", type=int, default=42)
    m.add_argument("--ids", type=str, help="lista explicita: 1,2,3")
    m.add_argument("--detalle", action="store_true")
    m.set_defaults(fn=cmd_muestrear)

    i = sub.add_parser("inventario")
    i.add_argument("--hilos", type=int, default=12)
    i.set_defaults(fn=cmd_inventario)

    b = sub.add_parser("barrer")
    b.add_argument("--id-min", type=int, default=1)
    b.add_argument("--id-max", type=int, default=100000)
    b.add_argument("--paso", type=int, default=1, help=">1 muestrea uno de cada N ids")
    b.add_argument("--ids", type=str, help="lista explicita: 1,2,3")
    b.add_argument("--anio-min", type=int, default=2018)
    b.add_argument("--anio-max", type=int, default=2024)
    b.add_argument("--hilos", type=int, default=32)
    b.add_argument("--mostrar", type=int, default=0, help="incluye N filas de muestra global")
    b.set_defaults(fn=cmd_barrer)

    d = sub.add_parser("descargar")
    d.add_argument("location_id", type=int)
    d.add_argument("fecha", help="AAAAMMDD")
    d.add_argument("--forzar", action="store_true", help="permite reescribir la zona cruda")
    d.set_defaults(fn=cmd_descargar)

    args = p.parse_args(argv)

    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "reconocer_openaq.log", encoding="utf-8"),
                  logging.StreamHandler(sys.stderr)],
    )

    res = args.fn(args)
    print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    if args.salida_json:
        asegurar(args.salida_json.parent)
        args.salida_json.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
