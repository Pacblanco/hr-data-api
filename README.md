# HR Data API

A REST API that gives access to an HR dataset of 1470 employees (35 columns)
and to a model that predicts attrition. A front-end team can read the data
through the API, without opening the file.

Built with FastAPI, pandas and scikit-learn. Runs in Docker.

**Live API: [hr-data-api-j9yt.onrender.com/docs](https://hr-data-api-j9yt.onrender.com/docs)**
The service runs on a free instance: the first call can take 30 to 50 seconds,
while the service wakes up.

![Interactive documentation of the API](docs/swagger.png)

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Check that the API is running |
| GET | `/preview` | First rows of the dataset (`rows`, default 10, max 100) |
| GET | `/unique-values` | All different values of a column (`column`) |
| GET | `/employee` | Profile of one employee (`employee_number`) |
| GET | `/quantile` | Employees with the highest or the lowest values of a numerical column (`column`, `percent`, `top`) |
| GET | `/groupby` | Group by a category and compute an aggregation (`column`, `by_method`) |
| GET | `/filter-by` | Keep only the employees of the chosen categories (one parameter per text column) |
| GET | `/predict-attrition` | Probability that an employee leaves (`employee_number`) |

The `column` parameter accepts only some columns:

- `/quantile`: numerical columns
- `/groupby`: text columns
- `/unique-values`: both

`/filter-by` has one parameter for each text column (`Gender`, `Department`,
`JobRole`...), each with its own list of categories. You can choose values in
one or more columns. In one column, a row is kept if it matches one of the
values. Between columns, a row must match all the columns you used.

The `column` parameter accepts only the numerical and text columns.
Identifiers, constant values and rating columns (such as `JobSatisfaction`
or `JobLevel`) are not accepted. The rating columns are still in the
results, and the prediction model uses them. In `/docs`, all these
parameters show the accepted values in a drop-down list.

The interactive documentation is available at `/docs` when the API runs.

## Errors

The API never answers a wrong request with an empty result. It returns an
error with a clear message:

- **422**: a parameter is missing or not valid, for example a column that does
  not exist or a number out of range
- **400**: the request is valid but cannot be used: `percent` out of range in
  `/quantile`, or no category chosen in `/filter-by`
- **404**: no result: unknown employee number, or no employee for the chosen
  categories

## Run with Docker

```bash
docker build -t ibm-attrition .
docker run --rm --name ibm-api -p 7860:7860 ibm-attrition
```

Then open http://localhost:7860/docs

## Run without Docker

```bash
pip install -r requirements.txt
python app.py
```

## Examples

The 10% of employees with the highest daily rate:

```bash
curl "http://localhost:7860/quantile?column=DailyRate&percent=0.1&top=true"
```

The mean values for each business travel group:

```bash
curl "http://localhost:7860/groupby?column=BusinessTravel&by_method=mean"
```

The women of the Sales department:

```bash
curl "http://localhost:7860/filter-by?Gender=Female&Department=Sales"
```

The profile of employee number 1, then the probability that this employee
leaves:

```bash
curl "http://localhost:7860/employee?employee_number=1"
curl "http://localhost:7860/predict-attrition?employee_number=1"
```

## Prediction model

`/predict-attrition` uses a scikit-learn model trained on the same dataset:
standard scaling, one-hot encoding and logistic regression. Its accuracy is
86%. The model is saved in `ibm_attrition_model.joblib`. It is loaded one
time, when the API starts.

You give the number of an employee: the `EmployeeNumber` column of `/preview`.
The API finds this employee in the dataset and returns the prediction
(`"Yes"` or `"No"`) and the probability to leave, between 0 and 1. Numbers go
from 1 to 2068, but some numbers do not exist: an unknown number returns a
404 error. To see the profile of this employee, use `/employee` with the same
number.

This is a demo. The model was trained on this same dataset, so the results
show how the model works, not how well it predicts. Also, 84% of the employees
in the dataset stay: a model that always answers "No" would already have 84%
accuracy.

## Project structure

| File | Role |
|---|---|
| `app.py` | the API: endpoints, Pydantic models, documentation |
| `requirements.txt` | the dependencies |
| `Dockerfile` | the image definition |
| `ibm_hr_attrition.xlsx` | the dataset |
| `ibm_attrition_model.joblib` | the trained model |
| `docs/swagger.png` | a screenshot of the interactive documentation |

## Notes and limits

- The aggregated values are rounded to 2 decimals. So a total can be a little
  different from the same total computed on the raw data.
- In `/quantile`, when many employees share the same value at the limit, the
  result can contain more employees than the requested share.
- The Excel file is read again at each request. It is slow, but the data never
  changes, so the result is always correct.
- `/filter-by` can still return a large part of the dataset, up to about 1 MB.
  There is no pagination: the client has to manage this volume.
- `scikit-learn` is fixed to the version 1.7.2, the version used to train the
  model. Another version can read the file, but the predictions can change.
- The model was trained with the column `Unnamed: 0`, an old row index with no
  meaning. The data endpoints hide this column. Its weight in the prediction
  is very small.

## Context

Project made during the Jedha Data Fullstack bootcamp, Data Products module.
