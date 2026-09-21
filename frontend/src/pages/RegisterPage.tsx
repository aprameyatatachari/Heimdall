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

// Mirrors the backend's own constraint (12–128 characters) so a user gets
// immediate feedback. The server remains the authority; its validation errors
// are attached to the field whatever this says.
const schema = z
  .object({
    email: z.string().min(1, "Enter your email address.").email("Enter a valid email address."),
    password: z
      .string()
      .min(12, "Use at least 12 characters.")
      .max(128, "Use at most 128 characters."),
    confirmPassword: z.string().min(1, "Re-enter your password."),
  })
  .refine((values) => values.password === values.confirmPassword, {
    path: ["confirmPassword"],
    message: "Passwords do not match.",
  });

type FormValues = z.infer<typeof schema>;

export function RegisterPage() {
  useDocumentTitle("Create your account");
  const { register: createAccount, status } = useAuth();
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
    defaultValues: { email: "", password: "", confirmPassword: "" },
  });

  if (status === "authenticated") {
    return <Navigate to={searchParams.get("next") ?? "/app"} replace />;
  }

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await createAccount(values.email, values.password);
      const next = searchParams.get("next");
      navigate(next && next.startsWith("/app") ? next : "/app", { replace: true });
    } catch (error) {
      if (error instanceof ApiError) {
        const fields = error.fieldErrors();
        let attached = false;
        for (const [name, message] of Object.entries(fields)) {
          if (name === "email" || name === "password") {
            setError(name, { message });
            attached = true;
          }
        }
        if (!attached) setFormError(error.message);
        return;
      }
      setFormError("Could not reach Heimdall. Check your connection and try again.");
    }
  });

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Start with a clearer view of what you hold."
      footer={
        <>
          Already have an account?{" "}
          <Link
            to={`/login${location.search}`}
            className="text-gold hover:text-gold-bright underline underline-offset-4"
          >
            Sign in
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
          autoComplete="new-password"
          required
          hint="At least 12 characters."
          error={errors.password?.message}
          {...register("password")}
        />

        <Field
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          required
          error={errors.confirmPassword?.message}
          {...register("confirmPassword")}
        />

        <Button type="submit" size="lg" fullWidth loading={isSubmitting}>
          {isSubmitting ? "Creating account" : "Create account"}
        </Button>
      </form>
    </AuthLayout>
  );
}
