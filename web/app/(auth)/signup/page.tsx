"use client";

import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import Link from "next/link";
import { useState } from "react";
import { Loader2 } from "lucide-react";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const supabase = createClient();
    const { error } = await supabase.auth.signUp({
      email,
      password,
    });

    if (error) {
      setError(error.message);
      setLoading(false);
      return;
    }

    setSuccess(true);
    setLoading(false);
  }

  if (success) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card className="w-full max-w-sm">
          <CardContent className="pt-6 text-center" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: 14,
                background: "var(--status-ready-bg)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--status-ready-fg)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <p style={{ fontSize: 16, fontWeight: 600, fontFamily: "var(--trove-sans, sans-serif)", color: "var(--fg-strong)" }}>
              Check your email
            </p>
            <p style={{ fontSize: 13, color: "var(--fg-muted)", fontFamily: "var(--trove-sans, sans-serif)", lineHeight: 1.5 }}>
              We sent a confirmation link to <strong>{email}</strong>.
            </p>
            <Link href="/login">
              <Button variant="outline">Back to sign in</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          {/* Trove logo mark */}
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 12 }}>
            <svg viewBox="0 0 64 64" width="40" height="40" aria-hidden="true">
              <rect x="4" y="4" width="56" height="56" rx="16" fill="#1B4D52" />
              <g stroke="#5FB6BB" strokeWidth="1.4" strokeLinecap="round">
                <line x1="32" y1="32" x2="32" y2="14" />
                <line x1="32" y1="32" x2="47" y2="41" />
                <line x1="32" y1="32" x2="18" y2="43" />
              </g>
              <circle cx="32" cy="32" r="6.8" fill="none" stroke="#EBF5F5" strokeWidth="2.2" />
              <circle cx="32" cy="32" r="1.4" fill="#EBF5F5" />
              <rect x="28.7" y="10.7" width="6.6" height="6.6" rx="1.2" fill="#EBF5F5" />
              <circle cx="47" cy="41" r="3.2" fill="#EBF5F5" />
              <circle cx="18" cy="43" r="2.8" fill="#EBF5F5" />
            </svg>
          </div>
          <h1
            style={{
              fontFamily: "var(--trove-serif, Georgia, serif)",
              fontStyle: "italic",
              fontWeight: 400,
              fontSize: 28,
              textAlign: "center",
              color: "var(--fg-strong)",
              letterSpacing: "-0.015em",
            }}
          >
            Trove
          </h1>
          <p style={{ textAlign: "center", fontSize: 13, color: "var(--fg-muted)", fontFamily: "var(--trove-sans, sans-serif)", marginTop: 4 }}>
            Create your account
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="signup-email"
                style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--fg-muted)", marginBottom: 5, fontFamily: "var(--trove-sans, sans-serif)" }}
              >
                Email address
              </label>
              <Input
                id="signup-email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div>
              <label
                htmlFor="signup-password"
                style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--fg-muted)", marginBottom: 5, fontFamily: "var(--trove-sans, sans-serif)" }}
              >
                Password
              </label>
              <Input
                id="signup-password"
                type="password"
                placeholder="Min 6 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={6}
                required
              />
            </div>
            {error && (
              <p
                role="alert"
                aria-live="polite"
                style={{
                  fontSize: 13,
                  color: "var(--status-error-fg)",
                  background: "var(--status-error-bg)",
                  border: "1px solid var(--status-error-dot)",
                  borderRadius: 7,
                  padding: "8px 12px",
                  fontFamily: "var(--trove-sans, sans-serif)",
                }}
              >
                {error}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading && <Loader2 aria-hidden="true" className="mr-2 h-4 w-4 animate-spin" />}
              {loading ? "Creating account…" : "Sign up"}
            </Button>
          </form>
          <p style={{ marginTop: 16, textAlign: "center", fontSize: 13, color: "var(--fg-muted)", fontFamily: "var(--trove-sans, sans-serif)" }}>
            Already have an account?{" "}
            <Link href="/login" style={{ color: "var(--accent-ink)", textDecoration: "underline" }}>
              Sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
