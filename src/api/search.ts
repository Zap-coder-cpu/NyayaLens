import { createServerFn } from "@tanstack/react-start";
import { searchRequestSchema, searchResponseSchema } from "@/contracts/search";

const DEFAULT_RETRIEVAL_URL = "http://127.0.0.1:8001";
const DEFAULT_RETRIEVAL_TIMEOUT_MS = 120_000;

export const searchCasesFn = createServerFn({ method: "POST" })
  .validator((input: unknown) => searchRequestSchema.parse(input))
  .handler(async ({ data }) => {
    const serviceUrl = (process.env["RETRIEVAL_SERVICE_URL"] || DEFAULT_RETRIEVAL_URL).replace(
      /\/$/,
      "",
    );
    const serviceSecret = process.env["RETRIEVAL_SERVICE_SECRET"]?.trim();
    const configuredTimeout = Number(process.env["RETRIEVAL_REQUEST_TIMEOUT_MS"]);
    const requestTimeoutMs =
      Number.isFinite(configuredTimeout) && configuredTimeout >= 1_000
        ? Math.min(configuredTimeout, 300_000)
        : DEFAULT_RETRIEVAL_TIMEOUT_MS;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), requestTimeoutMs);

    try {
      const response = await fetch(`${serviceUrl}/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(serviceSecret ? { "X-Retrieval-Secret": serviceSecret } : {}),
        },
        body: JSON.stringify(data),
        signal: controller.signal,
      });

      if (!response.ok) {
        console.error("Retrieval service returned", response.status, await response.text());
        throw new Error("The local retrieval service could not complete the search.");
      }

      return searchResponseSchema.parse(await response.json());
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        throw new Error("The local retrieval service timed out. Please try again.");
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  });
