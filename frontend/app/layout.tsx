import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Fraud Detector — 8-Layer Deep Analysis",
  description: "Detect AI-generated fraudulent images with 8 detection layers",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
