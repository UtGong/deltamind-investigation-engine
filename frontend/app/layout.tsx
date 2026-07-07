import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DeltaMind Investigation Engine",
  description: "Evidence-driven claim and report verification",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
