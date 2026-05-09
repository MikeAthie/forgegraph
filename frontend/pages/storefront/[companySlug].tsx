import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import { AlertCircle, ArrowLeft, Loader2, Lock, ShoppingBag } from "lucide-react";

import { Alert, AlertDescription, Badge, Button, Input, Spinner } from "@/components/ui";
import type { StorefrontProduct } from "@/lib/api";
import { storefrontApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const currency = new Intl.NumberFormat("es-MX", {
  style: "currency",
  currency: "MXN",
  maximumFractionDigits: 0,
});

export default function StorefrontPage() {
  const router = useRouter();
  const companySlug = typeof router.query.companySlug === "string" ? router.query.companySlug : "";
  const orderToken = typeof router.query.order === "string" ? router.query.order : "";
  const [products, setProducts] = useState<StorefrontProduct[]>([]);
  const [storefrontName, setStorefrontName] = useState("Storefront");
  const [orderStatus, setOrderStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [buyerAlias, setBuyerAlias] = useState("");
  const [error, setError] = useState<string | null>(null);

  const visibleProducts = useMemo(() => products.filter((product) => product.model), [products]);
  const availableCount = visibleProducts.filter((product) => !product.sold_out).length;

  useEffect(() => {
    if (!router.isReady) {
      return;
    }
    if (!companySlug) {
      return;
    }
    let cancelled = false;
    const loadProducts = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await storefrontApi.listProducts(companySlug);
        if (!cancelled) {
          setProducts(response.products);
          setStorefrontName(response.storefront_display_name || response.company_slug || "Storefront");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Storefront could not be loaded.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    void loadProducts();
    return () => {
      cancelled = true;
    };
  }, [companySlug, router.isReady]);

  useEffect(() => {
    if (!router.isReady || !companySlug || !orderToken) {
      setOrderStatus(null);
      return;
    }
    let cancelled = false;
    const loadOrder = async () => {
      try {
        const response = await storefrontApi.getOrderStatus(companySlug, orderToken);
        if (!cancelled) {
          setOrderStatus(
            `${response.order.reference}: payment ${response.order.payment_status.replaceAll("_", " ")}, fulfillment ${response.order.fulfillment_status.replaceAll("_", " ")}`,
          );
          if (response.storefront?.display_name) {
            setStorefrontName(response.storefront.display_name);
          }
        }
      } catch {
        if (!cancelled) {
          setOrderStatus("Order status is not available yet.");
        }
      }
    };
    void loadOrder();
    return () => {
      cancelled = true;
    };
  }, [companySlug, orderToken, router.isReady]);

  const startCheckout = async (product: StorefrontProduct) => {
    if (product.sold_out) {
      return;
    }
    setCheckoutLoading(product.id);
    setError(null);
    try {
      const result = await storefrontApi.createCheckoutSession(
        companySlug,
        {
          product_id: product.id,
          quantity: 1,
          buyer_alias: buyerAlias,
        },
        { idempotencyKey: idempotencyKey(`checkout:${product.id}`) },
      );
      window.location.href = result.checkout_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout could not be started.");
      setCheckoutLoading(null);
    }
  };

  return (
    <main className="min-h-screen bg-[#f7f4ef] text-slate-950">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 py-6 sm:px-6 lg:px-8">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-900/10 pb-4">
          <button
            type="button"
            onClick={() => router.back()}
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 transition hover:text-slate-950"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </button>
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <Lock className="h-4 w-4" />
            Secure Stripe checkout
          </div>
        </header>

        <section className="grid gap-6 py-6 lg:grid-cols-[20rem_1fr]">
          <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{storefrontName}</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Available Products</h1>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                One-piece reservations are held for 30 minutes while Stripe Checkout is open.
              </p>
            </div>
            {orderStatus ? (
              <Alert>
                <ShoppingBag className="h-4 w-4" />
                <AlertDescription>{orderStatus}</AlertDescription>
              </Alert>
            ) : null}
            <div className="grid grid-cols-2 gap-2">
              <Metric label="Available SKUs" value={availableCount} />
              <Metric label="Loaded SKUs" value={visibleProducts.length} />
            </div>
            <label className="block space-y-2">
              <span className="text-sm font-medium text-slate-700">Buyer alias</span>
              <Input
                value={buyerAlias}
                onChange={(event) => setBuyerAlias(event.target.value)}
                placeholder="Instagram handle or first name"
                className="bg-white"
              />
            </label>
            {error ? (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : null}
          </aside>

          <section className="min-w-0">
            {loading ? (
              <div className="flex min-h-[24rem] items-center justify-center">
                <Spinner size="lg" />
              </div>
            ) : null}
            {!loading && visibleProducts.length === 0 ? (
              <div className="border border-dashed border-slate-300 bg-white p-8 text-sm text-slate-600">
                No products are available yet.
              </div>
            ) : null}
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {visibleProducts.map((product) => (
                <ProductTile
                  key={product.id}
                  product={product}
                  loading={checkoutLoading === product.id}
                  onCheckout={() => startCheckout(product)}
                />
              ))}
            </div>
          </section>
        </section>
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="border border-slate-900/10 bg-white p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-950">{value}</p>
    </div>
  );
}

function ProductTile({
  product,
  loading,
  onCheckout,
}: {
  product: StorefrontProduct;
  loading: boolean;
  onCheckout: () => void;
}) {
  return (
    <article className="overflow-hidden border border-slate-900/10 bg-white">
      <div className="aspect-[4/3] bg-slate-100">
        {product.photo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={product.photo_url} alt={product.name || product.model} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-slate-100 px-6 text-center">
            <span className="text-lg font-semibold tracking-wide text-slate-700">{product.model}</span>
          </div>
        )}
      </div>
      <div className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-slate-950">{product.name || product.model}</h2>
            <p className="mt-1 text-sm text-slate-500">
              {product.color || "Frame"} · {product.sku}
            </p>
          </div>
          <Badge
            variant="outline"
            className={cn(
              "shrink-0",
              product.sold_out ? "border-slate-300 text-slate-500" : "border-emerald-700/25 text-emerald-700",
            )}
          >
            {product.sold_out ? "Sold out" : `${product.available_units} left`}
          </Badge>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-lg font-semibold text-slate-950">
            {currency.format(Number(product.price_mxn || 0))}
          </span>
          <Button type="button" onClick={onCheckout} disabled={product.sold_out || loading} className="min-w-28">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShoppingBag className="h-4 w-4" />}
            Checkout
          </Button>
        </div>
      </div>
    </article>
  );
}

function idempotencyKey(scope: string) {
  return `storefront:${scope}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
}
