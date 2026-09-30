import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { apiRequest, getErrorMessage } from "../api/client";
import { useBranding } from "../branding";
import { formatDateTime, formatKES } from "../schemas/analytics";
import { useToast } from "./toast";
import { Banner, Button, Field, Select, TextInput } from "./ui";

// Mirrors backend app/schemas/loan.py::StaffPaymentRequest / ReceiptResponse.
const paymentSchema = z
  .object({
    amount: z
      .string()
      .trim()
      .regex(/^\d+(\.\d{1,2})?$/, "Enter an amount like 1500 or 1500.50")
      .refine((v) => !/^0+(\.0+)?$/.test(v), "Amount must be more than zero"),
    method: z.enum(["cash", "mpesa", "bank"]),
    reference: z.string().trim().max(64).optional(),
    notes: z.string().trim().max(500).optional(),
  })
  .refine((v) => v.method === "cash" || !!v.reference, {
    message: "Enter the M-Pesa code or bank slip number",
    path: ["reference"],
  });
type PaymentInput = z.infer<typeof paymentSchema>;

export interface ReceiptResponse {
  transaction_id: number;
  receipt_number: string;
  loan_id: number;
  application_id: number;
  customer_full_name: string;
  loan_product_name: string;
  amount: string;
  method: "cash" | "mpesa" | "bank";
  reference: string | null;
  notes: string | null;
  received_by_name: string;
  received_at: string;
  outstanding_balance_after: string;
  loan_status: string;
}

const METHOD_LABEL: Record<string, string> = { cash: "Cash", mpesa: "M-Pesa", bank: "Bank deposit" };

/** Staff record money the borrower paid them. The server applies it (same
 * path as self-service repayment), issues the receipt number, and refuses a
 * reference it has already seen — this form only collects the facts. */
export function RecordPaymentPanel({
  loanId,
  outstanding,
  isOpen,
}: {
  loanId: number;
  outstanding: string;
  /** False once the loan is repaid (or not yet disbursed) — the receipt of
   * the payment that closed it stays visible, the form doesn't. */
  isOpen: boolean;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [receipt, setReceipt] = useState<ReceiptResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors },
  } = useForm<PaymentInput>({ resolver: zodResolver(paymentSchema), defaultValues: { method: "mpesa" } });
  const method = watch("method");

  const mutation = useMutation({
    mutationFn: (input: PaymentInput) =>
      apiRequest<ReceiptResponse>(`/loans/${loanId}/payments`, {
        method: "POST",
        body: {
          amount: input.amount,
          method: input.method,
          reference: input.reference || null,
          notes: input.notes || null,
        },
      }),
    onSuccess: (data) => {
      setError(null);
      setReceipt(data);
      reset({ method: data.method, amount: "", reference: "", notes: "" });
      toast(`Payment recorded — receipt ${data.receipt_number}`, "success");
      // Balances, dashboards, lists and this loan's history all changed.
      void queryClient.invalidateQueries({ queryKey: ["analytics"] });
      void queryClient.invalidateQueries({ queryKey: ["collections"] });
      void queryClient.invalidateQueries({ queryKey: ["finance"] });
      void queryClient.invalidateQueries({ queryKey: ["branch-manager"] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  if (receipt) return <ReceiptView receipt={receipt} onDone={() => setReceipt(null)} canRecordAnother={isOpen} />;
  if (!isOpen) return null;

  return (
    <form onSubmit={handleSubmit((v) => mutation.mutate(v))} className="space-y-3" noValidate>
      <p className="text-xs text-slate-500 dark:text-slate-400">
        Outstanding: <span className="font-semibold tabular-nums text-slate-900 dark:text-slate-50">{formatKES(outstanding)}</span>
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Amount (KES)" error={errors.amount?.message}>
          <TextInput inputMode="decimal" placeholder="1500" {...register("amount")} />
        </Field>
        <Field label="Method" error={errors.method?.message}>
          <Select {...register("method")}>
            <option value="mpesa">M-Pesa</option>
            <option value="cash">Cash</option>
            <option value="bank">Bank deposit</option>
          </Select>
        </Field>
      </div>
      <Field
        label={method === "mpesa" ? "M-Pesa code" : method === "bank" ? "Bank slip / reference" : "Reference (optional)"}
        error={errors.reference?.message}
      >
        <TextInput placeholder={method === "mpesa" ? "e.g. QAB12CD34E" : ""} autoCapitalize="characters" {...register("reference")} />
      </Field>
      <Field label="Notes (optional)" error={errors.notes?.message}>
        <TextInput placeholder="e.g. Paid at branch counter" {...register("notes")} />
      </Field>
      {error ? <Banner kind="error">{error}</Banner> : null}
      <Button type="submit" disabled={mutation.isPending}>
        {mutation.isPending ? "Recording…" : "Record payment"}
      </Button>
    </form>
  );
}

function ReceiptView({
  receipt,
  onDone,
  canRecordAnother,
}: {
  receipt: ReceiptResponse;
  onDone: () => void;
  canRecordAnother: boolean;
}) {
  const branding = useBranding();
  const rows: [string, string][] = [
    ["Receipt no.", receipt.receipt_number],
    ["Date", formatDateTime(receipt.received_at)],
    ["Customer", receipt.customer_full_name],
    ["Loan", `${receipt.loan_product_name} (#${receipt.loan_id})`],
    ["Amount paid", formatKES(receipt.amount)],
    ["Method", METHOD_LABEL[receipt.method] ?? receipt.method],
    ...(receipt.reference ? ([["Reference", receipt.reference]] as [string, string][]) : []),
    ["Balance after payment", formatKES(receipt.outstanding_balance_after)],
    ["Received by", receipt.received_by_name],
  ];

  function print() {
    const escape = (v: string) =>
      v.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
    const win = window.open("", "_blank", "width=420,height=640");
    if (!win) return;
    win.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${escape(receipt.receipt_number)}</title>
      <style>body{font-family:system-ui,sans-serif;padding:24px;color:#0f172a}h1{font-size:18px;margin:0}
      p{margin:2px 0 16px;color:#475569;font-size:12px}table{width:100%;border-collapse:collapse;font-size:13px}
      td{padding:6px 0;border-bottom:1px solid #e2e8f0}td:last-child{text-align:right;font-weight:600}
      .foot{margin-top:24px;font-size:11px;color:#64748b;text-align:center}</style></head><body>
      <h1>${escape(branding.name ?? "Payment receipt")}</h1><p>Payment receipt</p>
      <table>${rows.map(([k, v]) => `<tr><td>${escape(k)}</td><td>${escape(v)}</td></tr>`).join("")}</table>
      <div class="foot">Thank you for your payment.</div></body></html>`);
    win.document.close();
    win.focus();
    win.print();
  }

  return (
    <div className="space-y-3">
      <Banner kind="success">
        Payment recorded. Receipt <span className="font-semibold">{receipt.receipt_number}</span>
        {receipt.loan_status === "repaid" ? " — loan fully repaid." : "."}
      </Banner>
      <dl className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 py-1.5">
            <dt className="text-slate-500 dark:text-slate-400">{k}</dt>
            <dd className="text-right font-medium tabular-nums text-slate-900 dark:text-slate-50">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="flex gap-2">
        <Button type="button" onClick={print}>
          Print receipt
        </Button>
        {canRecordAnother ? (
          <Button type="button" variant="secondary" onClick={onDone}>
            Record another
          </Button>
        ) : null}
      </div>
    </div>
  );
}
