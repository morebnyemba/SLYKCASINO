import type { Metadata } from 'next';
import { LegalLayout } from '@/components/legal-layout';

export const metadata: Metadata = {
  title: 'Terms & Conditions — SLYK Casino',
  description: 'Terms and conditions governing use of the SLYK Casino platform.',
};

export default function TermsPage() {
  return (
    <LegalLayout title="Terms & Conditions" effectiveDate="[INSERT EFFECTIVE DATE]">
      <p>
        These Terms & Conditions (&quot;Terms&quot;) form a binding agreement between you (&quot;Player&quot;,
        &quot;you&quot;) and <strong>[COMPANY LEGAL NAME]</strong>, registered at <strong>[REGISTERED ADDRESS]</strong>
        (&quot;SLYK Casino&quot;, &quot;we&quot;, &quot;us&quot;), governing your access to and use of the SLYK
        Casino website, sportsbook, and casino games (the &quot;Service&quot;). By creating an account or using the
        Service you agree to be bound by these Terms, our{' '}
        <a href="/legal/privacy-policy">Privacy Policy</a>, <a href="/legal/cookie-policy">Cookie Policy</a>,{' '}
        <a href="/legal/responsible-gambling">Responsible Gambling Policy</a>, and{' '}
        <a href="/legal/aml-kyc-policy">AML &amp; KYC Policy</a>. If you do not agree, you must not use the Service.
      </p>

      <h2>1. Licensing & Eligibility</h2>
      <p>
        SLYK Casino operates under licence <strong>[LICENCE NUMBER / REGULATOR — INSERT ONCE LICENSED]</strong>.
        Until a licence is obtained and confirmed here, the Service should be treated as operating in a pre-launch
        or test capacity and is not available to residents of jurisdictions where online gambling is prohibited or
        unlicensed.
      </p>
      <ul>
        <li>You must be at least <strong>18 years old</strong> (or the legal gambling age in your jurisdiction, if higher) to register or play.</li>
        <li>You must be legally permitted to participate in online gambling under the laws of your country/state of residence.</li>
        <li>You may register only one account. Duplicate accounts may be suspended and any associated funds forfeited pending investigation.</li>
        <li>You confirm that funds deposited are your own and obtained legitimately.</li>
        <li>We reserve the right to verify your age and identity at any time (see our <a href="/legal/aml-kyc-policy">AML &amp; KYC Policy</a>) and to restrict or close accounts that fail verification.</li>
      </ul>

      <h2>2. Account Registration & Security</h2>
      <ul>
        <li>You are responsible for maintaining the confidentiality of your login credentials and for all activity occurring under your account.</li>
        <li>You must notify us immediately at <strong>[SUPPORT EMAIL]</strong> of any unauthorized use of your account.</li>
        <li>We may suspend or terminate accounts that provide false registration information, violate these Terms, or are used for fraud, collusion, bonus abuse, or money laundering.</li>
      </ul>

      <h2>3. Deposits, Withdrawals & Wallet</h2>
      <ul>
        <li>All transactions are processed in the currency specified on the platform. Applicable fees, if any, will be disclosed before you confirm a transaction.</li>
        <li>Withdrawals are paid to verified accounts only and may be subject to identity verification, AML checks, and applicable withdrawal limits.</li>
        <li>We reserve the right to delay, request additional verification for, or decline transactions reasonably suspected of fraud, money laundering, or violation of these Terms.</li>
        <li>Funds shown in your wallet do not constitute a deposit with a bank and are not insured by any deposit protection scheme unless explicitly stated.</li>
      </ul>

      <h2>4. Bets, Wagers & Casino Games</h2>
      <ul>
        <li>All bets and wagers are final once placed and confirmed by our systems, except where a manifest error, technical fault, or fraud is identified.</li>
        <li>We reserve the right to void, reverse, or adjust bets resulting from a pricing error, software malfunction, or other manifest error, and to recover funds incorrectly credited.</li>
        <li>Game outcomes for casino products are determined by certified random number generators (RNGs) provided by our licensed game providers. Game rules and RTP (return to player) information are displayed within each game where applicable.</li>
        <li>Sportsbook odds and markets may be suspended or settled in accordance with published market rules.</li>
      </ul>

      <h2>5. Bonuses & Promotions</h2>
      <p>
        Bonuses and promotions are subject to specific terms published at the time of the offer, including wagering
        requirements, eligible games, maximum bet limits, and expiry dates. We reserve the right to withhold or
        reclaim bonus funds and associated winnings obtained through bonus abuse, including but not limited to
        multiple accounts, collusion, or arbitrage betting designed to eliminate risk.
      </p>

      <h2>6. Responsible Gambling</h2>
      <p>
        We are committed to providing tools to help you stay in control, including deposit limits and
        self-exclusion. See our <a href="/legal/responsible-gambling">Responsible Gambling Policy</a> for full
        details and support resources.
      </p>

      <h2>7. Prohibited Conduct</h2>
      <ul>
        <li>Using cheats, exploits, bots, or unauthorized third-party software.</li>
        <li>Collusion with other players or attempting to manipulate game or betting outcomes.</li>
        <li>Using the Service for money laundering or any unlawful purpose.</li>
        <li>Accessing the Service from a jurisdiction where online gambling is prohibited.</li>
        <li>Chargebacks, payment fraud, or use of stolen payment instruments.</li>
      </ul>

      <h2>8. Intellectual Property</h2>
      <p>
        All content on the Service, including software, graphics, trademarks, and game assets, is owned by or
        licensed to SLYK Casino and protected by applicable intellectual property laws. You may not copy,
        reproduce, distribute, or create derivative works without our prior written consent.
      </p>

      <h2>9. Limitation of Liability</h2>
      <p>
        To the maximum extent permitted by law, SLYK Casino is not liable for indirect, incidental, or
        consequential damages arising from your use of the Service, including losses from internet connectivity
        issues, technical faults, or unauthorized account access not caused by our negligence. Nothing in these
        Terms limits liability that cannot be excluded under applicable law.
      </p>

      <h2>10. Suspension & Termination</h2>
      <p>
        We may suspend or close your account, with or without notice, if we reasonably believe you have breached
        these Terms, applicable law, or our policies. Where an account is closed without cause attributable to you,
        any remaining verified balance will be returned to you, subject to standard verification checks.
      </p>

      <h2>11. Complaints & Dispute Resolution</h2>
      <p>
        If you have a complaint, contact our support team at <strong>[SUPPORT EMAIL]</strong> in the first
        instance. We aim to acknowledge complaints within <strong>[X business days]</strong> and resolve them
        within <strong>[X business days]</strong>. Unresolved disputes may be referred to{' '}
        <strong>[ALTERNATIVE DISPUTE RESOLUTION BODY / REGULATOR — INSERT ONCE LICENSED]</strong>.
      </p>

      <h2>12. Governing Law</h2>
      <p>
        These Terms are governed by the laws of <strong>[GOVERNING JURISDICTION — INSERT ONCE LICENSED]</strong>,
        without regard to conflict-of-law principles, except where mandatory consumer protection laws of your
        country of residence apply.
      </p>

      <h2>13. Changes to These Terms</h2>
      <p>
        We may update these Terms from time to time. Material changes will be notified via the Service or email
        at least <strong>[X days]</strong> before taking effect. Continued use of the Service after changes take
        effect constitutes acceptance of the revised Terms.
      </p>

      <h2>14. Contact</h2>
      <p>
        Questions about these Terms can be sent to <strong>[SUPPORT EMAIL]</strong> or our registered address at{' '}
        <strong>[REGISTERED ADDRESS]</strong>.
      </p>
    </LegalLayout>
  );
}
