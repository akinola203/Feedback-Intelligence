"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Lock, Store } from "lucide-react";

import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";

export default function LoginPage() {
  const router = useRouter();
  const [orgSlug, setOrgSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    api.get("/api/auth/me/").catch(() => {
      // Expected 401 when unauthenticated; sets csrftoken cookie
    });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setIsLoading(true);

    try {
      await api.post("/api/auth/login/", {
        organization_slug: orgSlug.trim(),
        email: email.trim(),
        password: password,
      });

      router.push("/dashboard");
    } catch (err: any) {
      if (err.response?.data?.error) {
        setErrorMessage(err.response.data.error);
      } else if (err.response?.data?.detail) {
        setErrorMessage(err.response.data.detail);
      } else {
        setErrorMessage("Invalid credentials. Please check your details and try again.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen relative flex items-center justify-center p-4 bg-[#F3F3F3] text-black overflow-hidden">
      {/* Monochrome Ambient Light Blobs */}
      <div className="absolute top-1/4 -left-32 w-96 h-96 bg-neutral-300/30 rounded-full blur-3xl -z-10 pointer-events-none" />
      <div className="absolute bottom-1/4 -right-32 w-96 h-96 bg-black/[0.04] rounded-full blur-3xl -z-10 pointer-events-none" />
      <div className="absolute top-1/3 right-1/4 w-80 h-80 bg-neutral-400/20 rounded-full blur-3xl -z-10 pointer-events-none" />

      <Card className="max-w-md w-full overflow-hidden shadow-[0_16px_50px_rgba(0,0,0,0.08)]">
        {/* Smoked Black Glass Brand Header */}
        <div className="glass-smoked p-7 text-white border-b border-white/10 space-y-2">
          <div className="flex items-center space-x-2 text-[10px] font-bold uppercase tracking-widest text-neutral-300">
            <Store className="h-3.5 w-3.5 text-white" />
            <span>Feedback Intelligence</span>
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-white">
            Manager Portal
          </h1>
          <p className="text-xs text-neutral-300 font-medium">
            Sign in to monitor live store ratings, sector delegations &amp; QR stands
          </p>
        </div>

        <CardContent className="p-7 sm:p-8 space-y-6">
          {errorMessage && (
            <div className="p-3.5 bg-black/[0.05] border border-black/20 rounded-2xl text-xs font-semibold text-black">
              {errorMessage}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="orgSlug">
                Organization Slug{" "}
                <span className="text-neutral-400 font-normal normal-case">
                  (optional if email is unique)
                </span>
              </Label>
              <Input
                id="orgSlug"
                type="text"
                value={orgSlug}
                onChange={(e) => setOrgSlug(e.target.value)}
                placeholder="e.g. freshmart"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="email">Work Email</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@freshmart.ng"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
              />
            </div>

            <Button type="submit" disabled={isLoading} size="lg" className="w-full mt-2">
              <span>{isLoading ? "Signing in..." : "Sign In to Console"}</span>
              {!isLoading && <ArrowRight className="h-3.5 w-3.5" />}
            </Button>
          </form>

          <Separator />

          <div className="flex items-center justify-center gap-1.5 text-[10px] text-neutral-400 uppercase tracking-widest">
            <Lock className="h-3 w-3" />
            <span>Multi-Tenant Secure Session Authority</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
