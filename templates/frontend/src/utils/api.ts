const STAFF_TOKEN_KEY = "care_access_token";
const PATIENT_TOKEN_KEY = "care_patient_token";
const BASE_PATH = "/api/__PLUGIN_SNAKE__";

/** The patient portal authenticates with an OTP token instead of a staff one. */
function getPatientToken(): string | null {
  try {
    const stored = JSON.parse(
      localStorage.getItem(PATIENT_TOKEN_KEY) || "null",
    );
    return stored?.token ?? null;
  } catch {
    return null;
  }
}

export function isPatientSession() {
  return !localStorage.getItem(STAFF_TOKEN_KEY) && !!getPatientToken();
}

function getAuthToken() {
  return localStorage.getItem(STAFF_TOKEN_KEY) ?? getPatientToken();
}

/** OTP callers get a separate, phone-number-scoped set of routes. */
function scope() {
  return isPatientSession() ? "/otp" : "";
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(status: number, data: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

function readErrorMessage(status: number, data: unknown) {
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    const detail = record.detail ?? record.non_field_errors;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && typeof detail[0] === "string") return detail[0];
  }
  return `Request failed with status ${status}`;
}

export async function request<T>(
  endpoint: string,
  method: Method = "GET",
  body?: unknown,
  queryParams?: Record<string, string | number | boolean | undefined | null>,
): Promise<T> {
  let url = `${window.CARE_API_URL}${BASE_PATH}${endpoint}`;

  if (queryParams) {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(queryParams)) {
      if (value !== undefined && value !== null && value !== "") {
        search.append(key, String(value));
      }
    }
    const qs = search.toString();
    if (qs) url += `?${qs}`;
  }

  const token = getAuthToken();

  const response = await fetch(url, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  // Parse text-then-JSON so empty 204 bodies don't throw.
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new ApiError(
      response.status,
      data,
      readErrorMessage(response.status, data),
    );
  }

  return data as T;
}

export const API = {
  config: () => request<{ enabled: boolean }>(`${scope()}/config/`),
};
