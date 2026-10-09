import { checkHealth, analyzeDecision, ApiClientError, getApiBaseUrl } from "./api";

export { ApiClientError, checkHealth, analyzeDecision, getApiBaseUrl };

export const apiClient = {
  checkHealth,
  analyzeDecision,
  getBaseUrl: getApiBaseUrl,
};

