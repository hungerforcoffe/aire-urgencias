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

  /* ---------- color ---------- */
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  // Guías anuales OMS 2021. La escala no es decorativa: cada corte es un umbral
  // publicado, así que el color dice en qué peldaño está la ciudad.
  const CORTES = [5, 10, 15, 25, 35];
  const TONOS = ["--e0", "--e1", "--e2", "--e3", "--e4", "--e5"];
  const OMS = [
    { v: 5,  n: "Guía OMS" }, { v: 10, n: "Meta 4" }, { v: 15, n: "Meta 3" },
    { v: 25, n: "Meta 2" },   { v: 35, n: "Meta 1" },
  ];
  function nivel(v) { let i = 0; while (i < CORTES.length && v >= CORTES[i]) i++; return i; }
  function tono(v) { return (v === null || v === undefined) ? css("--nodata") : css(TONOS[nivel(v)]); }
  function peldano(v) {
    if (v === null || v === undefined) return "—";
    if (v < 5) return "cumple la guía OMS";
    for (let i = OMS.length - 1; i >= 0; i--) if (v >= OMS[i].v)
      return i === OMS.length - 1 ? "sobre la meta 1" : "entre meta " + (5 - i) + " y meta " + (4 - i);
    return "—";
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
    if (el) el.innerHTML = '<p class="aviso-caja"><b>No se pudieron cargar los datos.</b> ' +
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

  return { css, tono, nivel, peldano, num, miles, MESES, mesLargo, cargar, fallo,
           SECTORES, arco, sectorDe, vientoAhora, temaActual, CORTES, TONOS, OMS };
})();
