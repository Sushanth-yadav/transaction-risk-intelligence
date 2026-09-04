# Transaction Risk Intelligence

## Explainable Payment Risk Detection \& Investigation Platform

A multi-signal transaction risk intelligence system built with Django, machine learning, behavioral analysis, rule-based detection, relationship/graph analysis, evidence generation, and a natural-language Investigation Assistant powered by Google Gemini.

> \\\*\\\*Important:\\\*\\\* This is an independent project/prototype. "RazorGuard" is the internal project name used during development and is not presented as an official Razorpay product.

\---

## 1\. Overview

Fraud detection is not simply a matter of deciding whether a transaction is `fraudulent` or `legitimate`.

A real investigation often needs to answer:

* Why did the transaction receive this risk score?
* Is the transaction actually suspicious?
* Which signals increased the risk?
* Which signals reduce concern?
* Is the customer's current behavior different from their historical behavior?
* Is the transaction connected to suspicious devices or IP addresses?
* What evidence supports the decision?
* What should an investigator do next?

**Transaction Risk Intelligence** addresses this by combining multiple independent risk signals and turning them into an explainable transaction assessment.

The system combines:

1. **Machine-learning risk prediction**
2. **Deterministic rule-based analysis**
3. **Customer behavioral analysis**
4. **Relationship/graph analysis**
5. **Risk aggregation**
6. **Evidence generation**
7. **Investigation APIs**
8. **Audit logging**
9. **Natural-language investigation through Google Gemini**

The most important architectural principle is:

> \\\*\\\*The risk engine is the source of truth. Gemini is an explanation layer, not the final fraud decision-maker.\\\*\\\*

\---

# 2\. Problem Statement

Traditional fraud systems frequently reduce a transaction to a binary result:

```text
Transaction
    ↓
Fraud Model
    ↓
Fraud / Not Fraud
```

That creates a major problem for investigators.

A score alone does not explain:

* what caused the risk,
* whether the transaction differs from the customer's normal behavior,
* whether a rule was triggered,
* whether a device or IP is unusual,
* whether related entities exist,
* or why the system recommends monitoring, review, or escalation.

This project approaches the problem as **risk intelligence and investigation**, rather than only classification.

\---

# 3\. Solution

The project builds an investigation-oriented risk pipeline:

```text
                    Transaction
                         │
                         ▼
                Transaction Validation
                         │
                         ▼
                 Feature Engineering
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       ML Model       Rule Engine   Behavioral Analysis
          │              │              │
          └──────────────┼──────────────┘
                         │
                         ▼
                 Graph / Relationship
                      Analysis
                         │
                         ▼
                  Risk Aggregation
                         │
                         ▼
                 Risk Assessment
                         │
                         ▼
                    Evidence
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        Investigation API       Dashboard
              │
              ▼
       Investigation Assistant
              │
              ▼
        Google Gemini Layer
              │
              ▼
     Grounded Natural-Language
          Explanation
```

The assistant explains the evidence already produced by the backend. It does not override the underlying risk decision.

\---

# 4\. Core Design Principle

The system deliberately separates **risk decisioning** from **natural-language explanation**.

### Risk engine

The risk engine calculates:

* ML score
* rule score
* behavioral score
* graph score
* final score
* risk category
* confidence
* recommended action

### Investigation layer

The investigation layer:

* retrieves transaction context,
* retrieves customer history,
* retrieves evidence,
* retrieves related entities,
* retrieves model information,
* retrieves audit history,
* interprets the investigator's question,
* produces a readable explanation.

### Gemini

Google Gemini can be used as an optional conversational layer.

The backend-controlled evidence remains authoritative.

This separation is important because an LLM should not be trusted to independently invent or modify financial risk decisions.

\---

# 5\. Risk Signal Architecture

The project combines four major risk components.

|Component|Purpose|
|-|-|
|ML|Estimates fraud probability from learned transaction patterns|
|Rules|Applies deterministic, explainable conditions|
|Behavioral|Compares current activity with the customer's historical behavior|
|Graph|Examines relationships through shared entities such as devices and IPs|

The aggregated score uses the following weighting shown in the scoring pipeline:

```text
Final Score =
    ML Score         × 0.40
  + Rule Score       × 0.25
  + Behavioral Score × 0.20
  + Graph Score      × 0.15
```

The resulting score is used to derive:

* risk category,
* confidence,
* recommended action.

This makes the final assessment more interpretable than relying on a single model output.

\---

# 6\. Machine Learning

The project uses a **Random Forest** model for the main ML risk signal.

The model produces a fraud probability which is represented as a score on a 0–100 scale.

The live scoring implementation is designed to use the same feature definitions as the training pipeline.

A particularly important design choice is the **causal feature constraint**.

For a transaction being scored, historical customer features are calculated using transactions that occurred before the transaction being investigated.

This helps prevent future information from leaking into the features used to make the decision.

### Model artifact

The live scoring service expects a trained model at:

```text
ml/models/random\\\_forest.joblib
```

The project contains training/inference components under the `ml/` directory.

\---

# 7\. Behavioral Analysis

Behavioral analysis compares the current transaction against the customer's historical activity.

Signals include concepts such as:

* new location,
* new device,
* new IP,
* unusual transaction amount,
* transaction frequency,
* historical average amount,
* amount ratio to the customer's normal amount.

For example:

```text
Historical average = ₹295.09
Current transaction = ₹1351.85
Amount ratio ≈ 4.58×
```

This does not automatically mean fraud.

Instead, it means the transaction is behaviorally different and should be interpreted together with the other risk signals.

This distinction is important:

> \\\*\\\*Anomaly is evidence, not proof of fraud.\\\*\\\*

\---

# 8\. Rule-Based Risk Analysis

The rule engine provides deterministic risk signals.

Unlike an ML model, a rule can be directly explained:

```text
Condition
    ↓
Rule triggered
    ↓
Risk contribution
    ↓
Evidence description
```

This makes rule-based detection useful for:

* transparent decisions,
* investigator review,
* compliance-oriented explanations,
* debugging,
* predictable behavior.

\---

# 9\. Graph / Relationship Analysis

The project also analyzes relationships between transaction entities.

The investigation tools expose relationships involving:

* transactions,
* customers,
* devices,
* IP addresses.

A relationship can be created through shared entities such as a device or IP.

This enables the system to investigate questions such as:

```text
Is this transaction connected to other transactions?
Is the device shared?
Is the IP shared?
Is there a suspicious relationship cluster?
```

The current project is intentionally scoped rather than being a full enterprise fraud-ring graph engine.

\---

# 10\. Risk Aggregation

The risk aggregator combines the independent signals.

Example:

```text
ML             41.91
Rules           0.00
Behavioral     46.67
Graph           0.00
----------------------
Final Risk     26.10
```

The final score is then categorized into risk levels.

The current project uses:

```text
< 40       LOW
40–69.99   MEDIUM
>= 70      HIGH
```

The implementation also contains a lower "trusted" presentation range for extremely low scores.

The final assessment also includes:

* confidence,
* model version,
* recommended action.

\---

# 11\. Risk Assessment Data Model

The `RiskAssessment` model stores one aggregated assessment per transaction.

The model contains:

```text
transaction
ml\\\_score
rule\\\_score
behavioral\\\_score
graph\\\_score
final\\\_score
risk\\\_category
confidence
model\\\_version
recommended\\\_action
created\\\_at
```

The use of separate subsystem scores is valuable because investigators can see not only the final score but also which subsystem contributed to it.

\---

# 12\. Evidence System

Evidence is stored alongside the risk assessment.

Evidence can represent:

* model evidence,
* rule evidence,
* behavioral evidence,
* graph evidence.

A model evidence example is conceptually:

```text
The ML model estimated a fraud probability of X%.
```

Behavioral evidence can explain differences from the customer's historical behavior.

The evidence layer gives the Investigation Assistant structured facts to explain instead of requiring it to guess transaction information.

\---

# 13\. Investigation Assistant

The Investigation Assistant is designed for natural-language investigation.

An investigator can ask questions such as:

```text
Is this suspicious?

Why no suspicious?

Is this safe?

What happened?

What caused the risk?

Why is the score high?

What evidence do we have?

Should I be worried?

Tell me about this transaction.
```

The assistant should not assume that every transaction was flagged.

That is an important design improvement over a flag-centric investigation workflow.

### Question-aware investigation

The orchestrator detects different types of investigator intent, including concepts such as:

* fraud status,
* resolution / next action,
* customer history,
* risk explanation,
* evidence,
* behavioral analysis,
* transaction details.

This allows the system to produce an answer appropriate to the question instead of always returning the same "why was this flagged?" response.

\---

# 14\. Backend-Controlled Investigation Tools

The investigation layer uses a fixed backend tool registry.

Tools identified in the project include:

```text
get\\\_transaction
get\\\_customer\\\_history
get\\\_risk\\\_evidence
get\\\_related\\\_entities
get\\\_model\\\_explanation
get\\\_audit\\\_history
```

The design intentionally prevents unrestricted database access from the LLM layer.

The tool layer returns bounded, JSON-serializable information.

Conceptually:

```text
User Question
      ↓
Investigation Orchestrator
      ↓
Approved Backend Tool
      ↓
Structured Evidence
      ↓
Explanation
```

This is much safer than allowing an LLM to directly construct arbitrary database queries.

\---

# 15\. Google Gemini Integration

The current project uses **Google Gemini**, not Anthropic Claude, as the LLM integration.

Gemini is intended to provide a conversational explanation layer.

The project uses Google's Python SDK through imports such as:

```python
from google import genai
```

The Gemini API key is read from application configuration/environment settings.

A typical environment variable is:

```text
GEMINI\\\_API\\\_KEY
```

The Gemini layer is optional in the current architecture because the deterministic investigation path can still provide grounded answers when Gemini is unavailable or quota-limited.

### Why this architecture is useful

If Gemini becomes unavailable:

```text
Gemini unavailable
       ↓
Deterministic investigation path
       ↓
Grounded answer
```

The application therefore does not need to turn an LLM outage into a complete investigation outage.

\---

# 16\. Example Investigation

Suppose a transaction has:

```text
Amount: ₹1351.85
Historical average: ₹295.09
Location: Kolkata
Previous location: Chandigarh

ML score: 41.91
Rule score: 0
Behavioral score: 46.67
Graph score: 0
Final score: 26.10
Risk category: LOW
Recommended action: MONITOR
```

A good investigation explanation would distinguish between:

### Risk-increasing evidence

* The location is new for the customer.
* The amount is materially higher than the customer's historical average.
* The ML model produced a moderate fraud probability.
* Behavioral analysis contributed to the risk.

### Risk-reducing evidence

* No rule-based risk signal was generated.
* No graph-based risk signal was generated.
* The device was previously seen.
* The IP was previously seen.

### Final decision

The final RazorGuard score remains the authoritative decision:

```text
26.10 / 100 → LOW risk → MONITOR
```

The unusual amount and new location are therefore treated as investigation evidence, not as automatic proof of fraud.

\---

# 17\. Django Application Architecture

The backend is implemented using:

* Django
* Django REST Framework
* relational database support
* modular Django applications.

The project is divided into domain-oriented applications rather than placing all functionality into one large Django application.

The known application areas include:

```text
apps/
├── audit/
├── behavior/
├── dashboard/
├── evidence/
├── graph/
├── investigation/
├── risk/
└── transactions/
```

Each domain is responsible for a different part of the system.

\---

# 18\. Important Backend Components

## `apps/transactions/`

Responsible for transaction-domain data and transaction APIs.

Important concepts include:

* transaction,
* customer,
* merchant,
* device,
* IP address,
* payment instrument.

\---

## `apps/risk/`

Responsible for risk assessment and risk scoring.

Important components include:

* `models.py`
* risk scoring services
* risk aggregation
* risk views/API behavior.

`RiskAssessment` stores the output of the scoring pipeline.

\---

## `apps/evidence/`

Responsible for storing and exposing evidence generated by risk analysis.

Evidence connects risk decisions with understandable supporting information.

\---

## `apps/behavior/`

Responsible for behavioral anomaly analysis.

It compares the current transaction against historical customer behavior.

\---

## `apps/graph/`

Responsible for relationship analysis between entities.

It works with relationships involving customers, transactions, devices, and IP addresses.

\---

## `apps/investigation/`

Contains the Investigation Assistant architecture.

Important components include:

```text
tools.py
orchestrator.py
views.py
urls.py
models.py
```

### `tools.py`

Defines the backend-controlled investigation tools.

### `orchestrator.py`

Controls investigation flow, question intent, tool calls, deterministic explanations, and the optional Gemini layer.

### `views.py`

Exposes the Investigation API.

The main endpoint is:

```text
POST /api/investigate/<transaction\\\_id>/ask/
```

### `urls.py`

Maps the investigation route to the API view.

### `models.py`

Stores investigation questions and answers in the investigation log.

\---

# 19\. Investigation API Flow

The Investigation API follows this pattern:

```text
POST /api/investigate/<transaction\\\_id>/ask/
             │
             ▼
      Validate transaction
             │
             ▼
       Validate question
             │
             ▼
ask\\\_investigation\\\_assistant(...)
             │
             ▼
       Investigation tools
             │
             ▼
      Evidence/context
             │
             ▼
      Question-aware answer
             │
             ▼
      InvestigationLog
             │
             ▼
       Audit event
             │
             ▼
          Response
```

The API validates the question using a serializer with a maximum length of 2000 characters.

\---

# 20\. Auditability

The project includes an audit layer.

Investigation actions can be recorded with information such as:

* transaction,
* actor,
* action,
* question,
* tools called,
* resulting state.

This is important for financial systems because an investigation should not be a black box.

A useful audit trail allows a reviewer to ask:

```text
What happened?
When did it happen?
Which transaction was involved?
What did the investigator ask?
Which tools were used?
What decision/action followed?
```

\---

# 21\. Dashboard

The project includes a dashboard-oriented application for reviewing transaction risk.

The intended investigation workflow is:

```text
Transaction list
      ↓
Risk filtering
      ↓
Transaction detail
      ↓
Risk assessment
      ↓
Evidence
      ↓
Investigation Assistant
      ↓
Audit history
```

This creates a workflow closer to an investigator's job rather than simply displaying a model prediction.

\---

# 22\. Data Model

The project contains a relational domain model around the transaction.

The important entities include:

```text
Customer
   │
   ├── Transactions
   │       │
   │       ├── Merchant
   │       ├── Device
   │       ├── IP Address
   │       └── Payment Instrument
   │
   └── Historical Behavior

Transaction
   │
   └── RiskAssessment
           │
           └── Evidence

Transaction
   │
   └── InvestigationLog

Transaction
   │
   └── AuditLog
```

This structure supports both risk scoring and investigation.

\---

# 23\. Repository Structure

The project is organized approximately as follows based on the supplied project artifacts:

```text
transaction-risk-intelligence/
│
├── apps/
│   ├── audit/
│   ├── behavior/
│   ├── dashboard/
│   ├── evidence/
│   ├── graph/
│   ├── investigation/
│   ├── risk/
│   └── transactions/
│
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── ...
│
├── ml/
│   ├── data/
│   │   ├── raw/
│   │   └── ...
│   ├── features/
│   ├── models/
│   └── training/
│
├── scripts/
│   ├── seed\\\_db.py
│   └── backfill\\\_risk\\\_scores.py
│
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

Some generated files, caches, database files, and migration details may not be represented in this simplified tree.

\---

# 24\. Important Files

## `manage.py`

Django's command-line entry point.

It is used for commands such as:

```cmd
python manage.py migrate
python manage.py check
python manage.py shell
python manage.py test
python manage.py runserver
```

\---

## `config/settings.py`

Central Django configuration.

It controls areas such as:

* installed applications,
* middleware,
* database configuration,
* environment variables,
* static files,
* ML model paths,
* application settings.

\---

## `config/urls.py`

The project's top-level URL configuration.

It connects application-specific routes to the Django project.

\---

## `config/wsgi.py`

Provides the WSGI application entry point used by WSGI-compatible servers.

\---

## `apps/investigation/orchestrator.py`

One of the most important files in the project.

It coordinates:

```text
Question
  ↓
Intent detection
  ↓
Backend tools
  ↓
Structured evidence
  ↓
Deterministic explanation
  ↓
Optional Gemini layer
```

The orchestrator deliberately keeps the risk pipeline authoritative.

\---

## `apps/investigation/tools.py`

Contains backend-controlled tools for investigation.

The important security property is:

> The LLM does not receive unrestricted database access.

Instead, it receives information through predefined functions.

\---

## `apps/investigation/views.py`

Defines the REST API view for investigator questions.

The view:

1. finds the transaction,
2. validates the question,
3. calls the investigation assistant,
4. stores the investigation log,
5. records an audit event,
6. returns the answer.

\---

## `apps/investigation/urls.py`

Defines:

```text
investigate/<transaction\\\_id>/ask/
```

for the Investigation Assistant API.

\---

## `apps/risk/models.py`

Defines `RiskAssessment`.

It stores each subsystem's score and the final aggregated assessment.

\---

## `apps/risk/services.py`

Handles live risk scoring and live feature computation.

An important design characteristic is that historical information is constrained to transactions that occurred before the transaction being scored.

This supports causal serving-time feature calculation.

\---

## `ml/features/feature\\\_engineering.py`

Contains feature engineering definitions shared by the ML training/live-scoring pipeline.

Keeping training and serving feature definitions aligned reduces train/serve skew.

\---

## `ml/training/train\\\_and\\\_evaluate.py`

Responsible for training/evaluating the ML models represented in the project.

The supplied project documentation identifies Logistic Regression as a baseline and Random Forest as the main model.

\---

## `ml/data/generate\\\_synthetic\\\_data.py`

Generates synthetic transaction data for development/training.

The existing project documentation describes realistic fraud patterns and legitimate hard-negative cases.

\---

## `scripts/seed\\\_db.py`

Loads transaction data into the Django database.

This is useful when setting up the project on a fresh computer.

\---

## `scripts/backfill\\\_risk\\\_scores.py`

Used to generate/backfill risk assessments for existing transaction data where required by the project workflow.

\---

# 25\. API Overview

The supplied project documentation identifies the following API surface:

|Endpoint|Method|Purpose|
|-|-|-|
|`/api/transactions/`|POST|Ingest a transaction and run the risk pipeline|
|`/api/transactions/{id}/`|GET|Retrieve transaction details|
|`/api/transactions/{id}/risk/`|GET|Retrieve risk assessment|
|`/api/transactions/{id}/evidence/`|GET|Retrieve evidence|
|`/api/transactions/{id}/related/`|GET|Retrieve related entities|
|`/api/transactions/{id}/action/`|POST|Record investigator action|
|`/api/transactions/{id}/audit/`|GET|Retrieve audit history|
|`/api/investigate/{id}/ask/`|POST|Ask the Investigation Assistant|
|`/api/dashboard/summary/`|GET|Retrieve dashboard risk summary|

Always verify the exact URL configuration in the current checkout before relying on an endpoint in an external integration.

\---

# 26\. Fresh Computer Setup

The following workflow is intended for a fresh clone on Windows.

## Step 1 — Clone the repository

```cmd
git clone https://github.com/Sushanth-yadav/transaction-risk-intelligence.git
cd transaction-risk-intelligence
```

## Step 2 — Create the virtual environment

```cmd
python -m venv .venv
```

## Step 3 — Activate it

```cmd
.venv\\\\Scripts\\\\activate
```

You should see:

```text
(.venv)
```

in the command prompt.

## Step 4 — Upgrade pip

```cmd
python -m pip install --upgrade pip
```

## Step 5 — Install dependencies

```cmd
pip install -r requirements.txt
```

If a fresh environment reports a missing package, install the package required by the current source/requirements and update `requirements.txt` so the next clone is reproducible.

## Step 6 — Create environment configuration

```cmd
copy .env.example .env
```

Then configure the required values.

For the current Gemini-based implementation, the important LLM configuration is:

```text
GEMINI\\\_API\\\_KEY=your\\\_gemini\\\_api\\\_key
```

Do not commit the real `.env` file or API key.

\---

# 27\. Database Setup

Run:

```cmd
python manage.py migrate
```

Then verify Django:

```cmd
python manage.py check
```

Expected result:

```text
System check identified no issues (0 silenced).
```

\---

# 28\. ML/Data Setup

If the repository does not already contain the generated dataset/model artifacts, recreate them using the scripts included in the project.

The project documentation identifies this workflow:

```cmd
python ml\\\\data\\\\generate\\\_synthetic\\\_data.py --customers 2000 --avg-txns-per-customer 9 --days-span 120 --fraud-rate 0.025 --out ml\\\\data\\\\raw\\\\transactions.csv

python ml\\\\features\\\\feature\\\_engineering.py

python ml\\\\training\\\\train\\\_and\\\_evaluate.py
```

The exact generated artifacts should be confirmed against the current checkout.

The live risk service expects:

```text
ml/models/random\\\_forest.joblib
```

\---

# 29\. Seed the Database

After the data is available:

```cmd
python scripts\\\\seed\\\_db.py
```

Then, where required by the current data workflow:

```cmd
python scripts\\\\backfill\\\_risk\\\_scores.py
```

Verify the transaction count:

```cmd
python manage.py shell -c "from apps.transactions.models import Transaction; print(Transaction.objects.count())"
```

Verify risk assessments:

```cmd
python manage.py shell -c "from apps.risk.models import RiskAssessment; print(RiskAssessment.objects.count())"
```

Verify evidence:

```cmd
python manage.py shell -c "from apps.evidence.models import Evidence; print(Evidence.objects.count())"
```

\---

# 30\. Run the Application

Start Django:

```cmd
python manage.py runserver
```

Then open:

```text
http://127.0.0.1:8000/
```

The dashboard/application can then be used to inspect transactions and investigate their risk.

\---

# 31\. Investigation Assistant API Example

Endpoint:

```text
POST /api/investigate/<transaction\\\_id>/ask/
```

Request body:

```json
{
  "question": "Is this suspicious?"
}
```

Another example:

```json
{
  "question": "Why did the risk increase?"
}
```

Another:

```json
{
  "question": "Why no suspicious?"
}
```

The assistant should answer based on the selected transaction's available evidence.

\---

# 32\. Example Investigation Questions

### Suspicion

```text
Is this suspicious?
```

The answer should evaluate the available evidence against the RazorGuard risk assessment.

### Safety

```text
Is this safe?
```

The answer should explain the risk category and supporting/reducing signals without claiming certainty beyond the evidence.

### Risk

```text
What caused the risk?
```

The answer should focus on risk-increasing signals.

### Score

```text
Explain the risk score.
```

The answer should explain the ML, rules, behavioral, graph, and final score.

### Behavior

```text
Is this normal for the customer?
```

The answer should compare the current activity with customer history.

### Evidence

```text
What evidence do we have?
```

The answer should summarize the stored evidence.

### General

```text
What happened?
```

The assistant should provide a transaction assessment rather than assuming the transaction was flagged.

\---

# 33\. Testing

Run Django's test suite with:

```cmd
python manage.py test
```

If the repository organizes tests under a specific `tests` package, the project documentation also identifies:

```cmd
python manage.py test tests
```

Use the command matching the actual test layout in the current checkout.

Testing should cover important areas such as:

* rule behavior,
* behavioral scoring,
* graph behavior,
* risk aggregation,
* APIs,
* investigation behavior.



## Engineering Challenge & Recovery

During development, we performed a fresh database rebuild to verify that the project could be reproduced from a clean state.

The initial risk backfill exposed an integration issue in the graph-risk scoring layer: the required graph scoring function was missing from the graph service, causing the initial backfill pipeline to fail.

Instead of bypassing the failure, we traced the issue through the risk pipeline, identified the missing graph-risk integration, implemented the required graph scoring and evidence generation, and reran the complete backfill process.

### Final Verification

- Transactions processed: **1,000**
- Skipped: **0**
- Failed: **0**

The successful rebuild validated the complete reproducibility flow:

```text
Fresh Database
      ↓
Django Migrations
      ↓
Seed Demo Transactions
      ↓
Risk Backfill
      ↓
ML + Rules + Behavioral + Graph
      ↓
Risk Assessment + Evidence

\---

# 34\. Environment Variables

The project uses environment-based configuration.

Important configuration includes:

|Variable|Purpose|
|-|-|
|`GEMINI\\\_API\\\_KEY`|Authentication for Google Gemini|
|`GEMINI\\\_MODEL`|Optional Gemini model configuration where supported|
|`DJANGO\\\_SECRET\\\_KEY`|Django secret key|
|`DJANGO\\\_DEBUG`|Django debug configuration|
|`DJANGO\\\_ALLOWED\\\_HOSTS`|Allowed hosts|
|`POSTGRES\\\_DB`|PostgreSQL database name when PostgreSQL is used|
|`POSTGRES\\\_USER`|PostgreSQL username|
|`POSTGRES\\\_PASSWORD`|PostgreSQL password|
|`POSTGRES\\\_HOST`|PostgreSQL host|

The project has historically supported a local SQLite fallback when PostgreSQL configuration is not supplied.

Never commit production secrets.

\---

# 35\. Advantages

## 1\. Multi-signal risk intelligence

A transaction is evaluated from several perspectives instead of relying on one prediction.

## 2\. Explainability

The system stores the individual components of the risk decision.

## 3\. Customer-specific behavioral analysis

A transaction can be compared with the customer's own historical behavior.

## 4\. Deterministic rules

Rules are transparent and easier to audit than purely statistical decisions.

## 5\. Relationship awareness

Shared devices and IP addresses can provide useful relationship context.

## 6\. Evidence-driven investigation

Investigators receive evidence rather than only a score.

## 7\. Natural-language investigation

An investigator can ask questions in normal language.

## 8\. LLM safety boundary

Gemini is separated from the authoritative risk engine.

## 9\. Graceful fallback

The deterministic investigation path can still provide useful answers when the LLM is unavailable.

## 10\. Auditability

Investigation actions and questions can be recorded.

## 11\. Modular architecture

ML, rules, behavior, graph analysis, evidence, investigation, and audit functionality are separated into domains.

## 12\. Human-in-the-loop design

The system assists an investigator rather than blindly replacing human judgment.

\---

# 36\. Real-World Use Cases

The architecture is applicable to:

* payment gateways,
* fintech platforms,
* digital wallets,
* e-commerce payment systems,
* banking transaction monitoring,
* merchant risk monitoring,
* fraud operations,
* transaction investigation teams,
* financial crime investigation workflows.

The current project is a prototype and uses synthetic data, so these should be understood as target application areas rather than claims of production deployment.

\---

# 37\. What This Project Solves

The project addresses a major weakness of simple fraud classifiers:

```text
Traditional:

Transaction
     ↓
Fraud Model
     ↓
Fraud / Not Fraud
```

versus:

```text
Transaction
     ↓
ML
     +
Rules
     +
Behavior
     +
Graph
     ↓
Risk Aggregation
     ↓
Final Risk Assessment
     ↓
Evidence
     ↓
Investigation
     ↓
Human-readable Explanation
```

The second approach is more useful when an investigator needs to understand **why** a transaction received its risk assessment.

\---

# 38\. Security and Reliability Principles

Important design principles include:

### No unrestricted LLM database access

The investigation assistant uses predefined backend tools.

### No invented transaction evidence

The explanation layer should be grounded in backend-provided evidence.

### Risk engine remains authoritative

Gemini cannot legitimately rewrite the underlying risk score.

### Secrets belong in environment configuration

API keys should not be committed to Git.

### Validation

Investigation questions are validated before processing.

### Failure handling

The system contains deterministic investigation behavior so an LLM failure does not necessarily make investigation unavailable.

\---

# 39\. Limitations

This project is intentionally a prototype and has important limitations.

### Synthetic data

The training/development workflow uses synthetic transactions. Real-world fraud behavior is considerably more complex.

### Model performance

Prototype model metrics should not be interpreted as production fraud-detection performance.

### Graph scope

The graph analysis is scoped and should not be considered a complete enterprise fraud-ring/community detection system.

### Explainability

The system provides evidence-based explanations, but it does not currently represent a complete formal model-explainability stack such as SHAP.

### Synchronous processing

The current architecture performs scoring synchronously and would need asynchronous processing for very high transaction throughput.

### Authentication / authorization

The prototype is not a complete multi-tenant production investigation platform.

### LLM dependency

Gemini requires API access when the optional conversational layer is used.

\---

# 40\. Future Improvements

Potential production-oriented extensions include:

1. Real payment gateway integration
2. Streaming transaction processing
3. Asynchronous scoring with a task queue
4. Model monitoring
5. Concept drift detection
6. Threshold calibration
7. Cost-sensitive fraud decisioning
8. SHAP-based model explanations
9. More advanced graph community detection
10. Fraud-ring detection
11. Investigator case management
12. Alert lifecycle management
13. Role-based access control
14. Multi-tenant architecture
15. Rate limiting
16. Production PostgreSQL deployment
17. Containerization with Docker
18. Cloud deployment
19. Multi-provider LLM abstraction
20. Human feedback loops for model improvement

These are future improvements and are not claims that they are already implemented.

\---

# 41\. Engineering Highlights

The strongest engineering aspects of the project are the combination of:

```text
Machine Learning
       +
Feature Engineering
       +
Django / REST APIs
       +
Rule-Based Intelligence
       +
Behavioral Analytics
       +
Graph Analysis
       +
Risk Aggregation
       +
Evidence Generation
       +
LLM Investigation
       +
Auditability
```

The project therefore demonstrates more than a simple ML classifier.

It demonstrates how an ML prediction can be integrated into a broader risk and investigation system.

\---

# 42\. Recommended Project Review Flow

For a technical review, explain the project in this order:

### 1\. Problem

Fraud detection produces scores, but investigators need reasons and evidence.

### 2\. Solution

Build a multi-signal transaction risk intelligence platform.

### 3\. Transaction

Explain the transaction and customer entities.

### 4\. ML

Explain the model and feature engineering.

### 5\. Rules

Explain deterministic signals.

### 6\. Behavior

Explain customer-specific baselines.

### 7\. Graph

Explain shared-device/IP relationships.

### 8\. Risk aggregation

Explain how subsystem scores become the final risk score.

### 9\. Evidence

Explain how the decision becomes auditable.

### 10\. Investigation Assistant

Explain natural-language investigation.

### 11\. Gemini

Explain that Gemini is an explanation layer and not the authoritative decision-maker.

### 12\. Audit

Explain why financial systems need traceability.

### 13\. Limitations

Be honest about synthetic data and prototype constraints.

### 14\. Future work

Explain how the prototype could evolve into a production platform.

\---

# 43\. One-Minute Project Explanation

> \\\*\\\*Transaction Risk Intelligence is an explainable payment risk and investigation platform. Instead of relying on a single fraud classifier, it combines machine-learning predictions with deterministic rules, customer behavioral analysis, and relationship-based graph analysis. These signals are aggregated into a final risk score with a risk category, confidence, and recommended action. The system then stores structured evidence explaining the decision. Investigators can ask natural-language questions such as "Is this suspicious?", "Why did the risk increase?", or "What evidence do we have?" through the Investigation Assistant. Google Gemini can provide the conversational explanation, but the underlying deterministic risk engine remains the source of truth. This makes the system useful not only for detecting unusual transactions but also for explaining and investigating them.\\\*\\\*

\---

# 44\. Project Philosophy

The project follows four principles:

### Detect

Identify unusual and potentially risky transactions.

### Explain

Show which signals contributed to the assessment.

### Investigate

Allow investigators to ask questions about the transaction and its context.

### Audit

Preserve a traceable record of investigation activity.

In short:

> \\\*\\\*Detect → Explain → Investigate → Audit\\\*\\\*

\---

# 45\. Current Implementation Notes

The repository has evolved during development. In particular, the Investigation Assistant has been designed to support useful deterministic answers even when Gemini is unavailable.

The current intended LLM provider is **Google Gemini**.

If an older README, requirements file, comment, or environment example still references Anthropic/Claude, that reference should be treated as stale documentation and removed from the current repository configuration.

Similarly, the dependency list should contain the Google Gemini SDK required by the current source code.

Before a fresh deployment, always verify:

```cmd
python manage.py check
```

and confirm that all runtime dependencies listed by the current source are present.

\---

# 46\. License

If this repository contains an MIT `LICENSE` file, the MIT License generally permits use, modification, distribution, and private/commercial use, subject to the license conditions and preservation of the copyright/license notice.

Refer to the repository's actual `LICENSE` file as the authoritative license text.

\---

# 47\. Repository

GitHub:

```text
https://github.com/Sushanth-yadav/transaction-risk-intelligence
```

\---

## Final Architecture Summary

```text
                     ┌─────────────────────┐
                     │     Transaction     │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │ Feature Engineering │
                     └──────────┬──────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
          ▼                     ▼                     ▼
    ┌───────────┐         ┌───────────┐        ┌──────────────┐
    │ ML Model  │         │ Rule      │        │ Behavioral   │
    │           │         │ Engine    │        │ Analysis     │
    └─────┬─────┘         └─────┬─────┘        └──────┬───────┘
          │                     │                     │
          └─────────────────────┼─────────────────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │ Graph / Relationship│
                     │      Analysis       │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │  Risk Aggregation   │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │  Risk Assessment    │
                     │ Score / Category /  │
                     │ Confidence / Action │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │ Evidence Generation │
                     └──────────┬──────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
             ┌─────────────┐       ┌────────────────┐
             │ Investigation│       │    Dashboard   │
             │     API      │       └────────────────┘
             └──────┬──────┘
                    │
                    ▼
          ┌───────────────────────┐
          │ Investigation         │
          │ Orchestrator + Tools  │
          └──────────┬────────────┘
                     │
                     ▼
          ┌───────────────────────┐
          │ Optional Google       │
          │ Gemini Explanation    │
          └──────────┬────────────┘
                     │
                     ▼
          ┌───────────────────────┐
          │ Investigator-Friendly │
          │ Explanation           │
          └───────────────────────┘
```

**Transaction Risk Intelligence is ultimately an investigation system, not merely a fraud classifier.**



