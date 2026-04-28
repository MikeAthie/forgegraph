import type { AppProps } from "next/app";
import { IBM_Plex_Sans, Source_Serif_4 } from "next/font/google";
import { useRouter } from "next/router";
import { ThemeProvider } from "next-themes";

import "@xyflow/react/dist/style.css";
import "../styles/globals.css";
import { AuthProvider, useAuth } from "../contexts/AuthContext";
import { SeoHead } from "@/components/SeoHead";
import { Toaster } from "@/components/ui/sonner";
import { getRouteSeo } from "@/lib/seo";

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const serif = Source_Serif_4({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-serif",
  display: "swap",
});

function OrganizationScopedPage({ Component, pageProps }: Pick<AppProps, "Component" | "pageProps">) {
  const { user, isAuthenticated } = useAuth();
  const organizationScopeKey = isAuthenticated
    ? `${user?.id ?? "user"}:${user?.default_organization_id ?? "personal"}`
    : "anonymous";

  return <Component key={organizationScopeKey} {...pageProps} />;
}

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter();
  const seo = getRouteSeo(router.pathname, router.asPath);

  return (
    <>
      <SeoHead {...seo} />
      <div className={`${sans.variable} ${serif.variable}`}>
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange>
          <AuthProvider>
            <OrganizationScopedPage Component={Component} pageProps={pageProps} />
            <Toaster richColors position="top-right" />
          </AuthProvider>
        </ThemeProvider>
      </div>
    </>
  );
}
