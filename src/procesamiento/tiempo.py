"""Construye `dim_tiempo` con semanas epidemiológicas MMWR, y las valida.

Por qué no sirve la semana ISO
------------------------------
El DEIS numera sus semanas con la convención **MMWR**: van de domingo a sábado,
y la semana 1 de un año es la primera que tiene al menos cuatro días en ese año.
La semana ISO va de lunes a domingo y usa otra regla de asignación.

La diferencia no es cosmética. Comprobado sobre el archivo real de 2026:

    2026-01-01  jueves    DEIS = semana 53 (de 2025)    ISO = 2026-W01
    2026-01-04  domingo   DEIS = semana 1               ISO = 2026-W01
    2026-01-05  lunes     DEIS = semana 1               ISO = 2026-W02

Este error no rompe nada. Produce una tabla completa que se grafica bien y da
correlaciones plausibles, solo que el MP2.5 queda alineado contra la semana
equivocada de urgencias, con un desfase de hasta seis días. El estudio mide
rezagos de 0 a 2 semanas: un corrimiento sistemático de casi una semana es del
mismo orden que el efecto que se busca medir.

Por eso **`datetime.isocalendar()` y `strftime('%V')` no se usan en el
proyecto**, y por eso `validar` existe: contrasta la semana calculada aquí
contra la columna `semana` del DEIS, fila por fila. Si no coinciden al 100%, se
para.

Uso
---
    python -m src.procesamiento.tiempo construir
    python -m src.procesamiento.tiempo validar
    python -m src.procesamiento.tiempo validar --anios 2021,2026
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.rutas import INTERIM, LOGS, PROCESSED, RAW, asegurar  # noqa: E402

log = logging.getLogger("tiempo")

# Ventana del estudio. El fin es el ultimo SABADO con dato, para que la ultima
# semana epidemiologica este completa: el DEIS llega al 2026-08-24 (lunes) y la
# semana 34 quedaria con dos dias.
INICIO = dt.date(2018, 1, 1)
FIN = dt.date(2026, 8, 22)

DIAS = ("domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado")

# Estaciones meteorologicas del hemisferio SUR. Invierno es junio-agosto, que es
# cuando coinciden la calefaccion a lena y la circulacion viral: el periodo que
# el estudio necesita aislar.
ESTACIONES = {12: "verano", 1: "verano", 2: "verano",
              3: "otoño", 4: "otoño", 5: "otoño",
              6: "invierno", 7: "invierno", 8: "invierno",
              9: "primavera", 10: "primavera", 11: "primavera"}

# --- PERIODO DE PANDEMIA -----------------------------------------------------
# DECISION PENDIENTE DEL EQUIPO. Los cortes de abajo son un valor por defecto
# defendible, no un consenso. Cambiarlos cambia una variable de control del
# modelo, asi que conviene acordarlos antes de correr el analisis.
#
#   2020-03-03  primer caso confirmado en Chile
#   2021-09-30  fin del estado de excepcion constitucional por catastrofe
#   2023-08-31  fin de la alerta sanitaria
#
# El corte que mas pesa es el primero: durante 2020 y 2021 las consultas de
# urgencia respiratoria cayeron por confinamiento, mascarilla y cierre de
# colegios, no porque bajara el MP2.5. Sin esta variable el modelo atribuiria
# esa caida a la exposicion.
PANDEMIA_INICIO = dt.date(2020, 3, 3)
PANDEMIA_FIN_RESTRICCIONES = dt.date(2021, 9, 30)
PANDEMIA_FIN_ALERTA = dt.date(2023, 8, 31)


def periodo_pandemia(f: dt.date) -> str:
    if f < PANDEMIA_INICIO:
        return "prepandemia"
    if f <= PANDEMIA_FIN_RESTRICCIONES:
        return "pandemia_restricciones"
    if f <= PANDEMIA_FIN_ALERTA:
        return "pandemia_transicion"
    return "pospandemia"


def _domingo_de(f: dt.date) -> dt.date:
    """Domingo que abre la semana MMWR de `f`."""
    # weekday(): lunes=0 … domingo=6. Se recoloca a domingo=0.
    return f - dt.timedelta(days=(f.weekday() + 1) % 7)


def semana_mmwr(f: dt.date) -> tuple[int, int]:
    """Devuelve (año epidemiológico, número de semana) según MMWR.

    El año lo decide el **miércoles** de la semana, que es el cuarto de los siete
    días: si el miércoles cae en el año nuevo, la semana tiene al menos cuatro
    días en él y por tanto le pertenece. Es la misma regla de «al menos cuatro
    días» escrita de forma que no hay que contar.
    """
    domingo = _domingo_de(f)
    anio = (domingo + dt.timedelta(days=3)).year
    # Domingo que abre la semana 1 de ese año epidemiológico.
    enero1 = dt.date(anio, 1, 1)
    dom1 = _domingo_de(enero1)
    if (dom1 + dt.timedelta(days=3)).year < anio:
        dom1 += dt.timedelta(days=7)      # esa semana aún pertenece al año anterior
    return anio, (domingo - dom1).days // 7 + 1


def construir(inicio: dt.date = INICIO, fin: dt.date = FIN) -> list[dict]:
    filas = []
    f = inicio
    while f <= fin:
        anio_epi, sem = semana_mmwr(f)
        domingo = _domingo_de(f)
        sabado = domingo + dt.timedelta(days=6)
        filas.append({
            "fecha": f,
            "anio": f.year,
            "mes": f.month,
            "dia": f.day,
            "dia_semana": (f.weekday() + 1) % 7,          # 0 = domingo, como MMWR
            "nombre_dia": DIAS[(f.weekday() + 1) % 7],
            "anio_epi": anio_epi,
            "semana_epi": sem,
            "semana_id": f"{anio_epi}-W{sem:02d}",         # clave de unión semanal
            "inicio_semana": domingo,
            "fin_semana": sabado,
            "semana_completa": domingo >= inicio and sabado <= fin,
            "estacion_anio": ESTACIONES[f.month],
            "es_invierno": ESTACIONES[f.month] == "invierno",
            "periodo_pandemia": periodo_pandemia(f),
        })
        f += dt.timedelta(days=1)
    return filas


# --- validación contra el DEIS ----------------------------------------------
# Se extrae con expresión regular sobre el texto crudo en vez de partir cada
# línea en 15-19 campos: son ~9 millones de filas por año y solo hacen falta dos
# columnas, la fecha y la semana.
#
# Hay DOS formatos de fecha, y el lector no supone cuál (regla 6):
#
#   2021-2026   `;04/06/2021;22;`                            dd/mm/aaaa
#   2020        `;Wed Sep 23 00:00:00 GMT-04:00 2020;39;`    Date.toString() de Java
#
# 2020 además viene SIN fila de cabecera: la primera línea ya es un dato.
MESES = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), start=1)}

VARIANTES = {
    "dd/mm/aaaa": re.compile(r";(\d{2}/\d{2}/\d{4});(\d{1,2});"),
    "java_date": re.compile(
        r";\w{3} (\w{3}) (\d{2}) \d{2}:\d{2}:\d{2} GMT[+-]\d{2}:\d{2} (\d{4});(\d{1,2});"),
}
TROZO = 32 * 1024 * 1024


def _abrir(ruta: Path):
    """Devuelve (flujo binario, nombre) sea la ruta un ZIP o un CSV suelto.

    Los años 2018 y 2019 no tienen CSV dentro del ZIP —solo un .mdb de Access—,
    así que se validan contra el CSV que produce `deis_access.py` en interim/.
    """
    if ruta.suffix.lower() == ".csv":
        return open(ruta, "rb"), ruta.name
    z = zipfile.ZipFile(ruta)
    dentro = z.infolist()
    csvs = [i.filename for i in dentro if i.filename.lower().endswith(".csv")]
    if not csvs:
        otros = ", ".join(i.filename for i in dentro)
        z.close()
        raise ValueError(f"sin CSV dentro; contiene {otros}")
    return z.open(csvs[0]), csvs[0]


def pares_del_deis(ruta: Path) -> dict[dt.date, set[int]]:
    """Extrae los pares (fecha, semana) distintos de un año del DEIS."""
    vistos: dict[dt.date, set[int]] = {}
    fh, nombre = _abrir(ruta)
    cola = ""
    leidos = 0
    variante = None
    try:
        while True:
            bloque = fh.read(TROZO)
            if not bloque:
                break
            leidos += len(bloque)
            texto = cola + bloque.decode("latin-1")
            for etiqueta, patron in VARIANTES.items():
                hallazgos = patron.findall(texto)
                if not hallazgos:
                    continue
                if variante is None:
                    variante = etiqueta
                    log.info("%s: variante de fecha «%s»", ruta.name, etiqueta)
                for grupos in hallazgos:
                    if etiqueta == "dd/mm/aaaa":
                        d, m, a = (int(x) for x in grupos[0].split("/"))
                        sem = int(grupos[1])
                    else:
                        mes, d, a, sem = grupos
                        m, d, a, sem = MESES[mes], int(d), int(a), int(sem)
                    vistos.setdefault(dt.date(a, m, d), set()).add(sem)
            cola = texto[-60:]      # una coincidencia puede quedar partida
    finally:
        fh.close()
    log.info("%s: %.1f MB leídos, %d fechas", ruta.name, leidos / 1024**2, len(vistos))
    # Regla 5: un archivo que se leyó entero y no dio ni una fecha no es un
    # archivo vacío, es un lector que no lo entendió. No puede pasar por bueno.
    if not vistos:
        raise ValueError(f"se leyeron {leidos / 1024**2:.0f} MB de {nombre} y no salió "
                         f"ninguna fecha: el formato no coincide con ninguna variante conocida")
    return vistos


def fuentes_por_anio(filtro: str | None) -> dict[str, list[Path]]:
    """Candidatos por año: el ZIP crudo primero, y el CSV de interim como respaldo.

    2018 y 2019 solo existen como .mdb dentro del ZIP; su CSV lo produce
    `deis_access.py`. Se prueban en orden y se usa el primero que dé fechas.
    """
    porque: dict[str, list[Path]] = {}
    for ruta in sorted(RAW.glob("deis/*.zip")) + sorted(INTERIM.glob("deis/*.csv")):
        digitos = [t for t in re.findall(r"20\d{2}", ruta.name)]
        if not digitos:
            continue
        anio = digitos[0]
        if filtro and anio not in filtro:
            continue
        porque.setdefault(anio, []).append(ruta)
    return dict(sorted(porque.items()))


def cmd_validar(args) -> int:
    fuentes = fuentes_por_anio(args.anios)
    if not fuentes:
        raise SystemExit(f"No hay archivos del DEIS en {RAW / 'deis'} ni en {INTERIM / 'deis'}")

    total_dias = total_ok = 0
    discrepan, saltados = [], []
    for anio, rutas in fuentes.items():
        pares, usada, motivos = None, None, []
        for ruta in rutas:                      # ZIP primero, CSV de interim después
            try:
                pares = pares_del_deis(ruta)
                usada = ruta
                break
            except ValueError as e:
                motivos.append(f"{ruta.name}: {e}")
        if pares is None:
            saltados.append((anio, "; ".join(motivos)))
            print(f"  {anio}  SALTADO — {motivos[0]}")
            continue

        ok = malos = 0
        for fecha, semanas in sorted(pares.items()):
            if len(semanas) > 1:
                discrepan.append((fecha, sorted(semanas), "el DEIS se contradice"))
                continue
            deis = next(iter(semanas))
            _, mia = semana_mmwr(fecha)
            if deis == mia:
                ok += 1
            else:
                malos += 1
                discrepan.append((fecha, deis, mia))
        total_dias += ok + malos
        total_ok += ok
        origen = "interim" if usada.suffix.lower() == ".csv" else "raw"
        print(f"  {'OK ' if malos == 0 else '!! '}{anio}  {usada.name[:46]:<48} "
              f"[{origen:<7}] {ok:>4} días coinciden, {malos} no")

    print(f"\n  fechas contrastadas : {total_dias}")
    if total_dias:
        print(f"  coinciden           : {total_ok}  ({100 * total_ok / total_dias:.2f}%)")
    if saltados:
        print(f"\n  años no verificables ({len(saltados)}):")
        for anio, motivo in saltados:
            print(f"    · {anio}: {motivo}")
        print("    Para 2018-2019 corre antes:")
        print("      python -m src.procesamiento.deis_access convertir")
    if discrepan:
        print(f"\n  DISCREPANCIAS ({len(discrepan)}), primeras 20:")
        for fecha, a, b in discrepan[:20]:
            print(f"    {fecha}  DEIS={a}  calculada={b}")
        print("\n  La regla dice que esto para el proceso.")
        return 1
    print("\n  Coincidencia total. La semana MMWR calculada reproduce la del DEIS.")
    return 0


def cmd_construir(args) -> int:
    import pandas as pd

    filas = construir()
    df = pd.DataFrame(filas)
    destino = PROCESSED / "dim_tiempo"
    asegurar(destino)
    salida = destino / "dim_tiempo.parquet"
    df.to_parquet(salida, index=False)

    print(f"  filas          : {len(df):,}  ({INICIO} a {FIN})")
    print(f"  semanas MMWR   : {df['semana_id'].nunique():,}  "
          f"completas: {df[df.semana_completa]['semana_id'].nunique():,}")
    print(f"  escrito en     : {salida.relative_to(PROCESSED.parent.parent)}")
    print("\n  periodo_pandemia:")
    for p, n in df["periodo_pandemia"].value_counts().sort_index().items():
        print(f"    {p:<26}{n:>6} días")
    print("\n  primeras y últimas semanas, donde MMWR e ISO discrepan:")
    for _, r in pd.concat([df.head(5), df.tail(3)]).iterrows():
        print(f"    {r['fecha']}  {r['nombre_dia']:<10} -> {r['semana_id']}"
              f"   {'semana completa' if r['semana_completa'] else 'SEMANA PARCIAL'}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("construir").set_defaults(fn=cmd_construir, anios=None)
    v = sub.add_parser("validar")
    v.add_argument("--anios", default=None, help="lista separada por comas, p. ej. 2021,2026")
    v.set_defaults(fn=cmd_validar)

    args = p.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "tiempo.log", encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
