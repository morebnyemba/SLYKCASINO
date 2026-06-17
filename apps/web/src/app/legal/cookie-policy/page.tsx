import type { Metadata } from 'next';
import { LegalLayout } from '@/components/legal-layout';

export const metadata: Metadata = {
  title: 'Cookie Policy — SLYK Casino',
  description: 'How SLYK Casino uses cookies and similar technologies.',
};

export default function CookiePolicyPage() {
  return (
    <LegalLayout title="Cookie Policy" effectiveDate="[INSERT EFFECTIVE DATE]">
      <p>
        This Cookie Policy explains how <strong>[COMPANY LEGAL NAME]</strong> (&quot;SLYK Casino&quot;) uses
        cookies and similar tracking technologies on our website, and how you can control them, in line with the
        EU ePrivacy Directive, GDPR, and other applicable laws.
      </p>

      <h2>1. What Are Cookies?</h2>
      <p>
        Cookies are small text files stored on your device when you visit a website. They help the site function,
        remember your preferences, and provide analytics on how the Service is used.
      </p>

      <h2>2. Categories of Cookies We Use</h2>
      <ul>
        <li><strong>Strictly necessary cookies</strong> — required for login sessions, account security, and core platform functionality (e.g., authentication tokens). These cannot be disabled without affecting the Service.</li>
        <li><strong>Functional cookies</strong> — remember your preferences (e.g., display settings, recently viewed games/markets).</li>
        <li><strong>Analytics/performance cookies</strong> — help us understand how the Service is used so we can improve it.</li>
        <li><strong>Marketing/advertising cookies</strong> — used to measure the effectiveness of promotions and, where applicable, deliver relevant offers. Used only with your consent.</li>
      </ul>

      <h2>3. Third-Party Cookies</h2>
      <p>
        Some cookies are set by third-party services we use, such as analytics providers, payment processors, and
        identity verification partners. These third parties have their own privacy and cookie policies.
      </p>

      <h2>4. Managing Your Cookie Preferences</h2>
      <p>
        On your first visit, you will be asked to accept or customize non-essential cookies. You can change your
        preferences at any time via <strong>[COOKIE PREFERENCE LINK/CENTER]</strong> or through your browser
        settings, which allow you to block or delete cookies. Disabling strictly necessary cookies may prevent you
        from logging in or using core features.
      </p>

      <h2>5. Changes to This Policy</h2>
      <p>We may update this Cookie Policy from time to time. Changes will be posted on this page with a revised effective date.</p>

      <h2>6. Contact Us</h2>
      <p>Questions about our use of cookies can be sent to <strong>[PRIVACY EMAIL]</strong>.</p>
    </LegalLayout>
  );
}
