import path from 'path';
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Self-contained server output for a small Docker runner image.
  output: 'standalone',
  // Monorepo: trace files from the workspace root (top-level option in Next 16).
  outputFileTracingRoot: path.join(__dirname, '../../'),
  // Compile the shared workspace UI package (it ships .tsx source, not built JS).
  transpilePackages: ['@slyk/ui'],
};

export default nextConfig;
