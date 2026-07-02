'use client';

import { createContext, useContext } from 'react';
import { DEFAULT_IDENTITY, type SiteIdentity } from '@/lib/site-identity';

const IdentityContext = createContext<SiteIdentity>(DEFAULT_IDENTITY);

/** Fed by a server-side fetch in the root layout — see IdentityProvider usage there. */
export function IdentityProvider({ value, children }: { value: SiteIdentity; children: React.ReactNode }) {
  return <IdentityContext.Provider value={value}>{children}</IdentityContext.Provider>;
}

export function useSiteIdentity(): SiteIdentity {
  return useContext(IdentityContext);
}
