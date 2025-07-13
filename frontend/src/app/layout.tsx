import type { Metadata } from "next";
import "./globals.css";
import "../index.css";

export const metadata: Metadata = {
  title: "Context-Based PII Redaction",
  description: "A system for redacting PII from Contact Center AI transcripts",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        {children}
      </body>
    </html>
  );
}
