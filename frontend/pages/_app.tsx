import type { AppProps } from "next/app";
import { IBM_Plex_Sans, Source_Serif_4 } from "next/font/google";
import { ThemeProvider } from "next-themes";

import "@xyflow/react/dist/style.css";
import "../styles/globals.css";
import { AuthProvider } from "../contexts/AuthContext";
import { Toaster } from "@/components/ui/sonner";

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

export default function App({ Component, pageProps }: AppProps) {
  return (
    <div className={`${sans.variable} ${serif.variable}`}>
      <ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange>
        <AuthProvider>
          <Component {...pageProps} />
          <Toaster richColors position="top-right" />
        </AuthProvider>
      </ThemeProvider>
    </div>
  );
}
