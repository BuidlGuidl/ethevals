"use client";

import { useState } from "react";
import { domains, domainNames, type Domain } from "../src/areas";
import { updateQuery } from "./url-state";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

function UpcomingDomain({ domain }: { domain: Domain }) {
  const [open, setOpen] = useState(false);
  return <Tooltip open={open} onOpenChange={setOpen} disableHoverableContent><TooltipTrigger asChild>
    <span className="inline-flex" tabIndex={0} onClick={(event) => { event.preventDefault(); setOpen(true); }}>
      <button type="button" className="badge border-dashed pointer-events-none" aria-pressed={false} disabled>{domainNames[domain]}</button>
    </span></TooltipTrigger>
    <TooltipContent>{domainNames[domain]} tasks are coming soon.</TooltipContent>
  </Tooltip>;
}

export function selectDomain(current: Domain | undefined, value: Domain) {
  updateQuery({ domain: current === value ? null : value });
}

export function DomainFilter({ taskDomains, domain }: { taskDomains: Domain[]; domain: Domain | undefined }) {
  return <div className="task-areas" role="group" aria-label="Filter by domain">
    {domains.map((value) => {
      const count = taskDomains.filter((domain) => domain === value).length;
      return count === 0 ? <UpcomingDomain key={value} domain={value} /> :
        <button type="button" className="badge" key={value} aria-pressed={domain === value}
          onClick={() => selectDomain(domain, value)}>{domainNames[value]} <span>{count}</span></button>;
    })}
  </div>;
}
