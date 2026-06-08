/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#101b1d",
          800: "#243438",
          600: "#536468",
        },
        signal: {
          700: "#0f766e",
          600: "#0d9488",
          100: "#ccfbf1",
        },
        canvas: "#f4f7f6",
      },
      boxShadow: {
        panel: "0 1px 2px rgba(16, 27, 29, 0.06)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["Fira Code", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};
