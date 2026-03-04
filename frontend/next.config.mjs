/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'export',
    images: {
        unoptimized: true
    },
    swcMinify: false,
    transpilePackages: ['framer-motion', 'starknet', 'get-starknet']
};

export default nextConfig;
