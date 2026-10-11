'use client';

import Script from 'next/script';

// Tawk.to live chat (property 6acbb25aa18ba934c7c9cf5b, widget 1k4lr1cug).
const TAWK_SRC = 'https://embed.tawk.to/6acbb25aa18ba934c7c9cf5b/1k4lr1cug';

type TawkApi = { maximize?: () => void; toggle?: () => void };
declare global {
  interface Window { Tawk_API?: TawkApi; Tawk_LoadStart?: Date }
}

/** Loads the Tawk.to chat bubble once the page is idle. */
export function TawkChat() {
  return (
    <Script id="tawk-to" strategy="lazyOnload">
      {`var Tawk_API=Tawk_API||{}, Tawk_LoadStart=new Date();
(function(){var s1=document.createElement("script"),s0=document.getElementsByTagName("script")[0];
s1.async=true;s1.src='${TAWK_SRC}';s1.charset='UTF-8';s1.setAttribute('crossorigin','*');
s0.parentNode.insertBefore(s1,s0);})();`}
    </Script>
  );
}

/** Open the support chat: the Tawk.to window if it has loaded, else the Live support page. */
export function openSupportChat() {
  const tawk = typeof window !== 'undefined' ? window.Tawk_API : undefined;
  if (tawk?.maximize) tawk.maximize();
  else window.location.href = '/livechat';
}
