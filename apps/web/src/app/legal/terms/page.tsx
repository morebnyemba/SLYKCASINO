import type { Metadata } from 'next';
import { LegalLayout } from '@/components/legal-layout';
import { fetchLegalDetails } from '@/lib/legal';

export const metadata: Metadata = {
  title: 'Terms & Conditions',
  alternates: { canonical: '/legal/terms' },
  description: 'Terms and conditions governing use of the BetBlits platform.',
};

export default async function TermsPage() {
  const l = await fetchLegalDetails();
  return (
    <LegalLayout title="Terms & Conditions">
      <p>
        These Terms &amp; Conditions (&quot;Terms&quot;) form a binding agreement between you (&quot;Player&quot;,
        &quot;you&quot;) and <strong>{l.operator}</strong>
        {l.address && <>, registered at <strong>{l.address}</strong></>} (&quot;{l.siteName}&quot;, &quot;we&quot;,
        &quot;us&quot;), governing your access to and use of the {l.siteName} website, sportsbook and casino games
        (the &quot;Service&quot;). By creating an account or using the Service you agree to these Terms, our{' '}
        <a href="/legal/disclaimer">Disclaimer</a>, <a href="/legal/privacy">Privacy Policy</a>,{' '}
        <a href="/legal/cookies">Cookie Policy</a>, <a href="/legal/responsible-gambling">Responsible Gambling
        Policy</a> and <a href="/legal/aml-kyc-policy">AML &amp; KYC Policy</a>. If you do not agree, you must not
        use the Service.
      </p>
      <p>
        <strong>
          Please read sections 6 and 9 to 13 carefully. They explain that gambling is at your own risk and limit our
          liability to you.
        </strong>
      </p>

      <h2>1. Licensing &amp; Eligibility</h2>
      {l.licence ? (
        <p>{l.siteName} operates under the following licence: <strong>{l.licence}</strong>.</p>
      ) : (
        <p>
          {l.siteName} has not published a gambling licence on this page. Until a licence is shown here, treat the
          Service as operating in a pre-launch or test capacity. It is not offered to residents of any
          jurisdiction where online gambling is prohibited or must be licensed locally.
        </p>
      )}
      <ul>
        <li>You must be at least <strong>18 years old</strong> (or the legal gambling age where you live, if higher) to register or play.</li>
        <li>You are responsible for making sure that online gambling is legal for you where you live and where you are when you play. We do not advise you on this and accept no liability if it is not.</li>
        <li>You may register only one account. Duplicate accounts may be suspended and any associated funds forfeited pending investigation.</li>
        <li>You confirm that funds you deposit are your own and obtained legitimately.</li>
        <li>We may verify your age and identity at any time (see our <a href="/legal/aml-kyc-policy">AML &amp; KYC Policy</a>) and restrict or close accounts that fail verification.</li>
      </ul>

      <h2>2. Account Registration &amp; Security</h2>
      <ul>
        <li>You are responsible for keeping your login details secret and for all activity under your account, including bets placed by anyone using your login.</li>
        <li>Tell us immediately at {l.email ? <strong>{l.email}</strong> : l.contact} if you suspect anyone else is using your account.</li>
        <li>We may suspend or close accounts that give false registration details, break these Terms, or are used for fraud, collusion, bonus abuse or money laundering.</li>
      </ul>

      <h2>3. Deposits, Withdrawals &amp; Wallet</h2>
      <ul>
        <li>All transactions are processed in the currency shown on the platform. Any fees are shown before you confirm a transaction.</li>
        <li>Withdrawals are paid to verified accounts only and may be subject to identity verification, AML checks and withdrawal limits.</li>
        <li>We may delay, ask for more verification for, or decline transactions we reasonably suspect involve fraud, money laundering or a breach of these Terms.</li>
        <li>Your wallet balance is not a bank deposit, earns no interest, and is not protected by any deposit insurance or compensation scheme unless we expressly say so.</li>
        <li>We are not responsible for delays, fees, reversals or failures caused by mobile money operators, banks, card schemes or other payment providers.</li>
      </ul>

      <h2>4. Bets, Wagers &amp; Casino Games</h2>
      <ul>
        <li>A bet is accepted only when our systems confirm it. All accepted bets are final, except where a manifest error, technical fault or fraud is identified.</li>
        <li>We may void, reverse or adjust bets affected by an obvious error in odds, lines, markets, start times or results (whether caused by us, a data provider or a system fault), a software malfunction, or late betting after the outcome was known, and recover any amounts credited in error.</li>
        <li>Sports bets are settled on the official result as reported by our data providers. Scores, statistics, live times and match trackers shown on the Service are for information only and may be delayed or wrong.</li>
        <li>Third-party casino game outcomes are decided by the providers&apos; random number generators. In-house crash games are provably fair: each round&apos;s result is committed before betting opens and can be checked afterwards. Game rules and RTP information are shown in each game where applicable.</li>
        <li>If a game or connection fails during play, the result recorded on our servers decides the outcome. Malfunction voids all affected pays and plays.</li>
        <li>Markets may be suspended, limited or settled in line with the published market rules. We may refuse or limit any bet, or limit maximum stakes and payouts, without giving a reason.</li>
      </ul>

      <h2>5. Bonuses &amp; Promotions</h2>
      <p>
        Bonuses and promotions are subject to the specific terms published with each offer, including wagering
        requirements, eligible games, maximum bet limits and expiry dates. We may withhold or reclaim bonus funds,
        and winnings from them, obtained through bonus abuse, including multiple accounts, collusion, or betting
        designed to remove risk. We may change or withdraw any promotion at any time.
      </p>

      <h2>6. Gambling Is at Your Own Risk</h2>
      <ul>
        <li>Gambling involves the real risk of losing money. Only bet what you can afford to lose. Do not gamble to make money, to pay debts or to recover losses.</li>
        <li>You use the Service, and place every bet, entirely at your own risk and by your own choice. We do not give betting, financial or investment advice, and odds, tips, statistics, &quot;popular&quot; picks or any other content on the Service are not a recommendation to bet.</li>
        <li>To the fullest extent the law allows, we are not liable for any money you lose by gambling, or for any financial, emotional, health, family or other personal harm that results from your gambling.</li>
        <li>We offer tools to help you stay in control, including deposit limits and self-exclusion. See our <a href="/legal/responsible-gambling">Responsible Gambling Policy</a>. Using these tools is your responsibility; if you think you may have a gambling problem, stop playing and seek help.</li>
      </ul>

      <h2>7. Prohibited Conduct</h2>
      <ul>
        <li>Using cheats, exploits, bots, or unauthorized third-party software.</li>
        <li>Collusion with other players or attempting to manipulate game or betting outcomes.</li>
        <li>Using the Service for money laundering or any unlawful purpose.</li>
        <li>Accessing the Service from a jurisdiction where online gambling is prohibited, including by using a VPN or proxy to hide your location.</li>
        <li>Chargebacks, payment fraud, or use of stolen payment instruments.</li>
      </ul>

      <h2>8. Intellectual Property</h2>
      <p>
        All content on the Service, including software, graphics, trademarks and game assets, is owned by or
        licensed to us and protected by intellectual property laws. You may not copy, reproduce, distribute or
        create derivative works without our prior written consent.
      </p>

      <h2>9. The Service Is Provided &quot;As Is&quot;</h2>
      <p>
        The Service is provided &quot;as is&quot; and &quot;as available&quot;. To the fullest extent the law
        allows, we make no promise or warranty, express or implied, that the Service will be uninterrupted, timely,
        secure, error-free or free of viruses, that it will meet your requirements, or that any information on it
        (including odds, scores, results and statistics) is accurate, complete or up to date. We may change,
        suspend or withdraw any part of the Service, any game or any market at any time.
      </p>

      <h2>10. Third-Party Services &amp; Information</h2>
      <p>
        The Service relies on third parties, including sports data and odds feeds, game providers, payment
        providers, hosting and network providers, and links to other websites. We do not control them and are not
        responsible for their content, accuracy, availability, acts or omissions. Links to other websites are
        provided for convenience only and are not an endorsement.
      </p>

      <h2>11. Limitation of Liability</h2>
      <ul>
        <li>To the fullest extent the law allows, we, our group companies, directors, employees, agents and partners are not liable, whether in contract, negligence or otherwise, for any indirect, incidental, special or consequential loss, or for any loss of profit, revenue, winnings, opportunity, data or goodwill, arising from or connected with the Service.</li>
        <li>We are not liable for losses caused by: internet, network, device or power failures; the delay, failure or loss of any bet, transaction or message in transit; unauthorized use of your account that was not caused by our negligence; errors in information from third parties; or your breach of these Terms.</li>
        <li>Where we are liable to you in any case, our total liability is limited to the stakes on the bet or bets the claim concerns or, where the claim does not concern a particular bet, the total you deposited in the 12 months before the claim arose.</li>
        <li>Nothing in these Terms limits your right to withdraw a verified balance or winnings properly due to you, or excludes liability for fraud, for death or personal injury caused by our negligence, or for anything else that cannot be excluded or limited under the law that applies to you.</li>
      </ul>

      <h2>12. Indemnity</h2>
      <p>
        You agree to compensate us, our group companies, directors, employees and agents for any claims, losses,
        costs and expenses (including reasonable legal fees) arising from your breach of these Terms, your breach
        of any law, or anyone else&apos;s use of your account where you failed to keep your login details safe.
      </p>

      <h2>13. Events Outside Our Control</h2>
      <p>
        We are not liable for any failure or delay caused by events beyond our reasonable control, including
        natural disasters, epidemics, war, terrorism, civil unrest, strikes, government or regulatory action,
        sanctions, failures of power, internet, telecommunications, payment or data providers, cyber-attacks and
        the cancellation, postponement or abandonment of sporting events.
      </p>

      <h2>14. Suspension &amp; Termination</h2>
      <p>
        We may suspend or close your account, with or without notice, if we reasonably believe you have broken
        these Terms, the law or our policies. Where an account is closed without cause attributable to you, any
        remaining verified balance will be returned to you, subject to standard verification checks.
      </p>

      <h2>15. Complaints &amp; Dispute Resolution</h2>
      <p>
        If you have a complaint, contact {l.email ? <strong>{l.email}</strong> : l.contact} first. We aim to
        acknowledge complaints within <strong>2 business days</strong> and resolve them within{' '}
        <strong>14 days</strong>.
        {l.disputeBody ? (
          <> Disputes we cannot resolve may be referred to <strong>{l.disputeBody}</strong>.</>
        ) : (
          <> Disputes we cannot resolve may be referred to the courts named in section 16.</>
        )}
      </p>

      <h2>16. Governing Law</h2>
      <p>
        These Terms are governed by the laws of <strong>{l.law}</strong>, without regard to conflict-of-law
        principles, except where mandatory consumer protection laws of your country of residence apply.
      </p>

      <h2>17. General</h2>
      <ul>
        <li>If any part of these Terms is found invalid or unenforceable, it is limited to the minimum extent needed and the rest of the Terms stay in force.</li>
        <li>If we do not enforce a right straight away, we have not given it up.</li>
        <li>These Terms and the policies they refer to are the whole agreement between you and us about the Service.</li>
        <li>We may transfer our rights and obligations under these Terms to another company. You may not transfer yours.</li>
        <li>If these Terms are translated, the English version prevails.</li>
      </ul>

      <h2>18. Changes to These Terms</h2>
      <p>
        We may update these Terms from time to time. Material changes will be notified through the Service or by
        email at least <strong>14 days</strong> before they take effect, unless a change is required sooner by law
        or to prevent fraud. Using the Service after changes take effect means you accept the revised Terms.
      </p>

      <h2>19. Contact</h2>
      <p>
        Questions about these Terms can be sent to {l.email ? <strong>{l.email}</strong> : l.contact}
        {l.address && <> or to our registered address at <strong>{l.address}</strong></>}.
      </p>
    </LegalLayout>
  );
}
