import logging
from typing import Annotated, Literal

import joblib
import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


description = """
This API gives access to an HR dataset of 1470 employees (35 columns),
so that a front-end team can explore it without handling the file itself.

## Preview

* `/preview` — get the first rows of the dataset
* `/unique-values` — get all distinct values of a column
* `/employee` — get the profile of one employee

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

NumericColumn = Literal[
    "Age",
    "DailyRate",
    "DistanceFromHome",
    "HourlyRate",
    "MonthlyIncome",
    "MonthlyRate",
    "NumCompaniesWorked",
    "PercentSalaryHike",
    "TotalWorkingYears",
    "TrainingTimesLastYear",
    "YearsAtCompany",
    "YearsInCurrentRole",
    "YearsSinceLastPromotion",
    "YearsWithCurrManager",
]

CategoricalColumn = Literal[
    "Attrition",
    "BusinessTravel",
    "Department",
    "EducationField",
    "Gender",
    "JobRole",
    "MaritalStatus",
    "OverTime",
]


class Groupby(BaseModel):
    column: CategoricalColumn
    by_method: Literal["count", "sum", "mean", "max", "min"] = "mean"


class Filterby(BaseModel):
    Attrition: list[Literal["Yes", "No"]] = []
    BusinessTravel: list[
        Literal["Non-Travel", "Travel_Frequently", "Travel_Rarely"]
    ] = []
    Department: list[Literal["Human Resources", "Research & Development", "Sales"]] = []
    EducationField: list[
        Literal[
            "Human Resources",
            "Life Sciences",
            "Marketing",
            "Medical",
            "Other",
            "Technical Degree",
        ]
    ] = []
    Gender: list[Literal["Female", "Male"]] = []
    JobRole: list[
        Literal[
            "Healthcare Representative",
            "Human Resources",
            "Laboratory Technician",
            "Manager",
            "Manufacturing Director",
            "Research Director",
            "Research Scientist",
            "Sales Executive",
            "Sales Representative",
        ]
    ] = []
    MaritalStatus: list[Literal["Divorced", "Married", "Single"]] = []
    OverTime: list[Literal["Yes", "No"]] = []


class AttritionOutput(BaseModel):
    Attrition: str
    Probability: float


@app.get("/", tags=["Preview"], summary="Check that the API is running")
async def index():
    """Check that the API is running."""
    return "Hello world"


@app.get("/preview", tags=["Preview"], summary="Get the first rows of the dataset")
def preview(rows: int = Query(10, ge=1, le=100)):
    """
    Get the first rows of the dataset: 10 rows by default, 100 rows at most.

    To find other employees, use /filter-by or /quantile.
    """
    df = pd.read_excel("ibm_hr_attrition.xlsx", index_col=0)
    df10 = df.head(rows)
    df_preview = df10.to_dict(orient="records")
    return df_preview


@app.get("/unique-values", tags=["Preview"], summary="List the values of a column")
def unique(column: Literal[CategoricalColumn, NumericColumn]):
    """
    Get all distinct values of a given column.
    Useful to know which categories can be used in /filter-by.
    """
    df = pd.read_excel("ibm_hr_attrition.xlsx", index_col=0)
    df1 = df[column].unique()
    df_unique = df1.tolist()
    return df_unique


@app.get("/quantile", tags=["Numerical"], summary="Get the highest or lowest employees")
def quantile(column: NumericColumn, percent: float = 0.1, top: bool = True):
    """
    Get the employees above or below a given quantile of a numerical column.

    * `percent` — share of the dataset to keep, between 0.01 and 0.99
    * `top` — True for the highest values, False for the lowest

    Results are sorted, highest first when `top` is True.
    When many employees share the same value at the limit, the result can
    contain more employees than the requested share.
    """

    if percent > 0.99 or percent < 0.01:
        logger.warning(f"percent value is not acceptable: {percent}")
        raise HTTPException(
            status_code=400, detail=f"percent value is not acceptable: {percent}"
        )

    df = pd.read_excel("ibm_hr_attrition.xlsx", index_col=0)
    if top:
        limit = df[column].quantile(1 - percent)
        df = df[df[column] >= limit]
    else:
        limit = df[column].quantile(percent)
        df = df[df[column] <= limit]

    df = df.sort_values(column, ascending=not top)
    result = df.to_dict(orient="records")
    return result


@app.get("/groupby", tags=["Categorical"], summary="Group by a column and aggregate")
def group_by(payload: Annotated[Groupby, Query()]):
    """
    Group the dataset by a column and apply an aggregation method.

    Only numerical columns are aggregated. Values are rounded to 2 decimals,
    so totals may differ slightly from the raw data.
    """
    df = pd.read_excel("ibm_hr_attrition.xlsx", index_col=0)
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    df = (
        df.groupby(payload.column)[numeric_cols]
        .agg(payload.by_method)
        .round(2)
        .reset_index()
    )
    result = df.to_dict(orient="records")
    return result


@app.get("/filter-by", tags=["Categorical"], summary="Filter the rows by categories")
def filter_by(payload: Annotated[Filterby, Query()]):
    """
    Keep only the employees that match the chosen categories.

    Each column has its own list: choose one or more values, in one or more
    columns. In one column, a row is kept if it matches one of the values.
    Between columns, a row must match all the columns you used.

    At least one value is required. If no employee matches, the API
    returns a 404 error.
    """
    df = pd.read_excel("ibm_hr_attrition.xlsx", index_col=0)
    filters = {col: values for col, values in payload.model_dump().items() if values}
    if not filters:
        raise HTTPException(status_code=400, detail="Choose at least one category")
    for col, values in filters.items():
        df = df[df[col].isin(values)]
    if df.empty:
        raise HTTPException(
            status_code=404, detail=f"no employee matches these categories: {filters}"
        )
    return df.to_dict(orient="records")


@app.get("/employee", tags=["Preview"], summary="Get the profile of one employee")
def employee(employee_number: int):
    """
    Get all the data of one employee, from the `EmployeeNumber` column.

    Use it with /predict-attrition: give the same number to see the profile
    of the employee behind the prediction (age, job, overtime...).

    An unknown number returns a 404 error.
    """
    df = pd.read_excel("ibm_hr_attrition.xlsx", index_col=0)
    row = df[df["EmployeeNumber"] == employee_number]
    if row.empty:
        raise HTTPException(
            status_code=404, detail=f"Employee {employee_number} not found"
        )
    return row.to_dict(orient="records")[0]


@app.get(
    "/predict-attrition",
    tags=["Predict"],
    summary="Predict the probability that an employee will leave",
    response_model=AttritionOutput,
)
def predict_attrition(employee_number: int):
    """
    Predict if an employee is likely to leave the company.

    Give the number of an employee: the `EmployeeNumber` column of /preview.
    Numbers go from 1 to 2068, but some numbers do not exist.
    An unknown number returns a 404 error.

    The answer gives the prediction ("Yes" or "No") and the probability
    of leaving, between 0 and 1.

    To see the profile of this employee, use /employee with the same number.

    Demo only: the model was trained on this same dataset, so the results
    show how the model works, not how well it predicts.
    """
    df = pd.read_excel("ibm_hr_attrition.xlsx")
    row = df[df["EmployeeNumber"] == employee_number]

    if row.empty:
        logger.warning(f"Employee {employee_number} not found")
        raise HTTPException(
            status_code=404, detail=f"Employee {employee_number} not found"
        )

    prediction = model.predict(row[feature_names])[0]
    probability = model.predict_proba(row[feature_names])[0][1]

    return {
        "Attrition": "Yes" if prediction == 1 else "No",
        "Probability": round(float(probability), 3),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
