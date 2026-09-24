"""
数据分析模块 - 对12306票务记录进行统计分析（纯原生实现）
"""
from datetime import datetime
from collections import Counter, defaultdict
import logging
import json
import os

logger = logging.getLogger(__name__)


class DataAnalyzer:
    """数据分析器"""
    
    def __init__(self, records):
        """
        初始化分析器
        :param records: 票务记录列表
        """
        self.records = records
        self.city_mapping = self._load_city_mapping()
        self._prepare_data()
    
    def _load_city_mapping(self):
        """
        加载城市别名映射配置
        :return: 城市别名字典 {别名: 主城市}
        """
        mapping = {}
        try:
            # 尝试从配置文件加载（engine/ 上两级 = 仓库根，再进 config/）
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            candidates = [
                os.environ.get('MAIL12306_CITIES_CONFIG'),
                os.path.join(repo_root, 'config', 'config_cities.json'),
            ]
            config_path = next((p for p in candidates if p and os.path.exists(p)), None)
            if config_path:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    city_aliases = config.get('city_aliases', {})
                    # 构建反向映射：{别名: 主城市}
                    for main_city, aliases in city_aliases.items():
                        for alias in aliases:
                            mapping[alias] = main_city
                logger.info(f"已加载城市别名映射，共 {len(mapping)} 个站点映射")
            else:
                logger.debug("未找到城市别名配置文件，使用默认逻辑")
        except Exception as e:
            logger.warning(f"加载城市别名映射失败: {e}，使用默认逻辑")
            
        return mapping
    
    def _prepare_data(self):
        """数据预处理，添加日期字段"""
        if not self.records:
            logger.warning("没有记录可供分析")
            return
        
        for record in self.records:
            try:
                # 优先使用出发日期（departure_datetime），如果没有则使用邮件接收日期（date）
                date_str = record.get('departure_datetime') or record.get('date')
                event_date_str = record.get('date')

                event_dt = self._parse_datetime_string(event_date_str)
                if event_dt:
                    record['_event_datetime'] = event_dt

                dt = self._parse_datetime_string(date_str)
                if dt:
                    record['_datetime'] = dt
                    record['_year'] = dt.year
                    record['_month'] = dt.month
                    record['_year_month'] = f"{dt.year}-{dt.month:02d}"
                elif date_str:
                    logger.debug(f"无法解析日期: {date_str}")
            except Exception as e:
                logger.debug(f"日期解析失败: {e}")
        
        logger.info(f"已准备 {len(self.records)} 条记录用于分析")

    def _parse_datetime_string(self, value):
        """解析常见日期时间字符串"""
        if not value or not isinstance(value, str):
            return None

        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z"]:
            try:
                return datetime.strptime(value[:19], fmt[:19])
            except:
                continue
        return None
    
    def _filter_records(self, start_year=None, end_year=None, start_month=None, end_month=None):
        """
        按日期过滤记录
        :param start_year: 开始年份
        :param end_year: 结束年份
        :param start_month: 开始月份 (格式: "YYYY-MM")
        :param end_month: 结束月份 (格式: "YYYY-MM")
        :return: 过滤后的记录列表
        """
        if not self.records:
            return []
        
        filtered = []
        
        for record in self.records:
            if '_datetime' not in record:
                continue
            
            dt = record['_datetime']
            include = True
            
            if start_year and dt.year < start_year:
                include = False
            if end_year and dt.year > end_year:
                include = False
            
            if start_month:
                try:
                    year, month = map(int, start_month.split('-'))
                    if dt.year < year or (dt.year == year and dt.month < month):
                        include = False
                except:
                    pass
            
            if end_month:
                try:
                    year, month = map(int, end_month.split('-'))
                    if dt.year > year or (dt.year == year and dt.month > month):
                        include = False
                except:
                    pass
            
            if include:
                filtered.append(record)
        
        logger.info(f"过滤后剩余 {len(filtered)} 条记录")
        return filtered

    def _build_trip_keys(self, record):
        """构建多个层级的行程匹配键，用于识别已退票/已改签的购票记录"""
        order_number = record.get('order_number') or ''
        passenger_name = record.get('passenger_name') or ''
        train_number = record.get('train_number') or ''
        departure_station = self._normalize_station_name(record.get('departure_station') or '')
        arrival_station = self._normalize_station_name(record.get('arrival_station') or '')
        departure_datetime = record.get('departure_datetime') or ''
        seat_type = record.get('seat_type') or ''
        price = round(float(record.get('price', 0) or 0), 2)

        keys = []

        if order_number:
            keys.append(('order', order_number, passenger_name))
            keys.append(('order', order_number))

        trip_core = (
            passenger_name,
            train_number,
            departure_station,
            arrival_station,
            departure_datetime,
        )
        keys.append(('trip',) + trip_core + (seat_type, price))
        keys.append(('trip',) + trip_core + (seat_type,))
        keys.append(('trip',) + trip_core + (price,))
        keys.append(('trip',) + trip_core)

        return keys

    def _match_order_cancellation(self, purchase_record, canceled_record):
        """优先按订单号匹配，避免跨订单误抵消"""
        purchase_order = purchase_record.get('order_number') or ''
        canceled_order = canceled_record.get('order_number') or ''
        if not purchase_order or not canceled_order:
            return False
        if purchase_order != canceled_order:
            return False

        purchase_name = purchase_record.get('passenger_name') or ''
        canceled_name = canceled_record.get('passenger_name') or ''
        if canceled_name and purchase_name and canceled_name != purchase_name:
            return False

        return True

    def _remove_matching_active_record(self, active_records, target_record):
        """
        从当前有效行程中移除一条与目标记录匹配的记录
        优先按订单号+乘客匹配，其次退回到行程特征匹配
        """
        for idx in range(len(active_records) - 1, -1, -1):
            active_record = active_records[idx]
            if self._match_order_cancellation(active_record, target_record):
                return active_records.pop(idx)

        target_keys = self._build_trip_keys(target_record)
        for idx in range(len(active_records) - 1, -1, -1):
            active_record = active_records[idx]
            active_keys = set(self._build_trip_keys(active_record))
            if any(key in active_keys for key in target_keys):
                return active_records.pop(idx)

        return None

    def _get_conflict_group_key(self, record):
        """构建最终出行冲突键：同一乘客不可能在同一时刻坐同一趟同一路线的两张票"""
        passenger_name = record.get('passenger_name') or ''
        train_number = record.get('train_number') or ''
        departure_station = self._normalize_station_name(record.get('departure_station') or '')
        arrival_station = self._normalize_station_name(record.get('arrival_station') or '')
        departure_datetime = record.get('departure_datetime') or ''

        if not (passenger_name and train_number and departure_station and arrival_station and departure_datetime):
            return None

        return (
            passenger_name,
            train_number,
            departure_station,
            arrival_station,
            departure_datetime,
        )

    def _get_record_recency_key(self, record):
        """用于冲突场景下选保留哪条记录：优先保留后来的邮件记录"""
        event_dt = record.get('_event_datetime')
        record_type = record.get('type') or ''
        type_priority = 1 if record_type == 'change' else 0
        return (
            event_dt or datetime.min,
            type_priority,
            record.get('order_number') or '',
        )

    def _resolve_conflicting_final_records(self, records):
        """
        对最终行程做冲突消解：
        同一乘客在同一时刻的同车同路线，只保留较新的那条记录。
        返回: (resolved_records, superseded_records)
        """
        grouped = defaultdict(list)
        passthrough = []

        for record in records:
            key = self._get_conflict_group_key(record)
            if key is None:
                passthrough.append(record)
                continue
            grouped[key].append(record)

        resolved_records = list(passthrough)
        superseded_records = []

        for group_records in grouped.values():
            if len(group_records) == 1:
                resolved_records.extend(group_records)
                continue

            sorted_group = sorted(group_records, key=self._get_record_recency_key, reverse=True)
            resolved_records.append(sorted_group[0])
            superseded_records.extend(sorted_group[1:])

        return resolved_records, superseded_records

    def _get_effective_purchase_records(self, records):
        """
        获取有效出行记录
        - 退票对应的原购票记录不计入出行统计
        - 改签对应的原购票记录不计入出行统计
        - 改签后的新行程使用改签记录参与出行统计
        """
        tracked_records = [r for r in records if r.get('type') in ('purchase', 'change', 'refund')]
        tracked_records.sort(
            key=lambda record: (
                record.get('_event_datetime') or datetime.min,
                {'purchase': 0, 'change': 1, 'refund': 2}.get(record.get('type'), 9)
            )
        )

        # 预计算每个 (订单, 乘客) 的原始购票票面（用于改签补差/退差推算）
        order_passenger_face = defaultdict(float)
        for record in tracked_records:
            if record.get('type') == 'purchase' and record.get('order_number'):
                key = (record['order_number'], record.get('passenger_name') or '')
                order_passenger_face[key] += float(record.get('price', 0) or 0)

        # 先按事件顺序重建有效行程，再补处理乱序到达的抵消：
        # 12306 邮件可能乱序投递（如退票邮件早于购票邮件），仅按顺序抵消会漏掉。
        effective_records = []
        pending_cancellations = []
        for record in tracked_records:
            record_type = record.get('type')

            if record_type == 'purchase':
                effective_records.append(record)
                continue

            if record_type == 'change':
                self._fill_change_delta(record, order_passenger_face)
                removed = self._remove_matching_active_record(effective_records, record)
                effective_records.append(record)
                if removed is None:
                    pending_cancellations.append(record)
                continue

            if record_type == 'refund':
                removed = self._remove_matching_active_record(effective_records, record)
                if removed is None:
                    pending_cancellations.append(record)

        # 第二遍：处理乱序到达的抵消（退票邮件早于购票邮件）
        for record in pending_cancellations:
            if record.get('type') == 'refund':
                self._remove_matching_active_record(effective_records, record)

        resolved_records, _ = self._resolve_conflicting_final_records(effective_records)
        return resolved_records

    def _fill_change_delta(self, record, order_passenger_face):
        """
        改签邮件常只写"新车票票款共计 X"、不写补收/退差金额。
        当改签记录缺补差/退差时，用「新车票面 - 该乘客原购票票面」推算：
          新 > 原 → 补差（actual_spent_amount）
          新 < 原 → 退差（actual_refund_amount）
        等价改签（差额为 0）则两者均为 0。
        注意：改签可能只涉及订单内部分乘客，故按 (订单, 乘客) 匹配原票面，
        不能用整单票面合计（会把未改签乘客的票也算进去）。
        """
        if record.get('actual_spent_amount') is not None or record.get('actual_refund_amount') is not None:
            return

        new_face = float(record.get('price', 0) or 0)
        key = (record.get('order_number'), record.get('passenger_name') or '')
        orig_face = order_passenger_face.get(key, 0.0)
        delta = round(new_face - orig_face, 2)
        if delta > 0:
            record['actual_spent_amount'] = delta
            record['actual_refund_amount'] = 0.0
        elif delta < 0:
            record['actual_spent_amount'] = 0.0
            record['actual_refund_amount'] = -delta
        else:
            record['actual_spent_amount'] = 0.0
            record['actual_refund_amount'] = 0.0

    def _get_record_cashflow(self, record):
        """
        获取单条记录对现金流的影响
        返回: (spent, refunded)
        """
        record_type = record.get('type')
        price = float(record.get('price', 0) or 0)
        actual_spent = record.get('actual_spent_amount')
        actual_refunded = record.get('actual_refund_amount')

        if record_type == 'purchase':
            spent = float(actual_spent if actual_spent is not None else price)
            return spent, 0.0

        if record_type == 'refund':
            refunded = float(actual_refunded if actual_refunded is not None else price)
            return 0.0, refunded

        if record_type == 'change':
            spent = float(actual_spent) if actual_spent is not None else 0.0
            refunded = float(actual_refunded) if actual_refunded is not None else 0.0
            return spent, refunded

        return 0.0, 0.0

    def _dedupe_refund_records(self, records):
        """
        去重退票通知：12306 对同一笔退票可能按票面价和实付价各发一封通知，
        退款到账金额不可能超过实付金额，故同订单同乘客只保留实退金额最小的一条
        （即真实到账），其余视为重复通知。
        """
        refund_groups = defaultdict(list)
        passthrough = []
        for record in records:
            if record.get('type') == 'refund' and record.get('order_number') \
                    and record.get('actual_refund_amount') is not None:
                key = (record['order_number'], record.get('passenger_name') or '')
                refund_groups[key].append(record)
            else:
                passthrough.append(record)

        deduped = list(passthrough)
        for group in refund_groups.values():
            if len(group) == 1:
                deduped.append(group[0])
            else:
                deduped.append(min(group, key=lambda r: float(r.get('actual_refund_amount') or 0)))
        return deduped

    def _get_refund_fee_total(self, records):
        """
        退票手续费合计：同订单同乘客去重后各笔退票费之和。
        提前退票（未到扣费时段）退票费为 0，临近发车退票按阶梯扣费。
        """
        refund_groups = defaultdict(list)
        for record in records:
            if record.get('type') == 'refund' and record.get('order_number') \
                    and record.get('refund_fee') is not None:
                key = (record['order_number'], record.get('passenger_name') or '')
                refund_groups[key].append(record)

        return round(sum(min(float(r['refund_fee']) for r in group)
                         for group in refund_groups.values()), 2)

    def _get_change_fee_total(self, records):
        """
        改签手续费合计：改签为低票价时，差价部分按退票比例扣手续费。
        改签邮件（新格式）写"新车票款"与"实退票款"，但不写"应退原票款"，
        故手续费 = (原票面 - 新票面) - 实退金额。
        仅能从有"实退票款"的新格式改签邮件推算；旧格式邮件无此字段，无法统计。
        """
        total = 0.0
        # 同(订单,乘客)的原购票票面
        orig_face = defaultdict(float)
        for record in records:
            if record.get('type') == 'purchase' and record.get('order_number'):
                key = (record['order_number'], record.get('passenger_name') or '')
                orig_face[key] += float(record.get('price', 0) or 0)

        for record in records:
            if record.get('type') != 'change':
                continue
            # 仅当邮件明确写了"实退/应退票款"时才能推算手续费；
            # 旧格式邮件无此字段，实退为推算值，无法可靠计算手续费。
            if not record.get('_has_explicit_refund'):
                continue
            actual_refund = record.get('actual_refund_amount')
            if actual_refund is None:
                continue
            new_face = float(record.get('price', 0) or 0)
            key = (record.get('order_number'), record.get('passenger_name') or '')
            orig = orig_face.get(key, 0.0)
            if orig <= new_face:
                continue  # 非"改低"，无退差价，不涉及手续费
            should_refund = round(orig - new_face, 2)
            fee = round(should_refund - float(actual_refund), 2)
            if fee > 0.01:
                total += fee
        return round(total, 2)

    def _cashflow_refund_records(self, records):
        """
        现金流可用的退票记录：
        1. 同订单同乘客只保留实退金额最小的一条（12306 会按票面/实付各发一封通知）；
        2. 剔除无对应购票/改签记录的孤儿退款——购票邮件不在邮箱留存时
          （如窗口购票、线上退票），单独记退款只会产生无意义的负数。
        """
        paired_orders = {r.get('order_number') for r in records
                         if r.get('type') in ('purchase', 'change') and r.get('order_number')}
        return [r for r in self._dedupe_refund_records(records)
                if r.get('type') != 'refund'
                or not r.get('order_number')
                or r.get('order_number') in paired_orders]

    def _sum_cashflow(self, records):
        """汇总记录的实际消费与退款金额"""
        _, superseded_records = self._resolve_conflicting_final_records(
            [r for r in records if r.get('type') in ('purchase', 'change')]
        )
        superseded_ids = {id(record) for record in superseded_records}

        total_spent = 0.0
        total_refunded = 0.0

        for record in self._cashflow_refund_records(records):
            if id(record) in superseded_ids:
                continue
            spent, refunded = self._get_record_cashflow(record)
            total_spent += spent
            total_refunded += refunded

        return round(total_spent, 2), round(total_refunded, 2)
    
    def get_overview_stats(self, records=None):
        """
        获取总体统计信息
        :param records: 要分析的记录列表，默认为全部数据
        :return: 统计信息字典
        """
        if records is None:
            records = self.records
        
        if not records:
            return {}
        
        purchase_records = [r for r in records if r.get('type') == 'purchase']
        effective_purchase_records = self._get_effective_purchase_records(records)
        refund_records = [r for r in records if r.get('type') == 'refund']
        change_records = [r for r in records if r.get('type') == 'change']
        
        total_spent, total_refunded = self._sum_cashflow(
            purchase_records + refund_records + change_records
        )
        
        # 获取日期范围
        dates = [r['_datetime'] for r in records if '_datetime' in r]

        # 计算平均票价（与座位/列车/乘客/月度等统计同口径：抵消退改后的有效行程）
        if effective_purchase_records:
            avg_price = sum(r.get('price', 0) for r in effective_purchase_records if 'price' in r) / len(effective_purchase_records)
        else:
            avg_price = 0

        # 金额模型：
        #   消费总额 = 实际净支出 = 购票实付 + 改签补差 - 改签退差 - 退票退款
        #   退改费用 = 退票手续费 + 改签手续费（退票/改签因时间原因被扣的费用）
        net_spent = round(total_spent - total_refunded, 2)
        refund_fee_total = self._get_refund_fee_total(records)
        change_fee_total = self._get_change_fee_total(records)
        refund_change_fee = round(refund_fee_total + change_fee_total, 2)

        stats = {
            'total_records': len(records),
            'purchase_count': len(effective_purchase_records),
            'ticket_purchase_count': len(purchase_records),
            'refund_count': len(refund_records),
            'change_count': len(change_records),
            'total_spent': total_spent,
            'total_refunded': total_refunded,
            'net_spent': net_spent,
            'refund_fee_total': refund_fee_total,
            'change_fee_total': change_fee_total,
            'refund_change_fee': refund_change_fee,
            'avg_ticket_price': round(avg_price, 2),
            'date_range': {
                'start': min(dates).strftime("%Y-%m-%d %H:%M:%S") if dates else None,
                'end': max(dates).strftime("%Y-%m-%d %H:%M:%S") if dates else None,
            }
        }

        return stats
    
    def get_yearly_stats(self, records=None):
        """
        获取年度统计信息
        :param records: 要分析的记录列表
        :return: 年度统计列表
        """
        if records is None:
            records = self.records
        
        if not records:
            return []
        
        # 按年份分组（使用出发日期的年份，如果没有则用邮件接收日期）
        yearly_data = defaultdict(list)
        for record in records:
            # 优先使用出发日期的年份
            year = record.get('_year')
            if not year and '_datetime' in record:
                year = record['_datetime'].year
            if year:
                yearly_data[year].append(record)
        
        yearly_stats = []
        
        for year in sorted(yearly_data.keys()):
            year_records = yearly_data[year]
            
            purchase_records = [r for r in year_records if r.get('type') == 'purchase']
            effective_purchase_records = self._get_effective_purchase_records(year_records)
            refund_records = [r for r in year_records if r.get('type') == 'refund']
            change_records = [r for r in year_records if r.get('type') == 'change']
            
            total_spent, total_refunded = self._sum_cashflow(
                purchase_records + refund_records + change_records
            )
            net_spent = round(total_spent - total_refunded, 2)

            avg_price = (
                sum(r.get('price', 0) for r in effective_purchase_records if 'price' in r) / len(effective_purchase_records)
                if effective_purchase_records else 0
            )
            refund_fee_total = self._get_refund_fee_total(year_records)

            stat = {
                'year': year,
                'total_trips': len(effective_purchase_records),
                'refund_count': len(refund_records),
                'total_spent': total_spent,
                'total_refunded': total_refunded,
                'net_spent': net_spent,
                'refund_fee_total': refund_fee_total,
                'avg_price': round(avg_price, 2),
            }
            
            yearly_stats.append(stat)
        
        return yearly_stats
    
    def get_popular_cities(self, records=None):
        """
        获取热门城市统计
        :param records: 要分析的记录列表
        :return: 城市统计字典（departures/arrivals/routes，各取前 10）
        """
        if records is None:
            records = self.records
        
        if not records:
            return []
        
        purchase_records = self._get_effective_purchase_records(records)

        # 统计出发城市
        departure_counter = Counter()
        arrival_counter = Counter()
        city_pair_counter = Counter()
        departure_spent = defaultdict(float)
        arrival_spent = defaultdict(float)
        route_spent = defaultdict(float)
        departure_last = defaultdict(lambda: datetime.min)
        arrival_last = defaultdict(lambda: datetime.min)
        route_last = defaultdict(lambda: datetime.min)

        for record in purchase_records:
            dep_station = record.get('departure_station', '')
            arr_station = record.get('arrival_station', '')
            price = float(record.get('price', 0) or 0)
            dt = record.get('_datetime') or record.get('_event_datetime')

            dep_city = self._extract_city_name(dep_station) if dep_station else ''
            arr_city = self._extract_city_name(arr_station) if arr_station else ''
            # 同城行程（如 北京北→八达岭长城，归并后同为"北京"）不计入出发/到达城市次数
            same_city = bool(dep_city and arr_city and dep_city == arr_city)

            if dep_station and not same_city:
                departure_counter[dep_city] += 1
                departure_spent[dep_city] += price
                if dt and dt > departure_last[dep_city]:
                    departure_last[dep_city] = dt

            if arr_station and not same_city:
                arrival_counter[arr_city] += 1
                arrival_spent[arr_city] += price
                if dt and dt > arrival_last[arr_city]:
                    arrival_last[arr_city] = dt

            if dep_station and arr_station:
                dep_station_name = self._normalize_station_name(dep_station)
                arr_station_name = self._normalize_station_name(arr_station)
                route_key = f"{dep_station_name}→{arr_station_name}"
                city_pair_counter[route_key] += 1
                route_spent[route_key] += price
                if dt and dt > route_last[route_key]:
                    route_last[route_key] = dt

        # 格式化结果（次数降序，同次数按最近乘坐降序，各取前 10）
        popular_departures = [
            {'city': city, 'count': count, 'total_spent': round(departure_spent[city], 2),
             'avg_price': round(departure_spent[city] / count, 2),
             'last_departure': departure_last[city] if departure_last[city] != datetime.min else None,
             'type': '出发'}
            for city, count in departure_counter.most_common()
        ]
        popular_departures = self._sort_by_count_then_recent(popular_departures)[:10]

        popular_arrivals = [
            {'city': city, 'count': count, 'total_spent': round(arrival_spent[city], 2),
             'avg_price': round(arrival_spent[city] / count, 2),
             'last_departure': arrival_last[city] if arrival_last[city] != datetime.min else None,
             'type': '到达'}
            for city, count in arrival_counter.most_common()
        ]
        popular_arrivals = self._sort_by_count_then_recent(popular_arrivals)[:10]

        popular_routes = [
            {'route': route, 'count': count, 'total_spent': round(route_spent[route], 2),
             'avg_price': round(route_spent[route] / count, 2),
             'last_departure': route_last[route] if route_last[route] != datetime.min else None}
            for route, count in city_pair_counter.most_common()
        ]
        popular_routes = self._sort_by_count_then_recent(popular_routes)[:10]

        return {
            'departures': popular_departures,
            'arrivals': popular_arrivals,
            'routes': popular_routes,
        }
    
    def get_popular_trains(self, records=None):
        """
        获取常坐列车统计
        :param records: 要分析的记录列表
        :return: 列车统计列表（前 10）
        """
        if records is None:
            records = self.records
        
        if not records:
            return []
        
        purchase_records = self._get_effective_purchase_records(records)

        train_counter = Counter()
        train_prices = defaultdict(list)
        train_net = defaultdict(float)
        train_last = defaultdict(lambda: datetime.min)

        for record in purchase_records:
            if 'train_number' in record:
                train = record['train_number']
                train_counter[train] += 1
                if 'price' in record:
                    train_prices[train].append(record['price'])
                    train_net[train] += float(record.get('price', 0) or 0)
                dt = record.get('_datetime') or record.get('_event_datetime')
                if dt and dt > train_last[train]:
                    train_last[train] = dt

        popular_trains = []
        for train, count in train_counter.most_common():
            prices = train_prices.get(train, [])
            avg_price = sum(prices) / len(prices) if prices else 0

            popular_trains.append({
                'train_number': train,
                'count': count,
                'avg_price': round(avg_price, 2),
                'total_spent': round(train_net[train], 2),
                'last_departure': train_last[train] if train_last[train] != datetime.min else None,
            })

        popular_trains = self._sort_by_count_then_recent(popular_trains)[:10]
        return popular_trains
    
    def get_seat_type_stats(self, records=None):
        """
        获取座位类型统计
        :param records: 要分析的记录列表
        :return: 座位类型统计列表
        """
        if records is None:
            records = self.records
        
        if not records:
            return []
        
        purchase_records = self._get_effective_purchase_records(records)

        seat_counter = Counter()
        seat_prices = defaultdict(list)
        seat_last = defaultdict(lambda: datetime.min)

        for record in purchase_records:
            if 'seat_type' in record:
                seat = record['seat_type']
                seat_counter[seat] += 1
                if 'price' in record:
                    seat_prices[seat].append(record['price'])
                dt = record.get('_datetime') or record.get('_event_datetime')
                if dt and dt > seat_last[seat]:
                    seat_last[seat] = dt

        seat_stats = []
        for seat_type, count in seat_counter.most_common():
            prices = seat_prices.get(seat_type, [])
            avg_price = sum(prices) / len(prices) if prices else 0
            total_spent = sum(prices)

            seat_stats.append({
                'seat_type': seat_type,
                'count': count,
                'avg_price': round(avg_price, 2),
                'total_spent': round(total_spent, 2),
                'last_departure': seat_last[seat_type] if seat_last[seat_type] != datetime.min else None,
            })

        seat_stats = self._sort_by_count_then_recent(seat_stats)[:10]
        return seat_stats
    
    def get_passenger_stats(self, records=None):
        """
        获取乘客统计（如果有乘客信息）
        出行次数按有效行程计；金额按实际现金流（消费/退款）计。
        仅列出有有效行程的乘客：购票后全部退票、或退款缺少对应购票记录的不单列。
        :param records: 要分析的记录列表
        :return: 乘客统计列表
        """
        if records is None:
            records = self.records

        if not records:
            return []

        effective_purchase_records = self._get_effective_purchase_records(records)

        trip_counter = Counter()
        for record in effective_purchase_records:
            passenger = record.get('passenger_name') or '未知'
            trip_counter[passenger] += 1

        # 现金流按乘客聚合（剔除冲突消解中被取代的记录，与总览同口径）
        _, superseded_records = self._resolve_conflicting_final_records(
            [r for r in records if r.get('type') in ('purchase', 'change')]
        )
        superseded_ids = {id(record) for record in superseded_records}

        flow = defaultdict(lambda: [0.0, 0.0])
        for record in self._cashflow_refund_records(records):
            if id(record) in superseded_ids:
                continue
            passenger = record.get('passenger_name') or '未知'
            spent, refunded = self._get_record_cashflow(record)
            flow[passenger][0] += spent
            flow[passenger][1] += refunded

        passenger_stats = []
        for passenger in set(trip_counter) | set(flow):
            spent, refunded = flow.get(passenger, [0.0, 0.0])
            entry = {
                'passenger_name': passenger,
                'trip_count': trip_counter.get(passenger, 0),
                'total_spent': round(spent, 2),
                'total_refunded': round(refunded, 2),
                'net_spent': round(spent - refunded, 2),
            }
            # 出行 0 次的乘客不单列（购票后全部退票、或仅有孤儿退款）；全零行同样过滤
            if entry['trip_count'] == 0:
                continue
            passenger_stats.append(entry)

        passenger_stats.sort(key=lambda x: (-x['trip_count'], -x['net_spent']))
        return passenger_stats

    def get_departure_time_ranking(self, records=None):
        """
        获取出发时间段排行榜（按小时统计）
        :param records: 要分析的记录列表
        :return: 时间段统计列表，格式: [{'hour_range': '06:00-07:00', 'count': 10}, ...]
        """
        if records is None:
            records = self.records
        
        if not records:
            return []
        
        purchase_records = self._get_effective_purchase_records(records)
        
        # 统计每个小时的出发次数与最近出发时间
        hour_counter = Counter()
        hour_last = defaultdict(lambda: datetime.min)

        for record in purchase_records:
            dep_time = record.get('departure_datetime')
            if dep_time:
                try:
                    if ' ' in dep_time:
                        time_part = dep_time.split(' ')[1][:5]
                    else:
                        time_part = dep_time[:5]

                    hour = int(time_part.split(':')[0])
                    hour_counter[hour] += 1
                    dt = record.get('_datetime') or record.get('_event_datetime')
                    if dt and dt > hour_last[hour]:
                        hour_last[hour] = dt
                except:
                    continue

        # 转换为时间段格式并排序
        ranking = []
        for hour in range(24):
            count = hour_counter.get(hour, 0)
            if count > 0:
                ranking.append({
                    'hour_range': f"{hour:02d}:00-{(hour+1)%24:02d}:00",
                    'count': count,
                    'last_departure': hour_last[hour] if hour_last[hour] != datetime.min else None,
                    'hour': hour
                })
        
        # 次数降序，次数相同按最近出发时间降序，最多 10 个时段
        ranking = self._sort_by_count_then_recent(ranking)[:10]

        logger.info(f"出发时间段排行榜统计完成，共{len(ranking)}个时段")
        return ranking

    def _sort_by_count_then_recent(self, items):
        """
        通用排序：次数降序，次数相同时按最近乘坐时间降序（近的在前）。
        items 中每项需含 'count' 和 'last_departure'（datetime 或 None）。
        """
        return sorted(items, key=lambda x: (-x['count'], -(x['last_departure'] or datetime.min).timestamp()))
    
    def _extract_city_name(self, station_name):
        """
        从站点名称提取城市名
        :param station_name: 站点名称
        :return: 城市名
        """
        if not station_name:
            return ""
        
        municipalities = ['北京', '上海', '天津', '重庆', '香港', '澳门']
        for municipality in municipalities:
            if station_name.startswith(municipality):
                return municipality

        # 去掉常见后缀（按长度从长到短排序，优先匹配长的）
        city = station_name
        suffixes = ['火车站', '高铁站', '动车站', '城际站', '东站', '西站', '南站', '北站', '站', '东', '西', '南', '北']
        
        for suffix in suffixes:
            if city.endswith(suffix):
                city = city[:-len(suffix)]
                break
        
        # 应用城市别名映射，将站点名合并到主城市
        if city in self.city_mapping:
            city = self.city_mapping[city]
        
        return city

    def _normalize_station_name(self, station_name):
        """
        标准化站点名称，用于路线聚合
        例如：北京西/北京西站 -> 北京西，郑州/郑州站 -> 郑州
        """
        if not station_name:
            return ""

        name = station_name.strip()
        if name.endswith('站'):
            name = name[:-1]

        return name
    
    def generate_full_report(self, start_year=None, end_year=None, start_month=None, end_month=None):
        """
        生成完整分析报告
        :param start_year: 开始年份
        :param end_year: 结束年份
        :param start_month: 开始月份
        :param end_month: 结束月份
        :return: 报告数据字典
        """
        logger.info("开始生成分析报告...")
        
        # 过滤数据
        filtered_records = self._filter_records(start_year, end_year, start_month, end_month)
        
        if not filtered_records:
            logger.warning("过滤后没有数据")
            return {}
        
        # 生成各项统计
        report = {
            'overview': self.get_overview_stats(filtered_records),
            'yearly_stats': self.get_yearly_stats(filtered_records),
            'popular_cities': self.get_popular_cities(filtered_records),
            'popular_trains': self.get_popular_trains(filtered_records),
            'seat_type_stats': self.get_seat_type_stats(filtered_records),
            'passenger_stats': self.get_passenger_stats(filtered_records),
            'departure_time_ranking': self.get_departure_time_ranking(filtered_records),
            'filter_info': {
                'start_year': start_year,
                'end_year': end_year,
                'start_month': start_month,
                'end_month': end_month,
            }
        }

        logger.info("报告生成完成")
        return report
