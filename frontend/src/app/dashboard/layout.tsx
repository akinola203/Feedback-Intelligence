"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import api, { UserProfile } from "@/lib/api";

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
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="flex items-center space-x-3 text-slate-500 font-medium text-sm animate-pulse">
          <div className="w-5 h-5 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
          <span>Verifying authentication...</span>
        </div>
      </div>
    );
  }

  const roleBadgeColor = {
    admin: "bg-purple-100 text-purple-700 border-purple-200",
    manager: "bg-blue-100 text-blue-700 border-blue-200",
    staff: "bg-emerald-100 text-emerald-700 border-emerald-200",
  }[user?.role || "staff"];

  const navItems = [
    { label: "Analytics", href: "/dashboard", icon: "📊" },
    { label: "Complaints", href: "/dashboard/complaints", icon: "🚨" },
    { label: "Branch QR Codes", href: "/dashboard/qrcodes", icon: "📱" },
  ];

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Top Navigation Bar */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-8">
            <Link href="/dashboard" className="flex items-center space-x-2.5">
              <span className="text-xl">🛒</span>
              <div>
                <span className="font-bold text-slate-900 text-base leading-none block">
                  {user?.organization_name || "Supermarket"}
                </span>
                <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">
                  Feedback Intelligence
                </span>
              </div>
            </Link>

            <nav className="hidden md:flex space-x-1">
              {navItems.map((item) => {
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center space-x-2 px-3 py-2 rounded-xl text-xs font-semibold transition ${
                      isActive
                        ? "bg-slate-100 text-slate-900"
                        : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                    }`}
                  >
                    <span>{item.icon}</span>
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center space-x-4">
            <div className="hidden sm:flex flex-col items-end">
              <span className="text-xs font-semibold text-slate-800">
                {user?.full_name || user?.email}
              </span>
              <span className="text-[10px] text-slate-400">{user?.email}</span>
            </div>

            <span
              className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full border ${roleBadgeColor}`}
            >
              {user?.role}
            </span>

            <button
              onClick={handleLogout}
              className="text-xs text-slate-500 hover:text-slate-900 font-medium px-3 py-1.5 rounded-lg border border-slate-200 hover:border-slate-300 transition"
            >
              Sign Out
            </button>
          </div>
        </div>

        {/* Mobile Navigation Bar */}
        <div className="md:hidden border-t border-slate-100 px-4 py-2 flex space-x-1 bg-white overflow-x-auto">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap ${
                  isActive
                    ? "bg-slate-100 text-slate-900"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8">
        {children}
      </main>
    </div>
  );
}
