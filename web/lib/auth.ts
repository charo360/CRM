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

export function isAuthenticated(): boolean {
  return !!getToken();
}
