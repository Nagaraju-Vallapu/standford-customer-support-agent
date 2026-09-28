/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172b2a",
        forest: "#1e6257",
        mint: "#e3f2eb",
        coral: "#db775a",
        paper: "#f5f6f2",
      },
      fontFamily: {
        sans: ["DM Sans", "Avenir Next", "sans-serif"],
        display: ["Manrope", "Avenir Next", "sans-serif"],
      },
    },
  },
  plugins: [],
};