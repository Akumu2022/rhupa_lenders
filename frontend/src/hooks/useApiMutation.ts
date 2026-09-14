import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { getErrorMessage } from "../api/client";
import { useToast } from "../components/toast";

/**
 * Wraps the standard "mutate, invalidate a query, toast the result" shape
 * repeated across every toggle/create mutation in the app (activate/
 * deactivate staff, suspend/reactivate branches and companies, etc.) — was
 * hand-copied per call site. Only the mutation-shape boilerplate is
 * extracted here; the actually-different form/field logic around each call
 * site is left alone (forcing one "CRUD page" component over those would
 * trade real duplication for a worse, leakier abstraction).
 *
 * `onSuccess`/`onError` are escape hatches for call sites that need extra
 * behavior beyond invalidate+toast (e.g. resetting local drawer state, or
 * showing the error inline instead of as a toast).
 */
export function useApiMutation<TData, TVariables = void>({
  mutationFn,
  queryKey,
  successMessage,
  onSuccess,
  onError,
}: {
  mutationFn: (variables: TVariables) => Promise<TData>;
  queryKey: QueryKey;
  successMessage?: (data: TData) => string;
  onSuccess?: (data: TData) => void;
  onError?: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();

  return useMutation({
    mutationFn,
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey });
      if (successMessage) toast(successMessage(data), "success");
      onSuccess?.(data);
    },
    onError: (err) => {
      const message = getErrorMessage(err);
      if (onError) onError(message);
      else toast(message, "error");
    },
  });
}
