/**
 * Sign-in/sign-up flows get a focused page: no casino/sports nav rail and no
 * bet-slip rail beside the form, just the header, the form and the footer.
 */
const AUTH_ROUTES = ['/login', '/register', '/forgot-password', '/reset-password', '/verify-email'];

export function isAuthRoute(pathname: string | null) {
  return !!pathname && AUTH_ROUTES.some((r) => pathname === r || pathname.startsWith(`${r}/`));
}
