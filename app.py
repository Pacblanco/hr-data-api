import uvicorn
from fastapi import FastAPI, HTTPException
import pandas as pd
import logging
from pydantic import BaseModel
from typing import List, Literal, Dict, Any
import joblib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


description = """
This API gives access to an HR dataset of 1470 employees (36 columns),
so that a front-end team can explore it without handling the file itself.

## Preview

* `/preview` — get the first rows of the dataset
* `/unique-values` — get all distinct values of a column

## Numerical

* `/quantile` — get the employees above or below a given quantile

## Categorical

* `/groupby` — group by a column and apply an aggregation
* `/filter-by` — keep only the rows matching one or more categories

## Predict

* `/predict-attrition` — predict if an employee is likely to leave

All responses are JSON. Aggregated values are rounded to 2 decimals.
"""

tags_metadata = [
    {"name": "Preview", "description": "Quick exploration of the dataset."},
    {"name": "Numerical", "description": "Endpoints working on numerical columns."},
    {"name": "Categorical", "description": "Endpoints working on text columns."},
    {
        "name": "Predict",
        "description": (
            "Attrition prediction, based on a logistic regression model (86% accuracy)."
        ),
    },
]

app = FastAPI(
    title="HR Data API",
    description=description,
    version="0.1",
    openapi_tags=tags_metadata,
)


artifact = joblib.load("ibm_attrition_model.joblib")
model = artifact["model"]
feature_names = artifact["feature_names"]


class Groupby(BaseModel):
    column: str
    by_method: Literal["count", "sum", "mean", "max", "min"] = "mean"


class Filterby(BaseModel):
    column: str
    by_category: List[str]


class AttritionInput(BaseModel):
    features: Dict[str, Any]


class AttritionOutput(BaseModel):
    Attrition: str
    Probability: float


@app.get("/", tags=["Preview"], summary="Check that the API is running")
async def index():
    """Check that the API is running."""
    return "Hello world"


@app.get("/preview", tags=["Preview"], summary="Get the first rows of the dataset")
def preview(rows: int = 10):
    """
    Get the first rows of the dataset. Default is 10 rows.
    """
    df = pd.read_excel("ibm_hr_attrition.xlsx")
    df10 = df.head(rows)
    df_preview = df10.to_dict(orient="records")
    return df_preview


@app.get("/unique-values", tags=["Preview"], summary="List the values of a column")
def unique(column: str):
    """
    Get all distinct values of a given column.
    Useful to know which categories can be used in /filter-by.
    """
    df = pd.read_excel("ibm_hr_attrition.xlsx")
    df1 = df[column].unique()
    df_unique = df1.tolist()
    return df_unique


@app.get(
        "/quantile", 
        tags=["Numerical"], 
        summary="Get the highest or lowest employees")
def quantile(column: str, percent: float = 0.1, top: bool = True):
    """
    Get the employees above or below a given quantile of a numerical column.

    * `percent` — share of the dataset to keep, between 0.01 and 0.99
    * `top` — True for the highest values, False for the lowest

    Results are sorted, highest first when `top` is True.
    """

    if percent > 0.99 or percent < 0.01:
        logger.warning(f"percent value is not acceptable: {percent}")
        raise HTTPException(
            status_code=400, detail=f"percent value is not acceptable: {percent}"
        )

    df = pd.read_excel("ibm_hr_attrition.xlsx")
    if top:
        limit = df[column].quantile(1 - percent)
        df = df[df[column] > limit]
    else:
        limit = df[column].quantile(percent)
        df = df[df[column] < limit]

    df = df.sort_values(column, ascending=not top)
    result = df.to_dict(orient="records")
    return result


@app.post("/groupby", tags=["Categorical"], summary="Group by a column and aggregate")
def group_by(payload: Groupby):
    """
    Group the dataset by a column and apply an aggregation method.

    Only numerical columns are aggregated. Values are rounded to 2 decimals,
    so totals may differ slightly from the raw data.
    """
    df = pd.read_excel("ibm_hr_attrition.xlsx")
    df = (
        df.groupby(payload.column)
        .agg(payload.by_method, numeric_only=True)
        .round(2)
        .reset_index()
    )
    result = df.to_dict(orient="records")
    return result


@app.post("/filter-by", tags=["Categorical"], summary="Filter the rows by categories")
def filter_by(payload: Filterby):
    """
    Keep only the rows where the column matches one of the given categories.

    Use /unique-values first to know which categories exist.
    """
    df = pd.read_excel("ibm_hr_attrition.xlsx")
    df = df[df[payload.column].isin(payload.by_category)]
    result = df.to_dict(orient="records")
    return result


@app.post(
    "/predict-attrition",
    tags=["Predict"],
    summary="Predict the probability that an employee will leave",
    response_model=AttritionOutput,
)
def predict_attrition(payload: AttritionInput):
    """
    Predict if an employee is likely to leave the company.

    The request must contain the 31 columns used to train the model.
    A missing column returns a 400 error listing what is missing.

    The answer gives the prediction ("Yes" or "No") and the probability
    of leaving, between 0 and 1.
    """
    data = payload.features

    df_input = pd.DataFrame([data])

    missing = [c for c in feature_names if c not in df_input.columns]
    if missing:
        logger.warning(f"Missing columns: {missing}")
        raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")

    prediction = model.predict(df_input)[0]
    probability = model.predict_proba(df_input)[0][1]

    return {
        "Attrition": "Yes" if prediction == 1 else "No",
        "Probability": round(float(probability), 3),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)