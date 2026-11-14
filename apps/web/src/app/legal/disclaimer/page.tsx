import type { Metadata } from 'next';
import { LegalLayout } from '@/components/legal-layout';
import { fetchLegalDetails } from '@/lib/legal';

export const metadata: Metadata = {
  title: 'Disclaimer',
  alternates: { canonical: '/legal/disclaimer' },
  description: 'Gambling risk, liability and information disclaimers for BetBlits.',
};

export default async function DisclaimerPage() {
  const l = await fetchLegalDetails();
  return (
    <LegalLayout title="Disclaimer">
      <p>
        This Disclaimer forms part of our <a href="/legal/terms">Terms &amp; Conditions</a> and applies to everyone
        who visits or uses {l.siteName}, which is operated by <strong>{l.operator}</strong>. If anything here
        conflicts with the Terms, the Terms prevail.
      </p>

      <h2>18+ only</h2>
      <p>
        The Service is for adults aged 18 or over (or the legal gambling age where you live, if higher). Under-age
        gambling is an offence. Winnings from any account found to belong to a minor are forfeited.
      </p>

      <h2>Gambling involves risk</h2>
      <ul>
        <li>Every bet can be lost. Gambling is entertainment, not a way to make money, and over time players as a group lose more than they win.</li>
        <li>You gamble at your own risk and are solely responsible for your decisions to deposit and bet.</li>
        <li>To the fullest extent the law allows, {l.siteName} and its operator, directors, staff, affiliates, agents and partners are not liable for any gambling losses, or for any financial, emotional, health, relationship or other harm connected with your gambling or your use of the Service.</li>
        <li>If gambling stops being fun, stop. Set limits or self-exclude from your account, and see our <a href="/legal/responsible-gambling">Responsible Gambling</a> page for help.</li>
      </ul>

      <h2>No advice</h2>
      <p>
        Nothing on the Service, including odds, tips, previews, statistics, &quot;popular&quot; or &quot;hot&quot;
        picks, chat messages, promotions or messages from agents or affiliates, is betting, financial, legal, tax or
        investment advice, or a promise of any outcome. Messages from other players and from agents or affiliates are
        their own views, not ours.
      </p>

      <h2>Information may be wrong or late</h2>
      <p>
        Odds, scores, live match times, results and statistics come from third-party providers and can be delayed,
        incomplete or wrong. Bets are settled on official results under our <a href="/legal/terms">Terms</a>, and bets
        affected by obvious errors may be voided or corrected.
      </p>

      <h2>Legality where you are</h2>
      <p>
        Online gambling laws differ between countries and change over time. It is your responsibility to make sure you
        are allowed to gamble online where you live and where you are when you play. Making the Service available is
        not an offer or invitation to gamble anywhere it is unlawful.
        {l.licence ? <> Our licence: <strong>{l.licence}</strong>.</> : <> {l.siteName} does not currently publish a gambling licence.</>}
      </p>

      <h2>Availability and security</h2>
      <p>
        The Service is provided &quot;as is&quot; and &quot;as available&quot;, without any promise that it will be
        uninterrupted, error-free or secure. We are not responsible for losses caused by connection, device, network or
        power failures, by payment providers, or by events outside our control.
      </p>

      <h2>Taxes</h2>
      <p>
        You are responsible for declaring and paying any tax due on your winnings where you live, unless the law
        requires us to deduct it.
      </p>

      <h2>Limits of this disclaimer</h2>
      <p>
        Nothing in this Disclaimer excludes or limits liability that cannot be excluded or limited by law, including
        liability for fraud, or affects rights you have under consumer protection laws that cannot be waived.
      </p>

      <h2>Contact</h2>
      <p>Questions about this Disclaimer can be sent to {l.email ? <strong>{l.email}</strong> : l.contact}.</p>
    </LegalLayout>
  );
}
