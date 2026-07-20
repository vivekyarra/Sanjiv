# Sanjiv — India’s Energy Resilience Command Center

> **Keep India’s energy moving.**

No project can guarantee a hackathon win, but **this is the complete version of Sanjiv I would build to maximize the probability of winning**.

Sanjiv should not be presented as an oil dashboard, tanker tracker, chatbot, or collection of AI agents. It should be presented as:

> **A live decision-intelligence system that detects threats to India’s maritime energy supply, simulates the consequences, and generates an auditable procurement and strategic-reserve response within seconds.**

The complete workflow is:

> **Observe → Detect → Simulate → Optimise → Approve → Monitor**

This directly covers the problem statement’s geopolitical intelligence, disruption modelling, procurement orchestration, reserve optimisation, and digital-twin areas. The judges specifically evaluate signal-detection lead time, executability of alternatives, explicit and testable assumptions, geospatial evidence, and end-to-end response time.

---

# 1. The exact product

## Product name

**Sanjiv**<br>
**India’s Energy Resilience Command Center**<br>
**Tagline: Keep India’s energy moving.**

## Expanded product description

**Sanjiv is an AI-powered national energy resilience command centre for India.**

It continuously monitors:

* Tanker movements
* Chokepoint traffic
* Geopolitical events
* Sanctions
* Commodity prices
* Energy inventories
* Refinery capacities
* Import patterns
* Strategic reserve capacity
* Port and infrastructure incidents

When a disruption is detected or manually entered, Sanjiv:

1. Identifies the supply routes and assets potentially affected.
2. Estimates which Indian energy flows are exposed.
3. Simulates the disruption over time.
4. Calculates refinery, inventory and supply consequences.
5. Generates alternative procurement plans.
6. Determines whether strategic reserves should be released.
7. Explains every recommendation with sources, assumptions and confidence.
8. Tracks whether the approved response is working.

## One-line pitch

> **Describe an energy disruption in plain English. Sanjiv shows India’s exposed supply flows and targets a defensible procurement and reserve response in under ten seconds.**

The latency is an engineering target until measured for the current run and environment.

## Core product promise

Sanjiv must answer five questions:

1. **What is happening?**
2. **Which energy flows are exposed?**
3. **What happens if no action is taken?**
4. **What is the best available response?**
5. **Why should the decision-maker trust that response?**

---

# 2. Primary users

Sanjiv should support four user roles.

## National Energy Crisis Commander

Usually a policymaker or senior official.

Needs:

* National supply-shortfall forecast
* Days of inventory cover
* Strategic reserve recommendation
* Economic and operational consequences
* Clear choices and trade-offs

## Refinery Procurement Head

Needs:

* Alternative crude grades
* Alternative suppliers
* Landed cost
* Arrival dates
* Compatibility with refinery configuration
* Candidate shipping capacity
* Sanctions and corridor risk

## Maritime and Geopolitical Analyst

Needs:

* Live vessel activity
* Chokepoint anomalies
* News and security events
* Risk explanations
* Source provenance
* Historical comparison

## Strategic Reserve Planner

Needs:

* Reserve-site inventory assumptions
* Drawdown schedule
* Delivery constraints
* Minimum safety stock
* Replenishment strategy

The same interface can expose different detail levels according to the selected role.

---

# 3. Product scope

## Primary commodity

**Crude oil**

Build crude oil deeply because it allows you to demonstrate:

* Tanker movements
* Supplier substitution
* Refinery compatibility
* Strategic reserves
* Chokepoint dependency
* Procurement optimisation

## Secondary commodity

**LPG**

LPG becomes the second-commodity demonstration proving that Sanjiv is a reusable energy-resilience platform rather than a single crude-oil scenario application.

## Future commodities

After crude and LPG work correctly:

* LNG
* Fertiliser feedstock
* Coal
* Refined petroleum products

Do not dilute the crude model before it is complete and validated.

---

# 4. The complete Sanjiv platform

Sanjiv should contain eight connected modules.

---

## Module 1 — Sanjiv Watch

### Purpose

Create the real-time operational picture.

### Main screen

A live global maritime map focused on:

* Strait of Hormuz
* Bab el-Mandeb
* Suez Canal
* Strait of Malacca
* Cape of Good Hope
* Major crude-loading regions
* Indian ports
* Indian refineries
* Indian strategic reserve locations

### Live vessel features

Each tanker should display:

* Vessel name
* MMSI
* IMO number, when available
* Vessel type
* Latitude and longitude
* Speed over ground
* Course over ground
* Heading
* Navigation status
* Reported destination
* Reported ETA
* Draught, when available
* Last AIS update
* Track history
* Distance to chokepoint
* Estimated time to chokepoint
* Estimated time to Indian port
* Sanctions match
* India-bound confidence
* Current risk state

### Vessel colours

* **Green:** No current exposure
* **Yellow:** Approaching a monitored risk corridor
* **Orange:** Potentially affected
* **Red:** Inside or directly dependent on disrupted corridor
* **Purple:** Sanctions or compliance alert
* **Grey:** Data is stale

### Essential honesty rule

Sanjiv must not automatically call a vessel “India’s tanker.”

AIS destination information is manually entered and may contain free-text inconsistencies. AIS also does not reveal the vessel’s private charter contract or exact cargo ownership. ([Navigation Center][1])

Instead, Sanjiv displays:

> **India-bound likelihood: 84%**

Along with reasons:

* Reported destination resembles Jamnagar
* Current route geometry points toward India
* Previous position passed through the Arabian Sea
* Vessel class is consistent with the route
* ETA is consistent with expected arrival

### India-bound confidence model

Use a transparent heuristic initially:

[
C_{\text{India}} =
0.30D +
0.25R +
0.20H +
0.15P +
0.10V
]

Where:

* (D): destination-text match
* (R): route-cone match
* (H): heading consistency
* (P): previous-port consistency
* (V): vessel-class consistency

Display every contribution.

Later, calibrate the model using historical arrivals at Indian ports.

### AIS implementation

AISStream provides a WebSocket stream containing vessel positions, direction and other AIS messages. Its documentation recommends connecting from the backend so API keys are not exposed in the browser. The service is in beta, offers no SLA, and its terrestrial coverage is primarily around coastlines rather than complete open-ocean coverage. ([aisstream.io][2])

Therefore Sanjiv must display:

* AIS connection status
* Messages received per minute
* Last successful message
* Coverage disclaimer
* Staleness indicator
* Live/replay mode

---

## Module 2 — Sanjiv Sentinel

### Purpose

Detect emerging geopolitical and logistics threats before the user manually enters a scenario.

### Signals monitored

#### Geopolitical signals

* Armed conflict
* Threats against shipping
* Port closures
* Sanctions announcements
* Diplomatic escalation
* Labour strikes
* Political instability
* Terrorism or piracy
* Export restrictions
* Supplier-country instability

#### Maritime signals

* Sudden fall in chokepoint transits
* Tanker queue growth
* Unusual vessel slowdown
* Vessel diversion
* Abnormal anchorage duration
* AIS silence concentration
* Route abandonment
* Port-congestion increase

#### Market signals

* Crude benchmark movement
* Freight-rate proxies
* Inventory changes
* Volatility spikes
* Currency movement
* Refining-margin movement

#### Physical infrastructure signals

* Fire or thermal anomaly near:

  * Refineries
  * Oil terminals
  * Storage facilities
  * Ports
* Severe weather
* Earthquake
* Pipeline outage
* Port infrastructure failure

### Sources

GDELT can provide near-real-time news and event metadata, with its core datasets updating on a roughly 15-minute cycle. ([GDELT Project][3])

IMF PortWatch provides daily AIS-derived estimates covering 1,666 ports and 24 critical maritime passages from 2019 onward, making it useful for historical baselines and chokepoint anomaly detection rather than second-by-second tracking. ([IMF eLibrary][4])

NASA FIRMS can provide active-fire and thermal-hotspot data through downloadable products and web services. It should be treated as a supporting physical-event signal rather than automatic proof of an attack or industrial accident. ([NASA FIRMS][5])

### Corridor risk score

Generate a transparent score from 0 to 100.

[
R =
0.30T +
0.25G +
0.15A +
0.15M +
0.10S +
0.05I
]

Where:

* (T): transit anomaly
* (G): geopolitical-event severity
* (A): AIS behavioural anomaly
* (M): market stress
* (S): sanctions exposure
* (I): infrastructure or physical-event signal

### Risk-output example

**Strait of Hormuz — Risk 81/100, Critical**

Contributions:

* Transit count 42% below seasonal baseline: +24
* Conflict-event volume elevated: +20
* Tanker speed and route diversions detected: +13
* Brent volatility elevated: +11
* New maritime-sanctions entities: +9
* Data completeness: 88%

Do not describe this as an 81% probability unless the model has been historically calibrated as a probability model.

### Risk confidence

Keep risk severity and data confidence separate.

Example:

* **Risk severity:** 81/100
* **Evidence confidence:** High
* **Data completeness:** 88%
* **Last recalculation:** 48 seconds ago

---

## Module 3 — Sanjiv Scenario Compiler

### Purpose

Convert natural-language scenarios into valid, testable simulation parameters.

### Input examples

* “Iran closes the Strait of Hormuz for 72 hours.”
* “Bab el-Mandeb traffic falls by 60% for two weeks.”
* “A new sanction blocks crude shipments from supplier X.”
* “Jamnagar loses 30% of refining capacity for seven days.”
* “India’s diesel demand increases 12% while Suez is closed.”
* “Simulate simultaneous disruption at Hormuz and Bab el-Mandeb.”

### Structured scenario format

```json
{
  "scenario_name": "Hormuz closure for 72 hours",
  "event_type": "chokepoint_capacity_loss",
  "affected_assets": ["STRAIT_OF_HORMUZ"],
  "commodities": ["crude_oil"],
  "start_time": "now",
  "duration_hours": 72,
  "capacity_reduction_pct": 100,
  "demand_change_pct": 0,
  "supplier_outages": [],
  "refinery_outages": [],
  "reserve_policy": "allow_with_minimum_floor",
  "simulation_horizon_days": 30,
  "uncertainty": {
    "duration_range_hours": [48, 120],
    "capacity_loss_range_pct": [80, 100]
  },
  "assumptions": [
    "Commercial inventory levels use latest available public data or user-supplied estimates",
    "No private charter-contract information is available"
  ]
}
```

### Compiler design

Use an LLM only to:

* Interpret the language
* Identify entities
* Assign scenario type
* Extract numerical values
* Produce valid JSON
* Explain the parsed scenario

Then pass the output through deterministic validation.

### Validation rules

* Duration must be positive.
* Capacity loss must be between 0% and 100%.
* Every asset must exist in the network graph.
* Every commodity must be supported.
* Start date must be valid.
* Unsupported supplier or refinery names must be resolved.
* Missing values must use visible defaults.
* The system must never invent an asset silently.

### Scenario confirmation card

Before running, display:

**Sanjiv understood:**

* Asset: Strait of Hormuz
* Capacity loss: 100%
* Duration: 72 hours
* Commodities: Crude oil
* Analysis horizon: 30 days
* Reserve drawdown: Permitted
* Uncertainty interval: 48–120 hours

The user can edit any value.

---

## Module 4 — Sanjiv Digital Twin

### Purpose

Represent India’s energy-supply network as a dynamic graph.

### Network nodes

#### Supplier nodes

* Supplier countries
* Production regions
* Crude-loading ports
* LPG-loading terminals

#### Maritime nodes

* Chokepoints
* Major waypoints
* Alternative passages
* Transshipment locations

#### Indian infrastructure nodes

* Import terminals
* Ports
* Refineries
* Strategic reserve sites
* Product-distribution regions
* Demand centres

### Network edges

Each edge stores:

* Origin
* Destination
* Distance
* Typical sailing time
* Capacity
* Cost
* Chokepoint dependencies
* Vessel-size constraints
* Port-draft constraints
* Risk score
* Sanctions status
* Emissions estimate
* Current availability
* Disruption-capacity multiplier

### Indian reference data

PPAC publishes current and historical information covering crude imports and exports, refinery processing, petroleum-product consumption, refinery locations and installed capacities. Its refinery-capacity dataset lists a national installed capacity of 258.116 million tonnes per year as of April 2025. ([Petroleum Planning & Analysis Cell][6])

Use PPAC for:

* Refinery names
* Refinery locations
* Installed capacity
* Historical processing
* National crude imports
* Product consumption
* Historical demand trends

### Crude-grade catalogue

Create a curated reference catalogue containing approximately 12–20 major crude grades.

Each grade should include:

* Grade name
* Country
* Load port
* API gravity range
* Sulfur range
* Typical price differential
* Historical availability
* Typical tanker type
* Sanctions exposure
* Carbon-intensity estimate, optional

### Refinery-compatibility matrix

Each refinery receives:

* Maximum throughput
* Approximate complexity class
* Preferred API-gravity range
* Maximum sulfur tolerance
* Coastal or inland classification
* Connected ports
* Pipeline constraints
* Minimum viable utilization
* Product-yield profile

Compatibility score:

[
C_{g,r} =
w_1C_{\text{gravity}} +
w_2C_{\text{sulfur}} +
w_3C_{\text{configuration}} +
w_4C_{\text{logistics}}
]

Classification:

* **0.80–1.00:** Preferred
* **0.60–0.79:** Acceptable with cost or yield penalty
* **0.40–0.59:** Technically difficult
* **Below 0.40:** Disallowed

Where exact public refinery limits are unavailable, store the value as a **model assumption**, not observed fact.

### Time resolution

Use:

* Six-hour intervals for the first 14 days
* Daily intervals from day 15 to day 90

This captures immediate logistics while keeping simulations fast.

---

## Module 5 — Sanjiv Impact Simulator

### Purpose

Calculate the consequences of a disruption under “no action” and alternative responses.

### Core inventory equation

For refinery (r) and time (t):

$$
I_{r,t+1} = I_{r,t} + A_{r,t} + S_{r,t} - P_{r,t}
$$

Where:

* (I): inventory
* (A): cargo arrivals
* (S): strategic reserve release
* (P): crude processed

### Refinery run-rate

$$
U_{r,t} = \min\left(C_r, \frac{I_{r,t}+A_{r,t}+S_{r,t}}{\Delta t}\right)
$$

Where (C_r) is refinery capacity.

### Outputs

Sanjiv must calculate:

* Cargo delays
* Daily crude arrivals
* Daily supply shortfall
* Refinery utilization
* Inventory-cover days
* Strategic-reserve usage
* Additional procurement cost
* Route concentration
* Supplier concentration
* Sanctions exposure
* Average arrival delay
* Additional sailing distance
* Additional emissions
* Product-output pressure
* Demand not served

### No-action baseline

Every scenario begins by running:

> **What happens if India takes no action?**

This produces the counterfactual baseline against which Sanjiv recommendations are measured.

### Price impact

Do not present a single exact petrol-price prediction.

Display a range based on visible assumptions:

* Low sensitivity
* Central sensitivity
* High sensitivity

Example:

> Estimated wholesale fuel-price pressure: **+2.8% to +5.1%**

With:

* Historical relationship used
* Lag assumption
* Exchange-rate assumption
* Tax pass-through assumption
* Confidence range

### Economic impact

Keep GDP effects in an advanced analysis panel, not the main demo.

Label them:

> **Modeled macroeconomic sensitivity — not a forecast**

Use FRED for accessible macroeconomic series and EIA for energy statistics, prices and inventories. Both provide documented APIs, though update frequency differs by series. ([FRED][7])

### Uncertainty simulation

Run two modes.

#### Fast mode

* Deterministic baseline
* 30–50 sampled disruption combinations
* Designed for interactive response

#### Deep analysis mode

* 500 or more Monte Carlo runs
* Duration uncertainty
* Capacity-loss uncertainty
* Price uncertainty
* Supplier-capacity uncertainty
* Vessel-delay uncertainty
* Inventory uncertainty

Outputs:

* Median result
* 10th–90th percentile
* Best case
* Worst case
* Main drivers of uncertainty

---

## Module 6 — Sanjiv Procurement Optimiser

This should be the strongest technical component.

### Purpose

Produce executable, ranked alternatives rather than generic LLM advice.

### Decision variables

For:

* Supplier (s)
* Crude grade (g)
* Refinery (r)
* Route (p)
* Time (t)

Let:

[
x_{s,g,r,p,t}
]

represent the volume procured.

### Objective function

[
\min
\left[
\text{Landed Cost}
+
\lambda_1\text{Shortage}
+
\lambda_2\text{Delay}
+
\lambda_3\text{Route Risk}
+
\lambda_4\text{Concentration}
+
\lambda_5\text{Compatibility Penalty}
+
\lambda_6\text{Reserve Depletion}
+
\lambda_7\text{Emissions}
\right]
]

### Constraints

The optimiser must enforce:

* Supplier export-capacity limit
* Crude-grade availability
* Refinery throughput
* Refinery-grade compatibility
* Port capacity
* Port-draft limit
* Vessel-size restriction
* Route capacity
* Chokepoint availability
* Delivery window
* Budget
* Strategic-reserve minimum floor
* Sanctions exclusion
* Minimum diversification
* Maximum supplier concentration
* Maximum corridor concentration
* Inventory mass balance
* Demand-satisfaction requirement

### Output three plans

#### Plan A — Lowest cost

Prioritises procurement cost.

#### Plan B — Highest resilience

Prioritises supply continuity and diversification.

#### Plan C — Balanced

Balances cost, shortfall, timing and risk.

### Plan card example

**Balanced Response Plan**

* Increase West African allocation: modeled amount
* Increase US Gulf allocation: modeled amount
* Reduce affected Middle East exposure
* Draw strategic reserve on days 4–7
* Reassign arrivals between selected Indian ports
* Estimated shortfall reduction: 78%
* Additional landed cost: ₹X crore
* Average delay: X days
* Residual risk: Medium
* Confidence: 76%

### Explainability

Every recommendation should have a **Why this plan?** button.

It must show:

* Constraints satisfied
* Main objective contributions
* Why the route was selected
* Why other options were rejected
* Cost-versus-resilience trade-off
* Assumptions affecting the result

### Rejected-option explanation

Example:

**Why was Supplier B not selected?**

* Suitable grade: Yes
* Available capacity: Yes
* Delivery time: Too late
* Route risk: High
* Sanctions exposure: None
* Total landed cost: 14% higher
* Decision: Rejected due to delivery-window violation

### Candidate vessel matching

Sanjiv can identify candidate vessels near load ports based on:

* Vessel class
* Position
* Navigation status
* Speed
* Draught
* Proximity
* Recent movement
* Sanctions status

The UI must say:

> **Candidate transport capacity — commercial availability unverified**

Never say:

> “Book this tanker now.”

AIS cannot prove charter availability.

### Sanctions screening

OFAC’s Sanctions List Service provides current downloadable sanctions data and includes maritime vessels on the SDN list. ([OFAC][8])

Match vessels using:

* IMO number
* MMSI
* Vessel name
* Call sign
* Known aliases
* Owner or operator, when available

Use exact matching for IMO and MMSI and fuzzy matching only for names.

---

## Module 7 — Sanjiv Reserve

### Purpose

Determine whether, when and where India should release strategic reserves.

ISPRL states that India’s first-phase strategic-storage capacity totals 5.03 million metric tonnes across Visakhapatnam, Mangalore and Padur. ([ISPRL][9])

### Important distinction

Public capacity does not necessarily reveal current fill level.

Therefore show:

* **Storage capacity:** Observed
* **Current fill level:** User-supplied, latest verified value or assumption
* **Available drawdown:** Derived
* **Recommended release:** Modeled

### Reserve optimisation inputs

* Scenario duration
* Expected import shortfall
* Commercial inventory estimate
* Refinery demand
* Reserve-site location
* Pipeline connectivity
* Coastal-shipping capacity
* Minimum emergency floor
* Replenishment lead time
* Refill-price forecast range
* Probability of disruption extension

### Objective

[
\min
\left[
\text{Supply Shortage}
+
\alpha\text{Reserve Depletion}
+
\beta\text{Logistics Cost}
+
\gamma\text{Future Vulnerability}
\right]
]

### Reserve-plan output

* Which site releases crude
* Release start date
* Daily quantity
* Receiving refinery
* Transportation path
* Remaining reserve
* Days of cover after release
* Replenishment recommendation

### Policy modes

* Conservative reserve use
* Balanced reserve use
* Aggressive continuity protection
* No reserve use

The judge should be able to change policy mode and immediately see the result.

---

## Module 8 — Sanjiv Evidence Auditor

This is one of the most important differentiators.

### Purpose

Prevent hallucinations and make every output defensible.

### Every displayed number must carry

* Source
* Source URL through the UI
* Effective date
* Fetch timestamp
* Freshness
* Transformation
* Formula version
* Confidence
* Truth class

### Truth classes

#### OBSERVED

Directly retrieved from a source.

Examples:

* AIS position
* PPAC refinery capacity
* OFAC vessel match

#### DERIVED

Calculated from observed data.

Examples:

* Distance to chokepoint
* Transit-count anomaly
* Estimated arrival time

#### INFERRED

Estimated classification.

Examples:

* India-bound likelihood
* Possible diversion
* Possible vessel availability

#### MODELED

Produced by the simulator or optimiser.

Examples:

* Expected shortfall
* Recommended procurement volume
* Reserve-release schedule

#### ASSUMPTION

User-entered or defaulted because no public value exists.

Examples:

* Current refinery inventory
* Supplier spot capacity
* Current strategic-reserve fill level
* Commercial freight quote

### Evidence drawer

Clicking any KPI must reveal:

```text
Metric: Refinery utilisation on day 7
Value: 74%
Type: MODELED
Model version: scenario-engine-1.3
Inputs:
- Refinery capacity: PPAC, effective 01 Apr 2025
- Initial inventory: Assumption, 8.0 days
- Affected arrivals: AIS-derived route inference
- Scenario capacity loss: User input, 100%
Last computed: 14:32:08 IST
Confidence: Medium
```

### Auditor rules

The Evidence Auditor must block statements such as:

* “This vessel is definitely carrying Indian crude.”
* “This vessel is available for charter.”
* “Consumer petrol prices will increase exactly 8%.”
* “The reserve currently contains X tonnes,” without verified data.
* “The chokepoint is closed,” based only on news volume.

---

# 5. Data-source architecture

| Source                        | Used for                                 | Freshness classification | Sanjiv treatment                        |
| ----------------------------- | ---------------------------------------- | ------------------------ | -------------------------------------- |
| AISStream                     | Vessel position and movement             | Live stream              | Observed vessel movement               |
| IMF PortWatch                 | Chokepoint and port baselines            | Daily/historical         | Observed estimate and anomaly baseline |
| GDELT                         | News and geopolitical events             | Near-real-time           | Observed media/event signal            |
| OFAC                          | Sanctions screening                      | Latest published list    | Observed compliance status             |
| PPAC                          | Indian imports, refining and consumption | Periodic/monthly         | Official structural baseline           |
| ISPRL                         | Reserve-site capacity                    | Periodic/static          | Official capacity                      |
| EIA                           | Prices, inventories and supply           | Series dependent         | Market and supply inputs               |
| FRED                          | Macroeconomic indicators                 | Series dependent         | Macro sensitivity inputs               |
| UN Comtrade                   | Historical supplier trade flows          | Periodic                 | Supplier baseline                      |
| NASA FIRMS                    | Thermal anomalies                        | Near-real-time           | Supporting incident signal             |
| Curated grade catalogue       | Crude properties                         | Versioned reference      | Sourced static data                    |
| User-entered operational data | Inventory, contracts, freight quotes     | Current user input       | Private operational assumption/input   |

UN Comtrade offers detailed international trade information and developer API access, making it suitable for historical supplier-flow baselines rather than live cargo tracking. ([uncomtrade.org][10])

---

# 6. Data freshness system

Every data source must display a freshness badge.

* **LIVE:** Less than 60 seconds
* **RECENT:** Less than one hour
* **CURRENT:** Within expected source-update cycle
* **STALE:** Source has missed its expected update
* **REPLAY:** Recorded real data
* **UNAVAILABLE:** Source cannot currently be reached

Example header:

```text
AIS: LIVE, 4 seconds
GDELT: CURRENT, 11 minutes
PortWatch: CURRENT, latest daily estimate
PPAC: CURRENT, June 2026 report
OFAC: CURRENT, checked 2 hours ago
```

Never merge all source cadences into one “real-time data” label.

---

# 7. Exact user interface

## Screen 1 — Command Centre

### Header

* Sanjiv logo
* Current mode: Live or Replay
* Current UTC/IST timestamp
* Overall system health
* Source-freshness status
* Scenario input bar
* User role selector

### KPI strip

* National corridor-risk level
* Tankers currently monitored
* Potentially exposed vessels
* Chokepoint throughput deviation
* Estimated inventory cover
* Active sanctions alerts
* Time since latest recommendation

### Main map

Approximately 65–70% of the screen.

Layers:

* Tankers
* Tanker tracks
* Chokepoint geofences
* Shipping corridors
* Indian ports
* Refineries
* Reserve sites
* Sanctioned vessels
* Thermal anomalies
* Diversion routes
* Risk heatmap

### Right-hand panel

* Active alerts
* Risk ranking
* Latest news events
* Data-source health
* Recent scenario runs

### Bottom timeline

* Vessel movement
* News spike
* Transit anomaly
* Price change
* Sanctions event
* Generated recommendation

---

## Screen 2 — Scenario Lab

Components:

* Natural-language scenario input
* Parsed scenario card
* Duration slider
* Capacity-reduction slider
* Demand-change slider
* Reserve-policy selector
* Commodity selector
* Confidence assumptions
* Simulation-horizon selector
* Run button

Results:

* No-action impact
* Map animation
* Supply arrivals
* Refinery utilization
* Inventory drawdown
* Shortfall chart
* Cost-pressure range
* Confidence interval

---

## Screen 3 — Response Planner

Components:

* Lowest-cost plan
* Balanced plan
* Highest-resilience plan
* Cost-versus-risk chart
* Rerouting map
* Procurement timeline
* Supplier allocation
* Refinery allocation
* Candidate vessels
* Reserve-release recommendation
* Rejected alternatives
* Approve-plan button

---

## Screen 4 — Strategic Reserve

Components:

* Three reserve-site cards
* Assumed or verified fill level
* Capacity
* Available drawdown
* Pipeline or coastal connection
* Recommended release
* Remaining cover
* Replenishment timeline

---

## Screen 5 — Evidence and Assumptions

Permanent access from every screen.

Tabs:

* Sources
* Assumptions
* Model formulas
* Data freshness
* Confidence
* Audit log
* Model version
* Scenario JSON

---

## Screen 6 — Historical Replay

Allow the user to:

* Select a historical disruption
* Replay data chronologically
* See when Sanjiv would have detected it
* Compare Sanjiv response against no action
* Measure detection lead time
* Measure recommendation runtime

This becomes your validation screen, not just a demo feature.

---

# 8. Multi-agent design

Do not create agents only for marketing. Each agent must have a distinct tool and output contract.

## 1. Signal Agent

Inputs:

* GDELT
* PortWatch
* AIS-derived features
* Commodity prices
* Sanctions changes
* Physical incident feeds

Output:

```json
{
  "event_type": "maritime_security_escalation",
  "location": "Strait of Hormuz",
  "severity": 0.84,
  "evidence_ids": ["ev_1", "ev_2", "ev_3"],
  "affected_assets": ["STRAIT_OF_HORMUZ"],
  "confidence": 0.79
}
```

## 2. Scenario Compiler Agent

Converts natural language into validated scenario JSON.

## 3. Network Impact Agent

Runs the digital-twin simulation and produces structured impact metrics.

## 4. Procurement Optimisation Agent

Calls the mathematical optimisation engine.

It does not independently invent procurement advice.

## 5. Strategic Reserve Agent

Runs reserve scheduling and policy constraints.

## 6. Evidence Auditor Agent

Checks every output against evidence records and blocks unsupported claims.

## 7. Executive Briefing Agent

Converts verified structured results into:

* One-page crisis briefing
* Procurement action summary
* Assumption summary
* Decision options
* Draft request-for-quotation message

### Agent orchestration

```text
Signal detected or user scenario
              ↓
      Scenario Compiler
              ↓
       Evidence validation
              ↓
       Network simulation
              ↓
   Procurement + Reserve optimisation
              ↓
       Evidence Auditor
              ↓
 Executive explanation and visualisation
```

The agents exchange structured JSON, not free-form paragraphs.

---

# 9. System architecture

```text
                    EXTERNAL DATA
 ┌──────────┬───────────┬────────┬──────┬───────┬────────┐
 │ AISStream│ PortWatch │ GDELT  │ OFAC │ PPAC  │ EIA etc│
 └────┬─────┴─────┬─────┴───┬────┴──┬───┴───┬───┴────┬───┘
      │           │         │       │       │        │
      ▼           ▼         ▼       ▼       ▼        ▼
 ┌────────────────────────────────────────────────────────┐
 │             INGESTION AND NORMALISATION                │
 │ Validation • deduplication • timestamps • source IDs  │
 └─────────────────────────┬──────────────────────────────┘
                           ▼
 ┌────────────────────────────────────────────────────────┐
 │                  EVIDENCE LEDGER                       │
 │ Raw record • source • freshness • truth class • hash  │
 └───────────────┬──────────────────────┬─────────────────┘
                 │                      │
                 ▼                      ▼
       ┌──────────────────┐   ┌─────────────────────┐
       │ Live geospatial  │   │ Risk feature engine │
       │ vessel twin      │   └──────────┬──────────┘
       └────────┬─────────┘              ▼
                │                ┌─────────────────┐
                └───────────────►│ Risk intelligence│
                                 └────────┬────────┘
                                          ▼
                              ┌──────────────────────┐
 Natural-language scenario ──►│ Scenario compiler    │
                              └──────────┬───────────┘
                                         ▼
                              ┌──────────────────────┐
                              │ Digital-twin model   │
                              └──────────┬───────────┘
                                         ▼
                     ┌───────────────────┴─────────────────┐
                     ▼                                     ▼
          ┌─────────────────────┐             ┌──────────────────┐
          │ Procurement solver  │             │ Reserve solver   │
          └──────────┬──────────┘             └─────────┬────────┘
                     └───────────────────┬────────────────┘
                                         ▼
                              ┌──────────────────────┐
                              │ Evidence Auditor     │
                              └──────────┬───────────┘
                                         ▼
                              ┌──────────────────────┐
                              │ Command-centre UI    │
                              └──────────────────────┘
```

---

# 10. Recommended technology stack

## Frontend

* React with Next.js
* TypeScript
* MapLibre GL
* deck.gl for high-volume geospatial layers
* Tailwind CSS
* Apache ECharts or Plotly for operational charts
* WebSocket client for live map updates

## Backend

* Python
* FastAPI
* Pydantic schemas
* Async WebSocket ingestion
* LangGraph for agent orchestration
* Background worker processes

## Storage

* PostgreSQL
* PostGIS for geospatial queries
* TimescaleDB extension for vessel positions and time series
* Redis for caching, pub/sub and job state
* S3 or MinIO for raw snapshots and replay files

## Simulation

* NetworkX for network graph operations
* NumPy and Pandas for calculations
* SimPy only where discrete-event behaviour is genuinely required

## Optimisation

* OR-Tools or Pyomo
* HiGHS as the open-source solver
* Linear programming initially
* Mixed-integer constraints only where necessary

## Observability

* OpenTelemetry
* Prometheus
* Grafana
* Structured JSON logging
* Source-health dashboard

## Deployment

* Docker Compose for local and demo environments
* One modular FastAPI application
* Separate workers for:

  * AIS ingestion
  * Periodic data refresh
  * Simulation and optimisation

Avoid unnecessary Kubernetes or dozens of microservices.

---

# 11. Core database entities

## `vessels`

```text
mmsi
imo
name
ship_type
flag
length
beam
deadweight_estimate
sanctions_status
created_at
updated_at
```

## `vessel_positions`

```text
mmsi
timestamp
latitude
longitude
speed
course
heading
navigation_status
draught
destination_raw
eta_raw
source
```

## `chokepoints`

```text
id
name
geometry
baseline_transits
baseline_tanker_transits
capacity
alternative_routes
```

## `ports`

```text
id
name
country
geometry
maximum_draught
supported_vessel_classes
handling_capacity
```

## `refineries`

```text
id
name
operator
location
annual_capacity
preferred_api_min
preferred_api_max
sulfur_tolerance
complexity_class
connected_ports
```

## `crude_grades`

```text
id
name
country
api_gravity
sulfur_pct
load_ports
price_differential
sanctions_status
```

## `routes`

```text
id
origin_port
destination_port
distance_nm
travel_time_hours
chokepoints
capacity
risk_score
emissions_factor
```

## `risk_events`

```text
id
event_type
location
start_time
severity
confidence
evidence_ids
affected_assets
status
```

## `scenarios`

```text
id
user_input
parsed_json
assumptions
created_at
created_by
```

## `scenario_runs`

```text
id
scenario_id
model_version
started_at
completed_at
runtime_ms
baseline_result
disrupted_result
uncertainty_result
```

## `procurement_plans`

```text
id
scenario_run_id
plan_type
total_cost
shortfall
average_delay
risk
supplier_concentration
route_concentration
actions
rejected_options
```

## `reserve_sites`

```text
id
name
capacity
current_fill
fill_truth_class
connected_assets
minimum_floor
```

## `evidence_records`

```text
id
source
source_record_id
effective_at
fetched_at
freshness_status
truth_class
raw_payload_hash
transformation
confidence
```

---

# 12. Backend API design

```text
GET  /api/live/vessels
GET  /api/live/chokepoints
GET  /api/live/risks
GET  /api/live/source-health

POST /api/scenarios/compile
POST /api/scenarios/run
GET  /api/scenarios/{run_id}

POST /api/procurement/optimise
GET  /api/procurement/{plan_id}

POST /api/reserves/optimise
GET  /api/reserves/{run_id}

GET  /api/evidence/{evidence_id}
GET  /api/assumptions/{scenario_id}
GET  /api/audit/{scenario_id}

POST /api/replay/start
POST /api/replay/stop

WS   /ws/operations
WS   /ws/scenarios/{run_id}
```

Every result object should include:

```json
{
  "value": 74,
  "unit": "percent",
  "truth_class": "MODELED",
  "confidence": 0.77,
  "evidence_ids": ["e_102", "e_108"],
  "source_refs": [{"source_id": "PPAC", "record_id": "capacity-2025-04"}],
  "effective_at": "2026-07-20T10:00:00Z",
  "fetched_at": "2026-07-20T10:00:02Z",
  "computed_at": "2026-07-20T10:00:04Z",
  "freshness_status": "CURRENT",
  "transformation": "scenario-engine.inventory-cover.v1",
  "model_version": "impact-engine-1.0"
}
```

---

# 13. Reliability and demo survival

## Recorded real-data buffer

Continuously record incoming AIS data.

Keep:

* Previous 24 hours
* Last stable 30-minute segment
* Preselected demo segment
* Historical replay datasets

When the live source fails:

```text
LIVE SOURCE INTERRUPTED
Switching to recorded AIS data from 13:15–13:45 IST
Data type: real recorded AIS
```

Do not silently pretend replay data is live.

## Data-source circuit breakers

For every source:

* Timeout
* Retry with backoff
* Rate-limit handling
* Cached latest result
* Staleness threshold
* Health status
* Manual disable switch

## Graceful degradation

| Failure               | Sanjiv response                      |
| --------------------- | ----------------------------------- |
| AIS unavailable       | Replay or last-known tracks         |
| GDELT unavailable     | Cached geopolitical signals         |
| PortWatch unavailable | Historical baseline                 |
| Price API unavailable | Latest value marked stale           |
| LLM unavailable       | Structured scenario form            |
| Optimiser timeout     | Exact-input cached plan with warning, otherwise no plan |
| Evidence missing      | Block unsupported metric            |

## Deterministic demo scenario

Keep one scenario fully tested and cached, but still run the parser and optimiser live.

---

# 14. Validation and testing

## Data tests

* Coordinate validity
* Timestamp ordering
* Duplicate AIS removal
* Vessel identity consistency
* Chokepoint-geofence intersection
* Destination normalisation
* Sanctions exact match
* Source freshness

## Scenario-model tests

* Supply mass balance
* Inventory cannot become negative without explicit shortage
* Closed route carries zero flow
* Increasing disruption cannot improve the no-response result
* Longer disruption should not create fewer total delays without an explainable rerouting effect
* Refinery throughput never exceeds capacity
* Reserve release never exceeds available inventory

## Optimisation tests

* Zero constraint violations
* Reproducible result for fixed inputs
* Feasible fallback when ideal plan is impossible
* Sanctioned vessels and suppliers excluded
* Incompatible grades excluded
* Supplier and corridor limits respected
* Total landed cost calculated consistently

## Agent tests

* Scenario extraction accuracy
* Invalid asset rejection
* Numerical-value extraction
* Citation completeness
* Hallucination-blocking tests
* Unsupported-claim rejection

## Historical backtesting

Create at least 20 replay cases across:

* Chokepoint closure
* Partial chokepoint disruption
* Port closure
* Supplier outage
* Sanctions event
* Refinery outage
* Demand surge
* Combined disruption
* False news spike
* AIS source failure

For every case measure:

* Detection lead time
* False positive rate
* Scenario runtime
* Optimiser runtime
* Shortfall reduction
* Cost increase
* Evidence coverage
* Recommendation stability

---

# 15. Success metrics

## Performance

* AIS ingest-to-map latency: target below 5 seconds at p95
* Scenario compilation: target below 2 seconds
* Fast simulation: target below 3 seconds
* Procurement optimisation: target below 4 seconds
* End-to-end recommendation: target below 10 seconds
* Map interaction: target 60 frames per second under expected vessel load

These are engineering targets, not claims, until measured.

## Model quality

* Mass-balance error: zero within numerical tolerance
* Optimiser constraint violations: zero
* Scenario reproducibility: 100% for fixed inputs
* Evidence coverage: 100% of decision KPIs
* Unsupported definitive vessel-cargo claims: zero
* Sanctions exact-identifier recall: 100% on test set

## Business-value metrics

* Shortfall reduction versus no action
* Additional cost per avoided shortage unit
* Inventory-cover extension
* Refinery-utilisation recovery
* Supplier-concentration reduction
* Corridor-concentration reduction
* Decision time saved

---

# 16. Exact demonstration scenarios

## Scenario 1 — Main scripted scenario

> “The Strait of Hormuz loses 100% capacity for 72 hours.”

Sanjiv should:

1. Parse the scenario.
2. Highlight the corridor.
3. Mark affected observed vessels.
4. Separately mark inferred India-bound vessels.
5. Calculate no-action consequences.
6. Show refinery and inventory effects.
7. Produce three procurement plans.
8. Produce reserve drawdown guidance.
9. Show candidate transport capacity.
10. Explain rejected options.
11. Display assumptions and evidence.
12. Show total computation time.

## Scenario 2 — Generality demonstration

> “Bab el-Mandeb traffic falls 60% for 14 days.”

Demonstrates:

* Alternative route around the Cape
* Additional distance
* Arrival delay
* Freight-cost pressure
* Emissions increase
* Supplier and route reallocation

## Scenario 3 — Multi-variable scenario

> “Hormuz capacity falls 50%, one refinery loses 20% capacity, and diesel demand increases 8% for ten days.”

Demonstrates that Sanjiv handles compound disruptions rather than one simple closure.

## Scenario 4 — Second commodity

> “Model a two-week LPG disruption through Hormuz.”

Demonstrates platform scalability.

## Scenario 5 — Judge-selected event

Allow:

* Any supported chokepoint
* Any duration
* Any capacity reduction
* Demand shock
* Supplier outage
* Refinery outage
* Reserve policy

Unsupported scenarios should return:

> “Sanjiv cannot model that asset with sufficient evidence yet.”

A controlled refusal is better than a fabricated answer.

---

# 17. The exact winning demo screen sequence

## First 10 seconds

Open directly on the live map.

Show:

* Moving tankers
* Current time
* AIS connection
* Message rate
* Risk corridors
* Data-freshness badges

Do not begin with slides or architecture.

## Seconds 10–20

Enter:

> “Iran closes the Strait of Hormuz for 72 hours.”

## Seconds 20–30

Show the structured scenario Sanjiv generated.

## Seconds 30–45

Animate affected corridor, vessels and supply paths.

## Seconds 45–60

Display:

* No-action shortfall
* Refinery utilization
* Inventory-cover impact
* Arrival delays

## Seconds 60–80

Display three response plans.

Select Balanced.

## Seconds 80–100

Show:

* Supplier reallocation
* Alternative routes
* Reserve-release schedule
* Candidate transport capacity
* Shortfall avoided
* Added cost

## Seconds 100–115

Open **Why this plan?**

Show objective, constraints, rejected alternatives and assumptions.

## Seconds 115–125

Open an evidence record.

Prove the number is traceable.

## Seconds 125–135

Display:

> Signal-to-recommendation: 7.4 seconds

Only show the actual measured value.

## Final section

Run the judge-selected scenario.

---

# 18. Features that make Sanjiv more than a normal dashboard

## Counterfactual comparison

Always show:

| Metric                 | No action | Sanjiv balanced plan |
| ---------------------- | --------: | ------------------: |
| Supply shortfall       |    Result |              Result |
| Refinery utilization   |    Result |              Result |
| Inventory cover        |    Result |              Result |
| Added procurement cost |        ₹0 |              Result |
| Corridor concentration |    Result |              Result |
| Reserve remaining      |    Result |              Result |

## Sensitivity controls

Judges can change:

* Duration
* Capacity loss
* Initial inventory
* Price premium
* Supplier availability
* Reserve floor

The recommendation updates immediately.

## Plan stability indicator

Show whether a small input change changes the recommendation significantly.

Example:

> Plan stability: High
> Same supplier mix selected in 86% of uncertainty runs.

## Confidence-aware recommendation

Instead of one answer:

> Recommended action with 78% model confidence.

Show what would change the plan:

* If disruption lasts beyond seven days
* If supplier capacity falls
* If freight premium exceeds threshold
* If reserve inventory is lower than assumed

## Decision checkpoint

Sanjiv should not autonomously release reserves or place orders.

Use:

* Recommend
* Review
* Approve
* Export action package
* Monitor

## Automatic briefing package

Generate:

* Executive one-page summary
* Procurement recommendation
* Reserve recommendation
* Risk map snapshot
* Assumption sheet
* Evidence appendix
* Machine-readable scenario JSON

---

# 19. Build sequence

## Phase 0 — Truth and data contract

Complete first:

* Evidence-record schema
* Truth classes
* Source freshness
* Scenario schema
* Route and asset IDs
* Assumption registry

**Completion gate:** Every sample KPI has a source or assumption.

## Phase 1 — Live maritime twin

Build:

* AIS backend connection
* Vessel normalisation
* Timescale storage
* Map
* Tanker filtering
* Geofences
* Track history
* Live/replay mode
* Sanctions matching

**Completion gate:** A vessel crossing a chokepoint is detected correctly and visible in the UI.

## Phase 2 — India energy network

Build:

* Supplier ports
* Indian ports
* Refineries
* Reserve sites
* Shipping routes
* Crude grades
* Compatibility matrix
* Baseline flows

**Completion gate:** The baseline network conserves supply and demand.

## Phase 3 — Scenario simulator

Build:

* Natural-language parser
* Scenario validation
* Edge-capacity disruptions
* Inventory calculations
* Refinery calculations
* No-action result
* Uncertainty ranges

**Completion gate:** All scenario-model invariants pass.

## Phase 4 — Procurement optimiser

Build:

* Supplier choices
* Grade compatibility
* Route availability
* Delivery windows
* Cost objective
* Risk objective
* Three plan types
* Rejected-option explanations

**Completion gate:** Zero constraint violations across the test library.

## Phase 5 — Reserve optimiser

Build:

* Site-level reserves
* Drawdown scheduling
* Minimum floors
* Refinery allocation
* Replenishment guidance

**Completion gate:** Reserve plans remain feasible across short and extended scenarios.

## Phase 6 — Risk intelligence

Build:

* GDELT features
* PortWatch anomalies
* AIS anomaly features
* Market indicators
* Risk contributions
* Alert generation

**Completion gate:** Backtest detection against historical cases.

## Phase 7 — Evidence Auditor

Build:

* Metric-level evidence links
* Unsupported-claim blocker
* Confidence calculation
* Formula versioning
* Audit trail

**Completion gate:** 100% of displayed decision metrics have provenance.

## Phase 8 — Advanced product layer

Build:

* LPG model
* Historical replay
* Satellite incident layer
* Carbon impact
* Collaboration and approval
* Briefing export
* Plan-monitoring screen

## Phase 9 — Hardening

Complete:

* Source-failure tests
* Rate-limit tests
* Replay fallback
* Performance testing
* Browser testing
* Demo rehearsal
* Unscripted-scenario testing
* Offline deployment package

---

# 20. Features not to fake

Sanjiv must never claim access to:

* Private refinery inventories
* Private procurement contracts
* Actual tanker charter availability
* Exact cargo ownership
* Proprietary spot-market quotations
* Confidential strategic-reserve fill levels
* Confirmed crude grade on every vessel

Where these values are unavailable, support manual upload or input and label them clearly.

Example:

```text
Current commercial inventory
Value: 8 days
Type: ASSUMPTION
Entered by: Demo operator
Editable: Yes
```

That transparency will strengthen the project under the hackathon’s explicit requirement that scenario assumptions be testable.

---

# 21. Final complete definition

The finished Sanjiv platform should deliver all of the following:

* Live tanker map
* Chokepoint geofencing
* Vessel-track history
* India-bound confidence
* Sanctions matching
* Chokepoint traffic anomaly detection
* Geopolitical event monitoring
* Infrastructure incident signals
* Natural-language scenario generation
* Editable scenario assumptions
* India energy-supply digital twin
* Crude-grade and refinery compatibility
* Inventory and refinery simulation
* No-action counterfactual
* Uncertainty simulation
* Costed procurement optimisation
* Three response strategies
* Candidate transport-capacity matching
* Strategic-reserve optimisation
* Crude and LPG support
* Evidence and assumption ledger
* Explainable recommendations
* Rejected-alternative explanations
* Historical replay
* Data-source failure fallback
* Executive briefing export
* Approval workflow
* Response-plan monitoring
* Measured signal-to-recommendation latency

The central product experience must remain simple:

> **A live threat appears—or a user types one. Sanjiv shows what is exposed, what happens without intervention, and the best defensible action to take.**

Everything else exists to make that answer **real, testable, fast and trustworthy**.

[1]: https://navcen.uscg.gov/ais-frequently-asked-questions "https://navcen.uscg.gov/ais-frequently-asked-questions"
[2]: https://aisstream.io/documentation.html "https://aisstream.io/documentation.html"
[3]: https://www.gdeltproject.org/data.html?source=post_page--------------------------- "https://www.gdeltproject.org/data.html?source=post_page---------------------------"
[4]: https://www.elibrary.imf.org/view/journals/001/2025/093/article-A001-en.xml "https://www.elibrary.imf.org/view/journals/001/2025/093/article-A001-en.xml"
[5]: https://firms.modaps.eosdis.nasa.gov/active_fire/ "https://firms.modaps.eosdis.nasa.gov/active_fire/"
[6]: https://ppac.gov.in/import-export "https://ppac.gov.in/import-export"
[7]: https://fred.stlouisfed.org/docs/api/fred/overview.html "https://fred.stlouisfed.org/docs/api/fred/overview.html"
[8]: https://ofac.treasury.gov/sanctions-list-service "https://ofac.treasury.gov/sanctions-list-service"
[9]: https://isprlindia.com/aboutus.asp "https://isprlindia.com/aboutus.asp"
[10]: https://uncomtrade.org/docs/un-comtrade-api/ "https://uncomtrade.org/docs/un-comtrade-api/"
