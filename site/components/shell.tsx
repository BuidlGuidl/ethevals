"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { Logo } from "./logo";

export const repo = "https://github.com/BuidlGuidl/ethevals";
type Flight = { x: number; y: number; width: number; height: number; dx: number; dy: number; scale: number };

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const brand = useRef<HTMLAnchorElement>(null);
  const [inHero, setInHero] = useState(false);
  const [flight, setFlight] = useState<Flight | null>(null);
  const reduced = useReducedMotion();
  useEffect(() => {
    const logo = document.getElementById("hero-logo");
    if (!logo) return;
    let first = true, wasVisible = true;
    const observer = new IntersectionObserver(([entry]) => {
      const visible = entry.intersectionRatio >= .5;
      setInHero(visible);
      if (!first && wasVisible && !visible && !reduced && brand.current) {
        const a = logo.getBoundingClientRect(), b = brand.current.getBoundingClientRect();
        setFlight({ x: a.left, y: a.top, width: a.width, height: a.height,
          dx: b.left - a.left, dy: b.top - a.top, scale: b.width / a.width });
      }
      first = false;
      wasVisible = visible;
    }, { rootMargin: "-60px 0px 0px 0px", threshold: [0, .5, 1] });
    observer.observe(logo);
    return () => observer.disconnect();
  }, [pathname, reduced]);
  const hideBrand = pathname === "/" && inHero;
  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <nav className="topnav" aria-label="Site">
      <Link ref={brand} className={`brand ${hideBrand || flight ? "brand-hidden" : ""}`} href="/" aria-label="ETH Evals"><Logo id="nav-logo" /></Link>
      <span className={`navtag ${hideBrand ? "brand-hidden" : ""}`}>The open benchmark for AI on Ethereum</span>
      <div className="navlinks"><Link href="/" aria-current={pathname === "/" ? "page" : undefined}>Results</Link>
        <Link href="/how-it-works/" aria-current={pathname === "/how-it-works/" ? "page" : undefined}>How it works</Link>
        <a href={repo} target="_blank" rel="noreferrer">GitHub ↗</a></div>
    </nav>
    {flight && <motion.div aria-hidden="true" className="logo-flight" style={{ left: flight.x, top: flight.y, width: flight.width, height: flight.height }}
      initial={{ x: 0, y: 0, scale: 1 }} animate={{ x: flight.dx, y: flight.dy, scale: flight.scale }}
      transition={{ duration: .48, ease: [.2, .8, .2, 1] }} onAnimationComplete={() => setFlight(null)}><Logo id="flight-logo" /></motion.div>}
    {children}
    <footer className="sitefoot"><b>ETH Evals</b><span>Open evaluations of AI on Ethereum · <a href={repo} target="_blank" rel="noreferrer">BuidlGuidl/ethevals</a></span></footer>
  </>;
}
