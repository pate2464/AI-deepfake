import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Image Signal Review — authenticity & manipulation screening",
  description:
    "Plain-language image screening for manipulation and synthetic-content risk, with optional technical evidence for reviewers.",
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
