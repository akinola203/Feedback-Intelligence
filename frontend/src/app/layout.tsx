import "./globals.css";
import React from "react";

export const metadata = {
  title: "Supermarket Feedback Intelligence",
  description: "Customer feedback, analytics, and complaint resolution platform for supermarkets",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}
