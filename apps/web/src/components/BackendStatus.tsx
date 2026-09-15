"use client";

import { useEffect, useState } from "react";
import { checkBackendHealth } from "@/lib/api";

type Status = "checking" | "connected" | "disconnected";

const STATUS_LABEL: Record<Status, string> = {
  checking: "Checking backend connection…",
  connected: "Backend connected",
  disconnected: "Backend not reachable",
};

const STATUS_DOT_CLASS: Record<Status, string> = {
  checking: "bg-zinc-400",
  connected: "bg-green-500",
  disconnected: "bg-red-500",
};

export function BackendStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;

    checkBackendHealth().then((isHealthy) => {
      if (!cancelled) setStatus(isHealthy ? "connected" : "disconnected");
    });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex items-center gap-2 rounded-full border border-black/[.08] px-4 py-2 text-sm dark:border-white/[.145]">
      <span
        className={`h-2 w-2 rounded-full ${STATUS_DOT_CLASS[status]}`}
        aria-hidden
      />
      <span>{STATUS_LABEL[status]}</span>
    </div>
  );
}
