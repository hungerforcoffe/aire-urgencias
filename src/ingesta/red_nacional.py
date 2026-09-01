"""Ingesta de la red nacional de SINCA: catálogo con coordenadas y serie diaria.

Para qué existe
---------------
El estudio son tres ciudades, pero la red de SINCA es el país entero: **213
estaciones en las 16 regiones, 111 de ellas con MP2.5**. El mapa del sitio
mostraba 16 puntos sobre un mapa de Chile, que es una forma de decir que no hay
nada medido en el resto. Lo hay, y este módulo lo trae.

Qué NO hace, a propósito
------------------------
No alimenta `hecho_medicion`. Esa tabla es horaria, con los tres estados de
validación de SINCA por separado, y es la que sostiene el análisis; mezclarle
una serie ya promediada a día rompería su procedencia y dejaría de ser cierto
que cada fila es una medición horaria. La red nacional vive aparte, es contexto
del mapa, y así queda dicho en el sitio.

Sigue valiendo la regla 2 al revés de como suena: la ingesta se amplía a escala
nacional —que es lo que la regla pide— y el análisis se queda en las tres
ciudades.

Serie diaria, no horaria
------------------------
El macro de Airviro acepta `diario.diario`, y devuelve la misma cabecera de
cinco columnas que la horaria. Para 2018-2026 son **3.164 filas por estación en
vez de 75.000**: un pedido de 56 kB por estación y unos 6 MB para las 111. Con
resolución horaria serían varios GB para un mapa que muestra medias mensuales.

Las combinaciones que no existen —`mensual.mensual`, `diario.promedio`— **no
fallan**: devuelven HTTP 200 con un `text/plain` que dice
«psgraph: Could not load macro». Es otra vez la regla 5, y por eso `validar`
mira el tipo de contenido y la cabecera antes de dar por buena una descarga.

Uso
---
    python -m src.ingesta.red_nacional catalogo
    python -m src.ingesta.red_nacional catalogo --todos-los-parametros
    python -m src.ingesta.red_nacional descargar
    python -m src.ingesta.red_nacional descargar --limite 5
    python -m src.ingesta.red_nacional estado
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.ingesta.sinca_cliente import (  # noqa: E402
    UA,
    catalogo_nacional,
    construir_macro,
    construir_url,
)
from src.rutas import LOGS, RAW, asegurar  # noqa: E402

log = logging.getLogger("red-nacional")

DESTINO = RAW / "sinca" / "nacional"
CATALOGO = DESTINO / "sinca_catalogo_nacional.json"
SERIES = DESTINO / "series"

# Ventana del estudio. El fin se recorta a ayer: SINCA publica hasta el día
# anterior y pedir hoy devuelve una fila vacía que no aporta.
INICIO = "180101"
PARAMETRO = "PM25"

# Cabecera que debe traer una respuesta buena. Es la misma de la serie horaria.
CABECERA_ESPERADA = "FECHA (YYMMDD);HORA (HHMM);Registros validados"

# Rango plausible para MP2.5 diario en µg/m³. El máximo no es un límite físico
# sino un detector de unidad equivocada: Coyhaique en su peor día de 2018 llegó
# a 333 como percentil 98 horario, así que una media DIARIA sobre 1.000 es más
# probablemente un error de escala que un episodio.
MP25_MIN, MP25_MAX = 0.0, 1000.0


def hasta_ayer() -> str:
    ayer = date.today().toordinal() - 1
    return date.fromordinal(ayer).strftime("%y%m%d")


# ---------------------------------------------------------------------------
# Validación (regla 5): una descarga no es buena hasta que lo demuestra
# ---------------------------------------------------------------------------

class Rechazada(Exception):
    """La respuesta llegó, pero no es una serie utilizable."""


def validar(cuerpo: bytes, tipo: str | None) -> list[dict]:
    """Comprueba la respuesta y devuelve sus filas ya parseadas.

    En este orden, que es el que separa los modos de fallo:

    1. tamaño > 0
    2. el tipo declarado es CSV — un `text/plain` acá es el error de macro
    3. la cabecera es la conocida
    4. la primera columna parsea como fecha YYMMDD
    5. queda al menos una fila con valor, y los valores están en rango
    """
    if not cuerpo:
        raise Rechazada("cuerpo vacío")

    if tipo and "csv" not in tipo.lower():
        pista = cuerpo[:120].decode("latin-1", "replace").strip()
        raise Rechazada(f"tipo de contenido {tipo!r}, no CSV — respuesta: {pista!r}")

    texto = cuerpo.decode("latin-1")
    if not texto.startswith(CABECERA_ESPERADA):
        raise Rechazada(f"cabecera inesperada: {texto[:80]!r}")

    lector = csv.reader(io.StringIO(texto), delimiter=";")
    next(lector, None)

    filas, con_valor = [], 0
    for fila in lector:
        if len(fila) < 3 or not fila[0].strip():
            continue
        crudo = fila[0].strip()
        if len(crudo) != 6 or not crudo.isdigit():
            raise Rechazada(f"primera columna no es una fecha YYMMDD: {crudo!r}")
        aa, mm, dd = crudo[:2], crudo[2:4], crudo[4:6]
        if not ("01" <= mm <= "12" and "01" <= dd <= "31"):
            raise Rechazada(f"fecha fuera de rango: {crudo!r}")

        # Los tres estados de validación son excluyentes: el valor está en uno.
        valor = None
        estado = None
        for col, nombre in ((2, "validado"), (3, "preliminar"), (4, "no_validado")):
            if len(fila) > col and fila[col].strip():
                valor = fila[col].strip().replace(",", ".")
                estado = nombre
                break
        if valor is not None:
            try:
                v = float(valor)
            except ValueError:
                continue
            if not (MP25_MIN <= v <= MP25_MAX):
                log.warning("valor fuera de rango plausible, se omite: %s en %s", v, crudo)
                continue
            con_valor += 1
        else:
            v = None
        filas.append({"fecha": f"20{aa}-{mm}-{dd}", "mp25": v, "estado": estado})

    if con_valor == 0:
        raise Rechazada(f"{len(filas)} filas y ninguna con valor")
    return filas


# ---------------------------------------------------------------------------
# Subcomando: catálogo
# ---------------------------------------------------------------------------

def cmd_catalogo(args) -> int:
    asegurar(DESTINO)
    ses = requests.Session()
    ses.headers["User-Agent"] = UA

    filtro = None if args.todos_los_parametros else PARAMETRO
    log.info("recorriendo las 16 regiones%s…",
             "" if filtro is None else f" (solo estaciones con {filtro})")
    estaciones = catalogo_nacional(ses, pausa=args.pausa, solo_parametro=filtro)

    sin_coord = [e for e in estaciones if e["lat"] is None]
    ficha = {
        "consultado": date.today().isoformat(),
        "fuente": "https://sinca.mma.gob.cl/index.php/region/index/id/<region>",
        "filtro_parametro": filtro,
        "n_estaciones": len(estaciones),
        "n_sin_coordenadas": len(sin_coord),
        "estaciones": estaciones,
    }

    if not estaciones:
        log.error("el catálogo vino vacío; no se escribe nada")
        return 1

    # La zona cruda no se sobrescribe a ciegas: si ya hay catálogo y el nuevo
    # trae menos estaciones, se avisa y hay que forzar. Una caída de red que
    # devuelva media red no debe reemplazar en silencio a un catálogo completo.
    if CATALOGO.exists() and not args.forzar:
        previo = json.loads(CATALOGO.read_text(encoding="utf-8"))
        if len(estaciones) < previo.get("n_estaciones", 0):
            log.error("el catálogo nuevo trae %d estaciones y el guardado tiene %d. "
                      "No se sobrescribe: revisa y usa --forzar si es correcto.",
                      len(estaciones), previo.get("n_estaciones", 0))
            return 1

    CATALOGO.write_text(json.dumps(ficha, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  catálogo: {len(estaciones)} estaciones -> {CATALOGO}")
    print(f"  sin coordenadas: {len(sin_coord)}"
          + ("" if not sin_coord else "  " + ", ".join(e["nombre"] for e in sin_coord[:8])))
    por_region: dict[str, int] = {}
    for e in estaciones:
        por_region[e["region_romana"]] = por_region.get(e["region_romana"], 0) + 1
    print("  por región: " + " ".join(f"{k}={v}" for k, v in por_region.items()))
    return 0


# ---------------------------------------------------------------------------
# Subcomando: descargar
# ---------------------------------------------------------------------------

def cmd_descargar(args) -> int:
    if not CATALOGO.exists():
        raise SystemExit(f"No hay catálogo en {CATALOGO}.\n"
                         f"  Constrúyelo con: python -m src.ingesta.red_nacional catalogo")
    ficha = json.loads(CATALOGO.read_text(encoding="utf-8"))
    estaciones = [e for e in ficha["estaciones"] if e["lat"] is not None]
    if args.limite:
        estaciones = estaciones[:args.limite]

    asegurar(SERIES)
    ses = requests.Session()
    ses.headers["User-Agent"] = UA
    fin = args.hasta or hasta_ayer()

    ok, saltadas, rechazadas = 0, 0, []
    for i, e in enumerate(estaciones, 1):
        nombre = f"sinca_{e['region_macro']}_{e['codigo']}_mp25_diario.csv"
        destino = SERIES / nombre

        # Regla 3: la zona cruda es inmutable. Un archivo ya descargado no se
        # vuelve a pedir salvo que se pida explícitamente.
        if destino.exists() and not args.rehacer:
            saltadas += 1
            continue

        macro = construir_macro(e["region_macro"], e["codigo"], PARAMETRO,
                                "diario", "diario")
        url = construir_url(macro, INICIO, fin)
        try:
            r = ses.get(url, timeout=120)
            r.raise_for_status()
            filas = validar(r.content, r.headers.get("content-type"))
        except requests.HTTPError as ex:
            # 403 y 404 no significan lo mismo y no se tratan igual.
            codigo = ex.response.status_code if ex.response is not None else "?"
            motivo = ("bloqueo o permiso (revisa si es la IP: el proyecto está tras CGNAT)"
                      if codigo == 403 else "no existe")
            rechazadas.append({"estacion": e["nombre"], "codigo": e["codigo"],
                               "motivo": f"HTTP {codigo} — {motivo}"})
            log.error("%s (%s): HTTP %s", e["nombre"], e["codigo"], codigo)
            continue
        except (Rechazada, requests.RequestException) as ex:
            rechazadas.append({"estacion": e["nombre"], "codigo": e["codigo"],
                               "motivo": f"{type(ex).__name__}: {ex}"})
            log.error("%s (%s): %s", e["nombre"], e["codigo"], ex)
            continue

        destino.write_bytes(r.content)
        ok += 1
        log.info("[%d/%d] %s (%s): %d filas", i, len(estaciones), e["nombre"],
                 e["codigo"], len(filas))
        if args.pausa:
            time.sleep(args.pausa)

    print(f"\n  descargadas {ok}   ya estaban {saltadas}   rechazadas {len(rechazadas)}")
    if rechazadas:
        # La cola de errores queda escrita: un rechazo no se pierde en el log.
        cola = DESTINO / "_rechazadas.json"
        cola.write_text(json.dumps(rechazadas, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        print(f"  cola de errores -> {cola}")
        for r in rechazadas[:10]:
            print(f"    · {r['estacion']} ({r['codigo']}): {r['motivo']}")
    return 0


def cmd_estado(args) -> int:
    if not CATALOGO.exists():
        print("  sin catálogo todavía")
        return 0
    ficha = json.loads(CATALOGO.read_text(encoding="utf-8"))
    hay = sorted(SERIES.glob("*.csv")) if SERIES.exists() else []
    con_coord = sum(1 for e in ficha["estaciones"] if e["lat"] is not None)
    print(f"  catálogo consultado el {ficha['consultado']}")
    print(f"  estaciones: {ficha['n_estaciones']}  con coordenadas: {con_coord}")
    print(f"  series descargadas: {len(hay)}")
    if hay:
        peso = sum(p.stat().st_size for p in hay)
        print(f"  peso en disco: {peso / 1e6:.1f} MB")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("catalogo", help="lista la red nacional con coordenadas")
    c.add_argument("--todos-los-parametros", action="store_true",
                   help="no filtrar a las que miden MP2.5")
    c.add_argument("--pausa", type=float, default=0.4, help="segundos entre fichas")
    c.add_argument("--forzar", action="store_true",
                   help="sobrescribir aunque el catálogo nuevo sea más chico")
    c.set_defaults(fn=cmd_catalogo)

    d = sub.add_parser("descargar", help="baja la serie diaria de MP2.5 de cada estación")
    d.add_argument("--limite", type=int, default=0, help="0 = todas")
    d.add_argument("--hasta", default=None, metavar="AAMMDD")
    d.add_argument("--pausa", type=float, default=0.5)
    d.add_argument("--rehacer", action="store_true",
                   help="volver a pedir las que ya están en la zona cruda")
    d.set_defaults(fn=cmd_descargar)

    sub.add_parser("estado", help="qué hay descargado").set_defaults(fn=cmd_estado)

    args = p.parse_args(argv)
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "red_nacional.log", encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
