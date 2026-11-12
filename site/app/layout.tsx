import { JetBrains_Mono, VT323, Archivo } from "next/font/google";
import PlausibleProvider from "next-plausible";
import { Shell } from "../components/shell";
import { pageMetadata } from "../src/metadata";
import "./globals.css";

const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains" });
const terminal = VT323({ subsets: ["latin"], weight: "400", variable: "--font-vt323" });
const diagram = Archivo({ subsets: ["latin"], variable: "--font-archivo" });

export const metadata = pageMetadata("ETH Evals", "/");

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${mono.variable} ${terminal.variable} ${diagram.variable}`}>
      <head><PlausibleProvider src="https://plausible.io/js/pa-eNCEQYDtrvxw1dXrIz2f5.js" /></head>
      <body><Shell>{children}</Shell></body>
    </html>
  );
}
