import { Html, Head, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en" suppressHydrationWarning>
      <Head>
        {/* Favicon */}
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
        <link rel="apple-touch-icon" href="/favicon.svg" />

        {/* Primary Meta Tags */}
        <meta name="title" content="ForgeGraph - Build AI Agents Visually" />
        <meta
          name="description"
          content="Create powerful AI agents without the complexity. Visual workflow builder that lets you design, test, and deploy AI automation in minutes."
        />
        <meta name="keywords" content="AI agents, workflow automation, AI builder, no-code AI, visual programming, LLM automation, AI workflows" />
        <meta name="author" content="ForgeGraph" />

        {/* Open Graph / Facebook */}
        <meta property="og:type" content="website" />
        <meta property="og:url" content="https://forgegraph.dev/" />
        <meta property="og:title" content="ForgeGraph - Build AI Agents Visually" />
        <meta
          property="og:description"
          content="Create powerful AI agents without the complexity. Visual workflow builder that lets you design, test, and deploy AI automation in minutes."
        />
        <meta property="og:image" content="https://forgegraph.dev/og-image.png" />
        <meta property="og:site_name" content="ForgeGraph" />

        {/* Twitter */}
        <meta property="twitter:card" content="summary_large_image" />
        <meta property="twitter:url" content="https://forgegraph.dev/" />
        <meta property="twitter:title" content="ForgeGraph - Build AI Agents Visually" />
        <meta
          property="twitter:description"
          content="Create powerful AI agents without the complexity. Visual workflow builder that lets you design, test, and deploy AI automation in minutes."
        />
        <meta property="twitter:image" content="https://forgegraph.dev/og-image.png" />

        {/* Theme */}
        <meta name="theme-color" content="#6366f1" />

        {/* Fonts */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </Head>
      <body className="antialiased">
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
