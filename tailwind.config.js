/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['Outfit', 'sans-serif'],
        body: ['Inter', 'sans-serif'],
      },
      colors: {
        coral: '#ff158a',
        'warm-yellow': '#fff48d',
        mint: '#7af7f7',
        'mint-green': '#83f582',
        'vivid-pink': '#fd74fd',
        'soft-pink': '#fd97fd',
        'soft-orange': '#fdad70',
        dark: '#1d1c1c',
      },
      boxShadow: {
        card: '0 6px 0 0 #1d1c1c',
        'card-sm': '0 4px 0 0 #1d1c1c',
        pill: '0 3px 0 0 #1d1c1c',
      },
      borderRadius: {
        card: '12px',
      },
      animation: {
        gradient: 'gradient 10s ease infinite',
        float: 'float 6s ease-in-out infinite',
        'float-delay': 'float 6s ease-in-out 2s infinite',
        'float-slow': 'float 8s ease-in-out 1s infinite',
        'fade-in-up': 'fadeInUp 0.6s ease-out forwards',
        'scale-in': 'scaleIn 0.5s ease-out forwards',
        'slide-in-right': 'slideInRight 0.4s ease-out forwards',
        'slide-in-left': 'slideInLeft 0.4s ease-out forwards',
        'pulse-highlight': 'pulseHighlight 2s ease-in-out infinite',
        'bar-grow': 'barGrow 1s ease-out forwards',
        'spin-slow': 'spin 3s linear infinite',
      },
      keyframes: {
        gradient: {
          '0%, 100%': { backgroundPosition: '50% 50%' },
          '25%': { backgroundPosition: '0% 0%' },
          '50%': { backgroundPosition: '50% 50%' },
          '75%': { backgroundPosition: '100% 100%' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px) rotate(0deg)' },
          '33%': { transform: 'translateY(-15px) rotate(2deg)' },
          '66%': { transform: 'translateY(-8px) rotate(-1deg)' },
        },
        fadeInUp: {
          from: { opacity: '0', transform: 'translateY(30px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        scaleIn: {
          from: { opacity: '0', transform: 'scale(0.8)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
        slideInRight: {
          from: { opacity: '0', transform: 'translateX(40px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        slideInLeft: {
          from: { opacity: '0', transform: 'translateX(-40px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        pulseHighlight: {
          '0%, 100%': { backgroundColor: 'rgba(255, 244, 141, 0.3)' },
          '50%': { backgroundColor: 'rgba(255, 244, 141, 0.7)' },
        },
        barGrow: {
          from: { transform: 'scaleY(0)' },
          to: { transform: 'scaleY(1)' },
        },
      },
    },
  },
  plugins: [],
};
