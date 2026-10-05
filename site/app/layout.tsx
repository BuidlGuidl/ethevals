import type { Metadata } from "next";
import { JetBrains_Mono, VT323, Archivo } from "next/font/google";
import { Shell } from "../components/shell";
import "./globals.css";

const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains" });
const terminal = VT323({ subsets: ["latin"], weight: "400", variable: "--font-vt323" });
const diagram = Archivo({ subsets: ["latin"], variable: "--font-archivo" });

export const metadata: Metadata = {
  title: "ETH Evals",
  description: "How well agents do Ethereum work, and what bare models know about Ethereum.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" className={`${mono.variable} ${terminal.variable} ${diagram.variable}`}><body><Shell>{children}</Shell></body></html>;
}
