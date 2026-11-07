// choose-password.test.tsx — a person on a temporary password chooses their own before the office opens,
// with no second login (UI-5, AUTH-6, ADR-0038).
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ALLAUTH } from "@/api/allauth";
import { OfficeFrame } from "@/features/office/office-frame";
import { DAWA, whoIsHere } from "@/test/devices";
import { allauthRefusal, answer, fakeFetch, sent } from "@/test/fake-server";
import { render } from "@/test/render";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const CHANGE = `${ALLAUTH}account/password/change`;

const NEEMA = whoIsHere([{ side: DAWA, permissions: ["device.manage"] }]);

beforeEach(() => {
  // allauth's routes go through the browser's own fetch (src/api/allauth.ts).
  vi.stubGlobal("fetch", fakeFetch);
  document.cookie = "csrftoken=token-from-django; path=/";
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

/** Baba gave Neema a temporary password face to face; she has just logged in with it. The mark comes
 * off once she chooses her own, unless `change` answers otherwise. */
function onATemporaryPassword(change?: { status: number; body?: unknown }) {
  let mark = true;
  answer("GET", ME, () =>
    Response.json({ ...NEEMA, must_change_password: mark }),
  );
  answer(
    "POST",
    CHANGE,
    change ??
      (() => {
        mark = false;
        return Response.json({ status: 200 });
      }),
  );
}

function renderTheOffice() {
  return render(
    <OfficeFrame>
      <p>screen</p>
    </OfficeFrame>,
  );
}

function choose(temporary: string, fresh: string, again = fresh) {
  fireEvent.change(screen.getByLabelText("Nenosiri la muda"), {
    target: { value: temporary },
  });
  fireEvent.change(screen.getByLabelText("Nenosiri jipya"), {
    target: { value: fresh },
  });
  fireEvent.change(screen.getByLabelText("Andika nenosiri jipya tena"), {
    target: { value: again },
  });
  fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));
}

const changes = () =>
  sent.filter((request) => new URL(request.url).pathname === CHANGE);

describe("choosing your own password", () => {
  it("opens in place of the office screen while the password is temporary", async () => {
    onATemporaryPassword();

    renderTheOffice();

    expect(
      await screen.findByRole("heading", { name: "Chagua nenosiri lako" }),
    ).toBeTruthy();
    expect(screen.queryByText("screen")).toBeNull();
    // She can still leave: a lent phone must not stay logged in.
    expect(
      within(screen.getByRole("banner")).getByRole("button", { name: "Toka" }),
    ).toBeTruthy();
  });

  it("sends the temporary and the new password, and opens the office with no second login", async () => {
    onATemporaryPassword();
    renderTheOffice();
    await screen.findByRole("heading", { name: "Chagua nenosiri lako" });

    choose("muda-wa-baba-1", "siri-ya-neema-2026");

    expect(await screen.findByText("screen")).toBeTruthy();
    const [change] = changes();
    expect(await change?.json()).toEqual({
      current_password: "muda-wa-baba-1",
      new_password: "siri-ya-neema-2026",
    });
  });

  it("says beside its box when the temporary password is wrong", async () => {
    onATemporaryPassword(
      allauthRefusal(400, [
        { code: "enter_current_password", param: "current_password" },
      ]),
    );
    renderTheOffice();
    await screen.findByRole("heading", { name: "Chagua nenosiri lako" });

    choose("si-yenyewe", "siri-ya-neema-2026");

    expect(await screen.findByText("Nenosiri la sasa si sahihi.")).toBeTruthy();
    expect(
      screen.getByLabelText("Nenosiri la muda").getAttribute("aria-invalid"),
    ).toBe("true");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says beside the new box when the new password is the temporary one", async () => {
    // Baba still knows the temporary one (AUTH-6).
    onATemporaryPassword(
      allauthRefusal(400, [
        { code: "password.same_as_temporary", param: "new_password" },
      ]),
    );
    renderTheOffice();
    await screen.findByRole("heading", { name: "Chagua nenosiri lako" });

    choose("muda-wa-baba-1", "muda-wa-baba-1");

    expect(
      await screen.findByText("Chagua nenosiri tofauti na lile la muda."),
    ).toBeTruthy();
    expect(
      screen.getByLabelText("Nenosiri jipya").getAttribute("aria-invalid"),
    ).toBe("true");
  });

  it("asks for the new password twice, the same both times, before it sends anything", async () => {
    // A typo she can't see would lock her out until she sees the owner again.
    onATemporaryPassword();
    renderTheOffice();
    await screen.findByRole("heading", { name: "Chagua nenosiri lako" });

    choose("muda-wa-baba-1", "siri-ya-neema-2026", "siri-ya-neema-2062");

    expect(
      await screen.findByText("Andika nenosiri lile lile mara zote mbili."),
    ).toBeTruthy();
    expect(changes()).toEqual([]);
  });

  it("says too many tries when the limit answers", async () => {
    // 5 changes a minute per person (AUTH-6).
    onATemporaryPassword(allauthRefusal(429));
    renderTheOffice();
    await screen.findByRole("heading", { name: "Chagua nenosiri lako" });

    choose("muda-wa-baba-1", "siri-ya-neema-2026");

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Majaribio mengi mno",
    );
    await waitFor(() => expect(changes()).toHaveLength(1));
  });
});
