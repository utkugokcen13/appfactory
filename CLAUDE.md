# App Factory - Automated Mobile App Production Pipeline

## Vision
Full-cycle automated mobile app generation powered by Claude:
1. **Ideation** - AI-driven app concept generation and validation
2. **Design** - UI/UX generation via Stitch/Figma MCP
3. **Code** - SwiftUI app scaffolding and implementation via Claude Code
4. **Ship** - Build, test, deploy pipeline

## Tech Stack
- **AI Backend:** Claude API via Amazon Bedrock (Opus 4.6/4.7)
- **Language:** Python 3.11+
- **AWS Region:** us-west-2
- **Target Platform:** iOS (SwiftUI)
- **Design Tools:** Figma MCP, Stitch
- **Package Manager:** pip / uv

## Architecture

```
appfactory/
├── CLAUDE.md              # This file - project context
├── .env                   # AWS credentials (gitignored)
├── requirements.txt       # Python dependencies
├── main.py                # Entry point - pipeline orchestrator
├── factory/
│   ├── __init__.py
│   ├── client.py          # Bedrock client wrapper
│   ├── ideation.py        # App concept generation & refinement
│   ├── design.py          # Figma/Stitch integration for UI generation
│   ├── codegen.py         # SwiftUI code generation via Claude
│   └── pipeline.py        # End-to-end pipeline orchestration
└── output/                # Generated app projects land here
```

## Pipeline Flow
```
[Idea Prompt] → Ideation Agent → App Spec
     → Design Agent → Figma Screens → MCP Export
     → CodeGen Agent → SwiftUI Project → Xcode Build
```

## Current Phase
**Phase 1: Foundation** - Bedrock client setup, API key validation, basic prompt pipeline

## AWS Bedrock Config
- Auth: AWS Access Key + Secret Key (stored in .env)
- Model ID: `global.anthropic.claude-opus-4-7`
- Region: `us-west-2`
- SDK: `anthropic[bedrock]`

## Rules
- Never hardcode credentials - always use .env
- Keep each pipeline stage independent and testable
- Log all API calls with token usage for cost tracking
- Output generated apps as complete Xcode project directories
- Use async/await for all Bedrock calls
