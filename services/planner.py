from models.schemas import (
    TravelInput, TravelPlan, TransportItem, HotelItem, DayPlan,
    Activity, RestaurantItem, AttractionItem, CostBreakdown
)
from typing import Optional
from datetime import datetime, timedelta
from services.serpapi_client import (
    geocode, search_flights, search_hotels, search_places,
    search_places_bilingual, search_top_sights, rank_places, merge_places,
    estimate_flight_cost, SERPAPI_API_KEY
)

PACE_MULTIPLIER = {
    "thoải mái": (1, 2),
    "vừa phải": (2, 3),
    "nhanh": (3, 4),
}

MEAL_COST = {
    "sang": (30000, 50000),
    "trua": (50000, 150000),
    "toi": (100000, 300000),
}

HOTEL_PRICE_FALLBACK = {
    "2 sao": (300000, 500000),
    "3 sao": (500000, 800000),
    "4 sao": (800000, 1500000),
    "5 sao": (1500000, 3000000),
}

POPULAR_DESTINATIONS = [
    "Hà Nội", "TP. Hồ Chí Minh", "Đà Nẵng", "Hội An", "Huế",
    "Nha Trang", "Phú Quốc", "Đà Lạt", "Sapa", "Hạ Long",
    "Bangkok", "Tokyo", "Seoul", "Singapore", "Paris",
    "London", "New York", "Sydney", "Bali", "Dubai",
]


def get_supported_destinations() -> list[str]:
    return POPULAR_DESTINATIONS


def _price_level_to_vnd(level: str) -> str:
    mapping = {
        "$": "20.000 - 50.000 VND",
        "$$": "50.000 - 150.000 VND",
        "$$$": "150.000 - 300.000 VND",
        "$$$$": "300.000 - 500.000 VND",
        "$$$$$": "500.000+ VND",
    }
    return mapping.get(level.strip(), "50.000 - 150.000 VND")


def _estimate_cost(input_data: TravelInput, transport_items: list, hotel_items: list, restaurant_items: list) -> CostBreakdown:
    people = input_data.adults + input_data.children

    transport_total = 0
    for t in transport_items:
        p = t.get("_gia_min") or 0
        if p:
            transport_total += p * input_data.adults
    if transport_total == 0:
        transport_total = 2000000 * input_data.adults

    hotel_total = 0
    hotel_detail = "Liên hệ"
    if hotel_items:
        prices = []
        for h in hotel_items:
            p = h.get("_gia_min")
            if p:
                prices.append(p)
        if prices:
            avg = sum(prices) // len(prices)
            num_rooms = (input_data.adults + 1) // 2
            hotel_total = avg * (input_data.days - 1) * num_rooms
            hotel_detail = f"{hotel_total:,.0f} VND ({input_data.days - 1} đêm x {num_rooms} phòng)"
    if hotel_total == 0:
        hotel_level = input_data.hotel_level or "3 sao"
        h_range = HOTEL_PRICE_FALLBACK.get(hotel_level, HOTEL_PRICE_FALLBACK["3 sao"])
        avg = (h_range[0] + h_range[1]) // 2
        num_rooms = (input_data.adults + 1) // 2
        hotel_total = avg * (input_data.days - 1) * num_rooms
        hotel_detail = f"{hotel_total:,.0f} VND ({input_data.days - 1} đêm x {num_rooms} phòng)"

    meal_total = 0
    for meal, (low, high) in MEAL_COST.items():
        avg = (low + high) // 2
        meal_total += avg * people * input_data.days
    meal_total = meal_total // 3 * 3

    local_transport_per_day = 100000
    local_total = local_transport_per_day * input_data.days

    attraction_total = 200000 * people

    subtotal = transport_total + hotel_total + meal_total + local_total + attraction_total
    misc = int(subtotal * 0.1)
    total = subtotal + misc

    chenh_lech = None
    ngan_sach = None
    if input_data.budget:
        ngan_sach = f"{input_data.budget:,.0f} VND"
        diff = total - input_data.budget
        if diff > 0:
            chenh_lech = f"+{diff:,.0f} VND (vượt ngân sách)"
        elif diff < 0:
            chenh_lech = f"{diff:,.0f} VND (trong ngân sách)"
        else:
            chenh_lech = "0 VND (bằng ngân sách)"

    return CostBreakdown(
        ve_di_chuyen=f"{transport_total:,.0f} VND",
        khach_san=hotel_detail,
        an_uong=f"{meal_total:,.0f} VND",
        di_chuyen_noi_thanh=f"{local_total:,.0f} VND",
        ve_tham_quan=f"{attraction_total:,.0f} VND",
        chi_phi_phat_sinh=f"{misc:,.0f} VND (10%)",
        tong=f"{total:,.0f} VND",
        ngan_sach=ngan_sach,
        chenh_lech=chenh_lech,
    )


def _build_itinerary(input_data: TravelInput, attractions: list[AttractionItem], restaurants: list[RestaurantItem]) -> list[DayPlan]:
    min_attr, max_attr = PACE_MULTIPLIER.get(input_data.pace, (2, 3))
    if input_data.children > 0 or (input_data.special_requirements and "người già" in input_data.special_requirements.lower()):
        max_attr = max(1, max_attr - 1)

    r_idx = 0
    plans = []
    attr_idx = 0

    for day in range(1, input_data.days + 1):
        day_attrs = []
        for _ in range(max_attr):
            if attr_idx < len(attractions):
                day_attrs.append(attractions[attr_idx])
                attr_idx += 1

        day_restaurants = []
        for _ in range(3):
            if r_idx < len(restaurants):
                day_restaurants.append(restaurants[r_idx])
                r_idx += 1

        buoi_sang = [Activity(gio="07:00", mo_ta="Thức dậy và vệ sinh cá nhân")]
        if day == 1:
            buoi_sang.append(Activity(gio="07:30", mo_ta="Check-in khách sạn / gửi hành lý"))
        if day_restaurants:
            buoi_sang.append(Activity(gio="08:00", mo_ta=f"Ăn sáng tại {day_restaurants[0].ten_quan}"))
        if day_attrs:
            buoi_sang.append(Activity(gio="09:00", mo_ta=f"Tham quan {day_attrs[0].diem}"))

        buoi_trua = [Activity(gio="11:30", mo_ta="Nghỉ ngơi")]
        if len(day_restaurants) > 1:
            buoi_trua.append(Activity(gio="12:00", mo_ta=f"Ăn trưa tại {day_restaurants[1].ten_quan}"))
        if day == 1:
            buoi_trua.append(Activity(gio="13:30", mo_ta="Check-in khách sạn chính thức"))
        buoi_trua.append(Activity(gio="14:00", mo_ta="Nghỉ trưa"))

        buoi_chieu = []
        if len(day_attrs) > 1:
            buoi_chieu.append(Activity(gio="15:00", mo_ta=f"Tham quan {day_attrs[1].diem}"))
        buoi_chieu.append(Activity(gio="17:00", mo_ta="Dạo phố / mua sắm tự do"))

        buoi_toi = []
        if len(day_restaurants) > 2:
            buoi_toi.append(Activity(gio="18:30", mo_ta=f"Ăn tối tại {day_restaurants[2].ten_quan}"))
        buoi_toi.append(Activity(gio="20:00", mo_ta="Hoạt động tự do / đi dạo buổi tối"))
        if len(day_attrs) > 2:
            buoi_toi.append(Activity(gio="21:00", mo_ta=f"Tham quan {day_attrs[2].diem}"))

        tieu_de = f"Ngày {day} - Khám phá {input_data.destination}"
        if day == input_data.days:
            tieu_de = f"Ngày {day} - Ngày cuối & trở về"

        plans.append(DayPlan(
            ngay=day,
            tieu_de=tieu_de,
            buoi_sang=buoi_sang,
            buoi_trua=buoi_trua,
            buoi_chieu=buoi_chieu,
            buoi_toi=buoi_toi,
        ))

    return plans


def _filter_transport(transport: list[dict], preferred_type: Optional[str]) -> list[dict]:
    if not preferred_type:
        return transport
    filtered = [t for t in transport if preferred_type.lower() in t["loai"].lower()]
    return filtered or transport


def _filter_hotels(hotels: list[dict], hotel_level: Optional[str]) -> list[dict]:
    if not hotel_level:
        return hotels[:3]
    level_map = {"2 sao": 0, "3 sao": 1, "4 sao": 2, "5 sao": 3}
    preferred = level_map.get(hotel_level, 1)
    if preferred == 0:
        filtered = [h for h in hotels if "hostel" in h["ten"].lower() or "homestay" in h["ten"].lower()]
        return filtered[:3] if filtered else hotels[:3]
    elif preferred >= 3:
        filtered = [h for h in hotels if h.get("rating", 0) >= 4.5]
        return filtered[:3] if filtered else hotels[:3]
    return hotels[:3]


def _filter_attractions(attractions: list[dict], interests: Optional[list[str]]) -> list[dict]:
    if not interests:
        return attractions
    interest_keywords = {
        "văn hóa": ["Văn hóa", "Chùa", "Nhà thờ", "Phố cổ", "Bảo tàng", "Museum", "Temple", "Church"],
        "ẩm thực": ["Food", "Chợ", "Market", "Restaurant", "Ẩm thực"],
        "thiên nhiên": ["Thiên nhiên", "Biển", "Hồ", "Núi", "Park", "Nature", "Beach", "Mountain"],
        "mua sắm": ["Mua sắm", "Chợ", "Market", "Mall", "Shopping"],
        "giải trí": ["Giải trí", "Amusement", "Entertainment", "Nightlife"],
        "lịch sử": ["Lịch sử", "Lăng", "Hoàng Thành", "History", "Heritage", "Monument"],
    }
    matched = []
    for interest in interests:
        keywords = interest_keywords.get(interest, [])
        for attr in attractions:
            text = (attr.get("type", "") + " " + attr.get("title", "") + " " + attr.get("description", ""))
            if any(kw.lower() in text.lower() for kw in keywords):
                if attr not in matched:
                    matched.append(attr)
    return matched or attractions


def _filter_restaurants(restaurants: list[dict], cuisine: Optional[str]) -> list[dict]:
    if not cuisine:
        return restaurants
    kw = cuisine.lower()
    filtered = [r for r in restaurants if kw in (r.get("title", "") + " " + r.get("description", "")).lower()]
    return filtered or restaurants


def generate_plan(input_data: TravelInput) -> TravelPlan:
    dest_geo = geocode(input_data.destination)
    dep_geo = geocode(input_data.departure)

    check_in = input_data.start_date.isoformat()
    check_out = (input_data.start_date + timedelta(days=input_data.days)).isoformat()

    transport = []
    if dest_geo and dep_geo and SERPAPI_API_KEY and SERPAPI_API_KEY != "thay_bang_api_key_cua_ban":
        try:
            dep_name = dep_geo.get("name", input_data.departure)
            arr_name = dest_geo.get("name", input_data.destination)
            transport = search_flights(dep_name, arr_name, check_in, check_out, input_data.adults, input_data.children)
        except Exception:
            pass

    if not transport:
        if dep_geo and dest_geo:
            transport = estimate_flight_cost(dep_geo["lat"], dep_geo["lng"], dest_geo["lat"], dest_geo["lng"])
        else:
            transport = estimate_flight_cost(21.0285, 105.8542, 16.0544, 108.2022)

    if input_data.transportation:
        transport = _filter_transport(transport, input_data.transportation)

    hotels = []
    if dest_geo and SERPAPI_API_KEY and SERPAPI_API_KEY != "thay_bang_api_key_cua_ban":
        try:
            hotels = search_hotels(input_data.destination, check_in, check_out, input_data.adults)
        except Exception:
            pass

    hotels = _filter_hotels(hotels, input_data.hotel_level)

    attractions_raw = []
    restaurants_raw = []
    if dest_geo and SERPAPI_API_KEY and SERPAPI_API_KEY != "thay_bang_api_key_cua_ban":
        # Nguồn chính: top_sights do Google tuyển chọn; chỉ gọi thêm Maps khi còn thiếu
        try:
            attractions_raw = search_top_sights(input_data.destination)
        except Exception:
            pass
        if len(attractions_raw) < 8:
            try:
                maps_attractions = search_places_bilingual(
                    dest_geo["lat"], dest_geo["lng"],
                    f"địa điểm du lịch tại {input_data.destination}",
                    f"top tourist attractions in {input_data.destination}"
                )
                attractions_raw = merge_places(attractions_raw, maps_attractions)
            except Exception:
                pass
        try:
            restaurants_raw = search_places_bilingual(
                dest_geo["lat"], dest_geo["lng"],
                f"nhà hàng tại {input_data.destination}",
                f"best restaurants in {input_data.destination}"
            )
        except Exception:
            pass

    # Fallback khi API không khả dụng: gợi ý chung, KHÔNG gắn rating giả
    dest = input_data.destination
    fallback_note = "Gợi ý chung — chưa có dữ liệu thực tế, hãy kiểm tra lại trước khi đi"
    if not attractions_raw:
        attractions_raw = [
            {"title": f"Chợ Trung tâm {dest}", "type": "Mua sắm", "address": f"Trung tâm {dest}", "description": fallback_note},
            {"title": f"Quảng trường {dest}", "type": "Thắng cảnh", "address": f"Trung tâm {dest}", "description": fallback_note},
            {"title": f"Khu phố đi bộ {dest}", "type": "Văn hóa", "address": f"Trung tâm {dest}", "description": fallback_note},
            {"title": f"Công viên trung tâm {dest}", "type": "Thiên nhiên", "address": f"{dest}", "description": fallback_note},
            {"title": f"Bảo tàng {dest}", "type": "Văn hóa", "address": f"Trung tâm {dest}", "description": fallback_note},
            {"title": f"Chùa {dest}", "type": "Văn hóa", "address": f"{dest}", "description": fallback_note},
        ]

    if not restaurants_raw:
        restaurants_raw = [
            {"title": f"Phở {dest}", "rating": 0, "price": "$", "type": "Quán ăn", "address": f"Trung tâm {dest}"},
            {"title": f"Bún bò {dest}", "rating": 0, "price": "$", "type": "Quán ăn", "address": f"Trung tâm {dest}"},
            {"title": f"Nhà hàng Hải sản {dest}", "rating": 0, "price": "$$$", "type": "Nhà hàng", "address": f"{dest}"},
            {"title": f"Cafe {dest}", "rating": 0, "price": "$", "type": "Cafe", "address": f"Trung tâm {dest}"},
            {"title": f"Quán ăn vặt {dest}", "rating": 0, "price": "$", "type": "Quán ăn", "address": f"Chợ {dest}"},
            {"title": f"Nhà hàng Đặc sản {dest}", "rating": 0, "price": "$$", "type": "Nhà hàng", "address": f"{dest}"},
        ]

    if input_data.interests:
        attractions_raw = _filter_attractions(attractions_raw, input_data.interests)

    if input_data.cuisine:
        restaurants_raw = _filter_restaurants(restaurants_raw, input_data.cuisine)

    # Xếp theo độ hot (rating × log số review) và loại kết quả rác
    attractions_raw = rank_places(attractions_raw)
    restaurants_raw = rank_places(restaurants_raw)

    transport_items = _map_transport_items(transport)
    hotel_items = _map_hotel_items(hotels)
    attraction_items = _map_attraction_items(attractions_raw, input_data)
    restaurant_items = _map_restaurant_items(restaurants_raw, input_data)

    lich_trinh = _build_itinerary(input_data, attraction_items, restaurant_items)

    costs = _estimate_cost(input_data, transport, hotels, restaurants_raw)

    tong_quan = _build_overview(input_data, costs, dest_geo)
    meo = _generate_tips(input_data)

    days = min(input_data.days, 4)
    restaurant_subset = restaurant_items[:days * 3]
    attraction_subset = attraction_items[:days * 2]

    return TravelPlan(
        tong_quan=tong_quan,
        ve_di_chuyen=transport_items,
        khach_san=hotel_items,
        lich_trinh=lich_trinh,
        nha_hang=restaurant_subset,
        diem_tham_quan=attraction_subset,
        tong_chi_phi=costs,
        meo=meo,
    )


def _map_transport_items(data: list[dict]) -> list[TransportItem]:
    return [
        TransportItem(
            loai=t.get("loai", "Máy bay"),
            hang=t.get("hang", "Hãng hàng không"),
            thoi_gian=t.get("thoi_gian", ""),
            gia=t.get("gia", "Liên hệ"),
            link=t.get("link"),
        )
        for t in data
    ]


def _map_hotel_items(data: list[dict]) -> list[HotelItem]:
    return [
        HotelItem(
            ten=h.get("ten", ""),
            dia_chi=h.get("dia_chi", ""),
            rating=float(h.get("rating", 0)),
            review_count=int(h.get("review_count", 0)),
            tien_nghi=h.get("tien_nghi", []),
            gia_per_dem=h.get("gia_per_dem", "Liên hệ"),
            link=h.get("link"),
        )
        for h in data
    ]


def _map_attraction_items(data: list[dict], input_data: TravelInput) -> list[AttractionItem]:
    items = []
    for a in data:
        loai = a.get("type", "Thắng cảnh") or "Thắng cảnh"
        if isinstance(loai, list):
            loai = loai[0] if loai else "Thắng cảnh"
        items.append(AttractionItem(
            diem=a.get("title", ""),
            loai=loai,
            dia_chi=a.get("address", ""),
            gia_ve=a.get("price", "Miễn phí"),
            thoi_gian="1-2 giờ",
            ghi_chu=a.get("description", "")[:100] if a.get("description") else "Tham quan tự do",
        ))
    return items


def _map_restaurant_items(data: list[dict], input_data: TravelInput) -> list[RestaurantItem]:
    days = min(input_data.days, 4)
    items = []
    for i, r in enumerate(data):
        day = (i // 3) + 1
        if day > days:
            break
        bua_map = ["Sáng", "Trưa", "Tối"]
        bua = bua_map[i % 3]
        gia = r.get("price", "$$")
        if not gia:
            gia = "$$"
        gia_str = _price_level_to_vnd(gia) if gia and gia.startswith("$") else gia
        mon = r.get("description", "").split(".")[0][:60] if r.get("description") else "Đặc sản địa phương"
        rating = r.get("rating", 0) or 0
        items.append(RestaurantItem(
            ngay=day,
            bua=bua,
            ten_quan=r.get("title", ""),
            dia_chi=r.get("address", ""),
            mon_dac_trung=mon,
            gia=gia_str,
            rating=round(float(rating), 1),
        ))
    return items


def _build_overview(input_data: TravelInput, costs: CostBreakdown, dest_geo: Optional[dict]) -> str:
    dest_name = dest_geo["name"] if dest_geo else input_data.destination
    people_desc = f"{input_data.adults} người lớn"
    if input_data.children:
        people_desc += f", {input_data.children} trẻ em"
    pace_names = {"thoải mái": "thoải mái", "vừa phải": "vừa phải", "nhanh": "nhanh"}
    pace_desc = pace_names.get(input_data.pace, "vừa phải")
    return (
        f"**{input_data.departure} → {dest_name}** | {input_data.days} ngày | "
        f"{people_desc} | Nhịp độ: {pace_desc} | "
        f"Tổng chi phí dự kiến: {costs.tong}"
    )


def _generate_tips(input_data: TravelInput) -> list[str]:
    meo = [
        f"Nên đặt vé trước 2-3 tuần để có giá tốt nhất.",
        f"Thời điểm lý tưởng: tháng 2-5 hoặc 9-11 (mùa khô).",
        f"Mang theo kem chống nắng, mũ nếu đi vào mùa hè.",
    ]
    if input_data.children > 0:
        meo.append("Có trẻ em: nên chọn khách sạn có hồ bơi, mang đồ chơi và thuốc men.")
    if input_data.special_requirements:
        meo.append(f"Lưu ý: {input_data.special_requirements}. Hãy liên hệ trước khách sạn để được hỗ trợ.")
    return meo
