import type { Metadata } from 'next';
import Link from 'next/link';
import { LegalLayout } from '@/components/legal-layout';

export const metadata: Metadata = {
  title: 'Responsible Gambling — SLYK Casino',
  description: 'Tools, resources, and support for safer, controlled play.',
};

export default function ResponsibleGamblingPage() {
  return (
    <LegalLayout title="Responsible Gambling" effectiveDate="[INSERT EFFECTIVE DATE]">
      <p>
        Gambling should always be entertaining and never a way to make money or escape financial or personal
        problems. SLYK Casino is committed to promoting safer gambling and providing tools and resources to help
        you stay in control.
      </p>

      <h2>1. Age Restriction</h2>
      <p>
        It is strictly prohibited for anyone under 18 (or the legal gambling age in their jurisdiction, if higher)
        to register or play. We use identity verification to confirm age — see our{' '}
        <a href="/legal/aml-kyc-policy">AML &amp; KYC Policy</a>.
      </p>

      <h2>2. Tools Available to You</h2>
      <p>
        You can manage the following directly from{' '}
        <Link href="/account/settings">Account → Settings</Link>:
      </p>
      <ul>
        <li><strong>Deposit limits</strong> — set a daily limit on how much you can deposit. Reducing a limit takes effect immediately; increasing a limit takes effect after a cooling-off period to prevent impulsive changes.</li>
        <li><strong>Self-exclusion</strong> — temporarily or permanently exclude yourself from the platform for 7, 30, 90, 180, or 365 days, or indefinitely. During self-exclusion you will be unable to log in, deposit, or place bets, and we will not send you marketing communications.</li>
        <li><strong>Reality checks</strong> — periodic reminders of session duration and net win/loss <strong>[IF IMPLEMENTED]</strong>.</li>
        <li><strong>Account closure</strong> — close your account at any time via Account Settings.</li>
      </ul>
      <p>
        Self-exclusion requests are honored promptly and cannot be reversed early by the player; if you wish to
        discuss reinstatement after a self-exclusion period ends, contact <strong>[SUPPORT EMAIL]</strong>.
      </p>

      <h2>3. Recognizing the Signs of Problem Gambling</h2>
      <ul>
        <li>Spending more time or money gambling than you intended.</li>
        <li>Chasing losses or gambling to escape stress, anxiety, or other problems.</li>
        <li>Borrowing money or neglecting responsibilities to gamble.</li>
        <li>Feeling irritable or anxious when trying to cut down.</li>
        <li>Hiding gambling activity from family or friends.</li>
      </ul>

      <h2>4. Independent Support Organizations</h2>
      <p>If you or someone you know is struggling with gambling, free and confidential support is available:</p>
      <ul>
        <li><strong>BeGambleAware</strong> — <a href="https://www.begambleaware.org" target="_blank" rel="noopener noreferrer">begambleaware.org</a></li>
        <li><strong>GamCare</strong> — <a href="https://www.gamcare.org.uk" target="_blank" rel="noopener noreferrer">gamcare.org.uk</a> | Helpline: 0808 8020 133 (UK)</li>
        <li><strong>Gambling Therapy</strong> — <a href="https://www.gamblingtherapy.org" target="_blank" rel="noopener noreferrer">gamblingtherapy.org</a></li>
        <li><strong>National Council on Problem Gambling (US)</strong> — <a href="https://www.ncpgambling.org" target="_blank" rel="noopener noreferrer">ncpgambling.org</a> | Helpline: 1-800-522-4700</li>
        <li><strong>Gamblers Anonymous</strong> — <a href="https://www.gamblersanonymous.org" target="_blank" rel="noopener noreferrer">gamblersanonymous.org</a></li>
      </ul>
      <p>You may also use national self-exclusion schemes such as GAMSTOP (UK) where applicable to your jurisdiction.</p>

      <h2>5. Our Commitment</h2>
      <ul>
        <li>We will never target marketing at self-excluded or identified at-risk players.</li>
        <li>We monitor for patterns associated with harmful play and may proactively reach out to offer support or apply protective limits.</li>
        <li>We train support staff to respond sensitively to responsible gambling concerns.</li>
      </ul>

      <h2>6. Contact Us</h2>
      <p>
        To discuss responsible gambling tools or concerns, contact <strong>[SUPPORT EMAIL]</strong> or use{' '}
        <Link href="/livechat">Live Chat</Link>.
      </p>
    </LegalLayout>
  );
}
