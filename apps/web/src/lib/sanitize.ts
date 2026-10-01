import DOMPurify from 'dompurify';

/** Sanitize provider/admin-authored HTML (e.g. promotion terms) before
 * rendering with dangerouslySetInnerHTML, so a compromised or careless
 * content source can't inject scripts into a player's session. */
export function sanitizeHtml(html: string): string {
  if (typeof window === 'undefined') return ''; // server-render: defer to client
  return DOMPurify.sanitize(html);
}
