"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [orgSlug, setOrgSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Prefetch CSRF cookie on mount for clean first-attempt session login
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

      {/* Floating Frosted White Glass Showcase Card */}
      <div className="max-w-md w-full glass-panel rounded-3xl overflow-hidden shadow-[0_16px_50px_rgba(0,0,0,0.08)] border border-white/90">
        {/* Smoked Black Glass Brand Header */}
        <div className="glass-smoked p-7 text-white border-b border-white/10 space-y-2">
          <div className="flex items-center space-x-2 text-[10px] font-bold uppercase tracking-widest text-neutral-300">
            <span className="w-2 h-2 rounded-full bg-white" />
            <span>Feedback Intelligence</span>
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-white">
            Manager Portal
          </h1>
          <p className="text-xs text-neutral-300 font-medium">
            Sign in to monitor live store ratings, complaints & QR stands
          </p>
        </div>

        <div className="p-7 sm:p-8 space-y-6">
          {errorMessage && (
            <div className="p-3.5 bg-black/[0.05] border border-black/20 rounded-2xl text-xs font-semibold text-black">
              {errorMessage}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="block text-[11px] font-bold text-black uppercase tracking-wider">
                Organization Slug <span className="text-neutral-400 font-normal normal-case">(optional if email is unique)</span>
              </label>
              <input
                type="text"
                value={orgSlug}
                onChange={(e) => setOrgSlug(e.target.value)}
                placeholder="e.g. freshmart"
                className="w-full glass-input rounded-2xl px-4 py-3 text-xs placeholder-neutral-400 font-medium"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-[11px] font-bold text-black uppercase tracking-wider">
                Work Email
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@freshmart.ng"
                className="w-full glass-input rounded-2xl px-4 py-3 text-xs placeholder-neutral-400 font-medium"
              />
            </div>

            <div className="space-y-1.5">
              <label className="block text-[11px] font-bold text-black uppercase tracking-wider">
                Password
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full glass-input rounded-2xl px-4 py-3 text-xs placeholder-neutral-400 font-medium"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3.5 bg-black hover:bg-neutral-800 disabled:bg-neutral-300 text-white rounded-2xl text-xs font-bold shadow-xl hover:-translate-y-0.5 active:scale-[0.99] transition duration-200 mt-2"
            >
              {isLoading ? "Signing in..." : "Sign In to Console"}
            </button>
          </form>

          <div className="pt-3 text-center text-[10px] text-neutral-400 uppercase tracking-widest border-t border-black/[0.06]">
            Multi-Tenant Secure Session Authority
          </div>
        </div>
      </div>
    </div>
  );
}
