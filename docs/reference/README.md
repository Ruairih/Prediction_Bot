# Reference Documentation

This folder contains **detailed specifications and historical context**. These are reference materials - NOT prescriptive blueprints.

## How to Use This Folder

1. **Component CLAUDE.md files are your primary guide** - located in `src/polymarket_bot/{component}/CLAUDE.md`
2. **Use these specs for deeper understanding** - when you need more context on WHY something is designed a certain way
3. **Check gotchas before implementing** - `known_gotchas.md` has production bugs to avoid

## Trust Hierarchy

When in doubt, trust in this order:
1. **Code** - The actual implementation is the source of truth
2. **Component CLAUDE.md** - Each component's TDD guide
3. **Root CLAUDE.md** - Overall architecture and gotchas
4. **Reference docs** - This folder (detailed context, not prescriptive)

## Contents

### Critical Reading
- `known_gotchas.md` - Production bugs (G1-G6) and their fixes - **READ THIS FIRST**
- `architecture_decisions.md` - Why key design choices were made

### Detailed Specifications (Reference Only)
- `01_STORAGE_LAYER_SPEC.md` - Database, migrations, repositories
- `02_INGESTION_LAYER_SPEC.md` - REST/WebSocket clients, data fetching
- `03_STRATEGY_INTERFACE_SPEC.md` - Strategy protocol, signals, filters
- `04_CORE_AND_EXECUTION_SPEC.md` - Trading engine, order management
- `05_HEALTH_AND_SERVICES_SPEC.md` - Monitoring, alerting, dashboard

### Historical
- `past_iterations/` - Previous implementations for context
