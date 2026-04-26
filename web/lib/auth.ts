import { mergeSidebarFeatures } from "./sidebarFeatures";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function setToken(token: string) {
  localStorage.setItem("token", token);
}

export function clearToken() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
}

export function getUser(): Record<string, unknown> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setUser(user: Record<string, unknown>) {
  localStorage.setItem("user", JSON.stringify(user));
}

/** Merge into `user.settings` in localStorage (e.g. after saving features or loading /settings). */
export function patchStoredUserSettings(partial: Record<string, unknown>) {
  const prev = getUser() || {};
  const prevSettings = ((prev.settings as Record<string, unknown>) || {}) as Record<string, unknown>;
  setUser({
    ...prev,
    settings: { ...prevSettings, ...partial },
  });
}

export function getBusinessId(): string | null {
  const user = getUser();
  return user?.business_id as string || user?._id as string || null;
}

export function getBusinessSettings(): Record<string, unknown> {
  const user = getUser();
  return user?.settings as Record<string, unknown> || {};
}

export function getCurrency(): string {
  const settings = getBusinessSettings();
  return settings?.currency as string || "KES";
}

export function getBusinessType(): string {
  const settings = getBusinessSettings();
  return settings?.business_type as string || "retail";
}

/** `individual` = solo use; `business` = company-style workspace (default for existing users). */
export function getAccountMode(): "individual" | "business" {
  const settings = getBusinessSettings();
  const raw = settings?.account_mode as string | undefined;
  if (raw === "individual") return "individual";
  return "business";
}

export function getSidebarFeatures(): Record<string, boolean> {
  const settings = getBusinessSettings();
  return mergeSidebarFeatures(settings?.features);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}
