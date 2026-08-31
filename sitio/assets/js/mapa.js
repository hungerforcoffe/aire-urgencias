/* Mapa de exposición a MP2.5. Requiere Leaflet y comun.js.

   Decisión de fondo: el mapa muestra PUNTOS, no una superficie interpolada.
   Se probó predecir cada estación desde las demás (leave-one-station-out) y en
   Santiago el modelo dio R² 0,533 contra 0,750 del simple promedio de vecinas:
   pierde en las diez. Las Condes queda en −0,01, o sea es impredecible desde el
   resto de la ciudad. Pintar la mancha continua entre estaciones sería inventar
   los píxeles del medio. Ver la pestaña Fuentes. */

(async function () {
  const $ = s => document.querySelector(s);

  const TESELAS = {
    light: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    dark:  "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
  };
  const ATRIB = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
    + '&copy; <a href="https://carto.com/attributions">CARTO</a> · estaciones: SINCA (MMA)';

  // Bajo este zoom se ven burbujas de ciudad; sobre él, estaciones. Chile mide
  // 4.300 km de largo: a escala país las estaciones de Santiago caen todas en
  // el mismo píxel y el mapa no diría nada.
  const ZOOM_ESTACIONES = 9;
  const RADIO_MAX_ROSA = 1900;   // metros del pétalo más largo

  let meta, estaciones, meses, ciudades, clavesMes;
  try {
    [meta, estaciones, meses, ciudades] =
      await AU.cargar("meta", "estaciones", "mensual", "ciudades");
  } catch (e) { AU.fallo("#detalle-cuerpo", e); return; }
  clavesMes = Object.keys(meses).sort();

  const porId = new Map(estaciones.map(e => [e.id, e]));
  let t = clavesMes.length - 1;      // mes mostrado
  let sel = null;                    // estación seleccionada
  let tocando = false, cronometro = null;

  /* ================= mapa ================= */
  const mapa = L.map("mapa", { zoomControl: true, scrollWheelZoom: true, minZoom: 3 });
  let capaTeselas = null;
  function ponerTeselas() {
    if (capaTeselas) mapa.removeLayer(capaTeselas);
    capaTeselas = L.tileLayer(TESELAS[AU.temaActual() === "dark" ? "dark" : "light"],
      { attribution: ATRIB, maxZoom: 18, subdomains: "abcd" }).addTo(mapa);
    capaTeselas.getContainer().style.zIndex = 1;
  }
  ponerTeselas();

  const capaCiudades = L.layerGroup().addTo(mapa);
  const capaEstaciones = L.layerGroup().addTo(mapa);
  const capaRosa = L.layerGroup().addTo(mapa);

  // Vista país: encuadra las tres ciudades, que es lo que hace evidente la
  // distancia real entre Coyhaique y Santiago (unos 1.700 km).
  const limites = L.latLngBounds(estaciones.map(e => [e.lat, e.lon]));
  const VISTA_PAIS = () => mapa.fitBounds(limites, { padding: [60, 60] });
  VISTA_PAIS();

  function centroCiudad(cid) {
    const e = estaciones.filter(x => x.ciudad === cid);
    return L.latLngBounds(e.map(x => [x.lat, x.lon]));
  }

  /* ================= pétalos geográficos ================= */
  // El pétalo es un polígono en coordenadas reales, no un dibujo pegado a la
  // pantalla: al acercar o alejar el zoom conserva su tamaño en metros, que es
  // lo que lo hace comparable con la ciudad que tiene debajo.
  function petalo(lat, lon, sector, metros) {
    const pts = [[lat, lon]];
    const mLat = 110574, mLon = 111320 * Math.cos(lat * Math.PI / 180);
    for (let a = sector * 45 - 22.5; a <= sector * 45 + 22.5 + 0.01; a += 4.5) {
      const rad = a * Math.PI / 180;
      pts.push([lat + (metros * Math.cos(rad)) / mLat,
                lon + (metros * Math.sin(rad)) / mLon]);
    }
    return pts;
  }

  function dibujarRosa(e, animar) {
    capaRosa.clearLayers();
    if (!e || !e.rosa) return;
    const vals = e.rosa.invierno.filter(v => v !== null);
    if (!vals.length) return;
    const max = Math.max(...vals);
    const quieto = matchMedia("(prefers-reduced-motion: reduce)").matches || !animar;

    const piezas = [];
    e.rosa.invierno.forEach((v, i) => {
      if (v === null) return;
      const metros = (v / max) * RADIO_MAX_ROSA;
      const p = L.polygon(petalo(e.lat, e.lon, i, quieto ? metros : 1), {
        color: AU.tono(v), weight: 1.2, opacity: .9,
        fillColor: AU.tono(v), fillOpacity: .30, interactive: false,
      }).addTo(capaRosa);
      p.bindTooltip(`${AU.SECTORES[i]} · ${AU.num(v)} µg/m³ · ` +
        `${AU.miles(e.rosa.horas_invierno[i])} h`, { sticky: true });
      piezas.push({ capa: p, metros: metros, sector: i });
    });
    if (quieto) return;

    // Los pétalos crecen escalonados, en sentido horario desde el norte: el ojo
    // sigue la rosa igual que se lee una brújula.
    const INICIO = performance.now(), DUR = 460, PASO = 55;
    (function paso(ahora) {
      let vivos = false;
      for (const p of piezas) {
        const u = Math.min(1, Math.max(0, (ahora - INICIO - p.sector * PASO) / DUR));
        if (u < 1) vivos = true;
        const f = 1 - Math.pow(1 - u, 3);           // desaceleración cúbica
        p.capa.setLatLngs(petalo(e.lat, e.lon, p.sector, Math.max(1, p.metros * f)));
      }
      if (vivos) requestAnimationFrame(paso);
    })(INICIO);
  }

  /* ================= marcadores ================= */
  const radioPunto = v => v === null ? 5 : 5 + Math.sqrt(v) * 2.6;

  function dibujarMarcadores() {
    const mes = meses[clavesMes[t]] || {};
    const enEstaciones = mapa.getZoom() >= ZOOM_ESTACIONES;
    capaCiudades.clearLayers();
    capaEstaciones.clearLayers();

    if (!enEstaciones) {
      for (const c of ciudades) {
        const de = estaciones.filter(e => e.ciudad === c.id);
        const vs = de.map(e => mes[String(e.id)]).filter(Boolean).map(d => d[0]);
        const v = vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
        const centro = centroCiudad(c.id).getCenter();
        L.circleMarker(centro, {
          radius: 8 + Math.sqrt(v || 0) * 2.2,
          color: AU.tono(v), weight: 2, fillColor: AU.tono(v), fillOpacity: .6,
        }).addTo(capaCiudades)
          .bindTooltip(`<b>${c.nombre}</b><br>${v === null ? "sin dato" : AU.num(v) + " µg/m³"}` +
            `<br><span style="opacity:.7">${de.length} estaciones · clic para acercar</span>`,
            { direction: "top" })
          .on("click", () => irACiudad(c.id));
        L.marker(centro, {
          icon: L.divIcon({ className: "etiqueta-est", html: `<span>${c.nombre}</span>`,
                            iconSize: [90, 14], iconAnchor: [-12, 7] }),
          interactive: false,
        }).addTo(capaCiudades);
      }
      return;
    }

    for (const e of estaciones) {
      const d = mes[String(e.id)], v = d ? d[0] : null, act = sel === e.id;
      L.circleMarker([e.lat, e.lon], {
        radius: radioPunto(v), color: AU.tono(v), weight: act ? 3 : 1.4,
        fillColor: v === null ? "transparent" : AU.tono(v),
        fillOpacity: v === null ? 0 : (act ? .95 : .7),
        dashArray: v === null ? "3 3" : null,
      }).addTo(capaEstaciones)
        .bindTooltip(`<b>${e.nombre}</b><br>${v === null
            ? "no midió este mes"
            : AU.num(v) + " µg/m³ · " + d[1] + " días"}`, { direction: "top" })
        .on("click", () => seleccionar(e.id));
      L.marker([e.lat, e.lon], {
        icon: L.divIcon({ className: "etiqueta-est" + (act ? " activa" : ""),
                          html: `<span>${e.nombre}</span>`,
                          iconSize: [120, 14], iconAnchor: [-radioPunto(v) - 4, 7] }),
        interactive: false,
      }).addTo(capaEstaciones);
    }
  }

  function irACiudad(cid) {
    mapa.flyToBounds(centroCiudad(cid), { padding: [70, 70], maxZoom: 12, duration: .9 });
    document.querySelectorAll(".cc").forEach(b =>
      b.setAttribute("aria-pressed", b.dataset.ciudad === cid));
  }

  function seleccionar(id) {
    sel = sel === id ? null : id;
    dibujarMarcadores();
    dibujarRosa(porId.get(sel), true);
    pintarDetalle();
  }

  mapa.on("zoomend", () => { dibujarMarcadores(); });

  /* ================= panel de detalle ================= */
  function pintarDetalle() {
    const nom = $("#detalle-nombre"), met = $("#detalle-meta"), cuerpo = $("#detalle-cuerpo");
    const e = porId.get(sel);
    if (!e) {
      nom.textContent = "Ninguna estación seleccionada";
      met.textContent = "— · —";
      cuerpo.innerHTML = '<p class="aviso-caja">Acércate a una ciudad y haz clic en una ' +
        'estación. Se abre su rosa de contaminación sobre el mapa, el viento que sopla ' +
        'ahí ahora mismo, su serie mensual y su tabla año por año.</p>';
      return;
    }
    nom.textContent = e.nombre;
    met.textContent = `${e.comuna} · estación ${e.id} · ${e.lat.toFixed(4)}°, ${e.lon.toFixed(4)}°`;

    let html = "";
    if (e.rosa) {
      const inv = e.rosa.invierno, vals = inv.filter(v => v !== null);
      const max = Math.max(...vals), min = Math.min(...vals);
      html += svgRosa(e) +
        `<div class="lect">
          <div class="b" style="border-color:${AU.tono(max)}">
            <div class="k">Más sucio</div>
            <div class="v" style="color:${AU.tono(max)}">${AU.SECTORES[inv.indexOf(max)]}
              <small>${AU.num(max)} µg/m³</small></div></div>
          <div class="b" style="border-color:${AU.tono(min)}">
            <div class="k">Más limpio</div>
            <div class="v" style="color:${AU.tono(min)}">${AU.SECTORES[inv.indexOf(min)]}
              <small>${AU.num(min)} µg/m³</small></div></div>
          <div class="b"><div class="k">Contraste</div>
            <div class="v">${AU.num(max / min, 2)}×<small>entre extremos</small></div></div>
        </div>
        <p style="font-size:11.5px;color:var(--ink-2);margin:11px 0 0;line-height:1.5">
          Mediana horaria de invierno (mayo–agosto) por sector de procedencia del viento,
          sobre ${AU.miles(e.rosa.horas_invierno.reduce((a, b) => a + b, 0))} horas con
          viento y partículas medidos a la vez.</p>
        <div class="vivo" id="vivo"><div class="txt">
          <em>Viento ahora · Open-Meteo</em>consultando…</div></div>`;
    } else {
      html += '<p class="aviso-caja"><b>Esta estación no mide viento.</b> Registra MP2.5 ' +
        'pero no tiene anemómetro ni veleta, así que no hay rosa que dibujar. Sigue en el ' +
        'mapa porque su serie de partículas sí es válida.</p>';
    }

    html += '<div class="sec-t">Serie mensual</div>' + svgSerie(e);
    html += '<div class="sec-t">Año por año</div><div class="tabla-scroll"><table><thead><tr>' +
      '<th>Año</th><th>Días</th><th>Media</th><th>P98</th><th>&gt;50</th></tr></thead><tbody>';
    for (const a of Object.keys(e.anual).map(Number).sort((x, y) => x - y)) {
      const d = e.anual[a];
      html += `<tr class="${d.completo ? "" : "parcial"}"><td>${a}` +
        (d.completo ? "" : ' <span class="chip par">parcial</span>') +
        `</td><td>${d.dias}</td><td style="${d.completo ? "color:" + AU.tono(d.media) + ";" : ""}` +
        `font-weight:600">${AU.num(d.media)}</td><td>${AU.num(d.p98)}</td><td>${d.sobre50}</td></tr>`;
    }
    cuerpo.innerHTML = html + "</tbody></table></div>";

    if (e.rosa) mostrarViento(e);
  }

  /* El único dato que este sitio pide en vivo. Es meteorología —de dónde sopla
     ahora— para poder leer la rosa hoy. No es MP2.5 ni pronóstico. */
  async function mostrarViento(e) {
    const caja = $("#vivo");
    if (!caja) return;
    try {
      const c = await AU.vientoAhora(e.lat, e.lon);
      if (sel !== e.id) return;            // el usuario ya cambió de estación
      const dir = c.wind_direction_10m, sec = AU.sectorDe(dir);
      const i = AU.SECTORES.indexOf(sec);
      const v = e.rosa.invierno[i];
      caja.innerHTML =
        `<svg class="aguja" viewBox="0 0 40 40" aria-hidden="true">
           <circle cx="20" cy="20" r="17" fill="none" stroke="${AU.css("--line-2")}"/>
           <g transform="rotate(${dir + 180} 20 20)">
             <path d="M20 5 L25 26 L20 22 L15 26 Z" fill="${AU.tono(v)}"/></g>
         </svg>
         <div class="txt"><em>Viento ahora · Open-Meteo</em>
           Sopla del <b>${sec}</b> (${Math.round(dir)}°) a
           <b>${AU.num(c.wind_speed_10m)} km/h</b>, ${AU.num(c.temperature_2m)} °C.
           Con ese viento, la mediana histórica de invierno aquí es
           <b>${AU.num(v)} µg/m³</b>.</div>`;
    } catch (err) {
      if (sel !== e.id) return;
      caja.innerHTML = '<div class="txt"><em>Viento ahora · Open-Meteo</em>' +
        'No se pudo consultar el viento actual. La rosa de abajo no depende de esto: ' +
        'sale de las mediciones de SINCA ya guardadas.</div>';
    }
  }

  /* ================= gráficos del panel ================= */
  function svgRosa(e) {
    const R = 96, C = 118, inv = e.rosa.invierno;
    const max = Math.max(...inv.filter(v => v !== null));
    const L = AU.css("--line"), I3 = AU.css("--ink-3"), S = AU.css("--surface");
    const M = 'font-family="IBM Plex Mono,monospace"';
    let g = [0.25, 0.5, 0.75, 1].map(f =>
      `<circle cx="${C}" cy="${C}" r="${(R * f).toFixed(1)}" fill="none" stroke="${L}"/>`).join("");
    g += AU.SECTORES.map((s, i) => {
      const a = (i * 45 - 90) * Math.PI / 180;
      return `<line x1="${C}" y1="${C}" x2="${(C + Math.cos(a) * R).toFixed(1)}"
        y2="${(C + Math.sin(a) * R).toFixed(1)}" stroke="${L}"/>
        <text x="${(C + Math.cos(a) * (R + 14)).toFixed(1)}"
          y="${(C + Math.sin(a) * (R + 14) + 4).toFixed(1)}" text-anchor="middle" ${M}
          font-size="10" font-weight="600" fill="${I3}">${s}</text>`;
    }).join("");
    g += inv.map((v, i) => v === null ? "" :
      `<path d="${AU.arco(C, C, (v / max) * R, i)}" fill="${AU.tono(v)}" fill-opacity=".82"
        stroke="${S}" stroke-width="1"
        style="transform-origin:${C}px ${C}px;animation:brote .5s cubic-bezier(.34,1.3,.5,1) ${i * 55}ms both"/>`
    ).join("");
    return `<svg id="rosa" viewBox="0 0 236 236" role="img"
      aria-label="Rosa de contaminación de ${e.nombre}">${g}
      <text x="${C}" y="${C - R - 4}" text-anchor="middle" ${M} font-size="9"
        fill="${I3}">${AU.num(max, 0)} µg/m³</text></svg>`;
  }

  function svgSerie(e) {
    const w = 344, h = 96, ml = 26, mb = 15, mt = 8;
    const I3 = AU.css("--ink-3"), M = 'font-family="IBM Plex Mono,monospace"';
    const pts = clavesMes.map((k, i) => {
      const d = meses[k] && meses[k][String(e.id)];
      return { i, v: d ? d[0] : null };
    });
    const max = Math.max(35, ...pts.map(p => p.v || 0));
    const X = i => ml + (i / (clavesMes.length - 1)) * (w - ml - 4);
    const Y = v => mt + (1 - v / max) * (h - mt - mb);
    const ancho = X(1) - X(0);
    let bandas = "";
    clavesMes.forEach((k, i) => {
      const m = +k.slice(5);
      if (m >= 5 && m <= 8) bandas += `<rect x="${(X(i) - ancho / 2).toFixed(1)}" y="${mt}"
        width="${ancho.toFixed(2)}" height="${h - mt - mb}" fill="${AU.css("--accent-soft")}"/>`;
    });
    // La línea se corta donde no hubo dato en vez de saltar el hueco: un
    // segmento recto sobre un año sin mediciones inventa la tendencia.
    let seg = "", run = [];
    const cerrar = () => { if (run.length > 1) seg += `<polyline points="${run.join(" ")}"
      fill="none" stroke="${AU.css("--accent")}" stroke-width="1.5" stroke-linejoin="round"/>`; run = []; };
    pts.forEach(p => p.v === null ? cerrar() : run.push(X(p.i).toFixed(1) + "," + Y(p.v).toFixed(1)));
    cerrar();
    const marcas = pts.map(p => p.v === null ? "" :
      `<circle cx="${X(p.i).toFixed(1)}" cy="${Y(p.v).toFixed(1)}" r="1.6" fill="${AU.tono(p.v)}"/>`).join("");
    let anios = "";
    clavesMes.forEach((k, i) => { if (k.slice(5) === "01")
      anios += `<text x="${X(i).toFixed(1)}" y="${h - 3}" text-anchor="middle" ${M}
        font-size="8" fill="${I3}">${k.slice(2, 4)}</text>`; });
    return `<svg class="grafico" viewBox="0 0 ${w} ${h}" role="img"
      aria-label="Serie mensual de MP2.5 en ${e.nombre}">${bandas}
      <line x1="${ml}" y1="${Y(5).toFixed(1)}" x2="${w - 4}" y2="${Y(5).toFixed(1)}"
        stroke="${AU.css("--e0")}" stroke-dasharray="3 3"/>
      <text x="${ml - 4}" y="${(Y(5) + 3).toFixed(1)}" text-anchor="end" ${M} font-size="8"
        fill="${AU.css("--e0")}">5</text>
      <text x="${ml - 4}" y="${mt + 6}" text-anchor="end" ${M} font-size="8"
        fill="${I3}">${max.toFixed(0)}</text>${seg}${marcas}${anios}
      <text x="${w - 4}" y="${mt + 6}" text-anchor="end" ${M} font-size="8"
        fill="${I3}">bandas = invierno</text></svg>`;
  }

  /* ================= tarjetas de ciudad ================= */
  function pintarCiudades() {
    $("#ciudades").innerHTML = ciudades.map(c => {
      const r = c.resumen, col = AU.tono(r && r.media);
      return `<button class="cc" data-ciudad="${c.id}" aria-pressed="false" style="--bar:${col}">
        <h3>${c.nombre}</h3>
        <div class="sub">${AU.miles(c.poblacion)} habitantes · ${c.n_estaciones} estaciones</div>
        <div class="cifra"><span class="n" style="color:${col}">${AU.num(r && r.media)}</span>
          <span class="u">µg/m³ · media ${meta.anio_resumen}</span></div>
        <p class="pie"><b>${AU.num(r ? r.media / 5 : null)}×</b> la guía anual de la OMS.
          <b>${r ? r.sobre50 : "—"}</b> días sobre 50 µg/m³ al año.
          ${c.pct_lena_casen !== null ? `<b>${AU.num(c.pct_lena_casen)}%</b> de hogares con leña.` : ""}</p>
      </button>`;
    }).join("");
    $("#ciudades").querySelectorAll(".cc").forEach(b =>
      b.addEventListener("click", () => irACiudad(b.dataset.ciudad)));
    $("#escala-barra").innerHTML = AU.TONOS.map(v =>
      `<i style="background:${AU.css(v)}"></i>`).join("");
  }

  /* ================= reproductor ================= */
  const rango = $("#tiempo");
  rango.max = clavesMes.length - 1;
  rango.value = t;
  const verReloj = () => { $("#reloj").textContent = AU.mesLargo(clavesMes[t]); };
  rango.addEventListener("input", () => { t = +rango.value; verReloj(); dibujarMarcadores(); });

  $("#play").addEventListener("click", () => {
    tocando = !tocando;
    $("#icono-play").setAttribute("d", tocando ? "M3 1.5h3v10H3zM7 1.5h3v10H7z" : "M3 1.5v10l8-5z");
    $("#play").setAttribute("aria-label", tocando ? "Pausar" : "Reproducir la serie mensual");
    clearInterval(cronometro);
    if (tocando) cronometro = setInterval(() => {
      t = (t + 1) % clavesMes.length;
      rango.value = t; verReloj(); dibujarMarcadores();
    }, 240);
  });

  $("#ver-pais").addEventListener("click", () => {
    VISTA_PAIS();
    document.querySelectorAll(".cc").forEach(b => b.setAttribute("aria-pressed", "false"));
  });

  document.addEventListener("au:tema", () => {
    ponerTeselas(); pintarCiudades(); dibujarMarcadores();
    dibujarRosa(porId.get(sel), false); pintarDetalle();
  });

  $("#pie-corte").textContent = AU.mesLargo(meta.ultimo_mes);
  $("#pie-conteo").textContent =
    `${meta.conteos.estaciones} estaciones · ${meta.conteos.estaciones_con_viento} con viento`;
  pintarCiudades(); verReloj(); dibujarMarcadores(); pintarDetalle();
})();
