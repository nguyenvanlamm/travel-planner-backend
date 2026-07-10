from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import date


class TravelInput(BaseModel):
    departure: str = Field(..., description="Điểm xuất phát")
    destination: str = Field(..., description="Điểm đến")
    days: int = Field(..., ge=1, le=30, description="Số ngày du lịch")
    adults: int = Field(default=2, ge=1, description="Số người lớn")
    children: int = Field(default=0, ge=0, description="Số trẻ em")
    budget: Optional[int] = Field(default=None, description="Tổng ngân sách (VND)")
    hotel_level: Optional[Literal["2 sao", "3 sao", "4 sao", "5 sao"]] = Field(default=None)
    transportation: Optional[Literal["Máy bay", "Xe khách", "Tàu", "Ô tô"]] = Field(default=None)
    interests: Optional[list[str]] = Field(default=None)
    pace: Literal["thoải mái", "vừa phải", "nhanh"] = Field(default="vừa phải")
    cuisine: Optional[str] = Field(default=None)
    special_requirements: Optional[str] = Field(default=None)
    start_date: date = Field(..., description="Ngày bắt đầu chuyến đi")


class TransportItem(BaseModel):
    loai: str
    hang: str
    thoi_gian: str
    gia: str
    link: Optional[str] = None


class HotelItem(BaseModel):
    ten: str
    dia_chi: str
    rating: float
    review_count: int
    tien_nghi: list[str]
    gia_per_dem: str
    link: Optional[str] = None


class Activity(BaseModel):
    gio: str
    mo_ta: str


class DayPlan(BaseModel):
    ngay: int
    tieu_de: str
    buoi_sang: list[Activity]
    buoi_trua: list[Activity]
    buoi_chieu: list[Activity]
    buoi_toi: list[Activity]


class RestaurantItem(BaseModel):
    ngay: int
    bua: str
    ten_quan: str
    dia_chi: str = ""
    mon_dac_trung: str
    gia: str
    rating: float


class AttractionItem(BaseModel):
    diem: str
    loai: str
    dia_chi: str = ""
    gia_ve: str
    thoi_gian: str
    ghi_chu: str


class CostBreakdown(BaseModel):
    ve_di_chuyen: str
    khach_san: str
    an_uong: str
    di_chuyen_noi_thanh: str
    ve_tham_quan: str
    chi_phi_phat_sinh: str
    tong: str
    ngan_sach: Optional[str] = None
    chenh_lech: Optional[str] = None


class TravelPlan(BaseModel):
    tong_quan: str
    ve_di_chuyen: list[TransportItem]
    khach_san: list[HotelItem]
    lich_trinh: list[DayPlan]
    nha_hang: list[RestaurantItem]
    diem_tham_quan: list[AttractionItem]
    tong_chi_phi: CostBreakdown
    meo: list[str]
