import path from 'path';
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Self-contained server output for a small Docker runner image.
  output: 'standalone',
  // Monorepo: trace files from the workspace root (top-level option in Next 16).
  outputFileTracingRoot: path.join(__dirname, '../../'),
  // Compile the shared workspace UI package (it ships .tsx source, not built JS).
  transpilePackages: ['@slyk/ui'],
  // The sportsbook is the landing page; the promo lobby lives at /home.
  // Temporary (307) so the default page can be changed again later.
  async redirects() {
    return [
      { source: '/', destination: '/sportsbook', permanent: false },
      // The casino (stub slots + crash) is retired; old links land on the sportsbook.
      { source: '/casino', destination: '/sportsbook', permanent: false },
      { source: '/casino/:path*', destination: '/sportsbook', permanent: false },
      { source: '/account/casino', destination: '/account', permanent: false },
      // Tournaments only scored casino play.
      { source: '/tournaments', destination: '/promotions', permanent: false },
    ];
  },
};

export default nextConfig;
