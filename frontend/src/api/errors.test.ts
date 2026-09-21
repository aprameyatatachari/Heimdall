import { describe, expect, it } from "vitest";

import { ApiError, messageFor, NetworkError, toApiError } from "./errors";

function response(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("toApiError", () => {
  it("reads the backend envelope", async () => {
    const error = await toApiError(
      response(422, {
        error: { code: "validation_error", message: "Invalid.", request_id: "abc" },
      }),
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("validation_error");
    expect(error.message).toBe("Invalid.");
    expect(error.requestId).toBe("abc");
    expect(error.isValidation).toBe(true);
  });

  it("falls back to a generic message when the body is not the envelope", async () => {
    const error = await toApiError(new Response("<html>gateway</html>", { status: 502 }));

    expect(error.code).toBe("internal_error");
    expect(error.message).not.toContain("gateway");
  });

  it("never leaks an unparseable body to the user", async () => {
    const error = await toApiError(response(500, { detail: "psycopg2.OperationalError" }));

    expect(error.message).not.toContain("psycopg2");
  });
});

describe("ApiError", () => {
  it("maps field details onto their fields, stripping the body prefix", async () => {
    const error = await toApiError(
      response(422, {
        error: {
          code: "validation_error",
          message: "Invalid.",
          details: [
            { field: "body.password", message: "Too short.", code: "too_short" },
            { field: "body.email", message: "Not an email.", code: "invalid" },
          ],
        },
      }),
    );

    expect(error.fieldErrors()).toEqual({
      password: "Too short.",
      email: "Not an email.",
    });
  });

  it("ignores details that name no field", async () => {
    const error = await toApiError(
      response(422, {
        error: {
          code: "validation_error",
          message: "Invalid.",
          details: [{ message: "Something general." }],
        },
      }),
    );

    expect(error.fieldErrors()).toEqual({});
  });

  it("treats 404 as not found without distinguishing ownership", async () => {
    const error = await toApiError(
      response(404, {
        error: { code: "portfolio_not_found", message: "Portfolio not found." },
      }),
    );

    expect(error.isNotFound).toBe(true);
    expect(error.message).toBe("Portfolio not found.");
  });

  it("recognises a rate limit by status or by code", async () => {
    const byStatus = await toApiError(
      response(429, { error: { code: "rate_limited", message: "Too many attempts." } }),
    );
    expect(byStatus.isRateLimited).toBe(true);
  });
});

describe("messageFor", () => {
  it("passes through a described failure", () => {
    const error = new ApiError(400, { code: "bad", message: "Specific problem." });
    expect(messageFor(error)).toBe("Specific problem.");
  });

  it("distinguishes an unreachable server from a failing one", () => {
    expect(messageFor(new NetworkError())).toContain("Could not reach Heimdall");
  });

  it("gives an unknown throw a safe generic message", () => {
    expect(messageFor(new TypeError("x.y is not a function"))).not.toContain("not a function");
  });
});
