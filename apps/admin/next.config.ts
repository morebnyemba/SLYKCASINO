import path from 'path';
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  output: 'standalone',
  outputFileTracingRoot: path.join(__dirname, '../../'),
  transpilePackages: ['@slyk/ui'],

  // CRITICAL: the Admin UI shares one domain with the Player UI, so it must
  // namespace itself under /admin-portal. basePath scopes routes AND emits the
  // app's assets under /admin-portal/_next/* so they never collide with the
  // Player app's /_next/*. assetPrefix keeps static asset URLs consistent.
  basePath: '/admin-portal',
  assetPrefix: '/admin-portal',
  async redirects() {
    // The crash game's admin page moved with its rename to Aviator.
    return [{ source: '/games/jet', destination: '/games/aviator', permanent: true }];
  },
};

export default nextConfig;
