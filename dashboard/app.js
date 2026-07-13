/* Дашборд #OOTT. Читает предпосчитанные JSON из dashboard/data/. */
"use strict";

const COLORS = {
  bull: "#2fbf71", bear: "#e05252", neu: "#8b96ad",
  accent: "#4da3ff", text: "#e8ecf4", muted: "#8b96ad",
  grid: "#26304a", brent: "#f0b429",
};

const METRIC_RU = {
  views: "Просмотры", likes: "Лайки", replies: "Реплаи",
  retweets: "Ретвиты", quotes: "Цитаты", bookmarks: "Закладки",
};

const LANG_RU = {
  en: "Английский", es: "Испанский", fr: "Французский", de: "Немецкий",
  pt: "Португальский", it: "Итальянский", ru: "Русский", uk: "Украинский",
  ar: "Арабский", fa: "Персидский", tr: "Турецкий", ja: "Японский",
  ko: "Корейский", zh: "Китайский", hi: "Хинди", in: "Индонезийский",
  id: "Индонезийский", nl: "Голландский", no: "Норвежский", sv: "Шведский",
  da: "Датский", fi: "Финский", pl: "Польский", ro: "Румынский",
  ca: "Каталанский", th: "Тайский", vi: "Вьетнамский", et: "Эстонский",
  ht: "Гаитянский", tl: "Тагальский", cy: "Валлийский", eu: "Баскский",
  unknown: "Не определён", service: "Только хэштеги/медиа",
};

const ISO2_MAP_NAME = {
  US: "United States", GB: "United Kingdom", CA: "Canada", MX: "Mexico",
  BR: "Brazil", AR: "Argentina", CL: "Chile", CO: "Colombia", PE: "Peru",
  VE: "Venezuela", EC: "Ecuador", BO: "Bolivia", UY: "Uruguay", GY: "Guyana",
  TT: "Trinidad and Tobago", FR: "France", DE: "Germany", ES: "Spain",
  IT: "Italy", PT: "Portugal", NL: "Netherlands", BE: "Belgium",
  CH: "Switzerland", AT: "Austria", IE: "Ireland", NO: "Norway",
  SE: "Sweden", DK: "Denmark", FI: "Finland", IS: "Iceland", PL: "Poland",
  CZ: "Czech Rep.", SK: "Slovakia", HU: "Hungary", RO: "Romania",
  BG: "Bulgaria", GR: "Greece", CY: "Cyprus", MT: "Malta", HR: "Croatia",
  RS: "Serbia", SI: "Slovenia", UA: "Ukraine", RU: "Russia", BY: "Belarus",
  EE: "Estonia", LV: "Latvia", LT: "Lithuania", MD: "Moldova",
  GE: "Georgia", AM: "Armenia", AZ: "Azerbaijan", KZ: "Kazakhstan",
  UZ: "Uzbekistan", TM: "Turkmenistan", TR: "Turkey", CN: "China",
  HK: "Hong Kong", TW: "Taiwan", JP: "Japan", KR: "Korea",
  KP: "Dem. Rep. Korea", IN: "India", PK: "Pakistan", BD: "Bangladesh",
  LK: "Sri Lanka", NP: "Nepal", AF: "Afghanistan", ID: "Indonesia",
  MY: "Malaysia", SG: "Singapore", TH: "Thailand", VN: "Vietnam",
  PH: "Philippines", MM: "Myanmar", KH: "Cambodia", LA: "Lao PDR",
  BN: "Brunei", AU: "Australia", NZ: "New Zealand", FJ: "Fiji",
  PG: "Papua New Guinea", AE: "United Arab Emirates", SA: "Saudi Arabia",
  QA: "Qatar", KW: "Kuwait", BH: "Bahrain", OM: "Oman", YE: "Yemen",
  IQ: "Iraq", IR: "Iran", IL: "Israel", PS: "Palestine", JO: "Jordan",
  LB: "Lebanon", SY: "Syria", EG: "Egypt", LY: "Libya", DZ: "Algeria",
  TN: "Tunisia", MA: "Morocco", SD: "Sudan", NG: "Nigeria", GH: "Ghana",
  KE: "Kenya", ET: "Ethiopia", TZ: "Tanzania", UG: "Uganda", AO: "Angola",
  MZ: "Mozambique", ZM: "Zambia", ZW: "Zimbabwe", BW: "Botswana",
  NA: "Namibia", ZA: "South Africa", SN: "Senegal", CI: "Côte d'Ivoire",
  CM: "Cameroon", GA: "Gabon", CG: "Congo", CD: "Dem. Rep. Congo",
  TD: "Chad", NE: "Niger", ML: "Mali", MR: "Mauritania", GQ: "Eq. Guinea",
};

const state = {
  index: null, history: null, day: null, dayData: null,
  monthData: null, monthCache: {},
  modes: {
    summaryLang: "ru", priceIdx: "simple", emoIdx: "simple", idxHist: "price",
    vol: "day", hour: "day", engMetric: "views", engGran: "days",
    engStat: "avg", lang: "day", auth: "tweets", top: "views",
    map: "day", emoji: "day", word: "all",
  },
};

const charts = {};

function el(id) { return document.getElementById(id); }

function chart(id) {
  if (!charts[id]) {
    charts[id] = echarts.init(el(id), null, { renderer: "canvas" });
  }
  return charts[id];
}

function fmt(n) {
  if (n === null || n === undefined) return "—";
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (Math.abs(n) >= 1e4) return (n / 1e3).toFixed(1) + "K";
  return Number.isInteger(n) ? n.toLocaleString("ru-RU") : n.toLocaleString("ru-RU", { maximumFractionDigits: 1 });
}

async function fetchJSON(path) {
  const r = await fetch(path + "?v=" + Date.now());
  if (!r.ok) throw new Error(path + ": " + r.status);
  return r.json();
}

const baseAxis = {
  axisLine: { lineStyle: { color: COLORS.grid } },
  axisLabel: { color: COLORS.muted },
  splitLine: { lineStyle: { color: "rgba(38,48,74,0.5)" } },
};
const baseTooltip = {
  backgroundColor: "#1d2536", borderColor: COLORS.grid,
  textStyle: { color: COLORS.text }, confine: true,
};

/* ---------------------------------------------------------------- init */

async function init() {
  state.index = await fetchJSON("data/index.json");
  state.history = await fetchJSON("data/history.json");

  const days = state.index.days;
  const picker = el("datePicker");
  picker.min = days[0];
  picker.max = days[days.length - 1];
  picker.value = days[days.length - 1];
  picker.addEventListener("change", () => loadDay(picker.value));
  el("prevDay").addEventListener("click", () => step(-1));
  el("nextDay").addEventListener("click", () => step(1));

  setupSegments();
  await loadDay(picker.value);
  renderHistoryWidgets();

  el("footer").textContent =
    `Данные: ${days[0]} — ${days[days.length - 1]} · твиты #OOTT через twitterapi.io · ` +
    `обновлено ${state.index.generated_at.replace("T", " ").replace("Z", " UTC")}`;

  window.addEventListener("resize", () => Object.values(charts).forEach((c) => c.resize()));
}

function step(dir) {
  const days = state.index.days;
  const i = days.indexOf(state.day);
  const next = days[i + dir];
  if (next) { el("datePicker").value = next; loadDay(next); }
}

function setupSegments() {
  const bind = (segId, key, after) => {
    el(segId).querySelectorAll("button").forEach((b) => {
      b.addEventListener("click", () => {
        el(segId).querySelectorAll("button").forEach((x) => x.classList.remove("on"));
        b.classList.add("on");
        state.modes[key] = b.dataset.v;
        after();
      });
    });
  };
  bind("summaryLang", "summaryLang", renderSummary);
  bind("priceIdxMode", "priceIdx", renderSentiment);
  bind("emoIdxMode", "emoIdx", renderSentiment);
  bind("idxHistMode", "idxHist", renderIndexHistory);
  bind("volMode", "vol", renderVolume);
  bind("hourMode", "hour", renderHours);
  bind("engMetric", "engMetric", renderEngagement);
  bind("engGran", "engGran", renderEngagement);
  bind("engStat", "engStat", renderEngagement);
  bind("langMode", "lang", renderLanguages);
  bind("authMode", "auth", renderAuthors);
  bind("topMode", "top", renderTopTweets);
  bind("mapMode", "map", renderMap);
  bind("emojiMode", "emoji", renderEmoji);
  bind("wordMode", "word", renderWords);
}

async function loadDay(day) {
  state.day = day;
  state.dayData = await fetchJSON(`data/day/${day}.json`);
  const month = day.slice(0, 7);
  if (!state.monthCache[month]) {
    state.monthCache[month] = await fetchJSON(`data/month/${month}.json`);
  }
  state.monthData = state.monthCache[month];
  renderDayWidgets();
}

function renderDayWidgets() {
  renderCards();
  renderSummary();
  renderSentiment();
  renderTopics();
  renderVolume();
  renderHours();
  renderEngagement();
  renderLanguages();
  renderAuthors();
  renderTopTweets();
  renderMap();
  renderEmoji();
  renderWords();
  renderHashtagGraph();
}

function renderHistoryWidgets() {
  renderIndexHistory();
  renderHeatmap();
  renderAuthorsChart();
}

/* ---------------------------------------------------------------- cards */

function prevDayRow() {
  const rows = state.history.per_day;
  const i = rows.findIndex((r) => r.date === state.day);
  return i > 0 ? rows[i - 1] : null;
}

function renderCards() {
  const d = state.dayData;
  const prev = prevDayRow();
  const s = d.stats;
  const price = d.sentiment.price;
  const emo = d.sentiment.emotional;

  const delta = (cur, pre) => {
    if (cur === null || pre === null || pre === undefined) return "";
    const df = +(cur - pre).toFixed(1);
    if (df === 0) return `<div class="d">без изменений</div>`;
    const cls = df > 0 ? "up" : "down";
    const sign = df > 0 ? "+" : "";
    return `<div class="d ${cls}">${sign}${fmt(df)} к предыдущему дню</div>`;
  };
  const idxClass = (v) => (v === null ? "" : v > 10 ? "bullish" : v < -10 ? "bearish" : "");

  el("statCards").innerHTML = `
    <div class="card"><div class="k">Твиты</div><div class="v">${fmt(s.tweets)}</div>${delta(s.tweets, prev?.tweets)}</div>
    <div class="card"><div class="k">Авторы</div><div class="v">${fmt(d.unique_authors)}</div><div class="d">${fmt(d.new_authors)} новых</div></div>
    <div class="card"><div class="k">Просмотры</div><div class="v">${fmt(s.sum_views)}</div>${delta(s.sum_views, prev?.sum_views)}</div>
    <div class="card"><div class="k">Индекс цены</div><div class="v ${idxClass(price.index)}">${price.index === null ? "—" : (price.index > 0 ? "+" : "") + price.index}</div>${delta(price.index, prev?.price_index)}</div>
    <div class="card"><div class="k">Индекс эмоций</div><div class="v ${idxClass(emo.index)}">${emo.index === null ? "—" : (emo.index > 0 ? "+" : "") + emo.index}</div>${delta(emo.index, prev?.emo_index)}</div>
    <div class="card"><div class="k">Боты</div><div class="v">${d.bots_pct}%</div><div class="d">${fmt(d.bots)} твитов</div></div>`;
}

/* ---------------------------------------------------------------- summary */

function themeBlurb(t, lang) {
  const blurb = t["blurb_" + lang];
  if (blurb) return blurb;
  // fallback: первое предложение полного текста без имён авторов
  const raw = (t["text_" + lang] || "").replace(/\([^)]*@[^)]*\)/g, "").replace(/@\w+/g, "");
  const m = raw.match(/^[^.!?]+[.!?]/);
  return (m ? m[0] : raw).trim();
}

function renderSummary() {
  const s = state.dayData.summary;
  const lang = state.modes.summaryLang;
  const body = el("summaryBody");
  if (!s) {
    body.innerHTML = `<div class="no-data">Саммари за этот день ещё не сгенерировано.</div>`;
    return;
  }
  const themes = (s.themes || []).map((t) => {
    const links = (t.tweet_ids || [])
      .map((id, i) => `<a href="https://x.com/i/status/${id}" target="_blank" rel="noopener">твит ${i + 1} ↗</a>`)
      .join("");
    return `<div class="theme">
      <h3>${t["title_" + lang]} <span class="tone ${t.tone}">${t.tone}</span></h3>
      <div class="blurb">${themeBlurb(t, lang)}</div>
      <div class="links">${links}</div>
    </div>`;
  }).join("");
  body.innerHTML = `
    <div class="summary-layout">
      <div class="overview">${s["overview_" + lang]}</div>
      <div class="themes-col">${themes}</div>
    </div>`;
}

/* ---------------------------------------------------------------- sentiment */

function gaugeOption(value, title) {
  return {
    series: [{
      type: "gauge",
      min: -100, max: 100, startAngle: 200, endAngle: -20,
      axisLine: { lineStyle: { width: 16, color: [[0.35, COLORS.bear], [0.65, COLORS.neu], [1, COLORS.bull]] } },
      pointer: { itemStyle: { color: COLORS.text }, width: 4 },
      axisTick: { show: false }, splitLine: { length: 8, lineStyle: { color: "#0f1420", width: 2 } },
      axisLabel: { color: COLORS.muted, distance: 22, fontSize: 10 },
      title: { show: false },
      detail: {
        valueAnimation: true, fontSize: 30, fontWeight: 700, offsetCenter: [0, "62%"],
        color: value === null ? COLORS.muted : value > 10 ? COLORS.bull : value < -10 ? COLORS.bear : COLORS.text,
        formatter: value === null ? "нет данных" : (value > 0 ? "+" : "") + value,
      },
      data: [{ value: value === null ? 0 : value, name: title }],
    }],
  };
}

function hourlyStack(containerId, rows, names, colors) {
  chart(containerId).setOption({
    tooltip: { ...baseTooltip, trigger: "axis" },
    legend: { textStyle: { color: COLORS.muted }, top: 0 },
    grid: { left: 40, right: 16, top: 34, bottom: 28 },
    xAxis: { ...baseAxis, type: "category", data: rows.map((r) => r.hour), name: "час UTC", nameTextStyle: { color: COLORS.muted } },
    yAxis: { ...baseAxis, type: "value" },
    series: [
      { name: names[0], type: "bar", stack: "s", data: rows.map((r) => r.pos), itemStyle: { color: colors[0] } },
      { name: names[2], type: "bar", stack: "s", data: rows.map((r) => r.neu), itemStyle: { color: colors[2] } },
      { name: names[1], type: "bar", stack: "s", data: rows.map((r) => r.neg), itemStyle: { color: colors[1] } },
    ],
  }, true);
}

function renderSentiment() {
  const p = state.dayData.sentiment.price;
  const e = state.dayData.sentiment.emotional;

  const pVal = state.modes.priceIdx === "weighted" ? p.index_weighted : p.index;
  chart("priceGauge").setOption(gaugeOption(pVal, "price"));
  el("priceGaugeMeta").innerHTML = p.relevant
    ? `<b>${p.pos}</b> bullish · <b>${p.neu}</b> neutral · <b>${p.neg}</b> bearish<br>
       твитов с мнением: <b>${p.opinion_share}%</b> · релевантных: <b>${p.relevant}</b>`
    : "твиты этого дня ещё не классифицированы";

  const eVal = state.modes.emoIdx === "weighted" ? e.index_weighted : e.index;
  chart("emoGauge").setOption(gaugeOption(eVal, "emo"));
  el("emoGaugeMeta").innerHTML = e.relevant
    ? `<b>${e.pos}</b> positive · <b>${e.neu}</b> neutral · <b>${e.neg}</b> negative<br>
       твитов с мнением: <b>${e.opinion_share}%</b>`
    : "твиты этого дня ещё не классифицированы";

  hourlyStack("priceHourly", p.hourly, ["Bullish", "Bearish", "Neutral"], [COLORS.bull, COLORS.bear, COLORS.neu]);
  hourlyStack("emoHourly", e.hourly, ["Positive", "Negative", "Neutral"], [COLORS.bull, COLORS.bear, COLORS.neu]);
}

/* ---------------------------------------------------------------- index history + brent */

/* Линия Brent показывается только с июля 2026 — сентимент-история ведётся с этой даты,
   и цена без сентимента на графике не нужна (ICE Brent front-month: в июле — Sep26). */
const BRENT_FROM = "2026-07-01";

function renderIndexHistory() {
  // Ось начинается с июля 2026: сентимент и цена ведутся только с этой даты
  const rows = state.history.per_day.filter((r) => r.date >= BRENT_FROM);
  const mode = state.modes.idxHist;
  const key = mode === "price" ? "price_index" : "emo_index";
  const brent = state.history.brent || {};
  const dates = rows.map((r) => r.date);

  chart("idxHistory").setOption({
    tooltip: { ...baseTooltip, trigger: "axis" },
    legend: { textStyle: { color: COLORS.muted }, top: 0 },
    grid: { left: 48, right: 56, top: 34, bottom: 28 },
    xAxis: { ...baseAxis, type: "category", data: dates },
    yAxis: [
      { ...baseAxis, type: "value", name: "индекс", min: -100, max: 100 },
      { ...baseAxis, type: "value", name: "Brent, $", splitLine: { show: false }, scale: true },
    ],
    series: [
      {
        name: mode === "price" ? "Индекс (влияние на цену)" : "Индекс (эмоции)",
        type: "bar",
        data: rows.map((r) => r[key]),
        itemStyle: { color: (pr) => (pr.value === null ? COLORS.neu : pr.value >= 0 ? COLORS.bull : COLORS.bear) },
      },
      {
        name: "Brent (закрытие, ICE front-month)",
        type: "line", yAxisIndex: 1, connectNulls: true, smooth: true,
        data: dates.map((d) => (d >= BRENT_FROM ? brent[d] ?? null : null)),
        lineStyle: { color: COLORS.brent, width: 2 },
        itemStyle: { color: COLORS.brent },
        symbolSize: 5,
      },
    ],
  }, true);
}

/* ---------------------------------------------------------------- topics */

function renderTopics() {
  const rows = state.dayData.topics;
  const c = chart("topicsChart");
  if (!rows.length) {
    c.clear();
    c.setOption({ title: { text: "Темы появятся после классификации твитов дня", left: "center", top: "middle", textStyle: { color: COLORS.muted, fontSize: 14, fontWeight: 400 } } });
    return;
  }
  const cats = rows.map((r) => r.topic).reverse();
  const get = (k) => rows.map((r) => r[k]).reverse();
  c.setOption({
    tooltip: { ...baseTooltip, trigger: "axis", axisPointer: { type: "shadow" } },
    legend: { textStyle: { color: COLORS.muted }, top: 0 },
    grid: { left: 130, right: 30, top: 34, bottom: 28 },
    xAxis: { ...baseAxis, type: "value" },
    yAxis: { ...baseAxis, type: "category", data: cats, axisLabel: { color: COLORS.text } },
    series: [
      { name: "Bullish", type: "bar", stack: "t", data: get("bullish"), itemStyle: { color: COLORS.bull } },
      { name: "Neutral", type: "bar", stack: "t", data: get("neutral"), itemStyle: { color: COLORS.neu } },
      { name: "Bearish", type: "bar", stack: "t", data: get("bearish"), itemStyle: { color: COLORS.bear } },
    ],
  }, true);
}

/* ---------------------------------------------------------------- volume */

function renderVolume() {
  const mode = state.modes.vol;
  let cats, vals;
  if (mode === "day") {
    cats = state.history.per_day.map((r) => r.date);
    vals = state.history.per_day.map((r) => r.tweets);
  } else {
    cats = state.history.per_month.map((r) => r.month);
    vals = state.history.per_month.map((r) => r.tweets);
  }
  chart("volumeChart").setOption({
    tooltip: { ...baseTooltip, trigger: "axis" },
    grid: { left: 48, right: 16, top: 20, bottom: 28 },
    xAxis: { ...baseAxis, type: "category", data: cats },
    yAxis: { ...baseAxis, type: "value" },
    series: [{
      type: "bar",
      data: vals.map((v, i) => ({
        value: v,
        itemStyle: { color: mode === "day" && cats[i] === state.day ? COLORS.brent : COLORS.accent },
      })),
    }],
  }, true);
}

/* ---------------------------------------------------------------- hours */

function renderHours() {
  const mode = state.modes.hour;
  const dayHours = state.dayData.hours;
  const nDays = state.history.per_day.length;
  const avgHours = state.history.hours_total.map((v) => +(v / nDays).toFixed(1));

  const series = mode === "day"
    ? [
        { name: "Этот день", type: "bar", data: dayHours, itemStyle: { color: COLORS.accent } },
        { name: "Среднее за период", type: "line", data: avgHours, lineStyle: { color: COLORS.brent, type: "dashed" }, itemStyle: { color: COLORS.brent }, symbolSize: 4 },
      ]
    : [{ name: "Всего за период", type: "bar", data: state.history.hours_total, itemStyle: { color: COLORS.accent } }];

  chart("hoursChart").setOption({
    tooltip: { ...baseTooltip, trigger: "axis" },
    legend: { textStyle: { color: COLORS.muted }, top: 0 },
    grid: { left: 40, right: 16, top: 34, bottom: 28 },
    xAxis: { ...baseAxis, type: "category", data: [...Array(24).keys()] },
    yAxis: { ...baseAxis, type: "value" },
    series,
  }, true);
}

/* ---------------------------------------------------------------- heatmap */

function renderHeatmap() {
  const dayNames = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
  const data = [];
  let max = 0;
  state.history.heatmap.forEach((row, d) =>
    row.forEach((v, h) => { data.push([h, d, v]); max = Math.max(max, v); })
  );
  chart("heatmapChart").setOption({
    tooltip: { ...baseTooltip, formatter: (p) => `${dayNames[p.value[1]]}, ${p.value[0]}:00 UTC — <b>${p.value[2]}</b> твитов` },
    grid: { left: 40, right: 16, top: 10, bottom: 60 },
    xAxis: { ...baseAxis, type: "category", data: [...Array(24).keys()], splitArea: { show: true } },
    yAxis: { ...baseAxis, type: "category", data: dayNames, splitArea: { show: true } },
    visualMap: {
      min: 0, max, calculable: false, orient: "horizontal", left: "center", bottom: 0,
      textStyle: { color: COLORS.muted },
      inRange: { color: ["#1d2536", "#22537a", "#4da3ff", "#f0b429"] },
    },
    series: [{ type: "heatmap", data, emphasis: { itemStyle: { borderColor: "#fff", borderWidth: 1 } } }],
  }, true);
}

/* ---------------------------------------------------------------- engagement */

function renderEngagement() {
  const { engMetric: metric, engGran: gran, engStat: stat } = state.modes;
  const s = state.dayData.stats;

  el("engCards").innerHTML = `
    <div class="mini-card">Ср. просмотров/твит: <b>${fmt(s.avg_views)}</b> (медиана ${fmt(s.med_views)})</div>
    <div class="mini-card">Ср. лайков/твит: <b>${fmt(s.avg_likes)}</b></div>
    <div class="mini-card">Engagement rate (лайки/просмотры): <b>${s.engagement_rate}%</b></div>
    <div class="mini-card">Закладки за день: <b>${fmt(s.sum_bookmarks)}</b></div>`;

  let cats, vals, markDay = null;
  const key = stat + "_" + metric;
  if (gran === "days") {
    cats = state.history.per_day.map((r) => r.date);
    vals = state.history.per_day.map((r) => r[key]);
    markDay = state.day;
  } else if (gran === "months") {
    cats = state.history.per_month.map((r) => r.month);
    vals = state.history.per_month.map((r) => r[key] ?? null);
  } else {
    cats = [...Array(24).keys()];
    vals = state.dayData.hourly_engagement.map((r) => r[key]);
  }

  const statName = { avg: "среднее/твит", med: "медиана", sum: "сумма" }[stat];
  chart("engChart").setOption({
    tooltip: { ...baseTooltip, trigger: "axis", valueFormatter: fmt },
    grid: { left: 64, right: 16, top: 20, bottom: 28 },
    xAxis: { ...baseAxis, type: "category", data: cats },
    yAxis: { ...baseAxis, type: "value", name: `${METRIC_RU[metric]} (${statName})`, nameTextStyle: { color: COLORS.muted } },
    series: [{
      type: gran === "hours" ? "bar" : "line",
      data: vals.map((v, i) => ({
        value: v,
        itemStyle: markDay && cats[i] === markDay ? { color: COLORS.brent } : undefined,
      })),
      smooth: true,
      lineStyle: { color: COLORS.accent },
      itemStyle: { color: COLORS.accent },
      areaStyle: gran === "hours" ? undefined : { opacity: 0.08 },
    }],
  }, true);
}

/* ---------------------------------------------------------------- languages */

function langSource() {
  const m = state.modes.lang;
  if (m === "day") return state.dayData.languages;
  if (m === "month") return state.monthData.languages;
  return state.history.languages_all;
}

function renderLanguages() {
  const langs = langSource();
  const entries = Object.entries(langs);
  const total = entries.reduce((a, [, v]) => a + v, 0);
  const named = entries.filter(([k]) => k !== "unknown" && k !== "service");
  const top5 = named.slice(0, 5);
  const restVal = total - top5.reduce((a, [, v]) => a + v, 0);

  const pieData = top5.map(([k, v]) => ({ name: LANG_RU[k] || k, value: v }));
  if (restVal > 0) pieData.push({ name: "Прочие", value: restVal });

  chart("langChart").setOption({
    tooltip: { ...baseTooltip, formatter: (p) => `${p.name}: <b>${fmt(p.value)}</b> (${p.percent}%)` },
    series: [{
      type: "pie", radius: ["45%", "72%"],
      label: { color: COLORS.muted, fontSize: 12 },
      itemStyle: { borderColor: "#171e2e", borderWidth: 2 },
      data: pieData,
    }],
  }, true);

  const rows = top5.map(([k, v]) =>
    `<tr><td>${LANG_RU[k] || k} <span class="hint">${k}</span></td><td class="num">${fmt(v)} (${(100 * v / total).toFixed(1)}%)</td></tr>`
  );
  if (restVal > 0) rows.push(`<tr><td>Прочие (вкл. «только хэштеги/медиа»)</td><td class="num">${fmt(restVal)} (${(100 * restVal / total).toFixed(1)}%)</td></tr>`);
  el("langTable").innerHTML = `<table><thead><tr><th>Язык</th><th class="num">Твиты (%)</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

/* ---------------------------------------------------------------- authors */

function renderAuthors() {
  const d = state.dayData;
  el("authorsInfo").innerHTML = `
    <div class="mini-card">Уникальных авторов: <b>${d.unique_authors}</b></div>
    <div class="mini-card">Впервые с #OOTT: <b>${d.new_authors}</b></div>`;

  const rows = state.modes.auth === "tweets" ? d.top_authors_by_tweets : d.top_authors_by_views;
  el("authorsTable").innerHTML = `<table>
    <thead><tr><th>Автор</th><th class="num">Твиты</th><th class="num">Просмотры</th><th class="num">Лайки</th><th class="num">Фолловеры</th></tr></thead>
    <tbody>${rows.map((a) => `<tr>
      <td><a class="author-link" href="https://x.com/${a.username}" target="_blank" rel="noopener">@${a.username}</a><br><span class="hint">${a.name}</span></td>
      <td class="num">${a.tweets}</td>
      <td class="num">${fmt(a.views)}</td>
      <td class="num">${fmt(a.likes)}</td>
      <td class="num">${fmt(a.followers)}</td>
    </tr>`).join("")}</tbody></table>`;
}

function renderAuthorsChart() {
  const rows = state.history.per_day;
  chart("authorsChart").setOption({
    tooltip: { ...baseTooltip, trigger: "axis" },
    legend: { textStyle: { color: COLORS.muted }, top: 0 },
    grid: { left: 44, right: 16, top: 34, bottom: 28 },
    xAxis: { ...baseAxis, type: "category", data: rows.map((r) => r.date) },
    yAxis: { ...baseAxis, type: "value" },
    series: [
      { name: "Уникальные авторы", type: "line", data: rows.map((r) => r.unique_authors), smooth: true, lineStyle: { color: COLORS.accent }, itemStyle: { color: COLORS.accent }, areaStyle: { opacity: 0.08 } },
      { name: "Новые авторы", type: "bar", data: rows.map((r) => r.new_authors), itemStyle: { color: COLORS.bull, opacity: 0.7 } },
    ],
  }, true);
}

/* ---------------------------------------------------------------- top tweets */

function renderTopTweets() {
  const metric = state.modes.top;
  const rows = [...state.dayData.top_tweets].sort((a, b) => b[metric] - a[metric]).slice(0, 5);
  const linkify = (text) => text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/@(\w+)/g, `<a href="https://x.com/$1" target="_blank" rel="noopener">@$1</a>`);

  el("topTweets").innerHTML = `<table>
    <thead><tr><th>Твит</th><th class="num">Просм.</th><th class="num">Лайки</th><th class="num">Реплаи</th><th class="num">RT</th><th class="num">Закл.</th></tr></thead>
    <tbody>${rows.map((t) => {
      const lab = t.labels && t.labels.relevant ? `<span class="badge ${t.labels.price_sentiment}">${t.labels.price_sentiment}</span>` : "";
      return `<tr>
      <td class="tweet-text">${linkify(t.text)}${lab}
        <div class="tweet-meta">
          <a class="author-link" href="https://x.com/${t.author}" target="_blank" rel="noopener">@${t.author}</a>
          · ${fmt(t.followers)} фолловеров · ${t.time} UTC ·
          <a href="${t.url}" target="_blank" rel="noopener">открыть ↗</a>
        </div></td>
      <td class="num">${fmt(t.views)}</td><td class="num">${fmt(t.likes)}</td>
      <td class="num">${fmt(t.replies)}</td><td class="num">${fmt(t.retweets)}</td>
      <td class="num">${fmt(t.bookmarks)}</td></tr>`;
    }).join("")}</tbody></table>`;
}

/* ---------------------------------------------------------------- map */

function mapSource() {
  const m = state.modes.map;
  if (m === "day") return { c: state.dayData.countries, u: state.dayData.countries_unresolved, total: state.dayData.stats.tweets };
  if (m === "month") return { c: state.monthData.countries, u: state.monthData.countries_unresolved, total: state.monthData.stats.tweets };
  const h = state.history;
  const total = h.per_day.reduce((a, r) => a + r.tweets, 0);
  return { c: h.countries_all, u: h.countries_unresolved_all, total };
}

function renderMap() {
  const { c: countries, u: unresolved, total } = mapSource();
  const data = Object.entries(countries)
    .filter(([iso]) => ISO2_MAP_NAME[iso])
    .map(([iso, v]) => ({ name: ISO2_MAP_NAME[iso], value: v.tweets, authors: v.authors }));
  const max = Math.max(1, ...data.map((d) => d.value));
  const resolved = total - unresolved;
  el("mapCoverage").textContent = `страна определена у ${(100 * resolved / Math.max(total, 1)).toFixed(0)}% твитов (по профилю автора)`;

  chart("mapChart").setOption({
    tooltip: { ...baseTooltip, formatter: (p) => p.data ? `${p.name}<br><b>${fmt(p.data.value)}</b> твитов · ${p.data.authors} авторов` : `${p.name}: нет твитов` },
    visualMap: {
      min: 0, max, left: 10, bottom: 10, calculable: true,
      textStyle: { color: COLORS.muted },
      inRange: { color: ["#22304a", "#2a5b8f", "#4da3ff", "#f0b429"] },
    },
    series: [{
      type: "map", map: "world", roam: true, scaleLimit: { min: 1, max: 8 },
      itemStyle: { areaColor: "#1a2233", borderColor: "#26304a" },
      emphasis: { label: { show: false }, itemStyle: { areaColor: "#f0b429" } },
      data,
    }],
  }, true);
}

/* ---------------------------------------------------------------- emoji + words */

function renderEmoji() {
  const src = state.modes.emoji === "day" ? state.dayData.emojis : state.monthData.emojis;
  const data = Object.entries(src).map(([name, value]) => ({ name, value }));
  const c = chart("emojiCloud");
  c.clear();
  if (!data.length) {
    c.setOption({ title: { text: "Эмодзи не найдены", left: "center", top: "middle", textStyle: { color: COLORS.muted, fontSize: 14, fontWeight: 400 } } });
    return;
  }
  c.setOption({
    tooltip: { ...baseTooltip, formatter: (p) => `${p.name} — ${p.value} раз` },
    series: [{
      type: "wordCloud", shape: "circle", width: "100%", height: "100%",
      sizeRange: [16, 64], rotationRange: [0, 0], gridSize: 6, drawOutOfBound: false,
      textStyle: { color: () => COLORS.text },
      data,
    }],
  });
}

function renderWords() {
  const d = state.dayData;
  const mode = state.modes.word;
  const src = mode === "bull" ? d.words_bullish : mode === "bear" ? d.words_bearish : d.words;
  const data = Object.entries(src).map(([name, value]) => ({ name, value }));
  const c = chart("wordCloud");
  c.clear();
  if (!data.length) {
    const msg = mode === "all" ? "Нет данных" : "Появится после классификации твитов дня";
    c.setOption({ title: { text: msg, left: "center", top: "middle", textStyle: { color: COLORS.muted, fontSize: 14, fontWeight: 400 } } });
    return;
  }
  const palette = mode === "bull"
    ? ["#2fbf71", "#57d68f", "#9be8bd", "#e8ecf4"]
    : mode === "bear"
    ? ["#e05252", "#ea7f7f", "#f2b0b0", "#e8ecf4"]
    : ["#4da3ff", "#7cbcff", "#b0d5ff", "#e8ecf4", "#f0b429"];
  c.setOption({
    tooltip: { ...baseTooltip, formatter: (p) => `${p.name} — ${p.value} раз` },
    series: [{
      type: "wordCloud", shape: "circle", width: "100%", height: "100%",
      sizeRange: [12, 52], rotationRange: [-45, 45], rotationStep: 45, gridSize: 4,
      textStyle: { color: () => palette[Math.floor(Math.random() * palette.length)] },
      data,
    }],
  });
}

/* ---------------------------------------------------------------- hashtag graph */

function renderHashtagGraph() {
  const { nodes: nodeMap, edges } = state.dayData.hashtags;
  const c = chart("hashtagGraph");
  c.clear();
  const entries = Object.entries(nodeMap);
  if (!entries.length) {
    c.setOption({ title: { text: "Других хэштегов в этот день нет", left: "center", top: "middle", textStyle: { color: COLORS.muted, fontSize: 14, fontWeight: 400 } } });
    return;
  }
  const maxV = Math.max(...entries.map(([, v]) => v));
  const nodes = [
    { name: "#oott", symbolSize: 56, itemStyle: { color: COLORS.brent }, label: { show: true, fontSize: 15, fontWeight: 700 }, value: state.dayData.stats.tweets },
    ...entries.map(([name, v]) => ({
      name: "#" + name,
      value: v,
      symbolSize: 12 + 34 * Math.sqrt(v / maxV),
      itemStyle: { color: COLORS.accent },
      label: { show: v >= maxV * 0.15, fontSize: 11 },
    })),
  ];
  const links = [
    ...entries.map(([name, v]) => ({ source: "#oott", target: "#" + name, value: v, lineStyle: { width: Math.max(0.5, 3 * v / maxV), color: "rgba(77,163,255,0.25)" } })),
    ...edges.map((e) => ({ source: "#" + e.a, target: "#" + e.b, value: e.w, lineStyle: { width: Math.max(0.5, 2 * e.w / maxV), color: "rgba(240,180,41,0.28)" } })),
  ];
  c.setOption({
    tooltip: { ...baseTooltip, formatter: (p) => p.dataType === "node" ? `${p.name}: <b>${p.value}</b> твитов` : `${p.data.source} + ${p.data.target}: ${p.data.value} совместно` },
    series: [{
      type: "graph", layout: "force", roam: true,
      force: { repulsion: 140, edgeLength: [40, 140], gravity: 0.12 },
      label: { color: COLORS.text },
      emphasis: { focus: "adjacency" },
      nodes, links,
    }],
  });
}

init().catch((e) => {
  document.body.insertAdjacentHTML("beforeend",
    `<div style="position:fixed;bottom:16px;left:16px;background:#3a1c1c;color:#f2b0b0;padding:10px 14px;border-radius:8px;">Ошибка загрузки данных: ${e.message}</div>`);
  console.error(e);
});
