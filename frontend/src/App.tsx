import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Activity, ArrowDownToLine, ArrowUpFromLine, Check, ChevronRight, CircleHelp, ExternalLink, FileClock, LoaderCircle, Pin, Plus, RefreshCw, RotateCcw, Search, Trash2, X } from "lucide-react";
import { CountryMultiSelect } from "./CountrySelect";
import SearchableSelect from "./SearchableSelect";

type Entity = { id: number; name: string; [key: string]: unknown };
type Offer = { offer_id: number; offer_name: string; share: number; pinned: boolean; present: boolean; state: string; dirty: boolean };
type Stream = { stream_id: number; campaign_id: number; name: string; position: number; offers: Offer[]; dirty: boolean; has_offer_flow: boolean };
type Campaign = { id: number; name: string; alias?: string; state?: string };
type Catalogs = { offers: Entity[]; domains: Entity[]; groups: Entity[]; traffic_sources: Entity[] };
type HistoryItem = { id: number; campaign_id: number | null; stream_id: number | null; action: string; status: string; details: string; created_at: string };
type HistoryFilters = { campaign_id: string; action: string; status: string; search: string; date_from: string; date_to: string };
type AppRoute = "campaigns" | "history";

const blankCatalogs: Catalogs = { offers: [], domains: [], groups: [], traffic_sources: [] };
const initialForm = { name: "", country_codes: ["AU"], offer_id: "", domain_id: "1813", group_id: "10332", traffic_source_id: "836" };
const CAMPAIGN_BATCH_SIZE = 10;
const HISTORY_BATCH_SIZE = 50;

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail || `Ошибка запроса (${response.status})`);
  return body as T;
}

function routeFromPath(path: string): AppRoute {
  return path.startsWith("/history") ? "history" : "campaigns";
}

function App() {
  const [route, setRoute] = useState<AppRoute>(() => routeFromPath(window.location.pathname));
  const [catalogs, setCatalogs] = useState<Catalogs>(blankCatalogs);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignsLoading, setCampaignsLoading] = useState(false);
  const [campaignsHaveMore, setCampaignsHaveMore] = useState(true);
  const [selected, setSelected] = useState<Campaign | null>(null);
  const [showCreator, setShowCreator] = useState(true);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [pageError, setPageError] = useState("");
  const [toast, setToast] = useState("");
  const [busy, setBusy] = useState(false);
  const [offerSearch, setOfferSearch] = useState("");
  const [newOffer, setNewOffer] = useState("");
  const [form, setForm] = useState(initialForm);
  const campaignOffset = useRef(0);
  const campaignHasMoreRef = useRef(true);
  const campaignLoadingRef = useRef(false);
  const campaignListRef = useRef<HTMLDivElement>(null);
  const campaignSentinelRef = useRef<HTMLDivElement>(null);

  const navigate = useCallback((path: string) => {
    if (window.location.pathname + window.location.search !== path) window.history.pushState({}, "", path);
    setRoute(routeFromPath(path));
    setPageError("");
  }, []);

  useEffect(() => {
    const onPopState = () => setRoute(routeFromPath(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const loadCampaignBatch = useCallback(async (reset = false) => {
    if (campaignLoadingRef.current || (!reset && !campaignHasMoreRef.current)) return;
    campaignLoadingRef.current = true;
    setCampaignsLoading(true);
    const offset = reset ? 0 : campaignOffset.current;
    try {
      const result = await api<{ items: Campaign[] }>(`/campaigns?offset=${offset}&limit=${CAMPAIGN_BATCH_SIZE}`);
      const items = result.items || [];
      campaignOffset.current = offset + items.length;
      campaignHasMoreRef.current = items.length === CAMPAIGN_BATCH_SIZE;
      setCampaignsHaveMore(campaignHasMoreRef.current);
      setCampaigns((current) => {
        if (reset) return items;
        const known = new Set(current.map((campaign) => campaign.id));
        return [...current, ...items.filter((campaign) => !known.has(campaign.id))];
      });
      if (reset && campaignListRef.current) campaignListRef.current.scrollTop = 0;
    } finally {
      campaignLoadingRef.current = false;
      setCampaignsLoading(false);
    }
  }, []);

  const reloadCampaigns = () => {
    campaignOffset.current = 0;
    campaignHasMoreRef.current = true;
    setCampaignsHaveMore(true);
    void loadCampaignBatch(true).catch((error: Error) => setPageError(error.message));
  };

  useEffect(() => {
    void loadCampaignBatch(true).catch((error: Error) => setPageError(error.message));
    api<Catalogs>("/catalogs").then((data) => {
      setCatalogs(data);
      if (data.offers.length) setForm((current) => ({ ...current, offer_id: String(data.offers[0].id) }));
    }).catch((error: Error) => setPageError(error.message));
  }, [loadCampaignBatch]);

  useEffect(() => {
    const root = campaignListRef.current;
    const sentinel = campaignSentinelRef.current;
    if (!root || !sentinel || !campaignsHaveMore || route !== "campaigns") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        void loadCampaignBatch().catch((error: Error) => setPageError(error.message));
      }
    }, { root, rootMargin: "80px" });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [campaignsHaveMore, campaigns.length, campaignsLoading, loadCampaignBatch, route]);

  const reloadLocalStreams = useCallback(async (campaignId: number) => {
    setStreams(await api<Stream[]>(`/campaigns/${campaignId}/streams`));
  }, []);

  const filteredOffers = useMemo(() => {
    const query = offerSearch.trim().toLowerCase();
    return catalogs.offers.filter((offer) => !query || `${offer.id} ${offer.name}`.toLowerCase().includes(query));
  }, [catalogs.offers, offerSearch]);

  const selectCampaign = (campaign: Campaign) => {
    setSelected(campaign);
    setShowCreator(false);
    setStreams([]);
    setPageError("");
    void reloadLocalStreams(campaign.id).catch((error: Error) => setPageError(error.message));
  };

  const startNewCampaign = () => {
    setSelected(null);
    setShowCreator(true);
    setPageError("");
    setToast("");
    setForm((current) => ({ ...initialForm, offer_id: current.offer_id }));
  };

  const run = async (task: () => Promise<void>) => {
    setBusy(true);
    setPageError("");
    setToast("");
    try { await task(); }
    catch (error) { setPageError(error instanceof Error ? error.message : "Неизвестная ошибка"); }
    finally { setBusy(false); }
  };

  const createCampaign = () => run(async () => {
    const result = await api<Campaign & { streams: number[] }>("/campaigns", {
      method: "POST",
      body: JSON.stringify({ ...form, offer_id: Number(form.offer_id), domain_id: Number(form.domain_id), group_id: Number(form.group_id), traffic_source_id: Number(form.traffic_source_id) }),
    });
    campaignOffset.current = 0;
    campaignHasMoreRef.current = true;
    setCampaignsHaveMore(true);
    await loadCampaignBatch(true);
    setSelected(result);
    setShowCreator(false);
    setToast("Кампания создана и включена");
    await reloadLocalStreams(result.id);
  });

  const fetchStreams = () => selected && run(async () => {
    setStreams(await api<Stream[]>(`/campaigns/${selected.id}/streams/fetch`, { method: "POST" }));
    setToast("Потоки обновлены из Keitaro");
  });

  const mutate = (streamId: number, endpoint: string, method = "POST", body?: unknown) => selected && run(async () => {
    const updated = await api<Stream>(`/campaigns/${selected.id}/streams/${streamId}/${endpoint}`, {
      method, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    setStreams((current) => current.map((stream) => stream.stream_id === streamId ? updated : stream));
    setToast(endpoint === "push" ? "Изменения опубликованы в Keitaro" : endpoint === "cancel" ? "Черновик отменён" : "Изменения сохранены в черновике");
  });

  const addOffer = (streamId: number) => selected && newOffer && mutate(streamId, "offers", "POST", { offer_id: Number(newOffer) });

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" onClick={(event) => { event.preventDefault(); navigate("/"); }}>
          <div className="brand-mark">A</div><div><strong>adrobot</strong><span>KEITARO WRAPPER</span></div>
        </a>
        <nav className="top-nav" aria-label="Основная навигация">
          <a href="/" className={route === "campaigns" ? "active" : ""} onClick={(event) => { event.preventDefault(); navigate("/"); }}>Кампании</a>
          <a href="/history" className={route === "history" ? "active" : ""} onClick={(event) => { event.preventDefault(); navigate("/history"); }}>История операций</a>
        </nav>
        <a className="top-link" href="https://keitaro-for-tests.etolegko.com/admin/" target="_blank" rel="noreferrer">Открыть Keitaro <ExternalLink size={14} /></a>
      </header>

      <main className="workspace-page">
        {pageError && <div className="alert error"><X size={17} /><span>{pageError}</span><button onClick={() => setPageError("")} aria-label="Закрыть">×</button></div>}
        {toast && <div className="alert success"><Check size={17} /><span>{toast}</span><button onClick={() => setToast("")} aria-label="Закрыть">×</button></div>}

        {route === "history" ? (
          <OperationHistoryPage />
        ) : (
          <div className="workspace-layout">
            <aside className="campaign-sidebar">
              <button className={`new-campaign-button ${showCreator ? "selected" : ""}`} onClick={startNewCampaign}>
                <Plus size={17} /> Новая кампания
              </button>
              <div className="campaign-sidebar-heading">
                <div><h1>Кампании</h1><p>Выберите кампанию для редактирования</p></div>
                <button className="icon-button" onClick={reloadCampaigns} title="Обновить список"><RefreshCw size={15} /></button>
              </div>
              <div className="campaign-sidebar-list" ref={campaignListRef} aria-label="Список кампаний" aria-busy={campaignsLoading}>
                {campaigns.map((campaign) => (
                  <button key={campaign.id} className={`campaign-row ${selected?.id === campaign.id && !showCreator ? "selected" : ""}`} onClick={() => selectCampaign(campaign)}>
                    <span className="campaign-icon">↗</span>
                    <span className="campaign-name"><strong>{campaign.name}</strong><small>#{campaign.id}</small></span>
                    <span className={`state-pill ${campaign.state === "disabled" ? "muted" : ""}`}><i />{campaign.state || "active"}</span>
                  </button>
                ))}
                {campaigns.length === 0 && campaignsLoading && <div className="campaign-sidebar-state"><LoaderCircle size={15} className="spin" /> Загружаем кампании…</div>}
                {campaigns.length === 0 && !campaignsLoading && <div className="campaign-sidebar-empty">Пока нет кампаний</div>}
                {campaignsLoading && campaigns.length > 0 && <div className="campaign-sidebar-state"><LoaderCircle size={14} className="spin" /> Загружаем ещё…</div>}
                {campaignsHaveMore && <div className="campaign-sentinel" ref={campaignSentinelRef} aria-hidden="true" />}
                {!campaignsHaveMore && campaigns.length > 0 && <div className="campaign-sidebar-end">Все кампании загружены</div>}
              </div>
              <div className="campaign-sidebar-footer">Прокрутите список, чтобы загрузить следующие 10</div>
            </aside>

            <section className="workspace-content">
              {showCreator ? (
                <CampaignCreator catalogs={catalogs} form={form} setForm={setForm} busy={busy} onCreate={createCampaign} />
              ) : selected ? (
                <CampaignEditor campaign={selected} streams={streams} busy={busy} offerSearch={offerSearch} setOfferSearch={setOfferSearch} newOffer={newOffer} setNewOffer={setNewOffer} filteredOffers={filteredOffers} onFetch={fetchStreams} onMutate={mutate} onAddOffer={addOffer} />
              ) : (
                <div className="workspace-empty"><div className="empty-illustration"><Activity size={25} /></div><h2>Выберите кампанию</h2><p>Или создайте новую с помощью кнопки слева.</p></div>
              )}
            </section>
          </div>
        )}
        <footer className="footer"><span>ADROBOT <b>·</b> KEITARO WRAPPER</span><span>Локальная база хранит черновики и архив связей офферов</span></footer>
      </main>
      {busy && <div className="busy-indicator"><LoaderCircle size={15} className="spin" /> Выполняется запрос</div>}
    </div>
  );
}

function CampaignCreator({ catalogs, form, setForm, busy, onCreate }: {
  catalogs: Catalogs;
  form: typeof initialForm;
  setForm: React.Dispatch<React.SetStateAction<typeof initialForm>>;
  busy: boolean;
  onCreate: () => void;
}) {
  return (
    <section className="card create-card workspace-card">
      <div className="section-title"><div className="icon-box purple"><Plus size={18} /></div><div><div className="eyebrow">КАМПАНИИ</div><h2>Новая кампания</h2><p>Keitaro создаст GEO-поток и поток с оффером</p></div></div>
      <div className="form-grid">
        <label className="field wide"><span>Название кампании</span><input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Например, Australia test" /><small>Префикс <code>test_фамилия_</code> добавится автоматически</small></label>
        <div className="field"><span>Страна</span><CountryMultiSelect value={form.country_codes} onChange={(country_codes) => setForm((current) => ({ ...current, country_codes }))} /><small>В Keitaro отправятся ISO-2 коды: {form.country_codes.join(", ") || "выберите хотя бы одну страну"}</small></div>
        <label className="field"><span>Оффер для остальных</span><SearchableSelect label="Оффер для остальных" options={catalogs.offers} value={form.offer_id} onChange={(offer_id) => setForm((current) => ({ ...current, offer_id }))} placeholder="Поиск оффера по имени или ID" /><small>{catalogs.offers.length} офферов в каталоге</small></label>
        <label className="field"><span>Домен</span><SearchableSelect label="Домен" options={catalogs.domains} value={form.domain_id} onChange={(domain_id) => setForm((current) => ({ ...current, domain_id }))} /></label>
        <label className="field"><span>Группа</span><SearchableSelect label="Группа" options={catalogs.groups} value={form.group_id} onChange={(group_id) => setForm((current) => ({ ...current, group_id }))} /></label>
        <label className="field"><span>Источник трафика</span><SearchableSelect label="Источник трафика" options={catalogs.traffic_sources} value={form.traffic_source_id} onChange={(traffic_source_id) => setForm((current) => ({ ...current, traffic_source_id }))} /></label>
      </div>
      <div className="create-footer"><div className="flow-preview"><span className="flow-node google">01</span><span>Гео ({form.country_codes.length}) <ChevronRight size={13} /> Google</span><span className="flow-line" /><span className="flow-node offer">02</span><span>Остальные <ChevronRight size={13} /> оффер</span></div><button className="button primary" disabled={busy || !form.name.trim() || !form.offer_id || form.country_codes.length === 0 || catalogs.domains.length === 0} onClick={onCreate}>{busy ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />} Создать кампанию</button></div>
    </section>
  );
}

function CampaignEditor({ campaign, streams, busy, offerSearch, setOfferSearch, newOffer, setNewOffer, filteredOffers, onFetch, onMutate, onAddOffer }: {
  campaign: Campaign;
  streams: Stream[];
  busy: boolean;
  offerSearch: string;
  setOfferSearch: (value: string) => void;
  newOffer: string;
  setNewOffer: (value: string) => void;
  filteredOffers: Entity[];
  onFetch: () => void;
  onMutate: (streamId: number, endpoint: string, method?: string, body?: unknown) => void;
  onAddOffer: (streamId: number) => void;
}) {
  const [shareDrafts, setShareDrafts] = useState<Record<string, string>>({});

  const commitShare = (streamId: number, offer: Offer) => {
    const key = `${streamId}:${offer.offer_id}`;
    const draft = shareDrafts[key];
    if (draft === undefined) return;
    setShareDrafts((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    const share = Number(draft);
    if (!Number.isInteger(share) || share < 0 || share > 100 || share === offer.share) return;
    onMutate(streamId, `offers/${offer.offer_id}/share`, "PUT", { share });
  };

  return (
    <section className="card editor-card workspace-card">
      <div className="section-title editor-heading"><div className="icon-box orange"><Activity size={17} /></div><div><div className="eyebrow">РЕДАКТОР ПОТОКОВ · #{campaign.id}</div><h2>{campaign.name}</h2><p>Изменения сначала сохраняются в черновике</p></div><a className="button secondary small" href={`https://keitaro-for-tests.etolegko.com/admin/#!/campaign.editor/${campaign.id}`} target="_blank" rel="noreferrer">В Keitaro <ExternalLink size={14} /></a></div>
      <div className="editor-toolbar"><div><strong>Потоки и офферы</strong><span>{streams.length ? `${streams.length} потоков` : "Нажмите Fetch Streams, чтобы загрузить потоки"}</span></div><button className="button secondary" disabled={busy} onClick={onFetch}><ArrowDownToLine size={15} /> Fetch Streams</button></div>
      {streams.length === 0 ? <div className="empty-editor"><div className="empty-illustration"><ArrowDownToLine size={24} /></div><strong>Потоки не загружены</strong><span>Загрузите актуальные потоки этой кампании из Keitaro.</span></div> : <div className="streams-list">{streams.map((stream) => (
        <article className="stream-card" key={stream.stream_id}>
          <div className="stream-head"><div><div className="stream-title"><span className="stream-index">{String(stream.position).padStart(2, "0")}</span><h3>{stream.name}</h3><span className="stream-id">ID {stream.stream_id}</span></div><p>{stream.has_offer_flow ? "Поток с офферами" : "Без офферов · настройки потока не редактируются"}</p></div><span className={`draft-pill ${stream.dirty ? "dirty" : "clean"}`}><i />{stream.dirty ? "Черновик" : "Синхронизирован"}</span></div>
          {!stream.has_offer_flow ? <div className="placeholder-stream"><CircleHelp size={16} /> Поток сохранён в Keitaro. В этом редакторе управляются только потоки с офферами.</div> : <>
            <div className="table-head"><span>ОФФЕР</span><span>ДОЛЯ ТРАФИКА</span><span>СТАТУС</span><span>ДЕЙСТВИЯ</span></div>
            <div className="offer-list">{stream.offers.map((offer) => <div key={offer.offer_id} className={`offer-row ${!offer.present ? "removed" : ""}`}>
              <div className="offer-cell"><span className="offer-avatar">{offer.offer_name?.slice(0, 1)?.toUpperCase() || "O"}</span><span><strong>{offer.offer_name}</strong><small>ID {offer.offer_id}</small></span></div>
              <div className="share-cell">{offer.present && offer.pinned ? <><input className="share-input" type="number" min="0" max="100" step="1" aria-label={`Доля оффера ${offer.offer_id}, процентов`} value={shareDrafts[`${stream.stream_id}:${offer.offer_id}`] ?? String(offer.share)} onChange={(event) => setShareDrafts((current) => ({ ...current, [`${stream.stream_id}:${offer.offer_id}`]: event.target.value }))} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); commitShare(stream.stream_id, offer); } }} /><span className="share-suffix">%</span>{shareDrafts[`${stream.stream_id}:${offer.offer_id}`] !== undefined && <button className="apply-share-button" type="button" title="Пересчитать доли" aria-label={`Применить долю оффера ${offer.offer_id}`} onClick={() => commitShare(stream.stream_id, offer)}><Check size={14} /></button>}</> : <strong>{offer.present ? `${offer.share}%` : "0%"}</strong>}{offer.present && <button className={`pin-button ${offer.pinned ? "is-pinned" : ""}`} onClick={() => onMutate(stream.stream_id, `offers/${offer.offer_id}/pin`)} title={offer.pinned ? "Снять закрепление" : "Закрепить долю"} aria-label={offer.pinned ? "Снять закрепление доли" : "Закрепить долю"}><Pin size={15} fill={offer.pinned ? "currentColor" : "none"} /></button>}</div>
              <span className={`offer-status ${!offer.present ? "archived" : offer.dirty ? "pending" : ""}`}><i />{!offer.present ? "В архиве" : offer.dirty ? "Не опубликован" : "Активен"}</span>
              <div className={`action-cell ${!offer.present ? "archived-actions" : ""}`}>{offer.present ? <button className="text-button danger-text destructive-action" onClick={() => onMutate(stream.stream_id, `offers/${offer.offer_id}/remove`)}><Trash2 size={16} /> Удалить</button> : <><button className="text-button restore-text" onClick={() => onMutate(stream.stream_id, `offers/${offer.offer_id}/restore`)}><RotateCcw size={14} /> Восстановить</button><button className="text-button purge-text" title="Удалить архивную связь из Adrobot навсегда" onClick={() => { if (window.confirm(`Оффер «${offer.offer_name}» будет навсегда удалён из локального архива Adrobot. В Keitaro изменений не будет.`)) onMutate(stream.stream_id, `offers/${offer.offer_id}/archive`, "DELETE"); }}><Trash2 size={14} /> Удалить навсегда</button></>}</div>
            </div>)}</div>
            <div className="add-offer"><div className="search-wrap"><Search size={15} /><input value={offerSearch} onChange={(event) => setOfferSearch(event.target.value)} placeholder="Найти оффер по имени или ID" /></div><select value={newOffer} onChange={(event) => setNewOffer(event.target.value)}><option value="">Выберите оффер · {filteredOffers.length}</option>{filteredOffers.map((offer) => <option key={offer.id} value={offer.id}>#{offer.id} · {offer.name}</option>)}</select><button className="button secondary" disabled={!newOffer || busy} onClick={() => onAddOffer(stream.stream_id)}><Plus size={15} /> Добавить</button></div>
            <div className="stream-footer"><div className="weight-total"><span className={stream.offers.filter((item) => item.present).reduce((sum, item) => sum + item.share, 0) === 100 ? "total-ok" : "total-bad"}>{stream.offers.filter((item) => item.present).reduce((sum, item) => sum + item.share, 0)}%</span> распределено</div><div className="stream-actions"><button className="button ghost" disabled={!stream.dirty || busy} onClick={() => onMutate(stream.stream_id, "cancel")}><X size={15} /> Cancel</button><button className="button primary" disabled={!stream.dirty || busy} onClick={() => onMutate(stream.stream_id, "push")}><ArrowUpFromLine size={15} /> Push to Keitaro</button></div></div>
          </>}
        </article>
      ))}</div>}
    </section>
  );
}

function OperationHistoryPage() {
  const params = new URLSearchParams(window.location.search);
  const [draftFilters, setDraftFilters] = useState<HistoryFilters>({ campaign_id: params.get("campaign_id") || "", action: "", status: "", search: "", date_from: "", date_to: "" });
  const [appliedFilters, setAppliedFilters] = useState(draftFilters);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignsLoading, setCampaignsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const loadCampaignOptions = async () => {
      const loaded: Campaign[] = [];
      let nextOffset = 0;
      try {
        while (!cancelled) {
          const result = await api<{ items: Campaign[] }>(`/campaigns?offset=${nextOffset}&limit=500`);
          const batch = result.items || [];
          loaded.push(...batch);
          nextOffset += batch.length;
          if (batch.length < 500) break;
        }
        if (!cancelled) setCampaigns(loaded);
      } catch {
        if (!cancelled) setCampaigns([]);
      } finally {
        if (!cancelled) setCampaignsLoading(false);
      }
    };
    void loadCampaignOptions();
    return () => { cancelled = true; };
  }, []);

  const fetchHistory = useCallback(async (filters: HistoryFilters, nextOffset: number, append: boolean) => {
    setLoading(true);
    setError("");
    const query = new URLSearchParams({ offset: String(nextOffset), limit: String(HISTORY_BATCH_SIZE) });
    Object.entries(filters).forEach(([key, value]) => { if (value.trim()) query.set(key, value.trim()); });
    try {
      const result = await api<{ items: HistoryItem[]; total: number; has_more: boolean }>(`/history?${query.toString()}`);
      setItems((current) => append ? [...current, ...result.items] : result.items);
      setOffset(nextOffset + result.items.length);
      setTotal(result.total);
      setHasMore(result.has_more);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Не удалось загрузить историю");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchHistory(appliedFilters, 0, false); }, [appliedFilters, fetchHistory]);

  const updateFilter = (key: keyof HistoryFilters, value: string) => setDraftFilters((current) => ({ ...current, [key]: value }));
  const applyFilters = (event: FormEvent) => {
    event.preventDefault();
    setItems([]);
    setOffset(0);
    setAppliedFilters(draftFilters);
    if (JSON.stringify(draftFilters) === JSON.stringify(appliedFilters)) void fetchHistory(draftFilters, 0, false);
  };

  return (
    <section className="card history-page-card">
      <div className="section-title history-page-heading"><div className="icon-box blue"><FileClock size={18} /></div><div><div className="eyebrow">ЖУРНАЛ</div><h1>История операций</h1><p>Действия и синхронизации по всем кампаниям</p></div><span className="count-pill">{total} операций</span></div>
      <form className="history-filters" onSubmit={applyFilters}>
        <label className="history-campaign-field"><span>Кампания</span><SearchableSelect label="Кампания" options={campaigns} value={draftFilters.campaign_id} onChange={(value) => updateFilter("campaign_id", value)} placeholder={campaignsLoading ? "Загружаем кампании…" : "Поиск по имени или ID"} /></label>
        <label><span>Действие</span><input list="history-action-options" value={draftFilters.action} onChange={(event) => updateFilter("action", event.target.value)} placeholder="Любое действие или поиск" /><datalist id="history-action-options">{[
          "campaign.create", "campaign.enable", "offer.add.draft", "offer.archive.purged", "offer.pin", "offer.remove.draft", "offer.restore.draft", "offer.share", "stream.cancel", "stream.create.geo", "stream.create.offers", "stream.push", "streams.fetch",
        ].map((action) => <option key={action} value={action} />)}</datalist></label>
        <label><span>Статус</span><select value={draftFilters.status} onChange={(event) => updateFilter("status", event.target.value)}><option value="">Любой</option><option value="success">Успешно</option><option value="error">Ошибка</option></select></label>
        <label><span>С даты</span><input type="date" value={draftFilters.date_from} onChange={(event) => updateFilter("date_from", event.target.value)} /></label>
        <label><span>По дату</span><input type="date" value={draftFilters.date_to} onChange={(event) => updateFilter("date_to", event.target.value)} /></label>
        <label className="history-search-field"><span>Поиск в деталях</span><input value={draftFilters.search} onChange={(event) => updateFilter("search", event.target.value)} placeholder="Текст или ID оффера" /></label>
        <div className="history-filter-actions"><button className="button primary" type="submit" disabled={loading}><Search size={15} /> Применить</button><button className="button ghost" type="button" disabled={loading || Object.values(draftFilters).every((value) => !value)} onClick={() => { const empty: HistoryFilters = { campaign_id: "", action: "", status: "", search: "", date_from: "", date_to: "" }; setDraftFilters(empty); setItems([]); setOffset(0); setAppliedFilters(empty); }}>Сбросить</button></div>
      </form>
      <div className="history-results-summary">Показано {items.length} из {total} операций</div>
      {error && <div className="history-error">{error}</div>}
      <div className="history-table-wrap">
        <table className="history-table">
          <thead><tr><th>Время</th><th>Кампания</th><th>Поток</th><th>Действие</th><th>Статус</th><th>Детали</th></tr></thead>
          <tbody>
            {items.map((item) => <tr key={item.id}><td><time>{new Date(item.created_at).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" })}</time></td><td>{item.campaign_id ? `#${item.campaign_id}` : "—"}</td><td>{item.stream_id ? `#${item.stream_id}` : "—"}</td><td><code>{item.action}</code></td><td><span className={`history-status-pill ${item.status}`}>{item.status === "success" ? "Успешно" : "Ошибка"}</span></td><td>{item.details || "—"}</td></tr>)}
            {!items.length && !loading && <tr><td colSpan={6} className="history-table-empty">Операций по выбранным фильтрам нет</td></tr>}
            {loading && !items.length && <tr><td colSpan={6} className="history-table-empty"><LoaderCircle size={15} className="spin" /> Загружаем историю…</td></tr>}
          </tbody>
        </table>
      </div>
      {hasMore && <div className="history-load-more"><button className="button secondary" disabled={loading} onClick={() => void fetchHistory(appliedFilters, offset, true)}>{loading ? <LoaderCircle size={15} className="spin" /> : <ChevronRight size={15} />} Показать ещё</button></div>}
    </section>
  );
}

export default App;
