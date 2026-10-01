'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

/**
 * Renders children into document.body. Needed for popovers opened from the header:
 * its backdrop-filter makes it the containing block for `position: fixed`
 * descendants, which would otherwise clip overlays to the 64px header.
 */
export function Portal({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted ? createPortal(children, document.body) : null;
}
