"use client";

import Image from "next/image";
import { cn } from "@/lib/utils";

type ZiloLogoProps = {
  size?: number;
  className?: string;
  priority?: boolean;
  /**
   * `web` — normal site mark: modest rounding, no app-icon chrome (default).
   * `icon` — tighter squircle if you ever need an app-style tile.
   */
  shape?: "web" | "icon";
};

/** Brand mark from `/public/zilo-logo.png`. Default styling is for inline web headers, not app-store tiles. */
export function ZiloLogo({ size = 32, className, priority, shape = "web" }: ZiloLogoProps) {
  return (
    <Image
      src="/zilo-logo.png"
      alt="Zilo"
      width={size}
      height={size}
      priority={priority}
      className={cn(
        shape === "icon" ? "rounded-[22%] object-cover" : "rounded-md object-contain",
        className,
      )}
    />
  );
}
