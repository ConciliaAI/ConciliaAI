// Concilia AI · tema para Tailwind CSS
/** @type {import('tailwindcss').Config} */
module.exports = {
  theme: {
    extend: {
      colors: {
        noite: '#0F1E3D',
        confere: '#2F6BFF',
        tinta: '#1D47B8',
        ambar: '#F5B700',
        nevoa: '#E9EFFD',
        papel: '#F7F8FA',
        apoio: '#44506A',
        borda: '#E1E5EE',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        titulo: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
      },
      fontWeight: {
        texto: '400',
        subtitulo: '700',
        titulo: '800',
      },
      letterSpacing: {
        titulo: '-0.035em',
      },
      borderRadius: {
        botao: '10px',
        card: '14px',
      },
    },
  },
};
