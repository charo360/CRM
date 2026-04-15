import { getToken } from "@/lib/auth";
import { NANGO_PUBLIC_API_URL, NANGO_PUBLIC_CONNECT_UI_URL } from "@/lib/nango-config";
import { toast } from "sonner";

export async function openNangoConnect(allowedIntegrations: string[]): Promise<void> {
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
  const ui = nango.openConnectUI({
    sessionToken: data.sessionToken,
    apiURL: NANGO_PUBLIC_API_URL,
    baseURL: NANGO_PUBLIC_CONNECT_UI_URL,
    onEvent: (event) => {
      if (event.type === "connect") {
        toast.success("Connected");
        ui.close();
      }
      if (event.type === "error") {
        toast.error(event.payload.errorMessage || "Connection failed");
      }
    },
  });
  ui.open();
}
