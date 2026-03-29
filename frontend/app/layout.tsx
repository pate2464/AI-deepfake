import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Fraud Detector — Split Review Workspace",
  description: "Review source images and grouped 21-layer fraud analysis in a split-screen workspace.",
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
