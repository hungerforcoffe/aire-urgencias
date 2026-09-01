import { useState } from "react";
import PaginaInicio from "./pages/PaginaInicio";
import PaginaAnalisis from "./pages/PaginaAnalisis";
import PaginaMetodologia from "./pages/PaginaMetodologia";

type Pagina = "inicio" | "analisis" | "metodologia";

function Barra({
  pagina,
  setPagina,
  oscuro,
  setOscuro,
}: {
  pagina: Pagina;
  setPagina: (p: Pagina) => void;
  oscuro: boolean;
  setOscuro: (v: boolean) => void;
}) {
  const link = (p: Pagina, label: string) => (
    <button
      onClick={() => setPagina(p)}
      style={{
        background: pagina === p ? "rgba(255,255,255,0.12)" : "none",
        border: "none",
        color: pagina === p ? "#fff" : "rgba(255,255,255,0.6)",
        fontFamily: "var(--sans)",
        fontSize: ".78rem",
        fontWeight: 500,
        letterSpacing: ".04em",
        textTransform: "uppercase",
        padding: "6px 12px",
        borderRadius: 6,
        cursor: "pointer",
        transition: "all .15s",
      }}
    >
      {label}
    </button>
  );

  return (
    <div
      style={{
        position: "sticky",
        top: 0,
        zIndex: 200,
        height: 52,
        background: "var(--navy)",
        display: "flex",
        alignItems: "center",
        padding: "0 20px",
        gap: 8,
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        boxShadow: "0 1px 8px rgba(0,0,0,0.25)",
        flexShrink: 0,
      }}
    >
      <button
        onClick={() => setPagina("inicio")}
        style={{
          fontFamily: "var(--serif)",
          fontSize: "1.05rem",
          fontWeight: 600,
          color: "#fff",
          background: "none",
          border: "none",
          cursor: "pointer",
          paddingRight: 24,
          marginRight: 8,
          borderRight: "1px solid rgba(255,255,255,0.12)",
          display: "flex",
          alignItems: "center",
          gap: 2,
          whiteSpace: "nowrap",
        }}
      >
        Aire<span style={{ color: "var(--celeste)" }}>·</span>Urgencias
      </button>

      <nav style={{ display: "flex", gap: 2, marginRight: "auto" }}>
        {link("inicio", "Red MP2.5")}
        {link("analisis", "Análisis")}
        {link("metodologia", "Metodología")}
      </nav>

      <div
        style={{
          display: "flex",
          gap: 16,
          fontFamily: "var(--mono)",
          fontSize: ".68rem",
          color: "rgba(255,255,255,0.4)",
          marginRight: 12,
        }}
      >
        <span>SINCA / MMA</span>
        <span>
          corte <b style={{ color: "var(--celeste)" }}>ago 2026</b>
        </span>
        <span>
          <b style={{ color: "var(--celeste)" }}>16</b> estaciones
        </span>
      </div>

      <button
        onClick={() => setOscuro(!oscuro)}
        aria-label="Cambiar tema"
        style={{
          background: "none",
          border: "1px solid rgba(255,255,255,0.18)",
          color: "rgba(255,255,255,0.65)",
          width: 30,
          height: 30,
          borderRadius: "50%",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
          <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 1.5v11a5.5 5.5 0 010-11z" />
        </svg>
      </button>
    </div>
  );
}

export default function App() {
  const [pagina, setPagina] = useState<Pagina>("inicio");
  const [oscuro, setOscuro] = useState(false);

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: oscuro ? "#07111f" : "var(--fondo)",
        color: oscuro ? "#ddeeff" : "var(--texto)",
        "--panel": oscuro ? "#0d2040" : "#ffffff",
        "--panel-alt": oscuro ? "#102548" : "#f7faff",
        "--fondo": oscuro ? "#07111f" : "#f0f5fb",
        "--fondo-alt": oscuro ? "#0c1b30" : "#e4edf8",
        "--texto": oscuro ? "#ddeeff" : "#0c1c30",
        "--texto-2": oscuro ? "#7da8cc" : "#3d5a7a",
        "--texto-3": oscuro ? "#4a6e8a" : "#7a99b8",
        "--borde": oscuro ? "rgba(96,165,250,0.12)" : "rgba(26,74,138,0.15)",
        "--borde-f": oscuro ? "rgba(96,165,250,0.30)" : "rgba(26,74,138,0.35)",
      } as React.CSSProperties}
    >
      <Barra
        pagina={pagina}
        setPagina={setPagina}
        oscuro={oscuro}
        setOscuro={setOscuro}
      />
      <div style={{ flex: 1, overflow: "auto" }}>
        {pagina === "inicio" && <PaginaInicio />}
        {pagina === "analisis" && <PaginaAnalisis />}
        {pagina === "metodologia" && <PaginaMetodologia />}
      </div>
    </div>
  );
}
