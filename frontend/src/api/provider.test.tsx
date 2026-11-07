// provider.test.tsx — under QueryProvider a screen can ask for an answer, and a refusal reaches it at
// once, asked only one time (UI-2).
import { useQuery } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { QueryProvider } from "./provider";
import { ApiRefusal } from "./refusal";

// A screen in miniature: it asks for one answer and shows what became of it.
function Asker({ ask }: { ask: () => Promise<string> }) {
  const query = useQuery({ queryKey: ["test"], queryFn: ask });
  if (query.isError) return <p>{`failed: ${query.error.message}`}</p>;
  return <p>{query.data ?? "loading"}</p>;
}

describe("QueryProvider", () => {
  it("lets a screen ask for an answer", async () => {
    render(
      <QueryProvider>
        <Asker ask={() => Promise.resolve("Dawa")} />
      </QueryProvider>,
    );

    expect(await screen.findByText("Dawa")).toBeDefined();
  });

  it("shows a refusal at once, asked only one time", async () => {
    const ask = vi.fn(() =>
      Promise.reject(
        new ApiRefusal(403, {
          code: "password.must_change",
          message: "",
          fields: {},
          params: {},
        }),
      ),
    );

    render(
      <QueryProvider>
        <Asker ask={ask} />
      </QueryProvider>,
    );

    // With TanStack's default it would be asked 4 times, over about 7 seconds, and this would time out.
    expect(
      await screen.findByText("failed: password.must_change"),
    ).toBeDefined();
    expect(ask).toHaveBeenCalledTimes(1);
  });
});
