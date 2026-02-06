export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Custom network visualization colors
        network: {
          node: {
            server: '#3b82f6',
            workstation: '#22c55e',
            router: '#f97316',
            switch: '#8b5cf6',
            firewall: '#ef4444',
            printer: '#ec4899',
            iot: '#06b6d4',
            unknown: '#6b7280',
          },
          edge: {
            default: '#64748b',
            active: '#3b82f6',
            highlight: '#f97316',
          },
        },
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.3s ease-in-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(-10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
