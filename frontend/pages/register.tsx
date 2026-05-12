import { useEffect, useReducer, type FormEvent } from "react";
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

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type RegisterFormState = {
  email: string;
  password: string;
  confirmPassword: string;
  isSubmitting: boolean;
  formError: string;
};

type RegisterFormAction =
  | { type: "field"; field: "email" | "password" | "confirmPassword"; value: string }
  | { type: "set-error"; error: string }
  | { type: "submit-start" }
  | { type: "submit-end"; error?: string };

const initialRegisterFormState: RegisterFormState = {
  email: "",
  password: "",
  confirmPassword: "",
  isSubmitting: false,
  formError: "",
};

function registerFormReducer(state: RegisterFormState, action: RegisterFormAction): RegisterFormState {
  switch (action.type) {
    case "field":
      return { ...state, [action.field]: action.value, formError: "" };
    case "set-error":
      return { ...state, formError: action.error };
    case "submit-start":
      return { ...state, formError: "", isSubmitting: true };
    case "submit-end":
      return { ...state, isSubmitting: false, formError: action.error ?? "" };
    default:
      return state;
  }
}

function validateRegisterForm(email: string, password: string, confirmPassword: string): string | null {
  if (!email.trim()) {
    return "Email is required";
  }
  if (!EMAIL_PATTERN.test(email)) {
    return "Please enter a valid email address";
  }
  if (!password) {
    return "Password is required";
  }
  if (password.length < 8) {
    return "Password must be at least 8 characters";
  }
  if (!/[A-Z]/.test(password)) {
    return "Password must contain at least one uppercase letter";
  }
  if (!/[a-z]/.test(password)) {
    return "Password must contain at least one lowercase letter";
  }
  if (!/[0-9]/.test(password)) {
    return "Password must contain at least one number";
  }
  if (password !== confirmPassword) {
    return "Passwords do not match";
  }
  return null;
}

export default function RegisterPage() {
  const [{ email, password, confirmPassword, isSubmitting, formError }, dispatchForm] = useReducer(
    registerFormReducer,
    initialRegisterFormState,
  );

  const { register, isAuthenticated, loading, error, clearError } = useAuth();
  const router = useRouter();

  const { push } = router;
  useEffect(() => {
    if (!loading && isAuthenticated) {
      push("/companies");
    }
  }, [loading, isAuthenticated, push]);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    const validationError = validateRegisterForm(email, password, confirmPassword);
    if (validationError) {
      dispatchForm({ type: "set-error", error: validationError });
      return;
    }

    dispatchForm({ type: "submit-start" });
    let submitError: string | undefined;
    try {
      const result = await register(email, password);
      submitError = result.success ? undefined : result.error;
    } finally {
      dispatchForm({ type: "submit-end", error: submitError });
    }
  };

  const handleFieldChange = (field: "email" | "password" | "confirmPassword", value: string) => {
    clearError();
    dispatchForm({ type: "field", field, value });
  };

  if (loading) {
    return (
      <AuthLayout>
        <Spinner size="lg" label="Preparing account setup" />
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
            <CardTitle className="text-2xl font-bold">Create account</CardTitle>
            <CardDescription className="text-base mt-1">
              Start building and operating AI-driven companies
            </CardDescription>
          </CardHeader>

          <CardContent className="pt-4">
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
                  autoComplete="username"
                  aria-invalid={Boolean(displayError)}
                  required
                  value={email}
                  onChange={(e) => handleFieldChange("email", e.target.value)}
                  placeholder="you@example.com"
                  disabled={isSubmitting}
                  className="h-11"
                />
              </FormField>

              <FormField
                label="Password"
                required
                description="At least 8 characters with uppercase, lowercase, and number"
                htmlFor="password"
              >
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  aria-invalid={Boolean(displayError)}
                  required
                  value={password}
                  onChange={(e) => handleFieldChange("password", e.target.value)}
                  placeholder="Create a password"
                  disabled={isSubmitting}
                  className="h-11"
                />
              </FormField>

              <FormField label="Confirm password" required htmlFor="confirmPassword">
                <Input
                  id="confirmPassword"
                  name="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  aria-invalid={Boolean(displayError)}
                  required
                  value={confirmPassword}
                  onChange={(e) => handleFieldChange("confirmPassword", e.target.value)}
                  placeholder="Confirm your password"
                  disabled={isSubmitting}
                  className="h-11"
                />
              </FormField>

              <Button type="submit" className="w-full h-11 text-base font-medium" disabled={isSubmitting}>
                {isSubmitting ? (
                  <>
                    <Spinner size="xs" className="mr-2" />
                    Creating account…
                  </>
                ) : (
                  "Create account"
                )}
              </Button>
            </form>

            <div className="mt-6 text-center">
              <p className="text-sm text-muted-foreground">
                Already have an account?{" "}
                <Link href="/login" className="font-medium text-primary hover:text-primary/80 transition-colors">
                  Sign in
                </Link>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </AuthLayout>
  );
}
