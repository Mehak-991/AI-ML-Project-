from fastapi import FastAPI

app = FastAPI(
    title="AI/ML Project",
    description="Basic AI/ML project using Python and FastAPI",
    version="1.0.0"
)


@app.get("/")
def home():
    return {"message": "Welcome to AI / ML Project"}
