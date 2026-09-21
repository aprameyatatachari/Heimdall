import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { ApiError } from "@/api/errors";
import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Field } from "@/components/Field";
import { useAuth } from "@/auth/useAuth";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

import { AuthLayout } from "./parts/AuthLayout";

const schema = z.object({
  email: z.string().min(1, "Enter your email address.").email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});

type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  useDocumentTitle("Sign in");
  const { signIn, status } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  if (status === "authenticated") {
    return <Navigate to={searchParams.get("next") ?? "/app"} replace />;
  }

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await signIn(values.email, values.password);
      const next = searchParams.get("next");
      navigate(next && next.startsWith("/app") ? next : "/app", { replace: true });
    } catch (error) {
      if (error instanceof ApiError) {
        // Field-level problems belong on their field; everything else is one
        // message above the form.
        const fields = error.fieldErrors();
        let attached = false;
        for (const [name, message] of Object.entries(fields)) {
          if (name === "email" || name === "password") {
            setError(name, { message });
            attached = true;
          }
        }
        if (error.isRateLimited) {
          setFormError(error.message);
        } else if (!attached) {
          // Never reveal whether an email is registered: one message covers both
          // a wrong address and a wrong password. AGENTS.md section 6.3.
          setFormError(
            error.status === 401 ? "Email or password is incorrect." : error.message,
          );
        }
        return;
      }
      setFormError("Could not reach Heimdall. Check your connection and try again.");
    }
  });

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to continue."
      footer={
        <>
          Don&rsquo;t have an account?{" "}
          <Link
            to={`/register${location.search}`}
            className="text-gold hover:text-gold-bright underline underline-offset-4"
          >
            Create one
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-5">
        {formError && <Alert tone="error">{formError}</Alert>}

        <Field
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@domain.com"
          required
          error={errors.email?.message}
          {...register("email")}
        />

        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          error={errors.password?.message}
          {...register("password")}
        />

        <Button type="submit" size="lg" fullWidth loading={isSubmitting}>
          {isSubmitting ? "Signing in" : "Sign in"}
        </Button>
      </form>
    </AuthLayout>
  );
}
