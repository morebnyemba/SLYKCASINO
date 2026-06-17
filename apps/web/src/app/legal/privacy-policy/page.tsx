import type { Metadata } from 'next';
import { LegalLayout } from '@/components/legal-layout';

export const metadata: Metadata = {
  title: 'Privacy Policy — SLYK Casino',
  description: 'How SLYK Casino collects, uses, and protects your personal data.',
};

export default function PrivacyPolicyPage() {
  return (
    <LegalLayout title="Privacy Policy" effectiveDate="[INSERT EFFECTIVE DATE]">
      <p>
        <strong>[COMPANY LEGAL NAME]</strong> (&quot;SLYK Casino&quot;, &quot;we&quot;, &quot;us&quot;) respects your
        privacy. This Privacy Policy explains what personal data we collect, why we collect it, how it is used,
        and the rights available to you, in line with the EU/UK General Data Protection Regulation (GDPR), the
        California Consumer Privacy Act (CCPA/CPRA), and other applicable data protection laws.
      </p>

      <h2>1. Who We Are</h2>
      <p>
        SLYK Casino is operated by <strong>[COMPANY LEGAL NAME]</strong>, registered at{' '}
        <strong>[REGISTERED ADDRESS]</strong>. For data protection queries, contact our Data Protection Officer /
        privacy team at <strong>[PRIVACY EMAIL]</strong>.
      </p>

      <h2>2. Data We Collect</h2>
      <ul>
        <li><strong>Account data:</strong> username, email address, password (hashed), date of birth, country.</li>
        <li><strong>Identity verification (KYC) data:</strong> government ID documents, proof of address, selfies/liveness checks, submitted to our identity verification provider when required to confirm your identity, age, and source of funds.</li>
        <li><strong>Financial data:</strong> deposit/withdrawal records, payment method details (processed by our payment providers — we do not store full card numbers), wallet balance and transaction history.</li>
        <li><strong>Gameplay data:</strong> bets placed, casino round outcomes, sportsbook activity, promotional activity.</li>
        <li><strong>Responsible gambling data:</strong> deposit limits, self-exclusion status and history.</li>
        <li><strong>Communications:</strong> live chat messages, support tickets, emails.</li>
        <li><strong>Technical data:</strong> IP address, device/browser information, cookies and similar identifiers (see our <a href="/legal/cookie-policy">Cookie Policy</a>).</li>
      </ul>

      <h2>3. Why We Process Your Data (Legal Basis)</h2>
      <ul>
        <li><strong>Contract performance</strong> — operating your account, processing bets/payments, providing customer support.</li>
        <li><strong>Legal obligation</strong> — age verification, identity verification (KYC), anti-money laundering (AML) checks, tax and regulatory reporting (see our <a href="/legal/aml-kyc-policy">AML &amp; KYC Policy</a>).</li>
        <li><strong>Legitimate interests</strong> — fraud prevention, platform security, service improvement, and enforcing our Terms.</li>
        <li><strong>Consent</strong> — marketing communications and non-essential cookies, which you may withdraw at any time.</li>
        <li><strong>Vital/public interest</strong> — responsible gambling safeguarding measures, including detecting at-risk play.</li>
      </ul>

      <h2>4. How We Use Your Data</h2>
      <ul>
        <li>To create and manage your account and wallet.</li>
        <li>To verify your identity, age, and the legitimacy of funds (KYC/AML).</li>
        <li>To process deposits, withdrawals, bets, and settle winnings.</li>
        <li>To detect, investigate, and prevent fraud, money laundering, and bonus abuse.</li>
        <li>To provide responsible gambling tools and identify signs of harmful play.</li>
        <li>To respond to support requests and live chat queries.</li>
        <li>To send service notifications (e.g., verification, password reset) and, where you have consented, marketing communications.</li>
        <li>To comply with regulatory, tax, and law enforcement requests.</li>
      </ul>

      <h2>5. Who We Share Your Data With</h2>
      <ul>
        <li><strong>Identity verification providers</strong> (e.g., our KYC partner) to confirm your identity and age.</li>
        <li><strong>Payment processors and banking partners</strong> to process deposits and withdrawals.</li>
        <li><strong>Game and odds providers</strong> to deliver casino games and sportsbook markets.</li>
        <li><strong>Regulators, law enforcement, and tax authorities</strong> where legally required.</li>
        <li><strong>IT and infrastructure providers</strong> (hosting, email delivery, analytics) under data processing agreements.</li>
        <li><strong>Professional advisors</strong> (legal, audit) where necessary.</li>
      </ul>
      <p>We do not sell your personal data to third parties for their own marketing purposes.</p>

      <h2>6. International Data Transfers</h2>
      <p>
        Where personal data is transferred outside your country of residence (including to <strong>[LIST PROCESSING COUNTRIES]</strong>), we rely on
        appropriate safeguards such as Standard Contractual Clauses or equivalent mechanisms recognized under
        applicable data protection law.
      </p>

      <h2>7. Data Retention</h2>
      <p>
        We retain account, financial, and KYC records for as long as required by applicable gambling, AML, and tax
        regulations (typically <strong>[X years, e.g., 5 years]</strong> after account closure), and other
        personal data only for as long as necessary for the purposes described above, after which it is deleted or
        anonymized.
      </p>

      <h2>8. Your Rights</h2>
      <p>Subject to applicable law, you have the right to:</p>
      <ul>
        <li><strong>Access</strong> — request a copy of the personal data we hold about you. You can self-serve this from <a href="/account/settings">Account Settings → Your Data</a>, which generates a full export of your profile, wallet, bets, casino rounds, promotions, and chat history.</li>
        <li><strong>Rectification</strong> — correct inaccurate or incomplete data via your profile or by contacting support.</li>
        <li><strong>Erasure</strong> — request deletion of your account and associated data via Account Settings, subject to records we are legally required to retain (e.g., AML/financial records).</li>
        <li><strong>Restriction & objection</strong> — object to or request restriction of certain processing, including direct marketing.</li>
        <li><strong>Portability</strong> — receive your data in a structured, machine-readable format (available via the data export feature above).</li>
        <li><strong>Withdraw consent</strong> — for marketing or non-essential cookies, at any time.</li>
        <li><strong>Lodge a complaint</strong> — with your local data protection authority, or with <strong>[SUPERVISORY AUTHORITY — INSERT ONCE LICENSED]</strong>.</li>
      </ul>
      <p>To exercise these rights, use the tools in Account Settings or contact <strong>[PRIVACY EMAIL]</strong>. We will respond within the timeframe required by applicable law (e.g., 30 days under GDPR).</p>

      <h2>9. Data Security</h2>
      <p>
        We use technical and organizational measures — including encryption in transit, access controls, and
        password hashing — to protect your personal data. No system is completely secure; please also protect your
        own login credentials.
      </p>

      <h2>10. Children</h2>
      <p>
        The Service is strictly for adults. We do not knowingly collect data from anyone under 18 (or the legal
        gambling age in their jurisdiction). Accounts found to belong to minors will be closed and any funds
        handled in accordance with applicable law.
      </p>

      <h2>11. Cookies</h2>
      <p>
        We use cookies and similar technologies as described in our <a href="/legal/cookie-policy">Cookie Policy</a>.
      </p>

      <h2>12. Changes to This Policy</h2>
      <p>
        We may update this Privacy Policy periodically. Material changes will be notified via the Service or
        email before taking effect.
      </p>

      <h2>13. Contact Us</h2>
      <p>
        For privacy questions or to exercise your rights, contact <strong>[PRIVACY EMAIL]</strong> or write to{' '}
        <strong>[REGISTERED ADDRESS]</strong>.
      </p>
    </LegalLayout>
  );
}
