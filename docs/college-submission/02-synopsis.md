# Project Synopsis

**Title:** AIProject — A Role-Based, Explainable Machine Learning Platform

**Technology:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 18, scikit-learn, SHAP, LIME,
React 19 + TypeScript + Vite, Docker Compose, Nginx, GitHub Actions.

## 1. Problem

Training a machine-learning model is only a small part of using one. Teams also need a safe place to
store datasets, a repeatable way to train and compare models, a controlled way to let other people
run predictions, an explanation of why a model answered the way it did, and a record of who did what.
Most student projects stop at a notebook and leave out access control, auditing and deployment.

## 2. Objective

Build one web application in which people with different responsibilities can work with the same
machine-learning assets safely:

* a **user** can look at datasets and models and ask a model for predictions and explanations;
* an **admin** can additionally upload datasets, train and compare models, run background jobs,
  monitor drift and deploy models;
* a **superadmin** can additionally manage accounts and roles and read the audit log.

## 3. What was built (all of it exists in the repository and is tested)

| Area | Implementation |
|---|---|
| Data | CSV/Excel upload, validation (type, size, rows, columns), missing-value and duplicate detection, statistical profile, row preview |
| Modelling | Leakage-safe scikit-learn pipeline (imputation, encoding, scaling), train/validation/test split, four algorithms (linear/logistic, random forest, gradient boosting, decision tree), baseline model, 5-fold cross-validation, versioned model registry |
| Evaluation | Classification: accuracy, balanced accuracy, precision, recall, F1, ROC-AUC, log-loss, confusion matrix. Regression: MAE, RMSE, median absolute error, R² |
| Prediction | Single and batch prediction with input validation and a logged history |
| Explainability | SHAP and LIME explanations, global feature importance |
| MLOps | PostgreSQL-backed job queue with a worker, experiments with grid search, deployments, drift and data-quality monitoring with alerts |
| Security | JWT access tokens, rotating refresh tokens, Argon2id password hashing, three-role RBAC with a central permission registry (deny-by-default), append-only audit log, rate limiting, upload validation |
| Delivery | Docker Compose (database, migration, API, worker, Nginx), health checks, Alembic migrations, CI pipeline with lint, tests, dependency audit and secret scanning |

## 4. Methodology

Layered architecture (routes → services → repositories → database), test-driven verification
(unit, PostgreSQL integration and full-stack end-to-end tests), and a staged rollout (expand,
migrate, contract) for database changes.

## 5. Expected outcome

A working, documented and tested platform that can be run locally with Docker, demonstrated in a
viva, and deployed publicly once a domain and TLS certificate are provided.

## 6. Scope limits (stated honestly)

Tabular supervised learning only (classification and regression). Optional language-model features
need external services and are off by default. Public HTTPS has not been deployed; the repository
contains the configuration and the steps.
