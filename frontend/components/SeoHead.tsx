import Head from "next/head";

import {
  SOCIAL_IMAGE_ALT,
  SITE_DESCRIPTION,
  SITE_KEYWORDS,
  SITE_NAME,
  SITE_TITLE,
  SITE_URL,
  SOCIAL_IMAGE_PATH,
  TWITTER_IMAGE_PATH,
  absoluteUrl,
  type SeoConfig,
} from "@/lib/seo";

function buildJsonLd(config: Required<Pick<SeoConfig, "title" | "description">> & SeoConfig) {
  const canonicalUrl = absoluteUrl(config.canonicalPath);
  const imageUrl = absoluteUrl(config.imagePath);

  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${SITE_URL}/#organization`,
        name: SITE_NAME,
        url: SITE_URL,
        logo: {
          "@type": "ImageObject",
          "@id": `${SITE_URL}/#logo`,
          url: absoluteUrl("/icon1.png"),
          contentUrl: absoluteUrl("/icon1.png"),
          width: 96,
          height: 96,
        },
        description:
          "ForgeGraph builds operating software for AI-native organizations and AI-driven company workspaces.",
        knowsAbout: [
          "AI company operations",
          "AI-driven companies",
          "AI operating models",
          "company memory",
          "human approvals",
          "AI usage controls",
          "deliverable supervision",
        ],
      },
      {
        "@type": "WebSite",
        "@id": `${SITE_URL}/#website`,
        url: SITE_URL,
        name: SITE_NAME,
        alternateName: "AI Company OS",
        description: SITE_DESCRIPTION,
        inLanguage: "en-US",
        publisher: {
          "@id": `${SITE_URL}/#organization`,
        },
      },
      {
        "@type": "SoftwareApplication",
        "@id": `${SITE_URL}/#software`,
        name: SITE_NAME,
        alternateName: "ForgeGraph AI Company OS",
        applicationCategory: "BusinessApplication",
        applicationSubCategory: "AI operations software",
        operatingSystem: "Web",
        url: SITE_URL,
        description: SITE_DESCRIPTION,
        featureList: [
          "Create AI-driven companies from business objectives",
          "Define departments, skills, tools, autonomy, and AI access mode",
          "Launch and supervise company operations",
          "Review approvals, failures, deliverables, and usage controls",
          "Encapsulate company memory and knowledge by organization",
        ],
        audience: {
          "@type": "Audience",
          audienceType: "Founders, operators, and teams building AI-native organizations",
        },
        publisher: {
          "@id": `${SITE_URL}/#organization`,
        },
      },
      {
        "@type": "WebPage",
        "@id": `${canonicalUrl}#webpage`,
        url: canonicalUrl,
        name: config.title,
        description: config.description,
        inLanguage: "en-US",
        isPartOf: {
          "@id": `${SITE_URL}/#website`,
        },
        about: {
          "@id": `${SITE_URL}/#software`,
        },
        primaryImageOfPage: {
          "@type": "ImageObject",
          url: imageUrl,
          width: 1200,
          height: 630,
          caption: config.imageAlt,
        },
      },
    ],
  };
}

export function SeoHead({
  title = SITE_TITLE,
  description = SITE_DESCRIPTION,
  canonicalPath = "/",
  imagePath = SOCIAL_IMAGE_PATH,
  twitterImagePath = TWITTER_IMAGE_PATH,
  imageAlt = SOCIAL_IMAGE_ALT,
  keywords = SITE_KEYWORDS,
  noIndex = false,
  type = "website",
}: SeoConfig) {
  const canonicalUrl = absoluteUrl(canonicalPath);
  const imageUrl = absoluteUrl(imagePath);
  const twitterImageUrl = absoluteUrl(twitterImagePath);
  const robots = noIndex
    ? "noindex, nofollow, noarchive"
    : "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1";
  const jsonLd = buildJsonLd({
    title,
    description,
    canonicalPath,
    imagePath,
    twitterImagePath,
    imageAlt,
    keywords,
    noIndex,
    type,
  });

  return (
    <Head>
      <title key="title">{title}</title>
      <meta key="description" name="description" content={description} />
      <meta key="robots" name="robots" content={robots} />
      <meta key="googlebot" name="googlebot" content={robots} />
      <meta key="keywords" name="keywords" content={keywords.join(", ")} />
      <meta key="author" name="author" content={SITE_NAME} />
      <meta key="publisher" name="publisher" content={SITE_NAME} />
      <meta key="creator" name="creator" content={SITE_NAME} />
      <meta key="application-name" name="application-name" content={SITE_NAME} />
      <meta key="viewport" name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
      <meta key="apple-mobile-web-app-title" name="apple-mobile-web-app-title" content={SITE_NAME} />
      <meta key="apple-mobile-web-app-capable" name="apple-mobile-web-app-capable" content="yes" />
      <meta key="mobile-web-app-capable" name="mobile-web-app-capable" content="yes" />
      <meta
        key="apple-mobile-web-app-status-bar-style"
        name="apple-mobile-web-app-status-bar-style"
        content="black-translucent"
      />
      <meta key="category" name="category" content="AI operations software" />
      <meta key="classification" name="classification" content="Business software, AI operations, company workspace" />
      <meta key="rating" name="rating" content="General" />
      <meta key="referrer" name="referrer" content="strict-origin-when-cross-origin" />
      <meta key="format-detection" name="format-detection" content="telephone=no, address=no, email=no" />
      <meta key="msapplication-tile-color" name="msapplication-TileColor" content="#0f172a" />
      <meta key="msapplication-tile-image" name="msapplication-TileImage" content="/mstile-150x150.png" />
      <link key="canonical" rel="canonical" href={canonicalUrl} />
      <link key="alternate-en" rel="alternate" hrefLang="en" href={canonicalUrl} />
      <link key="alternate-x-default" rel="alternate" hrefLang="x-default" href={canonicalUrl} />

      <meta key="og-type" property="og:type" content={type} />
      <meta key="og-url" property="og:url" content={canonicalUrl} />
      <meta key="og-site-name" property="og:site_name" content={SITE_NAME} />
      <meta key="og-title" property="og:title" content={title} />
      <meta key="og-description" property="og:description" content={description} />
      <meta key="og-locale" property="og:locale" content="en_US" />
      <meta key="og-image" property="og:image" content={imageUrl} />
      <meta key="og-image-secure" property="og:image:secure_url" content={imageUrl} />
      <meta key="og-image-type" property="og:image:type" content="image/png" />
      <meta key="og-image-width" property="og:image:width" content="1200" />
      <meta key="og-image-height" property="og:image:height" content="630" />
      <meta key="og-image-alt" property="og:image:alt" content={imageAlt} />

      <meta key="twitter-card" name="twitter:card" content="summary_large_image" />
      <meta key="twitter-url" name="twitter:url" content={canonicalUrl} />
      <meta key="twitter-title" name="twitter:title" content={title} />
      <meta key="twitter-description" name="twitter:description" content={description} />
      <meta key="twitter-image" name="twitter:image" content={twitterImageUrl} />
      <meta key="twitter-image-alt" name="twitter:image:alt" content={imageAlt} />

      <script key="forgegraph-jsonld" type="application/ld+json">
        {JSON.stringify(jsonLd)}
      </script>
    </Head>
  );
}
