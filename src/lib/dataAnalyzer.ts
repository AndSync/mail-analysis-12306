/**
 * 数据分析模块 —— 对 12306 票务记录进行统计分析。
 * 逐条移植自 src/engine/data_analyzer.py，统计口径与排序规则一一对应。
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { REPO_ROOT } from "./config.js";
import { pyRound } from "./round.js";
import type { TicketRecord } from "./emailParser.js";

type Datetime = Date;

const DATETIME_MIN = new Date(-8640000000000000);

interface OverviewStats {
  total_records: number;
  purchase_count: number;
  ticket_purchase_count: number;
  refund_count: number;
  change_count: number;
  total_spent: number;
  total_refunded: number;
  net_spent: number;
  refund_fee_total: number;
  change_fee_total: number;
  refund_change_fee: number;
  avg_ticket_price: number;
  date_range: { start: string | null; end: string | null };
}

export class DataAnalyzer {
  records: TicketRecord[];
  cityMapping: Record<string, string>;

  constructor(records: TicketRecord[]) {
    this.records = records;
    this.cityMapping = this._loadCityMapping();
    this._prepareData();
  }

  _loadCityMapping(): Record<string, string> {
    const mapping: Record<string, string> = {};
    try {
      const candidates = [
        process.env.MAIL12306_CITIES_CONFIG,
        join(REPO_ROOT, "config", "config_cities.json"),
      ];
      const configPath = candidates.find((p) => p && exists(p));
      if (configPath) {
        const config = JSON.parse(readFileSync(configPath, "utf-8"));
        const cityAliases = (config.city_aliases || {}) as Record<string, string[]>;
        for (const [mainCity, aliases] of Object.entries(cityAliases)) {
          for (const alias of aliases) mapping[alias] = mainCity;
        }
      }
    } catch {
      // 加载失败用默认逻辑
    }
    return mapping;
  }

  _prepareData(): void {
    for (const record of this.records) {
      const dateStr = (record.departure_datetime as string) || (record.date as string) || "";
      const eventDateStr = (record.date as string) || "";

      const eventDt = this._parseDatetimeString(eventDateStr);
      if (eventDt) record._event_datetime = eventDt;

      const dt = this._parseDatetimeString(dateStr);
      if (dt) {
        record._datetime = dt;
        record._year = dt.getFullYear();
        record._month = dt.getMonth() + 1;
        record._year_month = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}`;
      }
    }
  }

  _parseDatetimeString(value: unknown): Datetime | null {
    if (!value || typeof value !== "string") return null;
    const v = value.slice(0, 19);
    // 依次尝试 Python 的四种格式
    const formats: Array<{ re: RegExp; build: (m: RegExpMatchArray) => Date }> = [
      {
        re: /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})/,
        build: (m) => new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]),
      },
      {
        re: /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/,
        build: (m) => new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], 0),
      },
      {
        re: /^(\d{4})-(\d{2})-(\d{2})/,
        build: (m) => new Date(+m[1], +m[2] - 1, +m[3], 0, 0, 0),
      },
      {
        re: /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})/,
        build: (m) => new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]),
      },
    ];
    for (const f of formats) {
      const m = v.match(f.re);
      if (m) {
        const d = f.build(m);
        if (!Number.isNaN(d.getTime())) return d;
      }
    }
    return null;
  }

  _filterRecords(
    startYear?: number | null,
    endYear?: number | null,
    startMonth?: string | null,
    endMonth?: string | null
  ): TicketRecord[] {
    const filtered: TicketRecord[] = [];
    for (const record of this.records) {
      if (!("_datetime" in record)) continue;
      const dt = record._datetime as Datetime;
      let include = true;

      if (startYear && dt.getFullYear() < startYear) include = false;
      if (endYear && dt.getFullYear() > endYear) include = false;

      if (startMonth) {
        const [year, month] = startMonth.split("-").map((x) => parseInt(x, 10));
        if (!Number.isNaN(year) && !Number.isNaN(month)) {
          if (dt.getFullYear() < year || (dt.getFullYear() === year && dt.getMonth() + 1 < month)) {
            include = false;
          }
        }
      }
      if (endMonth) {
        const [year, month] = endMonth.split("-").map((x) => parseInt(x, 10));
        if (!Number.isNaN(year) && !Number.isNaN(month)) {
          if (dt.getFullYear() > year || (dt.getFullYear() === year && dt.getMonth() + 1 > month)) {
            include = false;
          }
        }
      }

      if (include) filtered.push(record);
    }
    return filtered;
  }

  _buildTripKeys(record: TicketRecord): string[] {
    const orderNumber = (record.order_number as string) || "";
    const passengerName = (record.passenger_name as string) || "";
    const trainNumber = (record.train_number as string) || "";
    const departureStation = this._normalizeStationName((record.departure_station as string) || "");
    const arrivalStation = this._normalizeStationName((record.arrival_station as string) || "");
    const departureDatetime = (record.departure_datetime as string) || "";
    const seatType = (record.seat_type as string) || "";
    const price = pyRound(parseFloat(String((record.price as unknown) ?? 0) || "0") || 0, 2);

    const keys: string[] = [];
    if (orderNumber) {
      keys.push(JSON.stringify(["order", orderNumber, passengerName]));
      keys.push(JSON.stringify(["order", orderNumber]));
    }
    const tripCore = [passengerName, trainNumber, departureStation, arrivalStation, departureDatetime];
    keys.push(JSON.stringify(["trip", ...tripCore, seatType, price]));
    keys.push(JSON.stringify(["trip", ...tripCore, seatType]));
    keys.push(JSON.stringify(["trip", ...tripCore, price]));
    keys.push(JSON.stringify(["trip", ...tripCore]));
    return keys;
  }

  _matchOrderCancellation(purchaseRecord: TicketRecord, canceledRecord: TicketRecord): boolean {
    const purchaseOrder = (purchaseRecord.order_number as string) || "";
    const canceledOrder = (canceledRecord.order_number as string) || "";
    if (!purchaseOrder || !canceledOrder) return false;
    if (purchaseOrder !== canceledOrder) return false;

    const purchaseName = (purchaseRecord.passenger_name as string) || "";
    const canceledName = (canceledRecord.passenger_name as string) || "";
    if (canceledName && purchaseName && canceledName !== purchaseName) return false;
    return true;
  }

  _removeMatchingActiveRecord(
    activeRecords: TicketRecord[],
    targetRecord: TicketRecord
  ): TicketRecord | null {
    for (let idx = activeRecords.length - 1; idx >= 0; idx--) {
      if (this._matchOrderCancellation(activeRecords[idx], targetRecord)) {
        return activeRecords.splice(idx, 1)[0];
      }
    }

    const targetKeys = new Set(this._buildTripKeys(targetRecord));
    for (let idx = activeRecords.length - 1; idx >= 0; idx--) {
      const activeKeys = new Set(this._buildTripKeys(activeRecords[idx]));
      for (const k of targetKeys) {
        if (activeKeys.has(k)) return activeRecords.splice(idx, 1)[0];
      }
    }
    return null;
  }

  _getConflictGroupKey(record: TicketRecord): string | null {
    const passengerName = (record.passenger_name as string) || "";
    const trainNumber = (record.train_number as string) || "";
    const departureStation = this._normalizeStationName((record.departure_station as string) || "");
    const arrivalStation = this._normalizeStationName((record.arrival_station as string) || "");
    const departureDatetime = (record.departure_datetime as string) || "";

    if (!(passengerName && trainNumber && departureStation && arrivalStation && departureDatetime)) {
      return null;
    }
    return JSON.stringify([
      passengerName,
      trainNumber,
      departureStation,
      arrivalStation,
      departureDatetime,
    ]);
  }

  _getRecordRecencyKey(record: TicketRecord): [number, number, string] {
    const eventDt = (record._event_datetime as Datetime | undefined) || DATETIME_MIN;
    const typePriority = record.type === "change" ? 1 : 0;
    return [eventDt.getTime(), typePriority, (record.order_number as string) || ""];
  }

  _resolveConflictingFinalRecords(
    records: TicketRecord[]
  ): { resolved: TicketRecord[]; superseded: TicketRecord[] } {
    const grouped = new Map<string, TicketRecord[]>();
    const passthrough: TicketRecord[] = [];

    for (const record of records) {
      const key = this._getConflictGroupKey(record);
      if (key === null) {
        passthrough.push(record);
        continue;
      }
      const arr = grouped.get(key) || [];
      arr.push(record);
      grouped.set(key, arr);
    }

    const resolved: TicketRecord[] = [...passthrough];
    const superseded: TicketRecord[] = [];

    for (const groupRecords of grouped.values()) {
      if (groupRecords.length === 1) {
        resolved.push(...groupRecords);
        continue;
      }
      const sorted = [...groupRecords].sort((a, b) => {
        const [at, ap, ao] = this._getRecordRecencyKey(a);
        const [bt, bp, bo] = this._getRecordRecencyKey(b);
        if (at !== bt) return bt - at;
        if (ap !== bp) return bp - ap;
        return bo < ao ? 1 : bo > ao ? -1 : 0;
      });
      resolved.push(sorted[0]);
      superseded.push(...sorted.slice(1));
    }

    return { resolved, superseded };
  }

  _getEffectivePurchaseRecords(records: TicketRecord[]): TicketRecord[] {
    const tracked = records.filter((r) => ["purchase", "change", "refund"].includes(r.type));
    const typeOrder: Record<string, number> = { purchase: 0, change: 1, refund: 2 };
    tracked.sort((a, b) => {
      const at = ((a._event_datetime as Datetime | undefined) || DATETIME_MIN).getTime();
      const bt = ((b._event_datetime as Datetime | undefined) || DATETIME_MIN).getTime();
      if (at !== bt) return at - bt;
      return (typeOrder[a.type] ?? 9) - (typeOrder[b.type] ?? 9);
    });

    const orderPassengerFace = new Map<string, number>();
    for (const record of tracked) {
      if (record.type === "purchase" && record.order_number) {
        const key = JSON.stringify([record.order_number, (record.passenger_name as string) || ""]);
        orderPassengerFace.set(
          key,
          (orderPassengerFace.get(key) || 0) + (parseFloat(String((record.price as unknown) ?? 0) || "0") || 0)
        );
      }
    }

    const effectiveRecords: TicketRecord[] = [];
    const pendingCancellations: TicketRecord[] = [];
    for (const record of tracked) {
      if (record.type === "purchase") {
        effectiveRecords.push(record);
        continue;
      }
      if (record.type === "change") {
        this._fillChangeDelta(record, orderPassengerFace);
        const removed = this._removeMatchingActiveRecord(effectiveRecords, record);
        effectiveRecords.push(record);
        if (removed === null) pendingCancellations.push(record);
        continue;
      }
      if (record.type === "refund") {
        const removed = this._removeMatchingActiveRecord(effectiveRecords, record);
        if (removed === null) pendingCancellations.push(record);
      }
    }

    // 第二遍：乱序退票（退票邮件早于购票邮件）
    for (const record of pendingCancellations) {
      if (record.type === "refund") {
        this._removeMatchingActiveRecord(effectiveRecords, record);
      }
    }

    const { resolved } = this._resolveConflictingFinalRecords(effectiveRecords);
    return resolved;
  }

  _fillChangeDelta(record: TicketRecord, orderPassengerFace: Map<string, number>): void {
    if (record.actual_spent_amount != null || record.actual_refund_amount != null) return;

    const newFace = parseFloat(String((record.price as unknown) ?? 0) || "0") || 0;
    const key = JSON.stringify([record.order_number, (record.passenger_name as string) || ""]);
    const origFace = orderPassengerFace.get(key) || 0.0;
    const delta = pyRound(newFace - origFace, 2);
    if (delta > 0) {
      record.actual_spent_amount = delta;
      record.actual_refund_amount = 0.0;
    } else if (delta < 0) {
      record.actual_spent_amount = 0.0;
      record.actual_refund_amount = -delta;
    } else {
      record.actual_spent_amount = 0.0;
      record.actual_refund_amount = 0.0;
    }
  }

  _getRecordCashflow(record: TicketRecord): [number, number] {
    const price = parseFloat(String((record.price as unknown) ?? 0) || "0") || 0;
    const actualSpent = record.actual_spent_amount;
    const actualRefunded = record.actual_refund_amount;

    if (record.type === "purchase") {
      const spent = actualSpent != null ? parseFloat(String(actualSpent)) : price;
      return [spent, 0.0];
    }
    if (record.type === "refund") {
      const refunded = actualRefunded != null ? parseFloat(String(actualRefunded)) : price;
      return [0.0, refunded];
    }
    if (record.type === "change") {
      const spent = actualSpent != null ? parseFloat(String(actualSpent)) : 0.0;
      const refunded = actualRefunded != null ? parseFloat(String(actualRefunded)) : 0.0;
      return [spent, refunded];
    }
    return [0.0, 0.0];
  }

  _dedupeRefundRecords(records: TicketRecord[]): TicketRecord[] {
    const refundGroups = new Map<string, TicketRecord[]>();
    const passthrough: TicketRecord[] = [];
    for (const record of records) {
      if (
        record.type === "refund" &&
        record.order_number &&
        record.actual_refund_amount != null
      ) {
        const key = JSON.stringify([record.order_number, (record.passenger_name as string) || ""]);
        const arr = refundGroups.get(key) || [];
        arr.push(record);
        refundGroups.set(key, arr);
      } else {
        passthrough.push(record);
      }
    }

    const deduped = [...passthrough];
    for (const group of refundGroups.values()) {
      if (group.length === 1) {
        deduped.push(group[0]);
      } else {
        deduped.push(
          group.reduce((min, r) =>
            (parseFloat(String(r.actual_refund_amount)) || 0) <
            (parseFloat(String(min.actual_refund_amount)) || 0)
              ? r
              : min
          )
        );
      }
    }
    return deduped;
  }

  _getRefundFeeTotal(records: TicketRecord[]): number {
    const refundGroups = new Map<string, TicketRecord[]>();
    for (const record of records) {
      if (record.type === "refund" && record.order_number && record.refund_fee != null) {
        const key = JSON.stringify([record.order_number, (record.passenger_name as string) || ""]);
        const arr = refundGroups.get(key) || [];
        arr.push(record);
        refundGroups.set(key, arr);
      }
    }

    let total = 0;
    for (const group of refundGroups.values()) {
      total += Math.min(...group.map((r) => parseFloat(String(r.refund_fee)) || 0));
    }
    return pyRound(total, 2);
  }

  _getChangeFeeTotal(records: TicketRecord[]): number {
    let total = 0.0;
    const origFace = new Map<string, number>();
    for (const record of records) {
      if (record.type === "purchase" && record.order_number) {
        const key = JSON.stringify([record.order_number, (record.passenger_name as string) || ""]);
        origFace.set(
          key,
          (origFace.get(key) || 0) + (parseFloat(String((record.price as unknown) ?? 0) || "0") || 0)
        );
      }
    }

    for (const record of records) {
      if (record.type !== "change") continue;
      if (!record._has_explicit_refund) continue;
      const actualRefund = record.actual_refund_amount;
      if (actualRefund == null) continue;
      const newFace = parseFloat(String((record.price as unknown) ?? 0) || "0") || 0;
      const key = JSON.stringify([record.order_number, (record.passenger_name as string) || ""]);
      const orig = origFace.get(key) || 0.0;
      if (orig <= newFace) continue;
      const shouldRefund = pyRound(orig - newFace, 2);
      const fee = pyRound(shouldRefund - parseFloat(String(actualRefund)), 2);
      if (fee > 0.01) total += fee;
    }
    return pyRound(total, 2);
  }

  _cashflowRefundRecords(records: TicketRecord[]): TicketRecord[] {
    const pairedOrders = new Set<string>();
    for (const r of records) {
      if ((r.type === "purchase" || r.type === "change") && r.order_number) {
        pairedOrders.add(r.order_number as string);
      }
    }
    return this._dedupeRefundRecords(records).filter(
      (r) => r.type !== "refund" || !r.order_number || pairedOrders.has(r.order_number as string)
    );
  }

  _sumCashflow(records: TicketRecord[]): [number, number] {
    const { superseded } = this._resolveConflictingFinalRecords(
      records.filter((r) => r.type === "purchase" || r.type === "change")
    );
    const supersededIds = new Set(superseded);

    let totalSpent = 0.0;
    let totalRefunded = 0.0;
    for (const record of this._cashflowRefundRecords(records)) {
      if (supersededIds.has(record)) continue;
      const [spent, refunded] = this._getRecordCashflow(record);
      totalSpent += spent;
      totalRefunded += refunded;
    }
    return [pyRound(totalSpent, 2), pyRound(totalRefunded, 2)];
  }

  getOverviewStats(records?: TicketRecord[]): OverviewStats | Record<string, never> {
    const recs = records ?? this.records;
    if (!recs.length) return {};

    const purchaseRecords = recs.filter((r) => r.type === "purchase");
    const effectivePurchaseRecords = this._getEffectivePurchaseRecords(recs);
    const refundRecords = recs.filter((r) => r.type === "refund");
    const changeRecords = recs.filter((r) => r.type === "change");

    const [totalSpent, totalRefunded] = this._sumCashflow([
      ...purchaseRecords,
      ...refundRecords,
      ...changeRecords,
    ]);

    const dates = recs.filter((r) => "_datetime" in r).map((r) => r._datetime as Datetime);

    let avgPrice = 0;
    if (effectivePurchaseRecords.length) {
      const sum = effectivePurchaseRecords
        .filter((r) => "price" in r)
        .reduce((acc, r) => acc + (parseFloat(String((r.price as unknown) ?? 0)) || 0), 0);
      avgPrice = sum / effectivePurchaseRecords.length;
    }

    const netSpent = pyRound(totalSpent - totalRefunded, 2);
    const refundFeeTotal = this._getRefundFeeTotal(recs);
    const changeFeeTotal = this._getChangeFeeTotal(recs);
    const refundChangeFee = pyRound(refundFeeTotal + changeFeeTotal, 2);

    return {
      total_records: recs.length,
      purchase_count: effectivePurchaseRecords.length,
      ticket_purchase_count: purchaseRecords.length,
      refund_count: refundRecords.length,
      change_count: changeRecords.length,
      total_spent: totalSpent,
      total_refunded: totalRefunded,
      net_spent: netSpent,
      refund_fee_total: refundFeeTotal,
      change_fee_total: changeFeeTotal,
      refund_change_fee: refundChangeFee,
      avg_ticket_price: pyRound(avgPrice, 2),
      date_range: {
        start: dates.length ? this._formatDatetime(dates.reduce((a, b) => (a < b ? a : b))) : null,
        end: dates.length ? this._formatDatetime(dates.reduce((a, b) => (a > b ? a : b))) : null,
      },
    };
  }

  _formatDatetime(d: Datetime): string {
    const p = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }

  getYearlyStats(records?: TicketRecord[]): Array<Record<string, unknown>> {
    const recs = records ?? this.records;
    if (!recs.length) return [];

    const yearlyData = new Map<number, TicketRecord[]>();
    for (const record of recs) {
      let year = record._year as number | undefined;
      if (!year && "_datetime" in record) year = (record._datetime as Datetime).getFullYear();
      if (year) {
        const arr = yearlyData.get(year) || [];
        arr.push(record);
        yearlyData.set(year, arr);
      }
    }

    const yearlyStats: Array<Record<string, unknown>> = [];
    const years = [...yearlyData.keys()].sort((a, b) => a - b);
    for (const year of years) {
      const yearRecords = yearlyData.get(year)!;
      const purchaseRecords = yearRecords.filter((r) => r.type === "purchase");
      const effectivePurchaseRecords = this._getEffectivePurchaseRecords(yearRecords);
      const refundRecords = yearRecords.filter((r) => r.type === "refund");
      const changeRecords = yearRecords.filter((r) => r.type === "change");

      const [totalSpent, totalRefunded] = this._sumCashflow([
        ...purchaseRecords,
        ...refundRecords,
        ...changeRecords,
      ]);
      const netSpent = pyRound(totalSpent - totalRefunded, 2);

      let avgPrice = 0;
      if (effectivePurchaseRecords.length) {
        const sum = effectivePurchaseRecords
          .filter((r) => "price" in r)
          .reduce((acc, r) => acc + (parseFloat(String((r.price as unknown) ?? 0)) || 0), 0);
        avgPrice = sum / effectivePurchaseRecords.length;
      }
      const refundFeeTotal = this._getRefundFeeTotal(yearRecords);

      yearlyStats.push({
        year,
        total_trips: effectivePurchaseRecords.length,
        refund_count: refundRecords.length,
        total_spent: totalSpent,
        total_refunded: totalRefunded,
        net_spent: netSpent,
        refund_fee_total: refundFeeTotal,
        avg_price: pyRound(avgPrice, 2),
      });
    }
    return yearlyStats;
  }

  getPopularCities(records?: TicketRecord[]): Record<string, unknown> | unknown[] {
    const recs = records ?? this.records;
    if (!recs.length) return [];

    const purchaseRecords = this._getEffectivePurchaseRecords(recs);

    const departureCounter = new Map<string, number>();
    const arrivalCounter = new Map<string, number>();
    const cityPairCounter = new Map<string, number>();
    const departureSpent = new Map<string, number>();
    const arrivalSpent = new Map<string, number>();
    const routeSpent = new Map<string, number>();
    const departureLast = new Map<string, Datetime>();
    const arrivalLast = new Map<string, Datetime>();
    const routeLast = new Map<string, Datetime>();

    const inc = (m: Map<string, number>, k: string, v: number) => m.set(k, (m.get(k) || 0) + v);
    const updLast = (m: Map<string, Datetime>, k: string, dt: Datetime) => {
      if (!m.has(k) || dt > m.get(k)!) m.set(k, dt);
    };

    for (const record of purchaseRecords) {
      const depStation = (record.departure_station as string) || "";
      const arrStation = (record.arrival_station as string) || "";
      const price = parseFloat(String((record.price as unknown) ?? 0) || "0") || 0;
      const dt = (record._datetime as Datetime | undefined) || (record._event_datetime as Datetime | undefined);

      const depCity = depStation ? this._extractCityName(depStation) : "";
      const arrCity = arrStation ? this._extractCityName(arrStation) : "";
      const sameCity = !!(depCity && arrCity && depCity === arrCity);

      if (depStation && !sameCity) {
        inc(departureCounter, depCity, 1);
        inc(departureSpent, depCity, price);
        if (dt) updLast(departureLast, depCity, dt);
      }
      if (arrStation && !sameCity) {
        inc(arrivalCounter, arrCity, 1);
        inc(arrivalSpent, arrCity, price);
        if (dt) updLast(arrivalLast, arrCity, dt);
      }
      if (depStation && arrStation) {
        const routeKey = `${this._normalizeStationName(depStation)}→${this._normalizeStationName(arrStation)}`;
        inc(cityPairCounter, routeKey, 1);
        inc(routeSpent, routeKey, price);
        if (dt) updLast(routeLast, routeKey, dt);
      }
    }

    const mostCommon = (m: Map<string, number>): Array<[string, number]> =>
      [...m.entries()].sort((a, b) => b[1] - a[1]);

    const buildCities = (
      counter: Map<string, number>,
      spent: Map<string, number>,
      last: Map<string, Datetime>,
      type: string
    ): Array<Record<string, unknown>> =>
      this._sortByCountThenRecent(
        mostCommon(counter).map(([city, count]) => ({
          city,
          count,
          total_spent: pyRound(spent.get(city) || 0, 2),
          avg_price: pyRound((spent.get(city) || 0) / count, 2),
          last_departure: last.get(city) && last.get(city)! !== DATETIME_MIN ? last.get(city) : null,
          type,
        }))
      ).slice(0, 10);

    const popularDepartures = buildCities(departureCounter, departureSpent, departureLast, "出发");
    const popularArrivals = buildCities(arrivalCounter, arrivalSpent, arrivalLast, "到达");

    const popularRoutes = this._sortByCountThenRecent(
      mostCommon(cityPairCounter).map(([route, count]) => ({
        route,
        count,
        total_spent: pyRound(routeSpent.get(route) || 0, 2),
        avg_price: pyRound((routeSpent.get(route) || 0) / count, 2),
        last_departure: routeLast.get(route) && routeLast.get(route)! !== DATETIME_MIN ? routeLast.get(route) : null,
      }))
    ).slice(0, 10);

    return { departures: popularDepartures, arrivals: popularArrivals, routes: popularRoutes };
  }

  getPopularTrains(records?: TicketRecord[]): Array<Record<string, unknown>> {
    const recs = records ?? this.records;
    if (!recs.length) return [];

    const purchaseRecords = this._getEffectivePurchaseRecords(recs);

    const trainCounter = new Map<string, number>();
    const trainPrices = new Map<string, number[]>();
    const trainNet = new Map<string, number>();
    const trainLast = new Map<string, Datetime>();

    for (const record of purchaseRecords) {
      if ("train_number" in record) {
        const train = record.train_number as string;
        trainCounter.set(train, (trainCounter.get(train) || 0) + 1);
        if ("price" in record) {
          const arr = trainPrices.get(train) || [];
          arr.push(record.price as number);
          trainPrices.set(train, arr);
          trainNet.set(train, (trainNet.get(train) || 0) + (parseFloat(String((record.price as unknown) ?? 0)) || 0));
        }
        const dt = (record._datetime as Datetime | undefined) || (record._event_datetime as Datetime | undefined);
        if (dt && (!trainLast.has(train) || dt > trainLast.get(train)!)) trainLast.set(train, dt);
      }
    }

    const popularTrains = [...trainCounter.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([train, count]) => {
        const prices = trainPrices.get(train) || [];
        const avgPrice = prices.length ? prices.reduce((a, b) => a + b, 0) / prices.length : 0;
        return {
          train_number: train,
          count,
          avg_price: pyRound(avgPrice, 2),
          total_spent: pyRound(trainNet.get(train) || 0, 2),
          last_departure: trainLast.get(train) && trainLast.get(train)! !== DATETIME_MIN ? trainLast.get(train) : null,
        };
      });

    return this._sortByCountThenRecent(popularTrains).slice(0, 10);
  }

  getSeatTypeStats(records?: TicketRecord[]): Array<Record<string, unknown>> {
    const recs = records ?? this.records;
    if (!recs.length) return [];

    const purchaseRecords = this._getEffectivePurchaseRecords(recs);

    const seatCounter = new Map<string, number>();
    const seatPrices = new Map<string, number[]>();
    const seatLast = new Map<string, Datetime>();

    for (const record of purchaseRecords) {
      if ("seat_type" in record) {
        const seat = record.seat_type as string;
        seatCounter.set(seat, (seatCounter.get(seat) || 0) + 1);
        if ("price" in record) {
          const arr = seatPrices.get(seat) || [];
          arr.push(record.price as number);
          seatPrices.set(seat, arr);
        }
        const dt = (record._datetime as Datetime | undefined) || (record._event_datetime as Datetime | undefined);
        if (dt && (!seatLast.has(seat) || dt > seatLast.get(seat)!)) seatLast.set(seat, dt);
      }
    }

    const seatStats = [...seatCounter.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([seatType, count]) => {
        const prices = seatPrices.get(seatType) || [];
        const avgPrice = prices.length ? prices.reduce((a, b) => a + b, 0) / prices.length : 0;
        const totalSpent = prices.reduce((a, b) => a + b, 0);
        return {
          seat_type: seatType,
          count,
          avg_price: pyRound(avgPrice, 2),
          total_spent: pyRound(totalSpent, 2),
          last_departure: seatLast.get(seatType) && seatLast.get(seatType)! !== DATETIME_MIN ? seatLast.get(seatType) : null,
        };
      });

    return this._sortByCountThenRecent(seatStats).slice(0, 10);
  }

  getPassengerStats(records?: TicketRecord[]): Array<Record<string, unknown>> {
    const recs = records ?? this.records;
    if (!recs.length) return [];

    const effectivePurchaseRecords = this._getEffectivePurchaseRecords(recs);

    const tripCounter = new Map<string, number>();
    for (const record of effectivePurchaseRecords) {
      const passenger = (record.passenger_name as string) || "未知";
      tripCounter.set(passenger, (tripCounter.get(passenger) || 0) + 1);
    }

    const { superseded } = this._resolveConflictingFinalRecords(
      recs.filter((r) => r.type === "purchase" || r.type === "change")
    );
    const supersededIds = new Set(superseded);

    const flow = new Map<string, [number, number]>();
    for (const record of this._cashflowRefundRecords(recs)) {
      if (supersededIds.has(record)) continue;
      const passenger = (record.passenger_name as string) || "未知";
      const [spent, refunded] = this._getRecordCashflow(record);
      const cur = flow.get(passenger) || [0.0, 0.0];
      cur[0] += spent;
      cur[1] += refunded;
      flow.set(passenger, cur);
    }

    const allPassengers = new Set([...tripCounter.keys(), ...flow.keys()]);
    const passengerStats: Array<Record<string, unknown>> = [];
    for (const passenger of allPassengers) {
      const [spent, refunded] = flow.get(passenger) || [0.0, 0.0];
      const entry = {
        passenger_name: passenger,
        trip_count: tripCounter.get(passenger) || 0,
        total_spent: pyRound(spent, 2),
        total_refunded: pyRound(refunded, 2),
        net_spent: pyRound(spent - refunded, 2),
      };
      if (entry.trip_count === 0) continue;
      passengerStats.push(entry);
    }

    passengerStats.sort((a, b) => {
      const ac = a.trip_count as number;
      const bc = b.trip_count as number;
      if (ac !== bc) return bc - ac;
      return (b.net_spent as number) - (a.net_spent as number);
    });
    return passengerStats;
  }

  getDepartureTimeRanking(records?: TicketRecord[]): Array<Record<string, unknown>> {
    const recs = records ?? this.records;
    if (!recs.length) return [];

    const purchaseRecords = this._getEffectivePurchaseRecords(recs);

    const hourCounter = new Map<number, number>();
    const hourLast = new Map<number, Datetime>();

    for (const record of purchaseRecords) {
      const depTime = record.departure_datetime as string | undefined;
      if (depTime) {
        try {
          let timePart: string;
          if (depTime.includes(" ")) timePart = depTime.split(" ")[1].slice(0, 5);
          else timePart = depTime.slice(0, 5);
          const hour = parseInt(timePart.split(":")[0], 10);
          if (!Number.isNaN(hour)) {
            hourCounter.set(hour, (hourCounter.get(hour) || 0) + 1);
            const dt = (record._datetime as Datetime | undefined) || (record._event_datetime as Datetime | undefined);
            if (dt && (!hourLast.has(hour) || dt > hourLast.get(hour)!)) hourLast.set(hour, dt);
          }
        } catch {
          continue;
        }
      }
    }

    const ranking: Array<{ hour_range: string; count: number; last_departure: Datetime | null; hour: number }> = [];
    for (let hour = 0; hour < 24; hour++) {
      const count = hourCounter.get(hour) || 0;
      if (count > 0) {
        const lastDt = hourLast.get(hour);
        ranking.push({
          hour_range: `${String(hour).padStart(2, "0")}:00-${String((hour + 1) % 24).padStart(2, "0")}:00`,
          count,
          last_departure: lastDt && lastDt !== DATETIME_MIN ? lastDt : null,
          hour,
        });
      }
    }

    return this._sortByCountThenRecent(ranking).slice(0, 10);
  }

  _sortByCountThenRecent<T extends { count: number; last_departure: Datetime | null | undefined }>(items: T[]): T[] {
    return [...items].sort((a, b) => {
      if (a.count !== b.count) return b.count - a.count;
      const at = (a.last_departure || DATETIME_MIN).getTime();
      const bt = (b.last_departure || DATETIME_MIN).getTime();
      return bt - at;
    });
  }

  _extractCityName(stationName: string): string {
    if (!stationName) return "";

    const municipalities = ["北京", "上海", "天津", "重庆", "香港", "澳门"];
    for (const m of municipalities) {
      if (stationName.startsWith(m)) return m;
    }

    let city = stationName;
    const suffixes = ["火车站", "高铁站", "动车站", "城际站", "东站", "西站", "南站", "北站", "站", "东", "西", "南", "北"];
    for (const suffix of suffixes) {
      if (city.endsWith(suffix)) {
        city = city.slice(0, city.length - suffix.length);
        break;
      }
    }

    if (city in this.cityMapping) city = this.cityMapping[city];
    return city;
  }

  _normalizeStationName(stationName: string): string {
    if (!stationName) return "";
    let name = stationName.trim();
    if (name.endsWith("站")) name = name.slice(0, -1);
    return name;
  }

  generateFullReport(
    startYear?: number | null,
    endYear?: number | null,
    startMonth?: string | null,
    endMonth?: string | null
  ): Record<string, unknown> | Record<string, never> {
    const filteredRecords = this._filterRecords(startYear, endYear, startMonth, endMonth);
    if (!filteredRecords.length) return {};

    return {
      overview: this.getOverviewStats(filteredRecords),
      yearly_stats: this.getYearlyStats(filteredRecords),
      popular_cities: this.getPopularCities(filteredRecords),
      popular_trains: this.getPopularTrains(filteredRecords),
      seat_type_stats: this.getSeatTypeStats(filteredRecords),
      passenger_stats: this.getPassengerStats(filteredRecords),
      departure_time_ranking: this.getDepartureTimeRanking(filteredRecords),
      filter_info: { start_year: startYear, end_year: endYear, start_month: startMonth, end_month: endMonth },
    };
  }
}

function exists(p: string): boolean {
  try {
    readFileSync(p);
    return true;
  } catch {
    return false;
  }
}
