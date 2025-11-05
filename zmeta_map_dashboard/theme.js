const THEME_URL = "/assets/themes.json";
const STORAGE_SKIN = "zmeta.skin";
const STORAGE_DECOR = "zmeta.decor";

const FALLBACK_THEMES = {
  functional: {
    severity: {
      crit: "#FF3B30",
      warn: "#FF9500",
      info: "#1F7AE0",
      ok: "#16B365",
    },
    modality: {
      rf: "#007AFF",
      thermal: "#FF3B30",
      eo: "#34C759",
      ir: "#FF9500",
      acoustic: "#8E8E93",
    },
  },
  skins: {
    nostromo: {
      bg: "#0F1115",
      panel: "#141922",
      text: "#E8EDF3",
      subtext: "#8B94A7",
      accent: "#5B2E90",
      border: "#1E2530",
      hover: "#18202B",
      radius: "14px",
      border_width: "1px",
      shadow: "0 20px 32px rgba(4, 8, 16, 0.55)",
      glass: "blur(14px)",
      glow: "0 0 18px rgba(91, 46, 144, 0.35)",
      grid_spacing: 112,
      scan_step: 4,
      decor: { grid: true, scanlines: 0.04, glow: 0 },
    },
    shinjuku: {
      bg: "#0E0E12",
      panel: "#13131A",
      text: "#E5E7EB",
      subtext: "#9AA2B1",
      accent: "#00E6D1",
      border: "#1A1A22",
      hover: "#15151E",
      radius: "18px",
      border_width: "1px",
      shadow: "0 24px 42px rgba(0, 0, 0, 0.65)",
      glass: "blur(18px)",
      glow: "0 0 22px rgba(0, 230, 209, 0.45)",
      grid_spacing: 96,
      scan_step: 3,
      decor: { grid: false, scanlines: 0, glow: 0.1 },
    },
    section9: {
      bg: "#0A0F14",
      panel: "#0D1218",
      text: "#DCE7F5",
      subtext: "#9AB6D1",
      accent: "#7FB7FF",
      border: "#0F1620",
      hover: "#0C141C",
      radius: "16px",
      border_width: "1px",
      shadow: "0 28px 48px rgba(6, 12, 20, 0.7)",
      glass: "blur(20px)",
      glow: "0 0 20px rgba(127, 183, 255, 0.35)",
      grid_spacing: 128,
      scan_step: 4,
      decor: { grid: true, scanlines: 0, glow: 0.06 },
    },
  },
};

let themeData = null;
let themePromise = null;
let currentSkinName = null;
let functionalApplied = false;

function deepClone(value) {
  return value == null ? value : JSON.parse(JSON.stringify(value));
}

function safeJsonParse(text, fallback) {
  try {
    const data = JSON.parse(text);
    return data == null ? fallback : data;
  } catch (err) {
    return fallback;
  }
}

function applyFunctionalTokens(functional) {
  if (!functional || functionalApplied) {
    return;
  }
  const root = document.documentElement;
  Object.entries(functional.severity || {}).forEach(([key, value]) => {
    root.style.setProperty(`--severity-${key}`, value);
  });
  Object.entries(functional.modality || {}).forEach(([key, value]) => {
    root.style.setProperty(`--modality-${key}`, value);
  });
  functionalApplied = true;
}

export async function loadThemes() {
  if (!themePromise) {
    themePromise = fetch(THEME_URL, { cache: "no-store" })
      .then((resp) => {
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        return resp.json();
      })
      .catch(() => deepClone(FALLBACK_THEMES));
  }
  if (!themeData) {
    themeData = await themePromise;
    if (!themeData || !themeData.skins) {
      themeData = deepClone(FALLBACK_THEMES);
    }
    applyFunctionalTokens(themeData.functional);
  }
  return themeData;
}

function getSkin(name) {
  const data = themeData || FALLBACK_THEMES;
  return data.skins[name] || data.skins.nostromo || Object.values(data.skins)[0];
}

function setCssVariables(tokens) {
  const root = document.documentElement;
  const entries = {
    "--bg": tokens.bg,
    "--panel": tokens.panel,
    "--text": tokens.text,
    "--subtext": tokens.subtext,
    "--accent": tokens.accent,
    "--border": tokens.border,
    "--hover": tokens.hover,
    "--panel-radius": tokens.radius || "14px",
    "--panel-border-width": tokens.border_width || "1px",
    "--panel-shadow": tokens.shadow || "0 18px 32px rgba(0,0,0,0.6)",
    "--panel-glass": tokens.glass || "blur(16px)",
    "--panel-glow": tokens.glow || "none",
    "--grid-step": `${tokens.grid_spacing || 120}px`,
    "--scanline-step": `${tokens.scan_step || 4}px`,
  };
  Object.entries(entries).forEach(([key, value]) => {
    root.style.setProperty(key, value);
  });
}

export async function applySkin(name, { silent = false } = {}) {
  await loadThemes();
  const tokens = getSkin(name);
  setCssVariables(tokens);
  document.body.dataset.skin = name;
  currentSkinName = name;
  if (!silent) {
    document.dispatchEvent(new CustomEvent("zmeta:skin-change", { detail: { name, skin: tokens } }));
  }
  return tokens;
}

export function currentSkin() {
  if (currentSkinName) {
    return currentSkinName;
  }
  const stored = localStorage.getItem(STORAGE_SKIN);
  return stored || document.body.dataset.skin || "nostromo";
}

export function persistSkin(name) {
  try {
    localStorage.setItem(STORAGE_SKIN, name);
  } catch (err) {
    console.warn("Unable to persist skin", err);
  }
}

export function skinNames() {
  if (!themeData) {
    return Object.keys(FALLBACK_THEMES.skins);
  }
  return Object.keys(themeData.skins);
}

export function readDecorPreference() {
  const raw = localStorage.getItem(STORAGE_DECOR);
  if (!raw) {
    return null;
  }
  return safeJsonParse(raw, null);
}

export function persistDecorPreference(value) {
  try {
    localStorage.setItem(STORAGE_DECOR, JSON.stringify(value));
  } catch (err) {
    console.warn("Unable to persist decor settings", err);
  }
}

export function decorDefaults(name) {
  const theme = getSkin(name);
  const raw = theme.decor || {};
  const scanlines = typeof raw.scanlines === "number" ? raw.scanlines : raw.scanlines ? 0.06 : 0;
  const glow = typeof raw.glow === "number" ? raw.glow : raw.glow ? 0.06 : 0;
  return {
    grid: !!raw.grid,
    scanlines: scanlines > 0,
    glow: glow > 0,
    scanlinesValue: scanlines,
    glowValue: glow,
    gridSpacing: theme.grid_spacing || 120,
    scanStep: theme.scan_step || 4,
  };
}

export function getSkinTokens(name) {
  if (!themeData) {
    return FALLBACK_THEMES.skins[name] || null;
  }
  return themeData.skins[name] || null;
}
