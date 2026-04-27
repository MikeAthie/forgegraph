import { Html, Head, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en" suppressHydrationWarning>
      <Head>
        {/* Favicon */}
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
        <link rel="apple-touch-icon" href="/favicon.svg" />

        {/* Primary Meta Tags */}
        <meta name="title" content="ForgeGraph - AI Company Operating System" />
        <meta
          name="description"
          content="Create and operate AI-driven companies with shared objectives, departments, operations, approvals, deliverables, and command controls."
        />
        <meta
          name="keywords"
          content="AI company operating system, AI operations, autonomous company, company workspace, AI departments, AI deliverables"
        />
        <meta name="author" content="ForgeGraph" />

        {/* Open Graph / Facebook */}
        <meta property="og:type" content="website" />
        <meta property="og:url" content="https://forgegraph.dev/" />
        <meta property="og:title" content="ForgeGraph - AI Company Operating System" />
        <meta
          property="og:description"
          content="Create and operate AI-driven companies with company workspaces, operations, approvals, and deliverables."
        />
        <meta property="og:image" content="https://forgegraph.dev/og-image.png" />
        <meta property="og:site_name" content="ForgeGraph" />

        {/* Twitter */}
        <meta property="twitter:card" content="summary_large_image" />
        <meta property="twitter:url" content="https://forgegraph.dev/" />
        <meta property="twitter:title" content="ForgeGraph - AI Company Operating System" />
        <meta
          property="twitter:description"
          content="Create and operate AI-driven companies with company workspaces, operations, approvals, and deliverables."
        />
        <meta property="twitter:image" content="https://forgegraph.dev/og-image.png" />

        {/* Theme */}
        <meta name="theme-color" content="#0f172a" />

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
