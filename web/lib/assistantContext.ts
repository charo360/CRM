import { assistantApi } from "./api";

export async function getBusinessContext() {
  return assistantApi.businessContext();
}
