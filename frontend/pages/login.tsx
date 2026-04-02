import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import { useAuth } from "../contexts/AuthContext";
import AuthLayout from "../components/AuthLayout";
import {
  Alert,
  AlertDescription,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  FormField,
  Input,
  Spinner,
} from "@/components/ui";
import { authApi, getApiErrorMessage } from "../lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSsoLoading, setIsSsoLoading] = useState(false);
  const [formError, setFormError] = useState("");

  const { login, isAuthenticated, loading, error, clearError } = useAuth();
  const router = useRouter();

  const registeredParam = router.query.registered;
  const registered = Array.isArray(registeredParam) ? registeredParam[0] : registeredParam;
  const showRegisteredMessage = registered === "true" || registered === "1";

  useEffect(() => {
    if (!loading && isAuthenticated) {
      router.push("/overview");
    }
  }, [loading, isAuthenticated, router]);

  useEffect(() => {
    setFormError("");
    clearError();
  }, [email, password, clearError]);

  const validateForm = () => {
    if (!email.trim()) {
      setFormError("Email is required");
      return false;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setFormError("Please enter a valid email address");
      return false;
    }
    if (!password) {
      setFormError("Password is required");
      return false;
    }
    if (password.length < 6) {
      setFormError("Password must be at least 6 characters");
      return false;
    }
    return true;
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setFormError("");

    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await login(email, password);
      if (!result.success) {
        setFormError(result.error);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSsoLogin = async () => {
    setFormError("");
    if (!email.trim()) {
      setFormError("Enter your work email to continue with SSO.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setFormError("Please enter a valid email address.");
      return;
    }

    setIsSsoLoading(true);
    try {
      const authorizeUrl = await authApi.getSsoAuthorizeUrl(email);
      window.location.href = authorizeUrl;
    } catch (err: unknown) {
      setFormError(getApiErrorMessage(err, "SSO login failed. Please try again."));
    } finally {
      setIsSsoLoading(false);
    }
  };

  if (loading) {
    return (
      <AuthLayout>
        <Spinner size="lg" />
      </AuthLayout>
    );
  }

  if (isAuthenticated) {
    return null;
  }

  const displayError = formError || error;

  return (
    <AuthLayout>
      <div className="w-full max-w-md">
        <Card className="border-border/50 bg-card/80 backdrop-blur-sm shadow-2xl">
          <CardHeader className="text-center pb-2">
            <CardTitle className="text-2xl font-bold">Welcome back</CardTitle>
            <CardDescription className="text-base mt-1">Sign in to your account to continue</CardDescription>
          </CardHeader>

          <CardContent className="pt-4">
            {showRegisteredMessage && (
              <Alert className="mb-4 border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <AlertDescription>Registration successful! Please sign in with your new account.</AlertDescription>
              </Alert>
            )}

            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              {displayError && (
                <Alert variant="destructive">
                  <AlertDescription>{displayError}</AlertDescription>
                </Alert>
              )}

              <FormField label="Email address" required htmlFor="email">
                <Input
                  id="email"
                  name="username"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  disabled={isSubmitting}
                  className="h-11"
                />
              </FormField>

              <FormField label="Password" required htmlFor="password">
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  disabled={isSubmitting}
                  className="h-11"
                />
              </FormField>

              <Button type="submit" className="w-full h-11 text-base font-medium" disabled={isSubmitting}>
                {isSubmitting ? (
                  <>
                    <Spinner size="xs" className="mr-2" />
                    Signing in...
                  </>
                ) : (
                  "Sign in"
                )}
              </Button>

              <div className="flex items-center gap-3 py-2">
                <div className="h-px flex-1 bg-border/60" />
                <span className="text-xs uppercase tracking-wide text-muted-foreground">Or continue with SSO</span>
                <div className="h-px flex-1 bg-border/60" />
              </div>

              <Button
                type="button"
                variant="outline"
                className="w-full h-11 text-base font-medium"
                onClick={handleSsoLogin}
                disabled={isSsoLoading || isSubmitting}
              >
                {isSsoLoading ? (
                  <>
                    <Spinner size="xs" className="mr-2" />
                    Redirecting...
                  </>
                ) : (
                  "Continue with Auth0 SSO"
                )}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <p className="text-sm text-muted-foreground">
                Don&apos;t have an account?{" "}
                <Link href="/register" className="font-medium text-primary hover:text-primary/80 transition-colors">
                  Create one
                </Link>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </AuthLayout>
  );
}
