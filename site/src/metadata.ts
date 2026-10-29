import type { Metadata } from "next";

const description = "We evaluate agents used by developers, and the models behind them, on real Ethereum work.";

export function pageMetadata(title: string, pathname: string): Metadata {
  return {
    metadataBase: new URL("https://ethevals.com"),
    title,
    description,
    openGraph: {
      title,
      description,
      url: pathname,
      images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "The Open Benchmark for AI on Ethereum" }],
    },
    twitter: { card: "summary_large_image", title, description, images: ["/og-image.png"] },
    icons: { icon: "/favicon.ico" },
  };
}
