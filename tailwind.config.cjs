module.exports = {
    content: [
        "./src/templates/**/*.html",
        "./src/**/templates/**/*.html",
        "./src/static/js/**/*.js"
    ],
    theme: {extend: {}},
    corePlugins: {preflight: false}, // chroni /admin
    plugins: [require("@tailwindcss/forms"), require("daisyui")],
    daisyui: {
        themes: [
            {
                lownLight: {
                    "primary": "#d4af37",
                    "primary-content": "#111111",
                    "secondary": "#1f2937",
                    "accent": "#caa84a",
                    "neutral": "#111827",
                    "base-100": "#ffffff",
                    "base-200": "#f5f6f8",
                    "base-300": "#e6e8ee",
                    "base-content": "#0b0b0c",
                    "info": "#0ea5e9",
                    "success": "#16a34a",
                    "warning": "#f59e0b",
                    "error": "#dc2626"
                }
            },
            {
                // SZARY DARK (bez czerni, „graphite”)
                lownDark: {
                    "primary": "#d4af37",
                    "primary-content": "#101216",
                    "secondary": "#404754",   // chłodna szarość pod elementy
                    "accent": "#b89b3c",

                    // KLUCZ: jaśniejsze tony bazowe
                    "base-100": "#2B3038",   // tło strony
                    "base-200": "#343B45",   // karty / sekcje
                    "base-300": "#3F4753",   // obramowania / paski
                    "base-content": "#EEF1F5",// tekst

                    "neutral": "#1d2128",
                    "info": "#7cc7ff",
                    "success": "#3ddc84",
                    "warning": "#fdba74",
                    "error": "#f87171"
                }
            }
        ]
    }
}