import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { apiRequest, getErrorMessage } from "../../api/client";
import { AmortizationTable } from "../../components/AmortizationTable";
import { AppShell } from "../../components/AppShell";
import { Banner, Card, Field, PageHeader, Select, TextInput } from "../../components/ui";
import { loanCalculatorSchema, type LoanCalculatorInput, type LoanCalculatorResponse } from "../../schemas/admin";

const INTEREST_MODEL_LABELS: Record<string, string> = {
  flat: "Flat (principal × rate, once)",
  reducing_balance: "Reducing balance (amortized)",
  daily_accrual: "Daily accrual",
};

const INTEREST_MODELS = new Set(Object.keys(INTEREST_MODEL_LABELS));

function isInterestModel(value: string | null): value is LoanCalculatorInput["interest_model"] {
  return value !== null && INTEREST_MODELS.has(value);
}

/** CLAUDE.md §23: "frontend never computes real money" — every number below
 * comes from POST /admin/loans/calculator, which calls the exact same
 * generate_schedule() dispatcher the real approval flow uses. Nothing here
 * is persisted; this is a what-if tool, not a way to create a loan. */
export function CompanyLoanCalculatorPage() {
  // ProductsPage links here with these prefilled (see calculatorUrlForProduct)
  // so an admin can preview exactly what a specific product's own configured
  // rate/term actually produce, without retyping them by hand.
  const [searchParams] = useSearchParams();
  const interestModelParam = searchParams.get("interest_model");
  const {
    register,
    watch,
    formState: { errors },
  } = useForm<LoanCalculatorInput>({
    resolver: zodResolver(loanCalculatorSchema),
    defaultValues: {
      principal: searchParams.get("principal") ?? "10000.00",
      interest_rate: searchParams.get("interest_rate") ?? "10.00",
      interest_model: isInterestModel(interestModelParam) ? interestModelParam : "flat",
      term_days: searchParams.get("term_days") ?? "30",
      installment_count: searchParams.get("installment_count") ?? "1",
    },
    mode: "onChange",
  });

  const values = watch();

  const calculate = useMutation({
    mutationFn: (input: LoanCalculatorInput) =>
      apiRequest<LoanCalculatorResponse>("/admin/loans/calculator", {
        method: "POST",
        body: {
          principal: input.principal,
          interest_rate: input.interest_rate,
          interest_model: input.interest_model,
          term_days: Number(input.term_days),
          installment_count: Number(input.installment_count),
        },
      }),
  });

  // Debounced live preview — recalculates a moment after the admin stops
  // typing, rather than on every keystroke or requiring an explicit submit.
  useEffect(() => {
    const result = loanCalculatorSchema.safeParse(values);
    if (!result.success) return;
    const timer = window.setTimeout(() => calculate.mutate(result.data), 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values.principal, values.interest_rate, values.interest_model, values.term_days, values.installment_count]);

  const productName = searchParams.get("product_name");

  return (
    <AppShell>
      <PageHeader
        title="Loan calculator"
        subtitle={
          productName
            ? `Previewing "${productName}"'s configured figures — nothing here is saved`
            : "Preview a repayment schedule for any figures — nothing here is saved"
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <form className="space-y-4" noValidate>
            <Field label="Principal (KES)" error={errors.principal?.message}>
              <TextInput type="number" step="0.01" min="0" {...register("principal")} />
            </Field>
            <Field label="Interest rate (%)" error={errors.interest_rate?.message}>
              <TextInput type="number" step="0.01" min="0" {...register("interest_rate")} />
            </Field>
            <Field label="Interest model" error={errors.interest_model?.message}>
              <Select {...register("interest_model")}>
                {Object.entries(INTEREST_MODEL_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Term (days)" error={errors.term_days?.message}>
              <TextInput type="number" step="1" min="1" {...register("term_days")} />
            </Field>
            <Field label="Number of installments" error={errors.installment_count?.message}>
              <TextInput type="number" step="1" min="1" {...register("installment_count")} />
            </Field>
          </form>
        </Card>

        <Card>
          {calculate.isError ? <Banner kind="error">{getErrorMessage(calculate.error)}</Banner> : null}
          {calculate.data ? (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3 text-sm">
                <div>
                  <p className="text-slate-500 dark:text-slate-400">Principal</p>
                  <p className="font-semibold text-slate-900 dark:text-slate-100">KES {calculate.data.principal}</p>
                </div>
                <div>
                  <p className="text-slate-500 dark:text-slate-400">Total interest</p>
                  <p className="font-semibold text-slate-900 dark:text-slate-100">KES {calculate.data.total_interest}</p>
                </div>
                <div>
                  <p className="text-slate-500 dark:text-slate-400">Total repayable</p>
                  <p className="font-semibold text-slate-900 dark:text-slate-100">KES {calculate.data.total_repayable}</p>
                </div>
              </div>
              <AmortizationTable schedule={calculate.data.schedule} />
            </div>
          ) : (
            <p className="text-sm text-slate-500 dark:text-slate-400">Enter figures on the left to see the breakdown.</p>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
