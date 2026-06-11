"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

/**
 * Automations has been replaced by Delegate. Redirect any old links.
 */
export default function WorkflowsRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/dashboard/delegate");
  }, [router]);
  return (
    <div className="flex items-center justify-center py-20 text-slate-400">
      <Loader2 className="h-5 w-5 animate-spin" />
    </div>
  );
}
