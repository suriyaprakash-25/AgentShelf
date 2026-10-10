import { useEffect, useMemo, useState } from "react";
import { AgStudio, AgStudioProvider, createWidgets } from "ag-studio-react";
import {
  AgStudioAiModule,
  AgStudioLicenseManager,
  studioTheme,
  createAiHarness,
  directLlmRunner,
  type AgDefaultRegistry,
  type AgDefaultWidgetDefinition,
  type AgBaseWidgetDefinition,
  type AgWidgetData,
  type AgWidgetDataFormat,
  type AgReportState,
  type AgLlmAdapter,
  type AgLlmResponse,
  type AgAiEvent,
} from "ag-studio";
import { api } from "./api";

type Summary = {
  currency: string;
  products: { status: string; count: number; available_stock: number }[];
  orders: { status: string; count: number; gross_amount_minor: number }[];
  notice: string;
};
type CardData = { type: "shop-summary" } & AgWidgetData<
  Record<string, never>,
  AgWidgetDataFormat<Record<string, never>>
>;
type CardDefinition = AgBaseWidgetDefinition<"shop-summary", CardData>;
interface ShopRegistry extends Omit<AgDefaultRegistry, "widgets"> {
  widgets: readonly (AgDefaultWidgetDefinition | CardDefinition)[];
}
const licence = import.meta.env.VITE_AG_STUDIO_LICENSE_KEY;
if (licence) AgStudioLicenseManager.setLicenseKey(licence);
const theme = studioTheme.withParams({
  accentColor: "#45533b",
  backgroundColor: "#faf8f3",
  foregroundColor: "#252b22",
  studioCanvasBackgroundColor: "#faf8f3",
  studioWidgetBackgroundColor: "#fffdf7",
});
const initialState: AgReportState<ShopRegistry> = {
  pages: [
    {
      id: "shop",
      widgets: {
        summary: {
          type: "shop-summary",
          dataMapping: {},
          format: { title: { text: "Your shop at a glance" } },
        },
      },
      widgetLayout: { summary: { xTrack: 0, yTrack: 0, xSpan: 24, ySpan: 24 } },
    },
  ],
  selectedPageId: "shop",
  panels: {
    filters: { collapsed: true },
    data: { collapsed: true },
    edit: { collapsed: true },
    compose: { collapsed: true },
  },
};

export default function AnalyticsStudio({ csrf }: { csrf: string }) {
  const [facts, setFacts] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api<Summary>("/api/me/analytics", undefined, controller.signal)
      .then(setFacts)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, []);
  const widgets = useMemo(
    () =>
      createWidgets<ShopRegistry>({
        additionalTypes: [
          {
            id: "shop-summary",
            label: "Shop summary",
            form: (p) => p.createDefaults({ dataMappingItems: [] }),
            comp: () => (
              <div className="studio-summary">
                <h3>Catalog and orders</h3>
                <p>
                  Available stock:{" "}
                  {facts?.products.reduce((n, p) => n + p.available_stock, 0) ||
                    0}
                </p>
                {facts?.products.map((p) => (
                  <p key={p.status}>
                    {p.count} {p.status} products
                  </p>
                ))}
                {facts?.orders.map((o) => (
                  <p key={o.status}>
                    {o.count} {o.status} orders ·{" "}
                    {(o.gross_amount_minor / 100).toFixed(2)} USD gross
                  </p>
                ))}
                <p>{facts?.notice}</p>
              </div>
            ),
            defaultSize: { width: 700, height: 350 },
            minSize: { width: 250, height: 200 },
          },
        ],
      }),
    [facts],
  );
  const ai = useMemo(() => {
    const adapter: AgLlmAdapter = {
      executeTurn(request, options) {
        const latest = [...request.input]
          .reverse()
          .find((item) => item.type === "message" && item.role === "user");
        const message =
          latest?.type === "message"
            ? latest.content
                .filter((part) => part.type === "text")
                .map((part) => (part.type === "text" ? part.text : ""))
                .join(" ")
            : "Summarize my shop.";
        const complete: Promise<AgLlmResponse> = api<{ text: string }>(
          "/api/me/analytics/chat",
          { message },
          options?.signal,
          { csrf },
        ).then(({ text }) => ({
          id: crypto.randomUUID(),
          createdAt: Date.now(),
          status: "completed",
          output: [
            {
              id: crypto.randomUUID(),
              kind: "output",
              type: "message",
              role: "assistant",
              status: "completed",
              content: [{ type: "text", text, annotations: [] }],
            },
          ],
        }));
        return {
          complete,
          stream: {
            [Symbol.asyncIterator]:
              async function* (): AsyncGenerator<AgAiEvent> {
                const result = await complete;
                const item = result.output[0];
                if (item.type === "message") {
                  yield {
                    type: "TEXT_MESSAGE_START",
                    messageId: item.id,
                    role: "assistant",
                  };
                  yield {
                    type: "TEXT_MESSAGE_CONTENT",
                    messageId: item.id,
                    delta: item.content
                      .map((p) => (p.type === "text" ? p.text : ""))
                      .join(""),
                  };
                  yield { type: "TEXT_MESSAGE_END", messageId: item.id };
                }
              },
          },
        };
      },
    };
    return ({
      api: studioApi,
    }: {
      api: Parameters<typeof createAiHarness>[0];
    }) =>
      createAiHarness(studioApi, () => ({
        agents: [
          directLlmRunner({
            id: "shop-analyst",
            name: "Shop analyst",
            adapter,
            instructions: () =>
              "Summarize the seller's aggregate facts. No business changes.",
            tools: () => [],
          }),
        ],
        primary: "shop-analyst",
        promptStarters: [
          {
            label: "Summarize my shop",
            prompt: "Summarize my catalog and order totals.",
          },
        ],
      }));
  }, [csrf]);
  if (error) return <p role="alert">{error}</p>;
  if (!facts) return <p role="status">Loading shop analytics…</p>;
  if (!import.meta.env.DEV && !licence)
    return (
      <p>
        Analytics Studio requires a deployment licence. Your catalog and orders
        remain available below.
      </p>
    );
  return (
    <section>
      <h2>Shop analytics</h2>
      <p>
        Live shop totals. The analyst can explain aggregate figures; edit
        products and fulfil orders using the controls below.
      </p>
      <div className="analytics-studio">
        <AgStudioProvider modules={[AgStudioAiModule]}>
          <AgStudio<ShopRegistry>
            data={{
              sources: [
                { id: "products", data: facts.products },
                { id: "orders", data: facts.orders },
              ],
            }}
            mode="edit"
            initialState={initialState}
            widgets={widgets}
            theme={theme}
            ai={ai}
          />
        </AgStudioProvider>
      </div>
    </section>
  );
}
