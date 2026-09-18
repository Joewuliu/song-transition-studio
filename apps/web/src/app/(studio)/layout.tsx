import type { ReactNode } from "react";
import { StudioProvider } from "@/context/StudioContext";

/**
 * Groups the setup page (/) and the editor page (/editor) under one
 * client provider so the workspace state it holds (loaded files,
 * analyses, the transition plan, suggestion/preview state) survives
 * client-side navigation between them. The route group itself
 * (the parenthesized folder name) adds no URL segment.
 */
export default function StudioLayout({ children }: { children: ReactNode }) {
  return <StudioProvider>{children}</StudioProvider>;
}
