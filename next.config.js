/** @type {import('next').NextConfig} */
const nextConfig = {
  // Keep the PDF worker/native dependencies available in Vercel's Node runtime.
  serverExternalPackages: ['pdf-parse'],
  // Bound static-page worker fanout on small development/build machines.
  experimental: { cpus: 1 },
};

module.exports = nextConfig;

