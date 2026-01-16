import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import { useAuth } from "../contexts/AuthContext";
import { Alert, AlertDescription, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, FormField, Input, Spinner } from "@/components/ui";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  const { login, isAuthenticated, loading, error, clearError } = useAuth();
  const router = useRouter();

  const registeredParam = router.query.registered;
  const registered = Array.isArray(registeredParam) ? registeredParam[0] : registeredParam;
  const showRegisteredMessage = registered === "true" || registered === "1";

  useEffect(() => {
    if (!loading && isAuthenticated) {
      router.push("/graphs");
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

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Spinner size="lg" />
      </div>
    );
  }

  if (isAuthenticated) {
    return null;
  }

  const displayError = formError || error;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-3xl font-bold">ForgeGraph</CardTitle>
          <CardDescription className="text-lg mt-2">Sign in to your account</CardDescription>
          <p className="text-sm text-muted-foreground mt-2">
            Or{" "}
            <Link href="/register" className="font-medium text-primary hover:text-primary/80 transition-colors">
              create a new account
            </Link>
          </p>
        </CardHeader>

        <CardContent>
          {showRegisteredMessage && (
            <Alert className="mb-4 border-green-200 bg-green-50 text-green-700">
              <AlertDescription>
                Registration successful! Please sign in with your new account.
              </AlertDescription>
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
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                disabled={isSubmitting}
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
              />
            </FormField>

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Spinner size="xs" className="mr-2" />
                  Signing in...
                </>
              ) : (
                "Sign in"
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
