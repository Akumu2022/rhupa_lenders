import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiRequest, getErrorMessage } from "../../api/client";
import { Banner, Button, Card, Field, SectionLabel, TextInput } from "../../components/ui";
import { useToast } from "../../components/toast";

interface PaymentSettings {
  auto_disburse_enabled: boolean;
  auto_disburse_max_amount: string | null;
  stk_push_enabled: boolean;
}

/** system_administrator's switches for automatic disbursement and STK-push
 * reminders. Both are off until turned on here; every change is audited. */
export function PaymentAutomationCard() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [autoDisburse, setAutoDisburse] = useState(false);
  const [maxAmount, setMaxAmount] = useState("");
  const [stkPush, setStkPush] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const settingsQuery = useQuery({
    queryKey: ["companies", "me", "payment-settings"],
    queryFn: () => apiRequest<PaymentSettings>("/companies/me/payment-settings"),
  });

  useEffect(() => {
    if (settingsQuery.data) {
      setAutoDisburse(settingsQuery.data.auto_disburse_enabled);
      setMaxAmount(settingsQuery.data.auto_disburse_max_amount ?? "");
      setStkPush(settingsQuery.data.stk_push_enabled);
    }
  }, [settingsQuery.data]);

  async function save() {
    setError(null);
    if (autoDisburse && !(Number(maxAmount) > 0)) {
      setError("Enter a maximum amount before turning on automatic disbursement.");
      return;
    }
    setSaving(true);
    try {
      await apiRequest("/companies/me/payment-settings", {
        method: "PATCH",
        body: {
          auto_disburse_enabled: autoDisburse,
          ...(maxAmount ? { auto_disburse_max_amount: maxAmount } : {}),
          stk_push_enabled: stkPush,
        },
      });
      void queryClient.invalidateQueries({ queryKey: ["companies", "me", "payment-settings"] });
      toast("Payment settings saved", "success");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="mt-4">
      <SectionLabel>Payment automation</SectionLabel>
      {settingsQuery.isLoading ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
      ) : (
        <div className="space-y-4">
          {error ? <Banner kind="error">{error}</Banner> : null}

          <label className="flex items-start gap-3 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" className="mt-1 h-4 w-4" checked={autoDisburse} onChange={(e) => setAutoDisburse(e.target.checked)} />
            <span>
              <span className="font-semibold">Disburse approved loans automatically</span>
              <span className="block text-xs text-slate-500 dark:text-slate-400">
                Loans up to the maximum below are released as soon as they are approved. Larger loans still wait for the
                cashier / finance officer.
              </span>
            </span>
          </label>

          <Field label="Maximum amount released automatically (KES)">
            <TextInput
              inputMode="decimal"
              placeholder="e.g. 10000"
              value={maxAmount}
              onChange={(e) => setMaxAmount(e.target.value)}
            />
          </Field>

          <label className="flex items-start gap-3 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" className="mt-1 h-4 w-4" checked={stkPush} onChange={(e) => setStkPush(e.target.checked)} />
            <span>
              <span className="font-semibold">Send payment prompts (STK push) when an instalment is due</span>
              <span className="block text-xs text-slate-500 dark:text-slate-400">
                Daytime only, at most once a day and three times per instalment. Payments still arrive through the bank.
              </span>
            </span>
          </label>

          <Button type="button" onClick={() => void save()} disabled={saving}>
            {saving ? "Saving…" : "Save settings"}
          </Button>
        </div>
      )}
    </Card>
  );
}
