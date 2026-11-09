# Real Integration Roadmap for OpenCarbonChem Connectors

## Current State (Phase 0)
**Status**: All connectors (DEFRA, EPA, Ecoinvent) are **stub implementations** that return empty lists.
**Purpose**: Satisfy Milestone 11 deliverable requirement; provide unified interface; enable future integration.
**Data Source**: Synthetic datasets only (`review_status=illustrative`, `source_org=SYNTHETIC`).
**Tests**: the full suite passes without network dependencies.

---

## Phase 1: Public API Access (1-2 weeks)
**Goal**: Connect to freely available government databases.

### DEFRA (UK Government Conversion Factors)
- **Status**: ✅ Publicly accessible
- **Implementation**: HTTP GET requests to `https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting`
- **Authentication**: None required (public website)
- **Data Format**: HTML pages or JSON endpoints
- **Rate Limiting**: Polite delays between requests
- **Example Code**:
  ```python
  import requests
  def fetch_defra_factors(year=2024):
      url = f"https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting/{year}"
      response = requests.get(url, timeout=30)
      # Parse the response content
  ```

### EPA (Environmental Protection Agency AP-42)
- **Status**: ✅ Publicly accessible
- **Implementation**: HTTP requests to `https://www.epa.gov/air-emissions-factor-db`
- **Authentication**: None required (public database)
- **Data Format**: Searchable database, downloadable files
- **Rate Limiting**: Required (ETI - Empty Time Between requests)
- **Example Code**:
  ```python
  import requests
  import time
  def fetch_epa_factors(category, substance):
      url = "https://www.epa.gov/air-emissions-factor-db"
      # Search and download logic
      time.sleep(1)  # ETI compliance
  ```

### Ecoinvent
- **Status**: ❌ **Not available** in this phase
- **Reason**: Commercial proprietary database
- **Requirement**: Active commercial license + API credentials
- **Alternative**: Purchase license through ecoinvent.org

---

## Phase 2: Licensed Database Access (2-4 months)
**Goal**: Connect to paid/commercial data sources.

### Ecoinvent 3.x
- **Cost**: Commercial license (€€€ per year)
- **Access**: Web API or downloadable databases
- **Authentication**: API key + organization ID
- **Data Format**: JSON, CSV, or proprietary formats
- **Implementation Steps**:
  1. Purchase license from ecoinvent.org
  2. Obtain API credentials
  3. Implement `EcoinventConnector` with real API calls
  4. Handle rate limiting and pagination
  5. Map Ecoinvent categories to GHG Protocol categories
- **Estimated Effort**: 2-3 weeks development + license acquisition time

### Other Licensed Databases
- **GHG Protocol Sector Tools**: May have available data
- **ICCA Chemical Category Progress**: Industry-specific data
- **national inventories**: Country-specific emission factors

---

## Phase 3: Custom Data Source Integration (Ongoing)
**Goal**: Allow users to integrate their own data sources.

### Custom CSV/Excel Upload
- Drag-and-drop factor tables
- Map columns to internal format
- Validate against expected schema

### Database Connections
- PostgreSQL with emission_factor table
- MySQL connections
- SQLite databases
- API endpoints owned by organization

### Data Transformation Pipelines
- ETL scripts for converting external factor formats
- JSON schemas for different database outputs
- Validation rules and quality checks

---

## Phase 4: Deployment & Maintenance (Continuous)
**Goal**: Keep connectors working as APIs change.

### API Version Management
- Pin to specific API versions
- Deprecation warnings for older versions
- Automatic version detection

### Change Detection
- Weekly API status checks
- Automated tests for response format
- Changelog tracking for each connector

### Fallback Strategies
- Cache last-known-good data
- Graceful degradation to stub mode
- User notifications when APIs change

---

## Integration Priority Matrix

| Connector | Phase | Effort | Cost | Data Availability |
|-----------|-------|--------|------|-------------------|
| **DEFRA** | 1 | Low | Free | ✅ Public |
| **EPA** | 1 | Low | Free | ✅ Public |
| **Ecoinvent** | 2 | Medium | Paid | ❌ License Required |
| **Custom CSV** | 3 | Low | Free | ✅ User Provided |
| **Custom API** | 3 | Medium | Free | ✅ Organization API |

---

## Recommendations for OpenCarbonChem

### Immediate (Next 2 Weeks)
1. ✅ Keep current stub implementations (milestone requirement met)
2. ✅ Document the roadmap (this file)
3. ✅ Ensure all tests pass without network access
4. ✅ Maintain synthetic data framework for reproducibility

### Short-term (Next Month)
1. 🎯 Add DEPHA real API fetch (public, no cost)
2. 🎯 Add EPA real API fetch (public, no cost)
3. 📋 Test with actual HTML parsing of factor pages
4. 📋 Implement caching for repeated queries

### Medium-term (Next Quarter)
1. 💼 Evaluate Ecoinvent license cost/benefit
2. 💼 If licensed: implement real Ecoinvent integration
3. 💼 If not licensed: keep stub, document alternative paths
4. 📊 Add custom CSV upload feature for user factors

### Long-term (Ongoing)
1. 🔄 Monitor API changes and update connectors
2. 🔄 Add user-requested data sources
3. 🔄 Improve caching and performance
4. 🔄 Enhance error handling and fallbacks

---

## Migration Path from Synthetic to Real Data

### Current Workflow
```text
User loads synthetic data
→ Connectors return [] (stub)
→ PCF calculated with illustrative factors
→ Dashboard shows synthetic results
→ review_status=illustrative labeled
```

### After Phase 1 Integration
```text
User selects data source
→ DEPHA/EPA connectors fetch real factors
→ PCF calculated with actual emission factors
→ Dashboard shows real results
→ review_status can be updated (if verified)
→ Source tracking added to provenance
```

### After Phase 2 Integration
```text
If Ecoinvent license purchased:
→ EcoinventConnector fetches real LCA data
→ Expanded category coverage (full LC impact categories)
→ More granular Scope 3 factors
→ Higher data quality for product life-cycles
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| API changes break connectivity | Version pinning + automated tests |
| Rate limiting from government APIs | ETI compliance + caching |
| Data quality issues | Validation rules + user review |
| License costs exceed budget | Cost-benefit analysis before Phase 2 |
| Proprietary data restrictions | Clear licensing documentation |
| Synthetic data presented as real | `review_status=illustrative` labeling always |

---

## Success Metrics

- ✅ 0 test failures due to connector changes
- ✅ < 2 seconds average fetch time (after caching)
- ✅ 95%+ data validation success rate
- ✅ User satisfaction with data relevance
- ✅ Clear provenance tracking for all factors
- ✅ No unexpected API costs

---
*Roadmap version: 1.0 | Updated: 2026-11-05 | 
Part of OpenCarbonChem Milestone 11 Expansion Paths*