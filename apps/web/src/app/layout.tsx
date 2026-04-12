import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "danny_rag",
  description: "RAG knowledge chatbot — built end-to-end as a learning project.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
