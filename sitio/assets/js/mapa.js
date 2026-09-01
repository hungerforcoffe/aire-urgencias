/* Consola de la red de MP2.5. Requiere Leaflet y comun.js.

   Forma: meteograma. El detalle de una estación son paneles apilados que
   comparten UN eje de tiempo — concentración, episodios y cobertura, uno debajo
   del otro, con un solo eje abajo. Repetir el eje en cada panel gasta espacio y
   obliga a re-leer la escala en cada salto.

   La cobertura es un panel más y no una nota al pie a propósito: es la variable
   que decide si las otras dos significan algo.

   El mapa muestra puntos, nunca una superficie interpolada. Se probó predecir
   cada estación desde las demás y en Santiago el modelo dio R² 0,533 contra
   0,750 del promedio simple de vecinas: pierde en las diez. */

(async function () {
  const $ = s => document.querySelector(s);

  /* Cartografía: Esri Canvas (gris claro y gris oscuro), sin llave.

     Antes se usaba CARTO. Dejó de servir: hoy responde HTTP 200 con una imagen
     PNG válida de 6,7 kB que dice «API KEY REQUIRED» impreso sobre la tesela.
     Es exactamente la regla 5 del proyecto —un fallo que parece un éxito— y
     por eso no se notó desde el código: el `fetch` no falla, la capa se
     agrega, y el error solo existe en los píxeles. Se ve al abrir el mapa.

     El reemplazo se eligió por lo mismo que se descartó el anterior: no pide
     llave. GitHub Pages no puede guardar un secreto, así que cualquier
     proveedor que exija una clave queda fuera por diseño, no por precio. */
  const ESRI = "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/";
  const TESELAS = {
    light: ESRI + "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    dark:  ESRI + "World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
  };
  const ROTULOS = {
    light: ESRI + "World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
    dark:  ESRI + "World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
  };
  const ATRIB = '<a href="https://www.esri.com/">Esri</a>, HERE, Garmin, '
    + '<a href="https://www.openstreetmap.org/copyright">OSM</a> · estaciones SINCA';
  const ZOOM_ESTACIONES = 9;
  const RADIO_ROSA = 1900;          // metros del pétalo más largo

  let meta, estaciones, meses, ciudades, claves;
  try { [meta, estaciones, meses, ciudades] =
          await AU.cargar("meta", "estaciones", "mensual", "ciudades"); }
  catch (e) { AU.fallo("#d-meteograma", e); return; }
  claves = Object.keys(meses).sort();

  const porId = new Map(estaciones.map(e => [e.id, e]));
  let t = claves.length - 1, sel = null, tocando = false, reloj = null;

  /* La red nacional es una capa de contexto y se carga aparte, a propósito.
     Si `nacional.json` no está —porque nadie corrió el exportador todavía— el
     mapa tiene que seguir funcionando con las 16 del estudio. Por eso el fallo
     se traga acá y no aborta el arranque: es una capa opcional, no un dato que
     el sitio prometa. El flujo de Pages tampoco lo exige entre sus archivos. */
  let nacional = null;
  try {
    nacional = await AU.cargar("nacional");
  } catch (e) {
    console.info("capa nacional no disponible:", e.message);
  }
  let verNacional = true;

  const valorDe = (id, i) => {
    const m = meses[claves[i]]; const d = m && m[String(id)];
    return d ? d[0] : null;
  };

  /* ===================== mapa ===================== */
  const mapa = L.map("mapa", { zoomControl: true, minZoom: 3, attributionControl: true });
  let capaBase = null, capaRot = null;
  function teselas() {
    const modo = AU.temaActual() === "dark" ? "dark" : "light";
    if (capaBase) mapa.removeLayer(capaBase);
    if (capaRot) mapa.removeLayer(capaRot);
    capaBase = L.tileLayer(TESELAS[modo], { attribution: ATRIB, maxZoom: 18,
      maxNativeZoom: 16 }).addTo(mapa);
    // Los rótulos van en una capa aparte, encima de los datos: así los nombres
    // de comuna se leen sin que los círculos los tapen.
    capaRot = L.tileLayer(ROTULOS[modo], { maxZoom: 18, maxNativeZoom: 16,
      pane: "shadowPane", opacity: .9 }).addTo(mapa);
  }
  teselas();

  // El orden importa: la nacional se agrega primero para quedar DEBAJO de las
  // estaciones del estudio, que son las que tienen detalle y se pueden abrir.
  const capaNacional = L.layerGroup().addTo(mapa);
  const capaPuntos = L.layerGroup().addTo(mapa);
  const capaRosa = L.layerGroup().addTo(mapa);
  // El encuadre inicial incluye la red nacional cuando está: mostrar Chile
  // entero encuadrando solo tres ciudades dejaba el país vacío a los lados.
  const limites = L.latLngBounds(
    estaciones.map(e => [e.lat, e.lon])
      .concat(nacional ? nacional.estaciones.map(e => [e.lat, e.lon]) : []));
  const verPais = () => mapa.fitBounds(limites, { padding: [40, 40] });
  const cajaCiudad = c => L.latLngBounds(
    estaciones.filter(e => e.ciudad === c).map(e => [e.lat, e.lon]));
  verPais();

  function petalo(lat, lon, sector, metros) {
    const p = [[lat, lon]];
    const mLat = 110574, mLon = 111320 * Math.cos(lat * Math.PI / 180);
    for (let a = sector * 45 - 22.5; a <= sector * 45 + 22.6; a += 4.5) {
      const r = a * Math.PI / 180;
      p.push([lat + metros * Math.cos(r) / mLat, lon + metros * Math.sin(r) / mLon]);
    }
    return p;
  }

  function rosaEnMapa(e, animar) {
    capaRosa.clearLayers();
    if (!e || !e.rosa) return;
    const v = e.rosa.invierno.filter(x => x !== null);
    if (!v.length) return;
    const max = Math.max(...v);
    const quieto = matchMedia("(prefers-reduced-motion: reduce)").matches || !animar;
    const piezas = [];
    e.rosa.invierno.forEach((val, i) => {
      if (val === null) return;
      const m = (val / max) * RADIO_ROSA;
      const capa = L.polygon(petalo(e.lat, e.lon, i, quieto ? m : 1), {
        color: AU.tono(val), weight: 1, opacity: .95,
        fillColor: AU.tono(val), fillOpacity: .26, interactive: false,
      }).addTo(capaRosa);
      piezas.push({ capa, m, i });
    });
    if (quieto) return;
    const t0 = performance.now(), DUR = 420, PASO = 50;
    (function paso(ahora) {
      let vivo = false;
      for (const p of piezas) {
        const u = Math.min(1, Math.max(0, (ahora - t0 - p.i * PASO) / DUR));
        if (u < 1) vivo = true;
        p.capa.setLatLngs(petalo(e.lat, e.lon, p.i, Math.max(1, p.m * (1 - (1 - u) ** 3))));
      }
      if (vivo) requestAnimationFrame(paso);
    })(t0);
  }

  const radio = v => v === null ? 4 : 4 + Math.sqrt(v) * 2.5;

  function dibujarPuntos() {
    capaPuntos.clearLayers();
    const porCiudad = mapa.getZoom() < ZOOM_ESTACIONES;
    if (porCiudad) {
      for (const c of ciudades) {
        const de = estaciones.filter(e => e.ciudad === c.id);
        const vs = de.map(e => valorDe(e.id, t)).filter(v => v !== null);
        const v = vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
        const centro = cajaCiudad(c.id).getCenter();
        L.circleMarker(centro, { radius: 7 + Math.sqrt(v || 0) * 2, color: AU.tono(v),
          weight: 1.5, fillColor: AU.tono(v), fillOpacity: .55 })
          .addTo(capaPuntos)
          .bindTooltip(`${c.nombre} · ${v === null ? "s/d" : AU.num(v) + " µg/m³"} · ` +
            `${de.length} est.`, { direction: "top" })
          .on("click", () => irA(c.id));
        L.marker(centro, { interactive: false, icon: L.divIcon({ className: "rotulo",
          html: `<span>${c.nombre}</span>`, iconSize: [88, 13], iconAnchor: [-11, 6] }) })
          .addTo(capaPuntos);
      }
      return;
    }
    for (const e of estaciones) {
      const v = valorDe(e.id, t), on = sel === e.id, r = radio(v);
      L.circleMarker([e.lat, e.lon], { radius: r, color: on ? AU.css("--senal") : AU.tono(v),
        weight: on ? 2 : 1.2, fillColor: v === null ? "transparent" : AU.tono(v),
        fillOpacity: v === null ? 0 : .72, dashArray: v === null ? "2 3" : null })
        .addTo(capaPuntos)
        .bindTooltip(`${e.nombre} · ${v === null ? "no midió" : AU.num(v) + " µg/m³"}`,
          { direction: "top" })
        .on("click", () => elegir(e.id));
      L.marker([e.lat, e.lon], { interactive: false, icon: L.divIcon({
        className: "rotulo" + (on ? " on" : ""), html: `<span>${e.nombre}</span>`,
        iconSize: [116, 13], iconAnchor: [-r - 3, 6] }) }).addTo(capaPuntos);
    }
  }

  /* La red nacional: el resto de las estaciones de SINCA que miden MP2.5.

     Se dibujan deliberadamente en segundo plano —más chicas, con borde fino y
     sin rótulo— porque no son lo mismo que las 16 del estudio. De estas hay
     media mensual y nada más: no tienen rosa de contaminación, ni meteograma,
     ni serie horaria, ni pasaron por la validación de cobertura del análisis.
     Dibujarlas igual que las otras prometería un detalle que no existe.

     Tampoco entran en ningún promedio de ciudad ni en el análisis semanal. Su
     trabajo es responder «¿qué se mide en el resto de Chile?», que hasta ahora
     el mapa contestaba con un país en blanco. */
  function dibujarNacional() {
    capaNacional.clearLayers();
    if (!nacional || !verNacional) return;
    const mes = nacional.mensual[claves[t]] || {};
    for (const e of nacional.estaciones) {
      const d = mes[e.id];
      const v = d ? d[0] : null;
      // Sin dato ese mes no se dibuja nada: un círculo hueco por cada estación
      // apagada convertiría el mapa en ruido. La lista de abajo sí las cuenta.
      if (v === null) continue;
      L.circleMarker([e.lat, e.lon], {
        radius: 3 + Math.sqrt(v) * 1.15, color: AU.tono(v), weight: 1,
        fillColor: AU.tono(v), fillOpacity: .5, opacity: .75,
      }).addTo(capaNacional)
        .bindTooltip(`${e.n} · ${e.c || "—"} · ${AU.num(v)} µg/m³` +
          `<br><i style="opacity:.6">red nacional · ${d[1]} días</i>`,
          { direction: "top" });
    }
  }

  function irA(cid) { mapa.flyToBounds(cajaCiudad(cid), { padding: [50, 50], maxZoom: 12,
    duration: .8 }); }
  function elegir(id) {
    sel = sel === id ? null : id;
    dibujarPuntos(); dibujarNacional(); rosaEnMapa(porId.get(sel), true);
    pintarLista(); pintarDetalle(); dibujarTira();
    if (sel) {
      const f = document.querySelector(`.fila-est[data-id="${sel}"]`);
      if (f) f.scrollIntoView({ block: "nearest" });
    }
  }
  mapa.on("zoomend", dibujarPuntos);

  /* ===================== riel de estaciones ===================== */
  function chispa(id, ancho, alto) {
    // Últimos 24 meses. Sin ejes ni etiquetas: es un indicador de forma, no un
    // gráfico para leer valores — para eso está el meteograma de abajo.
    const desde = Math.max(0, claves.length - 24);
    const vs = [];
    for (let i = desde; i < claves.length; i++) vs.push({ i, v: valorDe(id, i) });
    const con = vs.filter(x => x.v !== null).map(x => x.v);
    if (!con.length) return `<svg width="${ancho}" height="${alto}"></svg>`;
    const max = Math.max(...con), min = 0;
    const X = i => (i - desde) / (claves.length - 1 - desde || 1) * (ancho - 1) + .5;
    const Y = v => alto - 1.5 - (v - min) / (max - min || 1) * (alto - 3);
    let d = "", run = [];
    const cerrar = () => { if (run.length > 1) d += `<polyline points="${run.join(" ")}"
      fill="none" stroke="${AU.css("--tinta-3")}" stroke-width="1"/>`; run = []; };
    vs.forEach(x => x.v === null ? cerrar() : run.push(X(x.i).toFixed(1) + "," + Y(x.v).toFixed(1)));
    cerrar();
    const ult = vs[vs.length - 1];
    const punto = ult.v === null ? "" :
      `<circle cx="${X(ult.i).toFixed(1)}" cy="${Y(ult.v).toFixed(1)}" r="1.7"
        fill="${AU.tono(ult.v)}"/>`;
    return `<svg width="${ancho}" height="${alto}" aria-hidden="true">${d}${punto}</svg>`;
  }

  function pintarLista() {
    const html = ciudades.map(c => {
      const de = estaciones.filter(e => e.ciudad === c.id);
      const vs = de.map(e => valorDe(e.id, t)).filter(v => v !== null);
      const v = vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
      const filas = de.map(e => {
        const val = valorDe(e.id, t);
        return `<button class="fila-est" data-id="${e.id}"
            aria-pressed="${sel === e.id}">
          <span class="nom">${e.nombre}</span>
          <span class="val" style="color:${val === null ? "var(--tinta-3)" : AU.tono(val)}">
            ${val === null ? "<i>s/d</i>" : AU.num(val, 0)}</span>
          ${e.rosa ? chispa(e.id, 62, 15)
                   : '<span class="sin-viento">sin viento</span>'}
        </button>`;
      }).join("");
      return `<div class="grupo-ciudad" data-ciudad="${c.id}" role="button" tabindex="0">
          <h3>${c.nombre}</h3>
          <span class="meta">${de.length} est · ${AU.miles(c.poblacion)} hab</span>
          <span class="cifra" style="color:${AU.tono(v)}">${AU.num(v, 1)}</span>
        </div>${filas}`;
    }).join("");
    $("#lista").innerHTML = html;
    $("#lista").querySelectorAll(".fila-est").forEach(b =>
      b.addEventListener("click", () => elegir(+b.dataset.id)));
    $("#lista").querySelectorAll(".grupo-ciudad").forEach(g => {
      const ir = () => irA(g.dataset.ciudad);
      g.addEventListener("click", ir);
      g.addEventListener("keydown", ev => {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); ir(); } });
    });
    $("#riel-mes").textContent = AU.mesLargo(claves[t]);
  }

  /* ===================== tira de tiempo ===================== */
  // Un gráfico que se recorre, no un deslizador con una perilla. El área es el
  // promedio de la red; la línea, la estación elegida.
  function dibujarTira() {
    const caja = $("#tira-lienzo");
    const w = Math.max(320, caja.clientWidth), h = caja.clientHeight || 86;
    const mt = 8, mb = 13;
    const red = claves.map((k, i) => {
      const vs = estaciones.map(e => valorDe(e.id, i)).filter(v => v !== null);
      return vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
    });
    const todos = red.filter(v => v !== null);
    const max = Math.max(35, ...todos) * 1.05;
    const X = i => i / (claves.length - 1) * w;
    const Y = v => mt + (1 - v / max) * (h - mt - mb);
    const L = AU.css("--linea"), T3 = AU.css("--tinta-3");

    let g = "";
    // Retícula: solo las guías OMS que caben. Números en el borde, sin caja.
    for (const o of AU.OMS) {
      if (o.v > max) continue;
      g += `<line x1="0" y1="${Y(o.v).toFixed(1)}" x2="${w}" y2="${Y(o.v).toFixed(1)}"
        stroke="${L}" stroke-width="1"/>
        <text x="3" y="${(Y(o.v) - 2).toFixed(1)}" font-family="JetBrains Mono,ui-monospace,monospace"
          font-size="8" fill="${T3}">${o.v}</text>`;
    }
    // Área de la red, cortada donde no hay dato.
    let tramo = [];
    const cerrar = () => {
      if (tramo.length > 1) {
        const d = tramo.map(p => p.join(",")).join(" ");
        g += `<polygon points="${tramo[0][0]},${h - mb} ${d} ${tramo[tramo.length - 1][0]},${h - mb}"
          fill="${AU.css("--tinta-3")}" fill-opacity=".16"/>
          <polyline points="${d}" fill="none" stroke="${AU.css("--tinta-2")}" stroke-width="1"/>`;
      }
      tramo = [];
    };
    red.forEach((v, i) => v === null ? cerrar() : tramo.push([+X(i).toFixed(1), +Y(v).toFixed(1)]));
    cerrar();

    if (sel) {
      let run = [];
      const cerrar2 = () => { if (run.length > 1) g += `<polyline points="${run.join(" ")}"
        fill="none" stroke="${AU.css("--senal")}" stroke-width="1.4"/>`; run = []; };
      claves.forEach((k, i) => { const v = valorDe(sel, i);
        v === null ? cerrar2() : run.push(X(i).toFixed(1) + "," + Y(v).toFixed(1)); });
      cerrar2();
    }
    // Marcas de año en el eje inferior, el único eje de esta tira.
    claves.forEach((k, i) => { if (k.slice(5) === "01") {
      g += `<line x1="${X(i).toFixed(1)}" y1="${h - mb}" x2="${X(i).toFixed(1)}" y2="${h - mb + 3}"
        stroke="${T3}"/><text x="${(X(i) + 3).toFixed(1)}" y="${h - 3}"
        font-family="JetBrains Mono,ui-monospace,monospace" font-size="8.5" fill="${T3}">${k.slice(0, 4)}</text>`;
    }});
    // Cursor.
    g += `<line x1="${X(t).toFixed(1)}" y1="0" x2="${X(t).toFixed(1)}" y2="${h - mb}"
      stroke="${AU.css("--senal")}" stroke-width="1"/>
      <rect x="${(X(t) - 3).toFixed(1)}" y="0" width="6" height="4"
        fill="${AU.css("--senal")}"/>`;

    caja.innerHTML = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"
      style="height:${h}px">${g}</svg>`;
    caja.setAttribute("aria-valuemax", claves.length - 1);
    caja.setAttribute("aria-valuenow", t);
    caja.setAttribute("aria-valuetext", AU.mesLargo(claves[t]));
  }

  function irAMes(i) {
    t = Math.max(0, Math.min(claves.length - 1, i));
    $("#reloj").textContent = AU.mesLargo(claves[t]);
    const mes = meses[claves[t]] || {};
    const n = Object.keys(mes).length;
    $("#reloj-sub").textContent = `${n} de ${estaciones.length} midieron`;
    dibujarPuntos(); dibujarNacional(); pintarLista(); dibujarTira();
  }

  (function scrub() {
    const caja = $("#tira-lienzo");
    let arrastrando = false;
    const desdeX = ev => {
      const r = caja.getBoundingClientRect();
      const u = (ev.clientX - r.left) / r.width;
      irAMes(Math.round(u * (claves.length - 1)));
    };
    caja.addEventListener("pointerdown", ev => {
      arrastrando = true; caja.setPointerCapture(ev.pointerId); desdeX(ev); });
    caja.addEventListener("pointermove", ev => { if (arrastrando) desdeX(ev); });
    caja.addEventListener("pointerup", () => { arrastrando = false; });
    caja.addEventListener("keydown", ev => {
      const p = { ArrowLeft: -1, ArrowRight: 1, PageDown: -12, PageUp: 12,
                  Home: -claves.length, End: claves.length }[ev.key];
      if (p === undefined) return;
      ev.preventDefault(); irAMes(t + p);
    });
  })();

  $("#anterior").addEventListener("click", () => irAMes(t - 1));
  $("#siguiente").addEventListener("click", () => irAMes(t + 1));
  $("#play").addEventListener("click", () => {
    tocando = !tocando;
    $("#icono-play").setAttribute("d", tocando ? "M2 1h2.2v7H2zM5.3 1h2.2v7H5.3z" : "M2 1v7l6-3.5z");
    $("#play").setAttribute("aria-label", tocando ? "Pausar" : "Reproducir la serie mensual");
    clearInterval(reloj);
    if (tocando) reloj = setInterval(() => irAMes(t >= claves.length - 1 ? 0 : t + 1), 230);
  });

  /* ===================== meteograma ===================== */
  // Tres paneles, un solo eje de tiempo abajo. Concentración, episodios y
  // cobertura. El tercero decide si los dos primeros valen algo.
  function meteograma(e) {
    const w = 760, ml = 34, mr = 8, mt = 6, ejeAlto = 15;
    const alturas = [104, 46, 30], sep = 13;
    const h = mt + alturas.reduce((a, b) => a + b + sep, 0) + ejeAlto;
    const L = AU.css("--linea"), T3 = AU.css("--tinta-3"), T2 = AU.css("--tinta-2");
    const M = 'font-family="JetBrains Mono,ui-monospace,monospace"';
    const X = i => ml + i / (claves.length - 1) * (w - ml - mr);

    const serie = claves.map((k, i) => {
      const d = meses[k] && meses[k][String(e.id)];
      return { i, v: d ? d[0] : null, dias: d ? d[1] : 0, ep: d ? d[2] : 0 };
    });
    const maxV = Math.max(35, ...serie.map(s => s.v || 0)) * 1.04;
    const maxEp = Math.max(5, ...serie.map(s => s.ep));

    let g = "", y0 = mt;
    const banda = (alto) => {
      let s = "";
      serie.forEach(p => { const m = +claves[p.i].slice(5);
        if (m >= 5 && m <= 8) s += `<rect x="${(X(p.i) - (X(1) - X(0)) / 2).toFixed(1)}"
          y="${y0}" width="${(X(1) - X(0)).toFixed(2)}" height="${alto}"
          fill="${AU.css("--senal")}" fill-opacity=".05"/>`; });
      return s;
    };

    // --- panel 1: concentración -------------------------------------------
    let a = alturas[0];
    const Y1 = v => y0 + (1 - v / maxV) * a;
    g += banda(a);
    for (const o of AU.OMS) {
      if (o.v > maxV) continue;
      g += `<line x1="${ml}" y1="${Y1(o.v).toFixed(1)}" x2="${w - mr}" y2="${Y1(o.v).toFixed(1)}"
        stroke="${L}"/><text x="${ml - 4}" y="${(Y1(o.v) + 3).toFixed(1)}" text-anchor="end"
        ${M} font-size="8.5" fill="${T3}">${o.v}</text>`;
    }
    let run = [], marcas = "";
    const cerrar1 = () => { if (run.length > 1) g += `<polyline points="${run.join(" ")}"
      fill="none" stroke="${T2}" stroke-width="1.3" stroke-linejoin="round"/>`; run = []; };
    serie.forEach(p => {
      if (p.v === null) { cerrar1(); return; }
      run.push(X(p.i).toFixed(1) + "," + Y1(p.v).toFixed(1));
      marcas += `<circle cx="${X(p.i).toFixed(1)}" cy="${Y1(p.v).toFixed(1)}" r="1.5"
        fill="${AU.tono(p.v)}"/>`;
    });
    cerrar1();
    g += marcas;
    g += `<text x="${ml}" y="${y0 - 1}" ${M} font-size="8.5" fill="${T3}">µg/m³ · media mensual</text>`;
    y0 += a + sep;

    // --- panel 2: episodios ------------------------------------------------
    a = alturas[1];
    g += banda(a);
    g += `<line x1="${ml}" y1="${y0 + a}" x2="${w - mr}" y2="${y0 + a}" stroke="${L}"/>`;
    const anchoB = Math.max(1.2, (w - ml - mr) / claves.length - .7);
    serie.forEach(p => { if (!p.ep) return;
      const alto = (p.ep / maxEp) * a;
      g += `<rect x="${(X(p.i) - anchoB / 2).toFixed(1)}" y="${(y0 + a - alto).toFixed(1)}"
        width="${anchoB.toFixed(1)}" height="${alto.toFixed(1)}" fill="${AU.css("--e4")}"
        fill-opacity=".8"/>`; });
    g += `<text x="${ml}" y="${y0 - 1}" ${M} font-size="8.5" fill="${T3}">días &gt; 50 µg/m³
      · máx ${maxEp}</text>`;
    y0 += a + sep;

    // --- panel 3: cobertura ------------------------------------------------
    a = alturas[2];
    g += banda(a);
    serie.forEach(p => {
      const u = Math.min(1, p.dias / 30);
      const alto = Math.max(1, u * a);
      const col = p.dias === 0 ? AU.css("--sindato")
                : (p.dias >= 24 ? AU.css("--e1") : AU.css("--e3"));
      g += `<rect x="${(X(p.i) - anchoB / 2).toFixed(1)}" y="${(y0 + a - alto).toFixed(1)}"
        width="${anchoB.toFixed(1)}" height="${alto.toFixed(1)}" fill="${col}"
        fill-opacity="${p.dias === 0 ? .35 : .75}"/>`;
    });
    g += `<text x="${ml}" y="${y0 - 1}" ${M} font-size="8.5" fill="${T3}">días con dato en el mes</text>`;
    y0 += a + sep;

    // --- eje único ---------------------------------------------------------
    g += `<line x1="${ml}" y1="${y0}" x2="${w - mr}" y2="${y0}" stroke="${AU.css("--linea-2")}"/>`;
    claves.forEach((k, i) => { if (k.slice(5) !== "01") return;
      g += `<line x1="${X(i).toFixed(1)}" y1="${y0}" x2="${X(i).toFixed(1)}" y2="${y0 + 3}"
        stroke="${T3}"/><text x="${X(i).toFixed(1)}" y="${y0 + 12}" text-anchor="middle"
        ${M} font-size="9" fill="${T3}">${k.slice(0, 4)}</text>`; });
    // Cursor compartido con la tira: mismo mes, misma posición vertical entera.
    g += `<line x1="${X(t).toFixed(1)}" y1="${mt}" x2="${X(t).toFixed(1)}" y2="${y0}"
      stroke="${AU.css("--senal")}" stroke-width="1" stroke-dasharray="2 2"/>`;

    return `<svg viewBox="0 0 ${w} ${h}" role="img"
      aria-label="Meteograma de ${e.nombre}: concentración, episodios y cobertura">${g}</svg>`;
  }

  /* ===================== rosa (panel lateral) ===================== */
  function rosaSVG(e) {
    const R = 88, C = 112, inv = e.rosa.invierno;
    const max = Math.max(...inv.filter(v => v !== null));
    const L = AU.css("--linea"), T3 = AU.css("--tinta-3");
    const M = 'font-family="JetBrains Mono,ui-monospace,monospace"';
    let g = "";
    // Anillos rotulados: una rosa sin escala no se puede leer.
    for (const f of [1 / 3, 2 / 3, 1]) {
      g += `<circle cx="${C}" cy="${C}" r="${(R * f).toFixed(1)}" fill="none" stroke="${L}"/>`;
      g += `<text x="${C + 3}" y="${(C - R * f + 8).toFixed(1)}" ${M} font-size="8"
        fill="${T3}">${AU.num(max * f, 0)}</text>`;
    }
    g += AU.SECTORES.map((s, i) => {
      const a = (i * 45 - 90) * Math.PI / 180;
      return `<line x1="${C}" y1="${C}" x2="${(C + Math.cos(a) * R).toFixed(1)}"
        y2="${(C + Math.sin(a) * R).toFixed(1)}" stroke="${L}"/>
        <text x="${(C + Math.cos(a) * (R + 13)).toFixed(1)}"
          y="${(C + Math.sin(a) * (R + 13) + 3.5).toFixed(1)}" text-anchor="middle"
          font-family="Source Sans 3,system-ui,sans-serif" font-size="10"
          font-weight="600" fill="${T3}">${s}</text>`;
    }).join("");
    g += inv.map((v, i) => v === null ? "" :
      `<path d="${AU.arco(C, C, (v / max) * R, i)}" fill="${AU.tono(v)}" fill-opacity=".78"
        stroke="${AU.css("--panel")}" stroke-width=".8"/>`).join("");
    return `<svg viewBox="0 0 224 224" role="img"
      aria-label="Rosa de contaminación de ${e.nombre}">${g}</svg>`;
  }

  /* ===================== panel de detalle ===================== */
  function pintarDetalle() {
    const e = porId.get(sel);
    if (!e) {
      $("#d-nombre").textContent = "Sin estación seleccionada";
      $("#d-id").textContent = "";
      $("#d-cifras").innerHTML = "";
      $("#d-meteograma").innerHTML = '<p class="aviso">Elige una estación en la lista de la '
        + 'izquierda o en el mapa. Se abre su meteograma —concentración, episodios y '
        + 'cobertura sobre un mismo eje— y su rosa de contaminación.</p>';
      $("#d-lado").innerHTML = "";
      return;
    }
    $("#d-nombre").textContent = e.nombre;
    $("#d-id").textContent = `${e.comuna} · est. ${e.id} · `
      + `${e.lat.toFixed(4)}° ${e.lon.toFixed(4)}°`;

    const ult = Object.keys(e.anual).map(Number).filter(a => e.anual[a].completo).sort();
    const a = ult.length ? e.anual[ult[ult.length - 1]] : null;
    const vAhora = valorDe(e.id, t);
    let cifras = `<div><div class="k">${AU.mesLargo(claves[t])}</div>
      <div class="v" style="color:${AU.tono(vAhora)}">${AU.num(vAhora)}</div></div>`;
    if (a) cifras += `<div><div class="k">Media ${ult[ult.length - 1]}</div>
      <div class="v" style="color:${AU.tono(a.media)}">${AU.num(a.media)}</div></div>
      <div><div class="k">Días &gt;50</div><div class="v">${a.sobre50}</div></div>`;
    if (e.rosa) {
      const inv = e.rosa.invierno, vs = inv.filter(v => v !== null);
      const mx = Math.max(...vs), mn = Math.min(...vs);
      cifras += `<div><div class="k">Contraste viento</div>
        <div class="v">${AU.num(mx / mn, 2)}×</div></div>`;
    }
    $("#d-cifras").innerHTML = cifras;
    $("#d-meteograma").innerHTML = meteograma(e);

    let lado = "";
    if (e.rosa) {
      const inv = e.rosa.invierno, vs = inv.filter(v => v !== null);
      const mx = Math.max(...vs), mn = Math.min(...vs);
      lado = `<h3>Rosa de contaminación</h3>${rosaSVG(e)}
        <p style="font-size:11px;color:var(--tinta-3);margin:6px 0 0;line-height:1.45">
          Mediana horaria de invierno por sector de procedencia.
          Máximo <b style="color:${AU.tono(mx)}">${AU.SECTORES[inv.indexOf(mx)]} ${AU.num(mx)}</b>,
          mínimo <b style="color:${AU.tono(mn)}">${AU.SECTORES[inv.indexOf(mn)]} ${AU.num(mn)}</b>,
          sobre ${AU.miles(e.rosa.horas_invierno.reduce((x, y) => x + y, 0))} horas.</p>
        <div class="viento" id="viento"><div class="txt"><em>Viento ahora</em>consultando…</div></div>`;
    } else {
      lado = `<h3>Sin anemómetro</h3><p class="aviso"><b>Esta estación no mide viento.</b>
        Registra MP2.5 pero no tiene anemómetro ni veleta, así que no hay rosa que dibujar.
        Sigue en el mapa porque su serie de partículas es válida.</p>`;
    }
    lado += `<h3 style="margin-top:14px">Año por año</h3><div class="scroll-x"><table><thead>
      <tr><th>Año</th><th>Días</th><th>Media</th><th>&gt;50</th></tr></thead><tbody>`;
    for (const y of Object.keys(e.anual).map(Number).sort((p, q) => p - q)) {
      const d = e.anual[y];
      lado += `<tr class="${d.completo ? "" : "parcial"}"><td>${y}</td><td>${d.dias}</td>
        <td style="${d.completo ? "color:" + AU.tono(d.media) : ""}">${AU.num(d.media)}</td>
        <td>${d.sobre50}</td></tr>`;
    }
    $("#d-lado").innerHTML = lado + "</tbody></table></div>";
    if (e.rosa) mostrarViento(e);
  }

  async function mostrarViento(e) {
    const caja = $("#viento");
    if (!caja) return;
    try {
      const c = await AU.vientoAhora(e.lat, e.lon);
      if (sel !== e.id) return;
      const dir = c.wind_direction_10m, sec = AU.sectorDe(dir);
      const v = e.rosa.invierno[AU.SECTORES.indexOf(sec)];
      caja.innerHTML = `<svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true"
          style="flex:none">
          <circle cx="16" cy="16" r="14" fill="none" stroke="${AU.css("--linea-2")}"/>
          <g transform="rotate(${dir + 180} 16 16)">
            <path d="M16 4 L20 22 L16 19 L12 22 Z" fill="${AU.tono(v)}"/></g></svg>
        <div class="txt"><em>Viento ahora · Open-Meteo</em>
          Del <b>${sec}</b> (${Math.round(dir)}°) a <b>${AU.num(c.wind_speed_10m)} km/h</b>,
          ${AU.num(c.temperature_2m)} °C. Con ese sector la mediana histórica de invierno
          aquí es <b>${AU.num(v)} µg/m³</b>.</div>`;
    } catch (err) {
      if (sel !== e.id) return;
      caja.innerHTML = '<div class="txt"><em>Viento ahora</em>No se pudo consultar. '
        + 'La rosa no depende de esto: sale de las mediciones ya guardadas.</div>';
    }
  }

  /* ===================== arranque ===================== */
  $("#rampa").innerHTML = AU.TONOS.map((v, i) =>
    `<div style="background:${AU.css(v)}">${i ? `<span>${AU.CORTES[i - 1]}</span>` : ""}</div>`).join("");
  $("#e-corte").textContent = meta.ultimo_mes;
  $("#e-red").textContent = `${meta.conteos.estaciones} est · `
    + `${meta.conteos.estaciones_con_viento} con viento`;

  document.addEventListener("au:tema", () => {
    teselas(); dibujarPuntos(); dibujarNacional(); rosaEnMapa(porId.get(sel), false);
    pintarLista(); dibujarTira(); pintarDetalle();
    $("#rampa").innerHTML = AU.TONOS.map((v, i) =>
      `<div style="background:${AU.css(v)}">${i ? `<span>${AU.CORTES[i - 1]}</span>` : ""}</div>`).join("");
  });
  addEventListener("resize", () => { dibujarTira(); mapa.invalidateSize(); });

  /* Interruptor de la capa nacional. Si el JSON no está, el control queda
     desactivado en vez de desaparecer: así se ve que la capa existe y que lo
     que falta es correr el exportador, en vez de parecer que nunca hubo tal
     cosa. */
  const chkNacional = $("#ver-nacional");
  if (chkNacional) {
    if (!nacional) {
      chkNacional.checked = false;
      chkNacional.disabled = true;
      chkNacional.closest(".interruptor").title =
        "Falta assets/datos/nacional.json — se genera con "
        + "python -m src.sitio.exportar_nacional";
    } else {
      $("#n-nacional").textContent = `${nacional.conteos.estaciones} est`;
      chkNacional.addEventListener("change", () => {
        verNacional = chkNacional.checked;
        dibujarNacional();
      });
    }
  }

  irAMes(t); pintarDetalle();
})();
