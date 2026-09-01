/* Utilidades compartidas por las tres páginas.
   Sin dependencias: se carga antes que todo lo demás y define `AU`. */

const AU = (() => {

  /* ---------- tema ---------- */
  // Tres estados: "claro", "oscuro" y sin marcar (sigue al sistema). El
  // interruptor solo alterna entre los dos explícitos; quien nunca lo toque se
  // queda con el del sistema, que es lo que la mayoría espera.
  const TEMA = "au-tema";
  function aplicarTema(t) {
    if (t) document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
  }
  function temaActual() {
    const marcado = document.documentElement.getAttribute("data-theme");
    if (marcado) return marcado;
    return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function iniciarTema() {
    let guardado = null;
    try { guardado = localStorage.getItem(TEMA); } catch (e) { /* modo privado */ }
    if (guardado) aplicarTema(guardado);
    const btn = document.querySelector(".tema");
    if (!btn) return;
    btn.addEventListener("click", () => {
      const nuevo = temaActual() === "dark" ? "light" : "dark";
      aplicarTema(nuevo);
      try { localStorage.setItem(TEMA, nuevo); } catch (e) { /* da igual */ }
      document.dispatchEvent(new CustomEvent("au:tema"));
    });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      if (!document.documentElement.getAttribute("data-theme"))
        document.dispatchEvent(new CustomEvent("au:tema"));
    });
  }

  /* ---------- color: la escala legal de MP2.5 ---------- */
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  /* El color de una concentración no es una escala inventada por este sitio: es
     el ICAP2,5, el Índice de Calidad del Aire referido a Partículas que define
     el D.S. N°12/2011 del Ministerio del Medio Ambiente en su artículo 2º letra
     l), como una función lineal por tramos anclada en tres puntos:

         ICAP   0  ->    0 µg/m³N
         ICAP 100  ->   50
         ICAP 500  ->  170

     de donde   ICAP = 2·C                 si C <= 50
                ICAP = 100 + (C - 50)·10/3  si C > 50

     Los niveles de episodio del artículo 5º —Alerta 80, Preemergencia 110,
     Emergencia 170— caen justo en ICAP 200, 300 y 500. Los colores son los que
     publica SINCA para cada categoría.

     ADVERTENCIA DE PERÍODO, y es la parte importante: el decreto define el ICAP
     sobre la concentración de VEINTICUATRO HORAS. El mapa de este sitio pinta
     MEDIAS MENSUALES, que no son la magnitud que la ley regula. Una media
     mensual de 45 µg/m³ se pinta verde —«bueno» en la escala de 24 h— y sin
     embargo es más del doble de la norma ANUAL, que el mismo decreto fija en 20
     µg/m³ en su artículo 3º. El color ubica el valor en la escala legal; no
     afirma que la estación cumpla la norma. Ver docs/calidad/escala_icap.md. */

  const NORMA_ANUAL = 20;   // D.S. 12/2011 art. 3º
  const NORMA_24H = 50;     // idem

  // Categorías del art. 5º. `c` es la concentración de 24 h donde empieza cada
  // una, `icap` su valor en el índice, `token` el color oficial de SINCA.
  const CATEGORIAS = [
    { c:   0, icap:   0, n: "Bueno",         token: "--icap-bueno" },
    { c:  50, icap: 100, n: "Regular",       token: "--icap-regular" },
    { c:  80, icap: 200, n: "Alerta",        token: "--icap-alerta" },
    { c: 110, icap: 300, n: "Preemergencia", token: "--icap-preemergencia" },
    { c: 170, icap: 500, n: "Emergencia",    token: "--icap-emergencia" },
  ];

  // Líneas de referencia de los gráficos: los umbrales que la ley nombra, no
  // una retícula decorativa elegida por ser redonda.
  const REFERENCIAS = [
    { v: NORMA_ANUAL, n: "norma anual" },
    { v: NORMA_24H,   n: "norma 24 h" },
    { v: 80,          n: "alerta" },
    { v: 110,         n: "preemergencia" },
    { v: 170,         n: "emergencia" },
  ];

  function icap(c) {
    if (c === null || c === undefined || Number.isNaN(c)) return null;
    if (c <= 0) return 0;
    return c <= 50 ? 2 * c : 100 + (c - 50) * 10 / 3;
  }

  /* Interpolación en OKLab y no en sRGB. Mezclar el verde con el amarillo en
     sRGB pasa por un oliva sucio que no está en la paleta de nadie; en OKLab la
     transición conserva el croma y se ve como la rampa de SINCA. */
  const _lin = c => (c /= 255) <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  const _gam = x => Math.round(255 * Math.min(1, Math.max(0,
    x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055)));

  function _leerRGB(txt) {
    const t = (txt || "").trim();
    const m = t.match(/^#?([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (m) {
      const h = m[1].length === 3 ? m[1].replace(/./g, c => c + c) : m[1];
      return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16));
    }
    const r = t.match(/rgba?\(([^)]+)\)/i);
    if (r) return r[1].split(/[,\s/]+/).filter(Boolean).slice(0, 3).map(x => parseInt(x, 10));
    return [0, 0, 0];
  }

  function _aOklab(txt) {
    const [R, G, B] = _leerRGB(txt).map(_lin);
    const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B);
    const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B);
    const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
    return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
  }

  function _deOklab(lab) {
    const [L, A, B] = lab;
    const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3;
    const m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3;
    const s = (L - 0.0894841775 * A - 1.2914855480 * B) ** 3;
    return "#" + [
      _gam( 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
      _gam(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
      _gam(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s),
    ].map(v => v.toString(16).padStart(2, "0")).join("");
  }

  // `getComputedStyle` es caro y `tono` se llama una vez por estación y por
  // repintado. Las paradas se resuelven una vez por tema y se rehacen cuando el
  // tema cambia; el listener de más abajo invalida la caché.
  let _paradas = null;
  const _resolverParadas = () =>
    (_paradas ||= CATEGORIAS.map(k => [k.icap, _aOklab(css(k.token))]));

  function tono(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return css("--sindato");
    const p = _resolverParadas(), x = icap(v);
    if (x <= p[0][0]) return _deOklab(p[0][1]);
    for (let i = 1; i < p.length; i++) {
      if (x <= p[i][0]) {
        const u = (x - p[i - 1][0]) / (p[i][0] - p[i - 1][0]);
        const a = p[i - 1][1], b = p[i][1];
        return _deOklab([0, 1, 2].map(k => a[k] + (b[k] - a[k]) * u));
      }
    }
    return _deOklab(p[p.length - 1][1]);
  }

  // La categoría legal a la que pertenece una concentración de 24 h.
  function peldano(v) {
    if (v === null || v === undefined) return "—";
    let n = CATEGORIAS[0].n;
    for (const k of CATEGORIAS) if (v >= k.c) n = k.n;
    return n;
  }

  /* ---------- números y fechas ---------- */
  const nf = new Intl.NumberFormat("es-CL");
  function num(v, d = 1) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return v.toLocaleString("es-CL", { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  const miles = v => (v === null || v === undefined) ? "—" : nf.format(Math.round(v));
  const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const mesLargo = k => MESES[+k.slice(5) - 1] + " " + k.slice(0, 4);

  /* ---------- carga de datos ---------- */
  // Las rutas son relativas a propósito: en GitHub Pages un sitio de proyecto
  // vive en /nombre-del-repo/, así que cualquier ruta que empiece con "/"
  // apuntaría a la raíz del dominio y daría 404.
  async function cargar(...nombres) {
    const r = await Promise.all(nombres.map(async n => {
      const res = await fetch("assets/datos/" + n + ".json");
      if (!res.ok) throw new Error(`no se pudo leer ${n}.json (HTTP ${res.status})`);
      return res.json();
    }));
    return nombres.length === 1 ? r[0] : r;
  }
  function fallo(contenedor, err) {
    console.error(err);
    const el = typeof contenedor === "string" ? document.querySelector(contenedor) : contenedor;
    if (el) el.innerHTML = '<p class="aviso"><b>No se pudieron cargar los datos.</b> ' +
      'Los JSON se generan con <code>python -m src.sitio.exportar</code> y viven en ' +
      '<code>sitio/assets/datos/</code>. Detalle: ' + String(err.message || err) + '</p>';
  }

  /* ---------- geometría de la rosa ---------- */
  const SECTORES = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
  // Sector i cubre 45° centrados en i*45. El -90 lleva el 0° (norte) hacia
  // arriba, porque en pantalla el ángulo 0 apunta a la derecha.
  function arco(cx, cy, r, i) {
    const a0 = (i * 45 - 22.5 - 90) * Math.PI / 180, a1 = (i * 45 + 22.5 - 90) * Math.PI / 180;
    return `M ${cx} ${cy} L ${(cx + Math.cos(a0) * r).toFixed(2)} ${(cy + Math.sin(a0) * r).toFixed(2)}`
      + ` A ${r.toFixed(2)} ${r.toFixed(2)} 0 0 1 ${(cx + Math.cos(a1) * r).toFixed(2)}`
      + ` ${(cy + Math.sin(a1) * r).toFixed(2)} Z`;
  }
  const sectorDe = grados => SECTORES[Math.floor(((grados % 360) + 360 + 22.5) % 360 / 45)];

  /* ---------- viento en vivo (Open-Meteo) ---------- */
  // Sin llave y con CORS, así que se puede llamar desde el navegador. Es
  // meteorología, no calidad del aire: sirve para leer la rosa hoy, nunca
  // como medición de MP2.5 ni como pronóstico de contaminación.
  async function vientoAhora(lat, lon) {
    const u = "https://api.open-meteo.com/v1/forecast?latitude=" + lat + "&longitude=" + lon
      + "&current=temperature_2m,wind_speed_10m,wind_direction_10m&timezone=auto";
    const ctrl = new AbortController();
    const reloj = setTimeout(() => ctrl.abort(), 8000);
    try {
      const res = await fetch(u, { signal: ctrl.signal });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const j = await res.json();
      if (!j.current || j.current.wind_direction_10m === undefined)
        throw new Error("respuesta sin viento");
      return j.current;
    } finally { clearTimeout(reloj); }
  }

  /* ---------- navegación ---------- */
  function marcarNav() {
    const aqui = location.pathname.split("/").pop() || "index.html";
    document.querySelectorAll("nav a").forEach(a => {
      if (a.getAttribute("href") === aqui) a.setAttribute("aria-current", "page");
    });
  }

  function iniciar() { iniciarTema(); marcarNav(); }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();

  // La caché de color depende del tema, así que se invalida antes de que nadie
  // repinte: este listener se registra al evaluar comun.js, o sea antes que los
  // de mapa.js, que es quien redibuja al recibir el mismo evento.
  document.addEventListener("au:tema", () => { _paradas = null; });

  return { css, tono, peldano, icap, num, miles, MESES, mesLargo, cargar, fallo,
           SECTORES, arco, sectorDe, vientoAhora, temaActual,
           CATEGORIAS, REFERENCIAS, NORMA_ANUAL, NORMA_24H };
})();
