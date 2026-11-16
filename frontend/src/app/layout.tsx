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
      <body className="min-h-screen bg-[#F3F3F3] text-black antialiased selection:bg-black selection:text-white">
        {children}
      </body>
    </html>
  );
}
