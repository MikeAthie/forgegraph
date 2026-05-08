import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Brain,
  Clock3,
  CreditCard,
  ExternalLink,
  FileCheck2,
  Megaphone,
  PackageCheck,
  PackageOpen,
  PlayCircle,
  ReceiptText,
  RotateCcw,
  ShoppingBag,
  Truck,
} from "lucide-react";

import { Panel, SectionHeader, StatusBadge, formatDateTime } from "@/components/os/operations-ui";
import {
  Alert,
  AlertDescription,
  Button,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
  Textarea,
} from "@/components/ui";
import type {
  CommerceOperationsOverview,
  CommerceOrder,
  CompanyOperationObjective,
  CompanyOpsOverview,
  CompanySignal,
  InventoryOverview,
  InventoryProduct,
  InventoryReservation,
  ProcurementDraft,
  PublicationDraft,
} from "@/lib/api";
import { commerceApi, companyOpsApi, inventoryApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { showError, showSuccess } from "@/lib/toast";

type CommerceInventoryPanelProps = {
  companyId: string;
};

const channels = ["manual", "instagram", "whatsapp", "dm", "storefront", "other"] as const;

const currency = new Intl.NumberFormat("es-MX", {
  style: "currency",
  currency: "MXN",
  maximumFractionDigits: 0,
});

export function CommerceInventoryPanel({ companyId }: CommerceInventoryPanelProps) {
  const [overview, setOverview] = useState<InventoryOverview | null>(null);
  const [commerceOverview, setCommerceOverview] = useState<CommerceOperationsOverview | null>(null);
  const [companyOpsOverview, setCompanyOpsOverview] = useState<CompanyOpsOverview | null>(null);
  const [orders, setOrders] = useState<CommerceOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [selectedProductId, setSelectedProductId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [buyerAlias, setBuyerAlias] = useState("");
  const [channel, setChannel] = useState<(typeof channels)[number]>("manual");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const products = useMemo(() => overview?.products ?? [], [overview?.products]);
  const operationalReservations = useMemo(
    () =>
      (overview?.reservations ?? []).filter(
        (reservation) => reservation.status === "active" || reservation.order_shell !== null,
      ),
    [overview?.reservations],
  );
  const stockStateSummary = overview?.stock_state_summary ?? companyOpsOverview?.stock_state_summary;

  const loadInventory = async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextOverview, nextCommerceOverview, nextOrders, nextCompanyOpsOverview] = await Promise.all([
        inventoryApi.getOverview(companyId),
        commerceApi.getOverview(companyId),
        commerceApi.listOrders(companyId),
        companyOpsApi.getOverview(companyId),
      ]);
      setOverview(nextOverview);
      setCommerceOverview(nextCommerceOverview);
      setOrders(nextOrders.orders);
      setCompanyOpsOverview(nextCompanyOpsOverview);
      if (!selectedProductId && nextOverview.products[0]) {
        setSelectedProductId(nextOverview.products[0].id);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Inventory could not be loaded.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadInventory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  const createHold = async () => {
    if (!selectedProductId) {
      showError("Select a product before creating a hold.");
      return;
    }
    const parsedQuantity = Math.max(1, Number.parseInt(quantity, 10) || 1);
    setActionLoading("create");
    try {
      await inventoryApi.createReservation(
        {
          company_id: companyId,
          product_id: selectedProductId,
          quantity: parsedQuantity,
          buyer_alias: buyerAlias,
          channel,
          note,
          ttl_minutes: 30,
        },
        { idempotencyKey: idempotencyKey("reserve") },
      );
      setBuyerAlias("");
      setNote("");
      setQuantity("1");
      await loadInventory();
      showSuccess("Inventory hold created.");
    } catch (err) {
      showError(err instanceof Error ? err.message : "Inventory hold could not be created.");
    } finally {
      setActionLoading(null);
    }
  };

  const runReservationAction = async (
    reservation: InventoryReservation,
    action: "release" | "extend" | "order" | "checkout",
  ) => {
    setActionLoading(`${action}:${reservation.id}`);
    try {
      if (action === "release") {
        await inventoryApi.releaseReservation(
          reservation.id,
          { reason: "manual operator release" },
          { idempotencyKey: idempotencyKey(`release:${reservation.id}`) },
        );
        showSuccess("Hold released.");
      }
      if (action === "extend") {
        await inventoryApi.extendReservation(
          reservation.id,
          { minutes: 30 },
          { idempotencyKey: idempotencyKey(`extend:${reservation.id}`) },
        );
        showSuccess("Hold extended.");
      }
      if (action === "order") {
        await inventoryApi.createOrderShell(reservation.id, {
          idempotencyKey: idempotencyKey(`order:${reservation.id}`),
        });
        showSuccess("Order shell created.");
      }
      if (action === "checkout") {
        const result = await commerceApi.createCheckoutSession(
          {
            company_id: companyId,
            reservation_id: reservation.id,
          },
          { idempotencyKey: idempotencyKey(`checkout:${reservation.id}`) },
        );
        window.open(result.checkout_url, "_blank", "noopener,noreferrer");
        showSuccess("Checkout link created.");
      }
      await loadInventory();
    } catch (err) {
      showError(err instanceof Error ? err.message : "Inventory action failed.");
    } finally {
      setActionLoading(null);
    }
  };

  const expireDue = async () => {
    setActionLoading("expire-due");
    try {
      const result = await inventoryApi.expireDue(companyId, {
        idempotencyKey: idempotencyKey("expire-due"),
      });
      await loadInventory();
      showSuccess(`${result.expired_count} expired hold${result.expired_count === 1 ? "" : "s"} released.`);
    } catch (err) {
      showError(err instanceof Error ? err.message : "Expired holds could not be released.");
    } finally {
      setActionLoading(null);
    }
  };

  const launchCompanyOperation = async (operationType: string, sourceSignalId?: string | null) => {
    setActionLoading(`operation:${operationType}:${sourceSignalId ?? "manual"}`);
    try {
      const operation = await companyOpsApi.launchOperation(
        {
          company_id: companyId,
          operation_type: operationType,
          source_signal_id: sourceSignalId ?? undefined,
          run_type: "rehearsal",
        },
        { idempotencyKey: idempotencyKey(`company-operation:${operationType}:${sourceSignalId ?? "manual"}`) },
      );
      await loadInventory();
      showSuccess(`Operation ${operation.id.slice(0, 8)} created.`);
    } catch (err) {
      showError(err instanceof Error ? err.message : "Company operation could not be created.");
    } finally {
      setActionLoading(null);
    }
  };

  const qualifyCompanySignal = async (signal: CompanySignal) => {
    setActionLoading(`qualify:${signal.id}`);
    try {
      await companyOpsApi.qualifySignal(
        signal.id,
        { next_action: "Review and decide the next company move." },
        { idempotencyKey: idempotencyKey(`qualify:${signal.id}`) },
      );
      await loadInventory();
      showSuccess("Signal qualified.");
    } catch (err) {
      showError(err instanceof Error ? err.message : "Signal could not be qualified.");
    } finally {
      setActionLoading(null);
    }
  };

  const requestDraftApproval = async (
    draft: PublicationDraft | ProcurementDraft,
    kind: "publication" | "procurement",
  ) => {
    setActionLoading(`approval:${kind}:${draft.id}`);
    try {
      if (kind === "publication") {
        await companyOpsApi.requestPublicationApproval(
          draft.id,
          { note: "Review before any external publication." },
          { idempotencyKey: idempotencyKey(`publication-approval:${draft.id}`) },
        );
      } else {
        await companyOpsApi.requestProcurementApproval(
          draft.id,
          { note: "Review before any procurement commitment." },
          { idempotencyKey: idempotencyKey(`procurement-approval:${draft.id}`) },
        );
      }
      await loadInventory();
      showSuccess("Approval requested.");
    } catch (err) {
      showError(err instanceof Error ? err.message : "Approval could not be requested.");
    } finally {
      setActionLoading(null);
    }
  };

  const selectedProduct = products.find((product) => product.id === selectedProductId);
  const recentOrders = orders.slice(0, 8);
  const recommendedOperations = companyOpsOverview?.recommended_operations ?? [];
  const objectiveContracts = companyOpsOverview?.objective_contracts ?? [];

  return (
    <section className="mt-10 space-y-4" data-testid="commerce-inventory-panel">
      <SectionHeader
        eyebrow="Commerce"
        title="Operations Control Tower"
        description="Backend-owned stock, payments, fulfillment, and operator-visible order state."
      />

      {error ? (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-3 md:grid-cols-4">
        <InventoryMetric
          icon={<PackageOpen className="h-4 w-4" />}
          label="Total"
          value={overview?.summary.total_units ?? 0}
        />
        <InventoryMetric
          icon={<PackageCheck className="h-4 w-4" />}
          label="Available"
          value={overview?.summary.available_units ?? 0}
          tone="emerald"
        />
        <InventoryMetric
          icon={<Clock3 className="h-4 w-4" />}
          label="Held"
          value={overview?.summary.held_units ?? 0}
          tone="amber"
        />
        <InventoryMetric
          icon={<AlertTriangle className="h-4 w-4" />}
          label="Low stock"
          value={stockStateSummary?.low_stock_count ?? overview?.summary.low_stock_products ?? 0}
          tone="rose"
        />
      </div>

      <Panel
        title="Stock States"
        description={
          stockStateSummary?.definition_used ?? "Canonical stock semantics will appear after inventory loads."
        }
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <InventoryMetric
            icon={<PackageCheck className="h-4 w-4" />}
            label="Active"
            value={stockStateSummary?.active_count ?? 0}
            tone="emerald"
          />
          <InventoryMetric
            icon={<AlertTriangle className="h-4 w-4" />}
            label="Low"
            value={stockStateSummary?.low_stock_count ?? 0}
            tone="amber"
          />
          <InventoryMetric
            icon={<Clock3 className="h-4 w-4" />}
            label="Last piece"
            value={stockStateSummary?.last_piece_count ?? overview?.summary.last_piece_products ?? 0}
            tone="rose"
          />
          <InventoryMetric
            icon={<PackageOpen className="h-4 w-4" />}
            label="Sold out"
            value={stockStateSummary?.sold_out_count ?? overview?.summary.sold_out_products ?? 0}
          />
        </div>
      </Panel>

      <div className="grid gap-3 md:grid-cols-5">
        <InventoryMetric
          icon={<CreditCard className="h-4 w-4" />}
          label="Paid"
          value={commerceOverview?.summary.orders_paid ?? 0}
          tone="emerald"
        />
        <InventoryMetric
          icon={<Clock3 className="h-4 w-4" />}
          label="Pending"
          value={commerceOverview?.summary.orders_pending_payment ?? 0}
          tone="amber"
        />
        <InventoryMetric
          icon={<AlertTriangle className="h-4 w-4" />}
          label="Stuck"
          value={commerceOverview?.summary.orders_stuck ?? 0}
          tone="rose"
        />
        <InventoryMetric
          icon={<Truck className="h-4 w-4" />}
          label="To fulfill"
          value={
            (commerceOverview?.summary.fulfillment_pending ?? 0) +
            (commerceOverview?.summary.fulfillment_ready ?? 0) +
            (commerceOverview?.summary.fulfillment_blocked ?? 0)
          }
        />
        <InventoryMetric
          icon={<ReceiptText className="h-4 w-4" />}
          label="Sales MXN"
          value={Number(commerceOverview?.summary.cash_sales_mxn ?? 0)}
        />
      </div>

      <div className="grid gap-3 md:grid-cols-5">
        <InventoryMetric
          icon={<Brain className="h-4 w-4" />}
          label="Signals"
          value={(companyOpsOverview?.summary.signals_new ?? 0) + (companyOpsOverview?.summary.signals_qualified ?? 0)}
        />
        <InventoryMetric
          icon={<ShoppingBag className="h-4 w-4" />}
          label="Opportunities"
          value={companyOpsOverview?.summary.opportunities_open ?? 0}
          tone="emerald"
        />
        <InventoryMetric
          icon={<Megaphone className="h-4 w-4" />}
          label="Drafts"
          value={companyOpsOverview?.summary.publication_drafts ?? 0}
          tone="amber"
        />
        <InventoryMetric
          icon={<FileCheck2 className="h-4 w-4" />}
          label="Procurement"
          value={companyOpsOverview?.summary.procurement_drafts ?? 0}
        />
        <InventoryMetric
          icon={<AlertTriangle className="h-4 w-4" />}
          label="Ops stuck"
          value={companyOpsOverview?.summary.stuck_orders ?? 0}
          tone="rose"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.35fr_0.9fr]">
        <Panel
          title="Products"
          description={`${products.length} SKU${products.length === 1 ? "" : "s"} loaded`}
          className="min-h-[28rem]"
          action={
            <Button variant="outline" size="sm" onClick={loadInventory} disabled={loading}>
              {loading ? <Spinner size="sm" /> : <RotateCcw className="h-4 w-4" />}
              Refresh
            </Button>
          }
        >
          <div className="grid gap-2">
            {products.length === 0 && !loading ? (
              <div className="rounded-xl border border-dashed border-slate-300 p-6 text-sm text-slate-500 dark:border-white/15 dark:text-slate-400">
                No inventory has been imported yet.
              </div>
            ) : null}
            {products.map((product) => (
              <ProductRow
                key={product.id}
                product={product}
                selected={product.id === selectedProductId}
                onSelect={() => setSelectedProductId(product.id)}
              />
            ))}
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel title="Create Hold">
            <div className="space-y-3">
              <Select value={selectedProductId} onValueChange={setSelectedProductId}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select SKU" />
                </SelectTrigger>
                <SelectContent>
                  {products.map((product) => (
                    <SelectItem key={product.id} value={product.id}>
                      {product.model} · {product.available_units} available
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="grid grid-cols-[5.5rem_1fr] gap-2">
                <Input
                  aria-label="Quantity"
                  type="number"
                  min={1}
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                />
                <Input
                  aria-label="Buyer alias"
                  value={buyerAlias}
                  onChange={(event) => setBuyerAlias(event.target.value)}
                  placeholder="Buyer alias"
                />
              </div>
              <Select value={channel} onValueChange={(value) => setChannel(value as typeof channel)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {channels.map((item) => (
                    <SelectItem key={item} value={item}>
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Textarea
                aria-label="Hold note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Operator note"
                rows={3}
              />
              <Button className="w-full" onClick={createHold} disabled={!selectedProduct || actionLoading === "create"}>
                {actionLoading === "create" ? <Spinner size="sm" /> : <Clock3 className="h-4 w-4" />}
                Hold 30m
              </Button>
            </div>
          </Panel>

          <Panel
            title="Holds And Orders"
            action={
              <Button variant="outline" size="sm" onClick={expireDue} disabled={actionLoading === "expire-due"}>
                {actionLoading === "expire-due" ? <Spinner size="sm" /> : <Clock3 className="h-4 w-4" />}
                Expire Due
              </Button>
            }
          >
            <div className="space-y-3">
              {operationalReservations.length === 0 ? (
                <p className="text-sm text-slate-500 dark:text-slate-400">No active holds or payment orders.</p>
              ) : null}
              {operationalReservations.map((reservation) => (
                <ReservationRow
                  key={reservation.id}
                  reservation={reservation}
                  actionLoading={actionLoading}
                  onAction={runReservationAction}
                />
              ))}
            </div>
          </Panel>
        </div>
      </div>

      <Panel title="Orders And Fulfillment" action={<Truck className="h-4 w-4 text-slate-500" />}>
        <div className="grid gap-2">
          {recentOrders.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">No commerce orders yet.</p>
          ) : null}
          {recentOrders.map((order) => (
            <OrderRow
              key={order.id}
              order={order}
              actionLoading={actionLoading}
              onAction={async (nextAction) => {
                setActionLoading(`${nextAction}:${order.id}`);
                try {
                  await runFulfillmentAction(order, nextAction);
                  await loadInventory();
                } catch (err) {
                  showError(err instanceof Error ? err.message : "Fulfillment action failed.");
                } finally {
                  setActionLoading(null);
                }
              }}
            />
          ))}
        </div>
      </Panel>

      <Panel title="Operating Loop" action={<Brain className="h-4 w-4 text-slate-500" />}>
        <div className="mb-4 rounded-xl border border-slate-900/10 bg-slate-50/80 p-4 dark:border-white/10 dark:bg-white/5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Objective Contract</p>
              <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">
                Sell-through learning is the scorecard: each operation records the goal, target signal, integrity gates,
                miss analysis, and next decision.
              </p>
            </div>
            <StatusBadge status="rehearsal" label="Learning + integrity" />
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">Recommended Operations</h3>
            {recommendedOperations.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">No operating-loop recommendations yet.</p>
            ) : null}
            {recommendedOperations.map((operation) => (
              <div
                key={operation.operation_type}
                className="grid gap-3 rounded-xl border border-slate-900/10 bg-white/80 p-3 dark:border-white/10 dark:bg-white/5 md:grid-cols-[1fr_auto]"
              >
                <div>
                  <p className="font-medium text-slate-950 dark:text-slate-50">{operation.label}</p>
                  <p className="text-sm text-slate-500 dark:text-slate-400">{operation.reason}</p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => launchCompanyOperation(operation.operation_type)}
                  disabled={actionLoading === `operation:${operation.operation_type}:manual`}
                >
                  {actionLoading === `operation:${operation.operation_type}:manual` ? (
                    <Spinner size="sm" />
                  ) : (
                    <PlayCircle className="h-4 w-4" />
                  )}
                  Launch
                </Button>
              </div>
            ))}
          </div>

          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">Signals</h3>
            {(companyOpsOverview?.signals ?? []).slice(0, 5).map((signal) => (
              <SignalRow
                key={signal.id}
                signal={signal}
                actionLoading={actionLoading}
                onQualify={qualifyCompanySignal}
                onLaunch={launchCompanyOperation}
              />
            ))}
            {companyOpsOverview && companyOpsOverview.signals.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">No company signals captured yet.</p>
            ) : null}
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <DraftColumn
            title="Publication Drafts"
            drafts={companyOpsOverview?.publication_drafts ?? []}
            actionLoading={actionLoading}
            onRequestApproval={(draft) => requestDraftApproval(draft, "publication")}
          />
          <DraftColumn
            title="Procurement Drafts"
            drafts={companyOpsOverview?.procurement_drafts ?? []}
            actionLoading={actionLoading}
            onRequestApproval={(draft) => requestDraftApproval(draft, "procurement")}
          />
        </div>

        <div className="mt-4">
          <h3 className="mb-2 text-sm font-semibold text-slate-950 dark:text-slate-50">Objective Reviews</h3>
          <div className="grid gap-2">
            {objectiveContracts.slice(0, 4).map((objective) => (
              <ObjectiveContractRow key={objective.id} objective={objective} />
            ))}
            {objectiveContracts.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                No operation objective contracts recorded yet.
              </p>
            ) : null}
          </div>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-semibold text-slate-950 dark:text-slate-50">Opportunities</h3>
            <div className="grid gap-2">
              {(companyOpsOverview?.opportunities ?? []).slice(0, 5).map((opportunity) => (
                <div
                  key={opportunity.id}
                  className="rounded-xl border border-slate-900/10 bg-white/80 p-3 dark:border-white/10 dark:bg-white/5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-medium text-slate-950 dark:text-slate-50">{opportunity.title}</p>
                    <StatusBadge status={opportunity.status} label={opportunity.status.replaceAll("_", " ")} />
                  </div>
                  <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                    {opportunity.next_action || opportunity.summary || "No next action recorded."}
                  </p>
                </div>
              ))}
              {companyOpsOverview && companyOpsOverview.opportunities.length === 0 ? (
                <p className="text-sm text-slate-500 dark:text-slate-400">No qualified opportunities yet.</p>
              ) : null}
            </div>
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold text-slate-950 dark:text-slate-50">Decisions And Policies</h3>
            <div className="grid gap-2">
              {(companyOpsOverview?.recent_decisions ?? []).slice(0, 3).map((decision) => (
                <div
                  key={decision.id}
                  className="rounded-xl border border-slate-900/10 bg-white/80 p-3 dark:border-white/10 dark:bg-white/5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-medium text-slate-950 dark:text-slate-50">
                      {decision.decision_type.replaceAll("_", " ")}
                    </p>
                    <StatusBadge status={decision.status} />
                  </div>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    {decision.requested_at ? formatDateTime(decision.requested_at) : "No timestamp"}
                  </p>
                </div>
              ))}
              {(companyOpsOverview?.policies ?? []).slice(0, 3).map((policy) => (
                <div
                  key={policy.id}
                  className="rounded-xl border border-slate-900/10 bg-white/80 p-3 dark:border-white/10 dark:bg-white/5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-medium text-slate-950 dark:text-slate-50">{policy.title}</p>
                    <StatusBadge status={policy.status} />
                  </div>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    Confidence {Math.round(policy.confidence * 100)}%
                  </p>
                </div>
              ))}
              {companyOpsOverview &&
              companyOpsOverview.recent_decisions.length === 0 &&
              companyOpsOverview.policies.length === 0 ? (
                <p className="text-sm text-slate-500 dark:text-slate-400">No decisions or policies recorded yet.</p>
              ) : null}
            </div>
          </div>
        </div>
      </Panel>

      <Panel title="Inventory Timeline" action={<ReceiptText className="h-4 w-4 text-slate-500" />}>
        <div className="grid gap-2">
          {(overview?.events ?? []).slice(0, 8).map((event) => (
            <div
              key={event.id}
              className="grid gap-2 rounded-xl border border-slate-900/10 bg-white/80 p-3 text-sm dark:border-white/10 dark:bg-white/5 md:grid-cols-[8rem_1fr_auto]"
            >
              <StatusBadge status={event.event_type} />
              <span className="text-slate-700 dark:text-slate-200">{event.message}</span>
              <span className="text-xs text-slate-500 dark:text-slate-400">{formatDateTime(event.created_at)}</span>
            </div>
          ))}
          {overview && overview.events.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">No inventory events yet.</p>
          ) : null}
        </div>
      </Panel>
    </section>
  );
}

async function runFulfillmentAction(order: CommerceOrder, action: "mark-ready" | "block" | "ship" | "deliver") {
  const key = idempotencyKey(`fulfillment:${action}:${order.id}`);
  if (action === "mark-ready") {
    await commerceApi.markFulfillmentReady(order.id, { note: "ready for fulfillment" }, { idempotencyKey: key });
  }
  if (action === "block") {
    await commerceApi.blockFulfillment(
      order.id,
      { reason_code: "operator_review", note: "blocked for operator review" },
      { idempotencyKey: key },
    );
  }
  if (action === "ship") {
    await commerceApi.shipFulfillment(order.id, { note: "marked shipped" }, { idempotencyKey: key });
  }
  if (action === "deliver") {
    await commerceApi.deliverFulfillment(order.id, { note: "marked delivered" }, { idempotencyKey: key });
  }
}

function InventoryMetric({
  icon,
  label,
  value,
  tone = "slate",
}: {
  icon: ReactNode;
  label: string;
  value: number;
  tone?: "slate" | "emerald" | "amber" | "rose";
}) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-white/85 p-4 shadow-[0_18px_52px_-42px_rgba(15,23,42,0.55)] dark:bg-white/5",
        tone === "slate" && "border-slate-900/10 text-slate-700 dark:border-white/10 dark:text-slate-200",
        tone === "emerald" && "border-emerald-700/20 text-emerald-800 dark:border-emerald-300/20 dark:text-emerald-100",
        tone === "amber" && "border-amber-700/20 text-amber-800 dark:border-amber-300/20 dark:text-amber-100",
        tone === "rose" && "border-rose-700/20 text-rose-800 dark:border-rose-300/20 dark:text-rose-100",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
          {label}
        </span>
        {icon}
      </div>
      <p className="mt-3 text-2xl font-semibold text-slate-950 dark:text-slate-50">{value}</p>
    </div>
  );
}

function ProductRow({
  product,
  selected,
  onSelect,
}: {
  product: InventoryProduct;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "grid w-full gap-3 rounded-xl border p-3 text-left transition hover:border-slate-400/70 dark:hover:border-white/25 md:grid-cols-[1fr_auto]",
        selected
          ? "border-slate-900/25 bg-slate-100/80 dark:border-white/30 dark:bg-white/10"
          : "border-slate-900/10 bg-white/70 dark:border-white/10 dark:bg-white/5",
      )}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium text-slate-950 dark:text-slate-50">{product.model}</p>
          <span className="text-xs text-slate-500 dark:text-slate-400">{product.sku}</span>
          {product.anchor_model ? <StatusBadge status="anchor" label="Anchor" /> : null}
          {product.scarcity_tag ? <StatusBadge status={product.scarcity_tag} label={product.scarcity_tag} /> : null}
          {product.stock_state ? (
            <StatusBadge status={product.stock_state} label={product.stock_state.replaceAll("_", " ")} />
          ) : null}
        </div>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {product.color || "No color"} · {currency.format(Number(product.price_mxn || 0))}
        </p>
      </div>
      <div className="grid grid-cols-3 gap-2 text-right text-xs">
        <CountPill label="Avail" value={product.available_units} />
        <CountPill label="Held" value={product.held_units} />
        <CountPill label="Total" value={product.total_units} />
      </div>
    </button>
  );
}

function CountPill({ label, value }: { label: string; value: number }) {
  return (
    <span className="rounded-lg border border-slate-900/10 px-2 py-1 dark:border-white/10">
      <span className="block text-[10px] uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">{label}</span>
      <span className="text-sm font-semibold text-slate-950 dark:text-slate-50">{value}</span>
    </span>
  );
}

function ReservationRow({
  reservation,
  actionLoading,
  onAction,
}: {
  reservation: InventoryReservation;
  actionLoading: string | null;
  onAction: (reservation: InventoryReservation, action: "release" | "extend" | "order" | "checkout") => void;
}) {
  const payment = reservation.order_shell?.commerce_payment;
  const checkoutUrl = reservation.order_shell?.stripe_checkout_url || payment?.checkout_url || "";
  const canMutateHold = reservation.status === "active";

  return (
    <div className="rounded-xl border border-slate-900/10 bg-white/75 p-3 dark:border-white/10 dark:bg-white/5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium text-slate-950 dark:text-slate-50">
            {reservation.product_model} x{reservation.quantity}
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {reservation.buyer_alias || "No alias"} · expires {formatDateTime(reservation.expires_at)}
          </p>
        </div>
        <StatusBadge status={reservation.status} />
      </div>
      {reservation.order_shell ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
          <StatusBadge
            status={reservation.order_shell.status}
            label={reservation.order_shell.status.replaceAll("_", " ")}
          />
          {payment ? (
            <StatusBadge status={payment.status} label={`payment ${payment.status.replaceAll("_", " ")}`} />
          ) : null}
          <span>{reservation.order_shell.order_number}</span>
        </div>
      ) : null}
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {canMutateHold ? (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onAction(reservation, "extend")}
              disabled={actionLoading === `extend:${reservation.id}`}
            >
              Extend
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onAction(reservation, "checkout")}
              disabled={actionLoading === `checkout:${reservation.id}`}
            >
              {actionLoading === `checkout:${reservation.id}` ? (
                <Spinner size="sm" />
              ) : (
                <CreditCard className="h-4 w-4" />
              )}
              Checkout
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onAction(reservation, "release")}
              disabled={actionLoading === `release:${reservation.id}`}
            >
              Release
            </Button>
          </>
        ) : null}
        {checkoutUrl && reservation.order_shell?.status === "pending_payment" ? (
          <Button variant="outline" size="sm" onClick={() => window.open(checkoutUrl, "_blank", "noopener,noreferrer")}>
            <ExternalLink className="h-4 w-4" />
            Open Link
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function OrderRow({
  order,
  actionLoading,
  onAction,
}: {
  order: CommerceOrder;
  actionLoading: string | null;
  onAction: (action: "mark-ready" | "block" | "ship" | "deliver") => void;
}) {
  const fulfillmentStatus = order.fulfillment?.status ?? "not_ready";
  const paymentStatus = order.payment?.status ?? "pending";
  const isLoading = (action: string) => actionLoading === `${action}:${order.id}`;
  return (
    <div className="grid gap-3 rounded-xl border border-slate-900/10 bg-white/80 p-3 dark:border-white/10 dark:bg-white/5 lg:grid-cols-[1fr_auto]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium text-slate-950 dark:text-slate-50">
            {order.public_reference || order.order_number}
          </p>
          <StatusBadge status={order.status} label={order.status.replaceAll("_", " ")} />
          <StatusBadge status={paymentStatus} label={`payment ${paymentStatus.replaceAll("_", " ")}`} />
          <StatusBadge status={fulfillmentStatus} label={`fulfillment ${fulfillmentStatus.replaceAll("_", " ")}`} />
        </div>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {order.product.model} x{order.quantity} · {order.buyer_alias || order.channel || "buyer"}
        </p>
        {order.fulfillment?.operator_note ? (
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{order.fulfillment.operator_note}</p>
        ) : null}
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:w-[24rem]">
        {fulfillmentStatus === "pending" || fulfillmentStatus === "blocked" ? (
          <Button variant="outline" size="sm" onClick={() => onAction("mark-ready")} disabled={isLoading("mark-ready")}>
            {isLoading("mark-ready") ? <Spinner size="sm" /> : null}
            Ready
          </Button>
        ) : null}
        {fulfillmentStatus === "pending" || fulfillmentStatus === "ready" ? (
          <Button variant="outline" size="sm" onClick={() => onAction("block")} disabled={isLoading("block")}>
            Block
          </Button>
        ) : null}
        {fulfillmentStatus === "ready" ? (
          <Button variant="outline" size="sm" onClick={() => onAction("ship")} disabled={isLoading("ship")}>
            <Truck className="h-4 w-4" />
            Ship
          </Button>
        ) : null}
        {fulfillmentStatus === "shipped" ? (
          <Button variant="outline" size="sm" onClick={() => onAction("deliver")} disabled={isLoading("deliver")}>
            Deliver
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function SignalRow({
  signal,
  actionLoading,
  onQualify,
  onLaunch,
}: {
  signal: CompanySignal;
  actionLoading: string | null;
  onQualify: (signal: CompanySignal) => void;
  onLaunch: (operationType: string, sourceSignalId?: string | null) => void;
}) {
  const launchType =
    signal.signal_type === "stockout"
      ? "sold_out_demand_capture"
      : signal.signal_type === "fulfillment_issue"
        ? "fulfillment_exception_review"
        : signal.signal_type === "paid_order"
          ? "paid_order_follow_up"
          : "daily_operating_brief";

  return (
    <div className="rounded-xl border border-slate-900/10 bg-white/80 p-3 dark:border-white/10 dark:bg-white/5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium text-slate-950 dark:text-slate-50">{signal.title}</p>
            <StatusBadge status={signal.signal_type} label={signal.signal_type.replaceAll("_", " ")} />
            <StatusBadge status={signal.status} />
          </div>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {signal.summary || signal.channel || "No summary yet."}
          </p>
        </div>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {signal.status === "new" ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onQualify(signal)}
            disabled={actionLoading === `qualify:${signal.id}`}
          >
            {actionLoading === `qualify:${signal.id}` ? <Spinner size="sm" /> : <FileCheck2 className="h-4 w-4" />}
            Qualify
          </Button>
        ) : null}
        <Button
          variant="outline"
          size="sm"
          onClick={() => onLaunch(launchType, signal.id)}
          disabled={actionLoading === `operation:${launchType}:${signal.id}`}
        >
          {actionLoading === `operation:${launchType}:${signal.id}` ? (
            <Spinner size="sm" />
          ) : (
            <PlayCircle className="h-4 w-4" />
          )}
          Launch
        </Button>
      </div>
    </div>
  );
}

function ObjectiveContractRow({ objective }: { objective: CompanyOperationObjective }) {
  const scoreLabel = objective.success_score === null ? "pending score" : `${objective.success_score}/100`;
  const integrityGateCount =
    objective.integrity_gates && typeof objective.integrity_gates === "object"
      ? Object.keys(objective.integrity_gates).length
      : 0;
  return (
    <div className="rounded-xl border border-slate-900/10 bg-white/80 p-3 dark:border-white/10 dark:bg-white/5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium text-slate-950 dark:text-slate-50">
              {objective.run_goal || "Operation objective"}
            </p>
            <StatusBadge status={objective.run_type} label={objective.run_type.replaceAll("_", " ")} />
            <StatusBadge status={objective.status} />
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
            {objective.target_signal || objective.hypothesis || "No target signal recorded."}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{scoreLabel}</p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{integrityGateCount} integrity gates</p>
        </div>
      </div>
      {objective.miss_analysis || objective.next_decision ? (
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <p className="rounded-lg bg-slate-50 p-2 text-xs leading-5 text-slate-600 dark:bg-white/5 dark:text-slate-300">
            {objective.miss_analysis || "No miss analysis recorded."}
          </p>
          <p className="rounded-lg bg-slate-50 p-2 text-xs leading-5 text-slate-600 dark:bg-white/5 dark:text-slate-300">
            {objective.next_decision || "No next decision recorded."}
          </p>
        </div>
      ) : null}
    </div>
  );
}

function DraftColumn({
  title,
  drafts,
  actionLoading,
  onRequestApproval,
}: {
  title: string;
  drafts: Array<PublicationDraft | ProcurementDraft>;
  actionLoading: string | null;
  onRequestApproval: (draft: PublicationDraft | ProcurementDraft) => void;
}) {
  const kind = title.toLowerCase().includes("publication") ? "publication" : "procurement";
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-slate-950 dark:text-slate-50">{title}</h3>
      <div className="grid gap-2">
        {drafts.slice(0, 5).map((draft) => (
          <div
            key={draft.id}
            className="grid gap-3 rounded-xl border border-slate-900/10 bg-white/80 p-3 dark:border-white/10 dark:bg-white/5 md:grid-cols-[1fr_auto]"
          >
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium text-slate-950 dark:text-slate-50">{draft.title}</p>
                <StatusBadge status={draft.status} label={draft.status.replaceAll("_", " ")} />
              </div>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                {"body" in draft
                  ? draft.channel || draft.call_to_action || "Draft content"
                  : draft.rationale || "Draft proposal"}
              </p>
            </div>
            {draft.status === "draft" ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onRequestApproval(draft)}
                disabled={actionLoading === `approval:${kind}:${draft.id}`}
              >
                {actionLoading === `approval:${kind}:${draft.id}` ? (
                  <Spinner size="sm" />
                ) : (
                  <FileCheck2 className="h-4 w-4" />
                )}
                Review
              </Button>
            ) : null}
          </div>
        ))}
        {drafts.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">No {title.toLowerCase()} recorded yet.</p>
        ) : null}
      </div>
    </div>
  );
}

function idempotencyKey(scope: string) {
  return `inventory:${scope}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
}
