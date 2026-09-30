import type { Metadata } from "next";
import "./style.css";

export const metadata: Metadata = {
  title: "ETH Evals",
  description: "How well agents do Ethereum work, and what bare models know about Ethereum.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
