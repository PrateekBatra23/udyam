/** Accel Business palette (spec 14D): primary blue, savings green, neutrals. */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        accel: { DEFAULT: "#1F4E8C", dark: "#163a68", light: "#e8eff8" },
        save: "#10B981",
      },
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
