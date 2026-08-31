"""Construye `dim_estacion` a partir del catálogo de coordenadas, corrigiendo.

Por qué existe este módulo y no un CSV arreglado a mano
-------------------------------------------------------
`raw/coordenadas_intereses.csv` tiene una coordenada mal: la estación Nueva
Libertad declara longitud -67.118855, que la sitúa **en Argentina**, a unos
535 km de Talcahuano. La tentación es abrir el archivo y cambiar el número.

No se hace. La regla 3 del proyecto dice que la zona cruda es inmutable, y la
política del bucket la respalda (`raw/*` deniega `s3:DeleteObject`). Un archivo
«arreglado» en la zona cruda deja de reproducir lo que entregó la fuente, y a
partir de ahí ningún reproceso es verificable: nadie puede distinguir un dato
original de una corrección hecha en algún momento por alguien.

La corrección vive aquí, en `CORRECCIONES`, con su motivo y su evidencia. Queda
versionada, revisable en un diff, y aplicada de forma idéntica cada vez que se
reconstruye la dimensión.

Qué se comprobó sobre el archivo (26 de agosto de 2026)
-------------------------------------------------------
Las 21 filas cruzan su lat/lon contra su propio UTM: **coinciden a 0,0 km en
las 21**. Es decir, las dos codificaciones no son independientes — una se
derivó de la otra — así que el UTM no puede usarse como testigo ingenuo.

La evidencia que sí sostiene la corrección es de otro tipo, y es triple:

  1. El huso declarado contradice a la comuna. Talcahuano cae en el huso 18;
     la fila declara 19.
  2. El mismo easting (667962) leído en huso 18 da exactamente -73.118855, que
     deja la estación a ~1,3 km de Inpesca, entre sus vecinas.
  3. La diferencia entre lo declarado y lo corregido es exactamente 6.000000°,
     que es el ancho de un huso UTM.

O sea: no se traspapeló un dígito. Se leyó un easting válido en el huso
equivocado, y la longitud errónea es consecuencia de eso.

El UTM no viaja a la dimensión. Su único papel en el proyecto fue delatar esta
fila; para todo lo demás se usa lat/lon.

Uso
---
    python -m src.procesamiento.estaciones auditar
    python -m src.procesamiento.estaciones auditar --bucket <bucket> --perfil <perfil>
    python -m src.procesamiento.estaciones construir --bucket <bucket> --perfil <perfil>
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.procesamiento.geografia import (  # noqa: E402
    ciudad_de,
    motivo_exclusion,
    normalizar_nombre,
)
from src.rutas import LOGS, PROCESSED, RAW, asegurar  # noqa: E402

log = logging.getLogger("estaciones")

CATALOGO = "coordenadas_intereses.csv"

# El catálogo usa la convención CONTRARIA a los CSV de SINCA: separador coma,
# decimal punto y UTF-8 con acentos, frente a `;`, coma decimal y ASCII puro.
# Aplicarle la regla de SINCA convierte «Estación» en «EstaciÃ³n» y rompe las
# coordenadas. Y una fila trae una coma dentro de comillas
# («Estación San Vicente, Bomberos»), así que `split(",")` la parte mal: hay
# que usar el módulo csv, no partir a mano.
CATALOGO_ENCODING = "utf-8"

# ---------------------------------------------------------------------------
# Correcciones al crudo. Una entrada por campo corregido, nunca en bloque.
# ---------------------------------------------------------------------------
CORRECCIONES = [
    {
        "id": "240",
        "estacion": "Estación Nueva Libertad",
        "campo": "Longitud",
        "valor_crudo": "-67.118855",
        "valor_corregido": "-73.118855",
        "motivo": "el easting se leyó en el huso 19 cuando Talcahuano está en el 18",
        "evidencia": (
            "667962 E leído en huso 18 da -73.118855 exacto; la diferencia con el "
            "valor crudo es 6.000000°, el ancho de un huso; las otras tres estaciones "
            "de Talcahuano tienen easting 667557-669252 en huso 18"
        ),
        "fecha": "2026-08-26",
    },
    {
        # Va junto a la anterior y no es cosmética: el huso es el campo que
        # estaba mal de origen, y la longitud errónea fue su consecuencia.
        # Corregir la longitud sola dejaría la fila contradiciéndose a sí misma,
        # y la auditoría —con razón— se negaría a pasar.
        "id": "240",
        "estacion": "Estación Nueva Libertad",
        "campo": "Huso",
        "valor_crudo": "19",
        "valor_corregido": "18",
        "motivo": ("Talcahuano está en el huso 18; es el error de origen que "
                   "produjo la longitud mala"),
        "evidencia": (
            "las otras tres estaciones de Talcahuano declaran huso 18, y solo en "
            "el 18 el easting 667962 reproduce la longitud corregida"
        ),
        "fecha": "2026-08-26",
    },
]

# Anomalías conocidas que NO se corrigen, para que la auditoría no las reporte
# como hallazgos nuevos cada vez. Documentar por qué se dejan pasar importa
# tanto como corregir: un aviso que siempre suena deja de leerse.
TOLERADAS = {
    "127": (
        "Estación Libertad declara huso 19 con easting 132748, fuera del rango "
        "válido (~160.000-834.000). Su lat/lon es correcta y el UTM no viaja a "
        "la dimensión, así que no afecta. Además no tiene archivos de datos."
    ),
}

# Huso UTM que corresponde a cada comuna del estudio. Talcahuano y Coyhaique
# caen al oeste de -72°, o sea huso 18; el Gran Santiago está al este, huso 19.
HUSO_ESPERADO = {"Talcahuano": 18, "Coyhaique": 18}
HUSO_POR_DEFECTO = 19

# Caja envolvente por ciudad, generosa a propósito: está para atrapar errores de
# 500 km, no para validar a nivel de manzana. Se llama CAJAS y no CIUDADES para
# no chocar con el CIUDADES de geografia.py, que es la definición por comunas.
CAJAS = {
    "santiago": {"lat": (-33.9, -33.2), "lon": (-71.2, -70.4), "region": "Metropolitana"},
    "talcahuano": {"lat": (-36.9, -36.6), "lon": (-73.3, -73.0), "region": "Biobío"},
    "coyhaique": {"lat": (-45.7, -45.4), "lon": (-72.2, -71.9), "region": "Aysén"},
}

# --- inversa de UTM a lat/lon, WGS84 -------------------------------------
# Se implementa a mano en vez de traer pyproj: son 21 filas, la fórmula es
# cerrada y el proyecto ya tiene bastantes dependencias.
_A = 6378137.0
_F = 1 / 298.257223563
_K0 = 0.9996
_E2 = _F * (2 - _F)
_EP2 = _E2 / (1 - _E2)


def utm_a_latlon(este: float, norte: float, huso: int, sur: bool = True) -> tuple[float, float]:
    """Convierte UTM a lat/lon geográficas (WGS84)."""
    x = este - 500000.0
    y = norte - 10000000.0 if sur else norte
    mu = (y / _K0) / (_A * (1 - _E2 / 4 - 3 * _E2**2 / 64 - 5 * _E2**3 / 256))
    e1 = (1 - math.sqrt(1 - _E2)) / (1 + math.sqrt(1 - _E2))
    p1 = (mu
          + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
          + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
          + (151 * e1**3 / 96) * math.sin(6 * mu)
          + (1097 * e1**4 / 512) * math.sin(8 * mu))
    c1 = _EP2 * math.cos(p1) ** 2
    t1 = math.tan(p1) ** 2
    n1 = _A / math.sqrt(1 - _E2 * math.sin(p1) ** 2)
    r1 = _A * (1 - _E2) / (1 - _E2 * math.sin(p1) ** 2) ** 1.5
    d = x / (n1 * _K0)
    lat = p1 - (n1 * math.tan(p1) / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * _EP2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * _EP2 - 3 * c1**2) * d**6 / 720)
    lon0 = math.radians((huso - 1) * 6 - 180 + 3)
    lon = lon0 + (d
                  - (1 + 2 * t1 + c1) * d**3 / 6
                  + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * _EP2 + 24 * t1**2) * d**5 / 120
                  ) / math.cos(p1)
    return math.degrees(lat), math.degrees(lon)


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia sobre la esfera, en kilómetros."""
    r = 6371.0088
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = (math.sin(dp / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(h))


def leer_catalogo(bucket: str | None = None, perfil: str | None = None) -> list[dict]:
    """Lee el catálogo de coordenadas desde `data/raw/` o desde S3."""
    if bucket:
        from src.nube import abrir_sesion
        s3 = abrir_sesion(perfil).client("s3")
        crudo = s3.get_object(Bucket=bucket, Key=f"raw/{CATALOGO}")["Body"].read()
    else:
        ruta = RAW / CATALOGO
        if not ruta.exists():
            raise SystemExit(
                f"No está {ruta}.\n"
                f"  Bájalo con:  python -m src.nube.sincronizar --bucket <bucket> "
                f"bajar --zona raw --aplicar\n"
                f"  O léelo directo de S3 pasando --bucket <bucket> --perfil <perfil>.")
        crudo = ruta.read_bytes()
    texto = crudo.decode(CATALOGO_ENCODING)
    return list(csv.DictReader(io.StringIO(texto)))


def aplicar_correcciones(filas: list[dict]) -> tuple[list[dict], list[dict]]:
    """Devuelve las filas corregidas y el registro de lo que se cambió.

    Falla si una corrección no encuentra el valor crudo que dice corregir. Eso
    significaría que el archivo de origen cambió y la corrección quedó obsoleta:
    aplicarla a ciegas escribiría un valor arbitrario encima de otro dato.
    """
    por_id = {f["ID"]: f for f in filas}
    aplicadas = []
    for c in CORRECCIONES:
        fila = por_id.get(c["id"])
        if fila is None:
            raise SystemExit(f"La corrección {c['id']} apunta a una fila que ya no existe "
                             f"en {CATALOGO}. Revísala antes de seguir.")
        actual = fila[c["campo"]].strip()
        if actual == c["valor_corregido"]:
            log.info("corrección %s ya venía aplicada en el origen; se omite", c["id"])
            continue
        if actual != c["valor_crudo"]:
            raise SystemExit(
                f"La corrección {c['id']} esperaba {c['campo']}={c['valor_crudo']} "
                f"y encontró {actual}. El archivo de origen cambió: revisa la "
                f"corrección en vez de aplicarla a ciegas.")
        fila[c["campo"]] = c["valor_corregido"]
        aplicadas.append(c)
    return filas, aplicadas


def auditar(filas: list[dict]) -> list[str]:
    """Comprueba coherencia interna. Devuelve la lista de problemas encontrados."""
    problemas = []
    vistos = {}
    for f in filas:
        ident, nombre = f["ID"], f["Estación"].strip()
        lat, lon = float(f["Latitud"]), float(f["Longitud"])
        huso = int(f["Huso"])
        partes = f["Coordenadas UTM"].split()
        este, norte = float(partes[0]), float(partes[2])

        ulat, ulon = utm_a_latlon(este, norte, huso)
        d = distancia_km(lat, lon, ulat, ulon)
        if d > 1.0:
            problemas.append(f"{ident} {nombre}: lat/lon y UTM discrepan {d:,.1f} km")

        ciudad = ciudad_de(f["Comuna"])
        esperado = HUSO_ESPERADO.get(f["Comuna"].strip(), HUSO_POR_DEFECTO)
        if huso != esperado and ident not in TOLERADAS:
            problemas.append(f"{ident} {nombre}: huso {huso}, la comuna "
                             f"{f['Comuna']} corresponde al {esperado}")

        if ciudad and ciudad in CAJAS:
            caja = CAJAS[ciudad]
            if not (caja["lat"][0] <= lat <= caja["lat"][1]
                    and caja["lon"][0] <= lon <= caja["lon"][1]):
                problemas.append(f"{ident} {nombre}: ({lat}, {lon}) cae fuera de "
                                 f"{ciudad}; la caja es lat {caja['lat']} lon {caja['lon']}")

        clave = normalizar_nombre(nombre)
        if clave in vistos:
            problemas.append(f"{ident} {nombre}: colisiona al normalizar con "
                             f"{vistos[clave]}")
        vistos[clave] = f"{ident} {nombre}"
    return problemas


def estaciones_con_datos(bucket: str, perfil: str | None) -> dict[str, set[str]]:
    """Nombres de estación que realmente tienen archivos en `raw/`, por ciudad.

    El catálogo trae 21 filas pero solo 19 estaciones tienen serie descargada.
    La dimensión se construye sobre las que tienen datos, no sobre el catálogo
    entero: una fila sin archivos es una estación que nadie puede consultar.
    """
    from src.nube import abrir_sesion
    s3 = abrir_sesion(perfil).client("s3")
    pag = s3.get_paginator("list_objects_v2")
    out: dict[str, set[str]] = {}
    for pagina in pag.paginate(Bucket=bucket, Prefix="raw/"):
        for o in pagina.get("Contents", []):
            k = o["Key"]
            if not k.lower().endswith(".csv") or "/SINCA/" not in k:
                continue
            nombre = k.split("/")[-1]
            est = nombre.split("_")[0] if "_" in nombre else nombre.split(" - ")[0]
            out.setdefault(normalizar_nombre(est), set()).add(k.split("/")[1])
    return out


def cmd_auditar(args) -> int:
    filas = leer_catalogo(args.bucket, args.perfil)
    print(f"  catálogo: {len(filas)} filas\n")

    crudas = [dict(f) for f in filas]
    problemas_antes = auditar(crudas)
    print(f"  auditoría del crudo, sin corregir : {len(problemas_antes)} problema(s)")
    for p in problemas_antes:
        print(f"    · {p}")

    filas, aplicadas = aplicar_correcciones(filas)
    print(f"\n  correcciones aplicadas            : {len(aplicadas)}")
    for c in aplicadas:
        print(f"    · {c['id']} {c['estacion']} · {c['campo']}: "
              f"{c['valor_crudo']} -> {c['valor_corregido']}")
        print(f"        motivo    : {c['motivo']}")
        print(f"        evidencia : {c['evidencia']}")

    problemas = auditar(filas)
    print(f"\n  auditoría tras corregir           : {len(problemas)} problema(s)")
    for p in problemas:
        print(f"    · {p}")

    if TOLERADAS:
        print(f"\n  anomalías toleradas               : {len(TOLERADAS)}")
        for ident, razon in TOLERADAS.items():
            print(f"    · {ident}: {razon}")

    if problemas:
        print("\n  La auditoría encontró problemas sin corrección registrada.")
        return 1
    print("\n  Sin problemas pendientes.")
    return 0


def cmd_construir(args) -> int:
    import pandas as pd

    filas, aplicadas = aplicar_correcciones(leer_catalogo(args.bucket, args.perfil))
    problemas = auditar(filas)
    if problemas:
        print("  No se construye la dimensión con la auditoría en rojo:")
        for p in problemas:
            print(f"    · {p}")
        return 1

    con_datos = estaciones_con_datos(args.bucket, args.perfil) if args.bucket else None
    if con_datos is None:
        print("  Sin --bucket no se puede saber qué estaciones tienen datos; "
              "se construye el catálogo completo y se marca 'tiene_datos' como nulo.")

    registros = []
    for f in filas:
        clave = normalizar_nombre(f["Estación"])
        ciudad = ciudad_de(f["Comuna"])
        registros.append({
            "estacion_id": int(f["ID"]),
            "nombre_sinca": f["Estación"].strip(),
            "clave_cruce": clave,
            "ciudad_id": ciudad,
            "region": f["Región"].strip(),
            "comuna": f["Comuna"].strip(),
            "latitud": float(f["Latitud"]),
            "longitud": float(f["Longitud"]),
            "tiene_datos": (clave in con_datos) if con_datos is not None else None,
            "corregida": any(c["id"] == f["ID"] for c in aplicadas),
            # ciudad_id nulo es lo que mantiene la estación fuera de cualquier
            # promedio por ciudad. `nota` dice por qué, para que quien lo vea en
            # una consulta no tenga que ir a buscarlo al código.
            "nota": motivo_exclusion(f["Comuna"]) if ciudad is None else "",
        })

    df = pd.DataFrame(registros).sort_values("estacion_id").reset_index(drop=True)
    destino = PROCESSED / "dim_estacion"
    asegurar(destino)
    salida = destino / "dim_estacion.parquet"
    df.to_parquet(salida, index=False)

    print(f"  filas escritas : {len(df)}  ->  {salida.relative_to(PROCESSED.parent.parent)}")
    if con_datos is not None:
        n = int(df["tiene_datos"].sum())
        print(f"  con datos      : {n}   sin datos: {len(df) - n}")
        for _, r in df[~df["tiene_datos"].astype(bool)].iterrows():
            print(f"    · sin archivos: {r['estacion_id']} {r['nombre_sinca']} ({r['comuna']})")
    print(f"  corregidas     : {int(df['corregida'].sum())}")
    fuera = df[df["ciudad_id"].isna()]
    if len(fuera):
        print(f"  fuera de alcance: {len(fuera)}  (ciudad_id nulo, no entran en ningún promedio)")
        for _, r in fuera.iterrows():
            print(f"    · {r['estacion_id']} {r['nombre_sinca']} ({r['comuna']})")
            if r["nota"]:
                print(f"        {r['nota']}")
    print("\n  Las columnas de cobertura (primer_dato, ultimo_dato, horas_ventana,")
    print("  horas_validadas_ventana, pct_validado) las rellena el lector de SINCA,")
    print("  que tiene que abrir los 81 archivos de todas formas.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for nombre, fn in (("auditar", cmd_auditar), ("construir", cmd_construir)):
        s = sub.add_parser(nombre)
        s.add_argument("--bucket", default=None,
                       help="lee el catálogo de S3 en vez de data/raw/")
        s.add_argument("--perfil", default=None, help="perfil de ~/.aws/credentials")
        s.set_defaults(fn=fn)

    args = p.parse_args(argv)
    # La consola de Windows viene en cp1252 y rompe los acentos de los mensajes.
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "estaciones.log", encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
