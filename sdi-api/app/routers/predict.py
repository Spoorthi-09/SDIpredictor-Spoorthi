from fastapi import APIRouter, HTTPException
import pandas as pd

from app.schemas import PredictRequest, PredictResponse
from app.services.model import pipe
from app.utils.preprocess import preprocess_input, clip_predictions

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok"}

@router.post("/predict", response_model=PredictResponse)
def predict(payload: PredictRequest):
    try:
        if not payload.rows:
            raise HTTPException(status_code=400, detail="No rows provided.")
        df_raw = pd.DataFrame(payload.rows)
        df = preprocess_input(df_raw)
        preds = pipe.predict(df)
        if payload.clip_to_max_benefit:
            preds = clip_predictions(df_raw, preds)
        return PredictResponse(
            predictions=[float(x) for x in preds],
            n_rows=len(df),
            clipped=payload.clip_to_max_benefit
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")
