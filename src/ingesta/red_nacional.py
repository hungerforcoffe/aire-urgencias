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
    python -m src.ingesta.red_nacional sondeo
    python -m src.ingesta.red_nacional viento
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
from dataclasses import asdict
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.ingesta.sinca_cliente import (  # noqa: E402
    FICHA,
    UA,
    catalogo_nacional,
    construir_macro,
    construir_url,
    series_estacion,
)
from src.rutas import LOGS, RAW, asegurar  # noqa: E402

log = logging.getLogger("red-nacional")

DESTINO = RAW / "sinca" / "nacional"
CATALOGO = DESTINO / "sinca_catalogo_nacional.json"
SONDEO = DESTINO / "sinca_series_nacional.json"
SERIES = DESTINO / "series"
# Las horarias van aparte: son otra resolucion y otro parametro, y mezclarlas
# con la diaria haria que `estado` contara como series lo que son mitades de
# un par.
SERIES_HORARIAS = DESTINO / "horario"

# Ventana del estudio. El fin se recorta a ayer: SINCA publica hasta el día
# anterior y pedir hoy devuelve una fila vacía que no aporta.
INICIO = "180101"
PARAMETRO = "PM25"

# Cabecera que debe traer una respuesta buena. Es la misma de la serie horaria.
CABECERA_ESPERADA = "FECHA (YYMMDD);HORA (HHMM);Registros validados"

# La meteorología trae dos columnas menos: no publica los tres estados de
# validación, solo el valor. Lo común a ambas es este prefijo.
CABECERA_HORARIA = "FECHA (YYMMDD);HORA (HHMM)"

# Rangos de las series horarias. No son límites físicos sino detectores de
# unidad o de columna equivocada. La dirección del viento en grados solo puede
# caer en [0, 360]; un 999 sería el código de dato faltante de otro sistema
# colándose como medición. El techo de MP2.5 horario es más alto que el diario
# (1.000): un promedio de 24 horas suaviza lo que una hora de episodio no.
RANGO_HORARIO = {"mp25": (0.0, 3000.0), "wdir": (0.0, 360.0)}

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


def validar_horaria(cuerpo: bytes, tipo: str | None, parametro: str) -> list[dict]:
    """Valida una serie **horaria** y devuelve fecha, hora y valor.

    No es la misma función que `validar`: aquella es para la serie diaria de
    MP2.5 y descarta la hora, que para una media diaria no existe. La rosa
    necesita justamente la hora, porque cruza la concentración con la dirección
    del viento **de la misma hora**.

    Y hay un modo de fallo propio de la meteorología que esta función existe
    para atrapar. Pedir la dirección del viento sin el sufijo `_spec` devuelve
    la **rosa de frecuencias** de 16 sectores: 400 bytes, HTTP 200,
    `application/csv` y la misma cabecera `FECHA (YYMMDD);HORA (HHMM)` que una
    serie legítima. Lo único que las separa es que su primera columna dice
    «352,5-7,5» en vez de una fecha. Un fallo que se ve como un éxito hasta el
    último chequeo posible: la regla 5 del proyecto en su forma más pura.
    """
    if not cuerpo:
        raise Rechazada("cuerpo vacío")
    if tipo and "csv" not in tipo.lower():
        pista = cuerpo[:120].decode("latin-1", "replace").strip()
        raise Rechazada(f"tipo de contenido {tipo!r}, no CSV — respuesta: {pista!r}")

    texto = cuerpo.decode("latin-1")
    if not texto.startswith(CABECERA_HORARIA):
        raise Rechazada(f"cabecera inesperada: {texto[:80]!r}")
    # Los tres estados de validación solo existen en el árbol de contaminantes.
    # La meteorología publica una columna sola, y llamarla «validado» sería
    # atribuirle una marca de calidad que SINCA no da.
    con_estados = texto.startswith(CABECERA_ESPERADA)

    lo, hi = RANGO_HORARIO[parametro]
    lector = csv.reader(io.StringIO(texto), delimiter=";")
    next(lector, None)

    filas, con_valor, fuera = [], 0, 0
    for fila in lector:
        if len(fila) < 3 or not fila[0].strip():
            continue
        crudo = fila[0].strip()
        if len(crudo) != 6 or not crudo.isdigit():
            raise Rechazada(
                f"primera columna no es una fecha YYMMDD: {crudo!r}. "
                f"Si dice algo como '352,5-7,5' esto no es la serie sino la rosa "
                f"de frecuencias: falta el sufijo _spec en el macro.")
        aa, mm, dd = crudo[:2], crudo[2:4], crudo[4:6]
        if not ("01" <= mm <= "12" and "01" <= dd <= "31"):
            raise Rechazada(f"fecha fuera de rango: {crudo!r}")
        hora = fila[1].strip().zfill(4)
        if len(hora) != 4 or not hora.isdigit():
            raise Rechazada(f"segunda columna no es una hora HHMM: {fila[1]!r}")

        valor, estado = None, None
        for col, nombre in ((2, "validado"), (3, "preliminar"), (4, "no_validado")):
            if len(fila) > col and fila[col].strip():
                valor = fila[col].strip().replace(",", ".")
                estado = nombre if con_estados else None
                break
        v = None
        if valor is not None:
            try:
                v = float(valor)
            except ValueError:
                v = None
            if v is not None and not (lo <= v <= hi):
                fuera += 1
                v = None
            elif v is not None:
                con_valor += 1
        filas.append({"fecha": f"20{aa}-{mm}-{dd}", "hora": hora, "valor": v,
                      "estado": estado})

    if fuera:
        log.warning("%s: %d valores fuera de [%s, %s]; se dejan en nulo",
                    parametro, fuera, lo, hi)
    if con_valor == 0:
        raise Rechazada(f"{len(filas)} filas y ninguna con valor")
    return filas


# ---------------------------------------------------------------------------
# Subcomando: sondeo de series (metadatos, no datos)
# ---------------------------------------------------------------------------

def cmd_sondeo(args) -> int:
    """Qué series declara cada ficha, con su rango de fechas. No baja series.

    Es un paso barato —111 páginas de ~30 kB— que responde antes de gastar
    ancho de banda la única pregunta que decide la etapa: cuántas estaciones
    de la red nacional tienen anemómetro y en qué período. La ficha publica el
    rango real de cada serie, así que se sabe sin descargar ni una fila.
    """
    if not CATALOGO.exists():
        raise SystemExit(f"No hay catálogo en {CATALOGO}.\n"
                         f"  Constrúyelo con: python -m src.ingesta.red_nacional catalogo")
    ficha = json.loads(CATALOGO.read_text(encoding="utf-8"))
    estaciones = [e for e in ficha["estaciones"] if e["ficha_id"]]
    if args.limite:
        estaciones = estaciones[:args.limite]

    ses = requests.Session()
    ses.headers["User-Agent"] = UA

    salida, fallidas = [], []
    for i, e in enumerate(estaciones, 1):
        try:
            series = series_estacion(e["ficha_id"], ses)
        except Exception as ex:  # noqa: BLE001 — una ficha caída no aborta el resto
            fallidas.append({"estacion": e["nombre"], "ficha_id": e["ficha_id"],
                             "motivo": f"{type(ex).__name__}: {ex}"})
            log.error("ficha %s (%s): %s", e["ficha_id"], e["nombre"], ex)
            continue
        salida.append({
            "region_macro": e["region_macro"], "codigo": e["codigo"],
            "ficha_id": e["ficha_id"], "nombre": e["nombre"], "comuna": e["comuna"],
            "series": [asdict(s) | {"macro_descarga": s.macro_descarga} for s in series],
        })
        log.info("[%d/%d] %s: %d series", i, len(estaciones), e["nombre"], len(series))
        if args.pausa:
            time.sleep(args.pausa)

    if not salida:
        log.error("ninguna ficha respondió; no se escribe nada")
        return 1

    con = {p: [x for x in salida if any(s["parametro"] == p for s in x["series"])]
           for p in ("WDIR", "WSPD", "TEMP")}
    doc = {
        "consultado": date.today().isoformat(),
        "fuente": FICHA.format("<ficha_id>"),
        "n_estaciones": len(salida),
        "n_fichas_fallidas": len(fallidas),
        "conteos": {p: len(v) for p, v in con.items()},
        "estaciones": salida,
        "fallidas": fallidas,
    }
    asegurar(DESTINO)
    SONDEO.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"  sondeo de {len(salida)} fichas -> {SONDEO}")
    if fallidas:
        print(f"  fichas que no respondieron: {len(fallidas)}")
    for p, v in con.items():
        print(f"  con {p}: {len(v)} de {len(salida)}")

    # Lo que decide la etapa: de las que tienen dirección del viento, cuántas
    # la tienen dentro de la ventana del estudio y por cuánto tiempo.
    utiles = []
    for x in con["WDIR"]:
        for s in x["series"]:
            if s["parametro"] != "WDIR":
                continue
            if s["hasta"] >= INICIO:      # AAMMDD compara bien como texto
                utiles.append((x["nombre"], x["comuna"], max(s["desde"], INICIO), s["hasta"]))
                break
    print(f"\n  con WDIR dentro de la ventana ({INICIO} en adelante): {len(utiles)}")
    for n, c, d, h in utiles[:12]:
        print(f"    - {n} ({c}): {d} a {h}")
    if len(utiles) > 12:
        print(f"    ... y {len(utiles) - 12} mas")
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


# ---------------------------------------------------------------------------
# Subcomando: viento (par horario dirección + MP2.5, para la rosa)
# ---------------------------------------------------------------------------

def serie_de(estacion: dict, parametro: str, macro: str | None = None) -> dict | None:
    """La serie de un parámetro que más horas puede aportar.

    Una ficha puede declarar el mismo parámetro dos veces, medido por sensores a
    distinta altura: Parque O'Higgins publica dirección del viento en
    `horario_010` (10 m) y en `horario_000` (altura sin informar). Se elige la
    que llega más lejos en el tiempo y, a igual fin, la que empieza antes.

    El macro NO se construye: se toma el que declara la ficha. El número es la
    altura del sensor y cambia de estación en estación, así que inventarlo sería
    asumir esquema — la regla 6 del proyecto.
    """
    cands = [s for s in estacion["series"] if s["parametro"] == parametro
             and (macro is None or s["macro"] == macro)]
    if not cands:
        return None
    return max(cands, key=lambda s: (s["hasta"], -int(s["desde"])))


def cmd_viento(args) -> int:
    """Baja el par horario que hace falta para la rosa: dirección y MP2.5.

    La rosa de contaminación cruza la concentración con el sector del que venía
    el viento **en la misma hora**, así que las dos series tienen que ser
    horarias y de la misma estación. La rosa de frecuencias que publica SINCA no
    sirve de reemplazo: dice cuánto sopló de cada lado, no cuánto se midió.

    Solo se piden las estaciones que el sondeo dice que tienen dirección del
    viento dentro de la ventana. Las demás se quedan sin rosa, que es lo que el
    sitio ya sabe mostrar para tres de las dieciséis del estudio.
    """
    if not SONDEO.exists():
        raise SystemExit(f"No hay sondeo en {SONDEO}.\n"
                         f"  Constrúyelo con: python -m src.ingesta.red_nacional sondeo")
    doc = json.loads(SONDEO.read_text(encoding="utf-8"))

    objetivo = []
    sin_viento, sin_horario = [], []
    for x in doc["estaciones"]:
        wdir = serie_de(x, "WDIR")
        if not wdir or wdir["hasta"] < INICIO:
            sin_viento.append(x["nombre"])
            continue
        # El MP2.5 tiene que ser el horario, no el diario: una media de 24 horas
        # no se puede repartir entre los sectores por los que rotó el viento.
        pm = serie_de(x, PARAMETRO, macro=f"{PARAMETRO}.horario.horario")
        if not pm or pm["hasta"] < INICIO:
            sin_horario.append(x["nombre"])
            continue
        objetivo.append((x, wdir, pm))
    if args.limite:
        objetivo = objetivo[:args.limite]

    print(f"  estaciones sondeadas        : {len(doc['estaciones'])}")
    print(f"  sin direccion de viento util: {len(sin_viento)}")
    print(f"  sin MP2.5 horario           : {len(sin_horario)}")
    print(f"  a descargar                 : {len(objetivo)} estaciones "
          f"({len(objetivo) * 2} peticiones)")

    asegurar(SERIES_HORARIAS)
    ses = requests.Session()
    ses.headers["User-Agent"] = UA
    fin = args.hasta or hasta_ayer()

    ok, saltadas, rechazadas, bytes_ok = 0, 0, [], 0
    for i, (x, wdir, pm) in enumerate(objetivo, 1):
        for etiqueta, s in (("wdir", wdir), ("mp25", pm)):
            destino = (SERIES_HORARIAS
                       / f"sinca_{x['region_macro']}_{x['codigo']}_{etiqueta}_horario.csv")
            # Regla 3: lo ya descargado no se vuelve a pedir.
            if destino.exists() and not args.rehacer:
                saltadas += 1
                continue
            url = construir_url(s["macro_descarga"], INICIO, fin)
            try:
                r = ses.get(url, timeout=300)
                r.raise_for_status()
                filas = validar_horaria(r.content, r.headers.get("content-type"), etiqueta)
            except requests.HTTPError as ex:
                codigo = ex.response.status_code if ex.response is not None else "?"
                motivo = ("bloqueo o permiso (revisa si es la IP: el proyecto está "
                          "tras CGNAT)" if codigo == 403 else "no existe")
                rechazadas.append({"estacion": x["nombre"], "codigo": x["codigo"],
                                   "parametro": etiqueta, "macro": s["macro_descarga"],
                                   "motivo": f"HTTP {codigo} — {motivo}"})
                log.error("%s %s: HTTP %s", x["nombre"], etiqueta, codigo)
                continue
            except (Rechazada, requests.RequestException) as ex:
                rechazadas.append({"estacion": x["nombre"], "codigo": x["codigo"],
                                   "parametro": etiqueta, "macro": s["macro_descarga"],
                                   "motivo": f"{type(ex).__name__}: {ex}"})
                log.error("%s %s: %s", x["nombre"], etiqueta, ex)
                continue

            destino.write_bytes(r.content)
            ok += 1
            bytes_ok += len(r.content)
            log.info("[%d/%d] %s %s: %d filas, %.1f kB", i, len(objetivo), x["nombre"],
                     etiqueta, len(filas), len(r.content) / 1024)
            if args.pausa:
                time.sleep(args.pausa)

    print(f"\n  descargadas {ok}   ya estaban {saltadas}   rechazadas {len(rechazadas)}")
    print(f"  peso bajado: {bytes_ok / 1e6:.1f} MB")
    if rechazadas:
        cola = DESTINO / "_rechazadas_horario.json"
        cola.write_text(json.dumps(rechazadas, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        print(f"  cola de errores -> {cola}")
        for r in rechazadas[:10]:
            print(f"    - {r['estacion']} ({r['parametro']}): {r['motivo']}")
    return 0


def cmd_estado(args) -> int:
    if not CATALOGO.exists():
        print("  sin catálogo todavía")
        return 0
    ficha = json.loads(CATALOGO.read_text(encoding="utf-8"))
    hay = sorted(SERIES.glob("*.csv")) if SERIES.exists() else []
    hor = sorted(SERIES_HORARIAS.glob("*.csv")) if SERIES_HORARIAS.exists() else []
    con_coord = sum(1 for e in ficha["estaciones"] if e["lat"] is not None)
    print(f"  catálogo consultado el {ficha['consultado']}")
    print(f"  estaciones: {ficha['n_estaciones']}  con coordenadas: {con_coord}")
    print(f"  series diarias descargadas: {len(hay)}")
    print(f"  series horarias para la rosa: {len(hor)} "
          f"({len(hor) // 2} estaciones con el par completo)")
    if hay:
        peso = sum(p.stat().st_size for p in hay + hor)
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

    v = sub.add_parser("viento",
                       help="baja el par horario (direccion + MP2.5) para la rosa")
    v.add_argument("--limite", type=int, default=0, help="0 = todas")
    v.add_argument("--hasta", default=None, metavar="AAMMDD")
    v.add_argument("--pausa", type=float, default=0.4)
    v.add_argument("--rehacer", action="store_true",
                   help="volver a pedir las que ya estan en la zona cruda")
    v.set_defaults(fn=cmd_viento)

    so = sub.add_parser("sondeo",
                        help="qué series declara cada ficha, con su rango de fechas")
    so.add_argument("--limite", type=int, default=0, help="0 = todas")
    so.add_argument("--pausa", type=float, default=0.35)
    so.set_defaults(fn=cmd_sondeo)

    sub.add_parser("estado", help="qué hay descargado").set_defaults(fn=cmd_estado)

    args = p.parse_args(argv)
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "red_nacional.log", encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
