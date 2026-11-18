"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, LogOut, QrCode, ShieldAlert, Store } from "lucide-react";

import api, { UserProfile } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    api
      .get<UserProfile>("/api/auth/me/")
      .then((res) => {
        if (isMounted) {
          setUser(res.data);
          setIsLoading(false);
        }
      })
      .catch(() => {
        if (isMounted) {
          router.push("/login");
        }
      });

    return () => {
      isMounted = false;
    };
  }, [router]);

  const handleLogout = async () => {
    try {
      await api.post("/api/auth/logout/");
    } catch {
      // ignore
    } finally {
      router.push("/login");
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F3F3F3]">
        <div className="glass-panel p-6 rounded-3xl flex items-center space-x-3 text-black font-semibold text-xs animate-pulse">
          <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
          <span>Verifying authentication context...</span>
        </div>
      </div>
    );
  }

  const roleBadgeVariant =
    user?.role === "admin"
      ? "default"
      : user?.role === "manager"
      ? "high"
      : "medium";

  const navItems = [
    { label: "Overview", href: "/dashboard", icon: BarChart3 },
    { label: "Complaints", href: "/dashboard/complaints", icon: ShieldAlert },
    { label: "QR Codes", href: "/dashboard/qrcodes", icon: QrCode },
  ];

  return (
    <div className="min-h-screen bg-[#F3F3F3] text-black relative flex flex-col overflow-x-hidden">
      {/* Monochrome Ambient Light Blobs */}
      <div className="absolute top-0 right-1/4 w-[500px] h-[500px] bg-neutral-300/25 rounded-full blur-3xl -z-10 pointer-events-none" />
      <div className="absolute bottom-1/3 -left-32 w-[450px] h-[450px] bg-black/[0.03] rounded-full blur-3xl -z-10 pointer-events-none" />

      {/* Sticky High-Contrast Frosted Glass Header */}
      <header className="sticky top-0 z-30 bg-white/70 backdrop-blur-2xl border-b border-black/[0.08] shadow-[0_4px_24px_rgba(0,0,0,0.02)]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex items-center justify-between">
          <div className="flex items-center space-x-8">
            <Link href="/dashboard" className="flex items-center space-x-3 group">
              <span className="w-9 h-9 bg-black text-white rounded-xl flex items-center justify-center shadow-md group-hover:scale-105 transition">
                <Store className="h-4 w-4" />
              </span>
              <div>
                <span className="font-extrabold text-black text-sm tracking-tight leading-none block">
                  {user?.organization_name || "Supermarket"}
                </span>
                <span className="text-[9px] uppercase font-bold text-neutral-400 tracking-widest">
                  Feedback Intelligence
                </span>
              </div>
            </Link>

            {/* Desktop Navigation Links */}
            <nav className="hidden md:flex glass-well p-1 rounded-2xl space-x-1">
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all duration-150 ${
                      isActive
                        ? "bg-black text-white shadow-sm"
                        : "text-neutral-600 hover:text-black hover:bg-white/60"
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center space-x-3.5">
            <div className="hidden sm:flex flex-col items-end text-right">
              <span className="text-xs font-bold text-black leading-tight">
                {user?.full_name || user?.email}
              </span>
              <span className="text-[10px] text-neutral-400 font-mono">{user?.email}</span>
            </div>

            <Badge variant={roleBadgeVariant}>{user?.role}</Badge>

            <Button variant="outline" size="sm" onClick={handleLogout}>
              <LogOut className="h-3.5 w-3.5" />
              <span>Sign Out</span>
            </Button>
          </div>
        </div>

        {/* Mobile Navigation Bar */}
        <div className="md:hidden border-t border-black/[0.06] px-4 py-2 flex space-x-1 bg-white/50 backdrop-blur-md overflow-x-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold whitespace-nowrap transition ${
                  isActive
                    ? "bg-black text-white"
                    : "text-neutral-600 hover:text-black"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      </header>

      {/* Main Content Viewport */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8">
        {children}
      </main>
    </div>
  );
}
