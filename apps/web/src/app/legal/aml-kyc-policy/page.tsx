import type { Metadata } from 'next';
import { LegalLayout } from '@/components/legal-layout';

export const metadata: Metadata = {
  title: 'AML & KYC Policy — SLYK Casino',
  description: 'Our anti-money laundering and identity verification practices.',
};

export default function AmlKycPolicyPage() {
  return (
    <LegalLayout title="Anti-Money Laundering & Know-Your-Customer Policy" effectiveDate="[INSERT EFFECTIVE DATE]">
      <p>
        SLYK Casino is committed to preventing the use of its platform for money laundering, terrorist financing,
        or other financial crime, and to verifying that players are of legal age and using their own legitimate
        funds. This policy outlines our approach to Anti-Money Laundering (AML) and Know-Your-Customer (KYC)
        compliance.
      </p>

      <h2>1. Customer Due Diligence</h2>
      <p>We verify the identity of our players using a risk-based approach. Verification may be required:</p>
      <ul>
        <li>Before your first withdrawal.</li>
        <li>When cumulative deposits or withdrawals exceed defined thresholds.</li>
        <li>When account activity appears unusual or inconsistent with your profile.</li>
        <li>At any time, at our discretion, to comply with legal or regulatory obligations.</li>
      </ul>
      <p>Verification is carried out via our identity verification provider and may require:</p>
      <ul>
        <li>A valid government-issued photo ID (passport, national ID, or driver&apos;s licence).</li>
        <li>Proof of address (e.g., utility bill or bank statement, generally no older than 3 months).</li>
        <li>A live selfie or liveness check to confirm the ID belongs to you.</li>
        <li>Proof of payment method ownership (e.g., card or bank account in your name) and, where relevant, source of funds documentation.</li>
      </ul>
      <p>
        Your account verification status is visible in <strong>Account → Profile</strong>. Unverified accounts may
        face deposit, withdrawal, or wagering limits until verification is complete.
      </p>

      <h2>2. Ongoing Monitoring</h2>
      <p>
        We monitor account activity, transaction patterns, and gameplay on an ongoing basis to detect behavior
        consistent with money laundering, structuring, fraud, or bonus abuse, including unusually large or rapid
        transactions, deposit-and-withdraw patterns with minimal play, and use of multiple payment instruments or
        accounts.
      </p>

      <h2>3. Source-of-Funds Checks</h2>
      <p>
        Where deposit or withdrawal activity exceeds risk thresholds, we may request evidence of the source of
        funds (e.g., payslips, bank statements, or other documentation) before processing further transactions.
      </p>

      <h2>4. Reporting Obligations</h2>
      <p>
        Where required by law, we will report suspicious activity to the relevant Financial Intelligence Unit or
        regulator (<strong>[INSERT RELEVANT FIU/REGULATOR ONCE LICENSED]</strong>) and may be legally prohibited
        from disclosing that a report has been made (&quot;tipping off&quot;).
      </p>

      <h2>5. Account Restrictions</h2>
      <p>
        We may suspend transactions, restrict an account, or delay withdrawals pending verification or
        investigation. We may also decline to process a transaction, terminate an account, or retain funds where
        required by law or where we reasonably suspect financial crime, without prior notice in cases where
        notice could prejudice an investigation.
      </p>

      <h2>6. Data Retention for Compliance</h2>
      <p>
        Identity verification and transaction records are retained for the period required by applicable AML and
        gambling regulations (typically <strong>[X years, e.g., 5 years]</strong> after the account is closed or
        the transaction occurs), as described in our <a href="/legal/privacy-policy">Privacy Policy</a>.
      </p>

      <h2>7. Your Responsibilities</h2>
      <ul>
        <li>Provide accurate, up-to-date identification and account information.</li>
        <li>Use only payment methods and accounts registered in your own name.</li>
        <li>Respond promptly to verification requests — delayed responses may delay withdrawals.</li>
      </ul>

      <h2>8. Contact Us</h2>
      <p>
        Questions about identity verification can be sent to <strong>[SUPPORT EMAIL]</strong>.
      </p>
    </LegalLayout>
  );
}
