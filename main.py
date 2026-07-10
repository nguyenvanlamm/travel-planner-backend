from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.plan import router as plan_router
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Travel Planner API",
    description="Lập kế hoạch du lịch thông minh dựa trên dữ liệu thực tế",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(plan_router)


@app.get("/")
def root():
    return {"message": "Travel Planner API is running. Go to /docs for API documentation."}
