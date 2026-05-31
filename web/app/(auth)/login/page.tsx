"use client";

import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2 } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const supabase = createClient();
    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (error) {
      setError(error.message);
      setLoading(false);
      return;
    }

    router.push("/");
    router.refresh();
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
            Sign in to your account
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="login-email"
                style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--fg-muted)", marginBottom: 5, fontFamily: "var(--trove-sans, sans-serif)" }}
              >
                Email address
              </label>
              <Input
                id="login-email"
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
                htmlFor="login-password"
                style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--fg-muted)", marginBottom: 5, fontFamily: "var(--trove-sans, sans-serif)" }}
              >
                Password
              </label>
              <Input
                id="login-password"
                type="password"
                placeholder="Your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
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
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </form>
          <p style={{ marginTop: 16, textAlign: "center", fontSize: 13, color: "var(--fg-muted)", fontFamily: "var(--trove-sans, sans-serif)" }}>
            No account?{" "}
            <Link href="/signup" style={{ color: "var(--accent-ink)", textDecoration: "underline" }}>
              Sign up
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
