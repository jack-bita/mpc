// use-approval.ts — sending an approval, a month's or one worker's alone (WAGE-3): what both sheets do alike around their
// own request. Once approved, every page it locks is read again before the sheet closes, so it never closes onto pay that
// still looks open. A try that failed reads them again too: refused because a total moved, the new ones show; and with no
// answer, it may have been approved all the same.
//
// The request's id is made once, as the sheet opens: the same try sent again is the same approval (ADR-0007).
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { newId } from "@/lib/ids";

import { whatAnApprovalLocks } from "./pay";

export function useApproval(
  send: (id: string) => Promise<unknown>,
  onDone: () => void,
) {
  const store = useQueryClient();
  const [id] = useState(newId);
  const askAgain = () =>
    Promise.all(
      whatAnApprovalLocks().map((queryKey) =>
        store.invalidateQueries({ queryKey }),
      ),
    );
  return useMutation({
    mutationFn: () => send(id),
    onSuccess: async () => {
      // The mutation stays on its way until this ends (TanStack waits for what it returns), so the sheet stays held.
      await askAgain();
      onDone();
    },
    onError: () => void askAgain(),
  });
}
