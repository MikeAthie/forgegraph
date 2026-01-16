import type { AppProps } from "next/app";

import "../styles/globals.css";
import "@xyflow/react/dist/style.css";
import { AuthProvider } from "../contexts/AuthContext";
import { Toaster } from "@/components/ui/sonner";

export default function App({ Component, pageProps }: AppProps) {
  return (
    <AuthProvider>
      <Component {...pageProps} />
      <Toaster richColors position="top-right" />
    </AuthProvider>
  );
}

