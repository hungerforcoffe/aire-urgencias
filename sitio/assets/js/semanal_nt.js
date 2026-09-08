/* Análisis semanal: series de tiempo, espacial y proyección. Requiere comun.js.

   Es el segundo cuerpo de análisis del proyecto, hecho por otra persona y con
   otro diseño: la unidad es ciudad-semana y las preguntas son de series de
   tiempo. Los números salen de `semanal_nt.json`, que escribe
   `src/sitio/exportar_semanal.py` leyendo las salidas guardadas de los
   notebooks. Acá no se calcula nada.

   Se engancha en los contenedores que ya abrió el HTML por pregunta, así que
   sus paneles aparecen junto a los del modelo diario y no en una sección
   aparte: el lector recorre preguntas, no autores.

   Sobre Granger. El test se llama «de causalidad» por convención estadística y
   mide otra cosa: si el pasado de una serie mejora la predicción de otra. Eso
   es precedencia temporal predictiva. Acá se nombra así, siempre, y no es una
   sutileza de redacción — es la regla 1 del proyecto.

   Los colores se escriben como var(--…) dentro del SVG, igual que en modelo.js.
   Es lo que hace que el modo oscuro funcione sin repintar nada. */

(async function () {
  const $ = s => document.querySelector(s);

  // El JSON se pide de inmediato, pero los paneles se añaden a contenedores que
  // llena modelo.js con innerHTML. Se espera a que termine para no borrarlo.
  let d;
  try { d = await AU.cargar("semanal_nt"); }
  catch (e) { console.warn("análisis semanal no disponible:", e); return; }
  await (window.MODELO_LISTO || Promise.resolve());

  const NOMBRE = { coyhaique: "Coyhaique", santiago: "Santiago", talcahuano: "Talcahuano" };
  const ORDEN = ["coyhaique", "santiago", "talcahuano"];
  const SEM = '<span class="origen">Serie semanal · 2018–2025</span>';
  const ALFA = 0.05;

  /* ================= barras horizontales =================
     Una fila por categoría, la barra desde el cero. Sirve para todo lo que no
     es una estimación con intervalo: correlaciones, coeficientes, kilómetros.
     Cuando hay valores negativos el cero queda dentro del gráfico y la barra
     crece hacia el lado que le toca. */
  function barras(filas, { w = 340, izq = 120, alto = 24, unidad = "", dec = 2 } = {}) {
    const der = 40, arriba = 6, eje = 22;
    const h = arriba + filas.length * alto + eje;
    const lo = Math.min(0, ...filas.map(f => f.v));
    const hi = Math.max(0, ...filas.map(f => f.v));
    const aire = Math.max((hi - lo) * 0.08, 1e-6);
    const x = AU.escala(lo - (lo < 0 ? aire : 0), hi + aire, izq, w - der);
    const x0 = x(0);

    const grilla = AU.marcas(lo, hi).map(v =>
      `<line x1="${x(v).toFixed(1)}" y1="${arriba}" x2="${x(v).toFixed(1)}"
        y2="${arriba + filas.length * alto}" style="stroke:var(--linea)" stroke-width="1"
        ${Math.abs(v) < 1e-9 ? "" : 'stroke-dasharray="2 3"'}/>
      <text x="${x(v).toFixed(1)}" y="${h - 8}" text-anchor="middle"
        style="fill:var(--tinta-3)" font-size="9" font-family="var(--mono)"
        >${AU.num(v, v % 1 ? dec : 0)}</text>`).join("");

    const cuerpo = filas.map((f, i) => {
      const y = arriba + i * alto + 4;
      const a = Math.min(x0, x(f.v)), b = Math.max(x0, x(f.v));
      const col = f.color || "var(--s1)";
      return `<text x="${izq - 8}" y="${y + alto / 2 - 1}" text-anchor="end"
          style="fill:var(--tinta-2)" font-size="10.5">${f.nom}</text>
        <rect x="${a.toFixed(1)}" y="${y}" width="${Math.max(b - a, 1).toFixed(1)}"
          height="${alto - 9}" rx="1.5" style="fill:${col}" opacity="${f.tenue ? .35 : .85}"
          ><title>${f.nom}: ${AU.num(f.v, dec)}${unidad}</title></rect>
        <text x="${(b + 5).toFixed(1)}" y="${y + alto / 2 - 1}" style="fill:var(--tinta-3)"
          font-size="9.5" font-family="var(--mono)">${AU.num(f.v, dec)}</text>`;
    }).join("");

    return `<svg class="grafico" viewBox="0 0 ${w} ${h}" role="img"
      aria-label="Comparación por categoría${unidad ? " en " + unidad : ""}">
      ${grilla}
      <line x1="${x0.toFixed(1)}" y1="${arriba}" x2="${x0.toFixed(1)}"
        y2="${arriba + filas.length * alto}" style="stroke:var(--tinta-3)" stroke-width="1.2"/>
      ${cuerpo}
    </svg>`;
  }

  /* ================= barras apiladas al 100 % =================
     Tres bloques que suman el total. Se usa para el reparto de importancia,
     donde lo que importa es la proporción y no la magnitud absoluta. */
  function apiladas(filas, claves) {
    const izq = 90, alto = 30, w = 480, der = 12, arriba = 6;
    const h = arriba + filas.length * alto + 4;
    const ancho = w - izq - der;
    const cuerpo = filas.map((f, i) => {
      const y = arriba + i * alto + 5;
      let acum = 0;
      const trozos = claves.map(k => {
        const px = f[k.campo] / 100 * ancho;
        const x = izq + acum;
        acum += px;
        return `<rect x="${x.toFixed(1)}" y="${y}" width="${Math.max(px, 0).toFixed(1)}"
            height="${alto - 13}" style="fill:${k.color}" opacity=".85"
            ><title>${f.nom} — ${k.nom}: ${AU.num(f[k.campo], 1)} %</title></rect>
          ${px > 34 ? `<text x="${(x + px / 2).toFixed(1)}" y="${y + (alto - 13) / 2 + 3.5}"
            text-anchor="middle" style="fill:#fff" font-size="9.5"
            font-family="var(--mono)">${AU.num(f[k.campo], 1)}</text>` : ""}`;
      }).join("");
      return `<text x="${izq - 8}" y="${y + (alto - 13) / 2 + 3.5}" text-anchor="end"
        style="fill:var(--tinta-2)" font-size="11">${f.nom}</text>${trozos}`;
    }).join("");
    // Como el panel es de ancho completo, sin tope el SVG se estira el doble y
    // los rótulos de ciudad quedan enormes junto a franjas finísimas.
    return `<svg class="grafico" viewBox="0 0 ${w} ${h}" role="img"
      style="max-width:660px" preserveAspectRatio="xMinYMid meet"
      aria-label="Reparto de la importancia entre bloques de variables">${cuerpo}</svg>`;
  }

  const clave = items => `<div class="clave">${items.map(i =>
    `<span><i style="background:${i.color}"></i>${i.nom}</span>`).join("")}</div>`;

  /* ================= pregunta 2: ¿cuándo ocurre? ================= */
  const granger = d.granger;
  const sig = granger.filter(f => f.p_valor < ALFA);
  const lagsUnicos = [...new Set(granger.map(f => f.lag_semanas))].sort((a, b) => a - b);

  // Los encabezados son solo el número de semanas, y la unidad se explica en la
  // bajada del panel: con «1 sem … 4 sem» la tabla no cabe en una tarjeta de la
  // grilla y se corta justo en la columna que importa, la de 3 y 4 semanas.
  const tablaGranger = `<div class="scroll-x"><table>
    <thead><tr><th>Ciudad</th>${lagsUnicos.map(l =>
      `<th>${l}</th>`).join("")}</tr></thead>
    <tbody>${ORDEN.map(c => `<tr><td>${NOMBRE[c]}</td>${lagsUnicos.map(l => {
      const f = granger.find(g => g.ciudad_id === c && g.lag_semanas === l);
      const s = f && f.p_valor < ALFA;
      return `<td style="font-family:var(--mono);${s
        ? "color:var(--senal);font-weight:600" : "color:var(--tinta-3)"}"
        >${f ? AU.num(f.p_valor, 4) : "—"}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div>`;

  const multi = ORDEN.map(c => d.multivariado.find(f => f.ciudad_id === c));

  $("#p-cuando").insertAdjacentHTML("beforeend", `
    <section>
      ${SEM}
      <h3>La misma pregunta, semana a semana</h3>
      <p class="sub">Prueba de precedencia temporal de Granger: ¿el MP2.5 de semanas
        anteriores ayuda a predecir las urgencias, más allá de lo que ya predice su propio
        pasado? Columnas: rezago en semanas. Valores p; en naranja los menores
        que ${AU.num(ALFA, 2)}.</p>
      ${tablaGranger}
      <p class="lee">A escala semanal la respuesta es <b>casi siempre que no</b>:
        ${sig.length} de las ${granger.length} pruebas quedan bajo el umbral, y las
        ${sig.length} están en <b>Coyhaique</b>, a ${[...new Set(sig.map(f => f.lag_semanas))]
        .join(" y ")} semanas. Es la ciudad donde el humo llega en pulsos enormes y aislados
        en un valle sin ventilación, así que es donde una semana con humo se distingue de
        las demás. En Santiago y Talcahuano el MP2.5 semanal <b>no agrega información</b> a
        la que ya trae la inercia de las consultas.</p>
    </section>

    <section>
      ${SEM}
      <h3>Lo que se lleva el invierno</h3>
      <p class="sub">Coeficiente del MP2.5 sobre la tasa semanal de urgencias: crudo, y con
        temperatura, humedad e inercia de la propia serie.</p>
      ${barras(multi.flatMap(f => [
        { nom: NOMBRE[f.ciudad_id] + " · crudo", v: f.coef_crudo, color: "var(--s2)" },
        { nom: "con clima + inercia", v: f.coef_clima_ar1, color: "var(--s1)",
          tenue: f.p_clima_ar1 >= ALFA },
      ]), { izq: 132, dec: 2 })}
      <p class="lee">Crudo, el coeficiente es grande y significativo en las tres ciudades.
        Al controlar clima e inercia <b>se desploma</b>: en Santiago pasa de
        ${AU.num(multi[1].coef_crudo, 2)} a ${AU.num(multi[1].coef_clima_ar1, 2)} y deja de
        distinguirse del cero (p = ${AU.num(multi[1].p_clima_ar1, 2)}). Las barras pálidas son
        las que ya no se distinguen del cero. En <b>Coyhaique</b> el coeficiente ajustado sí
        sigue siendo distinto de cero, pero <b>cambia de signo</b>
        (${AU.num(multi[0].coef_clima_ar1, 2)}, p = ${AU.num(multi[0].p_clima_ar1, 4)}) — un
        resultado que el propio autor no interpreta y que a esta resolución conviene leer
        como una señal de que el modelo semanal está mal especificado, no como un hallazgo.</p>
    </section>

    <section class="full">
      <h3>Dos análisis, dos resoluciones, una misma lección</h3>
      <p class="sub">Por qué el modelo diario encuentra asociación en Santiago y el semanal
        no, sin que ninguno de los dos esté equivocado.</p>
      <p class="lee" style="border-top:0;padding-top:0">Son <b>preguntas distintas</b>. El
        modelo diario pregunta si un día peor que sus días vecinos del mismo mes trae más
        consultas <b>ese mismo día</b>; la curva de rezagos muestra que casi todo ocurre en
        el día 0 y se apaga al segundo. El análisis semanal pregunta si una semana con más
        humo <b>anticipa</b> la semana siguiente. Promediar siete días diluye un fenómeno que
        dura uno o dos, y por eso a escala semanal se desvanece.<br><br>
        Lo notable es que <b>los dos trabajos, hechos por separado y con métodos
        distintos, llegan al mismo sitio</b>: la resolución temporal decide el resultado.
        Coyhaique es la excepción en ambos —es donde el aire varía tanto que sobrevive al
        promedio semanal—, y ese acuerdo entre dos diseños independientes vale más que
        cualquiera de los dos números por separado.</p>
    </section>`);

  /* ================= pregunta 3: ¿dónde? ================= */
  const dist = ORDEN.map(c => d.distancias.find(f => f.ciudad_id === c));
  const viento = d.talcahuano_viento.filter(f => f.escenario.startsWith("Viento oeste"));

  $("#p-donde").insertAdjacentHTML("beforeend", `
    <section>
      ${SEM}
      <h3>¿Mide la estación el aire del hospital?</h3>
      <p class="sub">Distancia entre cada establecimiento de urgencia y su estación SINCA más
        cercana, en kilómetros.</p>
      ${barras(dist.map(f => ({
        nom: NOMBRE[f.ciudad_id] + ` (${f.establecimientos})`,
        v: f.km_media, color: "var(--s1)",
      })), { izq: 128, unidad: " km", dec: 2 })}
      <p class="lee">En <b>Coyhaique y Talcahuano</b> el establecimiento más lejano está a
        ${AU.num(Math.max(dist[0].km_max, dist[2].km_max), 1)} km: la estación mide,
        literalmente, el aire del barrio del hospital. <b>Santiago es otra cosa</b> — con
        ${dist[1].establecimientos} establecimientos repartidos en la cuenca, la media sube a
        ${AU.num(dist[1].km_media, 1)} km y el más lejano queda a
        ${AU.num(dist[1].km_max, 1)}. Aun así ${dist[1].n_alta} de los
        ${dist[1].establecimientos} están dentro de los 5 km que la literatura usa como
        umbral de representatividad. <b>La exposición de Santiago es la peor medida de las
        tres</b>, y eso empuja las estimaciones hacia el cero, no hacia arriba.</p>
    </section>

    <section>
      ${SEM}
      <h3>Cuando el viento manda más que la distancia</h3>
      <p class="sub">Hospital Las Higueras, Talcahuano. Correlación entre el MP2.5 de dos
        estaciones y sus urgencias diarias, en los ${viento[0] ? viento[0].n_dias : "—"} días
        de viento del oeste.</p>
      ${barras(viento.map(f => ({
        nom: f.escenario.replace("Viento oeste, ", ""), v: f.r,
        color: f.escenario.includes("San Vicente") ? "var(--s2)" : "var(--s1)",
      })), { izq: 150, dec: 4 })}
      <p class="lee">La estación de <b>San Vicente está cuatro veces más lejos</b> que
        Inpesca y aun así correlaciona más con las urgencias del hospital
        (${AU.num(viento[0].r, 3)} contra ${AU.num(viento[1].r, 3)}) cuando el viento sopla
        desde la bahía industrial hacia el recinto. Es el argumento empírico de que
        <b>asignar la estación más cercana no siempre asigna el aire que se respira</b>. Son
        correlaciones simples, sin ajuste por clima ni estacionalidad: sirven para comparar
        dos estaciones entre sí, no como estimación de asociación.</p>
    </section>`);

  /* ================= extensión: fase de proyección ================= */
  const imp = ORDEN.map(c => d.importancias.find(f => f.ciudad_id === c));
  const BLOQUES = [
    { campo: "inercia", nom: "Inercia de las consultas", color: "var(--s1)" },
    { campo: "clima", nom: "Clima y calendario", color: "var(--s2)" },
    { campo: "mp25", nom: "MP2.5", color: "var(--senal)" },
  ];
  // A modelo fijo: comparar el mejor de B contra el mejor de C mezclaría
  // algoritmos y mediría la diferencia entre ellos, no el aporte del MP2.5.
  const aporte = ORDEN.map(c => {
    const de = cfg => d.ablacion.filter(f => f.ciudad_id === c
      && f.configuracion.startsWith(cfg));
    const b = de("B"), cc = de("C");
    const pares = b.map(x => {
      const y = cc.find(z => z.modelo === x.modelo);
      // La base es la del MISMO modelo, no la mejor de la configuración:
      // una ganancia de un algoritmo sobre la base de otro no significa nada.
      return y ? { modelo: x.modelo, delta: y.r2 - x.r2, base: x.r2 } : null;
    }).filter(Boolean);
    return { ciudad_id: c, ...pares.reduce((a, b2) => a.delta > b2.delta ? a : b2) };
  });
  const sem = ORDEN.map(c => d.semaforo.find(f => f.ciudad_id === c));

  $("#p-extension").innerHTML = `
    <section class="full">
      ${SEM}
      <h3>De qué depende la demanda de la semana siguiente</h3>
      <p class="sub">Reparto de la importancia de las variables en el modelo de proyección,
        agrupada en tres bloques. Suma 100 % por ciudad.</p>
      ${clave(BLOQUES)}
      ${apiladas(imp.map(f => ({ ...f, nom: NOMBRE[f.ciudad_id] })), BLOQUES)}
      <p class="lee">La demanda de urgencias de la semana que viene la explica, sobre todo,
        <b>la demanda de esta semana</b>: entre ${AU.num(Math.min(...imp.map(f => f.inercia)), 0)}
        y ${AU.num(Math.max(...imp.map(f => f.inercia)), 0)} % del peso. Es lo que cabe
        esperar de un fenómeno que se contagia de persona a persona. El MP2.5 se queda con
        una franja pequeña, y su orden entre ciudades <b>repite el de todo lo demás en esta
        página</b>: ${ORDEN.slice().sort((a, b2) =>
          imp.find(f => f.ciudad_id === b2).mp25 - imp.find(f => f.ciudad_id === a).mp25)
          .map(c => `${NOMBRE[c]} ${AU.num(imp.find(f => f.ciudad_id === c).mp25, 1)} %`)
          .join(", ")}.</p>
    </section>

    <section class="full">
      ${SEM}
      <h3>¿Cuánto agrega saber el aire?</h3>
      <p class="sub">Ganancia en R² al añadir el MP2.5 a un modelo que ya conoce la inercia y
        el clima, comparando el mismo algoritmo con y sin él.</p>
      <div style="max-width:520px">${barras(aporte.map(f => ({
        nom: NOMBRE[f.ciudad_id], v: f.delta,
        color: f.delta > 0 ? "var(--s2)" : "var(--tinta-3)",
      })), { izq: 100, dec: 3 })}</div>
      <p class="lee">Poco: en el mejor de los casos, <b>Coyhaique</b>, el R² sube
        ${AU.num(aporte[0].delta, 3)} desde ${AU.num(aporte[0].base, 3)} con
        ${aporte[0].modelo}. La comparación se hace <b>a algoritmo fijo</b> y contra la base
        de ese mismo algoritmo: el mejor modelo cambia de familia entre configuraciones, y
        comparar el mejor de cada una mediría la diferencia entre algoritmos, no el aporte
        del aire. La lectura honesta es que <b>el MP2.5 no es lo que permite anticipar la
        demanda</b> — eso lo hace la inercia epidemiológica. Pero la ciudad donde más suma
        vuelve a ser Coyhaique, igual que en la prueba de precedencia y en el reparto de
        importancia: <b>tres métodos distintos, el mismo orden entre ciudades</b>.</p>
    </section>

    <section class="full">
      ${SEM}
      <h3 class="alerta">Qué tan lejos llega esto, y qué no</h3>
      <p class="sub">Detección de semanas de alta demanda con una semana de anticipación,
        prueba ciega sobre 2024.</p>
      <div class="scroll-x"><table>
        <thead><tr><th>Ciudad</th><th>Semanas sobre el P75</th><th>Detectadas</th>
          <th>Sensibilidad</th><th>Precisión</th></tr></thead>
        <tbody>${sem.map(f => `<tr><td>${NOMBRE[f.ciudad_id]}</td>
          <td class="n">${f.semanas_saturacion}</td>
          <td class="n">${f.semanas_detectadas}</td>
          <td class="n">${AU.num(f.recall, 1)} %</td>
          <td class="n">${AU.num(f.precision, 1)} %</td></tr>`).join("")}</tbody>
      </table></div>
      <p class="lee">Sobre un solo año de prueba y tres ciudades, esto <b>no es un sistema
        validado</b>: es un ejercicio que muestra que la demanda respiratoria es en buena
        medida anticipable a una semana, y que el aire aporta poco a esa anticipación.
        Talcahuano, con ${sem[2].semanas_saturacion} semanas sobre el umbral en todo el año,
        no tiene casos suficientes para que su cifra signifique algo.<br><br>
        <b>Nada de esta sección responde la pregunta del estudio</b>, que es sobre
        asociación y no sobre pronóstico. Está publicada porque su respuesta acota la
        anterior: si el MP2.5 fuera el motor de las urgencias, aquí se habría notado.</p>
    </section>`;
})();
