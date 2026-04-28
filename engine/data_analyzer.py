"""
数据分析模块 - 对12306票务记录进行统计分析（纯原生实现）
"""
from datetime import datetime
from collections import Counter, defaultdict
import logging

logger = logging.getLogger(__name__)


class DataAnalyzer:
    """数据分析器"""
    
    def __init__(self, records):
        """
        初始化分析器
        :param records: 票务记录列表
        """
        self.records = records
        self._prepare_data()
    
    def _prepare_data(self):
        """数据预处理，添加日期字段"""
        if not self.records:
            logger.warning("没有记录可供分析")
            return
        
        for record in self.records:
            try:
                # 优先使用出发日期（departure_datetime），如果没有则使用邮件接收日期（date）
                date_str = record.get('departure_datetime') or record.get('date')
                
                if date_str and isinstance(date_str, str):
                    # 尝试多种日期格式
                    parsed = False
                    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z"]:
                        try:
                            dt = datetime.strptime(date_str[:19], fmt[:19])
                            record['_datetime'] = dt
                            record['_year'] = dt.year
                            record['_month'] = dt.month
                            record['_year_month'] = f"{dt.year}-{dt.month:02d}"
                            parsed = True
                            break
                        except:
                            continue
                    
                    if not parsed:
                        logger.debug(f"无法解析日期: {date_str}")
            except Exception as e:
                logger.debug(f"日期解析失败: {e}")
        
        logger.info(f"已准备 {len(self.records)} 条记录用于分析")
    
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
        departure_station = record.get('departure_station') or ''
        arrival_station = record.get('arrival_station') or ''
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

    def _get_effective_purchase_records(self, records):
        """
        获取有效出行记录
        已退票、已改签对应的原购票记录不再计入出行次数、城市、路线、座位等统计
        """
        purchase_records = [r for r in records if r.get('type') == 'purchase']
        canceled_records = [r for r in records if r.get('type') in ('refund', 'change')]

        canceled_counter = Counter()
        for record in canceled_records:
            for key in self._build_trip_keys(record):
                canceled_counter[key] += 1

        effective_records = []
        for record in purchase_records:
            for key in self._build_trip_keys(record):
                if canceled_counter[key] > 0:
                    canceled_counter[key] -= 1
                    break
            else:
                effective_records.append(record)

        return effective_records

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

    def _sum_cashflow(self, records):
        """汇总记录的实际消费与退款金额"""
        total_spent = 0.0
        total_refunded = 0.0

        for record in records:
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
        
        stats = {
            'total_records': len(records),
            'purchase_count': len(effective_purchase_records),
            'ticket_purchase_count': len(purchase_records),
            'refund_count': len(refund_records),
            'change_count': len(change_records),
            'total_spent': total_spent,
            'total_refunded': total_refunded,
            'net_spent': round(total_spent - total_refunded, 2),
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
            
            avg_price = (
                sum(r.get('price', 0) for r in purchase_records if 'price' in r) / len(purchase_records)
                if purchase_records else 0
            )
            
            stat = {
                'year': year,
                'total_trips': len(effective_purchase_records),
                'refund_count': len(refund_records),
                'total_spent': total_spent,
                'total_refunded': total_refunded,
                'avg_price': round(avg_price, 2),
            }
            
            stat['net_spent'] = round(stat['total_spent'] - stat['total_refunded'], 2)
            
            yearly_stats.append(stat)
        
        return yearly_stats
    
    def get_popular_cities(self, records=None, top_n=20):
        """
        获取热门城市统计
        :param records: 要分析的记录列表
        :param top_n: 返回前N个城市
        :return: 城市统计列表
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
        
        for record in purchase_records:
            dep_station = record.get('departure_station', '')
            arr_station = record.get('arrival_station', '')
            
            if dep_station:
                dep_city = self._extract_city_name(dep_station)
                departure_counter[dep_city] += 1
            
            if arr_station:
                arr_city = self._extract_city_name(arr_station)
                arrival_counter[arr_city] += 1
            
            if dep_station and arr_station:
                dep_station_name = self._normalize_station_name(dep_station)
                arr_station_name = self._normalize_station_name(arr_station)
                city_pair_counter[f"{dep_station_name}→{arr_station_name}"] += 1
        
        # 合并出发和到达统计
        all_cities = Counter()
        all_cities.update(departure_counter)
        all_cities.update(arrival_counter)
        
        # 格式化结果
        popular_departures = [
            {'city': city, 'count': count, 'type': '出发'}
            for city, count in departure_counter.most_common(top_n)
        ]
        
        popular_arrivals = [
            {'city': city, 'count': count, 'type': '到达'}
            for city, count in arrival_counter.most_common(top_n)
        ]
        
        popular_routes = [
            {'route': route, 'count': count}
            for route, count in city_pair_counter.most_common(top_n)
        ]
        
        return {
            'departures': popular_departures,
            'arrivals': popular_arrivals,
            'routes': popular_routes,
            'all_cities': [{'city': city, 'count': count} 
                          for city, count in all_cities.most_common(top_n)]
        }
    
    def get_popular_trains(self, records=None, top_n=20):
        """
        获取常坐列车统计
        :param records: 要分析的记录列表
        :param top_n: 返回前N个列车
        :return: 列车统计列表
        """
        if records is None:
            records = self.records
        
        if not records:
            return []
        
        purchase_records = self._get_effective_purchase_records(records)
        
        train_counter = Counter()
        train_prices = defaultdict(list)
        
        for record in purchase_records:
            if 'train_number' in record:
                train = record['train_number']
                train_counter[train] += 1
                if 'price' in record:
                    train_prices[train].append(record['price'])
        
        popular_trains = []
        for train, count in train_counter.most_common(top_n):
            prices = train_prices.get(train, [])
            avg_price = sum(prices) / len(prices) if prices else 0
            
            popular_trains.append({
                'train_number': train,
                'count': count,
                'avg_price': round(avg_price, 2)
            })
        
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
        
        for record in purchase_records:
            if 'seat_type' in record:
                seat = record['seat_type']
                seat_counter[seat] += 1
                if 'price' in record:
                    seat_prices[seat].append(record['price'])
        
        seat_stats = []
        for seat_type, count in seat_counter.most_common():
            prices = seat_prices.get(seat_type, [])
            avg_price = sum(prices) / len(prices) if prices else 0
            total_spent = sum(prices)
            
            seat_stats.append({
                'seat_type': seat_type,
                'count': count,
                'avg_price': round(avg_price, 2),
                'total_spent': round(total_spent, 2)
            })
        
        return seat_stats
    
    def get_monthly_trend(self, records=None, year=None):
        """
        获取月度消费趋势
        :param records: 要分析的记录列表
        :param year: 指定年份，None表示所有年份
        :return: 月度趋势数据
        """
        if records is None:
            records = self.records
        
        if not records:
            return []
        
        purchase_records = self._get_effective_purchase_records(records)
        
        if year:
            purchase_records = [r for r in purchase_records if r.get('_year') == year]
        
        # 按月统计
        monthly_data = defaultdict(lambda: {'prices': [], 'count': 0})
        
        for record in purchase_records:
            if '_year_month' in record and 'price' in record:
                month = record['_year_month']
                monthly_data[month]['prices'].append(record['price'])
                monthly_data[month]['count'] += 1
        
        result = []
        for month in sorted(monthly_data.keys()):
            data = monthly_data[month]
            prices = data['prices']
            result.append({
                'month': month,
                'total_spent': round(sum(prices), 2),
                'trip_count': data['count'],
                'avg_price': round(sum(prices) / len(prices), 2) if prices else 0
            })
        
        return result
    
    def get_passenger_stats(self, records=None):
        """
        获取乘客统计（如果有乘客信息）
        :param records: 要分析的记录列表
        :return: 乘客统计列表
        """
        if records is None:
            records = self.records
        
        if not records:
            return []
        
        purchase_records = self._get_effective_purchase_records(records)
        
        passenger_counter = Counter()
        passenger_prices = defaultdict(list)
        
        for record in purchase_records:
            if 'passenger_name' in record:
                passenger = record['passenger_name']
                passenger_counter[passenger] += 1
                if 'price' in record:
                    passenger_prices[passenger].append(record['price'])
        
        passenger_stats = []
        for passenger, count in passenger_counter.most_common():
            prices = passenger_prices.get(passenger, [])
            total_spent = sum(prices)
            
            passenger_stats.append({
                'passenger_name': passenger,
                'trip_count': count,
                'total_spent': round(total_spent, 2)
            })
        
        return passenger_stats
    
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
            'monthly_trend': self.get_monthly_trend(filtered_records),
            'passenger_stats': self.get_passenger_stats(filtered_records),
            'filter_info': {
                'start_year': start_year,
                'end_year': end_year,
                'start_month': start_month,
                'end_month': end_month,
            }
        }
        
        logger.info("报告生成完成")
        return report
