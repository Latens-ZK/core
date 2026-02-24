import type { Config } from "tailwindcss";

const config: Config = {
    content: [
        "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
        "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
        "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    ],
    theme: {
        extend: {
            colors: {
                starknet: '#535bf2',
                silver: {
                    primary: '#c0c0c0',
                    secondary: '#8a8a8a',
                },
                'accent-silver': '#e5e7eb',
                charcoal: '#121212',
                glass: {
                    bg: 'rgba(255, 255, 255, 0.03)',
                    border: 'rgba(255, 255, 255, 0.08)',
                }
            }
        },
    },
    plugins: [],
};
export default config;
