/** @type {import('next').NextConfig} */
const nextConfig = {
  // Keep the PDF worker/native dependencies available in Vercel's Node runtime.
  serverExternalPackages: ['pdf-parse'],
};

module.exports = nextConfig;

