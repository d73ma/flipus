/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        sabbath: {
          dark: '#1B4332',
          cream: '#F5EFE0',
          gold: '#B8860B',
          charcoal: '#2D2A26',
          light: '#FAF9F5',
        }
      },
      fontFamily: {
        display: ['Playfair Display', 'serif'],
        body: ['Inter', 'sans-serif'],
      }
    }
  },
  plugins: []
}
