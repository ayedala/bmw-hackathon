import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    // Radii are capped at 6px (rounded-md) by design.
    borderRadius: {
      none: "0",
      sm: "3px",
      DEFAULT: "4px",
      md: "6px",
      full: "9999px",
    },
    extend: {
      colors: {
        // BMW Product Decision Lab tokens (ui/workbench.css on main), shared with the Streamlit workbench.
        canvas: "#F5F6F8",
        ink: "#23272C",
        brand: { DEFAULT: "#0066CC", hover: "#0057AD", soft: "#EEF5FD", line: "#B9D3F0" },
        primary: { DEFAULT: "#0066CC", foreground: "#FFFFFF" },
        // Cool BMW neutrals replace Tailwind's slate/zinc so every screen inherits them.
        slate: {
          50: "#F7F8FA",
          100: "#EEF0F3",
          200: "#DCE1E7",
          300: "#C3CAD3",
          400: "#98A1AC",
          500: "#626B76",
          600: "#4E5661",
          700: "#3B424B",
          800: "#2A3038",
          900: "#1C2127",
          950: "#121519",
        },
        zinc: {
          50: "#F7F8FA",
          100: "#EEF0F3",
          200: "#DCE1E7",
          300: "#C3CAD3",
          400: "#98A1AC",
          500: "#626B76",
          600: "#4E5661",
          700: "#3B424B",
          800: "#2A3038",
          900: "#23272C",
          950: "#16191D",
        },
      },
      fontFamily: {
        sans: [
          "var(--font-plex)",
          "IBM Plex Sans",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      keyframes: {
        "slide-in": { from: { transform: "translateX(16px)", opacity: "0" }, to: { transform: "translateX(0)", opacity: "1" } },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
      },
      animation: {
        "slide-in": "slide-in 140ms ease-out",
        "fade-in": "fade-in 120ms ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
