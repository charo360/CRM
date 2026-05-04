import { getToken } from "@/lib/auth";
import { NANGO_PUBLIC_API_URL, NANGO_PUBLIC_CONNECT_UI_URL } from "@/lib/nango-config";
import { toast } from "sonner";

export type OpenNangoConnectOptions = {
  /** Called when Nango reports success; polled a few times so UI catches slightly delayed indexing. */
  onAfterConnect?: () => void;
};

export async function openNangoConnect(
  allowedIntegrations: string[],
  opts?: OpenNangoConnectOptions
): Promise<void> {
  const token = getToken();
  if (!token) {
    toast.error("Sign in required");
    return;
  }

  const res = await fetch("/api/nango/connect-session", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ allowed_integrations: allowedIntegrations }),
  });

  const data = (await res.json().catch(() => ({}))) as { sessionToken?: string; error?: string };
  if (!res.ok) {
    toast.error(data.error || "Could not start connection");
    return;
  }

  if (!data.sessionToken) {
    toast.error("Missing session from server");
    return;
  }

  const { default: Nango } = await import("@nangohq/frontend");
  const nango = new Nango();
  // openConnectUI already calls open() internally — do NOT call ui.open() again
  const ui = nango.openConnectUI({
    sessionToken: data.sessionToken,
    apiURL: NANGO_PUBLIC_API_URL,
    baseURL: NANGO_PUBLIC_CONNECT_UI_URL,
    onEvent: (event) => {
      if (event.type === "connect") {
        toast.success("Connected");
        ui.close();
        // Record each connected integration in our DB so status is user-isolated
        // and doesn't rely on Nango's tag-filter returning correct results.
        const currentToken = getToken();
        if (currentToken && allowedIntegrations.length) {
          for (const integrationId of allowedIntegrations) {
            fetch("/api/nango/record-connection", {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${currentToken}`,
              },
              body: JSON.stringify({ integration_id: integrationId }),
            }).catch(() => {});
          }
        }
        const fn = opts?.onAfterConnect;
        if (fn) {
          const delaysMs = [0, 700, 2000, 4500];
          for (const ms of delaysMs) {
            window.setTimeout(fn, ms);
          }
        }
      }
      if (event.type === "error") {
        toast.error(event.payload.errorMessage || "Connection failed");
      }
    },
  });
}
